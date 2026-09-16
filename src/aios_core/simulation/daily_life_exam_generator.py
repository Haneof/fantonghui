"""AIOS 3.0 全天生活流与多维总结 —— 高熵出卷引擎。

老大指令：**必须出 1 万个人的一天**。

每道试卷 = 一个真人完整 24 小时（07:00~23:30）：
  - ``cleaned_daily_stream``：已清洗的生活切片（MIC/APP/SENSOR），
    **关键大事**与**海量琐碎日常**混编，按时间戳严格升序；
  - ``directional_ground_truth``：六维方向性标答，每维给出
    ``core_content`` + ``acceptable_directions`` + ``red_line_deviations``。

跨维度冲突编织（老大硬要求）：
  事业弧 × 人际弧 × 健康弧 三者**因果咬合** —— 例如
  "白天被领导当众批评" + "晚上女友提分手" 会自动触发
  "21:06 心率骤升至125bpm" 的生理应激事件，形成真正的跨维度转折。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from aios_core.simulation.daily_life_exam_pools import (
    CAREER_ARCS,
    CITIES,
    EMOTION_PROFILES,
    FINANCE_ARCS,
    GIVEN_NAMES_F,
    GIVEN_NAMES_M,
    HEALTH_ARCS,
    MARITAL,
    OCCUPATIONS,
    SOCIAL_ARCS,
    SURNAMES,
    TRIVIA_COMMUTE,
    TRIVIA_EVENING,
    TRIVIA_MORNING,
    TRIVIA_WORK,
)
from aios_core.simulation.daily_life_exam_protocol import (
    DIMENSION_ORDER,
    DifficultyLevel,
    Dimension,
)

#: 琐事投放量（按难度）—— 难度越高琐事越密，主线越难挑出来。
TRIVIA_BUDGET: Dict[str, Tuple[int, int]] = {
    DifficultyLevel.EASY: (10, 14),
    DifficultyLevel.MEDIUM: (16, 22),
    DifficultyLevel.HARD: (24, 30),
    DifficultyLevel.ADVERSARIAL: (28, 36),
}

#: 对抗级干扰（用于**负面**真相）：字面粉饰太平，与真相相反。
#: 解题方必须看穿"嘴上说没事"的隐瞒，以传感器与硬事件为准。
DECOYS_MASK_NEGATIVE: Tuple[Tuple[str, str, str], ...] = (
    ("MIC", "{self}", "没事没事，我挺好的，真的，一点事都没有。"),
    ("APP", "朋友圈", "【{name}】今天也是元气满满的一天！[图片]"),
    ("MIC", "{peer}", "看你今天心情不错啊，是不是有什么好事？"),
    ("MIC", "{self}", "哈哈哈没有的事，你别听他们瞎说。"),
    ("APP", "{friend}", "周末爬山去不去？看你最近挺闲的。"),
    ("MIC", "{self}", "挺好的挺好的，一切都顺利，你们不用惦记我。"),
    ("APP", "家人群", "【{name}】我这边都挺好的，你们放心，别操心我。"),
)

#: 对抗级干扰（用于**正面/中性**真相）：字面唱衰或自嘲，与真相相反。
DECOYS_MASK_POSITIVE: Tuple[Tuple[str, str, str], ...] = (
    ("MIC", "{self}", "唉，我这辈子估计就这样了，混吃等死吧。"),
    ("MIC", "{peer}", "你看着怎么心事重重的，是不是出什么事了？"),
    ("APP", "朋友圈", "【{name}】人间不值得。[图片]"),
    ("MIC", "{self}", "别提了，烦得很，一言难尽。"),
    ("APP", "{friend}", "看你朋友圈发得挺丧啊，没事吧？要不要出来喝一杯。"),
)

#: 通用干扰：无信息量的噪声性强情绪表达（真假难辨，纯干扰）。
DECOYS_NEUTRAL_NOISE: Tuple[Tuple[str, str, str], ...] = (
    ("APP", "短视频", "您观看的剧情片已播完，下一集自动播放中。"),
    ("MIC", "电视", "……本轮比赛的结果令人大跌眼镜，比分被彻底逆转！"),
    ("MIC", "{self}", "这剧演得也太气人了，编剧出来挨打。"),
    ("APP", "游戏", "您的队伍连败3局，排位分下降28点。"),
)

_AMOUNTS = (800, 1200, 1500, 2000, 2600, 3000, 3500, 4200, 5000, 6800, 8000, 12000)
_SMALL = (6, 8, 9, 12, 15, 18, 22, 26, 28, 32, 35, 38, 45, 52, 68)


def _hhmm_to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _min_to_hhmm(minutes: int) -> str:
    minutes = max(0, min(23 * 60 + 59, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class DailyLifeExamGenerator:
    """全天生活流试卷生成器（确定性：同 seed 同产出）。"""

    def __init__(self, generator_agent: str, seed: int = 20260916) -> None:
        self.generator_agent = generator_agent
        self.seed = seed

    # -- 人物 -------------------------------------------------------------

    def _build_persona(self, rng: random.Random, idx: int) -> Dict[str, Any]:
        gender = rng.choice(("M", "F"))
        given = rng.choice(GIVEN_NAMES_M if gender == "M" else GIVEN_NAMES_F)
        surname = rng.choice(SURNAMES)
        name = surname + given
        occupation, scene, boss_title, peer_title = rng.choice(OCCUPATIONS)
        age = rng.randint(23, 58)
        city = rng.choice(CITIES)
        marital = rng.choice(MARITAL)

        partner_label = {
            "单身独居": "暧昧对象",
            "恋爱异地": "女友" if gender == "M" else "男友",
            "新婚一年": "妻子" if gender == "M" else "丈夫",
            "已婚育有一子": "妻子" if gender == "M" else "丈夫",
            "已婚育有一女": "妻子" if gender == "M" else "丈夫",
            "离异独自带娃": "前任",
            "与父母同住": "对象",
            "已婚双职工": "爱人",
        }[marital]

        return {
            "persona_id": f"P{idx:05d}",
            "name": name,
            "gender": "男" if gender == "M" else "女",
            "age": age,
            "city": city,
            "occupation": occupation,
            "marital_status": marital,
            "work_scene": scene,
            "boss_title": boss_title,
            "peer_title": peer_title,
            "partner_label": partner_label,
        }

    def _fmt_ctx(self, persona: Dict[str, Any], rng: random.Random) -> Dict[str, str]:
        return {
            "self": persona["name"],
            "name": persona["name"],
            "boss": persona["boss_title"],
            "peer": persona["peer_title"],
            "scene": persona["work_scene"],
            "city": persona["city"],
            "partner": persona["partner_label"],
            "friend": rng.choice(("老陈", "阿强", "小林", "老周", "大刘", "阿伟")),
            "family": rng.choice(("妈", "爸", "老妈", "母亲")),
            "tail": f"{rng.randint(1000, 9999)}",
            "amount": str(rng.choice(_AMOUNTS)),
            "months": str(rng.randint(60, 300)),
            "small1": str(rng.choice(_SMALL)),
            "small2": str(rng.choice(_SMALL)),
            "small3": str(rng.choice(_SMALL)),
            "hr": str(rng.randint(118, 142)),
            "rest": str(rng.randint(58, 78)),
            "sleep": str(round(rng.uniform(4.2, 7.8), 1)),
            "steps": str(rng.randint(2400, 16800)),
            "tmax": str(rng.randint(8, 36)),
            "code": f"{rng.randint(1, 9)}-{rng.randint(10, 29)}-{rng.randint(1000, 9999)}",
            "days": str(rng.randint(3, 240)),
        }

    # -- 弧选择（保证跨维度因果咬合） -------------------------------------

    def _select_arcs(
        self, rng: random.Random, difficulty: str, persona: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        career = rng.choice(CAREER_ARCS)

        # 人设自洽：已婚的人不会"提分手"，无子女的人不会被班主任叫家长。
        marital = persona["marital_status"]
        social_pool = [
            arc
            for arc in SOCIAL_ARCS
            if arc.get("requires_marital") is None or marital in arc["requires_marital"]
        ]
        social = rng.choice(social_pool)

        # 跨维度冲突编织：晚间情感重创 -> 必须触发生理应激
        evening_shock = social["valence"] <= -2
        if evening_shock:
            health_pool = [h for h in HEALTH_ARCS if h.get("requires_negative_evening")]
        else:
            health_pool = [h for h in HEALTH_ARCS if not h.get("requires_negative_evening")]
        health = rng.choice(health_pool)

        finance = rng.choice(FINANCE_ARCS)
        return career, social, health, finance

    def _select_emotion(
        self, career: Dict[str, Any], social: Dict[str, Any]
    ) -> Dict[str, Any]:
        cv, sv = career["valence"], social["valence"]
        by_key = {e["key"]: e for e in EMOTION_PROFILES}
        if sv <= -2 and cv < 0:
            return by_key["CRISIS_COLLAPSE"]
        if sv <= -2:
            return by_key["CRISIS_COLLAPSE"]
        if cv < 0 and sv < 0:
            return by_key["PRESSURE_ANXIOUS"]
        if cv < 0 and sv > 0:
            return by_key["RELIEF_AFTER_STRESS"]
        if cv > 0 and sv < 0:
            return by_key["MIXED_TURBULENT"]
        if cv > 0 and sv > 0:
            return by_key["UPLIFTED_JOY"]
        if cv < 0 or sv < 0:
            return by_key["PRESSURE_ANXIOUS"]
        if cv > 0 or sv > 0:
            return by_key["UPLIFTED_JOY"]
        return by_key["STEADY_CALM"]

    # -- 生活流编织 -------------------------------------------------------

    def _emit_arc_events(
        self, arc: Dict[str, Any], ctx: Dict[str, str], tag: str
    ) -> List[Dict[str, Any]]:
        out = []
        for hhmm, modality, source, text in arc["events"]:
            out.append(
                {
                    "_min": _hhmm_to_min(hhmm),
                    "modality": modality,
                    "source": source.format(**ctx),
                    "content": text.format(**ctx),
                    "is_key_event": True,
                    "_tag": tag,
                }
            )
        return out

    def _emit_trivia(
        self,
        rng: random.Random,
        ctx: Dict[str, str],
        difficulty: str,
        day_valence: int,
    ) -> List[Dict[str, Any]]:
        """投放琐碎日常。

        采用**无放回**抽样：同一条琐事在一天内不会逐字重复出现，
        否则生活流会出现"同事三次说同一句话"的穿帮。
        """
        lo, hi = TRIVIA_BUDGET[difficulty]
        budget = rng.randint(lo, hi)
        blocks = (
            (TRIVIA_MORNING, 7 * 60 + 5, 9 * 60),
            (TRIVIA_COMMUTE, 8 * 60, 9 * 60 + 40),
            (TRIVIA_WORK, 9 * 60 + 30, 18 * 60 + 30),
            (TRIVIA_EVENING, 18 * 60, 23 * 60 + 30),
        )
        weights = (0.2, 0.15, 0.4, 0.25)

        # 每个时段的候选池独立洗牌，逐条弹出 -> 天然无重复。
        shuffled: List[List[Tuple[str, str, str]]] = []
        for pool, _lo, _hi in blocks:
            items = list(pool)
            rng.shuffle(items)
            shuffled.append(items)

        out: List[Dict[str, Any]] = []
        for _ in range(budget):
            # 只在仍有余量的时段里抽，避免耗尽后重复。
            live = [i for i in range(len(blocks)) if shuffled[i]]
            if not live:
                break
            bi = rng.choices(live, weights=[weights[i] for i in live], k=1)[0]
            modality, source, text = shuffled[bi].pop()
            _pool, lo_m, hi_m = blocks[bi]
            out.append(
                {
                    "_min": rng.randint(lo_m, hi_m),
                    "modality": modality,
                    "source": source.format(**ctx),
                    "content": text.format(**ctx),
                    "is_key_event": False,
                    "_tag": "trivia",
                }
            )

        if difficulty == DifficultyLevel.ADVERSARIAL:
            # 干扰方向必须与当日真相**相反**：好日子唱衰，坏日子粉饰。
            if day_valence < 0:
                decoy_pool = list(DECOYS_MASK_NEGATIVE)
            elif day_valence > 0:
                decoy_pool = list(DECOYS_MASK_POSITIVE)
            else:
                decoy_pool = []
            # 中性噪声对所有日子都适用；用 dict 去重，避免同一条被抽两次。
            decoy_pool = list(dict.fromkeys(decoy_pool + list(DECOYS_NEUTRAL_NOISE)))
            rng.shuffle(decoy_pool)
            for _ in range(min(rng.randint(2, 4), len(decoy_pool))):
                modality, source, text = decoy_pool.pop()
                out.append(
                    {
                        "_min": rng.randint(9 * 60, 22 * 60),
                        "modality": modality,
                        "source": source.format(**ctx),
                        "content": text.format(**ctx),
                        "is_key_event": False,
                        "_tag": "decoy",
                    }
                )
        return out

    # -- 单题生成 ---------------------------------------------------------

    def build_question(self, idx: int) -> Dict[str, Any]:
        rng = random.Random(f"{self.generator_agent}:{self.seed}:{idx}")
        persona = self._build_persona(rng, idx)
        ctx = self._fmt_ctx(persona, rng)
        difficulty = rng.choices(
            (
                DifficultyLevel.EASY,
                DifficultyLevel.MEDIUM,
                DifficultyLevel.HARD,
                DifficultyLevel.ADVERSARIAL,
            ),
            weights=(0.18, 0.32, 0.30, 0.20),
            k=1,
        )[0]

        career, social, health, finance = self._select_arcs(rng, difficulty, persona)
        emotion = self._select_emotion(career, social)
        day_valence = career["valence"] + social["valence"]

        events: List[Dict[str, Any]] = []
        events += self._emit_arc_events(career, ctx, "career")
        events += self._emit_arc_events(social, ctx, "social")
        events += self._emit_arc_events(health, ctx, "health")
        events += self._emit_arc_events(finance, ctx, "finance")
        events += self._emit_trivia(rng, ctx, difficulty, day_valence)

        # 固定的起止锚点，保证覆盖 07:00~23:30
        events.append(
            {
                "_min": 7 * 60,
                "modality": "SENSOR",
                "source": "手环体征",
                "content": f"晨起唤醒，昨夜睡眠{ctx['sleep']}小时，静息心率{ctx['rest']}bpm",
                "is_key_event": False,
                "_tag": "anchor",
            }
        )
        events.append(
            {
                "_min": 23 * 60 + 30,
                "modality": "SENSOR",
                "source": "手环体征",
                "content": f"进入夜间休息，全天步数{ctx['steps']}步",
                "is_key_event": False,
                "_tag": "anchor",
            }
        )

        events.sort(key=lambda e: (e["_min"], 0 if e["_tag"] == "anchor" else 1))
        stream: List[Dict[str, Any]] = []
        for n, ev in enumerate(events, start=1):
            stream.append(
                {
                    "slice_id": f"s{n:03d}",
                    "timestamp": _min_to_hhmm(ev["_min"]),
                    "modality": ev["modality"],
                    "source": ev["source"],
                    "content": ev["content"],
                    "is_key_event": ev["is_key_event"],
                }
            )

        gt = self._build_ground_truth(persona, ctx, career, social, health, finance, emotion)

        return {
            "question_id": f"Q_{self.generator_agent}_{idx:05d}",
            "generator_agent": self.generator_agent,
            "exam_type": "DAILY_LIFE_MULTIDIM_SUMMARY",
            "difficulty": str(difficulty),
            "persona": persona,
            "arc_signature": {
                "career": career["key"],
                "social": social["key"],
                "health": health["key"],
                "finance": finance["key"],
                "emotion": emotion["key"],
            },
            "cleaned_daily_stream": stream,
            "directional_ground_truth": gt,
        }

    def _build_ground_truth(
        self,
        persona: Dict[str, Any],
        ctx: Dict[str, str],
        career: Dict[str, Any],
        social: Dict[str, Any],
        health: Dict[str, Any],
        finance: Dict[str, Any],
        emotion: Dict[str, Any],
    ) -> Dict[str, Any]:
        career_core = career["core"].format(**ctx)
        social_core = social["core"].format(**ctx)
        health_core = health["core"].format(**ctx)
        finance_core = finance["core"].format(**ctx)

        # 全局主线 = 事业 + 人际 + 情绪 的因果缝合
        global_core = (
            f"{persona['name']}（{persona['age']}岁{persona['occupation']}）的这一天："
            f"{career_core}；{social_core}；{health_core}。"
            f"全天主线为{emotion['core']}"
        )
        global_directions = sorted(
            set(career["directions"][:6]) | set(social["directions"][:6]) | set(emotion["directions"][:5])
        )
        global_red_lines = sorted(
            set(career["red_lines"][:4]) | set(social["red_lines"][:4]) | set(emotion["red_lines"][:4])
        )

        def pack(sem: str, core: str, arc: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "semantic_intent": sem,
                "core_content": core,
                "acceptable_directions": list(arc["directions"]),
                "red_line_deviations": list(arc["red_lines"]),
            }

        return {
            Dimension.GLOBAL: {
                "semantic_intent": f"{career['key']}__{social['key']}",
                "core_content": global_core,
                "acceptable_directions": global_directions,
                "red_line_deviations": global_red_lines,
            },
            Dimension.HEALTH: pack(health["key"], health_core, health),
            Dimension.SOCIAL: pack(social["key"], social_core, social),
            Dimension.EMOTION: pack(emotion["key"], emotion["core"], emotion),
            Dimension.FINANCE: pack(finance["key"], finance_core, finance),
            Dimension.CAREER: pack(career["key"], career_core, career),
        }

    # -- 批量 -------------------------------------------------------------

    def generate(self, count: int) -> Iterable[Dict[str, Any]]:
        for i in range(1, count + 1):
            yield self.build_question(i)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 全天生活流多维总结出卷器")
    parser.add_argument("--count", type=int, default=10000, help="出题数量（默认 1 万个人的一天）")
    parser.add_argument("--generator-agent", default="agent-01a0aa2e", help="出题战队标识")
    parser.add_argument("--seed", type=int, default=20260916)
    parser.add_argument("--out", type=Path, required=True, help="试卷 JSONL 落盘路径")
    parser.add_argument("--manifest", type=Path, default=None, help="题库清单 JSON")
    parser.add_argument("--pretty-sample", type=Path, default=None, help="导出首题样例 JSON")
    args = parser.parse_args(argv)

    gen = DailyLifeExamGenerator(args.generator_agent, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "difficulty": {},
        "career": {},
        "social": {},
        "health": {},
        "finance": {},
        "emotion": {},
    }
    slice_total = 0
    key_total = 0
    first: Dict[str, Any] | None = None
    seen_ids: set[str] = set()
    digest = hashlib.sha256()

    with args.out.open("w", encoding="utf-8") as fh:
        for q in gen.generate(args.count):
            if first is None:
                first = q
            seen_ids.add(q["question_id"])
            sig = q["arc_signature"]
            stats["difficulty"][q["difficulty"]] = stats["difficulty"].get(q["difficulty"], 0) + 1
            for k in ("career", "social", "health", "finance", "emotion"):
                stats[k][sig[k]] = stats[k].get(sig[k], 0) + 1
            slice_total += len(q["cleaned_daily_stream"])
            key_total += sum(1 for s in q["cleaned_daily_stream"] if s["is_key_event"])
            line = json.dumps(q, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            fh.write(line + "\n")

    manifest = {
        "generator_agent": args.generator_agent,
        "exam_type": "DAILY_LIFE_MULTIDIM_SUMMARY",
        "total_questions": args.count,
        "unique_question_ids": len(seen_ids),
        "seed": args.seed,
        "sha256": digest.hexdigest(),
        "dimensions": list(DIMENSION_ORDER),
        "avg_slices_per_question": round(slice_total / max(args.count, 1), 2),
        "avg_key_events_per_question": round(key_total / max(args.count, 1), 2),
        "total_slices": slice_total,
        "distribution": stats,
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.pretty_sample and first:
        args.pretty_sample.parent.mkdir(parents=True, exist_ok=True)
        args.pretty_sample.write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8")

    json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
