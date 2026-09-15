import sqlite3, time, os, json, sys, resource
PATH="/home/user/bench/big.db"
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
conn=sqlite3.connect(PATH); conn.execute("PRAGMA journal_mode=WAL")
base=os.path.getsize(PATH)

t0=time.perf_counter()
conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts USING fts5(object_id UNINDEXED, text, tokenize='unicode61')")
cur=conn.execute("SELECT object_id, payload_json FROM object_revisions")
batch=[]; ins=0
while True:
    rows=cur.fetchmany(20000)
    if not rows: break
    for oid,pj in rows:
        batch.append((oid, json.loads(pj)["payload"]["text"]))
    if len(batch)>=20000:
        conn.executemany("INSERT INTO obs_fts(object_id,text) VALUES(?,?)",batch); batch=[]; ins+=20000
        conn.commit()
if batch:
    conn.executemany("INSERT INTO obs_fts(object_id,text) VALUES(?,?)",batch); conn.commit(); ins+=len(batch)
dt=time.perf_counter()-t0
log(f"D. FTS5 index build over {ins} rows: {dt:.1f}s  extra_bytes={(os.path.getsize(PATH)-base)/1e6:.0f} MB  ({(os.path.getsize(PATH)-base)/base*100:.0f}% of base db)")

def fts(q,label):
    t0=time.perf_counter(); rows=conn.execute("SELECT object_id FROM obs_fts WHERE obs_fts MATCH ? LIMIT 50",(q,)).fetchall()
    log(f"E. FTS5 {label} q={q!r}: hits={len(rows)} time={(time.perf_counter()-t0)*1000:.1f} ms")

fts('"妈妈" AND "生日" AND "礼物"',"3kw co-occurrence")
fts('"加班" AND "熬夜" AND "心悸"',"3kw co-occurrence")
fts('"不存在关键词XYZ" AND "生日"',"negative 2kw")
fts('"妈妈" NEAR/5 "生日"',"NEAR/5 proximity")
# fan-out problem: single common keyword
n=conn.execute("SELECT count(*) FROM obs_fts WHERE obs_fts MATCH '\"妈妈\"'").fetchone()[0]
log(f"F. single-kw fan-out '妈妈': {n} matching rows ({n/ins*100:.1f}% of corpus) -> intersection must be ranked, not returned")
