# -*- coding: utf-8 -*-
"""Gemini API 轮换池（T24 · 原生 generateContent 端点版）
- 15 key 轮换 + 每键限速 + 429/配额冷却自动切换 + 失效键标记
- 端点：https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  认证：x-goog-api-key 头（已实测可用，模型列表 50 个）
- 密钥文件：run/api_keys.json（运行时配置，不入仓库）
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS_PATH = os.path.join(ROOT, "run", "api_keys.json")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class PoolExhausted(Exception):
    pass


class GeminiPool:
    def __init__(self, keys_path=KEYS_PATH, model="gemini-flash-latest",
                 min_interval_s=4.0, timeout_s=45, max_inflight=4):
        self.model = model
        self.min_interval_s = min_interval_s      # 每键最小调用间隔（免费档限速保护）
        self.timeout_s = timeout_s
        self._keys = []
        self._lock = threading.Lock()
        self._rr = 0
        self._inflight_sem = threading.Semaphore(max_inflight)
        self.load_keys(keys_path)

    def load_keys(self, path):
        keys = []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("keys", data) if isinstance(data, dict) else data
            for k in raw:
                if isinstance(k, str) and len(k) > 10:
                    keys.append({"key": k, "calls": 0, "errors": 0, "last_call": 0.0,
                                 "cooldown_until": 0.0, "dead": False})
        except Exception:
            pass
        with self._lock:
            self._keys = keys

    def _pick(self):
        """轮换选择：非冷却、距上次调用超过 min_interval 的键；无可用返回 None。"""
        now = time.time()
        n = len(self._keys)
        for i in range(n):
            k = self._keys[(self._rr + i) % n]
            if k["dead"] or now < k["cooldown_until"]:
                continue
            if now - k["last_call"] < self.min_interval_s:
                continue
            self._rr = (self._rr + i + 1) % n
            return k
        alive = [k for k in self._keys if not k["dead"] and now >= k["cooldown_until"]]
        if not alive:
            return None
        return min(alive, key=lambda k: k["last_call"])

    def stats(self):
        with self._lock:
            return [{"key": k["key"][:12] + "...", "calls": k["calls"], "errors": k["errors"],
                     "dead": k["dead"],
                     "cooling": max(0.0, k["cooldown_until"] - time.time())}
                    for k in self._keys]

    def chat(self, system, user, max_rounds=None):
        """带轮换重试的原生 generateContent。成功返回文本；全部键不可用抛 PoolExhausted。"""
        rounds = max_rounds or max(1, len(self._keys))
        url = f"{BASE}/{self.model}:generateContent"
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]}},
            ensure_ascii=False).encode("utf-8")
        last_err = "无可用密钥"
        with self._inflight_sem:
            for attempt in range(rounds):
                with self._lock:
                    k = self._pick()
                if k is None:
                    time.sleep(1.0)
                    last_err = "全部密钥冷却/限速中"
                    continue
                req = urllib.request.Request(
                    url, data=body, method="POST",
                    headers={"Content-Type": "application/json",
                             "x-goog-api-key": k["key"]})
                k["calls"] += 1
                k["last_call"] = time.time()
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text
                except urllib.error.HTTPError as e:
                    k["errors"] += 1
                    detail = e.read().decode("utf-8", "replace")[:200]
                    if e.code in (429, 500, 503):
                        k["cooldown_until"] = time.time() + 30      # 限速冷却 30s
                        last_err = f"HTTP {e.code}（冷却换键）"
                    elif e.code in (401, 403):
                        k["dead"] = True                            # 键失效
                        last_err = f"HTTP {e.code} 键失效"
                    else:
                        last_err = f"HTTP {e.code}: {detail}"
                        if e.code == 404:
                            last_err = f"HTTP 404 模型不存在: {self.model}"
                            raise PoolExhausted(last_err)           # 模型名错误不重试
                except Exception as e:
                    k["errors"] += 1
                    last_err = str(e)
                    k["cooldown_until"] = time.time() + 5
        raise PoolExhausted(last_err)
