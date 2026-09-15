import sqlite3, time, json, os, random, string, sys

SCHEMA = """
CREATE TABLE IF NOT EXISTS world_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO world_meta(key,value) VALUES ('world_revision','0');
CREATE TABLE IF NOT EXISTS world_commits (
  world_revision INTEGER PRIMARY KEY, committed_at TEXT NOT NULL,
  operation_id TEXT NOT NULL UNIQUE, session_id TEXT, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS object_revisions (
  object_id TEXT NOT NULL, revision INTEGER NOT NULL, object_type TEXT NOT NULL,
  subject_id TEXT NOT NULL, world_revision INTEGER NOT NULL, learned_at TEXT NOT NULL,
  recorded_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(object_id, revision),
  FOREIGN KEY(world_revision) REFERENCES world_commits(world_revision));
CREATE INDEX IF NOT EXISTS idx_objects_current_lookup ON object_revisions(object_id, world_revision DESC);
CREATE INDEX IF NOT EXISTS idx_objects_type_subject ON object_revisions(object_type, subject_id, world_revision DESC);
CREATE INDEX IF NOT EXISTS idx_objects_learned ON object_revisions(learned_at);
CREATE TABLE IF NOT EXISTS operations (
  operation_id TEXT PRIMARY KEY, session_id TEXT, operation_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL, expected_world_revision INTEGER NOT NULL, reason TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL, result_world_revision INTEGER,
  error_code TEXT, error_message TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency_records (
  idempotency_key TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
  world_revision INTEGER NOT NULL, result_json TEXT NOT NULL);
"""

def payload(i):
    return json.dumps({
      "object_id": f"OBS-{i:09d}", "object_type":"observation","subject_id":"U001",
      "revision":1,"occurred_at":"2026-03-01T10:00:00+00:00","learned_at":"2026-03-01T10:00:01+00:00",
      "recorded_at":"2026-03-01T10:00:02+00:00","status":"active","created_by":"simulator",
      "source_refs":[{"source_type":"sensor","source_id":"imu-1"}],
      "payload":{"dimension_id":"DIM_USER_CHAT","text":"今天和妈妈聊了生日礼物的事情，她说想要一个按摩仪，还提到老张借钱的事。"*2,
                 "modality":"text","confidence":0.83},
    }, ensure_ascii=False)

def run(path, n, sync):
    if os.path.exists(path): os.remove(path)
    for ext in ("-wal","-shm"):
        if os.path.exists(path+ext): os.remove(path+ext)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA foreign_keys=ON"); conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA synchronous={sync}")
    conn.executescript(SCHEMA); conn.commit()
    sizes=[]
    t0=time.perf_counter()
    wr=0
    for i in range(n):
        p=payload(i); sizes.append(len(p.encode()))
        conn.execute("BEGIN IMMEDIATE")
        wr+=1
        conn.execute("UPDATE world_meta SET value=? WHERE key='world_revision'",(str(wr),))
        conn.execute("INSERT INTO world_commits VALUES(?,?,?,?,?)",(wr,"2026-03-01T10:00:02+00:00",f"op-{i}",None,"bench"))
        conn.execute("INSERT INTO object_revisions VALUES(?,?,?,?,?,?,?,?)",
                     (f"OBS-{i:09d}",1,"observation","U001",wr,"2026-03-01T10:00:01+00:00","2026-03-01T10:00:02+00:00",p))
        conn.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"op-{i}",None,"observation.create","{}",wr-1,"bench",f"idem-{i}","succeeded",wr,None,None,"2026-03-01T10:00:02+00:00"))
        conn.execute("INSERT INTO idempotency_records VALUES(?,?,?,?)",(f"idem-{i}",f"op-{i}",wr,"{}"))
        conn.commit()
    dt=time.perf_counter()-t0
    db=os.path.getsize(path)/1e6
    print(f"[commit/{sync}] n={n} wall={dt:.1f}s rate={n/dt:.0f} commits/s avg_latency={dt/n*1000:.2f} ms db={db:.1f} MB avg_payload={sum(sizes)/len(sizes):.0f} B")
    conn.close()

if __name__=="__main__":
    n=int(sys.argv[1]) if len(sys.argv)>1 else 20000
    run("/home/user/bench/full.db", n, "FULL")
    run("/home/user/bench/normal.db", n, "NORMAL")
