import sqlite3, time, os, json, sys, resource, re
sys.path.insert(0,'/home/user/bench')
from b1_commit import SCHEMA, payload

PATH="/home/user/bench/big.db"
N=1_000_000

def build():
    if os.path.exists(PATH): return
    conn=sqlite3.connect(PATH); conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(SCHEMA)
    conn.execute("BEGIN")
    kw=[["妈妈","生日","礼物"],["老张","借钱","争执"],["加班","熬夜","心悸"],["跑步","操场","第一名"]]
    for i in range(N):
        p=json.loads(payload(i))
        if i%7==0:
            k=kw[i%4]
            p["payload"]["text"]=f"第{i}条记录：今天和{k[0]}聊到{k[1]}，顺便说起{k[2]}的事情，还有一些日常闲聊内容。"
        p["object_id"]=f"OBS-{i:09d}"
        conn.execute("INSERT INTO object_revisions VALUES(?,?,?,?,?,?,?,?)",
                     (p["object_id"],1,"observation","U001",i+1,"2026-03-01T10:00:01+00:00","2026-03-01T10:00:02+00:00",
                      json.dumps(p,ensure_ascii=False)))
        if i%50000==0: conn.commit(); print("  ...",i,flush=True)
    conn.commit()
    conn.execute("UPDATE world_meta SET value=? WHERE key='world_revision'",(str(N),)); conn.commit()
    conn.close(); print("built", os.path.getsize(PATH)/1e9, "GB")

def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024

def t(label, fn):
    t0=time.perf_counter(); r=fn(); dt=time.perf_counter()-t0
    print(f"{label}: {dt:.2f}s  rows={r}  peakRSS={rss():.0f} MB")
    return dt

# exact port of SQLiteWorldStore._list_payloads_historical dedup-in-python path
def hist_list(conn, as_of, object_type="observation"):
    sql=("SELECT object_id, revision, object_type, subject_id, recorded_at, payload_json "
         "FROM object_revisions WHERE world_revision<=? ORDER BY object_id, revision DESC")
    rows=conn.execute(sql,(as_of,)).fetchall()
    seen=set(); sel=[]
    for row in rows:
        oid=row[0]
        if oid in seen: continue
        seen.add(oid)
        if object_type is not None and row[2]!=object_type: continue
        sel.append((row[4], json.loads(row[5])))
    sel.sort(key=lambda x:x[0])
    return len(sel)

def like_scan(conn, kws):
    clauses=" AND ".join(["payload_json LIKE ?"]*len(kws))
    sql=f"SELECT object_id FROM object_revisions WHERE {clauses} LIMIT 50"
    return len(conn.execute(sql, tuple(f"%{k}%" for k in kws)).fetchall())

build()
conn=sqlite3.connect(PATH); conn.execute("PRAGMA journal_mode=WAL")
print("db GB:", os.path.getsize(PATH)/1e9)
print("--- A. historical snapshot list (as_of = N, full world) ---")
try:
    t("list_payloads(as_of=1e6)", lambda: hist_list(conn, N))
except MemoryError as e:
    print("MemoryError:", e)
print("--- B. historical snapshot list (as_of = 30 days ~= 100k) ---")
t("list_payloads(as_of=100k)", lambda: hist_list(conn, 100_000))
print("--- C. co-occurrence LIKE scan over payload_json ---")
t("LIKE [妈妈,生日,礼物]", lambda: like_scan(conn,["妈妈","生日","礼物"]))
print("--- D. build FTS5 external-content index ---")
t0=time.perf_counter()
conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts USING fts5(object_id UNINDEXED, text, tokenize='unicode61')")
conn.execute("BEGIN")
for i in range(0,N,20000):
    conn.executemany("INSERT INTO obs_fts(object_id,text) VALUES(?,?)",
        [(f"OBS-{j:09d}", json.loads(conn.execute("SELECT payload_json FROM object_revisions WHERE object_id=?",(f"OBS-{j:09d}",)).fetchone()[0])["payload"]["text"])
         for j in range(i,min(i+20000,N))])
    conn.commit()
print(f"FTS5 build: {time.perf_counter()-t0:.1f}s  extra_db={os.path.getsize(PATH)/1e9:.2f} GB")
def fts_co(conn,kws):
    q=" AND ".join(f'"{k}"' for k in kws)
    return len(conn.execute("SELECT object_id FROM obs_fts WHERE obs_fts MATCH ? LIMIT 50",(q,)).fetchall())
t("FTS5 co-occurrence [妈妈,生日,礼物]", lambda: fts_co(conn,["妈妈","生日","礼物"]))
t("FTS5 3kw w/ rowid join", lambda: len(conn.execute(
   "SELECT o.object_id FROM obs_fts f JOIN object_revisions o ON o.object_id=f.object_id WHERE obs_fts MATCH ? LIMIT 50",
   ('"妈妈" AND "生日" AND "礼物"',)).fetchall()))
