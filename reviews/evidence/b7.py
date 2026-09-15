import sqlite3, time, os, json, random
from collections import defaultdict, deque
PATH="/home/user/bench/dep.db"
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
if os.path.exists(PATH): os.remove(PATH)
conn=sqlite3.connect(PATH)
# Dependency edges as they are ACTUALLY stored today: one row per object_revisions payload
conn.execute("""CREATE TABLE object_revisions(object_id TEXT, revision INT, object_type TEXT,
 subject_id TEXT, world_revision INT, learned_at TEXT, recorded_at TEXT, payload_json TEXT,
 PRIMARY KEY(object_id,revision))""")
random.seed(7)
E=1_000_000
# realistic fan-in: 12 leaf dims -> 60 daily summaries -> 12 weekly -> 3 monthly -> 1 yearly claims
def mk(dep_id, rev):
    return {"object_id":dep_id,"object_type":"dependency","subject_id":"U001","revision":rev,
            "dependent_ref":{"object_id":f"OBJ-{random.randint(0,60000):06d}","revision":random.randint(1,4)},
            "dependency_ref":{"object_id":f"OBJ-{random.randint(0,200000):06d}","revision":random.randint(1,4)},
            "relation":"derives_from","created_at":"2026-03-01T10:00:00+00:00"}
t0=time.perf_counter(); batch=[]
for i in range(E):
    d=mk(f"DEP-{i:08d}",1); batch.append((d["object_id"],1,"dependency","U001",i+1,"2026-03-01T10:00:00+00:00","2026-03-01T10:00:00+00:00",json.dumps(d)))
    if len(batch)>=50000: conn.executemany("INSERT INTO object_revisions VALUES(?,?,?,?,?,?,?,?)",batch); batch=[]; conn.commit()
if batch: conn.executemany("INSERT INTO object_revisions VALUES(?,?,?,?,?,?,?,?)",batch); conn.commit()
log(f"L. dependency corpus: {E} edges, db={os.path.getsize(PATH)/1e6:.0f} MB, build={time.perf_counter()-t0:.1f}s")

# --- the ONLY way to answer "who depends on OBJ-x?" today: full scan + JSON parse
target="OBJ-000123"
t0=time.perf_counter(); hits=0
cur=conn.execute("SELECT payload_json FROM object_revisions WHERE object_type='dependency'")
while True:
    rows=cur.fetchmany(50000)
    if not rows: break
    for (pj,) in rows:
        d=json.loads(pj)
        if d["dependency_ref"]["object_id"]==target: hits+=1
dt=time.perf_counter()-t0
log(f"M. reverse-dependency lookup for one object (full scan + JSON parse): {hits} hits in {dt:.1f}s  -> per-correction cost")

# --- now with the missing native reverse index
conn.execute("CREATE TABLE dep_edges(dependency_object_id TEXT, dependency_revision INT, dependent_object_id TEXT, dependent_revision INT)")
t0=time.perf_counter()
cur=conn.execute("SELECT payload_json FROM object_revisions WHERE object_type='dependency'"); batch=[]
while True:
    rows=cur.fetchmany(50000)
    if not rows: break
    for (pj,) in rows:
        d=json.loads(pj)
        batch.append((d["dependency_ref"]["object_id"],d["dependency_ref"]["revision"],
                      d["dependent_ref"]["object_id"],d["dependent_ref"]["revision"]))
    if len(batch)>=100000: conn.executemany("INSERT INTO dep_edges VALUES(?,?,?,?)",batch); batch=[]; conn.commit()
if batch: conn.executemany("INSERT INTO dep_edges VALUES(?,?,?,?)",batch); conn.commit()
conn.execute("CREATE INDEX idx_dep_reverse ON dep_edges(dependency_object_id, dependency_revision)")
conn.execute("CREATE INDEX idx_dep_forward ON dep_edges(dependent_object_id, dependent_revision)")
conn.commit()
log(f"N. native reverse-index build: {time.perf_counter()-t0:.1f}s  extra={os.path.getsize(PATH)/1e6:.0f} MB total")
t0=time.perf_counter()
n=conn.execute("SELECT count(*) FROM dep_edges WHERE dependency_object_id=?",(target,)).fetchone()[0]
log(f"O. indexed reverse lookup: {n} dependents in {(time.perf_counter()-t0)*1000:.2f} ms  (speedup {dt/((time.perf_counter()-t0))*1000:.0f}x)")

# --- transitive blast radius of ONE leaf correction (the 算力雪崩 question)
adj=defaultdict(list)
t0=time.perf_counter()
for a,b,c_,d_ in conn.execute("SELECT dependency_object_id,dependency_revision,dependent_object_id,dependent_revision FROM dep_edges"):
    adj[(a,b)].append((c_,d_))
log(f"P. load reverse adjacency into RAM: {time.perf_counter()-t0:.1f}s, nodes={len(adj)}")
def blast(start, cap=None):
    q=deque([start]); seen={start}; 
    while q:
        cur_=q.popleft()
        for nxt in adj.get(cur_,()):
            if nxt in seen: continue
            seen.add(nxt); q.append(nxt)
            if cap and len(seen)>=cap: return len(seen), True
    return len(seen), False
t0=time.perf_counter(); n,capped=blast((target,1)); dt=time.perf_counter()-t0
log(f"Q. transitive impact set from ONE leaf revision: {n} objects, {'CAPPED' if capped else 'complete'}, {dt:.2f}s")
# worst case: correct a root
root=max(adj, key=lambda k: len(adj[k]))
t0=time.perf_counter(); n,capped=blast(root); dt=time.perf_counter()-t0
log(f"R. worst-case (hottest node {root}) transitive blast radius: {n} objects in {dt:.2f}s -> if each needs an LLM re-review at ~2k tokens, that is {n*2000/1e6:.1f}M tokens")
