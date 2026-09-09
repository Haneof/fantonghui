# -*- coding: utf-8 -*-
"""privacyd · 隐私守卫（M1 · T13 授权状态机 v0）
- 契约：宪法新增第十二章（授权前置/状态机/用户四权）
- 订阅 sys.privacy.set {source, state} → 更新 privacy_state.json +
  写 privacy_snapshot.json（perceptiond 读取执行）+ 发布 evt.privacy.changed
- 新数据源默认【未授权】——宪法 12.5 授权前置，不做静默采集
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(ROOT, "run")
STATE_PATH = os.path.join(RUN_DIR, "privacy_state.json")
SNAPSHOT_PATH = os.path.join(RUN_DIR, "privacy_snapshot.json")
VALID = ("未授权", "已授权", "已暂停", "已撤销")

svc = AIOSService("privacyd", subscribe=["sys.privacy.set", "sys.privacy.get"])
_lock = threading.Lock()


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    os.makedirs(RUN_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)
    snap = STATE_PATH + ".tmp"
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(snap, SNAPSHOT_PATH)


def on_event(topic, from_svc, msg):
    if topic == "sys.privacy.set":
        source = str((msg or {}).get("source", "")).strip()
        state = str((msg or {}).get("state", "")).strip()
        if not source or state not in VALID:
            svc.log(f"[拒绝] 非法授权请求 source={source!r} state={state!r} 来自 {from_svc}")
            return
        with _lock:
            state_map = load_state()
            old = state_map.get(source, "未授权")
            state_map[source] = state
            save_state(state_map)
        svc.log(f"[授权变更] {source}: {old} → {state}（请求方 {from_svc}）")
        svc.publish("evt.privacy.changed", {"source": source, "old": old,
                                            "state": state, "by": from_svc})
    elif topic == "sys.privacy.get":
        req_id = str((msg or {}).get("req_id", "0"))
        svc.publish(f"evt.query.reply.{req_id}", {"state": load_state()})


svc.on_event = on_event
save_state(load_state())          # 启动即落快照（全量默认未授权）
svc.log("服务启动（M1 · 授权状态机 v0：新数据源默认未授权）")
svc.run()
