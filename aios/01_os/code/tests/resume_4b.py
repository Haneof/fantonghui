# -*- coding: utf-8 -*-
"""4B 模型断点续传循环：直到文件完整（2614MB）才退出，断线自动重试"""
import os
import subprocess
import time

RT = r"D:\手镯开发\aios_runtime"
F = os.path.join(RT, "models", "Qwen3.5-4B-Q4_K_M.gguf")
URL = "https://modelscope.cn/models/unsloth/Qwen3.5-4B-GGUF/resolve/master/Qwen3.5-4B-Q4_K_M.gguf"
TARGET = 2614 * 1024 * 1024
LOG = os.path.join(RT, "dl_4b.log")

attempt = 0
while True:
    attempt += 1
    size = os.path.getsize(F) if os.path.exists(F) else 0
    if size >= TARGET * 0.999:
        print(f"[完成] {size/1048576:.0f} MB", flush=True)
        break
    if attempt > 40:
        print("[放弃] 40 次尝试未完成", flush=True)
        break
    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(f"{time.strftime('%H:%M:%S')} attempt {attempt}: 从 {size/1048576:.0f}MB 续传\n")
    subprocess.run(["curl", "-sS", "-C", "-", "-L", "--retry", "3", "--retry-delay", "2",
                    "--connect-timeout", "20", "-o", F, URL], timeout=600)
    time.sleep(3)
