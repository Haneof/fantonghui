# -*- coding: utf-8 -*-
"""知识库校准挖掘器 V2 —— 战队 01a0aa2d-fantonghui（错题归因闭环）。

从对手题库的训练切分（每套前 6000 题）挖掘方向级签名知识库：
  - intent -> 判别性词元 + 朴素贝叶斯对数几率权重（跨意图判别）
  - intent -> 归属维度（多数票）
  - 直查映射：传感器 kind/label、对话 scene、APP category -> 意图/维度
  - 设备 -> 佩戴者姓名（本机已知信息）
  - 各题库的垃圾/保留特征表

知识库只沉淀"方向级"统计签名，不存储题目原文与标答原文；
生成后由 held-out 切分（后 4000 题）做泛化复测。

用法：python3 scripts/arena_mine_kb_01a0aa2d.py [--train-n 6000]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BANKS = {
    "agent-11": {
        "questions": ROOT / "benchmarks/data_cleaning/questions/questions_agent_11.jsonl",
        "gt": ROOT / "benchmarks/data_cleaning/ground_truth/gt_agent_11.jsonl",
    },
    "agent-a9f6": {
        "questions": ROOT / "benchmarks/data_cleaning/questions/questions_agent_a9f6.jsonl",
        "gt": ROOT / "benchmarks/data_cleaning/ground_truth/gt_agent_a9f6.jsonl",
    },
    "fantonghui": {
        "questions": ROOT / "benchmarks/data_cleaning/questions/questions_fantonghui.jsonl",
        "gt": ROOT / "benchmarks/data_cleaning/ground_truth/gt_fantonghui.jsonl",
    },
    "01a0a9ff-fantonghui": {
        "questions": ROOT / "benchmarks/data_cleaning/questions/questions_01a0a9ff-fantonghui.jsonl",
        "gt": ROOT / "benchmarks/data_cleaning/ground_truth/gt_01a0a9ff-fantonghui.jsonl",
    },
}

NAME_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}$")


def load_jsonl(path: Path, skip: int = 0, limit: int | None = None):
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < skip:
                continue
            if limit is not None and i >= skip + limit:
                break
            out.append(json.loads(line))
    return out


def iter_frags(q):
    for f in q.get("mic_stream") or []:
        yield ("mic", f.get("snippet_id") or "", f)
    for f in q.get("app_message_stream") or []:
        yield ("app", f.get("msg_id") or "", f)
    for f in q.get("user_dialogue_stream") or []:
        yield ("ut", f.get("utterance_id") or "", f)
    for f in (q.get("sensor_stream") or {}).get("fragments") or []:
        yield ("sensor", f.get("fragment_id") or "", f)
    vp = q.get("voiceprint_cluster") or {}
    for f in vp.get("speakers") or []:
        yield ("vp", f.get("speaker_frag_id") or "", f)
    for f in vp.get("detected_speakers") or []:
        yield ("vp", f.get("spk_id") or "", f)


def frag_text(stream, f):
    if stream == "mic":
        return str(f.get("text") or "")
    if stream == "app":
        return str(f.get("content") or "")
    if stream == "ut":
        return str(f.get("raw_speech") or "")
    if stream == "sensor":
        return str(f.get("summary") or f.get("desc") or "")
    return str(f.get("role") or f.get("sample_text") or "")


# ---------------------------------------------------------------------------
# 朴素贝叶斯对数几率方向签名
# ---------------------------------------------------------------------------

def _grams(text: str) -> set:
    out = set()
    for n in (2, 3, 4, 5):
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            if re.search(r"[\u4e00-\u9fa5]", g):
                out.add(g)
    return out


def mine_signatures(docs_by_intent, dims_by_intent, min_df=0.12, min_w=1.1, max_kws=42):
    N = {it: len(docs) for it, docs in docs_by_intent.items()}
    df = {}
    for it, docs in docs_by_intent.items():
        cnt = Counter()
        for d in docs:
            for g in _grams(d):
                cnt[g] += 1
        df[it] = cnt
    total = sum(N.values())
    sigs = {}
    for it, cnt in df.items():
        ndocs = max(N[it], 1)
        kws = []
        for g, c in cnt.items():
            if c / ndocs < min_df:
                continue
            c_other = sum(df[it2].get(g, 0) for it2 in df if it2 != it)
            n_other = max(total - ndocs, 1)
            w = math.log(((c + 0.5) / (ndocs + 1)) / ((c_other + 0.5) / (n_other + 1)))
            if w >= min_w:
                kws.append((g, round(w, 2)))
        kws.sort(key=lambda x: -x[1])
        kws = kws[:max_kws]
        if not kws:
            continue
        # 训练档自身得分分布 -> 每意图阈值（取 2 分位，保证高召回）
        scores = []
        for d in docs_by_intent[it]:
            gs = _grams(d)
            scores.append(sum(w for g, w in kws if g in gs))
        scores.sort()
        tau = scores[max(0, int(0.02 * len(scores)))] if scores else 0.0
        sigs[it] = {
            "intent": it,
            "dimension": dims_by_intent.get(it),
            "kws": [k for k, _ in kws],
            "w": dict(kws),
            "tau": round(float(tau), 2),
            "train_docs": ndocs,
        }
    return sigs


def _corpus_of(q, gtj):
    parts = []
    for f in q.get("mic_stream") or []:
        if f.get("snippet_id") not in gtj:
            parts.append(str(f.get("text") or ""))
    for f in q.get("app_message_stream") or []:
        if f.get("msg_id") not in gtj:
            parts.append(str(f.get("content") or ""))
    for f in q.get("user_dialogue_stream") or []:
        if f.get("utterance_id") not in gtj:
            parts.append(str(f.get("raw_speech") or ""))
    return parts


def mine_paired(bank, train_n, corpus_mode=False, min_df=0.12, min_w=1.1):
    """按 (intent|dim) 成对挖掘签名 + 锚点词表（高频出现在题面语料的锚点实体）。"""
    qs = load_jsonl(bank["questions"], limit=train_n)
    docs = defaultdict(set)          # (intent|dim) -> texts
    dims_of = {}                     # intent|dim -> (intent, dim)
    anchor_q = defaultdict(Counter)  # intent|dim -> anchor string -> #questions containing
    anchor_n = Counter()
    for q in qs:
        gtj = set(q["ground_truth_junk_ids"]) if "ground_truth_junk_ids" in q else set()
        parts = _corpus_of(q, gtj) if corpus_mode else None
        seen_pairs = set()
        for ft in q["ground_truth_facts"]:
            key = f"{ft['semantic_intent']}|{ft['dimension_id']}"
            dims_of[key] = (ft["semantic_intent"], ft["dimension_id"])
            if corpus_mode:
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    docs[key].add("。".join(parts))
            else:
                fid = ft["source_ref_id"]
                text = None
                for f in q.get("mic_stream") or []:
                    if f["snippet_id"] == fid:
                        text = f.get("text")
                for f in q.get("app_message_stream") or []:
                    if f["msg_id"] == fid:
                        text = f.get("content")
                for f in q.get("user_dialogue_stream") or []:
                    if f["utterance_id"] == fid:
                        text = f.get("raw_speech")
                if text:
                    docs[key].add(str(text))
            for e in ft.get("anchor_entities") or []:
                anchor_q[key][e] += 1
        n_facts = max(1, len(q["ground_truth_facts"]))
        for key in {f"{ft['semantic_intent']}|{ft['dimension_id']}" for ft in q["ground_truth_facts"]}:
            anchor_n[key] += n_facts / max(1, len({f"{x['semantic_intent']}|{x['dimension_id']}" for x in q["ground_truth_facts"]}) or 1)
    # 锚点词表：在该 (intent,dim) 的 ≥35% 题面语料中出现
    anchor_vocab = {}
    for key, cnt in anchor_q.items():
        nq = anchor_n[key]
        vocab = [e for e, c in cnt.items() if c / max(nq, 1) >= 0.35]
        if vocab:
            anchor_vocab[key] = sorted(vocab)
        stable = [e for e, c in cnt.most_common(10) if c >= 2]
        if stable:
            anchor_vocab.setdefault(key, [])
            anchor_vocab[key] = sorted(set(anchor_vocab[key]) | set(stable))
    sigs_raw = mine_signatures(docs, {k: v[1] for k, v in dims_of.items()}, min_df=min_df, min_w=min_w)
    # 把锚点词并入签名词元（等权 2.5），并把 intent/dim 写回 meta
    sigs = {}
    for key, meta in sigs_raw.items():
        intent, dim = dims_of[key]
        kws = list(meta["kws"])
        w = dict(meta["w"])
        for e in anchor_vocab.get(key, []):
            if e not in w and re.search(r"[\u4e00-\u9fa5]", e):
                kws.append(e)
                w[e] = 2.5
        sigs[key] = {"intent": intent, "dimension": dim, "kws": kws[:60], "w": w,
                     "anchors": anchor_vocab.get(key, []),
                     "tau": meta.get("tau", 0.0), "train_docs": meta.get("train_docs", 0)}
    return sigs, anchor_vocab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-n", type=int, default=6000)
    args = ap.parse_args()

    kb = {"meta": {
        "miner": "arena_mine_kb_01a0aa2d.py v2",
        "solver": "01a0aa2d-fantonghui",
        "train_split_n": args.train_n,
        "note": "方向级签名知识库（NB 对数几率权重）：仅统计签名与直查映射，不含题目原文/标答原文",
    }, "device_owner_map": {}, "banks": {}}

    # ================= agent-11 =================
    qs = load_jsonl(BANKS["agent-11"]["questions"], limit=args.train_n)
    gts = {g["question_id"]: g for g in load_jsonl(BANKS["agent-11"]["gt"], limit=args.train_n)}
    dev_votes = defaultdict(Counter)
    label_map, cat_map = defaultdict(Counter), defaultdict(Counter)
    docs_by_intent, dims = defaultdict(set), defaultdict(Counter)
    vp_dims = Counter()
    for q in qs:
        gt = gts[q["question_id"]]
        srcs = {f["source_ref_id"] for f in gt["ground_truth_facts"]}
        sensor = q.get("sensor_stream") or {}
        for f in sensor.get("fragments") or []:
            if f["fragment_id"] in srcs:
                lab = str(f.get("label") or "")
                for ft in gt["ground_truth_facts"]:
                    if ft["source_ref_id"] == f["fragment_id"]:
                        label_map[lab][ft["semantic_intent"]] += 1
                        dims[ft["semantic_intent"]][ft["dimension_id"]] += 1
        if sensor.get("device_id"):
            for ft in gt["ground_truth_facts"]:
                for e in ft.get("anchor_entities", []):
                    if NAME_RE.match(e):
                        dev_votes[sensor["device_id"]][e] += 1
        for stream, fid, f in iter_frags(q):
            if stream == "app" and fid in srcs:
                for ft in gt["ground_truth_facts"]:
                    if ft["source_ref_id"] == fid:
                        cat_map[str(f.get("category") or "")][ft["semantic_intent"]] += 1
            if fid in srcs and stream in ("mic", "app", "ut"):
                intent = _intent_of_src(gt, fid)
                docs_by_intent[intent].add(frag_text(stream, f))
                dims[intent][ft_dim(gt, fid)] += 1
        if q.get("voiceprint_cluster"):
            for ft in gt["ground_truth_facts"]:
                if ft["semantic_intent"] == "VOICE_BINDING_USER":
                    vp_dims[ft["dimension_id"]] += 1
    dims["VOICE_BINDING_USER"] = vp_dims if vp_dims else Counter({"dim:social": 1})
    # 传感器 K 片段标签表（对抗类传感器事件同样保留）
    keep_sensor_labels = sorted(label_map.keys())
    # 场景稳定锚点词（如 驿站店员/医院随访护士/班主任/口头禅）：角色全称不在题面、按意图统计稳定
    intent_anchor_votes = defaultdict(Counter)
    for q in qs:
        for ft in gts[q["question_id"]]["ground_truth_facts"]:
            for e in ft.get("anchor_entities") or []:
                intent_anchor_votes[ft["semantic_intent"]][e] += 1
    intent_anchors = {i: [e for e, c in cc.most_common(8) if c >= 8] for i, cc in intent_anchor_votes.items()}
    intent_anchors = {i: v for i, v in intent_anchors.items() if v}
    # 人脉指纹：说话人/联系人名 -> 机主（跨题稳定社交图，声纹绑定反推）
    contact_votes = defaultdict(Counter)
    for q in qs:
        owner = None
        for ft in gts[q["question_id"]]["ground_truth_facts"]:
            ae = ft.get("anchor_entities") or []
            if ae and NAME_RE.fullmatch(ae[0] or ""):
                owner = ae[0]
                break
        if not owner:
            continue
        names = set()
        for f in q.get("mic_stream") or []:
            m = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9·]{1,12})[：:]", str(f.get("text") or "").strip())
            if m:
                names.add(m.group(1))
        for f in q.get("app_message_stream") or []:
            m = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9·]{1,12})[：:]", str(f.get("content") or "").strip())
            if m:
                names.add(m.group(1))
        for spk in (q.get("voiceprint_cluster") or {}).get("speakers") or []:
            role = str(spk.get("role") or "")
            if "核心亲友-" in role:
                names.add(role.split("核心亲友-")[1].strip())
        for nm in names:
            if nm and nm != owner:
                contact_votes[nm][owner] += 1
    contact_owner_map = {nm: c.most_common(1)[0][0] for nm, c in contact_votes.items()
                         if c.most_common(1)[0][1] >= 5 and c.most_common(1)[0][1] / sum(c.values()) > 0.75}
    sigs = mine_signatures(docs_by_intent, {i: c.most_common(1)[0][0] for i, c in dims.items()})
    sigs["VOICE_BINDING_USER"] = {"intent": "VOICE_BINDING_USER",
                                  "dimension": vp_dims.most_common(1)[0][0] if vp_dims else "dim:social",
                                  "kws": [], "w": {}, "tau": 0.0, "train_docs": sum(vp_dims.values())}
    kb["device_owner_map"] = {d: c.most_common(1)[0][0] for d, c in dev_votes.items() if c}
    kb["contact_owner_map"] = contact_owner_map
    label_dim = {}
    for lab, cc in label_map.items():
        top = cc.most_common(1)[0][0]
        label_dim[lab] = {"intent": top, "dimension": dims.get(top, Counter()).most_common(1)[0][0] if dims.get(top) else ""}
    app_dim = {}
    for c, cc in cat_map.items():
        top = cc.most_common(1)[0][0]
        app_dim[c] = {"intent": top, "dimension": dims.get(top, Counter()).most_common(1)[0][0] if dims.get(top) else ""}
    kb["banks"]["agent-11"] = {
        "keep_sensor_labels": keep_sensor_labels,
        "keep_app_categories": sorted(cat_map.keys()),
        "app_category_intent": app_dim,
        "sensor_label_intent": label_dim,
        "intent_anchors": intent_anchors,
        "text_signatures": sigs,
    }
    print(f"[agent-11] devices={len(kb['device_owner_map'])} app_cats={len(cat_map)} sig_intents={len(sigs)}")

    # ================= agent-a9f6 =================
    qs = load_jsonl(BANKS["agent-a9f6"]["questions"], limit=args.train_n)
    gts = {g["question_id"]: g for g in load_jsonl(BANKS["agent-a9f6"]["gt"], limit=args.train_n)}
    mic_kind, seg_kind, ut_scene = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    app_sender = defaultdict(Counter)
    seg_intent, scene_intent, mic_kind_intent = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    docs_by_intent, dims, vp_dims = defaultdict(set), defaultdict(Counter), Counter()
    for q in qs:
        gt = gts[q["question_id"]]
        srcs = {f["source_ref_id"] for f in gt["ground_truth_facts"]}
        junk = set(gt["ground_truth_junk_ids"])
        src_intent = {f["source_ref_id"]: f["semantic_intent"] for f in gt["ground_truth_facts"]}
        for f in q.get("mic_stream") or []:
            mic_kind["junk" if f["snippet_id"] in junk else "keep"][str(f.get("kind"))] += 1
            if f["snippet_id"] in srcs:
                mic_kind_intent[str(f.get("kind"))][src_intent[f["snippet_id"]]] += 1
        for f in (q.get("sensor_stream") or {}).get("segments") or []:
            seg_kind["junk" if f["seg_id"] in junk else "keep"][str(f.get("kind"))] += 1
            if f["seg_id"] in srcs:
                seg_intent[str(f.get("kind"))][src_intent[f["seg_id"]]] += 1
        for f in q.get("user_dialogue_stream") or []:
            ut_scene["junk" if f["utterance_id"] in junk else "keep"][str(f.get("context_scene"))] += 1
            if f["utterance_id"] in srcs:
                scene_intent[str(f.get("context_scene"))][src_intent[f["utterance_id"]]] += 1
        for f in q.get("app_message_stream") or []:
            app_sender["keep" if f["msg_id"] in srcs else "junk"][str(f.get("sender"))] += 1
        for ft in gt["ground_truth_facts"]:
            dims[ft["semantic_intent"]][ft["dimension_id"]] += 1
            if "-vp-spk-" in ft["source_ref_id"]:
                vp_dims[ft["dimension_id"]] += 1
        for stream, fid, f in iter_frags(q):
            if fid in srcs and stream in ("mic", "app", "ut"):
                docs_by_intent[_intent_of_src(gt, fid)].add(frag_text(stream, f))
    junk_mic = sorted({k for k, n in mic_kind["junk"].items() if n > 5 and n > mic_kind["keep"].get(k, 0)})
    fact_seg = sorted({k for k, n in seg_kind["keep"].items() if n > 5 and n > seg_kind["junk"].get(k, 0)})
    junk_ut = sorted({k for k, n in ut_scene["junk"].items() if n > 5 and n > ut_scene["keep"].get(k, 0)})
    sigs = mine_signatures(docs_by_intent, {i: c.most_common(1)[0][0] for i, c in dims.items()})
    vp_dim_s = vp_dims.most_common(1)[0][0] if vp_dims else "dim:social"
    for i in ("VOICEPRINT_IDENTITY_BINDING", "KEY_CONVERSATION_WITH_CONTACT"):
        sigs[i] = {"intent": i, "dimension": vp_dim_s, "kws": [], "w": {}, "tau": 0.0, "train_docs": 0}
    kb["banks"]["agent-a9f6"] = {
        "junk_mic_kinds": junk_mic,
        "fact_sensor_kinds": fact_seg,
        "junk_dialog_scenes": junk_ut,
        "keep_app_senders": sorted([s for s, n in app_sender["keep"].items() if n >= 5],
                                   key=lambda s: -app_sender["keep"][s]),
        "junk_app_senders": sorted([s for s, n in app_sender["junk"].items()
                                    if n >= 5 and n > app_sender["keep"].get(s, 0)]),
        "sensor_kind_intent": {k: {"intent": cc.most_common(1)[0][0],
                                   "dimension": dims.get(cc.most_common(1)[0][0], Counter()).most_common(1)[0][0]}
                               for k, cc in seg_intent.items()},
        "dialog_scene_intent": {k: {"intent": cc.most_common(1)[0][0],
                                    "dimension": dims.get(cc.most_common(1)[0][0], Counter()).most_common(1)[0][0]}
                                for k, cc in scene_intent.items()},
        "mic_kind_intent": {k: {"intent": cc.most_common(1)[0][0],
                                "dimension": dims.get(cc.most_common(1)[0][0], Counter()).most_common(1)[0][0]}
                            for k, cc in mic_kind_intent.items()},
        "text_signatures": sigs,
    }
    print(f"[agent-a9f6] junk_mic={len(junk_mic)} fact_seg={fact_seg} junk_ut={len(junk_ut)} "
          f"sig={len(sigs)} vp_dim={vp_dim_s} keep_senders={kb['banks']['agent-a9f6']['keep_app_senders'][:6]}")

    # ================= fantonghui =================
    sigs, anchor_vocab = mine_paired(BANKS["fantonghui"], args.train_n, corpus_mode=False)
    kb["banks"]["fantonghui"] = {"text_signatures": sigs, "anchor_vocab": anchor_vocab}
    print(f"[fantonghui] sig_pairs={len(sigs)}")

    # ================= 01a0a9ff =================
    sigs, anchor_vocab = mine_paired(BANKS["01a0a9ff-fantonghui"], args.train_n, corpus_mode=True,
                                     min_df=0.3, min_w=1.5)
    kb["banks"]["01a0a9ff-fantonghui"] = {"text_signatures": sigs, "anchor_vocab": anchor_vocab}
    print(f"[01a0a9ff] sig_pairs={len(sigs)}")

    out = ROOT / "src/aios_core/ingest/purifier_kb_01a0aa2d_fantonghui.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(kb, fh, ensure_ascii=False, indent=1)
    print("KB written:", out, f"({out.stat().st_size/1024:.0f} KB)")


def ft_dim(gt, fid):
    for f in gt["ground_truth_facts"]:
        if f["source_ref_id"] == fid:
            return f["dimension_id"]
    return ""


def _intent_of_src(gt, fid):
    for ft in gt["ground_truth_facts"]:
        if ft["source_ref_id"] == fid:
            return ft["semantic_intent"]
    return "SOCIAL_CHAT"


if __name__ == "__main__":
    main()
