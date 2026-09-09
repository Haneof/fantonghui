# -*- coding: utf-8 -*-
"""重启 AIOS（PYTHONUTF8=1 环境）→ 推送 90 天数据集 → 触发摘要 → 报告"""
import json, os, subprocess, sys, time

os.environ["PYTHONUTF8"] = "1"
ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)

# 1) 停旧栈（精准清理：只杀 aiosd/bus/服务进程树，不能误杀调用者自身）
subprocess.run(['powershell', '-Command',
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -match 'aiosd|aios_busd|services[/\\\\]' } | "
    "ForEach-Object { taskkill /T /F /PID $_.ProcessId }"], capture_output=True)
time.sleep(1)

# 2) 起新栈（aiosd 会给全部子进程注入 PYTHONUTF8=1）
aiosd = subprocess.Popen([sys.executable, "aiosd/aiosd.py"], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PYTHONUTF8="1"))
print(f"aiosd 新实例 pid={aiosd.pid}")

def load_health():
    try:
        return json.load(open(os.path.join(ROOT, "run", "health.json"), encoding="utf-8"))
    except Exception:
        return None

deadline = time.time() + 20
ready = False
while time.time() < deadline:
    h = load_health()
    if h and h.get("bus", {}).get("state") == "up":
        if all(v.get("state") == "up" for v in h.get("services", {}).values()):
            ready = True
            break
    time.sleep(0.3)
print(f"全栈就绪: {ready}")
assert ready

# 3) 授权 + 清计数基线
import socket, sqlite3, uuid
c = socket.create_connection(("127.0.0.1", 7800), timeout=5)
c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(obj): c.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
send({"t": "hello", "service": "dataset-driver"})
time.sleep(0.3)
send({"t": "pub", "topic": "sys.privacy.set", "msg": {"source": "sim", "state": "已授权"}})
time.sleep(0.3)

def db_count():
    try:
        conn = sqlite3.connect(f"file:{os.path.join(ROOT, 'run', 'life_tree.db')}?mode=ro", uri=True)
        n = conn.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0

start_n = db_count()
script = json.load(open(os.path.join(ROOT, "simulator", "scripts", "life_90days.json"), encoding="utf-8"))
print(f"推送前 {start_n} 条 | 本批 {len(script)} 条")

# 4) 推送（simd stdout 到 UTF-8 文件）
logf = open(os.path.join(ROOT, "run", "simd_90days.log"), "w", encoding="utf-8")
t0 = time.time()
simd = subprocess.Popen([sys.executable, "simulator/simd.py", "--script",
                         os.path.join(ROOT, "simulator", "scripts", "life_90days.json"),
                         "--loop", "1"], cwd=ROOT, stdout=logf,
                        stderr=subprocess.DEVNULL, env=dict(os.environ, PYTHONUTF8="1"))
last, last_t = start_n, t0
while True:
    time.sleep(5)
    n = db_count()
    now = time.time()
    rate = (n - last) / max(0.001, now - last_t)
    elapsed = now - t0
    alive = simd.poll() is None
    stats = {}
    try:
        stats = json.load(open(os.path.join(ROOT, "run", "bus_stats.json"), encoding="utf-8"))
    except Exception:
        pass
    qtotal = sum(v.get("qsize", 0) for v in stats.get("services", {}).values())
    print(f"t+{elapsed:5.1f}s | 人生树 {n} | 速率 {rate:.0f}/s | 队列积压 {qtotal} | simd存活={alive}")
    last, last_t = n, now
    # 退出条件：simd 完成且（a）库内数量达标 或（b）队列已清空且计数稳定
    if not alive:
        stable = (n == last or (n - last) < 5) and qtotal == 0
        if n >= start_n + len(script) - 2 or (stable and elapsed > 20):
            time.sleep(2)
            n = db_count()
            break
    if elapsed > 420:
        break

# 5) 摘要
send({"t": "pub", "topic": "sys.cmd.summarize", "msg": {}})
time.sleep(4)
n = db_count()
dt = time.time() - t0
print(f"最终：人生树 {n} 条（本批入库 +{n - start_n}）| 总耗时 {dt:.1f}s | 平均吞吐 {(n - start_n)/dt:.0f} 条/秒")
conn = sqlite3.connect(f"file:{os.path.join(ROOT, 'run', 'life_tree.db')}?mode=ro", uri=True)
s = conn.execute("SELECT COUNT(*) FROM summary").fetchone()[0]
by = conn.execute("SELECT type, COUNT(*) FROM raw_log GROUP BY type ORDER BY 2 DESC").fetchall()
conn.close()
print(f"小时摘要 {s} 份 | 类型分布: {by}")
simd_ok = simd.poll() == 0
print(f"simd 退出码: {simd.poll()}（0=全部回放完成）")
c.close()
