import sqlite3, time, random, json, os
DB="/tmp/aios_bench.db"
con=sqlite3.connect(DB)
def q(label,sql,params=()):
    t=time.time(); rows=con.execute(sql,params).fetchall(); dt=(time.time()-t)*1000
    print("%-62s %8.1f ms  rows=%d  %s"%(label,dt,len(rows), (rows[0] if len(rows)==1 else "")))
    return dt
# correct point lookup
q("indexed point lookup by object_id","SELECT payload_json FROM object_revisions WHERE object_id=? ORDER BY world_revision DESC LIMIT 1",("O00499999",))
q("repeat single keyword LIKE scan (warm cache)","SELECT count(*) FROM object_revisions WHERE payload_json LIKE '%妈妈%'")
# --- constructive: FTS5 external-content index ---
t=time.time()
con.executescript("""
CREATE VIRTUAL TABLE obs_fts USING fts5(payload_json, content='object_revisions', content_rowid='rowid', tokenize='unicode61');
INSERT INTO obs_fts(rowid, payload_json) SELECT rowid, payload_json FROM object_revisions;
""")
con.commit(); print("FTS5 build over 500k rows: %.1f s, db=%.1f MB"%(time.time()-t, os.path.getsize(DB)/1e6))
q("FTS5 single term 妈妈","SELECT count(*) FROM obs_fts WHERE obs_fts MATCH '妈妈'")
q("FTS5 3-term AND (妈妈 生日 礼物)","SELECT count(*) FROM obs_fts WHERE obs_fts MATCH '妈妈 AND 生日 AND 礼物'")
q("FTS5 3-term AND + top10 rank fetch","SELECT rowid FROM obs_fts WHERE obs_fts MATCH '妈妈 AND 生日 AND 礼物' LIMIT 10")
# --- constructive: posting-list junction table (keyword -> object_id) ---
t=time.time()
con.executescript("""
CREATE TABLE kw_postings(keyword TEXT NOT NULL, object_id TEXT NOT NULL, world_revision INTEGER NOT NULL, PRIMARY KEY(keyword, object_id));
""")
rows=[]
for oid, payload in con.execute("SELECT object_id, payload_json FROM object_revisions"):
    for kw in json.loads(payload)["kw"]:
        rows.append((kw,oid,1))
con.executemany("INSERT OR IGNORE INTO kw_postings VALUES (?,?,?)",rows)
con.commit(); print("posting list build: %.1f s, %d postings, db=%.1f MB"%(time.time()-t,len(rows),os.path.getsize(DB)/1e6))
q("posting-list 3-keyword intersection","""
SELECT count(*) FROM kw_postings a JOIN kw_postings b USING(object_id) JOIN kw_postings c USING(object_id)
WHERE a.keyword='妈妈' AND b.keyword='生日' AND c.keyword='礼物'""")
con.close()
