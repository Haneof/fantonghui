LOG=open("/home/user/bench/results.txt","a")
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.write(s+"\n"); LOG.flush()
log("")
log("=== BB-corrected. 实测内存放大系数：300,000 对象快照 = 1,360 MB -> 4.53 KB/对象 ===")
KO=4.53  # KB per object in the _list_payloads_historical path
for name, per_day in (("L 轻(第33条边缘轻量化真正生效)",300),
                      ("M 中(手机聊天记录+全天录音转写)",4500),
                      ("H 重(全向麦全天候+抓拍+IMU 原始特征)",30000)):
    objs1 = per_day*365*1.04*2.1
    db1 = objs1*1.0/1e6
    mem = objs1*KO/1e6   # GB
    log(f"  {name}: {per_day} obs/日")
    log(f"     1年 objects={objs1:,.0f} | db={db1:.2f} GB | 3年db={db1*3:.1f} GB | 一次全量历史快照 RAM={mem:.2f} GB -> {'OOM(实测 3.2GB 上限即失败)' if mem>2.0 else ('勉强' if mem>0.5 else 'ok')}")
    log(f"     一次快照耗时外推(实测 300k=3.94s) = {objs1/300000*3.94:.1f} s ; 首字响应 1s 目标超支 {objs1/300000*3.94:.0f}x")
