"""24h 日总结题库组卷器（01a0aa2c-fantonghui，原创）。

协议与 daily24h 兼容（同键名/同类型），内容全部原创：
顶层 question_id/generator_agent/persona/arc_tags/cleaned_daily_stream/
directional_ground_truth；arc_tags 弧码为不透明码（C01/S01/F01 + 数字极性）；
GT 每维 {core_content,acceptable_directions,forbidden_directions,anchor_entities}。

用法：
    python benchmarks/daily_summary/generators/daily24h_generator_01a0aa2c.py \\
        --n 10000 --seed 2401 --out benchmarks/daily_summary/questions/questions_daily24h_01a0aa2c.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily24h_pools_01a0aa2c as P

GENERATOR_AGENT = "01a0aa2c-fantonghui"
QID_PREFIX = "QD_01a0aa2c-fantonghui_"
DATE_SPAN = "07:00~23:30"

# 极性分布（对标 daily24h 实测）
POLARITY_WEIGHTS = [((-1, -1), 25), ((-1, 1), 25), ((1, 1), 18),
                    ((1, -1), 17), ((0, -1), 8), ((0, 1), 7)]
CAREER_BY_VALENCE = {1: ["C02", "C03", "C06", "C08", "C10"],
                     -1: ["C01", "C04", "C05", "C07", "C09"],
                     0: ["C11", "C12"]}
SOCIAL_BY_VALENCE = {1: ["S03", "S04", "S05", "S06", "S09", "S10", "S12"],
                     -1: ["S01", "S02", "S07", "S08", "S11"]}
FINANCE_CODES = sorted(P.FINANCE.keys())
# 必含窄口径陷阱的类别（每卷至少 1 条此类）
NARROW_TRAP_CLASSES = ["hotsearch", "loan_ads", "groupbuy", "health_fwd", "brag_vent", "scam"]
TRAP_TIMES = ["09:20", "13:20", "15:40", "18:40", "22:40"]
FILLER_TIMES = ["07:40", "08:20", "08:50", "12:10", "12:50", "14:10",
                "16:00", "17:30", "18:10", "19:00", "21:00", "22:20"]
SPIKE_SOCIAL = {"S01", "S02", "S07"}  # 冲突决裂夜必骤升
NEWTITLES = ["高级专员", "资深工程师", "部门副经理", "高级顾问", "项目主管"]
GLOBAL_ACC_EXTRA = {
    (1, 1): ["双喜临门", "事业感情双丰收"],
    (1, -1): ["喜忧参半", "冰火两重天"],
    (-1, 1): ["先苦后甜", "否极泰来"],
    (-1, -1): ["双重打击", "祸不单行"],
    (0, 1): ["平淡见温情", "稳中向好"],
    (0, -1): ["雪上加霜", "疲惫的一天"],
}
GLOBAL_FORBID_EXTRA = {
    (1, 1): ["一事无成", "霉运缠身", "至暗一日"],
    (1, -1): ["顺风顺水", "十全十美", "毫无波澜"],
    (-1, 1): ["顺风顺水", "十全十美", "毫无波澜"],
    (-1, -1): ["双喜临门", "一帆风顺", "人生巅峰"],
    (0, 1): ["一塌糊涂", "糟透了", "至暗一日"],
    (0, -1): ["春风得意", "喜气洋洋", "一帆风顺"],
}
SINGLE_ANCHOR_SOCIAL = {"S04", "S08", "S11"}  # 仅 (name,) 单锚点


def make_persona_names(rng: random.Random, n: int = 1000) -> list:
    names: list = []
    guard = 0
    while len(names) < n and guard < n * 50:
        guard += 1
        s = rng.choice(P.SURNAMES)
        g = rng.choice(P.GIVEN_A) + (rng.choice(P.GIVEN_B) if rng.random() < 0.65 else "")
        nm = s + g
        if 2 <= len(nm) <= 3 and nm not in names:
            names.append(nm)
    assert len(names) == n, "姓名池不足"
    return names


def person_name(rng: random.Random, ban: set) -> str:
    for _ in range(200):
        s = rng.choice(P.SURNAMES)
        g = rng.choice(P.GIVEN_A) + (rng.choice(P.GIVEN_B) if rng.random() < 0.6 else "")
        nm = s + g
        if 2 <= len(nm) <= 3 and nm not in ban:
            return nm
    raise RuntimeError("配角名枯竭")


def shift_time(base: str, delta_min: int) -> str:
    h, m = int(base[:2]), int(base[3:5])
    t = h * 60 + m + delta_min
    t = max(7 * 60, min(23 * 60 + 29, t))
    return f"{t // 60:02d}:{t % 60:02d}"


def fmt(tpl: str, slots: dict, where: str) -> str:
    try:
        return tpl.format(**slots)
    except KeyError as e:
        raise RuntimeError(f"槽位缺失 {where}: {e} <- {tpl[:60]}") from e


def build_slots(rng: random.Random, persona: dict, fin_code: str) -> dict:
    male = persona["gender"] == "男"
    city = persona["city"]
    city2 = rng.choice([c for c in P.CITIES if c != city])
    fin = P.FINANCE[fin_code]
    lo, hi = fin["amt_range"]
    amt = rng.randrange(lo, hi + 1)
    s = {
        "name": persona["name"], "city": city, "city2": city2,
        "bro": "兄弟" if male else "姐妹",
        "datetag": "姑娘" if male else "小伙",
        "kidcall": "儿子" if male else "闺女",
        "kidpar": "爸爸" if male else "妈妈",
        "kid": rng.choice(["儿子", "女儿"]),
        "co": "", "buddy": "", "boss": "", "lover": "",
        "client": rng.choice(P.CLIENT_COS), "project": rng.choice(P.PROJECTS),
        "bank": rng.choice(P.BANKS), "tail": f"{rng.randrange(1000, 10000)}",
        "amt": amt, "amt2": rng.randrange(1500, 4001, 100),
        "bal": rng.randrange(5000, 80001, 100),
        "raise": rng.randrange(15, 61), "newtitle": rng.choice(NEWTITLES),
        "bonus": rng.choice([5000, 8000, 10000, 15000, 20000, 30000]),
        "y_amt": rng.randrange(80, 501), "cert": rng.choice(P.CERTS),
        "b_amt": rng.choice([2000, 3000, 5000, 8000, 10000, 20000, 30000]),
        "r_amt": rng.randrange(800, 5001, 100), "t_amt": rng.randrange(200, 1001, 100),
        "hotel": rng.choice(P.HOTELS), "gift": rng.choice([600, 800, 1000, 1200, 1600, 2000]),
        "district": rng.choice(P.DISTRICTS), "trail": rng.choice(P.TRAILS),
        "contest": rng.choice(P.CONTESTS), "pet": rng.choice(P.PETS),
        "breed": rng.choice(P.BREEDS), "buddyocc": rng.choice(P.OCCUPATIONS),
        "star": rng.choice(P.STAR_NAMES), "score": f"{rng.randrange(40, 96) / 10:.1f}",
        "drink": rng.choice(P.DRINKS), "dish": rng.choice(P.DISHES),
        "drama": rng.choice(P.DRAMAS), "song": rng.choice(P.SONGS),
        "movie": rng.choice(P.MOVIES), "flower": rng.choice(P.FLOWERS),
        "goods": rng.choice(P.GOODS), "goods2": rng.choice(P.GOODS2),
        "drink2": rng.choice(P.DRINKS2), "car": rng.choice(P.CARS),
        "shop": rng.choice(P.SHOPS),
        "nn": rng.randrange(2, 21), "nnnn": f"{rng.randrange(1000, 10000)}",
        "km": f"{rng.randrange(10, 81) / 10:.1f}",
        "pct": f"{rng.randrange(12, 46) / 10:.1f}",
        "pace": f"{rng.randrange(5, 9)}'{rng.randrange(10, 60):02d}\"",
        "rate": rng.randrange(1, 7), "drop": rng.randrange(4, 13),
        "metro": rng.randrange(1, 20), "pwdlen": rng.randrange(6, 9),
        "batt": rng.randrange(85, 101), "burn": rng.randrange(200, 601, 10),
        "top": rng.randrange(60, 96), "stepnow": rng.randrange(6000, 9001, 100),
        "stepgoal": rng.randrange(8000, 12001, 500),
        "sh": rng.randrange(3, 10), "sm": rng.randrange(0, 60),
        "used": rng.randrange(10, 26), "left": rng.randrange(5, 21),
        "eps": rng.randrange(1, 5), "bonusm": rng.randrange(1, 9),
        "marathon": rng.randrange(3, 7), "bigsteps": rng.randrange(6000, 12001, 500),
        "pork": rng.randrange(18, 46), "sq": rng.choice(["5万2", "6万8", "8万6", "9万9", "12万"]),
        "s_amt": rng.randrange(5, 501, 5), "s_amt2": rng.randrange(5, 501, 5),
        "med_amt": rng.choice([399, 499, 699, 899, 1299, 1499, 1599, 1999, 2399, 2999, 3299, 3999, 4599, 5499, 6999]),
        "big_amt": rng.choice([5000, 6000, 8000, 10000, 12000, 15000, 20000, 30000, 50000]),
        "w_amt": rng.choice([120, 180, 260, 320, 450, 520, 680, 780]),
        "food_amt": rng.randrange(3, 26),
        "rent": 0, "halfrent": 0, "rent2": rng.randrange(2000, 6001, 100),
        "yy": rng.randrange(1, 9), "dd": rng.randrange(2, 15),
        "journal": rng.choice(P.JOURNALS), "floor": rng.randrange(8, 19),
        "mult": rng.choice(["双", "三"]),
        "ww": rng.choice(P.WEEKDAYS),
        "rest": rng.randrange(62, 79), "spo2": rng.randrange(95, 100),
        "sleep": f"{rng.randrange(50, 86) / 10:.1f}",
        "steps": rng.randrange(4000, 12001), "kcal": rng.randrange(300, 701),
        "peak": rng.randrange(118, 139), "dur": rng.randrange(20, 36),
    }
    rent = rng.randrange(2500, 6001, 100)
    s["rent"] = rent
    s["halfrent"] = rent // 2
    ban = {persona["name"]}
    s["co"] = person_name(rng, ban); ban.add(s["co"])
    s["buddy"] = person_name(rng, ban); ban.add(s["buddy"])
    s["boss"] = rng.choice(P.SURNAMES) + rng.choice(P.BOSS_TITLES)
    return s


def pick_polarity(rng: random.Random) -> tuple:
    total = sum(w for _, w in POLARITY_WEIGHTS)
    r = rng.randrange(total)
    acc = 0
    for pol, w in POLARITY_WEIGHTS:
        acc += w
        if r < acc:
            return pol
    return (-1, -1)


def lover_word(rng: random.Random, male: bool, soc_code: str) -> str:
    if soc_code in ("S01", "S11"):
        return "老婆" if male else "老公"
    if soc_code in ("S02", "S03", "S04"):
        return rng.choice(["女友", "未婚妻"] if male else ["男友", "未婚夫"])
    return "女友" if male else "男友"


def build_question(idx: int, seed: int, persona_names: list) -> dict:
    rng = random.Random((seed * 100003 + idx * 1009) & 0xFFFFFFFF)
    name = persona_names[rng.randrange(len(persona_names))]
    gender = "男" if rng.random() < 0.5 else "女"
    persona = {"name": name, "gender": gender, "age": rng.randrange(22, 53),
               "occupation": rng.choice(P.OCCUPATIONS), "city": rng.choice(P.CITIES)}
    pol = pick_polarity(rng)
    c_code = rng.choice(CAREER_BY_VALENCE[pol[0]])
    s_code = rng.choice(SOCIAL_BY_VALENCE[pol[1]])
    f_code = rng.choice(FINANCE_CODES)
    slots = build_slots(rng, persona, f_code)
    slots["lover"] = lover_word(rng, gender == "男", s_code)

    events: list = []  # (time, seq, channel, content)
    seq = [0]
    def add_ev(t: str, ch: str, content: str, is_trap: bool = False) -> None:
        seq[0] += 1
        events.append((t, seq[0], ch, content, is_trap))

    # SENSOR 头
    add_ev(f"07:{rng.randrange(0, 11):02d}", "SENSOR",
           f"晨起体征摘要：静息心率 {slots['rest']}bpm，血氧 {slots['spo2']}%，昨夜睡眠 {slots['sleep']} 小时。")
    # 事业弧
    for bt, ch, tpl in P.CAREER[c_code]["events"]:
        add_ev(shift_time(bt, rng.randrange(-20, 21)), ch, fmt(tpl, slots, c_code))
    # 社交弧
    soc_times = []
    for bt, ch, tpl in P.SOCIAL[s_code]["events"]:
        t = shift_time(bt, rng.randrange(-20, 21))
        soc_times.append(t)
        add_ev(t, ch, fmt(tpl, slots, s_code))
    # 财务弧
    for bt, ch, tpl in P.FINANCE[f_code]["events"]:
        add_ev(shift_time(bt, rng.randrange(-15, 16)), ch, fmt(tpl, slots, f_code))
    # 陷阱：1 条窄口径打底 + 50% 第二条
    trap_classes = [rng.choice(NARROW_TRAP_CLASSES)]
    if rng.random() < 0.5:
        trap_classes.append(rng.choice(sorted(P.TRAPS.keys())))
    trap_times = rng.sample(TRAP_TIMES, len(trap_classes))
    used_trap_tpl: set = set()
    for cls, tt in zip(trap_classes, trap_times):
        cands = [t for t in P.TRAPS[cls] if t not in used_trap_tpl] or P.TRAPS[cls]
        tpl = rng.choice(cands)
        used_trap_tpl.add(tpl)
        ch = "APP" if rng.random() < 0.6 else "MIC"
        prefix = {"hotsearch": "新闻APP推送：", "loan_ads": "", "groupbuy": "微信-拼单群：",
                  "health_fwd": "微信-家族群：", "brag_vent": "", "scam": "",
                  "showoff": "朋友圈：", "soup_jokes": "微信-好友群："}.get(cls, "")
        if ch == "MIC" and cls in ("brag_vent",):
            content = f"（同事闲聊）{fmt(tpl, slots, 'trap')}"
        elif ch == "MIC":
            content = f"（路人闲聊）{fmt(tpl, slots, 'trap')}"
        else:
            content = prefix + fmt(tpl, slots, "trap")
        add_ev(shift_time(tt, rng.randrange(-10, 11)), ch, content, True)
    # 琐事：补足到 20~23 条
    target_total = rng.randrange(20, 24)
    n_fill = max(0, target_total - len(events) - 1)  # 预留 SENSOR 尾
    type_ids = rng.sample(range(len(P.FILLERS)), min(n_fill, len(P.FILLERS)))
    fill_times = rng.sample(FILLER_TIMES, len(type_ids))
    for ti, tt in zip(type_ids, fill_times):
        tpl = rng.choice(P.FILLERS[ti])
        add_ev(shift_time(tt, rng.randrange(-8, 9)),
               "APP" if any(k in tpl for k in ("APP", "短信", "推送", "微信", "银行", "：【")) else "MIC",
               fmt(tpl, slots, "filler"))
    # 健康：骤升 or 平稳
    spike = pol == (-1, -1) or s_code in SPIKE_SOCIAL or (
        P.SOCIAL[s_code]["valence"] == -1 and rng.random() < 0.35)
    if spike:
        atime = sorted(soc_times)[-2]
        add_ev(atime, "SENSOR",
               f"心率告警：{slots['peak']}bpm（静息状态，无运动特征），已记录情绪应激事件。")
        press = "偏高"
        h_core = (f"晨起静息心率 {slots['rest']}bpm，{atime}情绪冲击下心率骤升至{slots['peak']}bpm"
                  f"持续约{slots['dur']}分钟，全天步数{slots['steps']}步")
        h_acc = [fmt(a, slots, "health") for a in P.HEALTH_SPIKE_ACC]
        h_forbid = list(P.HEALTH_SPIKE_FORBID)
    else:
        press = "正常"
        h_core = (f"晨起静息心率 {slots['rest']}bpm，全天体征平稳，步数{slots['steps']}步，"
                  f"睡眠{slots['sleep']}小时")
        h_acc = list(P.HEALTH_STEADY_ACC)
        h_forbid = list(P.HEALTH_STEADY_FORBID)
    # SENSOR 尾
    add_ev("23:30", "SENSOR",
           f"全天汇总：总步数 {slots['steps']} 步，活动消耗 {slots['kcal']} 千卡，压力指数{press}。")

    events.sort(key=lambda e: (e[0], e[1]))
    ev_list = [{"time": t, "channel": ch, "content": c} for t, _, ch, c, _ in events]
    trap_idx = {i for i, e in enumerate(events) if e[4]}

    # ---------------- GT ----------------
    C, S, F = P.CAREER[c_code], P.SOCIAL[s_code], P.FINANCE[f_code]
    c_core = fmt(C["core"], slots, "c_core")
    s_core = fmt(S["core"], slots, "s_core")
    f_core = fmt(F["core"], slots, "f_core")
    emo = P.EMOTION[pol]
    e_core = fmt(emo["core"], slots, "e_core")
    g_core = f"{c_core}；{s_core}"
    g_acc = C["acc"][:2] + S["acc"][:2] + GLOBAL_ACC_EXTRA[pol]
    g_forbid = [C["forbid"][0], S["forbid"][0]] + GLOBAL_FORBID_EXTRA[pol]
    a2 = S.get("anchor2")
    if s_code in SINGLE_ANCHOR_SOCIAL or not a2:
        s_anch = [name]
    elif a2 == "lover":
        s_anch = [name, slots["lover"]]
    elif a2 == "kin_mom":
        s_anch = [name, "妈妈"]
    else:
        s_anch = [name, slots[a2]]
    gt = {
        "global_daily_summary": {
            "core_content": g_core, "acceptable_directions": g_acc,
            "forbidden_directions": g_forbid, "anchor_entities": [name, c_code, s_code]},
        "dim:health": {
            "core_content": h_core, "acceptable_directions": h_acc,
            "forbidden_directions": h_forbid,
            "anchor_entities": ["佩戴者", f"{slots['rest']}bpm", f"{slots['steps']}步", f"{slots['sleep']}小时"]},
        "dim:social": {
            "core_content": s_core, "acceptable_directions": list(S["acc"]),
            "forbidden_directions": list(S["forbid"]), "anchor_entities": s_anch},
        "dim:emotion": {
            "core_content": e_core, "acceptable_directions": list(emo["acc"]),
            "forbidden_directions": list(emo["forbid"]), "anchor_entities": [name]},
        "dim:finance": {
            "core_content": f_core,
            "acceptable_directions": [fmt(a, slots, "f_acc") for a in F["acc"]],
            "forbidden_directions": list(F["forbid"]),
            "anchor_entities": [name, f"{slots['amt']}元"]},
        "dim:career": {
            "core_content": c_core, "acceptable_directions": list(C["acc"]),
            "forbidden_directions": list(C["forbid"]),
            "anchor_entities": [name, persona["occupation"]]},
    }
    q = {"question_id": f"{QID_PREFIX}{idx + 1:05d}", "generator_agent": GENERATOR_AGENT,
         "persona": persona,
         "arc_tags": {"career": c_code, "social": s_code, "finance": f_code,
                      "polarity": [pol[0], pol[1]]},
         "cleaned_daily_stream": {"date_span": DATE_SPAN, "events": ev_list},
         "directional_ground_truth": gt}
    return q, trap_idx


def self_check(q: dict, trap_idx: set) -> list:
    """单卷自检，返回问题列表（空=通过）。"""
    issues = []
    if list(q.keys()) != ["question_id", "generator_agent", "persona", "arc_tags",
                          "cleaned_daily_stream", "directional_ground_truth"]:
        issues.append(f"顶层键异常: {list(q.keys())}")
    if set(q["persona"].keys()) != {"name", "gender", "age", "occupation", "city"}:
        issues.append("persona键异常")
    if set(q["arc_tags"].keys()) != {"career", "social", "finance", "polarity"}:
        issues.append("arc_tags键异常")
    evs = q["cleaned_daily_stream"]["events"]
    if not (16 <= len(evs) <= 26):
        issues.append(f"事件数异常: {len(evs)}")
    for e in evs:
        if set(e.keys()) != {"time", "channel", "content"}:
            issues.append(f"事件键异常: {e.keys()}")
            break
        if e["channel"] not in ("SENSOR", "MIC", "APP"):
            issues.append(f"channel异常: {e['channel']}")
            break
    ts = [e["time"] for e in evs]
    if ts != sorted(ts):
        issues.append("时间轴非单调")
    if evs[-1]["channel"] != "SENSOR" or evs[-1]["time"] != "23:30":
        issues.append("尾事件非23:30 SENSOR")
    blob = " ".join(e["content"] for e in evs)
    blob_nospace = blob.replace(" ", "")
    safe = " ".join(e["content"] for i, e in enumerate(evs) if i not in trap_idx)
    safe_nospace = safe.replace(" ", "")
    gt = q["directional_ground_truth"]
    if set(gt.keys()) != {"global_daily_summary", "dim:health", "dim:social", "dim:emotion",
                          "dim:finance", "dim:career"}:
        issues.append(f"GT维异常: {set(gt.keys())}")
        return issues
    tags = q["arc_tags"]
    for dim, g in gt.items():
        if set(g.keys()) != {"core_content", "acceptable_directions",
                             "forbidden_directions", "anchor_entities"}:
            issues.append(f"{dim}: GT字段异常")
            continue
        if not g["core_content"] or not g["acceptable_directions"] or not g["forbidden_directions"]:
            issues.append(f"{dim}: 标答字段缺失")
        if not g["anchor_entities"]:
            issues.append(f"{dim}: 锚点为空")
        for a in g["acceptable_directions"]:
            for f in g["forbidden_directions"]:
                if a == f or a in f or f in a:
                    issues.append(f"{dim}: 同义∩红线: {a}/{f}")
        for f in g["forbidden_directions"]:
            if f and f.replace(" ", "") in safe_nospace:
                issues.append(f"{dim}: 红线进可信流: {f}")
            if f and f in g["core_content"]:
                issues.append(f"{dim}: 红线进core: {f}")
    # 锚点可观测（流文本 + persona + 弧码）
    pname = q["persona"]["name"]
    occ = q["persona"]["occupation"]
    for dim, g in gt.items():
        for a in g["anchor_entities"]:
            if a in (pname, occ, "佩戴者", tags["career"], tags["social"]):
                continue
            if a.replace(" ", "") not in blob_nospace:
                issues.append(f"{dim}: 锚点不可观测: {a}")
    # finance锚点金额必须出现在流内
    famt = gt["dim:finance"]["anchor_entities"][1]
    if famt.replace(" ", "") not in blob_nospace:
        issues.append(f"finance金额锚点失联: {famt}")
    return issues


def build_bank(n: int, seed: int, out_path: Path) -> dict:
    rng = random.Random(seed)
    persona_names = make_persona_names(rng, 1000)
    stats = {"polarity": {}, "career": {}, "social": {}, "finance": {},
             "events_total": 0, "trap_papers": 0, "spike_papers": 0,
             "trap_redline_papers": 0}
    qids: set = set()
    texts: dict = {}
    narrow = ("热搜", "明星", "官宣", "转发", "分期", "免息", "抽奖", "领取",
              "砍一刀", "拼单", "大理", "辞职", "中奖")
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(n):
            q, trap_idx = build_question(i, seed, persona_names)
            if q["question_id"] in qids:
                raise RuntimeError(f"QID重复: {q['question_id']}")
            qids.add(q["question_id"])
            issues = self_check(q, trap_idx)
            if issues:
                raise RuntimeError(f"{q['question_id']}: {issues[:4]}")
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
            pol = tuple(q["arc_tags"]["polarity"])
            stats["polarity"][str(list(pol))] = stats["polarity"].get(str(list(pol)), 0) + 1
            for k in ("career", "social", "finance"):
                c = q["arc_tags"][k]
                stats[k][c] = stats[k].get(c, 0) + 1
            blob = " ".join(e["content"] for e in q["cleaned_daily_stream"]["events"])
            stats["events_total"] += len(q["cleaned_daily_stream"]["events"])
            if any(m in blob for m in narrow):
                stats["trap_papers"] += 1
            if "心率告警" in blob:
                stats["spike_papers"] += 1
            trap_blob = " ".join(
                e["content"] for i, e in enumerate(q["cleaned_daily_stream"]["events"])
                if i in trap_idx).replace(" ", "")
            if any(f.replace(" ", "") in trap_blob
                   for g in q["directional_ground_truth"].values()
                   for f in g["forbidden_directions"] if f):
                stats["trap_redline_papers"] += 1
            for e in q["cleaned_daily_stream"]["events"]:
                texts[e["content"]] = texts.get(e["content"], 0) + 1
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    top_reuse = sorted(texts.values(), reverse=True)[:5]
    return {"total": n, "seed": seed, "sha256": sha,
            "avg_events": round(stats["events_total"] / n, 2),
            "polarity": stats["polarity"], "career": stats["career"],
            "social": stats["social"], "finance": stats["finance"],
            "trap_paper_rate": round(stats["trap_papers"] / n, 4),
            "spike_rate": round(stats["spike_papers"] / n, 4),
            "trap_redline_rate": round(stats["trap_redline_papers"] / n, 4),
            "distinct_texts": len(texts), "top_reuse": top_reuse}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=2401)
    ap.add_argument("--out", default="benchmarks/daily_summary/questions/questions_daily24h_01a0aa2c.jsonl")
    ap.add_argument("--manifest", default="benchmarks/daily_summary/questions/manifest_daily24h_01a0aa2c.json")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = build_bank(args.n, args.seed, out)
    size_mb = round(out.stat().st_size / 1024 / 1024, 2)
    manifest = {"generator_agent": GENERATOR_AGENT, "generator_version": "24h-v1",
                "seed": args.seed, "total_questions": args.n,
                "file": str(out), "sha256": rep["sha256"], "size_mb": size_mb,
                "protocol": "daily24h-compatible（同键名/同类型，弧码不透明，内容原创）",
                "avg_events_per_day": rep["avg_events"],
                "polarity_distribution": rep["polarity"],
                "arc_distribution": {"career": rep["career"], "social": rep["social"],
                                     "finance": rep["finance"]},
                "narrow_trap_paper_rate": rep["trap_paper_rate"],
                "sensor_spike_rate": rep["spike_rate"],
                "trap_redline_paper_rate": rep["trap_redline_rate"],
                "distinct_event_texts": rep["distinct_texts"],
                "top_text_reuse": rep["top_reuse"],
                "grading_rule": "方向60+锚点召回40；命中任一红线该维0分整卷FAIL；综合≥80 PASS。见 daily24h_matcher_01a0aa2c.py。",
                "note": "盲做时剥离 directional_ground_truth；arc_tags 为不透明弧码（可聚类，不泄露方向）。"}
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("total_questions", "sha256", "size_mb",
                                              "avg_events_per_day", "narrow_trap_paper_rate",
                                              "distinct_event_texts", "top_text_reuse")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
