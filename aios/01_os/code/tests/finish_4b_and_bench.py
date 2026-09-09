# -*- coding: utf-8 -*-
"""4B 双源断点续传（ModelScope → hf-mirror 回退）+ 2B/4B 基准完整启动"""
import json
import os
import subprocess
import sys
import time
import urllib.request

RT = r"D:\手镯开发\aios_runtime"
F4 = os.path.join(RT, "models", "Qwen3.5-4B-Q4_K_M.gguf")
TARGET = 2740039271   # 2614 MB 精确字节数（以 HEAD 为准的近似值）
CODE = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(CODE)
os.environ["PYTHONUTF8"] = "1"

# ---- 1) 双源续传 4B（每源最多 240s，交替直到完整）----
size = os.path.getsize(F4) if os.path.exists(F4) else 0
print(f"4B 当前: {size/1048576:.0f} MB / 目标 ~2614 MB", flush=True)
sources = [
    "https://modelscope.cn/models/unsloth/Qwen3.5-4B-GGUF/resolve/master/Qwen3.5-4B-Q4_K_M.gguf",
    "https://hf-mirror.com/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf",
]
for attempt in range(8):
    size = os.path.getsize(F4) if os.path.exists(F4) else 0
    if size >= 2730000000:          # ≈2.6GB 阈值
        print(f"[完成] {size/1048576:.0f} MB", flush=True)
        break
    src = sources[attempt % len(sources)]
    print(f"[尝试 {attempt+1}] 从 {size/1048576:.0f} MB 续传，源: {src.split('/')[2]}", flush=True)
    try:
        subprocess.run(["curl", "-sS", "-C", "-", "-L", "--max-time", "240",
                        "-o", F4, src], timeout=260)
    except subprocess.TimeoutExpired:
        print("  [超时] 切换源重试", flush=True)
    except Exception as e:
        print(f"  [错误] {e}", flush=True)
    time.sleep(2)

final = os.path.getsize(F4) if os.path.exists(F4) else 0
print(f"4B 最终: {final/1048576:.0f} MB", flush=True)

# ---- 2) 启动两个 llama-server（2B 8083 / 4B 8084，若 4B 已完整）----
if final >= 2730000000:
    subprocess.Popen([os.path.join(RT, "llama", "llama-server.exe"),
                      "-m", F4, "--host", "127.0.0.1", "--port", "8084",
                      "-c", "8192", "-np", "4", "-t", "6", "--alias", "qwen35-4b"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("llama-server 4B 已启动 (8084)", flush=True)
    time.sleep(15)

l2b = subprocess.Popen([os.path.join(RT, "llama", "llama-server.exe"),
                        "-m", os.path.join(RT, "models", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
                        "--host", "127.0.0.1", "--port", "8083",
                        "-c", "8192", "-np", "4", "-t", "6", "--alias", "qwen1.5b"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("llama-server 1.5B 已启动 (8083)", flush=True)
time.sleep(15)

# ---- 3) 重启 AIOS 栈 ----
aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=CODE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PYTHONUTF8="1"))
time.sleep(10)
print("AIOS 栈已重启", flush=True)

# ---- 4) 补跑 2B 剩余 108 题（T6 尾部）----
env2b = dict(os.environ, PYTHONUTF8="1", LLAMA_PORT="8083", COND_TAG="local2b",
             BENCH_RESULTS=os.path.join(CODE, "run", "bench1k", "results_2b.jsonl"),
             BENCH_NOISE="0")
r2 = subprocess.Popen([sys.executable, "-X", "utf8", "tests/run_1k.py"], cwd=CODE,
                      stdout=open(os.path.join(RT, "bench_2b_tail.log"), "w", encoding="utf-8"),
                      stderr=subprocess.STDOUT, env=env2b)
print(f"2B 补跑已启动 pid={r2.pid}", flush=True)
