# -*- coding: utf-8 -*-
"""modelrouterd v2 · 模型路由（T24 真实接入）
- 本地：llama-server（llama.cpp OpenAI 兼容端点 127.0.0.1:8080）
- 云端：Gemini 轮换池（15 key，OpenAI 兼容端点）
- 离线/失败降级队列保持不变
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService
from api_pool.gemini_pool import GeminiPool, PoolExhausted

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(ROOT, "run")
DEGRADE = os.path.join(RUN_DIR, "model_degrade.json")
LOCAL_URL = "http://127.0.0.1:8081/v1/chat/completions"   # llama-server（8080 被 sub2api 占用）

svc = AIOSService("modelrouterd", subscribe=["sys.model.request", "sys.model.set_offline", "evt.normalized"])
offline = {"flag": False}
local_alive = {"flag": False, "checked": 0.0}
pool = GeminiPool(model="gemini-flash-latest")   # 新账号可用模型（2.5 对新用户已下线）

def _http_json(url, body, timeout, auth=None):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + auth
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def local_chat(system, user, timeout=30):
    """llama-server OpenAI 兼容调用。失败抛异常。"""
    data = _http_json(LOCAL_URL, {"model": "local", "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout)
    return data["choices"][0]["message"]["content"]

def local_alive_probe():
    """每 10s 探测一次本地 llama-server；失败视为不存活。"""
    if time.time() - local_alive["checked"] < 10:
        return local_alive["flag"]
    local_alive["checked"] = time.time()
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            local_alive["flag"] = (resp.status == 200)
    except Exception:
        local_alive["flag"] = False
    return local_alive["flag"]

def route(task_type, payload):
    """路由决策：简单→本地真模型；复杂→云端 Gemini；均失败→本地桩；离线→降级队列。"""
    if offline["flag"]:
        return "degraded_queued", None
    if task_type in ("simple_judgment", "summarize"):
        if local_alive_probe():
            return "local_llama", None        # 走真本地模型
        return "local_stub", "（本地模型未启动，规则桩结果）"
    if task_type in ("complex_reason", "deep_chat"):
        return "cloud_gemini", None           # 走 Gemini 轮换池
    return "local_stub", None

def on_event(topic, from_svc, msg):
    if topic == "sys.model.request":
        req_id = (msg or {}).get("req_id", "0")
        task_type = (msg or {}).get("task_type", "simple_judgment")
        payload = (msg or {}).get("payload", "")
        system = "你是 AIOS 腕上终端的本地认知引擎，用中文简洁回答。"
        try:
            routed, stub = route(task_type, payload)
            if routed == "degraded_queued":
                result = None
            elif routed == "local_llama":
                result = local_chat(system, str(payload))
            elif routed == "cloud_gemini":
                result = pool.chat(system, str(payload))
            else:
                result = f"{stub or ''}[规则桩]"
            if routed == "degraded_queued":
                with open(DEGRADE, "r+", encoding="utf-8") as f:
                    try:
                        arr = json.load(f)
                    except Exception:
                        arr = []
                    arr.append({"task_type": task_type, "payload": str(payload)[:500], "ts": time.time()})
                    f.seek(0); json.dump(arr, f, ensure_ascii=False); f.truncate()
            svc.publish(f"evt.query.reply.{req_id}",
                        {"routed": routed, "task_type": task_type, "result": result})
            svc.log(f"[路由] {task_type} → {routed}")
        except PoolExhausted as e:
            svc.publish(f"evt.query.reply.{req_id}",
                        {"routed": "exhausted", "task_type": task_type, "result": str(e)})
            svc.log(f"[路由失败] 池耗尽: {e}")
        except Exception as e:
            svc.publish(f"evt.query.reply.{req_id}",
                        {"routed": "error", "task_type": task_type, "result": str(e)})
            svc.log(f"[异常] {e}")
    elif topic == "sys.model.set_offline":
        offline["flag"] = bool((msg or {}).get("offline"))
        svc.log(f"[模式] 离线={offline['flag']}")
        svc.publish("evt.model.offline", {"offline": offline["flag"]})

svc.on_event = on_event
svc.log("服务启动（M3.5 · 真实接入：本地 llama-server + 云端 Gemini 轮换池）")
svc.run()
