import time, json
from collections import defaultdict, deque
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()

# Realistic AIOS pyramid for ONE user, ONE year, 12 active dimensions
DAYS=365; DIMS=12; OBS_PER_DIM_DAY=25           # 25 obs/dim/day -> 300/day
obs = DAYS*DIMS*OBS_PER_DIM_DAY
daily_s = DAYS*DIMS
weekly_s = (DAYS//7)*DIMS
monthly_s = 12*DIMS
q_s, h_s, y_s, c3_s = 4*DIMS, 2*DIMS, DIMS, max(1,DIMS//4)
events, claims = 2*DAYS, 6*DAYS                  # ~2 events/day, 6 claims/day
preds = 1*DAYS
log(f"S. 1-year single-user object volume estimate: observations={obs:,} daily_summaries={daily_s:,} weekly={weekly_s:,} monthly={monthly_s:,} events={events:,} claims={claims:,} predictions={preds:,}")
total = obs+daily_s+weekly_s+monthly_s+q_s+h_s+y_s+c3_s+events+claims+preds
log(f"T. total first-class objects/year ~= {total:,} ; at measured 1.0 KB/row (db) -> {total*1.0/1000:.0f} MB/yr  (revisions x2-3 -> {total*2.5/1000:.0f} MB)")

# dependency edges (each derived object records its inputs)
edges = (daily_s*OBS_PER_DIM_DAY) + (weekly_s*7) + (monthly_s*4) + (q_s*3) + (h_s*2) + (y_s*4) + (c3_s*4) + events*8 + claims*3 + preds*1
log(f"U. Dependency rows generated per year ~= {edges:,}  (that is {edges/total:.1f} dependency records per object)")

# build layered DAG
adj=defaultdict(list)
def add(dst, src): adj[src].append(dst)
O=[f"OBS-{i}" for i in range(obs)]
L_prev=O
names=["daily","weekly","monthly","quarter","half","year","chapter3"]
counts=[daily_s,weekly_s,monthly_s,q_s,h_s,y_s,c3_s]
fanins=[OBS_PER_DIM_DAY,7,4,3,2,4,4]
for lvl,(nm,cnt,fi) in enumerate(zip(names,counts,fanins)):
    step=max(1,len(L_prev)//max(cnt,1))
    L=[]
    for k in range(cnt):
        nid=f"{nm}-{k}"
        base=k*step
        for s in L_prev[base:base+fi]:
            add(nid,s)
        L.append(nid)
    L_prev=L
t0=time.perf_counter()
def blast(start):
    q=deque([start]); seen={start}
    while q:
        c=q.popleft()
        for n in adj.get(c,()):
            if n in seen: continue
            seen.add(n); q.append(n)
    return seen
s=blast("OBS-12345"); dt=time.perf_counter()-t0
log(f"V. transitive dependents of ONE corrected Observation (realistic pyramid): {len(s):,} objects in {dt*1000:.1f} ms (graph in RAM)")
s2=blast("daily-1000")
log(f"W. transitive dependents of ONE corrected daily Summary: {len(s2):,} objects")
# LLM cost of a full re-review, 2k tokens each
log(f"X. if Article 49 marks ALL of them 待复核 and each re-review costs ~2k tokens: {len(s)*2000/1e6:.2f}M tokens per single observation correction; {len(s)*2000/1e6*0.005:.2f} USD-equivalent at $5/Mtok")
log(f"Y. Article 93 lazy path: 0 tokens now, but every later read of a STALE summary needs a freshness check -> unbounded read-time cost")
