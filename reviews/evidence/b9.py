import time
from collections import defaultdict, deque
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()

def build(dim_boundaries=True, cross_domain_synapses=0, seed=3):
    """Faithful AIOS pyramid: 12 dims x 365 days x 25 obs/day -> daily -> weekly -> monthly -> quarter -> half -> year -> 3yr."""
    import random; random.seed(seed)
    DIMS, DAYS, OBS = 12, 365, 25
    adj=defaultdict(list)
    obs=[[(f"OBS-d{d}-i{i}") for i in range(DAYS*OBS)] for d in range(DIMS)]
    prev=obs
    layers=[("daily",DAYS,7),("weekly",52,7),("monthly",12,4),("quarter",4,3),("half",2,2),("year",1,4)]
    for nm,cnt,fi in layers:
        new=[[] for _ in range(DIMS)]
        for d in range(DIMS):
            src=prev[d]; per=max(1,len(src)//cnt)
            for k in range(cnt):
                nid=f"{nm}-d{d}-{k}"
                for s in src[k*per:(k+1)*per][:fi*per]:
                    adj[s].append(nid)
                new[d].append(nid)
        prev=new
    # cross-domain resonance synapses (Article 22): each weekly summary in dim A also feeds a derived dim
    if cross_domain_synapses:
        derived=[f"DERIVED-{i}" for i in range(cross_domain_synapses)]
        for i in range(cross_domain_synapses):
            for _ in range(6):                       # each derived node resonates with 6 random upstream summaries
                d=random.randrange(DIMS); k=random.randrange(52)
                adj[f"weekly-d{d}-{k}"].append(derived[i])
        for dd in derived: adj[dd].append("LIFECHAPTER-1")
    return adj

for label, kw in [("pure axial pyramid (no cross-domain)", dict(cross_domain_synapses=0)),
                  ("axial + 200 cross-domain resonance nodes", dict(cross_domain_synapses=200)),
                  ("axial + 2000 cross-domain resonance nodes", dict(cross_domain_synapses=2000))]:
    t0=time.perf_counter(); adj=build(**kw); bt=time.perf_counter()-t0
    def blast(start):
        q=deque([start]); seen=set()
        while q:
            c=q.popleft()
            for n in adj.get(c,()):
                if n not in seen: seen.add(n); q.append(n)
        return seen
    s=blast("OBS-d3-i5000")
    edges=sum(len(v) for v in adj.values())
    log(f"Z. {label}: edges={edges:,} build={bt:.2f}s | dependents of ONE observation={len(s):,} | LLM re-review @2k tok = {len(s)*2000/1e6:.2f}M tokens")
