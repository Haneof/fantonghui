# -*- coding: utf-8 -*-
"""启动 llama-server（等待模型加载完成）+ 真模型探针"""
import json
import os
import subprocess
import sys
import time
import urllib.request

RT = r"D:\手镯开发\aios_runtime"
MODEL = os.path.join(RT, "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
EXE = os.path.join(RT, "llama", "llama-server.exe")
PORT = 8081

err_log = open(os.path.join(RT, "llama_err.log"), "w", encoding="utf-8", errors="replace")
proc = subprocess.Popen([EXE, "-m", MODEL, "--host", "127.0.0.1", "--port", str(PORT),
                         "-c", "4096", "-t", "6", "--alias", "qwen0.5b"],
                        stdout=err_log, stderr=err_log)
print(f"llama-server pid={proc.pid} 加载模型中...")

deadline = time.time() + 60
loaded = False
while time.time() < deadline:
    if proc.poll() is not None:
        print("[失败] llama-server 进程退出")
        err_log.close()
        with open(os.path.join(RT, "llama_err.log"), encoding="utf-8", errors="replace") as f:
            print("\n".join(f.readlines()[-6:]))
        sys.exit(1)
    time.sleep(3)
    err_log.flush()
    # 从日志判断加载完成（server 监听行）
    try:
        with open(os.path.join(RT, "llama_err.log"), encoding="utf-8", errors="replace") as f:
            content = f.read()
        if "listening" in content or "server is listening" in content:
            loaded = True
            print("模型加载完成，server 监听中")
            break
    except Exception:
        pass

if not loaded:
    # 兜底：直接探针
    print("日志未捕获监听标记，直接探针...")

ok = False
answer = ""
for attempt in range(5):
    try:
        body = json.dumps({"model": "qwen0.5b", "messages": [
            {"role": "user", "content": "用一句话介绍你自己"}]}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
                                     data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answer = data["choices"][0]["message"]["content"]
        ok = True
        break
    except Exception as e:
        print(f"探针尝试 {attempt+1} 失败: {e}")
        time.sleep(3)

print("本地真模型:", "在线 ✅" if ok else "离线 ❌")
print("回答:", answer)
err_log.close()
