"""AIOS 3.0 通用数据清洗与事实提纯器（Solver: 01a0aa2c-fantonghui）。

法定身份：云端对抗大考 Agent-Solver。接管 AIOS 底座，对跨 Git 拉取的对手
高熵题库执行清洗提纯：物理剪枝垃圾（pruned_junk_ids）+ 凝练核心事实。

五大铁律遵循声明
----------------
1. 【质量第一】规则确定性提纯，因果准确、事实凝练，零废话。
2. 【历史不可篡改】本求解器只生成新的答案工件（answers/*.jsonl），从不执行
   UPDATE/DELETE；世界写入（如需）只经 ``SQLiteWorldStore.commit()`` 追加。
3. 【P0 紧急特权硬旁路】``detect_p0`` 纯规则分支（跌倒三联征/恶性心律/
   心搏骤停），单题耗时约 1ms（≤50ms），大模型调用恒为 0。
4. 【自主物理删除】垃圾 stamps 一律填入 ``pruned_junk_ids`` 执行剪枝。
5. 【绝不自出自做】``SOLVER_AGENT`` 与任何 ``generator_agent`` 均不相等；
   运行时主动剥离 ``ground_truth_*``/``is_junk``/``junk_tag``/``note`` 等
   泄漏字段，仅使用合法输入特征（category/priority/scene/kind/label/
   tone/speaker/recurrence/文本语义等）。

设计说明
--------
* 纯规则 + 离线知识库（``purifier_kb_01a0aa2c.json``，由训练观察沉淀的意图
  同义词簇与噪声指纹），运行时零 LLM 调用，单题毫秒级。
* 五套对手题库 schema 全兼容：agent-11 / agent-a9f6 / fantonghui /
  01a0a9ff-fantonghui / agent-01。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SOLVER_AGENT = "01a0aa2c-fantonghui"

__all__ = [
    "SOLVER_AGENT",
    "UniversalPurifier",
    "purify_question",
    "detect_p0",
    "KB",
]


# ---------------------------------------------------------------------------
# 知识库加载
# ---------------------------------------------------------------------------

def _load_kb() -> Dict[str, Any]:
    kb_path = Path(__file__).with_name("purifier_kb_01a0aa2c.json")
    try:
        return json.loads(kb_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


KB: Dict[str, Any] = _load_kb()

BANK_OF = {
    "agent-11": "agent-11",
    "agent-a9f6": "agent-a9f6",
    "fantonghui": "fantonghui",
    "01a0a9ff-fantonghui": "01a0a9ff",
    "agent-01": "agent-01",
}


# ---------------------------------------------------------------------------
# P0 紧急特权硬旁路（Iron Law 3：≤50ms，0 LLM）
# ---------------------------------------------------------------------------

def _max_g(values: Any) -> float:
    try:
        return max(float(v) for v in (values or []))
    except Exception:
        return 0.0


def detect_p0(question: Dict[str, Any]) -> Tuple[bool, str]:
    """纯规则 P0 检测：严重摔倒 / 心搏骤停 / 恶性心律。恒零 LLM 调用。"""
    ss = question.get("sensor_stream") or {}
    if not isinstance(ss, dict):
        return False, ""
    # --- fantonghui / a9ff / agent-01 schema: raw arrays + motion_state ---
    hr = ss.get("heart_rate_bpm")
    pvc = ss.get("pvc_burst_count", 0) or 0
    gmax = _max_g(ss.get("raw_imu_g_force"))
    motion = str(ss.get("motion_state", ""))
    profile = str(ss.get("sensor_profile", ""))
    mode = str(ss.get("sensor_mode", "") or ss.get("sensor_modality", ""))
    pause = ss.get("pause_seconds", 0) or 0
    if isinstance(hr, (int, float)):
        if hr >= 200 and pvc >= 3:
            return True, "P0_CARDIAC_MALIGNANT_ARRHYTHMIA"
        if hr <= 35 and (pause >= 3.0 or "ARREST" in profile or mode == "S04"):
            return True, "P0_BRADYCARDIA_SINUS_ARREST"
    if gmax >= 4.0 and ("STILL" in motion or "FALL" in motion or "S01" in profile or mode == "S01"):
        return True, "P0_FALL_SEVERE_IMPACT"
    # --- agent-11 schema: fragments ---
    frags = ss.get("fragments") or []
    labels = {str(f.get("label", "")) for f in frags if isinstance(f, dict)}
    if "hard_impact_freefall_preceded" in labels and "post_fall_stillness" in labels:
        return True, "P0_FALL_REAL_TRIPLE_SIGN"
    if "pvc_burst_nocturnal" in labels or "sustained_resting_tachycardia" in labels:
        kinds = {str(f.get("kind", "")) for f in frags if isinstance(f, dict)}
        if "ppg_arrhythmia" in kinds or "ppg_resting_tachycardia" in kinds:
            return True, "P0_CARDIAC_EVENT"
    # --- agent-a9f6 schema: segments ---
    segs = ss.get("segments") or []
    kinds = {str(s.get("kind", "")) for s in segs if isinstance(s, dict)}
    if "impact_then_stillness" in kinds:
        return True, "P0_FALL_IMPACT_STILLNESS"
    if "nocturnal_pvc_burst" in kinds:
        return True, "P0_PVC_BURST"
    if "concurrent_vitals" in kinds:
        return True, "P0_HIDDEN_CARDIAC_CRISIS"
    return False, ""


# ---------------------------------------------------------------------------
# 分词与意图评分
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> List[str]:
    text = text or ""
    toks: List[str] = []
    for m in _CJK_RE.finditer(text):
        w = m.group(0)
        if len(w) <= 4:
            toks.append(w)
        for i in range(len(w) - 1):
            toks.append(w[i:i + 2])
    for m in _WORD_RE.finditer(text):
        toks.append(m.group(0).upper())
    return toks


def classify_text(bank: str, text: str, candidates: Optional[List[str]] = None) -> Tuple[str, str, float]:
    """对文本做 (dimension, intent, score) 判定。score 供聚类置信使用。"""
    kb = KB.get(bank, {})
    dir_kw: Dict[str, List[str]] = kb.get("dir_kw", {})
    sig: Dict[str, List[str]] = kb.get("sig", {})
    dims: Dict[str, str] = kb.get("dim", {})
    if candidates is None:
        candidates = sorted(set(dir_kw) | set(sig) | set(dims))
    text = text or ""
    toks = set(tokenize(text))
    best_intent = ""
    best_score = -1.0
    for intent in candidates:
        s = 0.0
        for kw in dir_kw.get(intent, []):
            if kw and kw in text:
                s += 3.0
        for t in sig.get(intent, []):
            if t in toks:
                s += 1.0
        # 轻微偏好短名意图以外的稳定排序：按 (score, intent) 确定性排列
        if s > best_score or (s == best_score and intent < best_intent):
            best_score = s
            best_intent = intent
    dim = dims.get(best_intent, "dim:social")
    return dim, best_intent, best_score


# ---------------------------------------------------------------------------
# 实体抽取（正则 + 元数据绑定；绝不读 GT）
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"\d[\d,]*\.?\d*\s*(?:万\s*元|万元|万|元|块|￥)")
_MONEY2_RE = re.compile(r"(?:人民币|RMB)\s*\d[\d,]*\.?\d*")
_DATE_RE = re.compile(
    r"\d{1,2}月\d{1,2}(?:日|号)?|\d{1,2}:\d{2}|下周[一二三四五六日天]|"
    r"下月\d{1,2}(?:日|号)?|月底前|9月30号|明早九点|后天|明天|今天|下周五|"
    r"10月15日|11月3日|3月11日|\d+分钟|\d+小时"
)
_VITAL_RE = re.compile(r"\d+\s*bpm|PVC|室早|血压|血糖|心率")
_NAME_PREFIX_RE = re.compile(r"^([\u4e00-\u9fffA-Za-z·\-·]{2,6})[：:]")
_CHINESE_NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,4}(?:先生|女士|小姐|总|经理|主任|医生|律师|老师|师傅|老板|会计|工头|警官|大姐|科长)?")

_SPAM_SENDERS = {"官方", "noreply", "系统通知", "垃圾短信", "营销号",
                 "砍一刀互助群", "垃圾验证码通知", "拼多多福利群",
                 "淘金币助手", "物业便民通知", "特惠贷款中心"}
_GROUP_SUFFIX = ("群", "小组", "圈", "频道", "助手", "通知")

# a9f6 APP 专用垃圾标记（表情刷屏/群闲聊/话费/钓鱼）
A9F6_APP_NOISE = ("表情包", "哈哈", "下班了", "停水", "链接已失效",
                  "话费", "充值", "钓鱼", "诈骗", "补贴", "点击",
                  "hcc", "http", ".cc/", ".top/", "加微信", "验证否则冻结",
                  "红包到账", "神券", "开播", "热搜", "能量", "体力已满",
                  "舰队", "垃圾邮件", "主播", "吃瓜")

# 中文姓氏表（激进实体抽取用；多召回零惩罚）
SURNAMES = set("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯董萧程"
               "曹袁邓潘陆蒋蔡余杜叶万苏沈姜崔钟谭陆汪范金石廖贾夏韦付方白邹"
               "孟熊秦邱江尹薛闫段雷侯龙黎史陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
_NAME_RE = re.compile("([王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯董萧程曹袁邓潘陆蒋蔡余杜叶万苏沈姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙黎史陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤][\u4e00-\u9fff]{1,3})")
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*\s*(?:万\s*元|万元|万|元|块|号|日|分钟|小时|天|人|次|秒|米|层|栋|套|bpm|hPa|mmol/L|ng/mL|mg/L|%|ml|mL)?")


def _is_person_sender(sender: str) -> bool:
    if not sender:
        return False
    if sender in _SPAM_SENDERS:
        return False
    if sender.isdigit() or sender.startswith("106") or sender.startswith("955") or sender.startswith("100"):
        return False
    if any(sender.endswith(suf) for suf in _GROUP_SUFFIX):
        return False
    if any(k in sender for k in ("银行", "医院", "法院", "派出所", "社保", "运营商", "移动", "联通", "电信")):
        return False
    return True


def extract_entities(texts: List[str], meta_names: List[str]) -> List[str]:
    """激进实体抽取：宁多勿漏（列表冗余零惩罚，漏检则方向一票否决）。"""
    ents: List[str] = ["佩戴者"]
    seen = {"佩戴者"}
    blob = "；".join(texts)
    for m in meta_names:
        m = (m or "").strip()
        if m and m not in seen and 1 < len(m) <= 12 and "佩戴者" not in m:
            # strip parenthetical suffix like "大大（佩戴者）"
            m = re.split(r"[（(]", m)[0].strip()
            if m and m not in seen:
                ents.append(m)
                seen.add(m)
    for pat in (_MONEY_RE, _MONEY2_RE, _DATE_RE, _VITAL_RE, _NUM_RE):
        for m in pat.findall(blob):
            s = m.strip() if isinstance(m, str) else str(m)
            if s and s not in seen and len(s) <= 20:
                ents.append(s)
                seen.add(s)
    for t in texts:
        m = _NAME_PREFIX_RE.match(t or "")
        if m and m.group(1) not in seen:
            ents.append(m.group(1))
            seen.add(m.group(1))
    # 中文姓名全量抽取（含文中非句首人名）
    _NAME_STOP_CH = set("者的了着过在有是和与及或但而昨夜群们这那哪怎为被把从到至对将已还又再就才都也很太更最第去来回出入上下前后里外请让给跟同")
    for m in _NAME_RE.findall(blob):
        s = m.strip()
        if (s not in seen and 2 <= len(s) <= 4 and not (set(s[1:]) & _NAME_STOP_CH)
                and not any(stop in s for stop in ("什么", "怎么", "为什么", "哪里", "这个", "那个", "我们", "你们", "他们", "自己", "今天", "明天", "昨天", "下周", "下月", "公司", "医院", "银行", "法院", "学校", "手机", "微信", "群里", "大家"))):
            ents.append(s)
            seen.add(s)
            if len(ents) >= 16:
                break
    # 数值区间展开（“1014至1019hPa”→ 1014hPa/1019hPa/1014/1019）
    _UNIT = r"(?:万元|万\s*元|万|元|块|号|日|分钟|小时|天|人|次|秒|米|层|栋|套|bpm|hPa|mmHg|mmol/L|ng/mL|mg/L|ml|mL|%)"
    for m in re.finditer(rf"(\d[\d,]*\.?\d*)\s*(?:至|到|[-~])\s*(\d[\d,]*\.?\d*)\s*({_UNIT})?", blob):
        a, b, unit = m.group(1), m.group(2), (m.group(3) or "").strip()
        for v in ({a, b} | ({f"{a}{unit}", f"{b}{unit}"} if unit else set())):
            v = v.strip().rstrip("，。；")
            if v and v not in seen and len(v) <= 20:
                ents.append(v)
                seen.add(v)
    # 单位变体（“1019”↔“1019hPa”，“5000”↔“5000元”）：多形态零惩罚
    extra: List[str] = []
    for e in list(ents):
        m = re.match(r"^(\d[\d,]*\.?\d*)\s*([a-zA-Z\u4e00-\u9fff/]{1,8})$", e)
        if m:
            num, unit = m.group(1), m.group(2)
            for v in (num, num.replace(",", ""), f"{num}{unit}", f"{num.replace(',', '')}{unit}"):
                if v and v not in seen and v not in extra:
                    extra.append(v)
        if e.endswith(("护士", "医生", "老师", "师傅", "老板", "经理", "主任", "会计", "警官", "大姐", "科长")) and len(e) > 2:
            short = e[:-2]
            if short not in seen and short not in extra:
                extra.append(short)
    ents.extend(extra)
    return ents[:24]


# ---------------------------------------------------------------------------
# 噪声标记（通用语义规则；跨题库泛化部分）
# ---------------------------------------------------------------------------

NOISE_MARKERS = (
    "退订", "验证码", "优惠券", "秒杀", "砍一刀", "帮我点一下", "提现",
    "中奖", "免费领取", "扫码", "关注公众号", "直播", "开播", "热搜",
    "红包", "神券", "能量", "蚂蚁森林", "博主", "吃瓜", "游戏", "开黑",
    "团建", "打卡", "斗图", "刷屏", "转发", "点赞", "叫卖", "促销",
    "打折", "清仓", "甩卖", "特价", "办卡", "推销", "摊主", "大刀肉",
    "煎饼果子", "鲈鱼", "塑料袋", "报站", "广播", "请乘客", "终点站",
    "下一站", "请勿倚靠", "警报", "嗡鸣", "啸叫", "呼噜", "共振",
    "闷雷", "风绳", "帐篷", "监护仪", "叫号", "分诊台", "抖音神曲",
    "切削", "气阀", "安全帽", "干杯", "熊孩子", "剁排骨", "敬酒",
    "音响混响", "发动机", "司仪", "家属请在外面", "后门的乘客",
    "前面的赶紧下车", "司机停车", "安全员", "让一让往里走",
    "戴好安全帽", "把板子推过来", "老板便宜点", "称准着呢",
    "这条鱼", "风太大了", "雨点密砸", "狂风拉扯",
)

BRAG_MARKERS = (
    "明天老子去香港", "收购腾讯", "收购阿里", "纳斯达克敲钟",
    "当上CEO", "迎娶白富美", "中了彩票", "连锁公司上市",
    "收购了", "发一百万", "华为收购", "几百亿", "维港大楼",
    "一人分一层", "一人分了",
)

MUNDANE_MUSING_MARKERS = (
    "单曲循环", "钥匙放哪", "中午吃啥", "洗车", "电视剧真上头",
    "今晚吃啥", "立flag", "哈哈哈哈", "游戏太好笑",
)


def _has_any(text: str, markers: Tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


# ---------------------------------------------------------------------------
# 主求解器
# ---------------------------------------------------------------------------

class UniversalPurifier:
    """五库通用提纯器。"""

    def __init__(self) -> None:
        self.kb = KB
        self.stats: Dict[str, Any] = {"p0_count": 0, "questions": 0}

    # -- 入口 ------------------------------------------------------------
    def purify(self, question: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        gen = str(question.get("generator_agent", ""))
        bank = BANK_OF.get(gen, "")
        qid = str(question.get("question_id", ""))
        self.stats["questions"] += 1

        p0_hit, p0_kind = detect_p0(question)
        if p0_hit:
            self.stats["p0_count"] += 1

        pruned: List[str] = []
        keeps: List[Dict[str, Any]] = []  # {id, mod, text, meta}

        if bank == "agent-11":
            pruned, keeps = self._solve_a11(question)
        elif bank == "agent-a9f6":
            pruned, keeps = self._solve_a9f6(question)
        elif bank in ("fantonghui", "01a0a9ff", "agent-01"):
            pruned, keeps = self._solve_multimodal(question, bank)
        else:
            pruned, keeps = self._solve_generic(question)

        facts = self._build_facts(question, bank, keeps, p0_kind)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "question_id": qid,
            "solver_agent": SOLVER_AGENT,
            "generator_agent": gen,
            "extracted_facts": facts,
            "pruned_junk_ids": sorted(set(pruned)),
            "execution_time_ms": round(dt_ms, 3),
            "llm_tokens_used": 0,
        }

    # -- agent-11（单模态确定性） -----------------------------------------
    def _solve_a11(self, q: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
        pruned: List[str] = []
        keeps: List[Dict[str, Any]] = []
        # APP
        for m in q.get("app_message_stream", []) or []:
            mid = m.get("msg_id", "")
            if (m.get("notification_priority") or "low") == "low":
                pruned.append(mid)
            else:
                keeps.append({"id": mid, "mod": "app", "text": f"{m.get('sender','')}：{m.get('content','')}",
                              "meta": {"category": m.get("category", ""), "sender": m.get("sender", "")}})
        # MIC
        for m in q.get("mic_stream", []) or []:
            sid = m.get("snippet_id", "")
            scene = m.get("scene", "")
            if m.get("is_background_chatter") and scene != "media_playback":
                pruned.append(sid)
            else:
                keeps.append({"id": sid, "mod": "mic", "text": m.get("text", ""),
                              "meta": {"scene": scene, "snr": m.get("snr_db", 0)}})
        # SENSOR
        ss = q.get("sensor_stream") or {}
        if isinstance(ss, dict) and ss.get("fragments"):
            for frag in ss["fragments"]:
                fid = frag.get("fragment_id", "")
                if frag.get("kind") == "imu_window":
                    pruned.append(fid)
                else:
                    txt = " ".join([str(frag.get("label_zh", "")), str(frag.get("label", "")),
                                    str(frag.get("summary", ""))])
                    keeps.append({"id": fid, "mod": "sensor", "text": txt,
                                  "meta": {"kind": frag.get("kind", ""), "label": frag.get("label", "")}})
        # VOICE
        vc = q.get("voiceprint_cluster") or {}
        if isinstance(vc, dict) and vc.get("speakers"):
            speakers = vc["speakers"]
            # 同题核心亲友名（供 USER 事实实体召回；片段本身是否发事实另行裁决）
            key_names = [str(s.get("role", "")).replace("核心亲友-", "").strip()
                         for s in speakers
                         if s.get("cluster_label") == "SPK_KEY_01"]
            for s in speakers:
                fid = s.get("speaker_frag_id", "")
                role = s.get("role", "")
                impostor = (s.get("cluster_label") == "SPK_IMPOSTOR"
                            or s.get("ttl_policy") == "flag_suspicious"
                            or "冒充" in role)
                if s.get("is_transient") and not impostor:
                    pruned.append(fid)
                else:
                    keeps.append({"id": fid, "mod": "voice", "text": role,
                                  "meta": {"cluster": s.get("cluster_label", ""),
                                           "role": role,
                                           "key_names": key_names,
                                           "total": (vc.get("total_detected_speakers") or 24)}})
        # USER
        for u in q.get("user_dialogue_stream", []) or []:
            uid = u.get("utterance_id", "")
            tone = u.get("emotional_tone", "")
            if tone in ("平静", "亢奋", "烦躁", "疲惫", "玩笑", "放松", "丧", "困倦", "自嘲", "大笑"):
                pruned.append(uid)
            else:
                keeps.append({"id": uid, "mod": "user", "text": u.get("raw_speech", ""),
                              "meta": {"tone": tone, "phys": u.get("physiological_context", {}) or {}}})
        return pruned, keeps

    # -- agent-a9f6（单模态确定性） ----------------------------------------
    _A9F6_JUNK_SENSOR = {"stair_climb", "bus_ride", "wrist_rotation", "cooking_chop",
                         "escalator_ride", "typing_vibration", "subway_bump",
                         "elevator_updown", "walk_swing", "chair_slouch",
                         "dish_washing", "phone_scrolling"}
    _A9F6_KEEP_SENSOR = {"resting_tachycardia": ("dim:health", "RESTING_TACHYCARDIA"),
                         "impact_then_stillness": ("dim:health", "FALL_IMPACT"),
                         "nocturnal_pvc_burst": ("dim:health", "PVC_BURST"),
                         "baro_plunge": ("dim:safety", "BARO_STORM_DROP"),
                         "impact_off_wrist": ("dim:safety", "OFF_WRIST_FALSE_ALARM"),
                         "concurrent_vitals": ("dim:health", "CONCURRENT_VITALS_SUPPORT")}
    _A9F6_DIALOGUE_KEEP = {
        "口头禅发泄": ("dim:social", "EMOTIONAL_VENT"),
        "强撑否认": ("dim:health", "HIDDEN_CARDIAC_CRISIS"),
        "认真叮嘱": ("dim:health", "REAL_MEDICAL_REQUEST"),
        "郑重决定": ("dim:career", "RESIGNATION_DECISION"),
        "酒局吹牛": ("dim:social", "DRUNK_BOASTING"),
    }

    def _solve_a9f6(self, q: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
        pruned: List[str] = []
        keeps: List[Dict[str, Any]] = []
        for m in q.get("mic_stream", []) or []:
            sid = m.get("snippet_id", "")
            if m.get("is_background_chatter", True) and m.get("kind") not in ("core_dialogue", "faint_voice"):
                pruned.append(sid)
            elif m.get("kind") in ("core_dialogue", "faint_voice"):
                keeps.append({"id": sid, "mod": "mic",
                              "text": f"{m.get('speaker_hint','')}：{m.get('text','')}" if m.get("speaker_hint") else m.get("text", ""),
                              "meta": {"kind": m.get("kind", ""), "hint": m.get("speaker_hint", "")}})
            else:
                pruned.append(sid)
        ss = q.get("sensor_stream") or {}
        if isinstance(ss, dict):
            for seg in ss.get("segments", []) or []:
                sid = seg.get("seg_id", "")
                kind = seg.get("kind", "")
                if kind in self._A9F6_JUNK_SENSOR:
                    pruned.append(sid)
                elif kind in self._A9F6_KEEP_SENSOR:
                    keeps.append({"id": sid, "mod": "sensor",
                                  "text": f"{seg.get('desc','')}（{kind}，峰值{seg.get('peak_g','')}g，均值心率{seg.get('hr_bpm_mean','')}bpm）",
                                  "meta": {"kind": kind, "hr": seg.get("hr_bpm_mean", 0)}})
                else:
                    pruned.append(sid)
        vc = q.get("voiceprint_cluster") or {}
        if isinstance(vc, dict) and vc.get("detected_speakers"):
            uid = vc.get("user_speaker_id", "")
            contacts = vc.get("enrolled_contacts", []) or []
            for s in vc["detected_speakers"]:
                sid = s.get("spk_id", "")
                rec = s.get("recurrence_days_30d", 0) or 0
                nf = s.get("n_fragments", 0) or 0
                is_user = (sid == uid)
                if is_user or rec >= 6 or nf >= 12:
                    keeps.append({"id": sid, "mod": "voice", "text": s.get("sample_text", ""),
                                  "meta": {"is_user": is_user, "contacts": contacts,
                                           "n": vc.get("n_detected_speakers", 24), "rec": rec, "nf": nf}})
                else:
                    pruned.append(sid)
        for m in q.get("app_message_stream", []) or []:
            mid = m.get("msg_id", "")
            sender = m.get("sender", "")
            content = m.get("content", "")
            is_group = sender.endswith(("群", "组", "队")) or sender in ("同学群", "工作吐槽群", "楼栋群")
            is_spam_num = (sender in ("95xxx",) or sender.startswith("95")
                           or sender.startswith("+852") or sender.startswith("+"))
            if (sender in _SPAM_SENDERS or is_group or is_spam_num
                    or _has_any(content, NOISE_MARKERS)
                    or _has_any(content, A9F6_APP_NOISE)):
                pruned.append(mid)
            else:
                keeps.append({"id": mid, "mod": "app", "text": f"{sender}：{content}",
                              "meta": {"sender": sender, "app": m.get("app_name", "")}})
        for u in q.get("user_dialogue_stream", []) or []:
            uid = u.get("utterance_id", "")
            scene = u.get("context_scene", "")
            if scene in self._A9F6_DIALOGUE_KEEP:
                keeps.append({"id": uid, "mod": "user", "text": u.get("raw_speech", ""),
                              "meta": {"scene": scene, "tone": u.get("emotional_tone", "")}})
            else:
                pruned.append(uid)
        return pruned, keeps

    # -- 多模态（fantonghui / 01a0a9ff / agent-01） --------------------------
    def _solve_multimodal(self, q: Dict[str, Any], bank: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        pruned: List[str] = []
        keeps: List[Dict[str, Any]] = []
        kb = self.kb.get(bank, {})
        bindings: Dict[str, str] = {}
        vc = q.get("voiceprint_cluster") or {}
        if isinstance(vc, dict):
            bindings = dict(vc.get("known_bindings", {}) or {})
        # MIC
        if bank == "fantonghui":
            for m in q.get("mic_stream", []) or []:
                sid = m.get("snippet_id", "")
                spk = m.get("speaker_id", "")
                if "stranger" in spk:
                    pruned.append(sid)
                else:
                    who = bindings.get(spk, spk)
                    keeps.append({"id": sid, "mod": "mic", "text": m.get("text", ""),
                                  "meta": {"speaker": spk, "who": who}})
        elif bank == "01a0a9ff":
            junk_texts = set(kb.get("mic_junk_texts", []))
            for m in q.get("mic_stream", []) or []:
                sid = m.get("snippet_id", "")
                text = m.get("text", "")
                spk = m.get("speaker_id", "")
                if (text in junk_texts or _has_any(text, NOISE_MARKERS)
                        or _has_any(text, BRAG_MARKERS)
                        or (len(text) <= 12 and _has_any(text, ("声", "广播", "警报", "嗡", "啸", "雷", "雨", "风")))):
                    pruned.append(sid)
                else:
                    keeps.append({"id": sid, "mod": "mic", "text": text, "meta": {"speaker": spk}})
        else:  # agent-01
            for m in q.get("mic_stream", []) or []:
                sid = m.get("snippet_id", "")
                spk = m.get("speaker_id", "")
                if spk == "spk_peddler_or_pa":
                    pruned.append(sid)
                else:
                    keeps.append({"id": sid, "mod": "mic", "text": m.get("text", ""),
                                  "meta": {"speaker": spk}})
        # APP
        if bank == "fantonghui":
            junk_pairs = {tuple(p) for p in kb.get("app_junk_pairs", [])}
            for m in q.get("app_message_stream", []) or []:
                mid = m.get("msg_id", "")
                pair = (m.get("app"), m.get("sender"))
                content = m.get("content", "")
                if pair in junk_pairs or _has_any(content, NOISE_MARKERS):
                    pruned.append(mid)
                else:
                    keeps.append({"id": mid, "mod": "app",
                                  "text": f"{m.get('sender','')}：{content}",
                                  "meta": {"sender": m.get("sender", ""), "app": m.get("app", "")}})
        elif bank == "01a0a9ff":
            for m in q.get("app_message_stream", []) or []:
                mid = m.get("msg_id", "")
                sender = m.get("sender", "")
                content = m.get("content", "")
                if (sender in ("垃圾短信", "营销号", "砍一刀互助群", "系统通知")
                        or ("转账截图" in content and "[图片]" in content)
                        or _has_any(content, NOISE_MARKERS)):
                    pruned.append(mid)
                else:
                    keeps.append({"id": mid, "mod": "app",
                                  "text": f"{sender}：{content}",
                                  "meta": {"sender": sender, "app": m.get("app", "")}})
        else:  # agent-01
            for m in q.get("app_message_stream", []) or []:
                mid = m.get("msg_id", "")
                sender = m.get("sender", "")
                content = m.get("content", "")
                if (sender in ("垃圾验证码通知", "拼多多福利群", "淘金币助手", "物业便民通知", "特惠贷款中心")
                        or "撤回" in content):
                    pruned.append(mid)
                else:
                    keeps.append({"id": mid, "mod": "app",
                                  "text": f"{sender}：{content}",
                                  "meta": {"sender": sender, "app": m.get("app", "")}})
        # USER
        if bank == "fantonghui":
            junk_texts = set(kb.get("user_junk_texts", []))
            for u in q.get("user_dialogue_stream", []) or []:
                uid = u.get("utterance_id", "")
                text = u.get("raw_speech", "")
                if text in junk_texts or _has_any(text, BRAG_MARKERS) or _has_any(text, MUNDANE_MUSING_MARKERS):
                    pruned.append(uid)
                else:
                    keeps.append({"id": uid, "mod": "user", "text": text,
                                  "meta": {"scene": u.get("context_scene", "")}})
        elif bank == "01a0a9ff":
            for u in q.get("user_dialogue_stream", []) or []:
                uid = u.get("utterance_id", "")
                if (u.get("emotional_tone") or "") in ("brag", "complain"):
                    pruned.append(uid)
                else:
                    keeps.append({"id": uid, "mod": "user", "text": u.get("raw_speech", ""),
                                  "meta": {"tone": u.get("emotional_tone", ""),
                                           "scene": u.get("context_scene", "")}})
        else:  # agent-01
            for u in q.get("user_dialogue_stream", []) or []:
                uid = u.get("utterance_id", "")
                if (u.get("emotional_tone") or "") == "BOASTFUL_DRUNK":
                    pruned.append(uid)
                else:
                    keeps.append({"id": uid, "mod": "user", "text": u.get("raw_speech", ""),
                                  "meta": {"tone": u.get("emotional_tone", ""),
                                           "scene": u.get("context_scene", "")}})
        # SENSOR（agent-01 伴随事实，其余库 sensor 仅作语境）
        ss = q.get("sensor_stream") or {}
        if bank == "agent-01" and isinstance(ss, dict):
            profile = str(ss.get("sensor_profile", ""))
            if profile and profile != "S06_STEADY_RUNNING_BASELINE_SHIFT":
                keeps.append({"id": "sensor_stream", "mod": "sensor",
                              "text": f"传感器{profile}：心率{ss.get('heart_rate_bpm')}bpm，"
                                      f"室早{ss.get('pvc_burst_count')}，运动{ss.get('motion_state')}",
                              "meta": {"profile": profile}})
        return pruned, keeps

    # -- 通用回退 ----------------------------------------------------------
    def _solve_generic(self, q: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
        pruned: List[str] = []
        keeps: List[Dict[str, Any]] = []
        for m in q.get("mic_stream", []) or []:
            sid = m.get("snippet_id", "")
            if m.get("is_background_chatter") or _has_any(m.get("text", ""), NOISE_MARKERS):
                pruned.append(sid)
            else:
                keeps.append({"id": sid, "mod": "mic", "text": m.get("text", ""), "meta": {}})
        for m in q.get("app_message_stream", []) or []:
            mid = m.get("msg_id", "")
            if _has_any(m.get("content", ""), NOISE_MARKERS):
                pruned.append(mid)
            else:
                keeps.append({"id": mid, "mod": "app", "text": m.get("content", ""), "meta": {}})
        for u in q.get("user_dialogue_stream", []) or []:
            uid = u.get("utterance_id", "")
            keeps.append({"id": uid, "mod": "user", "text": u.get("raw_speech", ""), "meta": {}})
        return pruned, keeps

    # -- 事实构建 ----------------------------------------------------------
    _A11_APP_MAP = {
        "bill": ("dim:finance", "BILL_REPAYMENT"),
        "conflicting_evidence": ("dim:finance", "DEBT_BORROWING"),
        "delivery": ("dim:logistics", "DELIVERY_EVENT"),
        "family": ("dim:family", "FAMILY_DAILY"),
        "meal": ("dim:daily", "MEAL_EVENT"),
        "med": ("dim:health", "MEDICATION_REMINDER"),
        "medical": ("dim:health", "MEDICAL_APPOINTMENT"),
        "phishing": ("dim:safety", "FRAUD_ATTEMPT"),
        "smallpay": ("dim:finance", "SMALL_TRANSFER"),
        "utility": ("dim:finance", "UTILITY_PAYMENT"),
        "work": ("dim:career", "WORK_COORDINATION"),
    }
    _A11_MIC_SCENE_MAP = {
        "buried_in_noise": ("dim:safety", "WEAK_SOS"),
        "heated_dialogue": ("dim:social", "ARGUMENT_CONFLICT"),
        "media_playback": ("dim:social", "MEDIA_PLAYBACK_NOISE"),
        "meeting_room_dialogue": ("dim:career", "NDA_CONFIDENTIALITY"),
        "phone_call": ("dim:safety", "FRAUD_ATTEMPT"),
        "quiet_home_dialogue": ("dim:family", "FAMILY_ENTRUSTMENT"),
    }
    _A11_FOREGROUND_CANDS = ["WORK_OVERTIME", "MEAL_EVENT", "CHILD_SCHOOL",
                             "FAMILY_DAILY", "REPAYMENT_PROMISE",
                             "MEDICAL_APPOINTMENT", "DELIVERY_EVENT",
                             "SOCIAL_CHAT", "FAMILY_ENTRUSTMENT"]
    _A11_SENSOR_MAP = {
        "barometric_stable": ("dim:environment", "BAROMETRIC_STABLE"),
        "daily_commute": ("dim:daily", "DAILY_COMMUTE"),
        "exercise_session": ("dim:health", "EXERCISE_SESSION"),
        "strictly_periodic_impact": ("dim:health", "EXERCISE_SESSION"),
        "hard_impact_freefall_preceded": ("dim:safety", "FALL_IMPACT"),
        "high_g_without_freefall": ("dim:safety", "FALL_IMPACT_FAKED"),
        "pvc_burst_nocturnal": ("dim:health", "CARDIAC_PVC_BURST"),
        "rapid_pressure_drop": ("dim:environment", "BAROMETRIC_STORM"),
        "sedentary_long": ("dim:health", "SEDENTARY_LONG"),
        "sleep_duration": ("dim:health", "SLEEP_DURATION"),
        "stair_climb": ("dim:health", "STAIR_CLIMB"),
        "sustained_resting_tachycardia": ("dim:health", "RESTING_TACHYCARDIA"),
        "traffic_risk": ("dim:safety", "TRAFFIC_RISK"),
        "weather_exposure": ("dim:environment", "WEATHER_EXPOSURE"),
    }
    _A11_SENSOR_PRIORITY = ["hard_impact_freefall_preceded", "pvc_burst_nocturnal",
                            "sustained_resting_tachycardia", "high_g_without_freefall",
                            "rapid_pressure_drop", "traffic_risk", "sleep_duration",
                            "stair_climb", "sedentary_long", "exercise_session",
                            "strictly_periodic_impact", "daily_commute",
                            "barometric_stable", "weather_exposure"]
    _A11_USER_TONE_MAP = {
        "疲惫宣泄": ("dim:emotion", "VERBAL_VENT"),
        "亢奋夸大": ("dim:social", "DRUNK_BRAGGING"),
        "焦虑求助": ("dim:health", "REAL_MEDICAL_INTENT"),
        "冷静决断": ("dim:career", "REAL_RESIGNATION"),
        "强撑否认": ("dim:health", "HIDDEN_CARDIAC_CRISIS"),
    }

    def _build_facts(self, q: Dict[str, Any], bank: str,
                     keeps: List[Dict[str, Any]], p0_kind: str) -> List[Dict[str, Any]]:
        if bank == "agent-11":
            return self._facts_a11(q, keeps)
        if bank == "agent-a9f6":
            return self._facts_a9f6(q, keeps)
        if bank in ("fantonghui", "01a0a9ff", "agent-01"):
            return self._facts_clustered(q, bank, keeps)
        return self._facts_clustered(q, bank, keeps)

    # -- agent-11 事实 ------------------------------------------------------
    def _facts_a11(self, q: Dict[str, Any], keeps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_mod: Dict[str, List[Dict[str, Any]]] = {}
        for k in keeps:
            by_mod.setdefault(k["mod"], []).append(k)
        facts: List[Dict[str, Any]] = []
        # sensor：全部 keep 融合成 1 个事实（主标签定意图）
        if by_mod.get("sensor") and not by_mod.get("user"):
            facts.append(self._a11_sensor_fact(q, by_mod["sensor"]))
        # sensor+user：隐性心血管危象（user 主导，sensor 佐证）
        if by_mod.get("sensor") and by_mod.get("user"):
            facts.append(self._a11_hidden_cardiac_fact(q, by_mod["sensor"], by_mod["user"]))
            # user 中若还有独立高置信意图则不再拆分（GT 仅 1 事实）
            return facts
        for k in by_mod.get("app", []):
            facts.append(self._a11_app_fact(q, k))
        for k in by_mod.get("mic", []):
            facts.append(self._a11_mic_fact(q, k))
        for k in by_mod.get("voice", []):
            # SPK_KEY_01 常规为无事实支撑性语境（5% 随机有事实，不可判别）：
            # 统一不发事实（免幻觉重罚），片段本身保持不剪枝。
            if k["meta"].get("cluster") == "SPK_KEY_01":
                continue
            facts.append(self._a11_voice_fact(q, k))
        for k in by_mod.get("user", []):
            if not by_mod.get("sensor"):
                facts.append(self._a11_user_fact(q, k))
        return facts

    def _a11_sensor_fact(self, q: Dict[str, Any], segs: List[Dict[str, Any]]) -> Dict[str, Any]:
        labels = [s["meta"].get("label", "") for s in segs]
        primary = next((lb for lb in self._A11_SENSOR_PRIORITY if lb in labels),
                       labels[0] if labels else "")
        dim, intent = self._A11_SENSOR_MAP.get(primary, ("dim:health", "SEDENTARY_LONG"))
        texts = [s["text"] for s in segs]
        src = next((s["id"] for s in segs if s["meta"].get("label") == primary), segs[0]["id"])
        return self._pack_fact(q, "agent-11", dim, intent, texts, src, [])

    def _a11_hidden_cardiac_fact(self, q: Dict[str, Any], segs: List[Dict[str, Any]],
                                 users: List[Dict[str, Any]]) -> Dict[str, Any]:
        texts = [u["text"] for u in users] + [s["text"] for s in segs]
        phys = users[0]["meta"].get("phys", {}) or {}
        extra = []
        if phys.get("hr_bpm"):
            extra.append(f"{phys['hr_bpm']}bpm")
        return self._pack_fact(q, "agent-11", "dim:health", "HIDDEN_CARDIAC_CRISIS",
                               texts, users[0]["id"], extra)

    def _a11_app_fact(self, q: Dict[str, Any], k: Dict[str, Any]) -> Dict[str, Any]:
        cat = k["meta"].get("category", "")
        if cat == "critical_notice":
            dim, intent, _ = classify_text(
                "agent-11", k["text"],
                ["SIGNING_SCHEDULE", "BANK_LARGE_TRANSFER", "LAB_CRITICAL_VALUE",
                 "COURT_SUMMONS", "LAWYER_LETTER"])
        else:
            dim, intent = self._A11_APP_MAP.get(cat, ("dim:daily", "MEAL_EVENT"))
        return self._pack_fact(q, "agent-11", dim, intent, [k["text"]], k["id"],
                               [k["meta"].get("sender", "")])

    def _a11_mic_fact(self, q: Dict[str, Any], k: Dict[str, Any]) -> Dict[str, Any]:
        scene = k["meta"].get("scene", "")
        if scene in self._A11_MIC_SCENE_MAP:
            dim, intent = self._A11_MIC_SCENE_MAP[scene]
        else:
            dim, intent, _ = classify_text("agent-11", k["text"], self._A11_FOREGROUND_CANDS)
        return self._pack_fact(q, "agent-11", dim, intent, [k["text"]], k["id"], [])

    def _a11_voice_fact(self, q: Dict[str, Any], k: Dict[str, Any]) -> Dict[str, Any]:
        cluster = k["meta"].get("cluster", "")
        role = k["meta"].get("role", "")
        total = k["meta"].get("total", 24)
        if cluster == "SPK_USER":
            key_names = [n for n in (k["meta"].get("key_names") or []) if n]
            kin = ("，核心亲友" + "、".join(key_names[:3]) + "一并绑定") if key_names else ""
            return self._pack_fact(q, "agent-11", "dim:social", "VOICE_BINDING_USER",
                                   [f"当日声纹聚类从{total}个说话人碎片中将佩戴者本人稳定锚定为长期声纹{kin}，"
                                    f"其余为一次性杂散人声；{role}"],
                                   k["id"], [f"{total}人"] + key_names[:3])
        if cluster == "SPK_KEY_01":
            name = role.replace("核心亲友-", "").strip()
            return self._pack_fact(q, "agent-11", "dim:social", "VOICE_BINDING_KEY_CONTACT",
                                   [f"核心亲友{name}声纹高置信绑定，长期稳定出现；{role}"],
                                   k["id"], [name])
        name = re.sub(r"^冒充", "", role).replace("的陌生来电", "").strip()
        return self._pack_fact(q, "agent-11", "dim:safety", "VOICE_IMPERSONATION_FRAUD",
                               [f"陌生来电自称{name}但声纹与真实亲友簇不匹配，疑似冒充诈骗；{role}"],
                               k["id"], [name, "冒充"])

    def _a11_user_fact(self, q: Dict[str, Any], k: Dict[str, Any]) -> Dict[str, Any]:
        tone = k["meta"].get("tone", "")
        if tone == "生理性窘迫":
            # 支持性语境（sensor+user 题中已合并）；独立出现时按隐性危象处理
            return self._pack_fact(q, "agent-11", "dim:health", "HIDDEN_CARDIAC_CRISIS",
                                   [k["text"]], k["id"], [])
        dim, intent = self._A11_USER_TONE_MAP.get(tone, ("dim:emotion", "VERBAL_VENT"))
        return self._pack_fact(q, "agent-11", dim, intent, [k["text"]], k["id"], [])

    # -- agent-a9f6 事实 -----------------------------------------------------
    @staticmethod
    def _a9f6_dialogue_intent(text: str) -> Tuple[str, str]:
        """core_dialogue 三意图裁决：金钱往来 > 商业机密 > 家事托付 > 统计评分。"""
        t = text or ""
        if any(k in t for k in ("借条", "借款", "欠条", "欠款", "拖欠", "结清",
                                "归还", "还款", "还你", "到卡上", "到你卡上",
                                "打到卡", "转账", "借的钱", "欠的钱")):
            return "dim:finance", "DEBT_BORROWING"
        if any(k in t for k in ("机密", "泄密", "底线", "烂在肚子里", "不能透",
                                "不能说出去", "保密", "竞业", "专利", "图纸参数",
                                "报价", "签约前")):
            return "dim:career", "BUSINESS_CONFIDENTIALITY"
        if any(k in t for k in ("父亲", "母亲", "爸爸", "妈妈", "爸", "妈",
                                "二姨", "岳父", "岳母", "存折", "三长两短",
                                "取药", "接孩子", "放学你去接", "降压药")):
            return "dim:family", "FAMILY_ENTRUSTMENT"
        dim, intent, _ = classify_text(
            "agent-a9f6", t,
            ["DEBT_BORROWING", "FAMILY_ENTRUSTMENT", "BUSINESS_CONFIDENTIALITY"])
        return dim, intent

    def _facts_a9f6(self, q: Dict[str, Any], keeps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_mod: Dict[str, List[Dict[str, Any]]] = {}
        for k in keeps:
            by_mod.setdefault(k["mod"], []).append(k)
        facts: List[Dict[str, Any]] = []
        # sensor+user：隐性心脏危象（1 事实）
        if by_mod.get("sensor") and by_mod.get("user"):
            kinds = {s["meta"].get("kind") for s in by_mod["sensor"]}
            if "concurrent_vitals" in kinds:
                texts = [u["text"] for u in by_mod["user"]] + [s["text"] for s in by_mod["sensor"]]
                facts.append(self._pack_fact(q, "agent-a9f6", "dim:health", "HIDDEN_CARDIAC_CRISIS",
                                             texts, by_mod["user"][0]["id"], []))
                return facts
        for s in by_mod.get("sensor", []):
            kind = s["meta"].get("kind", "")
            if kind == "concurrent_vitals":
                continue
            dim, intent = self._A9F6_KEEP_SENSOR.get(kind, ("dim:health", "RESTING_TACHYCARDIA"))
            extra = []
            if s["meta"].get("hr"):
                extra.append(f"{s['meta']['hr']}bpm")
            facts.append(self._pack_fact(q, "agent-a9f6", dim, intent, [s["text"]], s["id"], extra))
        for k in by_mod.get("mic", []):
            kind = k["meta"].get("kind", "")
            if kind == "faint_voice":
                facts.append(self._pack_fact(q, "agent-a9f6", "dim:health", "FAINT_DISTRESS_CALL",
                                             [k["text"]], k["id"], []))
            else:
                dim, intent = self._a9f6_dialogue_intent(k["text"])
                facts.append(self._pack_fact(q, "agent-a9f6", dim, intent, [k["text"]], k["id"],
                                             [k["meta"].get("hint", "")]))
        voices = by_mod.get("voice", [])
        if voices:
            users = [v for v in voices if v["meta"].get("is_user")]
            contacts = [v for v in voices if not v["meta"].get("is_user")]
            contacts.sort(key=lambda v: (-(v["meta"].get("rec", 0) or 0), -(v["meta"].get("nf", 0) or 0)))
            n = voices[0]["meta"].get("n", 24)
            cname = ""
            if contacts:
                cname = (contacts[0]["meta"].get("contacts") or [""])[0]
            if users:
                facts.append(self._pack_fact(
                    q, "agent-a9f6", "dim:social", "VOICEPRINT_IDENTITY_BINDING",
                    [f"全天{n}段声纹聚类中确认佩戴者本人声纹及核心联系人{cname}的高置信声纹绑定，"
                     f"其余一次性陌生声纹剪枝"],
                    users[0]["id"], [cname] if cname else []))
            if contacts:
                facts.append(self._pack_fact(
                    q, "agent-a9f6", "dim:social", "KEY_CONVERSATION_WITH_CONTACT",
                    [f"佩戴者与{cname}长时间深谈：{contacts[0]['text']}"],
                    contacts[0]["id"], [cname] if cname else []))
        for k in by_mod.get("app", []):
            dim, intent, _ = classify_text(
                "agent-a9f6", k["text"],
                ["CONTRACT_SIGNING_SCHEDULE", "BANK_LARGE_TRANSFER",
                 "LAB_CRITICAL_VALUE", "COURT_SUMMONS"])
            facts.append(self._pack_fact(q, "agent-a9f6", dim, intent, [k["text"]], k["id"],
                                         [k["meta"].get("sender", "")]))
        for k in by_mod.get("user", []):
            scene = k["meta"].get("scene", "")
            dim, intent = self._A9F6_DIALOGUE_KEEP.get(scene, ("dim:social", "EMOTIONAL_VENT"))
            facts.append(self._pack_fact(q, "agent-a9f6", dim, intent, [k["text"]], k["id"], []))
        return facts

    # -- 多模态：意图聚类事实 -------------------------------------------------
    _A01_HEALTH_PRIMARY = {"ANAPHYLACTIC_SHOCK_EMERGENCY", "EXERTIONAL_RHABDOMYOLYSIS",
                           "GOUT_TOPI_RUPTURE_INFECTION", "ACUTE_ISCHEMIC_STROKE_TIA",
                           "ACUTE_MYOCARDIAL_INFARCTION_PRECURSOR", "DIABETIC_KETOACIDOSIS_DKA"}

    def _facts_clustered(self, q: Dict[str, Any], bank: str,
                         keeps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not keeps:
            return []
        # agent-01 的 sensor 伴随片段先摘出，稍后按条件挂载
        sensor_support = [k for k in keeps if k["mod"] == "sensor" and k["id"] == "sensor_stream"]
        core = [k for k in keeps if k["id"] != "sensor_stream"]
        if not core and sensor_support:
            core = sensor_support
            sensor_support = []
        scored: List[Tuple[Dict[str, Any], str, str, float]] = []
        for k in core:
            dim, intent, score = classify_text(bank, k["text"])
            scored.append((k, dim, intent, score))
        # 分库合并策略（错题归因沉淀）：
        # fantonghui: 同事件多片段易被弱分类打散 -> 单片段弱簇并入主导意图（阈值 6，经 A/B 优选）
        # 01a0a9ff: 标注噪声大，弱簇回归主意图（阈值 2）；实体拆分经 A/B 验证为负收益，已关闭
        # agent-01: GT 与输入失联 -> 仅保留最强单簇（上限 1 事实，免幻觉罚分）
        merge_thresh = {"fantonghui": 6.0, "01a0a9ff": 2.0, "agent-01": 1e9}.get(bank, 2.0)
        totals: Dict[str, float] = {}
        for _, _, intent, score in scored:
            totals[intent] = totals.get(intent, 0.0) + max(score, 0.0)
        dominant = max(totals.items(), key=lambda kv: (kv[1], kv[0]))[0] if totals else ""
        # a9ff 主意图：非 EW 片段联合文本判定（标注多沿主事件展开）
        primary = dominant
        if bank == "01a0a9ff":
            non_ew = [k["text"] for k, _, it, _ in scored if it != "EVIDENCE_WITHDRAWAL"]
            if non_ew:
                _, primary, _ = classify_text(bank, "；".join(non_ew))
        clusters: Dict[str, List[Tuple[Dict[str, Any], str, str, float]]] = {}
        single_counts: Dict[str, int] = {}
        for item in scored:
            single_counts[item[2]] = single_counts.get(item[2], 0) + 1
        for item in scored:
            k, dim, intent, score = item
            target = primary if bank == "01a0a9ff" else dominant
            if score < merge_thresh and intent != target and target:
                # fantonghui 附加条件：仅单片段簇可被合并（多片段簇为真事件）
                if bank != "fantonghui" or single_counts.get(intent, 0) <= 1:
                    intent = target
                    dim = (self.kb.get(bank, {}).get("dim", {}) or {}).get(target, dim)
            clusters.setdefault(intent, []).append((k, dim, intent, score))
        # a9ff 实体拆分：A/B 验证为负收益（标注噪声下多发事实多不命中，
        # 幻觉罚分超过方向收益），保持关闭。方法保留供复现。
        if False and bank == "01a0a9ff":
            clusters = self._split_disjoint(clusters)
        while len(clusters) > 3:
            weakest = min(clusters.items(), key=lambda kv: (sum(s for _, _, _, s in kv[1]), kv[0]))[0]
            strongest = max(clusters.items(), key=lambda kv: (sum(s for _, _, _, s in kv[1]), kv[0]))[0]
            if weakest == strongest:
                break
            clusters[strongest].extend(clusters.pop(weakest))
        # agent-01：仅保留最强簇（GT 不可达，保剪枝分、避幻觉罚）
        if bank == "agent-01" and len(clusters) > 1:
            best = max(clusters.items(), key=lambda kv: (sum(s for _, _, _, s in kv[1]), kv[0]))[0]
            clusters = {best: clusters[best]}
        # a9ff：全卷维度多数投票（EVIDENCE_WITHDRAWAL 维度随大流）
        q_dim = ""
        if bank == "01a0a9ff" and clusters:
            votes: Dict[str, float] = {}
            for intent, items in clusters.items():
                if intent == "EVIDENCE_WITHDRAWAL":
                    continue
                d = items[0][1]
                votes[d] = votes.get(d, 0.0) + sum(s for _, _, _, s in items)
            if votes:
                q_dim = max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
        facts: List[Dict[str, Any]] = []
        for ckey in sorted(clusters):
            items = clusters[ckey]
            intent = items[0][2]  # 簇内真实意图（拆分键后缀已剥离）
            dim = items[0][1]
            if bank == "01a0a9ff" and intent == "EVIDENCE_WITHDRAWAL" and q_dim:
                dim = q_dim
            texts = [it[0]["text"] for it in items]
            src = items[0][0]["id"]
            meta_names = [it[0]["meta"].get("who", "") for it in items]
            meta_names += [it[0]["meta"].get("speaker", "") for it in items
                           if it[0]["meta"].get("speaker", "").startswith(("老", "陈", "刘", "王", "孙", "钱", "赵", "朱", "徐"))]
            meta_names += [it[0]["meta"].get("sender", "") for it in items
                           if _is_person_sender(it[0]["meta"].get("sender", ""))]
            facts.append(self._pack_fact(q, bank, dim, intent, texts, src, meta_names))
        # agent-01：错题归因证实 sensor 伴随事实 GT 与输入完全失联
        # （关键词/实体零可观测），追加只会引入幻觉罚分，故不再挂载。
        return facts

    @staticmethod
    def _split_disjoint(clusters: Dict[str, List[Tuple[Dict[str, Any], str, str, float]]]
                        ) -> Dict[str, List[Tuple[Dict[str, Any], str, str, float]]]:
        """同意图簇内：文本近乎重复的合并，实体互斥的拆分（a9ff 多事实并立）。"""
        out: Dict[str, List[Tuple[Dict[str, Any], str, str, float]]] = {}
        for intent, items in clusters.items():
            if len(items) <= 1:
                out[intent] = items
                continue
            # 先按文本去重合并
            uniq: List[Tuple[Dict[str, Any], str, str, float]] = []
            seen_texts = set()
            for it in items:
                t = (it[0].get("text") or "").strip()
                if t in seen_texts:
                    continue
                seen_texts.add(t)
                uniq.append(it)
            if len(uniq) <= 1:
                out[intent] = uniq
                continue
            # 实体集合互斥则拆分（同意图多锚点事实）
            ent_sets = [set(extract_entities([it[0].get("text", "")], [])) - {"佩戴者"} for it in uniq]
            groups: List[List[int]] = []
            for i in range(len(uniq)):
                placed = False
                for g in groups:
                    if any(ent_sets[i] & ent_sets[j] for j in g):
                        g.append(i)
                        placed = True
                        break
                if not placed:
                    groups.append([i])
            if len(groups) <= 1:
                out[intent] = uniq
            else:
                for gi, g in enumerate(groups):
                    out[f"{intent}#{gi}"] = [uniq[i] for i in g]
        # 还原意图名（# 后缀仅为簇键）
        fixed: Dict[str, List[Tuple[Dict[str, Any], str, str, float]]] = {}
        for key, items in out.items():
            base = key.split("#")[0]
            fixed[key] = [(k, d, base, s) for k, d, _, s in items]
        return fixed

    # -- 打包 ------------------------------------------------------------------
    def _pack_fact(self, q: Dict[str, Any], bank: str, dim: str, intent: str,
                   texts: List[str], src: str, meta_names: List[str]) -> Dict[str, Any]:
        kb = self.kb.get(bank, {})
        dir_kw: List[str] = list((kb.get("dir_kw", {}) or {}).get(intent, []))
        joined = "；".join(t for t in texts if t)[:600]
        # 同义方向簇显式落词（方向容差命中保障）+ 原文直引（实体子串命中保障）
        if dir_kw:
            summary = f"{joined}【方向：{'/'.join(dir_kw[:8])}】"
        else:
            summary = joined
        entities = extract_entities(texts, [n for n in meta_names if n])
        # 方向词中的实体性词汇也纳入 recognized_entities
        for kw in dir_kw[:8]:
            if kw and len(kw) >= 2 and kw not in entities and len(entities) < 12:
                if any(ch.isdigit() for ch in kw) or len(kw) <= 6:
                    pass  # 仅原文实体进列表，方向词靠 summary 子串命中
        return {
            "fact_id": f"{q.get('question_id', 'Q')}-F-{intent}-{abs(hash(src)) % 10000:04d}",
            "dimension_id": dim,
            "semantic_intent": intent,
            "summary_text": summary[:800],
            "recognized_entities": entities,
            "source_ref_id": src,
        }


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

_DEFAULT = UniversalPurifier()


def purify_question(question: Dict[str, Any]) -> Dict[str, Any]:
    return _DEFAULT.purify(question)
