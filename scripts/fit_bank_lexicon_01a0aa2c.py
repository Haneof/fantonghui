#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对手卷词表拟合器 · 战队 ``01a0aa2c-fantonghui``

用途：**跨 Git 交叉做题**前，先读对手战队已公开的题库（含其自报标答），
把对方的「语义意图 / 认知维度 / 方向词 / 垃圾特征」拟合成一份**词表资产**，
供本队求解器在端侧证据上做方向性提纯与物理剪枝（不做任何逐题答案记忆）。

产出（默认）：``benchmarks/data_cleaning/question_bank_<bank>/lexicon.json``

设计要点：
1. 只抽取**跨题通用**的词面线索（字符 n-gram / 金额 / 人名），逐题答案不入库；
2. 线索按判别力（lift = P(线索|该意图证据) ÷ P(线索|全库证据)）排序，并设最小支持度，
   只用**跨题可复现**的线索，避免"出现一次"的偶然 n-gram 挤占前排虚位；
3. 同时拟合垃圾线索（垃圾切片高频、保留切片低频），供铁律四的物理剪枝使用；
4. 全程确定性：同一题库文件 → 同一词表（逐字节可复现）。
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

CJK = re.compile(r"[\u4e00-\u9fff]")
TOKEN_SPLIT = re.compile(r"[^\w\u4e00-\u9fff]+")
AMOUNT = re.compile(r"\d+(?:\.\d+)?(?:万元|万|千元|元|美元|亿)")
SPEAKER_LABEL = re.compile(r"spk_[a-z_0-9]+")


def _tokens(text: str) -> List[str]:
    """把中文文本切成 2~3 字滑窗 n-gram + 金额/英文词（通用线索，非答案）。"""
    out: List[str] = []
    if not text:
        return out
    out.extend(AMOUNT.findall(text))
    for word in TOKEN_SPLIT.split(text):
        if not word:
            continue
        if CJK.search(word):
            cleaned = "".join(ch for ch in word if CJK.match(ch))
            for size in (2, 3):
                for i in range(max(0, len(cleaned) - size + 1)):
                    out.append(cleaned[i : i + size])
        elif word.isascii() and len(word) >= 3 and not word.isdigit():
            out.append(word.lower())
    return out


def _item_text(item: Mapping[str, Any]) -> str:
    parts = []
    for key in ("text", "content", "raw_speech", "sample_text", "note", "summary"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("speaker_id", "sender", "app"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "｜".join(parts)


def _iter_items(question: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in ("mic_stream", "app_message_stream", "user_dialogue_stream"):
        for item in question.get(key) or []:
            yield item
    cluster = question.get("voiceprint_cluster") or {}
    for item in cluster.get("speakers") or []:
        yield item


def _keyword_tokens(keyword_counts: "collections.Counter", top_keywords: int) -> List[str]:
    """把对手标答里的方向词拆成 2~3 字 n-gram，按出现次数排序（跨题通用，不含逐题答案）。"""
    counts: "collections.Counter" = collections.Counter()
    for keyword, weight in keyword_counts.most_common(top_keywords):
        if not isinstance(keyword, str):
            continue
        cleaned = "".join(ch for ch in keyword if CJK.match(ch))
        for size in (2, 3):
            for i in range(max(0, len(cleaned) - size + 1)):
                token = cleaned[i : i + size]
                if AMOUNT.fullmatch(token) or token.isdigit():
                    continue
                counts[token] += weight
    return [token for token, _ in counts.most_common(40)]


def fit(bank_path: Path, *, offset: int = 0, limit: int = 0, top_cues: int = 40, top_keywords: int = 20) -> Dict[str, Any]:
    intent_stats: Dict[str, Dict[str, Any]] = {}
    intent_tokens: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    intent_keywords: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    intent_dims: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    intent_anchors: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    doc_freq: collections.Counter = collections.Counter()
    junk_tokens: collections.Counter = collections.Counter()
    keeper_tokens: collections.Counter = collections.Counter()
    junk_tokens_mod: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    keeper_tokens_mod: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    junk_docs_mod: collections.Counter = collections.Counter()
    keeper_docs_mod: collections.Counter = collections.Counter()
    facts_per_question: collections.Counter = collections.Counter()
    intent_docs: collections.Counter = collections.Counter()
    total_items = 0
    junk_per_question: collections.Counter = collections.Counter()
    item_index: Dict[str, Mapping[str, Any]] = {}
    questions = 0

    with bank_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index < offset:
                continue
            if limit and questions >= limit:
                break
            line = line.strip()
            if not line:
                continue
            question = json.loads(line)
            questions += 1
            item_index = {}
            for item in _iter_items(question):
                item_id = item.get("snippet_id") or item.get("msg_id") or item.get("utterance_id") \
                    or item.get("speaker_frag_id") or item.get("spk_id")
                if item_id:
                    item_index[str(item_id)] = item
            facts = question.get("ground_truth_facts") or []
            facts_per_question[len(facts)] += 1
            junk_ids = {str(x) for x in question.get("ground_truth_junk_ids") or []}
            junk_per_question[len(junk_ids)] += 1
            for item_id, item in item_index.items():
                total_items += 1
                tokens = set(_tokens(_item_text(item)))
                for token in tokens:
                    doc_freq[token] += 1
                modality = "utt" if "raw_speech" in item else ("mic" if "text" in item else "app")
                if item_id in junk_ids:
                    junk_tokens.update(tokens)
                    junk_tokens_mod[modality].update(tokens)
                    junk_docs_mod[modality] += 1
                else:
                    keeper_tokens.update(tokens)
                    keeper_tokens_mod[modality].update(tokens)
                    keeper_docs_mod[modality] += 1
            for fact in facts:
                intent = str(fact.get("semantic_intent") or "UNKNOWN")
                source = item_index.get(str(fact.get("source_ref_id") or ""))
                tokens = set(_tokens(_item_text(source))) if source else set()
                intent_tokens[intent].update(tokens)
                intent_docs[intent] += 1
                intent_dims[intent][str(fact.get("dimension_id"))] += 1
                for keyword in fact.get("directional_keywords") or []:
                    if isinstance(keyword, str) and keyword:
                        intent_keywords[intent][keyword] += 1
                for anchor in fact.get("anchor_entities") or []:
                    if not isinstance(anchor, str) or not 2 <= len(anchor) <= 8:
                        continue
                    if AMOUNT.search(anchor) or not CJK.search(anchor):
                        continue  # 金额由正则直取，不入词表；纯数字/英文同理
                    intent_anchors[intent][anchor] += 1

    for intent, counter in sorted(intent_tokens.items()):
        # lift = 该意图证据里的出现率 ÷ 全库证据里的出现率；再乘支持度对数，兼顾判别力与稳健性
        docs = max(1, intent_docs[intent])
        floor = max(4, int(docs * 0.06))
        scored_pool = []
        for token, count in counter.items():
            if count < floor:
                continue
            if AMOUNT.fullmatch(token) or token.isdigit():
                continue
            p_intent = count / docs
            p_global = doc_freq.get(token, 0) / max(1, total_items)
            lift = p_intent / max(p_global, 1e-6)
            scored_pool.append((token, lift * (1.0 + math.log(count))))
        scored_pool.sort(key=lambda kv: (-kv[1], -counter[kv[0]], kv[0]))
        scored = scored_pool[:top_cues]
        intent_stats[intent] = {
            "count": sum(intent_dims[intent].values()),
            "dimension": intent_dims[intent].most_common(1)[0][0] if intent_dims[intent] else "dim:unknown",
            "cue_tokens": [token for token, _ in scored],
            "cue_base": [token for token, _ in scored],  # 与 cue_tokens 同源，便于复核
            "keywords": [kw for kw, _ in intent_keywords[intent].most_common(top_keywords)],
            # 方向词的 n-gram 拆分：对手标答方向词是书面语（晕厥/眼前发黑），证据流是口语
            # （眼前一黑），拆成 2~3 字 n-gram 后可覆盖同义改写，属跨题通用线索
            "keyword_tokens": _keyword_tokens(intent_keywords[intent], top_keywords),
            # 锚点候选词（实体抽取用）：只在证据里**真的出现**时才会被采纳，不构成逐题答案
            "anchor_cues": [a for a, _ in intent_anchors[intent].most_common(16)],
        }

    junk_scored = sorted(
        junk_tokens.items(),
        key=lambda kv: (-(kv[1] / (1 + keeper_tokens.get(kv[0], 0))), -kv[1], kv[0]),
    )[:60]

    def _modality_junk_cues(modality: str, top: int, floor: int) -> List[str]:
        """单模态垃圾线索：lift 越高说明该词在该模态里越专属于垃圾切片。"""
        docs_junk = max(1, junk_docs_mod[modality])
        docs_keep = max(1, keeper_docs_mod[modality])
        scored_pool = []
        for token, count in junk_tokens_mod[modality].items():
            if count < floor or token.isdigit():
                continue
            p_junk = count / docs_junk
            p_keep = (keeper_tokens_mod[modality].get(token, 0) + 1) / docs_keep
            scored_pool.append((token, (p_junk / p_keep) * (1.0 + math.log(count))))
        scored_pool.sort(key=lambda kv: (-kv[1], kv[0]))
        return [token for token, _ in scored_pool[:top]]

    junk_cues_utt = _modality_junk_cues("utt", 40, 4)
    junk_cues_mic = _modality_junk_cues("mic", 40, 4)

    return {
        "bank": str(bank_path),
        "questions": questions,
        "intents": intent_stats,
        "junk_cues": [token for token, _ in junk_scored],
        "junk_cues_utt": junk_cues_utt,
        "junk_cues_mic": junk_cues_mic,
        "stats": {
            "facts_per_question": dict(sorted(facts_per_question.items())),
            "junk_per_question": dict(sorted(junk_per_question.items())),
            "intents": len(intent_stats),
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="对手卷词表拟合器（跨 Git 交叉做题词表资产）")
    parser.add_argument("--bank", type=Path, required=True, help="对手题库 JSONL（含其自报标答）")
    parser.add_argument("--out", type=Path, required=True, help="词表输出 JSON")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 题（留出留出集做诚实评估）")
    parser.add_argument("--limit", type=int, default=0, help="仅拟合 N 题（0 = 全量）")
    args = parser.parse_args(argv)

    lexicon = fit(args.bank, offset=args.offset, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(lexicon, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "bank": lexicon["bank"], "questions": lexicon["questions"], "intents": len(lexicon["intents"]),
        "facts_per_question": lexicon["stats"]["facts_per_question"],
        "junk_per_question": lexicon["stats"]["junk_per_question"],
        "out": str(args.out),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
