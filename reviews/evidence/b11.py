LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
log("")
log("=== BB. 三档摄入规模的 1 年 / 3 年成本模型（实测 1.0 KB/行, 4.5 KB/对象 内存放大）===")
tiers = {
 "L 轻(宪法33条边缘轻量化生效): 300 obs/日": 300,
 "M 中(手机聊天记录+录音转写全量): 4500 obs/日": 4500,
 "H 重(全向麦全天候转写+抓拍+IMU): 30000 obs/日": 30000,
}
for name, per_day in tiers.items():
    y = per_day*365
    # summaries ~4% overhead, dependencies ~1.1x objects
    objs = y*1.04*2.1
    db_gb_1 = objs*1.0/1e6
    db_gb_3 = db_gb_1*3
    snap_mem_gb = objs*4.5/1e9
    log(f"  {name}")
    log(f"     1年 objects={objs:,.0f}  db={db_gb_1:.2f} GB  3年db={db_gb_3:.2f} GB  全量快照内存={snap_mem_gb:.2f} GB -> {'OOM on 1-2GB 手环' if snap_mem_gb>1 else 'ok'}")
log("")
log("=== CC. 1 秒首字响应的串行预算（云端大模型路径）===")
steps=[("VAD 尾静音判定",250,350),("端侧流式 ASR 出全文",150,400),
       ("四步序 step1-3 自省/羁绊/语调切片装载(缓存命中)",20,80),
       ("step4 + 三层联想召回 co_search/entity/events/promises",150,600),
       ("Cockpit Manifest 序列化",10,40),("移动网络 RTT(4G/5G)",60,250),
       ("云端 prefill 1500 tok + TTFT",120,400)]
lo=sum(s[1] for s in steps); hi=sum(s[2] for s in steps)
for n,a,b in steps: log(f"     {n:<52} {a:>4}-{b:>4} ms")
log(f"     {'合计':<52} {lo:>4}-{hi:>4} ms   -> 目标 1000ms: {'仅最优路径可达' if lo<1000 else '不可达'}，最差超支 {hi-1000} ms ({hi/1000:.1f}x)")
log("")
log("=== DD. 长平稳心跳的月度 Token 账单（第80条 每3~5小时一次）===")
for hrs in (3,4,5):
    n=24/hrs*30
    for preamble in (600,1200):
        for ctx in (1500,4000):
            tot=n*(preamble+ctx+150)
            log(f"     每{hrs}h -> {n:.0f} 次/月, 四步序{preamble}tok + 上下文{ctx}tok + 输出150tok = {tot/1e6:.2f}M tok/月")
    break
log("     对照: 第86条声称条件任务挂载可'零浪费'，但心跳本身的四步序+四层上下文是无条件的固定开销")
log("")
log("=== EE. 第33.5条'每日大模型清洗'的年度 LLM 账单 ===")
for per_day,tok_per_obs in ((300,300),(4500,300),(30000,300)):
    daily_tok=per_day*tok_per_obs
    log(f"     {per_day} obs/日 -> 每日清洗需读 {daily_tok/1e6:.2f}M tok, 一年 {daily_tok*365/1e9:.2f}B tok (仅清洗, 不含认知)")
