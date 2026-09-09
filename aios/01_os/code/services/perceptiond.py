# -*- coding: utf-8 -*-
"""perceptiond · 感知系统（M1 · T10 语义管线 v0）
- 订阅 evt.stream → ①授权检查（未授权源丢弃+计数，宪法 12.5）②语义字段补全
  （speaker="unknown"——异步人物绑定是 M2 认知系统职责）③转发 evt.normalized
- 保留 M0 回声链路（test_m0 回归保护）
"""
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

SNAPSHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "run", "privacy_snapshot.json")
svc = AIOSService("perceptiond", subscribe=["evt.stream", "evt.hub.echo"])
_drop = {"count": 0, "last_log": 0.0}


def auth_of(source):
    """读 privacyd 快照（带 mtime 缓存）。默认未授权——宪法 12.5 授权前置。"""
    try:
        mtime = os.path.getmtime(SNAPSHOT)
    except OSError:
        mtime = 0
    if not hasattr(auth_of, "_cache") or auth_of._mtime != mtime:
        try:
            with open(SNAPSHOT, encoding="utf-8") as f:
                auth_of._cache = json.load(f)
            auth_of._mtime = mtime
        except Exception:
            auth_of._cache = {}
    return auth_of._cache.get(source, "未授权")


def on_event(topic, from_svc, msg):
    if topic == "evt.hub.echo":                     # M0 回声链路（回归保护）
        svc.log("【回声链路OK】" + str(msg.get("content", "")))
        return
    if topic != "evt.stream":
        return
    ev = dict(msg or {})
    source = str(ev.get("source", "unknown"))
    # ① 授权检查：未授权 → 丢弃，只留计数（不落库不留内容）
    if auth_of(source) != "已授权":
        _drop["count"] += 1
        if time.time() - _drop["last_log"] > 5.0:
            svc.log(f"[隐私守卫] 未授权源 {source} 丢弃累计 {_drop['count']} 条")
            _drop["last_log"] = time.time()
        return
    # ② 语义字段补全（宪法 6.1 标准事件 + 认知五状态留待 M2）
    ev.setdefault("id", str(uuid.uuid4()))
    ev["ts"] = float(ev.get("ts") or time.time())
    ev.setdefault("speaker", "unknown")             # 人物绑定异步进行（C1）
    ev.setdefault("entities", [])
    ev.setdefault("mode_at_time", "unknown")        # modemgrd 接入后回填
    ev.setdefault("privacy_level", 1)               # 0=仅本地 1=脱敏可上云 2=可原样
    # ③ 转发标准化事件流
    svc.publish("evt.normalized", ev)


svc.on_event = on_event
svc.log("服务启动（M1 · 语义管线 v0：授权检查 + 字段补全）")
svc.run()
