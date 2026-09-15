import sqlite3, time, os, json, sys, resource, subprocess
PATH="/home/user/bench/big.db"
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
conn=sqlite3.connect(PATH); conn.execute("PRAGMA journal_mode=WAL")
N=conn.execute("SELECT count(*) FROM object_revisions").fetchone()[0]

# --- 1M full-world snapshot, capped at 3.2GB to capture OOM instead of dying silently
import ctypes
def hist(as_of, cap_bytes):
    code = f'''
import sqlite3,time,json,resource
conn=sqlite3.connect("{PATH}")
sql=("SELECT object_id, revision, object_type, subject_id, recorded_at, payload_json "
     "FROM object_revisions WHERE world_revision<=? ORDER BY object_id, revision DESC")
t0=time.perf_counter(); rows=conn.execute(sql,({as_of},)).fetchall(); t1=time.perf_counter()-t0
m1=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
seen=set(); sel=[]
t2=time.perf_counter()
for r in rows:
    if r[0] in seen: continue
    seen.add(r[0]); sel.append((r[4], json.loads(r[5])))
t3=time.perf_counter()-t2
print(f"OK objects={{len(sel)}} fetch={{t1:.2f}}s decode={{t3:.2f}}s total={{t1+t3:.2f}}s peakRSS_after_fetch={{m1:.0f}}MB peakRSS_final={{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}}MB")
'''
    p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,
                     preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_AS,(cap_bytes,cap_bytes)))
    if p.returncode!=0:
        tail=(p.stderr.strip().splitlines() or ["?"])[-1]
        log(f"B. as_of={as_of} (cap {cap_bytes/1e9:.1f}GB): FAILED rc={p.returncode} -> {tail}")
    else:
        log(f"B. as_of={as_of}: {p.stdout.strip()}")

hist(1_000_000, int(3.2e9))

# --- co-occurrence search: naive LIKE full scan (no index possible)
def like(kws, limit=50):
    clauses=" AND ".join(["payload_json LIKE ?"]*len(kws))
    t0=time.perf_counter()
    rows=conn.execute(f"SELECT object_id FROM object_revisions WHERE {clauses} LIMIT {limit}",
                      tuple(f"%{k}%" for k in kws)).fetchall()
    return len(rows), time.perf_counter()-t0
for kws in (["妈妈","生日","礼物"],["加班","熬夜","心悸"],["不存在关键词XYZ","生日","礼物"]):
    n,dt=like(kws)
    log(f"C. LIKE co-occurrence {kws}: hits={n} time={dt:.2f}s")
