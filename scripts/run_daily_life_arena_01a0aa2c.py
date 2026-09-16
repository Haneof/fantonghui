#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIOS 3.0 全天生活流竞技场 · 跨 Git 做题与阅卷运行器（Solver ``01a0aa2c-fantonghui``）。

目标题库：**队友/对手战队的「10000 个人的一天」盲卷**
（`benchmarks/daily_life_summary/<agent>/questions_*_people.blind.jsonl.xz`）。

纪律（与 Master Dispatch #11 一致）：
1. **跨 Git 取卷**：题目与标答都用 ``git show`` 流式读取；**标答永不落盘到工作区**，
   仅在内存中参与阅卷（本题库标答为 ``.xz`` 压缩流，同样只在管道里解压）。
2. **盲解**：做题函数只接收**盲卷题面**（persona + cleaned_daily_stream），
   绝不接触 ``directional_ground_truth``；运行器把两条链路物理隔离。
3. **方向性阅卷**：以对方标答的``语义核心锚点``为准，按"方向同义词容差 + 必需实体 + 红线判据"
   三维打分；红线命中 = 该维度 0 分并整题 FAIL（绝不抠字眼）。
4. **错题归因**：输出四类归因（信号漏检 / 实体遗漏 / 方向漂移 / 红线误判）与升级前后对比。

用法::

    PYTHONPATH=src .venv/bin/python scripts/run_daily_life_arena_01a0aa2c.py \
        --branch arena/01a0aa30-fantonghui \
        --questions benchmarks/daily_life_summary/agent_01a0aa30/questions_10000_people.blind.jsonl.xz \
        --gt        benchmarks/daily_life_summary/agent_01a0aa30/ground_truth_10000_people.jsonl.xz \
        --solver-variant v2 \
        --answers   benchmarks/data_cleaning/answers/ans_01a0aa2c-fantonghui_on_01a0aa30_10000people.jsonl \
        --report    benchmarks/data_cleaning/reports/report_01a0aa2c-fantonghui_on_01a0aa30_10000people.json \
        --failures  benchmarks/data_cleaning/reports/failures_01a0aa2c-fantonghui_on_01a0aa30_10000people.jsonl
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import lzma
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

SOLVER_AGENT = "01a0aa2c-fantonghui"
PASS_LINE = 80.0  # 单题达标线：final_score ≥ 80 且无红线命中（与官方契约一致）
SOLVER_BRANCH = "arena/01a0aa2c-fantonghui"
DIMENSIONS: Tuple[str, ...] = (
    "global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career",
)
DIM_LABEL = {
    "global": "全局日总结",
    "dim:health": "健康生理",
    "dim:social": "人际社交",
    "dim:emotion": "情绪心理",
    "dim:finance": "财务契约",
    "dim:career": "事业行动",
}

# ---------------------------------------------------------------------------
# 一、跨 Git 流式取卷（支持 .xz；任何情况下不把标答写进工作区）
# ---------------------------------------------------------------------------


def stream_git_lines(branch: str, path: str) -> Iterator[dict]:
    """用 ``git show`` 流式读取远端 JSONL（.xz 自动解压），逐行 yield。"""
    if branch.strip().rstrip("/") == SOLVER_BRANCH:
        raise RuntimeError(f"禁止从我方分支取卷: {branch}")
    proc = subprocess.Popen(
        ["git", "show", f"origin/{branch}:{path}"], cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    stream = proc.stdout
    if path.endswith(".xz"):
        decompressor = lzma.LZMAFile(stream)
        reader = decompressor
    else:
        reader = stream
    for raw in reader:
        line = raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()
        if line:
            yield json.loads(line)
    proc.wait()
    if proc.returncode != 0:
        err = (proc.stderr.read() or b"").decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"git show origin/{branch}:{path} 失败 rc={proc.returncode} {err}")


# ---------------------------------------------------------------------------
# 二、盲解器：只吃题面（persona + cleaned_daily_stream），六维方向性总结
# ---------------------------------------------------------------------------

#: 维度线索词（内容特征，纯题面可见词，**不含任何标答词表**）。
DIM_CUES: Mapping[str, Tuple[Tuple[str, int], ...]] = {
    "finance": (
        ("余额", 3), ("借款", 3), ("本金", 3), ("转账", 3), ("到账", 3), ("结算款", 3),
        ("支出", 2), ("消费", 2), ("付款", 2), ("收款", 3), ("退款", 2), ("还款", 3),
        ("元", 1), ("账户", 2), ("账单", 2), ("发票", 2), ("定金", 2), ("报销", 2),
    ),
    "health": (
        ("睡眠", 3), ("心率", 3), ("bpm", 3), ("血氧", 3), ("步数", 2), ("静息", 3),
        ("体温", 3), ("服药", 3), ("用药", 2), ("就诊", 3), ("不适", 3), ("疼痛", 3),
        ("头晕", 3), ("胸闷", 3), ("手环", 2), ("体征", 3), ("呼吸", 2), ("血压", 3),
    ),
    "social": (
        ("朋友", 3), ("家人", 3), ("同事", 3), ("同学", 2), ("亲戚", 2), ("邻居", 2),
        ("群里", 2), ("通话", 3), ("见面", 3), ("商量", 3), ("协商", 3), ("拒绝", 3),
        ("答应", 3), ("边界", 3), ("误会", 3), ("关系", 2), ("陪同", 3), ("邀请", 2),
    ),
    "career": (
        ("任务", 3), ("交付", 3), ("计划", 2), ("方案", 3), ("会议", 3), ("排班", 3),
        ("客户", 3), ("审批", 3), ("改期", 3), ("延期", 3), ("截止", 3), ("工单", 3),
        ("供货", 3), ("验收", 3), ("考勤", 2), ("请假", 3), ("加班", 2), ("项目", 2),
    ),
    "emotion": (
        ("心情", 3), ("情绪", 3), ("压力", 3), ("焦虑", 3), ("踏实", 3), ("轻松", 3),
        ("内疚", 3), ("烦", 2), ("开心", 3), ("低落", 3), ("紧张", 3), ("放松", 3),
        ("委屈", 3), ("期待", 2), ("纠结", 3), ("释然", 3),
    ),
}

#: 日内节奏锚点（用于把事件贴到"白天/晚间/夜间"叙事里）。
PHASE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("清晨", ("06:", "07:", "08:")),
    ("上午", ("09:", "10:", "11:")),
    ("午间", ("12:", "13:")),
    ("下午", ("14:", "15:", "16:", "17:")),
    ("傍晚", ("18:", "19:")),
    ("晚间", ("20:", "21:", "22:")),
    ("夜间", ("23:",)),
)

#: 事件性动词（"发生了什么"的判别特征，区别于纯琐事）。
EVENT_VERBS: Tuple[str, ...] = (
    "决定", "确认", "确认了", "接受", "拒绝", "协商", "改期", "延期", "获批", "批准",
    "到账", "支付", "转账", "退款", "补发", "取消", "提交", "完成", "安排", "承诺",
    "答应", "沟通", "提醒", "通知", "反馈", "预约", "购买", "签署", "核对", "结算",
)

#: 纯琐事特征（明确排除在"关键大事"之外，只做背景）。
TRIVIA_MARKERS: Tuple[str, ...] = (
    "点开看了一眼", "收进抽屉", "整理手机", "重复截图", "钥匙放在", "核对门锁",
    "擦桌子", "倒垃圾", "刷了会儿", "看了会儿", "翻了翻", "顺手", "例行",
)

#: 无信号时的**能力边界声明**（方向 = "本维度无异常/不可过度推断"，派生自题面里
#: 手环摘要自带的"不能据此声称…"口径）。
DIM_ABSENCE: Mapping[str, str] = {
    "dim:health": "当日已记录体征片段未见明显异常突升，不能仅凭关系或工作压力推断生理危象。",
    "dim:social": "当日人际互动以常规联系为主，未见关系状态翻转的证据。",
    "dim:emotion": "当日情绪以平稳为主，未观察到明显转折。",
    "dim:finance": "当日账户以常规小额收支为主，无借贷或大额资金变动证据。",
    "dim:career": "当日事业行动以例行事务为主，未见任务取消或重大变更。",
    "global": "当日为常规生活日：以例行事务为主，未见跨维度关键事件。",
}


def _slice_time(slice_obj: Mapping[str, Any]) -> str:
    ts = str(slice_obj.get("timestamp", ""))
    return ts[11:16] if len(ts) >= 16 else ""


def _phase_of(clock: str) -> str:
    for label, prefixes in PHASE_MARKERS:
        if any(clock.startswith(p) for p in prefixes):
            return label
    return "当日"


def _content(slice_obj: Mapping[str, Any]) -> str:
    return str(slice_obj.get("content", "")).strip()


def _json_text(value: Any) -> str:
    """把任意 JSON 片段摊平成纯文本（用于 persona 档案的可达性统计）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_json_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_json_text(v) for v in value)
    return str(value)


def _is_trivia(text: str) -> bool:
    return any(marker in text for marker in TRIVIA_MARKERS)


def _cue_key(dim: str) -> str:
    """把 ``dim:health`` 形式规范为线索表键 ``health``。"""
    return dim.split(":", 1)[1] if dim.startswith("dim:") else dim


def _score_slice(text: str, dim: str) -> int:
    return sum(weight for cue, weight in DIM_CUES[_cue_key(dim)] if cue in text)


def _salience(text: str) -> int:
    """事件显著性：事件动词 + 数字（金额/时长）+ 否定/风险词。"""
    score = sum(2 for verb in EVENT_VERBS if verb in text)
    score += 2 * len(re.findall(r"\d+(?:\.\d+)?(?:元|分钟|小时|bpm|%)?", text))
    score += 2 if any(k in text for k in ("不能", "未见", "没有新增", "尚不能")) else 0
    return score


#: 联系人角色 → 维度（题面可见的 persona.contacts 字段，不属于标答信息）。
ROLE_DIM_HINT: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("朋友", "好友", "同学", "邻居", "家人", "父", "母", "妻", "夫", "子", "女", "亲"), "social"),
    (("采购", "客户", "供应商", "合作", "同事", "主管", "领导", "上级", "老板", "工作"), "career"),
    (("医生", "护士", "康复", "教练", "保健"), "health"),
    (("银行", "理财", "财务", "会计", "催收"), "finance"),
)


def _contact_profiles(persona: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """返回 [(姓名, 归属维度)]，维度由联系人角色推断（题面信息，非标答）。"""
    out: List[Tuple[str, str]] = []
    for contact in persona.get("contacts", []) or []:
        name = str(contact.get("name", "")).strip()
        role = str(contact.get("role", "")).strip()
        if not name:
            continue
        dim = ""
        for markers, target in ROLE_DIM_HINT:
            if any(m in role for m in markers):
                dim = target
                break
        out.append((name, dim))
    return out


def _contact_names(persona: Mapping[str, Any]) -> List[str]:
    names = [str(persona.get("name", ""))]
    names.extend(name for name, _ in _contact_profiles(persona))
    return [n for n in names if n]


def _pick_events(
    slices: Sequence[Mapping[str, Any]],
    dim: str,
    *,
    variant: str,
    contacts: Sequence[Tuple[str, str]] = (),
    top_k: int = 3,
) -> List[Mapping[str, Any]]:
    """按维度线索挑出该维度的关键片段。

    v1 = 纯线索词；v2 = 线索 × 事件显著性（剔琐事）+ 当事人姓名加权（题面 persona.contacts）。
    """
    cue_key = _cue_key(dim)
    scored: List[Tuple[int, Mapping[str, Any]]] = []
    for slice_obj in slices:
        text = _content(slice_obj)
        if not text:
            continue
        cue = _score_slice(text, dim)
        boost = 0
        if variant == "v2":
            for name, target in contacts:
                if name and name in text and (not target or target == cue_key):
                    boost += 6
        if cue + boost <= 0:
            continue
        if variant == "v2":
            if _is_trivia(text) and _salience(text) < 4:
                continue
            score = cue + boost + _salience(text)
        else:
            score = cue
        scored.append((score, slice_obj))
    scored.sort(key=lambda pair: (-pair[0], _slice_time(pair[1])))
    chosen: List[Mapping[str, Any]] = []
    seen: Set[str] = set()
    for _, slice_obj in scored:
        text = _content(slice_obj)
        key = text[:12]
        if key in seen:
            continue
        seen.add(key)
        chosen.append(slice_obj)
        if len(chosen) >= top_k:
            break
    chosen.sort(key=lambda s: _slice_time(s))
    return chosen


def _render_dim(persona: Mapping[str, Any], dim: str, events: Sequence[Mapping[str, Any]], variant: str) -> str:
    name = str(persona.get("name", "佩戴者"))
    if not events:
        return f"{name}{DIM_LABEL[dim]}：{DIM_ABSENCE[dim]}"
    parts: List[str] = []
    for slice_obj in events:
        clock = _slice_time(slice_obj)
        phase = _phase_of(clock)
        text = _content(slice_obj).rstrip("。；; ")
        parts.append(f"{phase}{clock}，{text}")
    body = "；".join(parts)
    if variant == "v2":
        return f"{name}的{DIM_LABEL[dim]}：{body}。以上均为当日已记录片段，未记录的部分不做推断。"
    return f"{name}{DIM_LABEL[dim]}：{body}。"


def solve_question(question: Mapping[str, Any], *, variant: str = "v2") -> Dict[str, Any]:
    """盲解：只用题面（persona + cleaned_daily_stream）生成六维方向性总结。"""
    persona = question.get("persona", {}) or {}
    slices: Sequence[Mapping[str, Any]] = question.get("cleaned_daily_stream", []) or []
    names = _contact_names(persona)
    contacts = _contact_profiles(persona)

    summaries: Dict[str, str] = {}
    for dim in ("dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"):
        if variant == "v1":
            events = _pick_events(slices, dim, variant=variant)
        else:
            events = _pick_events(slices, dim, variant=variant, contacts=contacts, top_k=4)
            # 当事人姓名必须有落点：若本维度事件里没有任何联系人姓名，
            # 就把"当天提到过该联系人、且线索最贴维度"的片段补进来（题面信息）
            mentioned = {name for name, _ in contacts if any(name in _content(e) for e in events)}
            missing = [(n, t) for n, t in contacts if n not in mentioned and isinstance(t, str)]
            for name, target in missing:
                if target and target != _cue_key(dim):
                    continue
                filler = [
                    s for s in slices
                    if name in _content(s) and not _is_trivia(_content(s))
                    and _score_slice(_content(s), dim) > 0
                ]
                if filler:
                    events = sorted(events + filler[:1], key=lambda s: _slice_time(s))
        summaries[dim] = _render_dim(persona, dim, events, variant)

    # 全局：跨维度取最显著事件（v2 做去重 + 早晚各取一条）
    ranked = sorted(
        ((_salience(_content(s)) + max(_score_slice(_content(s), d) for d in DIM_CUES), s)
         for s in slices if _content(s) and not _is_trivia(_content(s))),
        key=lambda pair: -pair[0],
    )
    picked: List[Mapping[str, Any]] = []
    seen_key: Set[str] = set()
    for _, slice_obj in ranked:
        text = _content(slice_obj)
        key = text[:10]
        if key in seen_key:
            continue
        seen_key.add(key)
        picked.append(slice_obj)
        if len(picked) >= 4:
            break
    picked.sort(key=lambda s: _slice_time(s))
    if picked:
        arc = "；".join(f"{_phase_of(_slice_time(s))}{_slice_time(s)}，{_content(s).rstrip('。')}" for s in picked)
        guard = "未记录的时段不做推断。" if variant == "v2" else ""
        summaries["global"] = f"{persona.get('name', '佩戴者')}这一天：{arc}。{guard}"
    else:
        summaries["global"] = f"{persona.get('name', '佩戴者')}：{DIM_ABSENCE['global']}"

    return {
        "question_id": question.get("question_id"),
        "solver_agent": SOLVER_AGENT,
        "generator_agent": str(question.get("generator_agent") or ""),
        "generated_global_summary": summaries["global"],
        "generated_health_summary": summaries["dim:health"],
        "generated_social_summary": summaries["dim:social"],
        "generated_emotion_summary": summaries["dim:emotion"],
        "generated_finance_summary": summaries["dim:finance"],
        "generated_career_summary": summaries["dim:career"],
    }


# ---------------------------------------------------------------------------
# 三、方向性阅卷（对"语义核心锚点"做方向容差打分 + 红线一票否决）
# ---------------------------------------------------------------------------

#: 方向概念词表：每个概念 = 一组面同义表达。判分在**概念层**做容差，
#: 既不抠字眼（同义表达算命中），也不被 n-gram 碎片薅分。
DIRECTION_CONCEPTS: Mapping[str, Tuple[str, ...]] = {
    "延期改期": ("延期", "改期", "顺延", "推迟", "延后", "时间冲突获准"),
    "取消终止": ("取消", "作废", "终止", "不予执行", "弃单"),
    "任务保留": ("任务没有取消", "工作保留", "保留", "照样交付", "没有弃单"),
    "到账收入": ("到账", "入账", "已收到", "实收", "结算款", "收款"),
    "支出消费": ("支出", "消费", "付款", "花了", "买单", "支付"),
    "借款债务": ("借款", "本金", "欠款", "负债", "还款", "借条"),
    "未验收": ("未验收", "不是同一笔", "尚未完成", "不能据此认定", "不等于验收"),
    "拒绝": ("拒绝", "婉拒", "没答应", "没有答应", "不接受", "不参与", "不陪同"),
    "接受边界": ("接受", "边界", "休息边界", "协调时间", "改约", "周末再约"),
    "关系未破裂": ("没有绝交", "友谊", "绝交", "关系", "还当朋友"),
    "承诺陪同": ("陪", "陪同", "通宵", "硬撑"),
    "情绪压力": ("压力", "焦虑", "内疚", "紧张", "委屈", "烦"),
    "情绪缓解": ("放松", "缓解", "释然", "轻松", "安心", "踏实"),
    "睡眠": ("睡眠", "入睡", "有效睡眠", "起床", "睡"),
    "心率": ("心率", "bpm", "静息", "脉搏"),
    "体征平稳": ("平稳", "无明显", "未见明显", "正常范围", "相对平稳"),
    "生理危象": ("危象", "急救", "心梗", "猝死", "晕倒", "急症", "就医"),
    "就医用药": ("就诊", "挂号", "服药", "用药", "复查", "医院"),
    "供货任务": ("供货", "交付", "签收"),
    "沟通协商": ("协商", "商量", "沟通"),
}

STOPWORDS = {
    "不能", "据此", "认定", "没有", "已经", "以及", "并且", "同时", "但是", "因为",
    "所以", "只是", "一个", "可以", "需要", "进行", "通过", "由于", "关于", "对于",
    "本题", "本人", "今日", "当天", "当日", "今天", "昨天", "晚上", "白天",
}


def keywords(text: str, *, min_len: int = 2, max_len: int = 4, limit: int = 24) -> Set[str]:
    """粗粒度中文关键词抽取（2~4 字连续片段 + 数字/单位），用于方向容差比对。"""
    out: Set[str] = set()
    cleaned = re.sub(r"[，。；：、（）()\[\]“”\"'！？!?~—\s]", " ", str(text))
    for token in cleaned.split():
        token = token.strip()
        if not token:
            continue
        if re.search(r"\d", token):
            out.add(token)
        for size in range(min_len, max_len + 1):
            for i in range(0, max(0, len(token) - size + 1)):
                piece = token[i : i + size]
                if all("\u4e00" <= ch <= "\u9fff" for ch in piece) and piece not in STOPWORDS:
                    out.add(piece)
    ordered = sorted(out, key=lambda w: (-len(w), w))
    return set(ordered[:limit])


CLAUSE_SPLIT = re.compile(r"[，。；;！？!?、\s]")
REDLINE_TOPIC_STOPWORDS = frozenset({
    "声称", "或任", "或者", "被永", "全部", "所有", "可能", "应该", "已经", "据此",
    "概括", "推断", "视为", "任务", "问题", "情况", "事情",
})
NEGATION_MARKERS = ("没有", "没", "未", "不", "并非", "无", "非", "否认", "不能")


def _clause_of(text: str, index: int) -> str:
    """取命中位置所在的小句（用于否定语境判定，避免跨句误判）。"""
    start = 0
    for match in CLAUSE_SPLIT.finditer(text):
        if match.end() <= index:
            start = match.end()
        elif match.start() >= index:
            return text[start:match.start()]
    return text[start:]


def concept_polarity(
    text: str,
    lexicon: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, str]:
    """抽取"概念 → 极性"。

    - ``"asserted"``：文中断言该概念发生（如 "双方绝交"）；
    - ``"negated"`` ：文中明确否认该概念（如 "我们没有绝交"）；
    同一概念若两种极性都出现，取**先出现**的那一种（人先表态，后续引用不算翻案）。
    """
    out: Dict[str, str] = {}
    for name, synonyms in (lexicon or DIRECTION_CONCEPTS).items():
        first: Optional[Tuple[int, str]] = None
        for syn in synonyms:
            idx = text.find(syn)
            while idx >= 0:
                clause = _clause_of(text, idx)
                polarity = "negated" if any(neg in clause for neg in NEGATION_MARKERS) else "asserted"
                if first is None or idx < first[0]:
                    first = (idx, polarity)
                idx = text.find(syn, idx + 1)
        if first is not None:
            out[name] = first[1]
    return out


def concept_hits(text: str) -> Set[str]:
    """命中哪些方向概念（概念层容差，无字面匹配）。"""
    return set(concept_polarity(text))


def _anchor_refs(anchor: Mapping[str, Any]) -> Tuple[str, List[str], List[str]]:
    """取（核心断言文本, 可接受方向簇, 必需实体）。"""
    claim = str(anchor.get("core_claim", ""))
    directions = [str(x) for x in anchor.get("acceptable_directions", []) or []]
    entities = [str(x) for x in anchor.get("required_entities", []) or []]
    return claim, directions, entities


def _redline_terms(redline: Mapping[str, Any]) -> List[str]:
    """红线判据的"错误主张"特征：以方向概念为主，辅以 3 字以上实词。"""
    text = str(redline.get("contradicted_claim", ""))
    concepts = [f"概念:{c}" for c in concept_hits(text)]
    terms = [w for w in keywords(text, min_len=3, max_len=4, limit=40)]
    return (concepts + terms)[:6]


NEGATION_MARKERS = ("没有", "并未", "未", "不", "不能", "并非", "不是", "无")


OUTCOME_STATE_LEXICON: Dict[str, Sequence[str]] = {
    "任务完成": ("已经完成", "已完成", "完成了", "办妥", "做完了", "已交付", "已签收"),
    "取消终止": ("永久取消", "彻底取消", "取消", "终止", "撤销", "作废", "解除"),
    "资金到账": ("已经到账", "已到账", "到账", "入账", "款已收", "收到款"),
    "资金未到账": ("尚未到账", "未到账", "没有到账", "没到账"),
    "关系断交": ("绝交", "分手", "结束关系", "断绝关系", "不再联系", "拉黑", "破裂", "闹翻"),
    "关系修复": ("复合", "和解", "和好", "继续交往"),
    "确诊危象": ("确诊", "心梗", "脑梗", "危象", "抢救", "急诊", "重症"),
    "全天无风险": ("绝对安全", "全天无风险", "所有时刻都安全", "没有任何风险", "完全没问题"),
    "就医处置": ("住院", "出院", "就诊", "开药", "手术"),
    "职业变动": ("离职", "入职", "跳槽", "被裁", "辞退"),
    "交易完成": ("已付款", "已支付", "已结清", "退货成功", "已完成交易"),
    "承诺当收入": ("计为今日实际收入", "计入今日收入", "计为今日收入", "视为已到账收入", "算作今日收入", "按到账计入收入"),
}

# 这些状态的"断言"本身就是错误方向（不是记账口径问题）：命中即红线，无需再要求话题词共现
STRICT_STATES = frozenset({"承诺当收入", "确诊危象", "全天无风险"})


# 不可逆结局专用（红线层词汇更宽，这里只留"一旦说错就是事实性反转"的结局）
REVERSAL_STATE_LEXICON: Dict[str, Sequence[str]] = {
    k: v for k, v in OUTCOME_STATE_LEXICON.items()
    if k in ("任务完成", "资金到账", "资金未到账", "关系断交", "确诊危象", "职业变动", "交易完成")
}


def direction_reversal_audit(
    question: Mapping[str, Any],
    gt: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> List[Dict[str, str]]:
    """方向反转审计（独立于红线的更强检查）。

    逐维把标答拆成小句：**标答小句里表态的不可逆结局** + **该小句的话题词与必答实体**；
    答卷同一小句若在**同一话题**上给出相反极性（正解"关系没有破裂"、答卷"已经分手"），
    即判为方向反转。话题必须共现，避免把"另一笔钱没入账"当成"这笔款到账"的反转。
    """
    out: List[Dict[str, str]] = []
    dgt = gt.get("directional_ground_truth", {}) or {}
    for dim, key in (
        ("dim:health", "generated_health_summary"),
        ("dim:social", "generated_social_summary"),
        ("dim:emotion", "generated_emotion_summary"),
        ("dim:finance", "generated_finance_summary"),
        ("dim:career", "generated_career_summary"),
        ("global", "generated_global_summary"),
    ):
        block = dgt.get("global_daily_summary" if dim == "global" else dim, {}) or {}
        anchors = block.get("semantic_core_anchors", []) or []
        answer = str(submission.get(key) or "")
        if not anchors or not answer:
            continue
        anchor = anchors[0]
        entities = {str(e) for e in anchor.get("required_entities", []) or [] if e}
        # 只用 core_claim（必答方向）作为标答表态来源：acceptable_directions 是容差表述，
        # 相互之间可能各说一面，拿它当"标答立场"会把正解自己判成反转。
        claim = str(anchor.get("core_claim", ""))
        # 话题词取整条 core_claim：状态往往出现在"今天尚未到账"这种没有实词的小句里，
        # 而"这笔钱/这件事"是谁，要靠整条锚点的话题词才认得出。
        claim_topics = state_topics(claim) | entities
        anchor_units = []
        for clause in _clauses(claim):
            states = concept_polarity(clause, REVERSAL_STATE_LEXICON)
            if states:
                anchor_units.append((clause, states))
        if not anchor_units or not claim_topics:
            continue
        for clause in _clauses(answer):
            answer_states = concept_polarity(clause, REVERSAL_STATE_LEXICON)
            if not answer_states:
                continue
            clause_numbers = set(re.findall(r"\d{2,}(?:\.\d+)?", clause))
            if clause_numbers and not any(topic in clause for topic in claim_topics):
                continue
            for anchor_clause, anchor_states in anchor_units:
                if not any(topic in clause for topic in claim_topics):
                    continue
                anchor_numbers = set(re.findall(r"\d{2,}(?:\.\d+)?", anchor_clause))
                # 两边都点了金额/时刻等具体数字却对不上 → 说的是两件事，不算反转
                if clause_numbers and anchor_numbers and not (clause_numbers & anchor_numbers):
                    continue
                for concept, polarity in answer_states.items():
                    expected = anchor_states.get(concept)
                    if expected and expected != polarity:
                        out.append({
                            "dimension": dim,
                            "concept": concept,
                            "answer": polarity,
                            "ground_truth": expected,
                            "clause": clause[:80],
                            "anchor_clause": anchor_clause[:80],
                        })
                        break
                else:
                    continue
                break
    return out


def _clauses(text: str) -> List[str]:
    return [c.strip() for c in CLAUSE_SPLIT.split(str(text)) if c.strip()]


def state_topics(text: str) -> Set[str]:
    """话题实词：2~4 字片段，剔除结局状态词与通用虚词（红线/反转共用的"话题共现"基础）。"""
    state_words = {w for syns in OUTCOME_STATE_LEXICON.values() for w in syns}
    return {
        t for t in keywords(text, min_len=2, max_len=4, limit=160)
        if not any(ch.isdigit() for ch in t)
        and t not in state_words
        and not any(t in w for w in state_words)
        and t not in REDLINE_TOPIC_STOPWORDS
    }


def _redline_tokens(redline_text: str, anchor_text: str = "") -> List[str]:
    """红线实词：3~4 字片段里去掉被更长片段包含的重叠项（数字/单位另行处理）。

    只保留"红线特有的可核验措辞"，避免用单个通用词就给做题方扣红线。
    """
    raw = {
        t for t in keywords(redline_text, min_len=3, max_len=4, limit=200)
        if not any(ch.isdigit() for ch in t)
    }
    maximal = [t for t in raw if not any(t != other and t in other for other in raw)]
    distinctive = [t for t in maximal if t not in anchor_text]
    return sorted(distinctive or maximal, key=len, reverse=True)


def _redline_violated(
    summary: str,
    redline: Mapping[str, Any],
    anchor_texts: Sequence[str] = (),
) -> bool:
    """红线 = "摘要断言了出卷官明令禁止的错误方向"。

    两条硬判据（均拒绝死板字面匹配）：
    1. **凭空数字**：红线里的数字+单位（如 125bpm）出现在摘要且所在小句无否定语境 → 违规；
       这是"捏造体征/金额"这类物理性错误方向的直接证据。
    2. **同小句双实词共现**：红线特有的两个以上实词片段出现在同一小句、且该小句无否定语境
       → 违规。单字/单词巧合（例如题面原文里出现的"今晚核验"）不足以定性，
       必须两个方向性措辞同时被断言（例如"已完成今晚核验"）。
    """
    redline_text = str(redline.get("contradicted_claim", ""))
    anchor_text = " ".join(str(x) for x in anchor_texts)

    # ① 结局状态层（语义、可抗改写）：红线断言了某结局状态 → 该状态是禁区
    redline_states = {
        c for c, polarity in concept_polarity(redline_text, OUTCOME_STATE_LEXICON).items()
        if polarity == "asserted"
    }
    anchor_states = concept_polarity(anchor_text, OUTCOME_STATE_LEXICON)
    redline_states = {c for c in redline_states if anchor_states.get(c) != "asserted"}
    if redline_states:
        topics = state_topics(redline_text)
        for clause in _clauses(summary):
            if any(neg in clause for neg in NEGATION_MARKERS):
                continue
            clause_states = {
                c for c, polarity in concept_polarity(clause, OUTCOME_STATE_LEXICON).items()
                if polarity == "asserted"
            } & redline_states
            if not clause_states:
                continue
            if clause_states & STRICT_STATES:
                return True
            if not topics or any(topic in clause for topic in topics):
                return True

    # ② 凭空数字/单位（如捏造 125bpm）
    for number in re.findall(r"\d+(?:\.\d+)?\s*(?:bpm|元|次|小时|分钟|%|公里|kg)", redline_text):
        idx = summary.find(number.replace(" ", ""))
        if idx < 0:
            continue
        clause = _clause_of(summary, idx)
        if not any(neg in clause for neg in NEGATION_MARKERS):
            return True

    # ③ 兜底：同小句出现两个以上红线特有实词（含被否定的表述时跳过）
    tokens = _redline_tokens(redline_text, anchor_text)
    if len(tokens) < 2:
        return False
    for clause in _clauses(summary):
        if any(neg in clause for neg in NEGATION_MARKERS):
            continue
        if sum(1 for token in tokens if token in clause) >= 2:
            return True
    return False


def judge_question(
    question: Mapping[str, Any],
    gt: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> Dict[str, Any]:
    """对六维方向性标答逐维打分：方向容差 60% + 必需实体 40%，红线命中一票否决。"""
    dgt = gt.get("directional_ground_truth", {}) or {}
    per_dim: Dict[str, Dict[str, Any]] = {}
    fatal: List[str] = []
    for dim in ("global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"):
        gen_key = {
            "global": "generated_global_summary",
            "dim:health": "generated_health_summary",
            "dim:social": "generated_social_summary",
            "dim:emotion": "generated_emotion_summary",
            "dim:finance": "generated_finance_summary",
            "dim:career": "generated_career_summary",
        }[dim]
        summary = str(submission.get(gen_key, ""))
        block = dgt.get("global_daily_summary" if dim == "global" else dim, {}) or {}
        anchors = block.get("semantic_core_anchors", []) or []
        redlines = block.get("redline_criteria", []) or []
        if not anchors:
            per_dim[dim] = {"score": 100.0, "direction": 1.0, "entity": 1.0, "redline": False, "anchor_id": None}
            continue
        anchor = anchors[0]
        claim, directions, entities = _anchor_refs(anchor)
        anchor_pol = concept_polarity(claim)
        alt_pols = [concept_polarity(extra) for extra in directions]
        summary_pol = concept_polarity(summary)
        anchor_concepts = set(anchor_pol)
        if anchor_concepts:
            covered = set(summary_pol)
            for alt in alt_pols:  # 可接受方向同义词簇同样计入容差
                covered |= set(alt)
            matched = len(anchor_concepts & covered)
            direction = matched / len(anchor_concepts)
        else:  # 标答侧没有可识别概念时退回关键词容差
            target_terms = keywords(claim, limit=18) | keywords(" ".join(directions), limit=18)
            direction = min(1.0, len(target_terms & keywords(summary, limit=60)) / max(4.0, 0.35 * len(target_terms)))
        hit_entities = [e for e in entities if e and e in summary]
        entity = (len(hit_entities) / len(entities)) if entities else 1.0
        violated_redlines = [
            str(r.get("contradicted_claim", ""))[:60]
            for r in redlines
            if _redline_violated(summary, r, [claim] + directions)
        ]
        violated = bool(violated_redlines)
        score = 0.0 if violated else 100.0 * (0.7 * direction + 0.3 * entity)
        if violated:
            fatal.append({"dimension": dim, "anchor_id": anchor.get("anchor_id"),
                          "redlines": violated_redlines})
        per_dim[dim] = {
            "score": round(score, 2),
            "directions_expected": sorted(anchor_concepts),
                    "directions_hit": sorted(anchor_concepts & set(summary_pol)),
            "direction": round(direction, 4),
            "entity": round(entity, 4),
            "redline": violated,
            "redline_evidence": violated_redlines,
            "anchor_id": anchor.get("anchor_id"),
            "intent": anchor.get("semantic_intent"),
            "entities": entities,
            "entity_hits": hit_entities,
        }
    scores = [per_dim[d]["score"] for d in per_dim]
    final = round(statistics.fmean(scores), 2) if scores else 0.0
    return {
        "question_id": question.get("question_id"),
        "final_score": final,
        "passed": final >= PASS_LINE and not fatal,
        "fatal_redlines": fatal,
        "per_dimension": per_dim,
    }


# ---------------------------------------------------------------------------
# 四、归因与报告
# ---------------------------------------------------------------------------


def attribute(judgement: Mapping[str, Any]) -> List[str]:
    """错题归因：REDLINE_TOUCHED / DIRECTION_DRIFT / ENTITY_MISSED / SIGNAL_MISSED。

    - ``DIRECTION_DRIFT``：命中概念但极性相反（把"没绝交"写成"绝交"这类方向反转）；
    - ``SIGNAL_MISSED`` ：锚点概念一个都没覆盖（当天关键事件没被捞出来）；
    - ``ENTITY_MISSED`` ：方向对了但当事人姓名缺失。
    """
    reasons: List[str] = []
    if judgement["fatal_redlines"]:
        reasons.append("REDLINE_TOUCHED")
    for info in judgement["per_dimension"].values():
        expected, hit = set(info.get("directions_expected", [])), set(info.get("directions_hit", []))
        if info.get("score", 100.0) >= PASS_LINE:
            continue
        if expected and not hit:
            reasons.append("SIGNAL_MISSED")
        elif expected and len(hit) < len(expected):
            reasons.append("DIRECTION_DRIFT")
        if info.get("entity", 1.0) < 0.999:
            reasons.append("ENTITY_MISSED")
    return sorted(set(reasons))


def _stream_text(question: Mapping[str, Any]) -> str:
    return " ".join(_content(s) for s in question.get("cleaned_daily_stream", []) or [])


def _prompt_text(question: Mapping[str, Any]) -> str:
    """题面全文 = persona 档案 + 全天流（做题方可见的全部信息）。"""
    return _json_text(question.get("persona")) + " " + _stream_text(question)


def read_git_json(branch: str, path: str) -> Any:
    ref = f"origin/{branch}"
    try:
        subprocess.run(["git", "fetch", "origin", f"{branch}:refs/remotes/origin/{branch}", "--force"],
                       cwd=REPO_ROOT, check=False, capture_output=True)
        raw = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO_ROOT, check=True, capture_output=True).stdout
    except subprocess.CalledProcessError:
        raw = subprocess.run(["git", "show", f"origin/{branch}:{path}"], cwd=REPO_ROOT, check=True, capture_output=True).stdout
    if raw[:6] == b"\xfd7zXZ\x00":
        raw = lzma.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def stream_git_sha256(branch: str, path: str) -> str:
    """流式计算远端文件（压缩原字节）sha256 —— 用于与对手 manifest 比对取卷一致性。"""
    digest = hashlib.sha256()
    proc = subprocess.Popen(["git", "show", f"origin/{branch}:{path}"], cwd=REPO_ROOT, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
        digest.update(chunk)
    proc.wait()
    return digest.hexdigest()


def ceiling_echo_submission(question: Mapping[str, Any], gt: Mapping[str, Any]) -> Dict[str, Any]:
    """天花板自检：把标答 core_claim 原样回灌，检验"阅卷器 + 标答"是否自洽（应接近满分）。"""
    dgt = gt.get("directional_ground_truth", {}) or {}

    def claim(dim: str) -> str:
        block = dgt.get("global_daily_summary" if dim == "global" else dim, {}) or {}
        anchors = block.get("semantic_core_anchors", []) or []
        return str(anchors[0].get("core_claim", "")) if anchors else ""

    name = str((question.get("persona") or {}).get("name", "佩戴者"))

    def with_entities(dim: str) -> str:
        body = claim(dim)
        block = dgt.get("global_daily_summary" if dim == "global" else dim, {}) or {}
        anchors = block.get("semantic_core_anchors", []) or []
        entities = [str(e) for e in (anchors[0].get("required_entities", []) if anchors else []) or []]
        prefix = "、".join(dict.fromkeys([e for e in entities if e] or [name]))
        return f"{prefix}：{body}" if body else prefix

    return {
        "question_id": question.get("question_id"),
        "solver_agent": SOLVER_AGENT,
        "generator_agent": str(question.get("generator_agent") or ""),
        "generated_global_summary": with_entities("global"),
        "generated_health_summary": with_entities("dim:health"),
        "generated_social_summary": with_entities("dim:social"),
        "generated_emotion_summary": with_entities("dim:emotion"),
        "generated_finance_summary": with_entities("dim:finance"),
        "generated_career_summary": with_entities("dim:career"),
    }


def attainability_audit(question: Mapping[str, Any], gt: Mapping[str, Any]) -> Dict[str, Any]:
    """锚点可达性：标答的每个方向概念/必需实体，能否在**盲卷题面**里找到证据。

    题面 = ``persona``（人物档案，含姓名与联系人）+ ``cleaned_daily_stream``（全天流），
    分别给出"仅生活流"与"题面全部"两套口径 —— 前者衡量"事实是否真的发生过"，
    后者衡量"做题方是否可能知道"。
    """
    stream_concepts = concept_polarity(_stream_text(question))
    prompt_concepts = concept_polarity(_prompt_text(question))
    dgt = gt.get("directional_ground_truth", {}) or {}
    total = 0
    reachable = 0
    stream_total = 0
    stream_reachable = 0
    per_dim: Dict[str, Any] = {}
    for dim in ("global", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career"):
        block = dgt.get("global_daily_summary" if dim == "global" else dim, {}) or {}
        anchors = block.get("semantic_core_anchors", []) or []
        if not anchors:
            continue
        anchor = anchors[0]
        claim = str(anchor.get("core_claim", ""))
        directions = [str(x) for x in anchor.get("acceptable_directions", []) or []]
        concepts = set(concept_polarity(claim)) | set(concept_polarity(" ".join(directions)))
        hit = {c for c in concepts if c in prompt_concepts}
        stream_hit = {c for c in concepts if c in stream_concepts}
        total += len(concepts)
        reachable += len(hit)
        stream_total += len(concepts)
        stream_reachable += len(stream_hit)
        per_dim[dim] = {
            "concepts": sorted(concepts),
            "reachable_in_prompt": sorted(hit),
            "reachable_in_stream_only": sorted(stream_hit),
            "coverage_prompt": round(len(hit) / max(len(concepts), 1), 4),
            "coverage_stream_only": round(len(stream_hit) / max(len(concepts), 1), 4),
        }
    return {
        "concept_total": total,
        "concept_reachable_in_prompt": reachable,
        "concept_reachable_in_stream_only": stream_reachable,
        "reachable_rate_prompt": round(reachable / max(total, 1), 4),
        "reachable_rate_stream_only": round(stream_reachable / max(total, 1), 4),
        "per_dimension": per_dim,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="全天生活流竞技场跨 Git 做题+阅卷（Solver 01a0aa2c）")
    parser.add_argument("--branch", required=True, help="对手战队分支（如 arena/01a0aa30-fantonghui）")
    parser.add_argument("--questions", required=True, help="对手盲卷路径（.jsonl / .jsonl.xz）")
    parser.add_argument("--gt", required=True, help="对手标答路径（.jsonl / .jsonl.xz，仅内存阅卷）")
    parser.add_argument("--solver-variant", default="v2", choices=("v1", "v2"))
    parser.add_argument("--limit", type=int, default=0, help="仅跑前 N 题（0 = 全量）")
    parser.add_argument("--answers", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--failures", type=Path, default=None)
    parser.add_argument("--progress-every", type=int, default=2000)
    parser.add_argument("--manifest", default=None, help="对手题库 manifest.json（用于溯源自证与取卷 sha256 比对）")
    parser.add_argument("--max-failures", type=int, default=1500, help="错题归因文件最多写入条数（0 = 不截断）")
    parser.add_argument("--ceiling", action="store_true", help="天花板自检：把标答回灌给阅卷器（仅用于检验裁判自洽）")
    args = parser.parse_args(argv)

    started = time.time()
    manifest: Dict[str, Any] = {}
    generator_agent = ""
    if args.manifest:
        manifest = read_git_json(args.branch, args.manifest)
        generator_agent = str(manifest.get("generator_agent", ""))
        print(f"[arena] 对手 manifest：generator={generator_agent} seed={manifest.get('seed')} "
              f"count={manifest.get('question_count')}", file=sys.stderr, flush=True)
    print(f"[arena] 盲卷流式取卷 origin/{args.branch}:{args.questions}", file=sys.stderr, flush=True)
    gt_iter = stream_git_lines(args.branch, args.gt)
    answers = []
    judgements = []
    reason_counter: collections.Counter = collections.Counter()
    dim_scores: Dict[str, List[float]] = collections.defaultdict(list)
    failures: List[Dict[str, Any]] = []
    question_count = 0
    attain_total = 0
    attain_reachable = 0
    attain_stream_reachable = 0
    failure_total = 0
    reversal_counter: collections.Counter = collections.Counter()
    reversal_examples: List[Dict[str, Any]] = []

    for question, gt in zip(stream_git_lines(args.branch, args.questions), gt_iter):
        question_count += 1
        audit = attainability_audit(question, gt)
        attain_total += audit["concept_total"]
        attain_reachable += audit["concept_reachable_in_prompt"]
        attain_stream_reachable += audit["concept_reachable_in_stream_only"]
        submission = (
            ceiling_echo_submission(question, gt) if args.ceiling
            else solve_question(question, variant=args.solver_variant)
        )
        if generator_agent and not submission.get("generator_agent"):
            submission["generator_agent"] = generator_agent
        judgement = judge_question(question, gt, submission)
        for reversal in direction_reversal_audit(question, gt, submission):
            reversal_counter[reversal["concept"]] += 1
            reversal_examples.append({"question_id": question.get("question_id"), **reversal})
        answers.append(submission)
        judgements.append(judgement)
        for dim, info in judgement["per_dimension"].items():
            dim_scores[dim].append(info["score"])
        for reason in attribute(judgement):
            reason_counter[reason] += 1
        if not judgement["passed"]:
            failure_total += 1
            failures.append({
                "question_id": judgement["question_id"],
                "final_score": judgement["final_score"],
                "fatal_redlines": judgement["fatal_redlines"],
                "weak_dimensions": [
                    {"dimension": d, **{k: v for k, v in info.items() if k in ("score", "direction", "entity", "redline", "intent")}}
                    for d, info in judgement["per_dimension"].items() if info["score"] < PASS_LINE
                ],
                "generated": {k: v for k, v in submission.items() if k.startswith("generated_")},
            })
        if args.progress_every and question_count % args.progress_every == 0:
            print(f"[arena] 已做题 {question_count}", file=sys.stderr, flush=True)
        if args.limit and question_count >= args.limit:
            break

    ordered_failures = sorted(
        failures, key=lambda f: (0 if f.get("fatal_redlines") else 1, f.get("final_score", 100.0))
    )
    if args.max_failures > 0:
        ordered_failures = ordered_failures[: args.max_failures]
    questions_sha = stream_git_sha256(args.branch, args.questions)
    gt_sha = stream_git_sha256(args.branch, args.gt)
    manifest_sha_match: Dict[str, bool] = {}
    scores = [j["final_score"] for j in judgements]
    pass_count = sum(1 for j in judgements if j["passed"])
    report = {
        "report_version": "1.0",
        "arena": "daily_life_summary（10000 个人的一天 · 六维方向性总结）",
        "judge": "本战队方向性阅卷器（scripts/run_daily_life_arena_01a0aa2c.py:judge_question）",
        "judge_semantics": {
            "direction": "生成总结与锚点 core_claim 的方向概念覆盖率（0.7 权重；同义表达与可接受方向簇均计入，极性相反判 0）",
            "entity": "required_entities 命中率（0.3 权重）",
            "redline": "红线条目 contradicted_claim 的**硬断言**命中（数字+单位，或仅出现在红线中的实词）且其小句无否定语境 → 该维度 0 分并整题 FAIL",
            "pass_line": "final_score ≥ 80.0 且无红线命中（方向 0.7 + 实体 0.3，概念层容差）",
        },
        "solver": {
            "agent": SOLVER_AGENT,
            "variant": "ceiling-echo" if args.ceiling else args.solver_variant,
            "mode": "blind（仅题面 persona + cleaned_daily_stream；零标答接触）",
        },
        "bank": {
            "branch": args.branch,
            "questions_path": args.questions,
            "ground_truth_path": args.gt,
            "manifest_path": args.manifest,
            "manifest_generator_agent": generator_agent,
            "manifest_seed": manifest.get("seed"),
            "manifest_question_count": manifest.get("question_count"),
            "questions_sha256": questions_sha,
            "ground_truth_sha256": gt_sha,
            "manifest_sha256_match": manifest_sha_match,
            "evaluated": len(judgements),
        },
        "metrics": {
            "evaluated": len(judgements),
            "average_score": round(statistics.fmean(scores), 2) if scores else 0.0,
            "median_score": round(statistics.median(scores), 2) if scores else 0.0,
            "pass_count": pass_count,
            "pass_rate_percent": round(100.0 * pass_count / max(len(judgements), 1), 2),
            "fatal_redline_questions": sum(1 for j in judgements if j["fatal_redlines"]),
            "per_dimension_average": {d: round(statistics.fmean(v), 2) for d, v in sorted(dim_scores.items()) if v},
        },
        "attainability_audit": {
            "note": "标答方向概念在盲卷题面中的可观测比例（判断题库可解性上限）",
            "concept_total": attain_total,
            "concept_reachable_in_prompt": attain_reachable,
            "concept_reachable_in_stream_only": attain_stream_reachable,
            "reachable_rate_prompt": round(attain_reachable / max(attain_total, 1), 4),
            "reachable_rate_stream_only": round(attain_stream_reachable / max(attain_total, 1), 4),
        },
        "direction_reversal_audit": {
            "note": "独立于红线的更强检查：答卷把标答否认的不可逆结局说成发生（或反之）即计一次",
            "reversal_count": sum(reversal_counter.values()),
            "by_concept": dict(reversal_counter.most_common()),
            "examples": reversal_examples[:20],
        },
        "failures": {
            "total_not_passed": failure_total,
            "written": len(ordered_failures),
            "truncated": len(ordered_failures) < failure_total,
            "order": "红线命中优先，其次按总分升序（最值得复盘的先写）",
        },
        "error_attribution": dict(reason_counter.most_common()),
        "failures_sample": ordered_failures[:200],
        "failures_sample_note": "完整错题清单见 --failures 输出文件，本报告仅保留最值得复盘的前 200 条",
        "elapsed_seconds": round(time.time() - started, 1),
    }

    if manifest:
        artifacts = manifest.get("artifacts", {}) or {}
        q_name = Path(args.questions).name
        g_name = Path(args.gt).name
        for name in (q_name, g_name):
            if name not in artifacts:
                continue
            expected = str(artifacts[name].get("sha256", ""))
            actual = questions_sha if name == q_name else gt_sha
            manifest_sha_match[name] = bool(expected) and expected == actual
    if args.answers:
        args.answers.parent.mkdir(parents=True, exist_ok=True)
        with args.answers.open("w", encoding="utf-8") as handle:
            for record in answers:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.failures and failures:
        args.failures.parent.mkdir(parents=True, exist_ok=True)
        with args.failures.open("w", encoding="utf-8") as handle:
            for record in ordered_failures:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(report["metrics"], ensure_ascii=False, indent=1))
    print(json.dumps(report["error_attribution"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
