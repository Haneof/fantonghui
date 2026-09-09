# -*- coding: utf-8 -*-
"""4B 干净测速探针"""
import json
import time
import urllib.request

URL = "http://127.0.0.1:8084/v1/chat/completions"


def probe(prompt, max_tokens, tag):
    body = json.dumps({"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        j = json.loads(r.read())
    dt = time.time() - t0
    txt = j["choices"][0]["message"]["content"]
    usage = j.get("usage", {})
    ct = usage.get("completion_tokens", "?")
    print(f"[{tag}] 耗时 {dt:.1f}s | 生成 {ct} tok | 速度 {ct/dt if dt else 0:.1f} tok/s | 回答: {txt[:60]}")


probe("回答一个字：好", 8, "tiny")
probe("07月10日 19:48 楼下快餐 ¥28。问：7月10日晚上吃了什么？只答店名或“没有”。", 60, "bench-like")
probe("请把下面这句话压缩成10个字以内的小结：林川今天上午去工地干活，中午吃了外卖炒饭，下午开会讨论了AIOS项目的交付时间表，晚上和张总确认了下周三的评审安排。", 80, "summarize")
