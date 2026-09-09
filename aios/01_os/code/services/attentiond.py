# -*- coding: utf-8 -*-
"""attentiond · 注意力引擎（M2 · T15 算力租约发放/回收 v0）
契约：tasks/contracts_m2.md §T15
- 租约表（内存）：{lease_id: {event_id, deadline, state}}，state ∈ ACTIVE/RELEASED/EXPIRED
- 订阅 evt.stream / sys.lease.request / sys.lease.release
- sys.lease.request {req_id, event_id, budget_ms} → 签发 uuid 租约，deadline=now+budget_ms/1000
  → 回 evt.query.reply.<req_id> {lease_id, deadline, budget_ms}
- sys.lease.release {lease_id} → 存在则置 RELEASED → 回 {released:true}；不存在回 {released:false}
- 后台线程每 0.2s 扫描 ACTIVE 且 now>deadline → 置 EXPIRED → 发布 evt.lease.expired {lease_id, event_id}
- 每次变更后全量重写 run/lease_stats.json {granted, active, released, expired}
- 对 evt.stream：v0 被动，不自动发租约
"""
import json
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_PATH = os.path.join(ROOT, "run", "lease_stats.json")

svc = AIOSService("attentiond", subscribe=["evt.stream", "sys.lease.request", "sys.lease.release"])


class LeaseEngine:
    """租约签发/释放/过期核心逻辑（与总线解耦，publish 可注入便于单测）。"""

    def __init__(self, publish=None, stats_path=STATS_PATH):
        self.leases = {}            # lease_id -> {event_id, deadline, state}
        self.stats = {"granted": 0, "active": 0, "released": 0, "expired": 0}
        self.publish = publish or (lambda topic, msg: None)
        self.stats_path = stats_path
        self.lock = threading.Lock()

    def _write_stats_locked(self):
        """全量重写 stats 文件（调用方需已持锁）。"""
        try:
            os.makedirs(os.path.dirname(self.stats_path), exist_ok=True)
            with open(self.stats_path, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False)
        except Exception:
            pass

    def write_stats(self):
        with self.lock:
            self._write_stats_locked()

    def request(self, req_id, event_id, budget_ms):
        """签发租约并回执。返回 lease_id。"""
        lease_id = str(uuid.uuid4())
        deadline = time.time() + float(budget_ms) / 1000.0
        with self.lock:
            self.leases[lease_id] = {"event_id": event_id, "deadline": deadline, "state": "ACTIVE"}
            self.stats["granted"] += 1
            self.stats["active"] += 1
            self._write_stats_locked()
        self.publish(f"evt.query.reply.{req_id}",
                     {"lease_id": lease_id, "deadline": deadline, "budget_ms": budget_ms})
        return lease_id

    def release(self, lease_id):
        """释放租约：存在则置 RELEASED（幂等），不存在返回 False。"""
        with self.lock:
            rec = self.leases.get(lease_id)
            if rec is None:
                return False
            if rec["state"] == "ACTIVE":
                rec["state"] = "RELEASED"
                self.stats["active"] -= 1
                self.stats["released"] += 1
                self._write_stats_locked()
            # 已 RELEASED / EXPIRED：存在即 released:true，无副作用
            return True

    def expire_due(self, now=None):
        """扫描 ACTIVE 且 now>deadline 的租约 → EXPIRED，并逐条发布事件。返回过期列表。"""
        now = time.time() if now is None else now
        expired = []
        with self.lock:
            for lease_id, rec in self.leases.items():
                if rec["state"] == "ACTIVE" and now > rec["deadline"]:
                    rec["state"] = "EXPIRED"
                    self.stats["active"] -= 1
                    self.stats["expired"] += 1
                    expired.append((lease_id, rec["event_id"]))
            if expired:
                self._write_stats_locked()
        for lease_id, event_id in expired:
            self.publish("evt.lease.expired", {"lease_id": lease_id, "event_id": event_id})
        return expired


engine = LeaseEngine(publish=svc.publish)


def on_event(topic, from_svc, msg):
    if topic == "sys.lease.request":
        req_id = str(msg.get("req_id") or uuid.uuid4())
        engine.request(req_id, msg.get("event_id"), msg.get("budget_ms", 0))
    elif topic == "sys.lease.release":
        req_id = msg.get("req_id")
        released = engine.release(str(msg.get("lease_id", "")))
        if req_id:
            svc.publish(f"evt.query.reply.{req_id}", {"released": released})
        else:
            svc.publish("evt.lease.released", {"lease_id": msg.get("lease_id"), "released": released})
    # evt.stream：v0 被动，不自动发租约


svc.on_event = on_event


def _expiry_tick():
    while True:
        time.sleep(0.2)
        try:
            engine.expire_due()
        except Exception as e:
            svc.log(f"[异常] 租约过期扫描: {e}")


if __name__ == "__main__":
    svc.log("服务启动（M2 · 租约发放/回收 v0）")
    engine.write_stats()   # 落一份初始全零计数，保证 lease_stats.json 常驻
    threading.Thread(target=_expiry_tick, daemon=True).start()
    svc.run()
