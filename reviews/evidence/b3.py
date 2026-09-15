import sqlite3, time, os, json, sys, resource
PATH="/home/user/bench/big.db"
LOG=open("/home/user/bench/results.txt","w")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
conn=sqlite3.connect(PATH); conn.execute("PRAGMA journal_mode=WAL")
log("db size GB:", round(os.path.getsize(PATH)/1e9,3))
log("rows:", conn.execute("SELECT count(*) FROM object_revisions").fetchone()[0])

def hist_rows_and_mem(as_of):
    """Replicates _list_payloads_historical: fetchall + python dedup + json.loads each payload."""
    sql=("SELECT object_id, revision, object_type, subject_id, recorded_at, payload_json "
         "FROM object_revisions WHERE world_revision<=? ORDER BY object_id, revision DESC")
    t0=time.perf_counter(); rows=conn.execute(sql,(as_of,)).fetchall()
    t_fetch=time.perf_counter()-t0; m_after_fetch=rss()
    seen=set(); sel=[]
    t1=time.perf_counter()
    for row in rows:
        if row[0] in seen: continue
        seen.add(row[0]); sel.append((row[4], json.loads(row[5])))
    t_decode=time.perf_counter()-t1
    sel.sort(key=lambda x:x[0])
    del rows
    return len(sel), t_fetch, t_decode, m_after_fetch, rss()

for as_of in (10_000, 100_000, 300_000):
    n,tf,td,mf,mt = hist_rows_and_mem(as_of)
    log(f"A. historical list as_of={as_of}: objects={n} fetchall={tf:.2f}s json_decode={td:.2f}s total={tf+td:.2f}s peakRSS={mt:.0f}MB")
