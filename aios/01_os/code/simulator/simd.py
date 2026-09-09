# -*- coding: utf-8 -*-
"""simd · M0 模拟事件源（T05）
契约：tasks/contracts.md §2 —— 以服务名 simd 接入总线，按剧本发布事件
用法：python simulator/simd.py --script simulator/scripts/m0_smoke.json --loop 1
剧本条目：{"delay_s":0.5,"topic":"evt.sim.vital","event":{"id":"","ts":0,"source":"sim","type":"vital","content":"..."}}
  ts=0 → 发布时自动填当前时间；id 为空 → 自动 uuid4
"""
import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService


def load_script(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_script(svc, entries, loop):
    for round_no in range(1, loop + 1):
        for item in entries:
            delay = float(item.get("delay_s", 0))
            if delay > 0:
                time.sleep(delay)
            ev = dict(item.get("event", {}))
            if not ev.get("id"):
                ev["id"] = str(uuid.uuid4())
            if not ev.get("ts"):
                ev["ts"] = time.time()
            topic = item["topic"]
            svc.publish(topic, ev)
            print(f"[simd r{round_no}] -> {topic}: {ev.get('content', '')}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--loop", type=int, default=1)
    args = ap.parse_args()
    entries = load_script(args.script)
    svc = AIOSService("simd")
    import threading
    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(0.6)  # 等连接建立
    run_script(svc, entries, args.loop)
    time.sleep(0.3)
    svc.close()
    print("[simd] 剧本回放完成", flush=True)
