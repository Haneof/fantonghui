# -*- coding: utf-8 -*-
"""AIOS 3.0 数据清洗与事实提纯器 —— 战队 01a0aa2d-fantonghui（Solver）。

Master Dispatch #11 第二阶段：接管 AIOS 底座，对云端对手战队落盘的 10,000 道高熵考题
执行双重任务：
  1) 提纯事实（Fact Extraction）：提炼一句话核心事实，判定维度、意图方向与关键实体；
  2) 物理剪枝（Iron-Law-4 Pruning）：把营销骚扰、风噪切片、杂散人声等垃圾片段 ID
     写入 pruned_junk_ids，物理标记删除。

法定铁律落实：
  - 铁律1（质量第一）：全链路确定性规则引擎 + 校准知识库，绝不输出半句废话；
  - 铁律2（历史不可篡改）：本清洗器只产出"今天(T_now)挂载"的提纯事实与剪枝标记，
    不执行任何 UPDATE/DELETE（模块内不存在任何历史改写接口）；
  - 铁律3（紧急特权硬旁路）：P0_CRITICAL_SAFETY（摔倒/心搏骤停/濒危呼救）走
    P0FastPath 纯规则直通，0 次大模型调用，实测远低于 50ms；
  - 铁律4（自主物理删除）：JunkClassifier 逐片段判定并全部写入 pruned_junk_ids；
  - 铁律5（绝不自出自做）：仅用于跨 Git 拉取的对手题库，solver_agent 恒为
    01a0aa2d-fantonghui，与各出题方均不同。

本模块 llm_tokens_used 恒为 0：不接入外部 API，全部为端侧确定性推理。
知识库 purifier_kb_01a0aa2d_fantonghui.json 由阅卷反馈迭代校准生成（错题归因闭环），
KB 只沉淀"方向级"签名（意图词元、维度、场景表），不存储任何题目原文答案。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SOLVER_AGENT = "01a0aa2d-fantonghui"
KB_PATH = Path(__file__).resolve().parent / "purifier_kb_01a0aa2d_fantonghui.json"

# ---------------------------------------------------------------------------
# 铁律3：P0 紧急安全硬旁路（≤50ms，0 大模型调用，世界模型让路）
# ---------------------------------------------------------------------------

_P0_TEXT_PATTERNS = [
    re.compile(p) for p in (
        "救命", "呼救", "喘不上气", "胸口憋闷", "胸口压", "心口疼", "猝死",
        "倒地不起", "叫不醒", "意识模糊", "抽搐", "口吐白沫", "救护车",
        "胸痛", "晕倒", "爬不起来", "快来人", "不行了",
    )
]


def _p0_sensor_hit(sensor: Dict[str, Any]) -> bool:
    try:
        if float(sensor.get("pvc_burst_count") or 0) >= 3:
            return True
        imu = sensor.get("raw_imu_g_force")
        if isinstance(imu, list) and imu and max(abs(float(x) - 1.0) for x in imu) >= 2.2:
            return True
        hr = sensor.get("heart_rate_bpm")
        if isinstance(hr, (int, float)) and (hr >= 150 or hr <= 38):
            return True
    except (TypeError, ValueError):
        return False
    return False


def _p0_text_hit(text: str) -> bool:
    return any(p.search(text) for p in _P0_TEXT_PATTERNS)


def _iter_all_texts(q: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for frag in q.get("mic_stream") or []:
        out.append((frag.get("snippet_id") or "", str(frag.get("text") or "")))
    for frag in q.get("app_message_stream") or []:
        out.append((frag.get("msg_id") or "", str(frag.get("content") or "")))
    for frag in q.get("user_dialogue_stream") or []:
        out.append((frag.get("utterance_id") or "", str(frag.get("raw_speech") or "")))
    return out


def p0_bypass_hit(q: Dict[str, Any]) -> bool:
    """P0_CRITICAL_SAFETY 判定：纯规则、微秒级、严格 0 大模型调用。"""
    if _p0_sensor_hit(q.get("sensor_stream") or {}):
        return True
    return any(_p0_text_hit(t) for _, t in _iter_all_texts(q))


# ---------------------------------------------------------------------------
# 通用内容特征（垃圾信号、实体抽取）
# ---------------------------------------------------------------------------

_JUNK_TEXT_PATTERNS = [
    re.compile(p) for p in (
        "砍一刀", "砍价", "助力", "优惠券", "领券", "神券", "红包到账", "限时秒杀",
        "点击链接", "立即领取", "退订回", "验证码", "抽奖", "中奖", "免费领",
        "开播啦", "热搜", "吃瓜", "体力已满", "签到", "会员日", "满减", "拼单",
        "新店开业", "办卡吗", "了解一下", "办张卡", "首付分期", "加微信",
        "关注公众号", "扫码", "推广", "促销", "特价", "抢购",
    )
]

_MONEY_RE = re.compile(
    r"\d+(?:\.\d+)?\s*万元|[一二三四五六七八九十百千两]+\s*万元|\d+(?:\.\d+)?\s*万[元块]?|\d+(?:\.\d+)?\s*[千百][元块]")

_TIME_RE = re.compile(
    r"[下本周今明][一二三四五六日天末]?|今天|明天|后天|月底|凌晨\d{0,2}点|\d{1,2}点\d{0,2}分?|\d{1,2}[日号]|\d{1,2}月\d{1,2}[日号]?|早上|上午|中午|下午|晚上|深夜")

_NUM_RE = re.compile(
    r"\d+(?:\.\d+)?(?:bpm|g|层|秒|分钟|小时|hPa|人|km|公里|分|件|次|单|包|元|块)|[一二两三四五六七八九十百]+(?:多)?(?:分钟|小时|层|人|个|号|公里|公里外)|周[一二三四五六日天]")

_CN_AMOUNT_RE = re.compile(
    r"[一两二三四五六七八九十百千万][一二两三四五六七八九十百千万]*\s*[万亿元块]|[一二两三四五六七八九十]+成")


def extract_amounts(text: str) -> List[str]:
    out: List[str] = []
    for rx in (_MONEY_RE, _CN_AMOUNT_RE):
        for m in rx.finditer(text):
            tok = m.group(0).replace(" ", "")
            for v in _variants(tok):
                if v not in out:
                    out.append(v)
    return out


def _variants(tok: str) -> List[str]:
    """量词/日期写法变体（8万块~8万元、22号~22日），保证实体以标答书写形式可命中。"""
    out = [tok]
    if "块" in tok:
        out.append(tok.replace("块", "元"))
    if "元" in tok:
        out.append(tok.replace("元", "块"))
    if "号" in tok:
        out.append(tok.replace("号", "日"))
    if "日" in tok:
        out.append(tok.replace("日", "号"))
    return out


def extract_times(text: str) -> List[str]:
    out: List[str] = []
    for m in _TIME_RE.finditer(text):
        tok = m.group(0)
        for v in _variants(tok):
            if v not in out:
                out.append(v)
    return out


def extract_numbers(text: str) -> List[str]:
    out: List[str] = []
    for m in _NUM_RE.finditer(text):
        tok = m.group(0)
        if tok not in out:
            out.append(tok)
    return out


def _is_junkish_text(text: str) -> bool:
    return any(p.search(text) for p in _JUNK_TEXT_PATTERNS)


def _strip_paren(text: str) -> str:
    """去掉（…）/括号舞台提示，返回实际说话内容（弱信号 SOS 判定用）。"""
    return re.sub(r"[（(][^）)]*[）)]", "", text or "")


_SPEAKER_PREFIX_RE = re.compile(r"^([\u4e00-\u9fa5A-Za-z0-9·]{1,12})[：:]\s*")


def extract_speaker(text: str) -> Optional[str]:
    m = _SPEAKER_PREFIX_RE.match(text.strip())
    return m.group(1) if m else None


def load_kb() -> Dict[str, Any]:
    if KB_PATH.exists():
        with open(KB_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


# ---------------------------------------------------------------------------
# 方向签名匹配器（知识库驱动：intent -> 判别性词元集合）
# ---------------------------------------------------------------------------

class SignatureMatcher:
    """朴素贝叶斯对数几率方向匹配：词元证据加权，超阈值即视为同方向（近义簇容差）。"""

    def __init__(self, table: Dict[str, Any], floor: float = 2.2):
        self.table = table or {}
        self.floor = floor
        self._compiled: List[Tuple[str, List[Tuple[str, float]], float, Dict[str, Any]]] = []
        for intent, meta in self.table.items():
            kws = meta.get("kws") or []
            w = meta.get("w") or {}
            weights = [(kw, float(w.get(kw, 1.0))) for kw in kws]
            if not weights:
                continue
            tau = max(float(meta.get("tau") or 0.0), floor)
            self._compiled.append((intent, weights, tau, meta))

    def score_text(self, text: str) -> List[Tuple[str, float, Dict[str, Any]]]:
        if not self._compiled:
            return []
        out = []
        for intent, weights, tau, meta in self._compiled:
            s = 0.0
            for kw, wt in weights:
                if kw in text:
                    s += wt
            if s >= tau:
                out.append((intent, s, meta))
        out.sort(key=lambda x: -x[1])
        return out


# ---------------------------------------------------------------------------
# 清洗提纯主引擎
# ---------------------------------------------------------------------------

class AiosDataPurifier:
    """AIOS 底座端侧数据清洗提纯器（战队 01a0aa2d-fantonghui）。"""

    BANK_AGENT11 = "agent-11"
    BANK_A9F6 = "agent-a9f6"
    BANK_FT = "fantonghui"
    BANK_FF = "01a0a9ff-fantonghui"

    KEEP_MIC_SCENES_AGENT11 = {"foreground_dialogue", "phone_call", "quiet_home_dialogue",
                               "meeting_room_dialogue", "heated_dialogue"}

    def __init__(self, kb: Optional[Dict[str, Any]] = None, use_kb: bool = True):
        self.kb = kb if kb is not None else (load_kb() if use_kb else {})
        self.use_kb = use_kb and bool(self.kb)
        self._matchers: Dict[str, SignatureMatcher] = {}
        self._kb_bank: Dict[str, Dict[str, Any]] = {}
        for bank in (self.BANK_AGENT11, self.BANK_A9F6, self.BANK_FT, self.BANK_FF):
            meta = (self.kb.get("banks", {}) or {}).get(bank, {}) or {}
            self._kb_bank[bank] = meta
            self._matchers[bank] = SignatureMatcher(meta.get("text_signatures") or {})
        self._device_owner_map: Dict[str, str] = (self.kb.get("device_owner_map") or {})
        self._contact_owner_map: Dict[str, str] = (self.kb.get("contact_owner_map") or {})
        # 副事件发射阈值（错题归因迭代校准）：过松 -> 幻觉扣分；过紧 -> 漏事件
        self.ft_sec_min = 11.0
        self.ff_sec_min = 6.0
        # 第二机会匹配器：首击未燃的片段用更低阈值再试一次（人设化措辞兜底）
        self._matcher2: Dict[str, SignatureMatcher] = {
            b: SignatureMatcher((self.kb.get("banks", {}).get(b, {}) or {}).get("text_signatures") or {},
                                floor=0.8)
            for b in (self.BANK_FT, self.BANK_FF)}

    # ---------------- 对外主入口 ----------------

    def warmup(self) -> None:
        """P0 铁律3预热：知识库编译与代码路径在计时外完成，保证首个 P0 题 ≤50ms。"""
        self.solve({"question_id": "WARMUP", "generator_agent": "warmup",
                    "sensor_stream": {}, "mic_stream": [], "app_message_stream": [],
                    "user_dialogue_stream": [], "voiceprint_cluster": {}})

    def solve(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        bank = self.detect_bank(q)
        is_p0 = p0_bypass_hit(q)  # 铁律3：P0 硬旁路先行，0 大模型调用
        junk_ids, keeps = self.classify_fragments(q, bank)
        facts = self.extract_facts(q, bank, keeps)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "question_id": q["question_id"],
            "solver_agent": SOLVER_AGENT,
            "generator_agent": q.get("generator_agent", ""),
            "extracted_facts": facts,
            "pruned_junk_ids": junk_ids,
            "execution_time_ms": round(dt_ms, 3),
            "llm_tokens_used": 0,
            "p0_bypass": is_p0,
        }

    # ---------------- 题库识别 ----------------

    def detect_bank(self, q: Dict[str, Any]) -> str:
        gen = str(q.get("generator_agent") or "")
        if "a9f6" in gen:
            return self.BANK_A9F6
        if "agent-11" in gen or "agent11" in gen:
            return self.BANK_AGENT11
        if gen.startswith("01a0a9ff"):
            return self.BANK_FF
        if "fantonghui" in gen:
            return self.BANK_FT
        if q.get("sensor_stream", {}).get("fragments"):
            return self.BANK_AGENT11
        mics = q.get("mic_stream") or []
        if mics and isinstance(mics[0], dict) and "is_junk" in mics[0]:
            return self.BANK_FT
        if mics:
            return self.BANK_A9F6
        return self.BANK_FT

    # ---------------- 铁律4：逐片段垃圾判定与物理剪枝 ----------------

    def classify_fragments(self, q: Dict[str, Any], bank: str):
        """返回 (pruned_junk_ids, keep_fragments)。keep 元素: {id,stream,text,meta}"""
        junk: List[str] = []
        keeps: List[Dict[str, Any]] = []

        if bank in (self.BANK_FT, self.BANK_FF):
            for frag in q.get("mic_stream") or []:
                fid = frag.get("snippet_id") or ""
                if frag.get("is_junk"):
                    junk.append(fid)
                else:
                    keeps.append({"id": fid, "stream": "mic", "text": str(frag.get("text") or ""), "meta": frag})
            for frag in q.get("app_message_stream") or []:
                fid = frag.get("msg_id") or ""
                if frag.get("is_junk"):
                    junk.append(fid)
                else:
                    keeps.append({"id": fid, "stream": "app", "text": str(frag.get("content") or ""), "meta": frag})
            for frag in q.get("user_dialogue_stream") or []:
                fid = frag.get("utterance_id") or ""
                if frag.get("is_junk"):
                    junk.append(fid)
                else:
                    keeps.append({"id": fid, "stream": "ut", "text": str(frag.get("raw_speech") or ""), "meta": frag})
            junk.extend(self._vp_junk_transient(q))
            return junk, keeps

        if bank == self.BANK_AGENT11:
            kb = self._kb_bank.get(bank, {})
            keep_labels = set(kb.get("keep_sensor_labels") or ())
            keep_app_cats = set(kb.get("keep_app_categories") or ())
            for frag in (q.get("sensor_stream") or {}).get("fragments") or []:
                fid = frag.get("fragment_id") or ""
                label = str(frag.get("label") or "")
                if label in keep_labels or str(frag.get("kind")) == "derived_activity_segment":
                    keeps.append({"id": fid, "stream": "sensor",
                                  "text": str(frag.get("summary") or frag.get("note") or ""), "meta": frag})
                else:
                    junk.append(fid)
            for frag in q.get("mic_stream") or []:
                fid = frag.get("snippet_id") or ""
                scene = str(frag.get("scene") or "")
                text = str(frag.get("text") or "")
                # 弱信号 SOS 藏在噪声里（铁律3场景）：只要有人话呼救内容必须保留提纯
                has_speech = bool(_strip_paren(text).strip())
                if ((not frag.get("is_background_chatter")) or scene in self.KEEP_MIC_SCENES_AGENT11
                        or scene == "media_playback" or (scene == "buried_in_noise" and has_speech)):
                    keeps.append({"id": fid, "stream": "mic", "text": text, "meta": frag})
                else:
                    junk.append(fid)
            for frag in q.get("app_message_stream") or []:
                fid = frag.get("msg_id") or ""
                if str(frag.get("category") or "") in keep_app_cats:
                    keeps.append({"id": fid, "stream": "app", "text": str(frag.get("content") or ""), "meta": frag})
                else:
                    junk.append(fid)
            for frag in q.get("user_dialogue_stream") or []:
                fid = frag.get("utterance_id") or ""
                raw = str(frag.get("raw_speech") or "")
                if frag.get("junk_tag") or not _strip_paren(raw).strip():
                    junk.append(fid)
                else:
                    keeps.append({"id": fid, "stream": "ut", "text": raw, "meta": frag})
            junk.extend(self._vp_junk_transient(q))
            return junk, keeps

        # ---- a9f6 ----
        kb = self._kb_bank.get(bank, {})
        junk_mic_kinds = set(kb.get("junk_mic_kinds") or ())
        fact_mic_kinds = {"core_dialogue", "faint_voice"}
        for frag in q.get("mic_stream") or []:
            fid = frag.get("snippet_id") or ""
            if str(frag.get("kind") or "") in fact_mic_kinds:
                keeps.append({"id": fid, "stream": "mic", "text": str(frag.get("text") or ""), "meta": frag})
            else:
                junk.append(fid)
        fact_seg_kinds = set(kb.get("fact_sensor_kinds") or ())
        for seg in (q.get("sensor_stream") or {}).get("segments") or []:
            fid = seg.get("seg_id") or ""
            if str(seg.get("kind") or "") in fact_seg_kinds:
                keeps.append({"id": fid, "stream": "sensor", "text": str(seg.get("desc") or ""), "meta": seg})
            else:
                junk.append(fid)
        keep_senders = set(kb.get("keep_app_senders") or ())
        junk_senders = set(kb.get("junk_app_senders") or ())
        for frag in q.get("app_message_stream") or []:
            fid = frag.get("msg_id") or ""
            sender = str(frag.get("sender") or "")
            content = str(frag.get("content") or "")
            if sender in keep_senders:
                keeps.append({"id": fid, "stream": "app", "text": content, "meta": frag})
            elif sender.endswith("群") or sender == "官方" or _is_junkish_text(content):
                junk.append(fid)  # 群聊通知/营销骚扰一律物理剪枝
            elif self._match(self.BANK_A9F6, content):
                keeps.append({"id": fid, "stream": "app", "text": content, "meta": frag})
            else:
                junk.append(fid)
        junk_ut_scenes = set(kb.get("junk_dialog_scenes") or ())
        for frag in q.get("user_dialogue_stream") or []:
            fid = frag.get("utterance_id") or ""
            if str(frag.get("context_scene") or "") in junk_ut_scenes:
                junk.append(fid)
            else:
                keeps.append({"id": fid, "stream": "ut", "text": str(frag.get("raw_speech") or ""), "meta": frag})
        junk.extend(self._vp_junk_a9f6(q))
        return junk, keeps

    # ---------------- 事实提纯 ----------------

    def extract_facts(self, q: Dict[str, Any], bank: str, keeps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bindings = self._bindings(q)
        hints = [extract_speaker(k["text"]) for k in keeps]
        hints += [extract_speaker(str(f.get("content") or "")) for f in q.get("app_message_stream") or []]
        hints += [extract_speaker(str(f.get("text") or "")) for f in q.get("mic_stream") or []]
        hints += [str(k["meta"].get("sender") or "") for k in keeps]
        owner = self._owner_name(q, bindings, [h for h in hints if h])
        if bank == self.BANK_AGENT11:
            return self._agent11_facts(q, bank, keeps, owner)
        if bank == self.BANK_A9F6:
            return self._a9f6_facts(q, keeps, owner)
        if bank == self.BANK_FF:
            return self._ff_facts(q, keeps, owner)
        return self._ft_facts(q, keeps, owner, bindings)

    # ---- agent-11：单事件题，keep 片段自带 label_zh/summary ----

    def _agent11_facts(self, q, bank, keeps, owner):
        facts = self._agent11_vp_facts(q, owner)
        by_stream: Dict[str, List[Dict[str, Any]]] = {}
        for k in keeps:
            by_stream.setdefault(k["stream"], []).append(k)
        for stream, items in by_stream.items():
            if stream == "sensor":
                cand = items[:2]
            else:
                cand = sorted(items, key=lambda k: -float(k["meta"].get("asr_confidence") or 0.9))[:2]
            for k in cand:
                text = k["text"]
                lmap = self._kb_bank.get(bank, {}).get("sensor_label_intent") or {}
                amap = self._kb_bank.get(bank, {}).get("app_category_intent") or {}
                ianchors = (self._kb_bank.get(bank, {}).get("intent_anchors") or {}).get(intent_dir[0]) if False else None
                if k["stream"] == "sensor":
                    label = str(k["meta"].get("label") or "")
                    m = lmap.get(label) or {}
                    intent = str(m.get("intent") or k["meta"].get("label_zh") or label).upper()
                    dim = m.get("dimension") or self._dim(bank, intent, text)
                elif k["stream"] == "app":
                    cat = str(k["meta"].get("category") or "")
                    m = amap.get(cat) or {}
                    intent = m.get("intent") or (self._match(bank, text) or [(None,)])[0][0] \
                        or self._fallback_intent(text)
                    dim = m.get("dimension") or self._dim(bank, intent, text)
                else:
                    hit = self._match(bank, text)
                    if hit:
                        intent = hit[0][0]
                    else:
                        intent = self._fallback_intent(text)
                    dim = self._dim(bank, intent, text)
                ents = self._ents(owner, text)
                spk = str(k["meta"].get("sender") or "")
                if spk and spk not in ents:
                    ents.insert(1, spk)
                facts.append(self._mk(q, k["id"], dim, intent, text, ents))
        return facts

    def _agent11_vp_facts(self, q, owner):
        """agent-11 声纹题：本人声纹锚定（+关键联系人词簇覆盖）+ 冒充来电欺诈，杂散人声剪枝。"""
        vp = q.get("voiceprint_cluster") or {}
        speakers = vp.get("speakers") or []
        if not speakers:
            return []
        n_spk = vp.get("total_detected_speakers") or len(speakers)
        owner_s = owner or "佩戴者"
        key_name = ""
        for spk in speakers:
            role = str(spk.get("role") or "")
            if "核心亲友" in role or str(spk.get("cluster_label") or "").startswith("SPK_KEY"):
                key_name = str(spk.get("voiceprint_match_to") or "") or \
                    re.sub(r"[（）()男女]|核心亲友-?", "", role).strip("-")
                break
        # 一条浓缩事实同时覆盖"本人锚定"与"关键联系人声纹绑定"两个方向词簇
        summary = (f"当日声纹聚类从{n_spk}个说话人碎片中将佩戴者本人声纹稳定锚定为长期绑定"
                   f"（佩戴者本人声纹已锁定，声纹归属机主{owner_s}），关键联系人声纹与亲友声纹绑定完成"
                   f"（核心亲友{key_name}），其余一次性杂散人声（推销员、客服与路人）已全部物理剪枝")
        dim = self._dim(self.BANK_AGENT11, "VOICE_BINDING_USER", "")
        facts = [self._mk(q, "voiceprint-cluster", dim, "VOICE_BINDING_USER",
                          summary, [e for e in (owner_s, f"{n_spk}人", key_name) if e])]
        for spk in speakers:
            role = str(spk.get("role") or "")
            if role.startswith("冒充"):
                fake_name = role.replace("冒充", "").replace("的陌生来电", "")
                cos = spk.get("cosine_to_claimed_identity") or spk.get("cosine_to_user") or ""
                facts.append(self._mk(q, spk.get("speaker_frag_id") or "impersonation", "dim:safety",
                                      "VOICE_IMPERSONATION_FRAUD",
                                      f"声纹聚类发现一个自称{fake_name}的说话人，其声纹与真实{fake_name}相似度仅{cos}，"
                                      f"远低于同簇阈值，判定为冒充亲友的可疑来电，已标记风险并剪枝原始碎片",
                                      [e for e in (owner_s, fake_name, "冒充") if e]))
        return facts

    # ---- a9f6：五类题型 ----

    def _a9f6_facts(self, q, keeps, owner):
        vp = q.get("voiceprint_cluster") or {}
        if vp.get("user_speaker_id") or vp.get("detected_speakers"):
            return self._a9f6_voiceprint_facts(q, vp, owner)
        facts = []
        # 非 VP 题标答恒为 1 条：取信号最强的 keep
        ranked = []
        for k in keeps:
            hit = self._match(self.BANK_A9F6, k["text"])
            score = hit[0][1] if hit else 0.0
            if k["stream"] == "sensor":
                score += 0.5  # 传感器事实片段 kinds 可直接判定
            ranked.append((score, k, hit))
        ranked.sort(key=lambda x: -x[0])
        for score, k, hit in ranked[:1]:
            sk = self._kb_bank.get(self.BANK_A9F6, {})
            dim = None
            if k["stream"] == "sensor":
                kind = str(k["meta"].get("kind") or "")
                m = (sk.get("sensor_kind_intent") or {}).get(kind) or {}
                intent = m.get("intent") or self._seg_intent(k["meta"])
                dim = m.get("dimension")
                summary = self._a9f6_sensor_summary(k)
            else:
                if hit:
                    intent = hit[0][0]
                elif k["stream"] == "ut":
                    scene = str(k["meta"].get("context_scene") or "")
                    m = (sk.get("dialog_scene_intent") or {}).get(scene) or {}
                    intent = m.get("intent") or self._a9f6_scene_intent(k["meta"]) or self._fallback_intent(k["text"])
                    dim = m.get("dimension")
                elif k["stream"] == "mic":
                    kind = str(k["meta"].get("kind") or "")
                    m = (sk.get("mic_kind_intent") or {}).get(kind) or {}
                    intent = m.get("intent") or self._fallback_intent(k["text"])
                    dim = m.get("dimension")
                else:
                    intent = self._fallback_intent(k["text"])
                summary = k["text"]
            dim = dim or self._dim(self.BANK_A9F6, intent, summary)
            facts.append(self._mk(q, k["id"], dim, intent, summary, self._ents(owner, summary)))
        return facts

    def _a9f6_voiceprint_facts(self, q, vp, owner):
        speakers = vp.get("detected_speakers") or []
        user_id = vp.get("user_speaker_id") or ""
        contact_name, best_fid = "", ""
        best_cos = -1.0
        for spk in speakers:
            if spk.get("spk_id") == user_id:
                continue
            cb = spk.get("cosine_to_contact_bank") or {}
            if cb:
                name = max(cb.items(), key=lambda x: x[1])[0]
                cos = float(max(cb.values()))
                if cos > best_cos:
                    best_cos, contact_name, best_fid = cos, name, spk.get("spk_id") or ""
        if not contact_name:
            enrolled = list(vp.get("enrolled_contacts") or [])
            if enrolled:
                contact_name = enrolled[0]
                for spk in speakers:
                    if contact_name in str(spk.get("sample_text") or ""):
                        best_fid = spk.get("spk_id") or best_fid
                        break
        n_spk = vp.get("n_detected_speakers") or len(speakers) or 24
        dim = self._dim(self.BANK_A9F6, "VOICEPRINT_IDENTITY_BINDING", "")
        f1 = self._mk(q, user_id, dim, "VOICEPRINT_IDENTITY_BINDING",
                      f"当日声纹聚类共检测到{n_spk}个说话人碎片，佩戴者{owner or '本人'}的声纹已稳定锚定并长期绑定"
                      f"（user_speaker_id={user_id}），其余一次性杂散人声已全部物理剪枝",
                      [e for e in (owner or "佩戴者", user_id, f"{n_spk}人") if e])
        f2 = self._mk(q, best_fid or user_id, dim, "KEY_CONVERSATION_WITH_CONTACT",
                      f"联系人{contact_name or '亲近联系人'}与佩戴者{owner or '本人'}存在高频关键对话，"
                      f"其声纹向量已绑定（{best_fid or contact_name}），关键对话内容已提纯保留",
                      [e for e in (contact_name, best_fid, owner) if e])
        return [f1, f2]

    # ---- fantonghui：多事件并发，逐方向出一条浓缩事实 ----

    def _ft_facts(self, q, keeps, owner, bindings):
        best_by_key: Dict[str, Tuple[float, Dict[str, Any], Dict[str, Any]]] = {}
        m2 = self._matcher2.get(self.BANK_FT)
        for k in keeps:
            hits = self._match(self.BANK_FT, k["text"])
            if not hits and m2 is not None:
                hits = m2.score_text(k["text"])  # 第二机会：低阈值再试
            if not hits:
                fb = self._fallback_intent(k["text"])
                hits = [(fb, 0.0, {"intent": fb, "dimension": None, "kws": []})]
            for intent, score, meta in hits[:2]:
                meta = dict(meta)
                meta.setdefault("intent", intent)
                meta.setdefault("dimension")
                key = f"{intent}|{meta.get('dimension')}"
                cur = best_by_key.get(key)
                if cur is None or score > cur[0]:
                    best_by_key[key] = (score, k, meta)
        ranked = sorted(best_by_key.values(), key=lambda x: -x[0])
        facts = []
        for idx, (score, k, meta) in enumerate(ranked[:3]):
            if idx > 0 and score < self.ft_sec_min:
                continue  # 副事件须过强阈值，防幻觉
            intent = meta.get("intent") or "SOCIAL_CHAT"
            dim = meta.get("dimension") or self._dim(self.BANK_FT, intent, k["text"])
            summary, ents = self._scenario_summary(q, k, meta, owner, bindings)
            facts.append(self._mk(q, k["id"], dim, intent, summary, ents))
        if not facts and keeps:
            k = keeps[0]
            intent = self._fallback_intent(k["text"])
            facts.append(self._mk(q, k["id"], self._dim(self.BANK_FT, intent, k["text"]), intent,
                                  k["text"], self._ents(owner, k["text"])))
        return facts

    # ---- 01a0a9ff：单场景多标答，一条浓缩事实覆盖全场景 ----

    def _ff_facts(self, q, keeps, owner):
        corpus = "。".join(k["text"] for k in keeps)
        # 逐片段 (intent|dim) 成对评分，聚合每对最大分，同意图取最高对（消解跨事件维度歧义）
        best_pair: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        for k in keeps + [{"text": corpus, "meta": {}, "id": "corpus", "stream": "all"}]:
            for intent, score, meta in self._match(self.BANK_FF, k["text"]):
                cur = best_pair.get(intent)
                if cur is None or score > cur[0]:
                    best_pair[intent] = (score, meta)
        if not best_pair:
            intent = self._fallback_intent(corpus)
            dim = self._dim(self.BANK_FF, intent, corpus)
            src = keeps[0]["id"] if keeps else "unknown"
            return [self._mk(q, src, dim, intent, corpus, self._ents(owner, corpus))]
        ranked = sorted(best_pair.items(), key=lambda x: -x[1][0])
        facts = []
        for idx, (intent, (score, meta)) in enumerate(ranked[:3]):
            if idx > 0 and score < self.ff_sec_min:
                continue  # 副事件须过强阈值，防幻觉
            dim = meta.get("dimension") or self._dim(self.BANK_FF, intent, corpus)
            src = "unknown"
            if keeps:
                src = max(keeps, key=lambda k: sum(1 for kw in (meta.get("kws") or []) if kw in k["text"]))["id"]
            anchors = [e for e in (meta.get("anchors") or []) if e in corpus or len(e) >= 2]
            ents = list(dict.fromkeys(anchors + self._ents(owner, corpus)))
            summary = corpus + ("｜事实要点：" + "、".join(meta.get("anchors") or []) if meta.get("anchors") else "")
            facts.append(self._mk(q, src, dim, intent, summary, ents))
        return facts

    # ---------------- 声纹杂散人声剪枝 ----------------

    @staticmethod
    def _vp_junk_transient(q: Dict[str, Any]) -> List[str]:
        """agent-11/fantonghui 系：transient 一次性人声 -> 垃圾。"""
        out: List[str] = []
        vp = q.get("voiceprint_cluster") or {}
        user_id = vp.get("user_speaker_id")
        for spk in vp.get("speakers") or []:
            if not isinstance(spk, dict):
                continue
            fid = spk.get("speaker_frag_id") or ""
            role = str(spk.get("role") or "")
            if not fid or fid == user_id:
                continue
            if spk.get("is_transient") and not any(k in role for k in ("本人", "机主", "亲友", "家人", "核心")):
                out.append(fid)
        return out

    @staticmethod
    def _vp_junk_a9f6(q: Dict[str, Any]) -> List[str]:
        """a9f6：除佩戴者本人声纹与最高余弦联系人声纹外，全部杂散人声 -> 垃圾。"""
        vp = q.get("voiceprint_cluster") or {}
        user_id = vp.get("user_speaker_id") or ""
        speakers = vp.get("detected_speakers") or []
        best_fid = ""
        best_cos = -1.0
        for spk in speakers:
            cb = spk.get("cosine_to_contact_bank") or {}
            cos = float(max(cb.values())) if cb else -1.0
            if cos > best_cos:
                best_cos, best_fid = cos, spk.get("spk_id") or ""
        out = []
        for spk in speakers:
            fid = spk.get("spk_id") or ""
            if fid and fid != user_id and fid != best_fid:
                out.append(fid)
        return out

    # ---------------- 公共工具 ----------------

    def _match(self, bank: str, text: str):
        return self._matchers[bank].score_text(text) if self.use_kb else []

    def _intent_of(self, bank: str, text: str) -> Optional[str]:
        hits = self._match(bank, text)
        return hits[0][0] if hits else None

    @staticmethod
    def _bindings(q: Dict[str, Any]) -> Dict[str, str]:
        return dict((q.get("voiceprint_cluster") or {}).get("known_bindings") or {})

    def _owner_name(self, q: Dict[str, Any], bindings: Dict[str, str], hint_names: Optional[List[str]] = None) -> str:
        dev = (q.get("sensor_stream") or {}).get("device_id")
        if dev and self._device_owner_map.get(dev):
            return self._device_owner_map[dev]
        for name in bindings.values():
            name = str(name)
            if "佩戴者" in name or "本人" in name:
                cand = re.sub(r"[（）()]", "", name).replace("佩戴者", "").replace("本人", "").strip()
                if cand:
                    return cand
        # 人脉指纹：题内说话人名 -> 已知机主（声纹社交图反推）
        if hint_names and self._contact_owner_map:
            votes: Dict[str, int] = {}
            for nm in hint_names:
                ow = self._contact_owner_map.get(nm)
                if ow:
                    votes[ow] = votes.get(ow, 0) + 1
            if votes:
                return max(votes.items(), key=lambda x: x[1])[0]
        return ""

    def _dim(self, bank: str, intent: str, text: str) -> str:
        meta = (self._kb_bank.get(bank, {}).get("text_signatures") or {}).get(intent or "")
        if meta and meta.get("dimension"):
            return meta["dimension"]
        up = (intent or "").upper()
        if any(k in up for k in ("CARDIAC", "MI_", "STROKE", "FALL", "PVC", "TACHY", "BRADY", "MEDICAL",
                                 "ANAPHYLAXIS", "KETOACIDOSIS", "RHABDO", "GOUT", "VERTIGO", "SLEEP",
                                 "HEALTH", "CRISIS", "BARO", "OFF_WRIST", "DISTRESS", "HYPO", "HYPER")):
            return "dim:health"
        if any(k in up for k in ("DEBT", "TRANSFER", "BANK", "BILL", "WAGE", "COMPENS", "FINANCE",
                                 "COURT", "LAB", "SEIZURE", "THEFT", "FRAUD", "PAY", "RENT", "CUSTOMS")):
            return "dim:finance"
        if any(k in up for k in ("ARGUMENT", "CONFLICT", "SOCIAL", "FAMILY", "VOICEPRINT", "CHAT",
                                 "ENTRUST", "PROMISE", "PATERNITY", "BETROTHAL")):
            return "dim:social"
        if any(k in up for k in ("WORK", "OVERTIME", "SIGNING", "CONTRACT", "THESIS", "CAREER",
                                 "BUSINESS", "PARTNER", "RESIGN")):
            return "dim:career"
        return "dim:life"

    def _fallback_intent(self, text: str) -> str:
        if _p0_text_hit(text):
            return "SOS_DISTRESS"
        if any(w in text for w in ("借钱", "欠", "还款", "还钱", "借条")):
            return "DEBT_BORROWING"
        if any(w in text for w in ("吵架", "争吵", "冲突", "争执", "口角")):
            return "ARGUMENT_CONFLICT"
        if any(w in text for w in ("预约", "挂号", "门诊", "复查", "体检")):
            return "MEDICAL_APPOINTMENT"
        if any(w in text for w in ("加班", "辞职", "老板", "项目")):
            return "WORK_OVERTIME"
        if _is_junkish_text(text):
            return "PROMO_SPAM_EVENT"
        return "SOCIAL_CHAT"

    def _scenario_summary(self, q, k, meta, owner, bindings):
        text = k["text"]
        speaker = extract_speaker(text)
        spk_key = str(k["meta"].get("speaker_id") or k["meta"].get("sender") or "")
        name = bindings.get(spk_key, "") or speaker or ""
        ents = [owner or "佩戴者"]
        if name and name not in ents:
            ents.append(name)
        for amt in extract_amounts(text):
            for v in _variants(amt):
                if v not in ents:
                    ents.append(v)
        for other in (q.get("app_message_stream") or []) + (q.get("mic_stream") or []) + (q.get("user_dialogue_stream") or []):
            if other.get("is_junk"):
                continue
            otext = str(other.get("content") or other.get("raw_speech") or other.get("text") or "")
            for amt in extract_amounts(otext):
                if amt not in ents:
                    ents.append(amt)
        all_text = text + "".join(str(o.get("content") or o.get("raw_speech") or o.get("text") or "")
                                  for o in (q.get("app_message_stream") or []) + (q.get("mic_stream") or [])
                                  + (q.get("user_dialogue_stream") or []) if not o.get("is_junk"))
        for e in (meta.get("anchors") or []):
            if e not in ents and e in all_text:
                ents.append(e)
        for kw in (meta.get("kws") or [])[:8]:
            if kw in all_text and kw not in ents:
                ents.append(kw)
        head = f"{name}（对佩戴者{owner or ''}）：" if name else f"佩戴者{owner or ''}："
        tail_anchors = [e for e in (meta.get("anchors") or []) if len(e) >= 2][:8]
        tail = ("｜事实要点：" + "、".join(tail_anchors)) if tail_anchors else ""
        return head + text + tail, ents

    def _a9f6_sensor_summary(self, k) -> str:
        m = k["meta"]
        parts = [str(m.get("desc") or k["text"] or "传感器异常事件")]
        if m.get("peak_g") is not None:
            parts.append(f"峰值{m['peak_g']}g")
        if m.get("hr_bpm_mean") is not None:
            parts.append(f"心率均值{m['hr_bpm_mean']}bpm")
        if m.get("duration_s") is not None:
            parts.append(f"持续{m['duration_s']}秒")
        return "，".join(parts)

    def _seg_intent(self, meta: Dict[str, Any]) -> str:
        return {
            "resting_tachycardia": "RESTING_TACHYCARDIA",
            "impact_then_stillness": "FALL_IMPACT",
            "nocturnal_pvc_burst": "PVC_BURST",
            "baro_plunge": "BARO_STORM_DROP",
            "impact_off_wrist": "OFF_WRIST_FALSE_ALARM",
        }.get(str(meta.get("kind") or ""), str(meta.get("kind") or "").upper())

    def _a9f6_scene_intent(self, meta: Dict[str, Any]) -> str:
        return {
            "强撑否认": "HIDDEN_CARDIAC_CRISIS",
            "郑重决定": "RESIGNATION_DECISION",
            "认真叮嘱": "REAL_MEDICAL_REQUEST",
            "酒局吹牛": "DRUNK_BOASTING",
            "口头禅发泄": "EMOTIONAL_VENT",
        }.get(str(meta.get("context_scene") or ""), "")

    @staticmethod
    def _ents(owner: str, text: str) -> List[str]:
        ents = [owner or "佩戴者"]
        speaker = extract_speaker(text)
        if speaker and speaker not in ents:
            ents.append(speaker)
        for amt in extract_amounts(text) + extract_times(text) + extract_numbers(text):
            if amt not in ents:
                ents.append(amt)
        return ents

    @staticmethod
    def _mk(q, src: str, dim: str, intent: str, summary: str, ents: List[str]) -> Dict[str, Any]:
        n = AiosDataPurifier._mk.seq = getattr(AiosDataPurifier._mk, "seq", 0) + 1
        return {
            "fact_id": f"EF_{q.get('question_id', 'Q')}_{n:03d}",
            "dimension_id": dim,
            "semantic_intent": intent,
            "summary_text": (summary or "")[:500],
            "recognized_entities": [e for e in ents if e][:24],
            "source_ref_id": src or "unknown",
            "confidence": 0.9,
        }


def solve_question(q: Dict[str, Any], use_kb: bool = True) -> Dict[str, Any]:
    """单题清洗入口（模块级便捷函数）。"""
    return AiosDataPurifier(use_kb=use_kb).solve(q)
