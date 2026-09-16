"""Agent-11 出题构造器：把内容池组装为 10,000 道高熵多模态清洗考题。

关键设计：
* 每题以一条主数据流为主战场，并按 95%（声纹流为 90%）的比例灌入垃圾碎片，
  其余 5% 为承载真实事实的信号碎片，`ground_truth_facts.source_ref_id` 严格指向信号碎片；
* 5% 致命事实题（跌倒冲击 / PVC 阵发 / 静息心动过速 / 低气压暴风雨 / 借还款约定 /
  家属托付 / 保密承诺 / 微弱求救 / 大额到账 / 法院传票 / 检验危急值 / 签约日程 /
  真实就医 / 真实辞职 / 隐性心血管危象）；
* 另设 ADVERSARIAL 陷阱题（甩腕伪冲击、跑步冲击、真假欠条对冲、银行钓鱼短信、
  冒充公检法诈骗、反讽玩笑），其标答方向是"识破"而非"采信"。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .pools import (
    APP_JUNK,
    ARTICLES,
    BANKS,
    BRANDS,
    CASE_TYPES,
    COMPANIES,
    COURTS,
    DARES,
    DIALOGUE_JUNK,
    DIRECTIONS,
    DRINKS,
    FESTIVALS,
    FOOD_ITEMS,
    GROUPS,
    HOSPITALS,
    KEYWORD_CLUSTERS,
    LAB_ITEMS,
    LINES,
    MALL_ITEMS,
    MIC_AMBIENT_DB,
    MIC_JUNK,
    PERSONAS,
    PLANS,
    PUSH_APPS,
    PUSH_TITLES,
    PURPOSES,
    ROADS,
    SCENE_BY_HOUR,
    SELLERS,
    SONGS,
    STATIONS,
    SURNAME_POOL,
    THREATS,
    TOPICS,
    VENTS,
    VOICEPRINT_NOISE_ROLES,
)

# ==========================================================================
# 传感器垃圾碎片库：刻意包含与"致命事实"高度形似的干扰项
# ==========================================================================

SENSOR_JUNK: List[Dict[str, Any]] = [
    dict(label="keyboard_typing_jitter", zh="桌面打字高频微抖", g_rms=(0.10, 0.24),
         g_peak=(0.28, 0.55), freq=(5.0, 9.0), dur=(15, 45),
         note="等间距小幅抖动，节拍与敲击一致，无自由落体段"),
    dict(label="mouse_clicking", zh="鼠标点击微动", g_rms=(0.07, 0.16),
         g_peak=(0.18, 0.34), freq=(3.0, 6.0), dur=(20, 60),
         note="幅度极低的离散脉冲，腕部姿态基本不变"),
    dict(label="phone_scrolling", zh="刷手机拇指滑动", g_rms=(0.09, 0.20),
         g_peak=(0.22, 0.41), freq=(2.0, 5.0), dur=(20, 70),
         note="低幅连续抖动，屏幕点亮时段吻合"),
    dict(label="walking_arm_swing", zh="步行摆臂", g_rms=(0.22, 0.52),
         g_peak=(0.55, 1.05), freq=(1.6, 2.1), dur=(30, 120),
         note="规律摆臂正弦包络，步频稳定，非冲击型"),
    dict(label="subway_carriage_jitter", zh="地铁车厢颠簸", g_rms=(0.28, 0.68),
         g_peak=(0.70, 1.45), freq=(3.0, 12.0), dur=(30, 180),
         note="宽频随机振动叠加轨道接缝周期冲击"),
    dict(label="bus_speedbump", zh="公交过减速带", g_rms=(0.30, 0.62),
         g_peak=(0.95, 1.60), freq=(1.5, 4.0), dur=(5, 25),
         note="单次竖向冲击后立即恢复行进节律"),
    dict(label="car_idle_vibration", zh="车内怠速振动", g_rms=(0.07, 0.18),
         g_peak=(0.16, 0.33), freq=(8.0, 20.0), dur=(40, 200),
         note="发动机基频振动，静止但非零动"),
    dict(label="elevator_start_stop", zh="电梯启停失重感", g_rms=(0.15, 0.32),
         g_peak=(0.30, 0.62), freq=(0.3, 0.9), dur=(4, 14),
         note="低频竖向分量变化，气压同步微幅波动"),
    dict(label="leg_bouncing", zh="坐姿抖腿", g_rms=(0.13, 0.29),
         g_peak=(0.26, 0.52), freq=(2.0, 4.5), dur=(20, 90),
         note="周期性小幅抖动，腕部无位移趋势"),
    dict(label="swatting_mosquito", zh="拍蚊子挥臂", g_rms=(0.35, 0.70),
         g_peak=(0.80, 1.35), freq=(1.0, 2.5), dur=(2, 8),
         note="孤立挥击后立刻回归静止，无后续体位改变"),
    dict(label="clapping_hands", zh="鼓掌", g_rms=(0.45, 0.85),
         g_peak=(0.90, 1.50), freq=(3.0, 7.0), dur=(5, 30),
         note="双手对击的高重复率短脉冲串"),
    dict(label="rocking_baby", zh="抱小孩轻晃", g_rms=(0.09, 0.19),
         g_peak=(0.18, 0.36), freq=(0.5, 0.9), dur=(60, 240),
         note="极低频钟摆式往复，姿态平稳"),
    dict(label="mopping_floor", zh="拖地往复", g_rms=(0.28, 0.58),
         g_peak=(0.55, 1.10), freq=(0.8, 1.6), dur=(30, 120),
         note="水平方向大幅往复，垂直冲击很小"),
    dict(label="wok_tossing", zh="颠锅翻炒", g_rms=(0.40, 0.78),
         g_peak=(0.85, 1.55), freq=(1.2, 2.4), dur=(10, 60),
         note="有节奏的上抛接锅，间歇出现"),
    dict(label="toothbrushing", zh="刷牙", g_rms=(0.18, 0.34),
         g_peak=(0.30, 0.60), freq=(3.0, 5.5), dur=(60, 180),
         note="恒定频率小幅往复，持续约三分钟"),
    dict(label="shaving", zh="剃须", g_rms=(0.13, 0.26),
         g_peak=(0.24, 0.46), freq=(6.0, 12.0), dur=(30, 90),
         note="高频低幅贴面移动"),
    dict(label="stair_climbing", zh="爬楼梯", g_rms=(0.42, 0.80),
         g_peak=(0.85, 1.65), freq=(1.5, 2.2), dur=(20, 90),
         note="台阶节律清晰，气压出现小幅下降"),
    dict(label="door_slam_recoil", zh="关门反冲", g_rms=(0.30, 0.60),
         g_peak=(0.62, 1.15), freq=(1.0, 3.0), dur=(1, 5),
         note="瞬时单次冲击，前后均为正常行走"),
    dict(label="laughing_table_slap", zh="大笑拍桌", g_rms=(0.50, 0.95),
         g_peak=(0.95, 1.70), freq=(1.5, 4.0), dur=(3, 20),
         note="伴随笑声与多人交谈的间歇拍击"),
    dict(label="washing_machine_adjacent", zh="洗衣机旁振动", g_rms=(0.24, 0.46),
         g_peak=(0.40, 0.85), freq=(12.0, 20.0), dur=(60, 300),
         note="高频机械振动经桌面传导，与体动无关"),
    dict(label="handwriting", zh="手写签字", g_rms=(0.09, 0.19),
         g_peak=(0.17, 0.33), freq=(2.0, 4.5), dur=(10, 60),
         note="细微不规则运动，幅度极小"),
    dict(label="bag_searching", zh="翻找包内物品", g_rms=(0.20, 0.42),
         g_peak=(0.38, 0.80), freq=(1.0, 3.0), dur=(5, 30),
         note="无规律多方向小幅晃动"),
    dict(label="hair_dryer_wrist", zh="吹风机手持振动", g_rms=(0.28, 0.52),
         g_peak=(0.45, 0.90), freq=(18.0, 30.0), dur=(60, 240),
         note="电机高频振动，姿态基本固定"),
    dict(label="chopping_vegetables", zh="切菜", g_rms=(0.33, 0.62),
         g_peak=(0.65, 1.25), freq=(1.5, 3.0), dur=(20, 90),
         note="垂直下切节律，砧板反冲明显"),
    dict(label="mahjong_tile_slam", zh="麻将牌拍桌", g_rms=(0.42, 0.82),
         g_peak=(0.85, 1.60), freq=(1.0, 3.0), dur=(2, 15),
         note="离散短促冲击，间隔随机"),
    dict(label="coughing_body_jerk", zh="咳嗽身体抖动", g_rms=(0.35, 0.68),
         g_peak=(0.70, 1.30), freq=(2.0, 5.0), dur=(1, 6),
         note="孤立抖动，PPG 未见提前搏动，与心电事件无关"),
    dict(label="sneezing_jerk", zh="喷嚏抖动", g_rms=(0.40, 0.75),
         g_peak=(0.80, 1.45), freq=(2.0, 5.0), dur=(1, 4),
         note="单次爆发后立即恢复，心律连续"),
    dict(label="wrist_flick_water", zh="甩手甩水", g_rms=(0.70, 1.30),
         g_peak=(2.20, 3.80), freq=(2.0, 4.0), dur=(2, 8),
         note="【形似跌倒】高g瞬时峰值，但无自由落体前段且0.8秒内恢复自主运动"),
    dict(label="treadmill_running_impact", zh="跑步机落地冲击", g_rms=(0.75, 1.35),
         g_peak=(1.90, 3.30), freq=(2.6, 3.2), dur=(120, 600),
         note="【形似跌倒】周期性高冲击，节律严格等间隔，心率同步线性上升"),
    dict(label="jump_rope", zh="跳绳", g_rms=(0.80, 1.40),
         g_peak=(2.00, 3.40), freq=(1.8, 2.8), dur=(30, 180),
         note="【形似跌倒】规律腾空落地，无静止期"),
    dict(label="reflex_catch_object", zh="掉落物应急接物", g_rms=(0.55, 1.05),
         g_peak=(1.20, 2.40), freq=(1.0, 3.0), dur=(1, 5),
         note="【形似跌倒】瞬时大幅挥臂，随后恢复站立姿态"),
    dict(label="petting_dog", zh="抚摸宠物", g_rms=(0.14, 0.28),
         g_peak=(0.25, 0.48), freq=(1.0, 2.5), dur=(30, 150),
         note="温和往复运动，环境底噪含犬类呼吸声"),
    dict(label="folding_clothes", zh="叠衣物", g_rms=(0.12, 0.24),
         g_peak=(0.22, 0.42), freq=(0.8, 2.0), dur=(30, 120),
         note="低幅双手协同动作"),
    dict(label="e_scooter_road_vibration", zh="电动车路面振动", g_rms=(0.35, 0.72),
         g_peak=(0.75, 1.60), freq=(4.0, 14.0), dur=(60, 400),
         note="持续宽频振动叠加砖缝冲击，速度稳定"),
    dict(label="sedentary_micro_adjust", zh="久坐姿势微调", g_rms=(0.05, 0.12),
         g_peak=(0.10, 0.24), freq=(0.2, 0.8), dur=(30, 200),
         note="长时间低活动量，仅偶发体位调整"),
]

SENSOR_AMBIENT_FACTS = [
    dict(intent="DAILY_COMMUTE", dim="dim:daily",
         tpl="佩戴者于{t}从{a}前往{b}，全程约{mins}分钟、{km}公里，以{mode}方式完成通勤",
         ents=["{a}", "{b}"]),
    dict(intent="SEDENTARY_LONG", dim="dim:health",
         tpl="佩戴者在{place}连续静坐约{hours}小时{mins}分，期间几乎无起身活动",
         ents=["{hours}小时"]),
    dict(intent="EXERCISE_SESSION", dim="dim:health",
         tpl="佩戴者在{place}进行{mins}分钟{mode}，平均心率{hr}bpm，估算消耗{kcal}千卡",
         ents=["{mins}分钟", "{hr}bpm"]),
    dict(intent="SLEEP_DURATION", dim="dim:health",
         tpl="佩戴者昨夜{start}入睡至{end}，总睡眠约{hours}小时{mins}分，静息心率均值{hr}bpm",
         ents=["{hours}小时"]),
    dict(intent="STAIR_CLIMB", dim="dim:health",
         tpl="佩戴者在{place}爬楼梯{floors}层，用时约{secs}秒，心率峰值{hr}bpm",
         ents=["{floors}层"]),
    dict(intent="WEATHER_EXPOSURE", dim="dim:environment",
         tpl="佩戴者在{place}户外暴露约{mins}分钟，环境{cond}，腕部皮温{temp}℃",
         ents=["{mins}分钟", "{cond}"]),
    dict(intent="TRAFFIC_RISK", dim="dim:safety",
         tpl="佩戴者骑行途中在{road}出现{n}次急刹避让，最大减速约{g}g",
         ents=["{road}", "{n}次"]),
    dict(intent="BAROMETRIC_STABLE", dim="dim:environment",
         tpl="当日气压在{lo}至{hi}hPa之间平稳波动，无明显天气系统影响",
         ents=["{lo}hPa", "{hi}hPa"]),
]

# ==========================================================================
# 通用工具
# ==========================================================================


class _Slots(dict):
    """format_map 用安全槽位字典：任何未预置的槽位都由 RNG 现场生成合理值。"""

    def __init__(self, rng: random.Random, persona: Dict[str, Any], extra: Optional[Dict[str, Any]] = None):
        super().__init__()
        self._rng = rng
        self._p = persona
        if extra:
            self.update(extra)

    def __missing__(self, key: str) -> Any:  # noqa: D105
        val = self._generate(key)
        self[key] = val  # 缓存：同一个 _Slots 实例内，同一槽位永远取到同一个值，
        return val        # 保证 core_content 与 anchor_entities 中的数字/人名不会自相矛盾

    def _generate(self, key: str) -> Any:
        rng, p = self._rng, self._p
        table = {
            "direction": lambda: rng.choice(DIRECTIONS),
            "station": lambda: rng.choice(STATIONS),
            "side": lambda: rng.choice(["左", "右"]),
            "city": lambda: p["city"],
            "line": lambda: rng.choice(LINES),
            "minutes": lambda: rng.randint(3, 62),
            "mins": lambda: rng.randint(3, 62),
            "stops": lambda: rng.randint(2, 18),
            "discount": lambda: rng.choice(["3", "4", "5", "6", "7"]),
            "brand": lambda: rng.choice(BRANDS),
            "threshold": lambda: rng.choice([199, 299, 399, 499, 599, 999]),
            "cut": lambda: rng.choice([30, 50, 80, 100, 150, 200]),
            "festival": lambda: rng.choice(FESTIVALS),
            "days": lambda: rng.randint(2, 9),
            "item": lambda: rng.choice(MALL_ITEMS + FOOD_ITEMS),
            "price": lambda: rng.choice([9.9, 19, 29, 39, 59, 79, 99, 129]),
            "prize": lambda: rng.choice(["智能手机", "电饭煲", "购物车免单", "加油卡"]),
            "num": lambda: rng.randint(2, 60),
            "num2": lambda: rng.randint(1, 9),
            "hour": lambda: rng.randint(1, 23),
            "hours": lambda: rng.randint(1, 9),
            "seconds": lambda: rng.randint(2, 40),
            "secs": lambda: rng.randint(2, 90),
            "db": lambda: rng.randint(42, 84),
            "song": lambda: rng.choice(SONGS),
            "bpm": lambda: rng.randint(88, 136),
            "meters": lambda: rng.randint(30, 220),
            "topic": lambda: rng.choice(TOPICS),
            "drink": lambda: rng.choice(DRINKS),
            "freq": lambda: round(rng.uniform(0.3, 28.0), 1),
            "count": lambda: rng.randint(2, 15),
            "dept": lambda: rng.choice(["内科", "外科", "骨科", "检验科", "放射科", "急诊", "心血管内科"]),
            "room": lambda: f"{rng.randint(1, 9)}0{rng.randint(1, 9)}",
            "floor": lambda: rng.randint(1, 12),
            "surname": lambda: rng.choice(SURNAME_POOL),
            "gender": lambda: rng.choice(["先生", "女士"]),
            "class": lambda: f"高{rng.randint(1, 3)}({rng.randint(1, 12)})班",
            "group": lambda: rng.choice(GROUPS),
            "article": lambda: rng.choice(ARTICLES),
            "code": lambda: rng.choice(["10690", "10657", "95588", "95533", "10086", "10010", "12368"]),
            "vcode": lambda: "".join(rng.choice("0123456789") for _ in range(6)),
            "purpose": lambda: rng.choice(PURPOSES),
            "wan": lambda: rng.randint(2, 30),
            "yuan": lambda: rng.choice([1, 3, 5, 8, 10, 18, 50, 100, 200]),
            "fen": lambda: rng.choice([1, 2, 3, 5, 8]),
            "url": lambda: f"https://{rng.choice(['dwz', 'url', 't', 's'])}.{rng.choice(['cn', 'cc', 'shop'])}/{rng.randint(10000, 99999)}",
            "app": lambda: rng.choice(PUSH_APPS),
            "title": lambda: rng.choice(PUSH_TITLES),
            "seller": lambda: rng.choice(SELLERS),
            "subject": lambda: rng.choice(["数学", "英语", "物理", "语文", "编程"]),
            "road": lambda: rng.choice(ROADS),
            "friend": lambda: rng.choice(SURNAME_POOL) + rng.choice(["姐", "哥", "老师", "总", "医生"]),
            "company": lambda: rng.choice(COMPANIES),
            "plan": lambda: rng.choice(PLANS),
            "amount": lambda: rng.choice([10, 20, 50]),
            "big": lambda: rng.choice([300, 500, 800, 1000]),
            "person": lambda: rng.choice(SURNAME_POOL) + "总",
            "vent": lambda: rng.choice(VENTS),
            "dare": lambda: rng.choice(DARES),
            "threat": lambda: rng.choice(THREATS),
            "date": lambda: f"{rng.randint(1, 12)}月{rng.randint(1, 28)}日",
            "place": lambda: rng.choice([p["home"], p["workplace"], "小区楼下", "公园", "菜市场", "地铁站"]),
            "mode": lambda: rng.choice(["步行", "地铁", "公交", "骑行", "自驾"]),
            "km": lambda: round(rng.uniform(0.8, 26.0), 1),
            "hr": lambda: rng.randint(58, 138),
            "kcal": lambda: rng.randint(60, 720),
            "floors": lambda: rng.randint(2, 18),
            "cond": lambda: rng.choice(["高温暴晒", "阴雨淋湿", "大风降温", "湿闷"]),
            "temp": lambda: round(rng.uniform(28.0, 39.5), 1),
            "n": lambda: rng.randint(2, 7),
            "g": lambda: round(rng.uniform(0.4, 1.2), 2),
            "lo": lambda: rng.randint(1004, 1014),
            "hi": lambda: rng.randint(1015, 1024),
            "t": lambda: f"{rng.randint(6, 22):02d}:{rng.randint(0, 59):02d}",
            "a": lambda: p["home"],
            "b": lambda: p["workplace"],
            "start": lambda: f"{rng.randint(21, 23):02d}:{rng.randint(0, 59):02d}",
            "end": lambda: f"{rng.randint(4, 7):02d}:{rng.randint(0, 59):02d}",
        }
        fn = table.get(key)
        return fn() if fn else f"<{key}>"


def _f(rng: random.Random, persona: Dict[str, Any], tpl: str, extra: Optional[Dict[str, Any]] = None) -> str:
    """一次性填充（每次调用生成新槽位值）。"""
    return tpl.format_map(_Slots(rng, persona, extra))


def _slots(rng: random.Random, persona: Dict[str, Any]) -> _Slots:
    """创建可复用的槽位上下文——同一实例内多次 format 保证取值一致。"""
    return _Slots(rng, persona)


def _fmt(slots: _Slots, tpl: str) -> str:
    return tpl.format_map(slots)


def _r(rng: random.Random, span: Tuple[float, float], nd: int = 2) -> float:
    return round(rng.uniform(span[0], span[1]), nd)


def _pick(rng: random.Random, seq: Sequence[Any]) -> Any:
    return seq[rng.randrange(len(seq))]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _keywords(rng: random.Random, intent: str, must: Sequence[str]) -> List[str]:
    """构造方向性同义词簇：核心词固定 + 随机补充，保证覆盖又不失多样性。"""
    cluster = KEYWORD_CLUSTERS.get(intent, [])
    base = [m for m in must if m not in cluster]
    extra = [k for k in cluster if k not in must]
    rng.shuffle(extra)
    return base + list(must) + extra[: max(4, 12 - len(must))]


class QuestionBuilder:
    """把 12 位佩戴者的生活流切成 10,000 道考题。"""

    def __init__(self, generator_agent: str, seed: int = 20260916) -> None:
        self.generator_agent = generator_agent
        self.seed = seed
        self.rng = random.Random(seed)
        self._qnum = 0
        self._base = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)

    # ------------------------------------------------------------------ 工具
    def _stamp(self, stream: str, qnum: int, kind: str, n: int) -> str:
        return f"{stream}{qnum:05d}{kind}{n:02d}"

    def _fact(self, qnum: int, n: int, dim: str, intent: str,
              entities: Sequence[str], core: str, ref: str,
              must: Sequence[str], confidence: float = 0.95) -> Dict[str, Any]:
        return dict(
            fact_id=f"F{qnum:05d}_{n:02d}",
            dimension_id=dim,
            semantic_intent=intent,
            anchor_entities=[e for e in entities if e],
            directional_keywords=_keywords(self.rng, intent, must),
            core_content=core,
            source_ref_id=ref,
            confidence=round(confidence, 2),
        )

    # ---------------------------------------------------- 传感器流（3,000 题）
    def build_sensor(self, qnum: int, persona: Dict[str, Any], ts: datetime,
                     critical: bool, adversarial: bool) -> Dict[str, Any]:
        rng = self.rng
        junk: List[Dict[str, Any]] = []
        signal: List[Dict[str, Any]] = []
        facts: List[Dict[str, Any]] = []

        n_junk = rng.randint(23, 30) if (critical or adversarial) else rng.randint(17, 22)
        pool = SENSOR_JUNK[:]
        rng.shuffle(pool)
        offset = 0.0
        for i in range(n_junk):
            spec = pool[i % len(pool)]
            dur = rng.randint(*spec["dur"])
            junk.append(dict(
                fragment_id=self._stamp("S", qnum, "J", i + 1),
                kind="imu_window",
                label=spec["label"],
                label_zh=spec["zh"],
                window_offset_s=round(offset, 1),
                duration_s=dur,
                g_rms=_r(rng, spec["g_rms"]),
                g_peak=_r(rng, spec["g_peak"]),
                dominant_freq_hz=_r(rng, spec["freq"], 1),
                hr_bpm=rng.randint(persona["resting_hr"][0], persona["resting_hr"][1] + 18),
                activity_confidence=round(rng.uniform(0.71, 0.97), 2),
                note=spec["note"],
            ))
            offset += dur + rng.randint(3, 60)

        # 原始序列：场景构造器可就地改写，使 50Hz 摘要与碎片级结论互相印证
        lo = rng.randint(1002, 1016)
        # 心率 60s 一档共 72 档（覆盖 72 分钟窗口）、气压 10min 一档共 24 档（覆盖 4 小时）
        hr = [rng.randint(persona["resting_hr"][0] - 4, persona["resting_hr"][1] + 22)
              for _ in range(72)]
        baro = [round(lo + rng.uniform(-1.5, 1.5), 1) for _ in range(24)]
        ctx = {"ts": ts, "hr": hr, "baro": baro}

        if adversarial:
            facts, signal = self._sensor_adversarial(qnum, persona, junk, offset, ctx)
        elif critical:
            facts, signal = self._sensor_critical(qnum, persona, ts, junk, offset, ctx)
        else:
            facts, signal = self._sensor_ambient(qnum, persona, ts, junk, offset, ctx)

        ts = ctx["ts"]
        last_end = offset + 120.0
        for f in signal:
            last_end = max(last_end, float(f.get("window_offset_s", 0.0))
                           + float(f.get("duration_s", 0.0)))
        stream = dict(
            sampling_hz=50,
            device_id=f"aios-band-{persona['pid'].lower()}-0731",
            window_start_utc=_iso(ts),
            window_end_utc=_iso(ts + timedelta(seconds=int(last_end) + 60)),
            fragments=junk + signal,
            hr_series_interval_s=60,
            hr_series_bpm=ctx["hr"],
            baro_series_interval_s=600,
            baro_hpa_series=ctx["baro"],
            gps_track=[
                dict(lat=round(rng.uniform(22.0, 40.0), 5), lon=round(rng.uniform(104.0, 121.0), 5),
                     t=_iso(ts + timedelta(minutes=i * 7)), speed_mps=round(rng.uniform(0.0, 12.0), 1))
                for i in range(rng.randint(3, 6))
            ],
        )
        junk_ids = [f["fragment_id"] for f in junk]
        return dict(sensor_stream=stream, facts=facts, junk_ids=junk_ids)

    def _sensor_ambient(self, qnum, persona, ts, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        spec = _pick(rng, SENSOR_AMBIENT_FACTS)
        slots = _slots(rng, persona)
        fid = self._stamp("S", qnum, "K", 1)
        txt = _fmt(slots, spec["tpl"])
        ents = [_fmt(slots, e) for e in spec["ents"]]
        sig = dict(
            fragment_id=fid, kind="derived_activity_segment",
            label=spec["intent"].lower(), label_zh=spec["intent"],
            window_offset_s=round(offset + 60, 1), duration_s=rng.randint(300, 5400),
            summary=txt, salience="ambient",
            note="低显著度但客观成立的日常体征事实，需保留而非剪枝",
        )
        return [self._fact(qnum, 1, spec["dim"], spec["intent"],
                           [persona["name"]] + ents, txt, fid,
                           _keywords(rng, spec["intent"], []))], [sig]

    def _sensor_critical(self, qnum, persona, ts, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        if roll < 0.30:
            return self._sc_fall(qnum, persona, ts, junk, offset, ctx)
        if roll < 0.60:
            return self._sc_pvc(qnum, persona, ts, junk, offset, ctx)
        if roll < 0.80:
            return self._sc_tachy(qnum, persona, junk, offset, ctx)
        return self._sc_baro(qnum, persona, junk, offset, ctx)

    def _sc_fall(self, qnum, persona, ts, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        f1 = self._stamp("S", qnum, "K", 1)
        f2 = self._stamp("S", qnum, "K", 2)
        f3 = self._stamp("S", qnum, "K", 3)
        peak = _r(rng, (3.6, 6.4), 2)
        still = rng.randint(38, 240)
        place = _pick(rng, [f"{persona['home']}楼梯间", "小区单元门口", "卫生间瓷砖地面",
                            "菜市场湿滑过道", "公园石板路", "地下车库坡道"])
        t = _iso(ts + timedelta(minutes=offset / 60 + 12))
        sig = [
            dict(fragment_id=f1, kind="imu_impact", label="hard_impact_freefall_preceded",
                 label_zh="真实跌倒冲击波形", window_offset_s=round(offset + 60, 1), duration_s=4,
                 g_peak=peak, g_rms=_r(rng, (1.1, 2.4)), impact_rise_ms=rng.randint(38, 96),
                 freefall_segment_ms=rng.randint(90, 220), posture_change_deg=rng.randint(65, 168),
                 note="存在自由落体前段 + 三轴合成冲顶 + 姿态角大幅翻转，符合真实跌倒力学三联征"),
            dict(fragment_id=f2, kind="post_impact_immobility", label="post_fall_stillness",
                 label_zh="跌倒后长时间零动", window_offset_s=round(offset + 64, 1), duration_s=still,
                 g_rms=_r(rng, (0.01, 0.05)), motion_energy=_r(rng, (0.001, 0.008), 3),
                 note=f"冲击后连续{still}秒近乎零动，未出现自主起身动作"),
            dict(fragment_id=f3, kind="ppg_response", label="post_fall_hr_surge",
                 label_zh="跌倒后心率应激升高", window_offset_s=round(offset + 64, 1), duration_s=still,
                 hr_before=rng.randint(*persona["resting_hr"]), hr_peak=rng.randint(104, 148),
                 spo2_percent=_r(rng, (92.0, 97.5), 1),
                 note="应激性心率升高伴血氧轻度下降，与冲击事件时间锁定"),
        ]
        hr_peak = sig[2]["hr_peak"]
        idx = min(len(ctx["hr"]) - 1, int((offset + 60) // 60))
        for k in range(idx, min(len(ctx["hr"]), idx + max(1, still // 60) + 2)):
            ctx["hr"][k] = hr_peak - rng.randint(0, 12)
        ctx["hr"][max(0, idx - 1)] = sig[2]["hr_before"]
        core = (f"佩戴者{persona['name']}于{t}在{place}发生真实跌倒，"
                f"冲击峰值{peak}g、跌倒后持续静止{still}秒未能自主起身")
        fact = self._fact(qnum, 1, "dim:safety", "FALL_IMPACT",
                          [persona["name"], place, f"{peak}g", f"{still}秒"],
                          core, f1, ["摔倒", "跌倒", "倒地", "摔伤", "滑倒"], confidence=0.97)
        return [fact], sig

    def _sc_pvc(self, qnum, persona, ts, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        f1 = self._stamp("S", qnum, "K", 1)
        f2 = self._stamp("S", qnum, "K", 2)
        n = rng.randint(6, 17)
        hour = rng.randint(1, 4)
        base_hr = rng.randint(52, 66)
        # 事件必须真的落在凌晨：本地时区 UTC+8，把窗口起点搬到当夜
        ctx["ts"] = ts.replace(hour=(hour - 8) % 24, minute=rng.randint(0, 59),
                               second=rng.randint(0, 59))
        ev_off = round(offset + 30, 1)
        idx = min(len(ctx["hr"]) - 6, int(ev_off // 60))
        ctx["hr"][max(0, idx - 3):idx] = [base_hr + rng.randint(-3, 3) for _ in range(3)]
        for k in range(idx, min(len(ctx["hr"]), idx + 6)):   # 连发早搏：忽快忽漏的锯齿
            ctx["hr"][k] = base_hr + rng.choice([-14, -11, 22, 27, -16, 25])
        sig = [
            dict(fragment_id=f1, kind="ppg_arrhythmia", label="pvc_burst_nocturnal",
                 label_zh="夜间室性早搏连续阵发", window_offset_s=ev_off,
                 duration_s=rng.randint(20, 90),
                 pvc_burst_count=n, pvc_coupling_interval_ms=rng.randint(280, 430),
                 rr_irregularity_index=_r(rng, (0.31, 0.62)), hr_baseline=base_hr,
                 local_clock=f"{hour:02d}:{rng.randint(0, 59):02d}",
                 note=f"睡眠期连续{n}次提前搏动伴代偿间歇，脉搏波形态宽大畸形，非运动伪差"),
            dict(fragment_id=f2, kind="sleep_context", label="sleep_stage_n2",
                 label_zh="事件发生于睡眠N2期", window_offset_s=ev_off,
                 duration_s=rng.randint(600, 3600), body_motion_energy=_r(rng, (0.002, 0.01), 3),
                 note="事件期间体动能量极低，可排除翻身与肢体运动导致的伪差"),
        ]
        core = (f"佩戴者{persona['name']}在凌晨{hour}时睡眠中出现连续{n}次室性早搏阵发，"
                f"期间体动极低可排除运动伪差")
        fact = self._fact(qnum, 1, "dim:health", "CARDIAC_PVC_BURST",
                          [persona["name"], f"{n}次", f"凌晨{hour}时"],
                          core, f1, ["室性早搏", "早搏", "室早", "心律失常"], confidence=0.94)
        return [fact], sig

    def _sc_tachy(self, qnum, persona, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        f1 = self._stamp("S", qnum, "K", 1)
        f2 = self._stamp("S", qnum, "K", 2)
        hr = rng.randint(104, 132)
        mins = rng.randint(35, 150)
        for k in range(len(ctx["hr"])):
            ctx["hr"][k] = hr + rng.randint(-6, 9)
        sig = [
            dict(fragment_id=f1, kind="ppg_resting_tachycardia", label="sustained_resting_tachycardia",
                 label_zh="静息状态持续心动过速", window_offset_s=round(offset + 40, 1),
                 duration_s=mins * 60, hr_mean=hr, hr_min=hr - rng.randint(4, 12),
                 hr_max=hr + rng.randint(3, 16), hrv_rmssd_ms=rng.randint(9, 26),
                 note=f"连续{mins}分钟静息心率均值{hr}bpm，显著高于本人基线"
                      f"{persona['resting_hr'][0]}-{persona['resting_hr'][1]}bpm"),
            dict(fragment_id=f2, kind="activity_context", label="verified_sedentary",
                 label_zh="同期体动确认静止", window_offset_s=round(offset + 40, 1),
                 duration_s=mins * 60, g_rms=_r(rng, (0.03, 0.10)),
                 note="同期IMU体动极低，心动过速不能由运动解释"),
        ]
        core = (f"佩戴者{persona['name']}在静息无体动状态下心率持续{mins}分钟维持在均值{hr}bpm，"
                f"明显高于其个人基线")
        fact = self._fact(qnum, 1, "dim:health", "RESTING_TACHYCARDIA",
                          [persona["name"], f"{hr}bpm", f"{mins}分钟"],
                          core, f1, ["静息心动过速", "心率过快", "心动过速", "心悸"], confidence=0.93)
        return [fact], sig

    def _sc_baro(self, qnum, persona, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        f1 = self._stamp("S", qnum, "K", 1)
        f2 = self._stamp("S", qnum, "K", 2)
        p0 = rng.randint(1012, 1020)
        p1 = p0 - rng.randint(22, 38)
        symptom = rng.random() < 0.5
        n_b = len(ctx["baro"])
        for k in range(n_b):
            ctx["baro"][k] = round(p0 + (p1 - p0) * (k / max(n_b - 1, 1))
                                   + rng.uniform(-0.6, 0.6), 1)
        sig = [
            dict(fragment_id=f1, kind="barometric_plunge", label="rapid_pressure_drop",
                 label_zh="气压短时骤降", window_offset_s=round(offset + 50, 1),
                 duration_s=rng.randint(7200, 14400),
                 baro_start_hpa=p0, baro_end_hpa=p1, drop_hpa=p0 - p1,
                 drop_rate_hpa_per_3h=round((p0 - p1) / 2, 1),
                 note=f"3小时内气压由{p0}hPa跌至{p1}hPa，降幅{p0 - p1}hPa，符合强低压系统过境"),
        ]
        ents = [persona["name"], f"{p0}hPa", f"{p1}hPa"]
        dim, intent, core, must = ("dim:environment", "BAROMETRIC_STORM",
                                   f"佩戴者所在位置3小时内气压由{p0}hPa骤降至{p1}hPa，预示强对流暴风雨天气逼近",
                                   ["气压骤降", "低气压", "暴风雨"])
        if symptom:
            hr_mean = rng.randint(78, 102)
            f2s = self._stamp("S", qnum, "K", 2)
            sig.append(dict(fragment_id=f2s, kind="symptom_correlation", label="pressure_triggered_pain",
                            label_zh="气压变化诱发躯体症状", window_offset_s=round(offset + 90, 1),
                            duration_s=rng.randint(900, 5400),
                            reported_symptom=_pick(rng, ["偏头痛加重", "关节酸痛", "胸闷", "旧伤口隐痛"]),
                            hr_mean=hr_mean,
                            note="气压骤降窗口内同步出现躯体不适与心率上抬"))
            tail = len(ctx["hr"]) - min(len(ctx["hr"]), 10)
            for k in range(tail, len(ctx["hr"])):
                ctx["hr"][k] = hr_mean + rng.randint(-6, 8)
            core = (f"气压3小时内由{p0}hPa骤降至{p1}hPa，同期佩戴者{persona['name']}"
                    f"出现躯体不适且心率上抬，存在气象诱因关联")
            ents = ents + ["躯体不适"]
            must = must + ["诱发不适"]
        else:
            sig.append(dict(fragment_id=self._stamp("S", qnum, "K", 2), kind="gps_shelter",
                            label_zh="转入室内避雨", label="indoor_shelter",
                            window_offset_s=round(offset + 120, 1), duration_s=rng.randint(600, 3600),
                            note="定位由室外切换为室内并停留"))
        return [self._fact(qnum, 1, dim, intent, ents, core, f1, must, confidence=0.9)], sig

    def _sensor_adversarial(self, qnum, persona, junk, offset, ctx) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        if roll < 0.5:
            f1 = self._stamp("S", qnum, "K", 1)
            peak = _r(rng, (2.4, 3.9), 2)
            sig = [dict(fragment_id=f1, kind="imu_impact", label="high_g_without_freefall",
                        label_zh="高g冲击但无自由落体前段", window_offset_s=round(offset + 70, 1),
                        duration_s=3, g_peak=peak, freefall_segment_ms=0,
                        post_impact_stillness_s=0, resume_motion_ms=rng.randint(320, 900),
                        hr_delta=rng.randint(-3, 6),
                        note="峰值虽高但缺失自由落体段、无姿态翻转、0.9秒内即恢复自主运动，"
                             "且心率无应激反应——判定为甩手腕/抖落水滴类日常动作，非真实跌倒")]
            core = (f"佩戴者{persona['name']}腕部出现{peak}g高幅冲击，但无自由落体前段、"
                    f"无姿态翻转、冲击后立即恢复自主运动且心率无应激，判定为日常甩腕而非真实跌倒")
            return [self._fact(qnum, 1, "dim:safety", "FALL_IMPACT_FAKED",
                               [persona["name"], f"{peak}g"], core, f1,
                               ["非真实跌倒", "并非摔倒", "日常甩腕", "误判为跌倒"],
                               confidence=0.92)], sig
        f1 = self._stamp("S", qnum, "K", 1)
        peak = _r(rng, (2.0, 3.2), 2)
        dur = rng.randint(240, 900)
        idx = min(len(ctx["hr"]) - 4, int((offset + 80) // 60))
        span = min(len(ctx["hr"]) - idx, max(2, dur // 60))
        for k in range(span):
            ctx["hr"][idx + k] = 92 + int(58 * k / span)   # 线性爬升
        sig = [dict(fragment_id=f1, kind="imu_periodic_impact", label="strictly_periodic_impact",
                    label_zh="严格等间隔周期性高冲击", window_offset_s=round(offset + 80, 1),
                    duration_s=dur, g_peak=peak, step_cadence_hz=_r(rng, (2.6, 3.1), 2),
                    cadence_cv=_r(rng, (0.01, 0.05), 3), hr_progression="线性上升",
                    note="冲击间隔变异系数极低呈严格周期，心率线性爬升，"
                         "判定为跑步/跳绳等周期性运动，不是跌倒")]
        core = (f"佩戴者{persona['name']}在{dur // 60}分钟内出现峰值{peak}g的严格等间隔周期性冲击，"
                f"步频变异系数极低伴心率线性上升，判定为跑步锻炼而非跌倒事件")
        return [self._fact(qnum, 1, "dim:health", "EXERCISE_SESSION",
                           [persona["name"], f"{peak}g", f"{dur // 60}分钟"], core, f1,
                           ["跑步", "锻炼", "运动", "非跌倒"], confidence=0.93)], sig

    # ------------------------------------------------- MIC 录音流（3,000 题）
    def build_mic(self, qnum: int, persona: Dict[str, Any], ts: datetime,
                  critical: bool, adversarial: bool) -> Dict[str, Any]:
        rng = self.rng
        hour = (ts.hour + 8) % 24
        scenes = SCENE_BY_HOUR[hour]
        junk: List[Dict[str, Any]] = []
        n_junk = rng.randint(21, 28) if (critical or adversarial) else rng.randint(16, 21)
        offset = 0.0
        for i in range(n_junk):
            scene = _pick(rng, scenes)
            tpl = _pick(rng, MIC_JUNK[scene])
            lo, hi = MIC_AMBIENT_DB[scene]
            dur = round(rng.uniform(2.0, 22.0), 1)
            junk.append(dict(
                snippet_id=self._stamp("M", qnum, "J", i + 1),
                start_offset_s=round(offset, 1),
                duration_s=dur,
                ambient_noise_db=rng.randint(lo, hi),
                snr_db=round(rng.uniform(-6.0, 4.0), 1),
                scene=scene,
                text=_f(rng, persona, tpl),
                is_background_chatter=True,
                speaker_diarization="unknown_or_multi",
                asr_confidence=round(rng.uniform(0.28, 0.74), 2),
            ))
            offset += dur + round(rng.uniform(1.0, 25.0), 1)

        if adversarial:
            facts, sig = self._mic_adversarial(qnum, persona, offset)
        elif critical:
            facts, sig = self._mic_critical(qnum, persona, offset)
        else:
            facts, sig = self._mic_ambient(qnum, persona, offset)

        junk_ids = [s["snippet_id"] for s in junk]
        return dict(mic_stream=junk + sig, facts=facts, junk_ids=junk_ids)

    def _mic_ambient(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        kinds = [
            dict(intent="SOCIAL_CHAT", dim="dim:social", who=lambda: _pick(rng, persona["colleagues"]),
                 tpl="佩戴者与{who}在{place}进行约{mins}分钟日常寒暄闲聊，话题为{topic}，无实质约定",
                 txt="{who}：哎你说这{topic}，现在真是越来越看不懂了。"),
            dict(intent="FAMILY_DAILY", dim="dim:family", who=lambda: _pick(rng, persona["close"]),
                 tpl="佩戴者与{who}通话{mins}分钟，内容为家常问候与生活琐事，无重大信息",
                 txt="{who}：晚上想吃什么？我顺路买点{item}回去。"),
            dict(intent="MEAL_EVENT", dim="dim:daily", who=lambda: "餐馆服务员",
                 tpl="佩戴者在{place}用餐，向服务员点单{item}与{drink}，全程约{mins}分钟",
                 txt="服务员：您点的{item}好了，慢用。"),
            dict(intent="DELIVERY_EVENT", dim="dim:logistics", who=lambda: "驿站店员",
                 tpl="佩戴者在小区驿站凭取件码领取{num}件快递，全程约{mins}分钟",
                 txt="店员：{num}号货架，取件码报一下，麻烦签个字。"),
            dict(intent="MEDICAL_APPOINTMENT", dim="dim:health", who=lambda: "医院随访护士",
                 tpl="佩戴者接到医院随访电话，被提醒{days}天后到{dept}复诊",
                 txt="护士：{surname}您好，提醒您{days}天后到{dept}复诊，记得空腹。"),
            dict(intent="WORK_OVERTIME", dim="dim:career", who=lambda: _pick(rng, persona["colleagues"]),
                 tpl="佩戴者与{who}在工作场所沟通进度，确认当晚需加班约{hours}小时",
                 txt="{who}：这个今天必须交，你辛苦一下，晚上加个班。"),
            dict(intent="CHILD_SCHOOL", dim="dim:family", who=lambda: "班主任",
                 tpl="佩戴者与班主任通话{mins}分钟，沟通孩子在校的{topic}问题",
                 txt="老师：孩子最近{topic}方面有点状况，家长这边也配合一下。"),
            dict(intent="SOCIAL_CHAT", dim="dim:social", who=lambda: _pick(rng, persona["close"]),
                 tpl="佩戴者与{who}在{place}偶遇并寒暄{mins}分钟，聊及{topic}，无实质约定",
                 txt="{who}：好久不见啊，最近{topic}那边怎么样了？"),
        ]
        spec = _pick(rng, kinds)
        slots = _slots(rng, persona)
        who = spec["who"]()
        mins = rng.randint(2, 28)
        slots.update(dict(who=who.split("(")[0], mins=mins))
        fid = self._stamp("M", qnum, "K", 1)
        core = _fmt(slots, spec["tpl"])
        sig = [dict(
            snippet_id=fid, start_offset_s=round(offset + 20, 1), duration_s=round(mins * 4.5, 1),
            ambient_noise_db=rng.randint(60, 70), snr_db=round(rng.uniform(8.0, 19.0), 1),
            scene="foreground_dialogue",
            text=_fmt(slots, spec["txt"]),
            is_background_chatter=False,
            speaker_diarization="user+1",
            asr_confidence=round(rng.uniform(0.86, 0.98), 2),
            note="前景清晰对话，信噪比高，具备可提纯的事实价值",
        )]
        return [self._fact(qnum, 1, spec["dim"], spec["intent"],
                           [persona["name"], slots["who"], f"{mins}分钟"], core, fid,
                           _keywords(rng, spec["intent"], []))], sig

    def _mic_critical(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        if roll < 0.26:
            return self._mc_debt(qnum, persona, offset)
        if roll < 0.46:
            return self._mc_entrust(qnum, persona, offset)
        if roll < 0.62:
            return self._mc_nda(qnum, persona, offset)
        if roll < 0.80:
            return self._mc_sos(qnum, persona, offset)
        return self._mc_argument(qnum, persona, offset)

    def _mc_debt(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        who = _pick(rng, [c for c in persona["close"] if "(" in c] or persona["close"])
        short = who.split("(")[0]
        amount = _pick(rng, [5, 8, 10, 12, 15, 20, 30, 50, 80, 100])
        day = rng.randint(5, 28)
        month_word = _pick(rng, ["下月", "下个月", "下月"])
        fid = self._stamp("M", qnum, "K", 1)
        line = _pick(rng, [
            f"{month_word}{day}号{short}还我{amount}万，这事儿说好了啊。",
            f"那{amount}万块钱，{month_word}{day}号之前肯定给你，放心。",
            f"借条我写了，{amount}万，{month_word}{day}号还，白纸黑字。",
            f"{short}你记着，{month_word}{day}号，{amount}万，别再拖了。",
        ])
        sig = [dict(
            snippet_id=fid, start_offset_s=round(offset + 30, 1), duration_s=round(rng.uniform(6.0, 18.0), 1),
            ambient_noise_db=rng.randint(60, 74), snr_db=round(rng.uniform(6.0, 16.0), 1),
            scene="foreground_dialogue", text=line, is_background_chatter=False,
            speaker_diarization="user+counterpart", asr_confidence=round(rng.uniform(0.88, 0.99), 2),
            voiceprint_match=short,
            note="清晰双人对话，含明确金额、人名与还款日期，属高价值约定事实",
        )]
        core = f"{short}与佩戴者{persona['name']}口头约定：{month_word}{day}日归还借款{amount}万元"
        return [self._fact(qnum, 1, "dim:finance", "REPAYMENT_PROMISE",
                           [short, persona["name"], f"{amount}万元", f"{month_word}{day}日"],
                           core, fid, ["约定还款", "还款约定", "还钱", "借款"], confidence=0.96)], sig

    def _mc_entrust(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        kin = _pick(rng, persona["children"] or persona["close"])
        kin_short = kin.split("(")[0]
        amount = _pick(rng, [8, 12, 18, 26, 40, 60])
        fid = self._stamp("M", qnum, "K", 1)
        line = _pick(rng, [
            f"{kin_short}，我卡里那{amount}万，密码是你生日，万一有个啥事，都留给你。",
            f"我要是有个三长两短，房子和那{amount}万都给{kin_short}，你们别争。",
            f"这话我交代在前面：{amount}万存折在衣柜第二层，交给{kin_short}。",
        ])
        sig = [dict(
            snippet_id=fid, start_offset_s=round(offset + 40, 1), duration_s=round(rng.uniform(9.0, 26.0), 1),
            ambient_noise_db=rng.randint(60, 68), snr_db=round(rng.uniform(9.0, 18.0), 1),
            scene="quiet_home_dialogue", text=line, is_background_chatter=False,
            speaker_diarization="user+family", asr_confidence=round(rng.uniform(0.87, 0.98), 2),
            note="安静环境下的家属托付性陈述，含财产指向，须完整保留",
        )]
        core = (f"佩戴者{persona['name']}向家属{kin_short}口头交代：若有意外，"
                f"名下{amount}万元存款归{kin_short}所有")
        return [self._fact(qnum, 1, "dim:family", "FAMILY_ENTRUSTMENT",
                           [persona["name"], kin_short, f"{amount}万元"], core, fid,
                           ["托付", "嘱托", "交代后事", "口头遗嘱"], confidence=0.94)], sig

    def _mc_nda(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        partner = _pick(rng, persona["colleagues"] + persona["close"])
        short = partner.split("(")[0]
        penalty = _pick(rng, [50, 80, 100, 200, 300, 500])
        proj = _pick(rng, ["新厂区选址", "并购标的估值", "投标底价", "临床数据", "客户名单与报价", "融资条款"])
        fid = self._stamp("M", qnum, "K", 1)
        line = _pick(rng, [
            f"{proj}这事在签约前谁都不能说，包括{short}，听见没有？",
            f"这是保密条款，泄露出去要赔{penalty}万，你把嘴管住。",
            f"{proj}的细节属于商业机密，签约前一个字都不能往外漏。",
        ])
        sig = [dict(
            snippet_id=fid, start_offset_s=round(offset + 50, 1), duration_s=round(rng.uniform(7.0, 22.0), 1),
            ambient_noise_db=rng.randint(60, 70), snr_db=round(rng.uniform(8.0, 17.0), 1),
            scene="meeting_room_dialogue", text=line, is_background_chatter=False,
            speaker_diarization="user+colleague", asr_confidence=round(rng.uniform(0.86, 0.97), 2),
            note="涉及明确保密义务与违约金额的商业对话",
        )]
        core = (f"佩戴者{persona['name']}就「{proj}」向{short}作出商业保密承诺，"
                f"约定签约前不得外泄，违约金{penalty}万元")
        return [self._fact(qnum, 1, "dim:career", "NDA_CONFIDENTIALITY",
                           [persona["name"], short, proj, f"{penalty}万元"], core, fid,
                           ["保密承诺", "保密约定", "不得外泄", "商业机密"], confidence=0.94)], sig

    def _mc_sos(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        fid = self._stamp("M", qnum, "K", 1)
        f2 = self._stamp("M", qnum, "K", 2)
        line = _pick(rng, [
            "胸口疼……起不来……帮我打120……",
            "救命……我不行了……喘不上气……",
            "有人吗……我摔了……动不了……",
            "心脏……好疼……快叫救护车……",
        ])
        sig = [
            dict(snippet_id=fid, start_offset_s=round(offset + 60, 1), duration_s=round(rng.uniform(3.0, 9.0), 1),
                 ambient_noise_db=rng.randint(62, 80), snr_db=round(rng.uniform(-4.0, 2.5), 1),
                 scene="buried_in_noise", text=line, is_background_chatter=False,
                 speaker_diarization="user_weak", asr_confidence=round(rng.uniform(0.31, 0.55), 2),
                 voice_energy_db=rng.randint(28, 41),
                 note="【关键】音量极低、被环境噪声掩埋，ASR置信度仅三至五成，"
                      "但内容与佩戴者声纹高度匹配，属微弱求救信号，绝不可当噪声剪掉"),
            dict(snippet_id=f2, start_offset_s=round(offset + 66, 1), duration_s=6.0,
                 ambient_noise_db=rng.randint(62, 80), snr_db=round(rng.uniform(-4.0, 2.0), 1),
                 scene="buried_in_noise", text="（微弱喘息与衣物摩擦声，随后长时间无声）",
                 is_background_chatter=False, speaker_diarization="user_weak",
                 asr_confidence=0.22,
                 note="求救后语音活动骤降，与IMU静止段吻合"),
        ]
        core = (f"佩戴者{persona['name']}在环境噪声中发出音量极低的求救，"
                f"自述胸痛无法起身，声纹归属机主，ASR置信度不足但内容危急")
        return [self._fact(qnum, 1, "dim:safety", "WEAK_SOS",
                           [persona["name"], "胸痛", "120"], core, fid,
                           ["求救", "呼救", "救命", "打120"], confidence=0.88)], sig

    def _mc_argument(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        who = _pick(rng, persona["close"] + persona["colleagues"])
        short = who.split("(")[0]
        topic = _pick(rng, ["借款迟迟未还", "工程款分摊", "孩子教育分歧", "赡养责任分配",
                            "合同违约责任", "房租涨价", "项目背锅"])
        fid = self._stamp("M", qnum, "K", 1)
        sig = [dict(
            snippet_id=fid, start_offset_s=round(offset + 45, 1), duration_s=round(rng.uniform(25.0, 90.0), 1),
            ambient_noise_db=rng.randint(60, 78), snr_db=round(rng.uniform(4.0, 12.0), 1),
            scene="heated_dialogue",
            text=_pick(rng, [
                f"你凭什么这么说！{topic}你自己心里没数吗？",
                f"行行行，你说得都对！这事儿就这么定了！",
                f"我们没什么好谈的了，你爱怎么想怎么想！",
                f"{topic}拖到今天，你还有脸说这种话？",
            ]),
            is_background_chatter=False, speaker_diarization="user+counterpart",
            asr_confidence=round(rng.uniform(0.80, 0.96), 2),
            voice_emotion="高唤醒/负效价", fundamental_freq_hz=rng.randint(180, 320),
            note="双方音量抬升、基频升高、话语重叠明显，判定为激烈言语冲突",
        )]
        core = f"佩戴者{persona['name']}与{short}因{topic}发生激烈言语争执，双方情绪激动、互不相让"
        return [self._fact(qnum, 1, "dim:social", "ARGUMENT_CONFLICT",
                           [persona["name"], short, topic], core, fid,
                           ["吵架", "争吵", "冲突", "口角", "争执"], confidence=0.95)], sig

    def _mic_adversarial(self, qnum, persona, offset) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        fid = self._stamp("M", qnum, "K", 1)
        if rng.random() < 0.5:
            line = _pick(rng, [
                "这里是市公安局，你名下账户涉嫌一起洗钱案，现在需要你配合调查。",
                "我是社保中心的，你的医保卡在外地被盗刷了，需要立即核实身份。",
                "你包裹里有违禁品，海关已扣留，请转账到安全账户核验。",
            ])
            sig = [dict(snippet_id=fid, start_offset_s=round(offset + 55, 1),
                        duration_s=round(rng.uniform(12.0, 40.0), 1),
                        ambient_noise_db=rng.randint(60, 70), snr_db=round(rng.uniform(8.0, 16.0), 1),
                        scene="phone_call", text=line, is_background_chatter=False,
                        speaker_diarization="stranger_caller",
                        asr_confidence=round(rng.uniform(0.85, 0.97), 2),
                        caller_number_masked=f"00{rng.randint(10, 99)}****{rng.randint(1000, 9999)}",
                        note="话术含「安全账户」「配合调查」「立即核实」等典型诈骗要素，"
                             "来电为境外改号，应判定为诈骗而非真实公务")]
            core = (f"佩戴者{persona['name']}接到自称公检法/社保机构的来电要求转账至「安全账户」，"
                    f"话术与改号特征齐备，判定为冒充类电信诈骗")
            return [self._fact(qnum, 1, "dim:safety", "FRAUD_ATTEMPT",
                               [persona["name"], "安全账户", "冒充公检法"], core, fid,
                               ["诈骗电话", "冒充公检法", "疑似诈骗"], confidence=0.95)], sig
        line = _pick(rng, [
            "（影视剧台词）你涉嫌洗钱，现在依法对你采取强制措施！",
            "（短视频外放）警察同志，我真的没有骗人！",
            "（话剧排练台词）钱我下周一定还你，你相信我这一次！",
        ])
        sig = [dict(snippet_id=fid, start_offset_s=round(offset + 55, 1),
                    duration_s=round(rng.uniform(8.0, 30.0), 1),
                    ambient_noise_db=rng.randint(60, 74), snr_db=round(rng.uniform(3.0, 11.0), 1),
                    scene="media_playback", text=line, is_background_chatter=True,
                    speaker_diarization="non_user_media",
                    asr_confidence=round(rng.uniform(0.70, 0.92), 2),
                    note="语音来自屏幕外放而非现场对话：无对话轮次、含配乐与混响、"
                         "说话人声纹与现场任何人均不匹配——属媒体播放噪声，不可提纯为事实")]
        core = (f"录音中出现的「涉洗钱」「下周还钱」等语句经判定为影视/短视频外放内容，"
                f"非佩戴者{persona['name']}现场真实对话，不应作为事实提纯")
        return [self._fact(qnum, 1, "dim:social", "MEDIA_PLAYBACK_NOISE",
                           [persona["name"], "媒体外放"], core, fid,
                           ["媒体外放", "非真实对话", "影视台词", "外放噪声"], confidence=0.9)], sig

    # ------------------------------------------------- 声纹聚类流（2,000 题）
    def build_voiceprint(self, qnum: int, persona: Dict[str, Any], ts: datetime,
                         critical: bool, adversarial: bool) -> Dict[str, Any]:
        rng = self.rng
        speakers: List[Dict[str, Any]] = []
        facts: List[Dict[str, Any]] = []
        # 规范固定：单日混杂 24 个人声纹碎片；对抗题多出的冒充者占用一个杂散名额
        n_junk = 21 if adversarial else 22

        roles = VOICEPRINT_NOISE_ROLES[:]
        rng.shuffle(roles)
        for i in range(n_junk):
            speakers.append(dict(
                speaker_frag_id=self._stamp("V", qnum, "J", i + 1),
                cluster_label=f"SPK_{i + 1:02d}",
                role=roles[i % len(roles)],
                fragment_count=rng.randint(1, 3),
                total_duration_s=round(rng.uniform(1.5, 26.0), 1),
                cosine_to_user=round(rng.uniform(0.11, 0.54), 3),
                first_seen=_iso(ts + timedelta(minutes=rng.randint(0, 700))),
                is_transient=True,
                ttl_policy="expire_24h",
            ))

        sig: List[Dict[str, Any]] = []
        uid = self._stamp("V", qnum, "K", 1)
        cid = self._stamp("V", qnum, "K", 2)
        kin = _pick(rng, persona["close"])
        kin_short = kin.split("(")[0]

        speakers.append(dict(
            speaker_frag_id=uid, cluster_label="SPK_USER", role="佩戴者本人",
            fragment_count=rng.randint(14, 46), total_duration_s=round(rng.uniform(120.0, 1400.0), 1),
            cosine_to_user=1.0, is_transient=False, ttl_policy="permanent_anchor",
            first_seen=_iso(ts),
        ))
        speakers.append(dict(
            speaker_frag_id=cid, cluster_label="SPK_KEY_01", role=f"核心亲友-{kin_short}",
            fragment_count=rng.randint(5, 22), total_duration_s=round(rng.uniform(40.0, 600.0), 1),
            cosine_to_user=round(rng.uniform(0.61, 0.79), 3), is_transient=False,
            ttl_policy="keep_90d", first_seen=_iso(ts + timedelta(minutes=rng.randint(10, 600))),
            voiceprint_match_to=kin_short,
        ))

        bind_core = (f"当日声纹聚类从24个说话人碎片中将佩戴者{persona['name']}本人"
                     f"稳定锚定为长期声纹，核心亲友{kin_short}一并绑定，"
                     f"其余21至22个为推销员、客服与路人等一次性杂散人声")
        facts.append(self._fact(qnum, 1, "dim:social", "VOICE_BINDING_USER",
                               [persona["name"], "24人", kin_short], bind_core, uid,
                               ["佩戴者本人声纹", "本人声纹确认", "锁定佩戴者"], confidence=0.92))

        if adversarial:
            imp = self._stamp("V", qnum, "K", 3)
            speakers.append(dict(
                speaker_frag_id=imp, cluster_label="SPK_IMPOSTOR", role=f"冒充{kin_short}的陌生来电",
                fragment_count=rng.randint(3, 9), total_duration_s=round(rng.uniform(12.0, 90.0), 1),
                cosine_to_user=round(rng.uniform(0.18, 0.35), 3),
                cosine_to_claimed_identity=round(rng.uniform(0.47, 0.62), 3),
                is_transient=True, ttl_policy="flag_suspicious",
                first_seen=_iso(ts + timedelta(minutes=rng.randint(20, 600))),
                note="自称身份与声纹簇不匹配：与真实亲友声纹中心距离过远，且使用合成音残留特征",
            ))
            core = (f"声纹聚类发现一个自称{kin_short}的说话人，其声纹与真实{kin_short}"
                    f"相似度仅{_r(rng, (0.47, 0.62), 2)}，远低于同簇阈值，判定为冒充亲友的可疑来电")
            facts.append(self._fact(qnum, 2, "dim:safety", "VOICE_IMPERSONATION_FRAUD",
                                    [persona["name"], kin_short, "冒充"], core, imp,
                                    ["冒充家人", "冒充亲友", "诈骗电话", "声纹不符"], confidence=0.91))
        elif critical:
            core = (f"声纹聚类将佩戴者{persona['name']}本人与核心亲友{kin_short}"
                    f"从当日24个说话人碎片中稳定绑定为长期锚点，其余均为一次性杂散人声")
            facts.append(self._fact(qnum, 2, "dim:social", "VOICE_BINDING_KEY_CONTACT",
                                    [persona["name"], kin_short, "24人"], core, cid,
                                    ["关键联系人声纹", "亲友声纹绑定", "熟人声纹"], confidence=0.93))

        cluster = dict(
            cluster_date=ts.strftime("%Y-%m-%d"),
            total_detected_speakers=len(speakers),
            lsh_bands=32, lsh_rows=8, cosine_merge_threshold=0.86,
            embedding_dim=192, speakers=speakers,
        )
        junk_ids = [s["speaker_frag_id"] for s in speakers if s["is_transient"]
                    and s["cluster_label"] not in ("SPK_IMPOSTOR",)]
        return dict(voiceprint_cluster=cluster, facts=facts, junk_ids=junk_ids)

    # ------------------------------------------------ APP 消息流（1,500 题）
    def build_app(self, qnum: int, persona: Dict[str, Any], ts: datetime,
                  critical: bool, adversarial: bool) -> Dict[str, Any]:
        rng = self.rng
        msgs: List[Dict[str, Any]] = []
        n_junk = rng.randint(21, 28) if (critical or adversarial) else rng.randint(16, 21)
        cats = list(APP_JUNK.keys())
        for i in range(n_junk):
            cat = _pick(rng, cats)
            spec = _pick(rng, APP_JUNK[cat])
            msgs.append(dict(
                msg_id=self._stamp("A", qnum, "J", i + 1),
                app_name=_f(rng, persona, spec["app"]),
                sender=_f(rng, persona, spec["sender"]),
                content=_f(rng, persona, spec["content"]),
                timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 40000))),
                category=cat,
                notification_priority="low",
            ))

        if adversarial:
            facts, sig = self._app_adversarial(qnum, persona, ts)
        elif critical:
            facts, sig = self._app_critical(qnum, persona, ts)
        else:
            facts, sig = self._app_ambient(qnum, persona, ts)

        junk_ids = [m["msg_id"] for m in msgs]
        return dict(app_message_stream=msgs + sig, facts=facts, junk_ids=junk_ids)

    def _app_ambient(self, qnum, persona, ts) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        kinds = [
            dict(cat="delivery", app="菜鸟驿站", sender="菜鸟驿站",
                 tpl="您的{num}个包裹已到{place}驿站，取件码{vcode}，请及时领取。",
                 intent="DELIVERY_EVENT", dim="dim:logistics",
                 core="佩戴者有{num}件快递到达驿站，取件码{vcode}，待领取",
                 ents=["{num}件"]),
            dict(cat="family", app="微信", sender="{kin}",
                 tpl="{line}", intent="FAMILY_DAILY", dim="dim:family",
                 core="佩戴者与{kin}通过微信进行日常寒暄，内容为家常问候，无重大信息",
                 ents=["{kin}"]),
            dict(cat="meal", app="美团外卖", sender="美团外卖",
                 tpl="您的订单（{item}等{num}件）已送达，骑手{surname}师傅，祝您用餐愉快。",
                 intent="MEAL_EVENT", dim="dim:daily",
                 core="佩戴者点外卖{item}等{num}件并已送达",
                 ents=["{item}"]),
            dict(cat="work", app="企业微信", sender="{col}",
                 tpl="{line}", intent="WORK_COORDINATION", dim="dim:career",
                 core="佩戴者与{col}就工作事项进行日常协调沟通",
                 ents=["{col}"]),
            dict(cat="medical", app="健康云", sender="{hospital}医院",
                 tpl="您已成功预约{date} {dept}门诊，请提前{minutes}分钟到院取号。",
                 intent="MEDICAL_APPOINTMENT", dim="dim:health",
                 core="佩戴者已预约{date}到{dept}门诊就诊",
                 ents=["{date}", "{dept}"]),
            dict(cat="med", app="用药助手", sender="用药助手",
                 tpl="【服药提醒】该吃{med}了，请按处方剂量服用。",
                 intent="MEDICATION_REMINDER", dim="dim:health",
                 core="佩戴者收到{med}服药提醒，属长期用药管理",
                 ents=["{med}"]),
            dict(cat="bill", app="支付宝", sender="支付宝",
                 tpl="您的花呗账单已出，本期应还{yuan}0元，还款日为{date}，请提前安排。",
                 intent="BILL_REPAYMENT", dim="dim:finance",
                 core="佩戴者本期花呗账单应还{yuan}0元，还款日为{date}",
                 ents=["{yuan}0元", "{date}"]),
            dict(cat="smallpay", app="微信", sender="{kin}",
                 tpl="【微信转账】{kin}向你转账{yuan}元，备注：饭钱AA。",
                 intent="SMALL_TRANSFER", dim="dim:finance",
                 core="佩戴者收到{kin}微信转账{yuan}元，备注为聚餐AA分摊",
                 ents=["{kin}", "{yuan}元"]),
            dict(cat="utility", app="网上国网", sender="网上国网",
                 tpl="您{date}的电费{yuan}元已到期，请及时缴纳以免影响用电。",
                 intent="UTILITY_PAYMENT", dim="dim:finance",
                 core="佩戴者{date}的电费{yuan}元到期需缴纳",
                 ents=["{yuan}元", "{date}"]),
        ]
        spec = _pick(rng, kinds)
        slots = _slots(rng, persona)
        slots.update(dict(
            kin=_pick(rng, persona["close"]).split("(")[0],
            col=_pick(rng, persona["colleagues"]).split("(")[0],
            hospital=_pick(rng, HOSPITALS),
            med=_pick(rng, ["美托洛尔", "阿司匹林", "二甲双胍", "氨氯地平", "华法林", "阿托伐他汀"]),
            line=_pick(rng, [
                "晚上回来吃饭吗？我买了你爱吃的{item}。",
                "天冷了记得加衣服，别老熬夜。",
                "周末回来一趟吧，家里包了饺子。",
                "报告发你了，麻烦看一下第三页。",
                "今天进度还行，明天上午对一下。",
            ]),
        ))
        # line 本身也含槽位，需先解析一次再回填，确保消息正文与 core_content 数字一致
        slots["line"] = _fmt(slots, slots["line"])
        fid = self._stamp("A", qnum, "K", 1)
        core = _fmt(slots, spec["core"])
        sig = [dict(
            msg_id=fid, app_name=_fmt(slots, spec["app"]),
            sender=_fmt(slots, spec["sender"]),
            content=_fmt(slots, spec["tpl"]),
            timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 40000))),
            category=spec["cat"], notification_priority="normal",
        )]
        ents = [persona["name"]] + [_fmt(slots, e) for e in spec["ents"]]
        return [self._fact(qnum, 1, spec["dim"], spec["intent"], ents, core, fid,
                           _keywords(rng, spec["intent"], []))], sig

    def _app_critical(self, qnum, persona, ts, ) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        fid = self._stamp("A", qnum, "K", 1)
        if roll < 0.08:
            # 律师函 / 仲裁通知：现实中比传票更常见的前置法律动作
            firm = _pick(rng, ["恒信", "京师", "德恒", "中伦", "天同"]) + "律师事务所"
            plaintiff = _pick(rng, [c.split("(")[0] for c in persona["close"] + persona["colleagues"]])
            ctype = _pick(rng, CASE_TYPES)
            amount = _pick(rng, [80000, 120000, 260000, 480000, 760000, 1800000])
            content = (f"【{firm}】{persona['name']}：本所受{plaintiff}委托，就你方{ctype}纠纷"
                       f"（涉及金额{amount:,}元）正式发出律师函，请于收到之日起15日内履行义务，"
                       f"否则将依法提起诉讼或申请仲裁。")
            core = (f"{firm}受{plaintiff}委托向佩戴者{persona['name']}发出律师函，"
                    f"就{ctype}纠纷主张{amount:,}元，限期15日履行否则起诉或仲裁")
            ents = [persona["name"], plaintiff, firm, ctype, f"{amount:,}元"]
            dim, intent, must = "dim:legal", "LAWYER_LETTER", ["律师函", "催告函", "限期履行", "委托律师"]
            sig = [dict(msg_id=fid, app_name="短信", sender=firm, content=content,
                        timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 30000))),
                        category="critical_notice", notification_priority="high")]
            return [self._fact(qnum, 1, dim, intent, ents, core, fid, must, confidence=0.96)], sig
        if roll < 0.34:
            bank = _pick(rng, BANKS)
            amount = _pick(rng, [100000, 150000, 200000, 380000, 500000, 800000, 1200000])
            tail = "".join(rng.choice("0123456789") for _ in range(4))
            payer = _pick(rng, [c.split("(")[0] for c in persona["close"] + persona["colleagues"]])
            content = (f"【{bank}】您尾号{tail}的账户{ts.month}月{ts.day}日"
                       f"{(ts.hour + 8) % 24:02d}时入账人民币{amount:,}元，"
                       f"余额{amount + rng.randint(20000, 900000):,}元。对方户名：{payer}。")
            core = (f"佩戴者{persona['name']}的{bank}账户（尾号{tail}）收到{payer}"
                    f"转账{amount:,}元，形成大额到账回执")
            ents = [persona["name"], bank, payer, f"{amount:,}元"]
            dim, intent, must = "dim:finance", "BANK_LARGE_TRANSFER", ["大额到账", "入账", "转账到账"]
        elif roll < 0.60:
            court = _pick(rng, COURTS)
            plaintiff = _pick(rng, [c.split("(")[0] for c in persona["close"] + persona["colleagues"]])
            ctype = _pick(rng, CASE_TYPES)
            case_no = f"（2026）{court[:2]}{rng.randint(100, 999)}民初{rng.randint(1000, 9999)}号"
            d = ts + timedelta(days=rng.randint(12, 45))
            content = (f"【{court}法院】{persona['name']}：本院受理{plaintiff}诉你{ctype}纠纷一案，"
                       f"案号{case_no}，定于{d.month}月{d.day}日9时30分在第{rng.randint(1, 12)}法庭开庭，"
                       f"请准时到庭，逾期将依法缺席审理。")
            core = (f"佩戴者{persona['name']}被{plaintiff}以{ctype}纠纷诉至{court}法院，"
                    f"案号{case_no}，定于{d.month}月{d.day}日开庭应诉")
            ents = [persona["name"], plaintiff, ctype, case_no, f"{d.month}月{d.day}日"]
            dim, intent, must = "dim:legal", "COURT_SUMMONS", ["法院传票", "开庭通知", "被起诉"]
        elif roll < 0.86:
            lab = _pick(rng, LAB_ITEMS)
            hosp = _pick(rng, HOSPITALS)
            crit = lab["crit_high"] if lab["crit_high"] is not None else lab["crit_low"]
            val = round(crit * rng.uniform(1.02, 1.35), 2) if crit else 0.0
            ref = f"{lab['low']}~{lab['high']}{lab['unit']}"
            content = (f"【{hosp}医院】{persona['name']}您好，您的{lab['item']}检验结果为"
                       f"{val}{lab['unit']}（参考区间{ref}），已达危急值标准，"
                       f"请立即联系{rng.choice(['心血管内科', '血液科', '肾内科', '急诊科'])}就诊。")
            core = (f"佩戴者{persona['name']}在{hosp}医院的{lab['item']}检验结果为{val}{lab['unit']}"
                    f"（参考{ref}），已达危急值，医院要求立即就诊")
            ents = [persona["name"], lab["item"], f"{val}{lab['unit']}", ref]
            dim, intent, must = "dim:health", "LAB_CRITICAL_VALUE", ["检验危急值", "危急值", "化验异常"]
        else:
            partner = _pick(rng, persona["close"] + persona["colleagues"])
            short = partner.split("(")[0]
            d = ts + timedelta(days=rng.randint(2, 20))
            deal = _pick(rng, ["战略合作框架协议", "年度采购合同", "股权转让协议", "施工总承包合同", "品牌代理协议"])
            content = (f"【日程】{d.month}月{d.day}日10:00 于{persona['city']}"
                       f"{_pick(rng, ['国际会议中心', '希尔顿酒店', '公司大会议室'])}"
                       f"与{short}签署{deal}，请携带公章与营业执照原件，联系人{short}。")
            core = (f"佩戴者{persona['name']}定于{d.month}月{d.day}日10时与{short}"
                    f"签署{deal}，需携带公章与营业执照原件")
            ents = [persona["name"], short, deal, f"{d.month}月{d.day}日10时"]
            dim, intent, must = "dim:career", "SIGNING_SCHEDULE", ["签约日程", "签约安排", "合同签署"]

        sig = [dict(msg_id=fid, app_name=_pick(rng, ["短信", "手机银行", "12368", "医院公众号", "日程"]),
                    sender=content.split("】")[0].lstrip("【"), content=content,
                    timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 30000))),
                    category="critical_notice", notification_priority="high")]
        return [self._fact(qnum, 1, dim, intent, ents, core, fid, must, confidence=0.97)], sig

    def _app_adversarial(self, qnum, persona, ts) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        fid = self._stamp("A", qnum, "K", 1)
        if rng.random() < 0.55:
            bank = _pick(rng, BANKS)
            tail = "".join(rng.choice("0123456789") for _ in range(4))
            amount = _pick(rng, [800000, 1000000, 2000000, 5000000])
            url = _f(rng, persona, "{url}")
            content = (f"【{bank}】尊敬的用户，您的账户异常入账{amount:,}元已被临时冻结，"
                       f"请点击 {url} 完成身份核验解冻，逾期将永久锁定。")
            sig = [dict(msg_id=fid, app_name="短信", sender="10690", content=content,
                        timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 30000))),
                        category="phishing", notification_priority="high",
                        note="伪造银行名义：使用短链而非官方域名、制造恐慌与紧迫感、"
                             "诱导点击钓鱼链接，应判定为诈骗短信而非真实到账回执")]
            core = (f"佩戴者{persona['name']}收到伪装成{bank}的短信，谎称账户异常入账"
                    f"{amount:,}元被冻结并诱导点击短链，判定为钓鱼诈骗而非真实银行回执")
            return [self._fact(qnum, 1, "dim:safety", "FRAUD_ATTEMPT",
                               [persona["name"], bank, f"{amount:,}元", "钓鱼链接"], core, fid,
                               ["诈骗短信", "钓鱼", "疑似诈骗", "伪造银行"], confidence=0.96)], sig
        who = _pick(rng, [c.split("(")[0] for c in persona["close"]])
        a1 = rng.randint(10, 50)
        a2 = a1 + rng.randint(5, 40)
        content = (f"【相册】同一日拍摄的两张借条照片：一张写「今借到{who}{a1}万元」，"
                   f"另一张写「今借到{who}{a2}万元」，日期相同、笔迹一致、金额冲突。")
        sig = [dict(msg_id=fid, app_name="微信", sender=who, content=content,
                    timestamp=_iso(ts + timedelta(seconds=rng.randint(0, 30000))),
                    category="conflicting_evidence", notification_priority="high",
                    note="同日同笔迹出现金额互斥的两份借据，构成对冲证据，"
                         "不可任选其一直接采信，应标记为待核实的债务争议")]
        core = (f"佩戴者{persona['name']}与{who}之间出现同日同笔迹但金额互斥的两张借条"
                f"（{a1}万元与{a2}万元），构成对冲证据，债务金额存在争议待核实")
        return [self._fact(qnum, 1, "dim:finance", "DEBT_BORROWING",
                           [persona["name"], who, f"{a1}万元", f"{a2}万元"], core, fid,
                           ["借款", "借条", "欠款", "金额冲突"], confidence=0.85)], sig

    # ---------------------------------------------- 用户原话流（500 题）
    def build_dialogue(self, qnum: int, persona: Dict[str, Any], ts: datetime,
                       critical: bool, adversarial: bool) -> Dict[str, Any]:
        rng = self.rng
        utts: List[Dict[str, Any]] = []
        n_junk = rng.randint(21, 27) if (critical or adversarial) else rng.randint(18, 24)
        pool = DIALOGUE_JUNK[:]
        rng.shuffle(pool)
        for i in range(n_junk):
            spec = pool[i % len(pool)]
            utts.append(dict(
                utterance_id=self._stamp("D", qnum, "J", i + 1),
                raw_speech=_f(rng, persona, spec["raw"]),
                context_scene=spec["ctx"],
                emotional_tone=spec["tone"],
                junk_tag=spec["tag"],
                duration_s=round(rng.uniform(1.2, 7.5), 1),
                snr_db=round(rng.uniform(6.0, 22.0), 1),
                is_self_talk=True,
                blood_alcohol_hint=("elevated" if spec["ctx"] == "酒局" else "normal"),
                physiological_context=dict(
                    hr_bpm=rng.randint(70, 118) if spec["ctx"] == "酒局" else rng.randint(*persona["resting_hr"], ) + 8,
                    spo2_percent=round(rng.uniform(95.0, 99.0), 1),
                ),
            ))

        if adversarial or critical:
            facts, sig = self._dlg_critical(qnum, persona, ts)
        else:
            facts, sig = self._dlg_ambient(qnum, persona, utts)

        junk_ids = [u["utterance_id"] for u in utts]
        return dict(user_dialogue_stream=utts + sig, facts=facts, junk_ids=junk_ids)

    def _dlg_ambient(self, qnum, persona, utts) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        fid = self._stamp("D", qnum, "K", 1)
        hr = rng.randint(86, 126)
        if roll < 0.4:
            company = _pick(rng, COMPANIES)
            line = f"等我把{company}收购了，第一件事就是给你们每人发一百万！"
            sig = [dict(utterance_id=fid, raw_speech=line, context_scene="酒局",
                        emotional_tone="亢奋夸大", duration_s=round(rng.uniform(3.0, 9.0), 1),
                        snr_db=round(rng.uniform(4.0, 16.0), 1), is_self_talk=False,
                        blood_alcohol_hint="elevated",
                        speech_rate_syl_per_s=round(rng.uniform(5.2, 7.4), 2),
                        physiological_context=dict(hr_bpm=hr, spo2_percent=round(rng.uniform(95.0, 98.5), 1)),
                        note="血液酒精线索升高、语速加快、内容明显超出本人财务能力，判定为酒后吹牛")]
            core = (f"佩戴者{persona['name']}在酒局中自称将收购{company}并向众人发钱，"
                    f"伴随血液酒精线索升高与语速加快，判定为酒后夸大言辞，不构成真实商业计划")
            return [self._fact(qnum, 1, "dim:social", "DRUNK_BRAGGING",
                               [persona["name"], company, "酒后"], core, fid,
                               ["酒后吹牛", "吹牛", "醉话", "夸大其词"], confidence=0.94)], sig
        line = _pick(rng, [
            "烦死了，真想把这一切都扔了不管了。",
            "我真的不想活了，天天这样熬着有什么意思。（语气平稳，随后正常点外卖）",
            "累死了，我要是猝死在工位上算不算工伤。",
        ])
        sig = [dict(utterance_id=fid, raw_speech=line, context_scene="独处",
                    emotional_tone="疲惫宣泄", duration_s=round(rng.uniform(2.0, 7.0), 1),
                    snr_db=round(rng.uniform(8.0, 20.0), 1), is_self_talk=True,
                    blood_alcohol_hint="normal",
                    speech_rate_syl_per_s=round(rng.uniform(3.2, 4.8), 2),
                    physiological_context=dict(
                        hr_bpm=rng.randint(persona["resting_hr"][0], persona["resting_hr"][1] + 12),
                        spo2_percent=round(rng.uniform(96.0, 99.0), 1), hrv_rmssd_ms=rng.randint(28, 62)),
                    post_utterance_behavior="随后正常完成点外卖、洗澡、入睡等日常动作",
                    note="高频口头禅式宣泄，无计划性表述、无自伤准备行为，"
                         "生理指标平稳且事后行为正常，判定为情绪发泄而非真实自伤意图")]
        core = (f"佩戴者{persona['name']}独处时说出「不想活了」类口头禅式宣泄，"
                f"但无计划性表述、生理指标平稳且随后行为正常，判定为情绪发泄而非真实自伤意图")
        return [self._fact(qnum, 1, "dim:emotion", "VERBAL_VENT",
                           [persona["name"], "口头禅"], core, fid,
                           ["口头禅", "情绪发泄", "气话", "非真实意图"], confidence=0.93)], sig

    def _dlg_critical(self, qnum, persona, ts) -> Tuple[List[Dict], List[Dict]]:
        rng = self.rng
        roll = rng.random()
        fid = self._stamp("D", qnum, "K", 1)
        if roll < 0.30:
            hosp = _pick(rng, HOSPITALS)
            line = _pick(rng, [
                "胸口这块闷得慌，喘不上气，我想去医院看看。",
                "我这头晕了两天了，明天得去查个血压和血糖。",
                "胃疼得实在不行，明天早上挂个号吧。",
            ])
            sig = [dict(utterance_id=fid, raw_speech=line, context_scene="家中",
                        emotional_tone="焦虑求助", duration_s=round(rng.uniform(3.0, 10.0), 1),
                        snr_db=round(rng.uniform(10.0, 22.0), 1), is_self_talk=True,
                        blood_alcohol_hint="normal",
                        physiological_context=dict(
                            hr_bpm=rng.randint(84, 108), spo2_percent=round(rng.uniform(94.0, 97.5), 1)),
                        note="清醒状态下的主动求医表述，含具体症状与就诊意愿，非玩笑")]
            core = (f"佩戴者{persona['name']}清醒状态下主动表述身体不适并明确提出就医意愿，"
                    f"计划前往医院检查，属真实就医诉求")
            return [self._fact(qnum, 1, "dim:health", "REAL_MEDICAL_INTENT",
                               [persona["name"], "就医", hosp], core, fid,
                               ["就医诉求", "想去医院", "看病", "挂号"], confidence=0.95)], sig
        if roll < 0.55:
            boss = _pick(rng, [c.split("(")[0] for c in persona["colleagues"]])
            line = _pick(rng, [
                "我想清楚了，下周一就把辞职信交给" + boss + "。",
                "这活儿我是真干不下去了，明天就跟" + boss + "说我不干了。",
                "辞职这事我考虑三个月了，这次是真的，不是气话。",
            ])
            sig = [dict(utterance_id=fid, raw_speech=line, context_scene="独处",
                        emotional_tone="冷静决断", duration_s=round(rng.uniform(4.0, 12.0), 1),
                        snr_db=round(rng.uniform(10.0, 22.0), 1), is_self_talk=True,
                        blood_alcohol_hint="normal",
                        speech_rate_syl_per_s=round(rng.uniform(3.0, 4.4), 2),
                        physiological_context=dict(
                            hr_bpm=rng.randint(persona["resting_hr"][0], persona["resting_hr"][1] + 6),
                            hrv_rmssd_ms=rng.randint(30, 60)),
                        note="语速平稳、心率正常、含明确时间节点与对象，非酒后亦非情绪爆发，"
                             "判定为经过思考的真实辞职决定")]
            core = (f"佩戴者{persona['name']}在清醒平静状态下明确决定向{boss}提出辞职，"
                    f"含具体时间节点，判定为真实辞职决定而非气话")
            return [self._fact(qnum, 1, "dim:career", "REAL_RESIGNATION",
                               [persona["name"], boss, "辞职"], core, fid,
                               ["辞职", "离职", "递交辞呈", "不干了"], confidence=0.95)], sig
        # 隐性心血管危象：嘴硬说"没事"，但体征与副语言线索全面报警
        hr = rng.randint(116, 142)
        line = _pick(rng, [
            "没事没事，就是有点闷，歇会儿就好了，别大惊小怪的。",
            "不用叫救护车，我缓一下就行，真没事。",
            "老毛病了，忍忍就过去了，别告诉家里人。",
        ])
        sig = [
            dict(utterance_id=fid, raw_speech=line, context_scene="客厅静坐",
                 emotional_tone="强撑否认", duration_s=round(rng.uniform(3.0, 8.0), 1),
                 snr_db=round(rng.uniform(8.0, 18.0), 1), is_self_talk=False,
                 blood_alcohol_hint="normal",
                 speech_rate_syl_per_s=round(rng.uniform(2.0, 3.1), 2),
                 voice_tremor=round(rng.uniform(0.42, 0.78), 2),
                 breath_sound="可闻及喘息与吸气费力",
                 note="言语否认不适，但语速显著减慢、声颤明显、可闻喘息，"
                      "语言内容与生理证据严重矛盾"),
        ]
        s2 = self._stamp("D", qnum, "K", 2)
        sig.append(dict(
            utterance_id=s2, raw_speech="（连续粗重喘息声，伴随衣物被汗浸的窸窣声）",
            context_scene="客厅静坐", emotional_tone="生理性窘迫",
            duration_s=round(rng.uniform(12.0, 45.0), 1), snr_db=round(rng.uniform(6.0, 15.0), 1),
            is_self_talk=False, blood_alcohol_hint="normal",
            note="非语言声学线索显示明显呼吸窘迫"))
        core = (f"佩戴者{persona['name']}口头反复否认不适称「没事」，但同期心率升至{hr}bpm、"
                f"血氧降至{round(rng.uniform(89.0, 93.5), 1)}%、语速减慢伴声颤与喘息、皮肤大汗，"
                f"生理证据与言语否认严重矛盾，判定为疑似急性心血管事件的隐性危象")
        return [self._fact(qnum, 1, "dim:health", "HIDDEN_CARDIAC_CRISIS",
                           [persona["name"], f"{hr}bpm", "大汗", "喘憋", "嘴硬否认"], core, fid,
                           ["嘴硬否认", "隐瞒症状", "疑似心梗", "喘不上气", "胸口憋闷"],
                           confidence=0.9)], sig

    # ------------------------------------------------------------- 组装
    def build(self, quotas: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
        quotas = quotas or dict(sensor=3000, mic=3000, voiceprint=2000, app=1500, dialogue=500)
        rng = self.rng
        plan: List[str] = []
        for stream, n in quotas.items():
            plan.extend([stream] * n)
        rng.shuffle(plan)

        questions: List[Dict[str, Any]] = []
        for idx, stream in enumerate(plan, start=1):
            qnum = idx
            persona = PERSONAS[(qnum * 7) % len(PERSONAS)]
            day = (qnum * 13) % 91
            hour = rng.choice([0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
                               15, 16, 17, 18, 19, 20, 21, 22, 23])
            ts = self._base + timedelta(days=day, hours=hour, minutes=rng.randint(0, 59),
                                        seconds=rng.randint(0, 59))
            critical = (qnum % 20 == 0)          # 5% 致命/核心事实题
            adversarial = (qnum % 13 == 0) and not critical  # ≈7.2% 对抗陷阱题

            builders = dict(sensor=self.build_sensor, mic=self.build_mic,
                            voiceprint=self.build_voiceprint, app=self.build_app,
                            dialogue=self.build_dialogue)
            part = builders[stream](qnum, persona, ts, critical, adversarial)

            if adversarial:
                difficulty = "ADVERSARIAL"
            elif critical:
                difficulty = "HARD"
            else:
                difficulty = rng.choice(["EASY", "MEDIUM", "MEDIUM"])

            q = dict(
                question_id=f"Q_{self.generator_agent.replace('-', '')}_{qnum:05d}",
                generator_agent=self.generator_agent,
                timestamp_utc=_iso(ts),
                difficulty=difficulty,
                sensor_stream=part.get("sensor_stream", {}),
                mic_stream=part.get("mic_stream", []),
                voiceprint_cluster=part.get("voiceprint_cluster", {}),
                app_message_stream=part.get("app_message_stream", []),
                user_dialogue_stream=part.get("user_dialogue_stream", []),
                ground_truth_facts=part["facts"],
                ground_truth_junk_ids=part["junk_ids"],
            )

            # 跨模态佐证：用户原话类的隐性危象题同时给出传感器流，形成多模态对撞
            if stream == "dialogue" and any(
                    f["semantic_intent"] == "HIDDEN_CARDIAC_CRISIS" for f in part["facts"]):
                q["sensor_stream"] = dict(
                    sampling_hz=50,
                    device_id=f"aios-band-{persona['pid'].lower()}-0731",
                    window_start_utc=q["timestamp_utc"],
                    window_end_utc=_iso(ts + timedelta(minutes=12)),
                    fragments=[dict(
                        fragment_id=self._stamp("S", qnum, "K", 9), kind="ppg_acute_stress",
                        label="acute_cardiac_stress", label_zh="急性心血管应激体征",
                        window_offset_s=0.0, duration_s=720,
                        hr_mean=124, hr_max=148, spo2_percent=91.2,
                        skin_conductance_uS=round(rng.uniform(6.0, 14.0), 1),
                        note="静息状态下心率与皮电同步飙升、血氧下降，与「没事」的口头否认形成硬冲突",
                    )],
                )
            questions.append(q)
        return questions


def split_ground_truth(questions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从考题中抽出标答底稿（供裁判席使用）。"""
    return [
        dict(
            question_id=q["question_id"],
            generator_agent=q["generator_agent"],
            timestamp_utc=q["timestamp_utc"],
            difficulty=q["difficulty"],
            ground_truth_facts=q["ground_truth_facts"],
            ground_truth_junk_ids=q["ground_truth_junk_ids"],
        )
        for q in questions
    ]


def strip_ground_truth(questions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """生成"盲考卷"：物理剥离标答，供跨 Git 交叉做题方使用，杜绝偷看答案。"""
    out = []
    for q in questions:
        blind = {k: v for k, v in q.items()
                 if k not in ("ground_truth_facts", "ground_truth_junk_ids")}
        out.append(blind)
    return out
