# -*- coding: utf-8 -*-
"""entityd · 空壳（实体系统：人/地/物/关系）
职责：接入总线、心跳常亮、记录收到的事件（业务逻辑 M1-M3 落地）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

svc = AIOSService("entityd", subscribe=["evt.#"])
_counter = {"n": 0}


def on_event(topic, from_svc, msg):
    _counter["n"] += 1
    if _counter["n"] <= 3 or _counter["n"] % 50 == 0:   # 限频日志：防日志拖慢流水线
        svc.log(f"收到 {topic} 来自 {from_svc}: {msg.get('content', '')} (累计 {_counter['n']})")


svc.on_event = on_event
svc.log("服务启动（空壳）")
svc.run()
