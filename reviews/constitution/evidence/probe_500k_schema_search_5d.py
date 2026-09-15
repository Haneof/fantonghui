import sqlite3, time, random, json, string, os, sys
DB="/tmp/aios_bench.db"
if os.path.exists(DB): os.remove(DB)
con=sqlite3.connect(DB)
con.executescript("""
CREATE TABLE world_commits(world_revision INTEGER PRIMARY KEY, committed_at TEXT NOT NULL,
  operation_id TEXT NOT NULL UNIQUE, session_id TEXT, reason TEXT NOT NULL);
CREATE TABLE object_revisions(
  object_id TEXT NOT NULL, revision INTEGER NOT NULL, object_type TEXT NOT NULL,
  subject_id TEXT NOT NULL, world_revision INTEGER NOT NULL, learned_at TEXT NOT NULL,
  recorded_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(object_id, revision));
CREATE INDEX idx_objects_current_lookup ON object_revisions(object_id, world_revision DESC);
CREATE INDEX idx_objects_type_subject ON object_revisions(object_type, subject_id, world_revision DESC);
CREATE INDEX idx_objects_learned ON object_revisions(learned_at);
""")
N=500_000
words=["妈妈","生日","礼物","老张","借钱","争执","加班","熬夜","心悸","操场","跑步","考试","微信","吵架","餐厅","项目","会议","咖啡","健身","房租"]
random.seed(7)
types=["Observation","Claim","EventAnchor","Summary","Entity","Relation","EvidenceSet"]
batch=[]
t0=time.time()
for i in range(N):
    oid=f"O{i:08d}"
    kw=random.sample(words, random.randint(1,4))
    payload={"content":"用户原话片段 "+" ".join(kw)+" "+"填"*random.randint(20,120), "kw":kw}
    # 5% of rows carry each rare keyword
    batch.append((oid,1,types[i%len(types)],f"SUBJ{i%3}",i,
                  f"2027-{(i%12)+1:02d}-{(i%28)+1:02d}T00:00:00+00:00",
                  f"2027-{(i%12)+1:02d}-{(i%28)+1:02d}T00:00:00+00:00", json.dumps(payload,ensure_ascii=False)))
con.executemany("INSERT INTO object_revisions VALUES (?,?,?,?,?,?,?,?)",batch)
con.commit()
print("insert 500k rows: %.1fs  db=%.1f MB"%(time.time()-t0, os.path.getsize(DB)/1e6))
def q(label,sql,params=()):
    t=time.time(); rows=con.execute(sql,params).fetchall(); dt=time.time()-t
    print("%-58s %8.1f ms  rows=%d"%(label,dt*1000,len(rows)))
    return dt
# 1) indexed point lookup (by object_id)
q("indexed lookup object_id (current rev)","SELECT payload_json FROM object_revisions WHERE object_id=? ORDER BY world_revision DESC LIMIT 1",("O000499999",))
# 2) indexed type+subject scan slice
q("indexed type+subject range","SELECT count(*) FROM object_revisions WHERE object_type=? AND subject_id=? AND world_revision<=?",("Claim","SUBJ1",400000))
# 3) single keyword LIKE scan (no FTS)
q("single keyword LIKE '%妈妈%' (full scan)","SELECT count(*) FROM object_revisions WHERE payload_json LIKE '%妈妈%'")
# 4) 3-keyword AND scan
q("3-keyword AND LIKE (co-occurrence, full scan)","SELECT count(*) FROM object_revisions WHERE payload_json LIKE '%妈妈%' AND payload_json LIKE '%生日%' AND payload_json LIKE '%礼物%'")
# 5) 3-keyword AND + time window slice (1 month)
q("3-keyword AND LIKE + 1-month learned_at window","SELECT count(*) FROM object_revisions WHERE learned_at>='2027-06-01' AND learned_at<'2027-07-01' AND payload_json LIKE '%妈妈%' AND payload_json LIKE '%生日%' AND payload_json LIKE '%礼物%'")
# 6) aggregate 5D slider: monthly bucket counts over a year
q("5D slider: monthly bucket group-by (full scan)","SELECT substr(learned_at,1,7) g, count(*) FROM object_revisions GROUP BY g")
con.close()
