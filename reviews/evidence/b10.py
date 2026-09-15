from collections import defaultdict, deque
LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
adj=defaultdict(list)
# 2 years: entity 老张 appears in ~200 events/yr; each event anchors 3 dims x 5 obs; each obs feeds daily summaries
DIMS=3; EV_PER_YR=200; OBS_PER_EV=5
for yr in (1,2):
    for e in range(EV_PER_YR):
        ev=f"EVT-y{yr}-{e}"
        adj[f"ENT-老张"].append(ev)
        for d in range(DIMS):
            for o in range(OBS_PER_EV):
                oid=f"OBS-y{yr}-e{e}-d{d}-{o}"
                adj[oid].append(ev)
                adj[ev].append(f"daily-d{d}-y{yr}-{e//7}")   # events also feed daily summaries
            adj[f"daily-d{d}-y{yr}-{e//7}"].append(f"weekly-d{d}-y{yr}-{e//30}")
        adj[f"weekly-d0-y{yr}-{e//30}"].append(f"claim-关于老张-{yr}-{e%12}")
        adj[f"claim-关于老张-{yr}-{e%12}"].append(f"summary-人际信任-y{yr}")
        adj[f"summary-人际信任-y{yr}"].append("derived-人际信任危机")
        adj["derived-人际信任危机"].append("LIFECHAPTER-涅槃重组期")
def blast(start):
    q=deque([start]); seen=set()
    while q:
        c=q.popleft()
        for n in adj.get(c,()):
            if n not in seen: seen.add(n); q.append(n)
    return seen
s=blast("ENT-老张")
by_type=defaultdict(int)
for x in s: by_type[x.split("-")[0]]+=1
log("AA. ENTITY-level correction ('老张是骗子') transitive impact over 2 years:")
log(f"    total dependent objects = {len(s):,} | breakdown = {dict(by_type)}")
log(f"    eager full re-review @2k tokens = {len(s)*2000/1e6:.1f}M tokens ; @10 LLM sessions/s = {len(s)/10/3600:.1f} hours of serial re-review")
log(f"    Article 93 lazy path = 0 tokens now, but {by_type.get('summary',0)+by_type.get('claim',0):,} summaries/claims stay STALE and must be freshness-checked at every read")
