"""样卷 builder：persona×冲突弧×反转×琐事编织为 24 小时生活流 + 六维方向标答。"""
from __future__ import annotations

import copy
import random
from collections import Counter
from typing import Any, Dict, List, Tuple

from .pools import (ARCS, DIM_ORDER, FILLERS, HOSPS, NAMES, NEUTRAL, PERSONAS,
                    PLACES, SCHOOLS, FIRMS, FOODS, GENERATOR, TWISTS)

_QID = "Q_daily01a0aa2c_{:05d}"
_TWIST_PROB = 0.75
_MIN_SLICES, _MAX_SLICES = 15, 25


def _mm(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _hhmm(mm: int) -> str:
    return f"{mm // 60:02d}:{mm % 60:02d}"


def _sample_time(rng: random.Random, span: Tuple[str, str]) -> str:
    lo, hi = _mm(span[0]), _mm(span[1])
    return _hhmm(rng.randint(lo, hi))


def need_ok(need: Dict[str, Any], flags: Dict[str, Any]) -> bool:
    """need 语义：True 要求具备；False / not_ 前缀要求不具备。"""
    for k, v in need.items():
        if k.startswith("not_"):
            if flags.get(k[4:]):
                return False
        elif v is False:
            if flags.get(k):
                return False
        elif flags.get(k) != v:
            return False
    return True


def eligible_arcs(persona: Dict[str, Any]) -> List[Dict[str, Any]]:
    flags = persona["flags"]
    return [a for a in ARCS if need_ok(a.get("need", {}), flags)]


def _make_slots(rng: random.Random, persona: Dict[str, Any]) -> Dict[str, str]:
    names = rng.sample(NAMES, 9)
    (partner, leader, colleague, colleague2, friend, friend2, kid, parent,
     doctor) = names
    if persona["flags"].get("adult_kid"):
        kid = names[0] + "（已成年）"
    female = persona["gender"] == "女"
    mortgage = persona["flags"].get("mortgage")
    amt = rng.choice([3000, 5000, 8000, 12000, 20000, 30000, 50000])
    amt2 = rng.choice([2000, 3000, 5000, 8000, 15000])
    small = rng.choice([35, 60, 120, 200, 380, 600, 800, 1200, 2000])
    return dict(
        me=persona["name"], partner=partner, leader=leader, colleague=colleague,
        colleague2=colleague2, friend=friend, friend2=friend2, kid=kid,
        parent=parent, doctor=doctor, vendor=rng.choice(NAMES),
        amt=str(amt), amt2=str(amt2), small=str(small),
        hosp=rng.choice(HOSPS), school=rng.choice(SCHOOLS),
        firm=rng.choice(FIRMS), food=rng.choice(FOODS), place=rng.choice(PLACES),
        rest=str(rng.randint(58, 74)),
        parent_role="妈妈" if female else "爸爸",
        child_call="闺女啊" if female else "儿啊",
        debt="房贷" if mortgage else "账单",
        bill="房贷本月" if mortgage else "信用卡本月",
        pet_word=persona["flags"].get("pet_word", "猫"),
        pet_star=persona["flags"].get("pet_star", "喵星"),
        sib_call="姐妹" if female else "兄弟",
        role="伴娘" if female else "伴郎")


def _render(text: str, slots: Dict[str, str]) -> str:
    try:
        return text.format(**slots)
    except KeyError as e:  # 缺槽即抛错，绝不产出半成品
        raise ValueError(f"未知槽位 {e}：{text!r}") from e


def _render_beat(rng: random.Random, beat: Dict[str, Any],
                 slots: Dict[str, str]) -> Dict[str, Any]:
    s: Dict[str, Any] = {"time": _sample_time(rng, beat["t"]), "modality": beat["mod"]}
    if beat["mod"] == "mic":
        s["scene"] = _render(beat["scene"], slots)
        s["speaker"] = _render(beat["who"], slots)
    elif beat["mod"] == "app":
        s["source"] = _render(beat["src"], slots)
    else:
        s["metric"] = beat["metric"]
    s["text"] = _render(beat["text"], slots)
    return s


class PaperBuilder:
    """单卷编织器；rng 由调用方注入以保证可复现。"""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def build(self, idx: int, persona: Dict[str, Any],
              arc: Dict[str, Any]) -> Dict[str, Any]:
        rng = self.rng
        flags = persona["flags"]
        slots = _make_slots(rng, persona)
        slices: List[Dict[str, Any]] = []
        for b in arc["beats"]:
            slices.append(_render_beat(rng, b, slots))
        twist = None
        if rng.random() < _TWIST_PROB:
            cands = [t for t in TWISTS if need_ok(t.get("need", {}), flags)]
            if cands:
                twist = rng.choice(cands)
                for b in twist["beats"]:
                    slices.append(_render_beat(rng, b, slots))
        # 琐事：先按 persona 过滤，再模态保底（mic≥3、app≥3、sensor≥2），
        # 最后随机填充至 15~25 切片
        avail = [f for f in FILLERS if need_ok(f.get("need", {}), flags)]
        mods = Counter(s["modality"] for s in slices)
        need = {"mic": max(0, 3 - mods["mic"]), "app": max(0, 3 - mods["app"]),
                "sensor": max(0, 2 - mods["sensor"])}
        rng.shuffle(avail)
        picked: List[Dict[str, Any]] = []
        for f in avail:
            if need.get(f["mod"], 0) > 0:
                picked.append(f)
                need[f["mod"]] -= 1
        assert all(v == 0 for v in need.values()), f"模态保底无可用填充：{need}"
        rest = [f for f in avail if f not in picked]
        for f in picked:
            slices.append(_render_beat(rng, f, slots))
        target = rng.randint(_MIN_SLICES, _MAX_SLICES)
        for f in rest:
            if len(slices) >= target:
                break
            slices.append(_render_beat(rng, f, slots))
        slices.sort(key=lambda s: s["time"])
        for i, s in enumerate(slices, 1):
            s["slice_id"] = f"S{i:02d}"
        gt = self._build_gt(arc, twist, slots)
        return {
            "question_id": _QID.format(idx),
            "generator_agent": GENERATOR,
            "date": f"2026-09-{rng.randint(1, 28):02d}",
            "persona": {k: persona[k] for k in
                        ("name", "age", "gender", "job", "city", "family", "finance", "health")},
            "arc_id": arc["id"],
            "twist_id": twist["id"] if twist else None,
            "cleaned_daily_stream": slices,
            "directional_ground_truth": gt,
        }

    def _build_gt(self, arc: Dict[str, Any], twist: Dict[str, Any] | None,
                  slots: Dict[str, str]) -> Dict[str, Any]:
        gt: Dict[str, Any] = {}
        arc_gt = arc["gt"]
        g = copy.deepcopy(arc_gt["global"])
        g["core"] = _render(g["core"], slots)
        for a in g["anchors"]:
            a["key"] = _render(a["key"], slots)
            a["accept"] = [_render(x, slots) for x in a["accept"]]
        if twist:
            g["core"] += f"（另有小插曲：{_render(twist['anchor'], slots)}）"
            g["anchors"].append(dict(key=_render(twist["anchor"], slots),
                                     accept=[_render(x, slots) for x in twist["accept"]]))
        g["neutral"] = False
        gt["global"] = g
        for dim in DIM_ORDER[1:]:
            if dim in arc_gt:
                d = copy.deepcopy(arc_gt[dim])
                d["core"] = _render(d["core"], slots)
                for a in d["anchors"]:
                    a["key"] = _render(a["key"], slots)
                    a["accept"] = [_render(x, slots) for x in a["accept"]]
                d["neutral"] = False
            else:
                d = copy.deepcopy(NEUTRAL[dim])
                d["neutral"] = True
            gt[dim] = d
        return gt


# ---------------------------------------------------------------- 盲卷拆分
GT_KEY = "directional_ground_truth"


def split_ground_truth(q: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """拆分为盲卷与独立标答卷。"""
    blind = {k: v for k, v in q.items() if k != GT_KEY}
    gt = {"question_id": q["question_id"], "generator_agent": q.get("generator_agent"),
          GT_KEY: q[GT_KEY]}
    return blind, gt


def strip_ground_truth(q: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in q.items() if k != GT_KEY}
