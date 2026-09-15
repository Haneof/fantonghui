import sqlite3, time, os, json
print("sqlite version:", sqlite3.sqlite_version, "| fts5:", sqlite3.Connection(":memory:").execute("select 1").fetchone())
PATH="/home/user/bench/big.db"
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
conn=sqlite3.connect(PATH)
row=conn.execute("SELECT text FROM obs_fts LIMIT 1").fetchone()[0]
log("G. sample indexed text:", row[:60])
# what does unicode61 produce as tokens?
def toks(s):
    c=sqlite3.connect(":memory:")
    c.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61')")
    c.execute("INSERT INTO t VALUES(?)",(s,))
    return [r[0] for r in c.execute("SELECT fts5_tokenize?" if 0 else "SELECT '' ")]
import re
log("H. unicode61 CJK tokenization check:")
for probe in ['"妈妈"','"妈妈聊到生日"','"妈妈*"',f'"{row[:20]}"']:
    try:
        n=conn.execute("SELECT count(*) FROM obs_fts WHERE obs_fts MATCH ?",(probe,)).fetchone()[0]
        log(f"   MATCH {probe}: {n} hits")
    except Exception as e:
        log(f"   MATCH {probe}: ERROR {e}")
# trigram tokenizer (SQLite >= 3.34)
try:
    t0=time.perf_counter()
    conn.execute("CREATE VIRTUAL TABLE obs_tri USING fts5(object_id UNINDEXED, text, tokenize='trigram')")
    cur=conn.execute("SELECT object_id, payload_json FROM object_revisions"); batch=[]
    base=os.path.getsize(PATH)
    while True:
        rows=cur.fetchmany(20000)
        if not rows: break
        for oid,pj in rows: batch.append((oid, json.loads(pj)["payload"]["text"]))
        if len(batch)>=20000:
            conn.executemany("INSERT INTO obs_tri(object_id,text) VALUES(?,?)",batch); batch=[]; conn.commit()
    if batch: conn.executemany("INSERT INTO obs_tri(object_id,text) VALUES(?,?)",batch); conn.commit()
    log(f"I. trigram FTS5 build: {time.perf_counter()-t0:.1f}s extra={(os.path.getsize(PATH)-base)/1e6:.0f} MB")
    for q in ['妈妈 AND 生日 AND 礼物','加班 AND 熬夜 AND 心悸','按摩仪']:
        t0=time.perf_counter(); n=conn.execute("SELECT count(*) FROM obs_tri WHERE obs_tri MATCH ?",(q,)).fetchone()[0]
        log(f"J. trigram MATCH {q!r}: {n} hits in {(time.perf_counter()-t0)*1000:.1f} ms")
except Exception as e:
    log("I. trigram unsupported:", e)
# ground truth via LIKE
t0=time.perf_counter()
n=conn.execute("SELECT count(*) FROM object_revisions WHERE payload_json LIKE '%妈妈%' AND payload_json LIKE '%生日%' AND payload_json LIKE '%礼物%'").fetchone()[0]
log(f"K. ground-truth LIKE 3kw intersection: {n} hits, full scan {(time.perf_counter()-t0):.2f}s")
