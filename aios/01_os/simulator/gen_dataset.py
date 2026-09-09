# -*- coding: utf-8 -*-
"""90 天模拟生命事件生成器（执行 tasks/数据生成提示词.md）
输出：90 天 × 400-500 条/工作日 ≈ 36000+ 条，秒级时间戳全天唯一
"""
import json, random, time, uuid, os

random.seed(20260909)
NOW = time.time()
DAY = 86400
START = NOW - 90 * DAY                    # 90 天前
PEOPLE = ["小王", "张总", "李经理", "小雅", "小陈", "王医生"]
MEETINGS = ["AIOS 项目评审会", "Q3 产品路线图对齐", "客户交付方案讨论", "周例会", "需求评审", "数据看板验收"]
WORK_TALK = [
    "这个版本的交互要重做，明天给你方案", "张总那边交付周期又提前了，压力很大",
    "Q3 路线图第三阶段要先做记忆压缩", "客户说预算可以谈，但交付必须保", "把测试报告发给李经理",
    "小陈，这个需求文档今晚补完", "评审会上李经理质疑了排期，需要数据支撑", "张总问我们能不能月底交付",
    "方案我改到第三版了，李经理还没批", "跟小王对了一下接口联调时间",
]
CHAT = [
    "明天能见面吗？", "晚上一起吃饭？", "周末去爬山怎么样", "方案我看完了，有两点要改",
    "上次说的那个事情有进展了", "生日快乐！", "最近加班多吗？注意身体", "那家店的咖啡不错",
    "会议纪要发我一份", "客户签约了，晚上庆祝一下",
]
LUNCH = [("公司食堂", 22), ("楼下快餐", 28), ("兰州拉面", 19), ("便利店饭团", 15), ("外卖·黄焖鸡", 32)]
DINNER = [("家常菜馆", 68), ("火锅", 158), ("日料", 128), ("外卖·炒饭", 35), ("西餐厅", 216)]
COFFEE = [("美式", 18), ("拿铁", 28), ("冷萃", 22)]
BOOKS = ["《认知觉醒》", "《计算机网络》", "《三体》", "《经济学原理》", "《活着》"]
PLACES = ["公司", "家", "万达广场", "健身房", "客户办公室", "常去餐厅"]
TOPICS_EVT = "evt.sim."

out = []
def add(ts, typ, content, source="sim"):
    out.append({"delay_s": 0, "topic": f"evt.sim.{typ}",
                "event": {"id": str(uuid.uuid4()), "ts": round(ts, 3),
                          "source": source, "type": typ, "content": content}})

def pick(seq): return random.choice(seq)

for day in range(90):
    day0 = START + day * DAY
    wd = time.localtime(day0).tm_wday          # 0=周一
    weekend = wd >= 5
    base = day0 + (10 * 3600 if weekend else random.uniform(7.2, 7.9) * 3600)
    base = int(base)                            # 秒对齐
    day_events = []

    def at(hour_off, typ, content, source="sim"):
        ts = base + int(hour_off * 3600) + random.randint(0, 1800)
        day_events.append((ts, typ, content, source))

    # 晨起体征
    at(0, "vital", f"静息心率 {random.randint(58, 72)}，醒来")
    at(0.2, "motion", "起床，佩戴手环")
    at(0.3, "env", f"在家（{pick(PLACES[:2])}）")
    if weekend:
        at(1.0, "payment", f"{pick(DINNER)[0]} 早餐外卖 ¥{random.randint(15,35)}")
        at(2.0, "speech", f"和{pick(PEOPLE)}打电话聊了 {random.randint(10,40)} 分钟")
        at(3.0, "env", pick(PLACES[2:5]))
        at(4.0, "motion", pick(["散步 3 公里", "骑车 6 公里", "逛街 2 小时"]))
        at(6.0, "book", f"读《{pick(BOOKS)}》{random.randint(20,60)} 分钟")
        at(8.0, "vital", f"步行 {random.randint(3000, 9000)} 步")
        at(11.0, "vital", f"静息心率 {random.randint(56, 66)}，入睡")
    else:
        # 通勤
        at(1.1, "motion", "通勤：地铁 2 号线")
        at(1.5, "env", "到达公司")
        at(1.6, "vital", f"心率 {random.randint(75, 95)}（步行中）")
        # 上午工作
        if day % 3 == 0:
            at(2.2, "schedule", f"参加{pick(MEETINGS)}（{random.randint(30,90)} 分钟）")
            at(2.6, "speech", f"{pick(['我','李经理'])}在会上说：{pick(WORK_TALK)}")
        at(3.2, "speech", "对{0}说：{1}".format(pick(PEOPLE[:3]), pick(WORK_TALK)))
        at(3.8, "message", f"{pick(PEOPLE[:3])}发来消息：{pick(CHAT)}")
        at(4.4, "message", f"回复{pick(PEOPLE[:3])}：{pick(CHAT)}")
        # 午餐
        r = pick(LUNCH)
        at(5.2, "payment", f"{r[0]} ¥{r[1]}")
        at(5.4, "vital", f"餐后心率 {random.randint(78, 92)}")
        # 下午工作
        if day % 2 == 0:
            at(6.5, "schedule", f"{pick(MEETINGS)}（{random.randint(30,60)} 分钟）")
        at(7.2, "speech", "对张总说：" + pick(WORK_TALK))
        at(8.0, "message", f"张总发来消息：{pick(['交付时间表发我','价格还有空间吗','下周到我这聊聊'])}")
        # 下班健身/晚餐
        if day % 2 == 1:
            at(9.2, "env", "健身房")
            at(9.5, "motion", f"跑步 {random.uniform(3, 6):.1f} 公里")
            at(10.0, "vital", f"运动心率 {random.randint(125, 150)}")
        r = pick(DINNER)
        at(10.6, "payment", f"{r[0]} ¥{r[1]}")
        if day % 5 == 2:
            at(11.0, "speech", f"和小雅吃饭，聊了{pick(['周末计划','工作近况','旅行安排'])}")
        # 晚间
        at(12.0, "book", f"读《{pick(BOOKS)}》{random.randint(15, 50)} 分钟")
        at(13.0, "message", f"{pick(PEOPLE)}发来消息：{pick(CHAT)}")
        at(14.5, "vital", f"静息心率 {random.randint(56, 68)}，入睡")
        # 睡眠期：每小时 1 条体征（C1：稀疏采样，无占位）
        for h in range(1, 6):
            at(14.5 + h, "vital", f"睡眠心率 {random.randint(48, 62)}")

    day_events.sort(key=lambda x: x[0])
    for ts, typ, content, source in day_events:
        add(ts, typ, content, source)

print(f"生成事件总数: {len(out)}")
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code", "simulator", "scripts", "life_90days.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print("大小: %.1f MB" % (os.path.getsize(out_path) / 1048576))
print("输出:", out_path)
