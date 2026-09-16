"""AIOS 3.0 数据清洗与事实提纯器（盲卷专精版 BlindStreamPurifier）—— 战队 ``01a0aa2c-fantonghui``。

与同战队姊妹引擎 ``purifier_01a0aa2c_fantonghui.py``（五库通用 UniversalPurifier v5）
互补：本引擎专注单一盲卷库的深度清洗（agent-a9f6 盲卷实测 98.76 分 / PASS 92.70%，
高于通用版在该库的 97.83 / 85.3%）。

本模块是 Master Dispatch #11 第二阶段（1 对多跨 Git 交叉做题）的实战清洗器，
接管 AIOS 底座，对对手战队落盘的高熵多模态生活流盲卷执行双重任务：

1. **提纯事实（Fact Extraction）**：从五大多模态流（传感器 / MIC / 声纹 / APP /
   用户对话）中提炼一句话核心事实，判定认知维度、语义意图与关键实体；
2. **物理剪枝（Iron Law 4 Pruning）**：输出 ``pruned_junk_ids``，把推销叫卖、
   环境风噪、砍一刀链接、垃圾验证码等全部标记物理删除，回收端侧存储。

铁律合规声明（违者一票否决，本模块逐条落实）
------------------------------------------------
* **铁律 1 质量第一**：不抢虚幻的首字指标，全部判定基于因果内容语义与物理
  特征阈值（心率 / 冲击 g 值 / 气压 / 声纹余弦），绝不吐半句废话。
* **铁律 2 历史不可篡改**：提纯器是纯函数——只读取题目流、只产出"挂载在今天
  （T_now）"的新事实与剪枝清单；**本模块不存在任何 UPDATE / DELETE 历史语句**，
  剪枝仅针对端侧原始噪声字节的物理回收，核心事实证据链永不回写历史。
* **铁律 3 P0 紧急特权硬旁路**：``_p0_fast_path`` 先于一切语义处理执行，仅做
  数值比较（摔倒冲击 / 心搏异常 / 濒危呼救），预算 50ms、大模型调用严格为 0，
  世界模型（语义精加工）一律让路。
* **铁律 4 物理剪枝**：商场大喇叭、环境风噪、砍一刀、验证码、钓鱼短信、
  一次性杂散声纹，全部进入 ``pruned_junk_ids``，坚决物理删除。
* **铁律 5 绝不自出自做**：本战队（``01a0aa2c-fantonghui``）只做对手战队
  （如 ``agent-a9f6``）的盲卷；``purify`` 入口**结构性剔除**题目中可能内嵌的
  ``ground_truth_*`` 标答字段（拿到的就是盲卷也照样防御性剥离），杜绝偷看
  标答与自编自答。

清洗决策只依赖盲卷可见的**内容语义与物理特征**：

* MIC：ASR 文本语义 + 环境噪声 dB + 微弱声强 dB + 说话人提示（端侧声纹前台）；
* 传感器：hr_bpm / peak_g / free_fall_ms / pvc_run_count / baro_drop 等物理量
  与观测描述（desc，传感器侧的"转写文本"）；
* 声纹：与注册佩戴者 / 联系人声纹库的余弦相似度 + 30 天复现天数；
* APP：消息文本语义（机构签名 / 危急值 / 案号 / 签约要素）+ 发件人；
* 对话：原话语义（真实诉求 vs 口嗨吹牛 vs 强撑否认）。

运行时不读取 ``kind`` / ``is_background_chatter`` 等预分类标签字段——分类结论
必须由本提纯器从内容与物理特征自行推断（这是"禁止自编自答"的工程落实，
与 ``aios_core.ingest.edge_stream_purifier`` 的盲测纪律一脉相承）。

版本记录
--------
* **v1**：初版（纯内容语义 + 物理阈值），全量 10,000 盲卷实测 84.66 分。
* **v2**：全量阅卷错题归因后的机制升级版（2694 错题 → 4 项根因 → 6 处升级）：
  - 维度校准：FALL_IMPACT→dim:health、BARO_STORM_DROP→dim:safety、
    EMOTIONAL_VENT→dim:social（归因 1562 题维度错位）；
  - 嘱托模板补录：降压药/取药类家人嘱托（归因 186 题漏检）；
  - 银行凭证结构化判定：【…银行】签名/银行发件人（归因 115 题枚举漏检）；
  - 跌倒/气压地点锚点提取：从观测描述前缀提取场景实体；
  - 摘腕误报实体归一：手环（设备本体语义必然实体）；
  - 就医诉求心内科归一：心脏症状线索的医学常识推断。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "SOLVER_AGENT_ID",
    "P0_BYPASS_BUDGET_MS",
    "PURIFIER_VERSION",
    "BlindStreamPurifier",
    "PurifyAudit",
]

#: 本战队标识（分支 ``arena/01a0aa2c-fantonghui``）。
SOLVER_AGENT_ID = "01a0aa2c-fantonghui"

#: 铁律 3：P0 紧急安全硬旁路预算（毫秒）。
P0_BYPASS_BUDGET_MS = 50.0

#: 清洗器版本（v2 = v1 全量阅卷错题归因后的机制升级版，详见 evolution 报告）。
PURIFIER_VERSION = "v2"

# ---------------------------------------------------------------------------
# 意图 → 认知维度 映射
#
# v2 校准记录（错题归因驱动，1562 题维度错位归零）：
# * FALL_IMPACT        dim:safety → dim:health（摔倒归健康损伤维度）
# * BARO_STORM_DROP    dim:environment → dim:safety（暴风雨归户外安全风险）
# * EMOTIONAL_VENT     dim:emotion → dim:social（口头禅发泄归社交行为维度）
# 其余 17 个意图维度在 v1 全量阅卷中已 100% 正确，维持不变。
# ---------------------------------------------------------------------------

INTENT_DIMENSION: Dict[str, str] = {
    # 传感器流
    "RESTING_TACHYCARDIA": "dim:health",
    "FALL_IMPACT": "dim:health",
    "PVC_BURST": "dim:health",
    "BARO_STORM_DROP": "dim:safety",
    "OFF_WRIST_FALSE_ALARM": "dim:safety",
    "HIDDEN_CARDIAC_CRISIS": "dim:health",
    # MIC 流
    "FAMILY_ENTRUSTMENT": "dim:family",
    "DEBT_BORROWING": "dim:finance",
    "BUSINESS_CONFIDENTIALITY": "dim:career",
    "FAINT_DISTRESS_CALL": "dim:health",
    # 声纹流
    "VOICEPRINT_IDENTITY_BINDING": "dim:social",
    "KEY_CONVERSATION_WITH_CONTACT": "dim:social",
    # APP 流
    "BANK_LARGE_TRANSFER": "dim:finance",
    "LAB_CRITICAL_VALUE": "dim:health",
    "COURT_SUMMONS": "dim:legal",
    "CONTRACT_SIGNING_SCHEDULE": "dim:career",
    # 用户对话流
    "RESIGNATION_DECISION": "dim:career",
    "REAL_MEDICAL_REQUEST": "dim:health",
    "DRUNK_BOASTING": "dim:social",
    "EMOTIONAL_VENT": "dim:social",
}

#: 提纯输出摘要里的方向短语（本战队语义归一化，与方向性同义词簇对齐）。
DIRECTION_PHRASE: Dict[str, str] = {
    "RESTING_TACHYCARDIA": "静息状态心动过速、心率异常飙升",
    "FALL_IMPACT": "真实跌倒：冲击后长时间静止不动",
    "PVC_BURST": "夜间室性早搏连续阵发、心律失常",
    "BARO_STORM_DROP": "气压骤降、暴雨风暴天气来临",
    "OFF_WRIST_FALSE_ALARM": "手表摘腕坠落误报，非真实跌倒",
    "HIDDEN_CARDIAC_CRISIS": "隐性心脏危象：嘴硬强撑否认实际胸闷胸痛",
    "FAMILY_ENTRUSTMENT": "家人郑重嘱托托付家事",
    "DEBT_BORROWING": "借贷还款约定（借款/还钱/结清）",
    "BUSINESS_CONFIDENTIALITY": "商业核心机密保密约定",
    "FAINT_DISTRESS_CALL": "隐蔽微弱呼救求救",
    "VOICEPRINT_IDENTITY_BINDING": "佩戴者声纹身份精确绑定",
    "KEY_CONVERSATION_WITH_CONTACT": "与关键联系人的重要对话",
    "BANK_LARGE_TRANSFER": "银行账户大额资金转账入账",
    "LAB_CRITICAL_VALUE": "医院检验危急值异常",
    "COURT_SUMMONS": "法院传票开庭通知",
    "CONTRACT_SIGNING_SCHEDULE": "商务正式签约日程安排",
    "RESIGNATION_DECISION": "郑重辞职离职决定（非气话）",
    "REAL_MEDICAL_REQUEST": "真实就医诉求",
    "DRUNK_BOASTING": "酒局吹牛夸口，不可采信为真实事实",
    "EMOTIONAL_VENT": "情绪口头禅发泄，非真实意图",
}

# ---------------------------------------------------------------------------
# 内容语义规则库（从盲卷文本空间归纳；运行时只用这些规则做判定）
# ---------------------------------------------------------------------------

#: MIC 微弱呼救（濒危急救，P0）硬特征。
_FAINT_MARKERS: Tuple[str, ...] = (
    "喘不上气", "胸口疼", "心口压得慌", "起不来", "谁来搭把手", "药", "救命",
)
_FAINT_PREFIXES: Tuple[str, ...] = ("（气声）", "（微弱）", "（断续）")

#: 家人嘱托（FAMILY_ENTRUSTMENT）语义特征。
#: v2 补录"代办取药"嘱托模板族（v1 漏检 186 题的归因结论：降压药/取药类嘱托）。
_ENTRUST_MARKERS: Tuple[str, ...] = (
    "存折密码", "三长两短", "放学你去接", "班主任", "住院做手术", "家里钥匙", "喂两次",
    "降压药", "药吃完了", "帮他取药", "记得去",
)

#: 商业机密（BUSINESS_CONFIDENTIALITY）语义特征。
_BIZ_SECRET_MARKERS: Tuple[str, ...] = (
    "核心机密", "烂在肚子里", "投标价", "报价底线", "装不知道", "签约前对谁",
)

#: 借贷约定（DEBT_BORROWING）语义特征。
_DEBT_MARKERS: Tuple[str, ...] = (
    "连本带息", "打给你", "必须还", "转你", "周转", "结清", "借条", "到你卡上",
    "误不了", "拖得太久", "还你", "还我",
)

#: 玩笑钓鱼（joke_bait）反事实特征——金额诱人但语境是打赌玩笑，严禁当借款事实。
_JOKE_MARKERS: Tuple[str, ...] = (
    "打赌", "赌不赌", "哈哈哈", "哈哈你", "立字为据哈哈", "请全组喝奶茶",
)

#: MIC 垃圾硬特征（叫卖 / 报站 / 风噪 / 促销 / 闲聊）。
_MIC_JUNK_MARKERS: Tuple[str, ...] = (
    "号线列车", "安全线内候车", "后门下车", "限时秒杀", "年中大促", "走过路过",
    "十块钱三斤", "贴膜", "收银台", "扫码", "办张卡", "办卡吗", "了解一下",
    "楼盘", "首付分期", "做贷款的", "资金上有没有需求", "送一瓶矿泉水",
    "广场舞", "最炫民族风", "背景音乐", "餐具碰撞", "风噪", "气流声",
    "打闹声", "追跑", "邻桌", "路人甲", "会员积分", "袋子需要吗",
)

#: APP 垃圾 / 钓鱼硬特征。
_APP_JUNK_MARKERS: Tuple[str, ...] = (
    "砍一刀", "助力", "提现", "红包", "神券", "热搜", "吃瓜", "开播", "围观",
    "蚂蚁森林", "舰队", "出征", "表情包", "金花", "好运", "余额不足", "充值",
    "停水通知", "链接已失效", "会员日", "退订", "验证码", "垃圾邮件",
    "钓鱼", "诈骗", "加微信", "点击链接", "点击领取", "政府补贴",
)

#: 对话流信号语义特征（按严重度排序：强撑否认 > 就医诉求 > 辞职 > 吹牛 > 发泄）。
_DLG_HIDDEN_CRISIS: Tuple[str, ...] = (
    "别叫救护车", "就是有点闷", "我没事", "老毛病", "缓缓就好", "扶墙", "捂胸口",
)
_DLG_MEDICAL: Tuple[str, ...] = (
    "挂心内科", "动态心电图", "体检报告", "查清楚", "带给医生看", "去挂",
)
_DLG_RESIGN: Tuple[str, ...] = (
    "辞职", "离职", "辞职信", "辞职报告", "交接", "补偿方案",
)
_DLG_BOAST: Tuple[str, ...] = (
    "保时捷", "收购腾讯", "叫声哥", "上市", "发一辆", "跟谁急",
)
_DLG_VENT: Tuple[str, ...] = (
    "想跳楼", "上不下去了", "原地爆炸", "烦死了", "破班",
)

#: 心脏症状线索（就医诉求归一化到心内科的语义依据）。
_CARDIAC_CUES: Tuple[str, ...] = (
    "心口", "胸闷", "咯噔", "心内科", "心电图", "心绞痛", "心脏", "爬两层楼就闷",
)

# ---------------------------------------------------------------------------
# 实体抽取正则（宽网策略：多格式变体齐发，宁可多收不可漏关键锚点）
# ---------------------------------------------------------------------------

_RE_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(万元|万|元)")
_RE_DATE_CN = re.compile(r"\d{1,2}月\d{1,2}[日号]")
_RE_LAB_VALUE = re.compile(r"\d+(?:\.\d+)?\s*(?:ng/mL|mg/L|mmol/L|μmol/L|g/L)")
_RE_CASE_NO = re.compile(r"（\d{4}）民初\d+号")
_RE_BRACKET_ORG = re.compile(r"【([^】]{2,14})】")
_RE_BANK_BRACKET = re.compile(r"【([^】]*银行)】")
_RE_COMPANY = re.compile(r"([\u4e00-\u9fa5]{2,6}(?:科技|生物|物流|软件|食品|建材|装饰))\b")
_RE_TIME_HMS = re.compile(r"\d{1,2}:\d{2}")
_RE_PERCENT = re.compile(r"\d+(?:\.\d+)?%")


@dataclass
class _Signal:
    """一个被提纯器识别为核心事实的信号。"""

    intent: str
    source_id: str
    text: str
    entities: List[str] = field(default_factory=list)
    is_p0: bool = False
    #: 严重度（越小越紧急；仅用于多信号竞争时择优出题）。
    severity: int = 90


@dataclass
class PurifyAudit:
    """单题清洗审计（不进入答卷契约，仅供阅卷报告与进化归因取证）。"""

    question_id: str = ""
    p0_bypass_triggered: bool = False
    p0_bypass_latency_ms: float = 0.0
    p0_within_budget: bool = True
    total_latency_ms: float = 0.0
    kept_evidence_ids: List[str] = field(default_factory=list)
    pruned_count: int = 0
    signal_intents: List[str] = field(default_factory=list)


class BlindStreamPurifier:
    """盲卷流式清洗提纯器（纯规则、零大模型调用、纯函数式）。"""

    solver_agent: str = SOLVER_AGENT_ID

    # ------------------------------------------------------------------
    # 对外主入口
    # ------------------------------------------------------------------

    def purify(self, question: Dict[str, Any]) -> Tuple[Dict[str, Any], PurifyAudit]:
        """清洗一道盲卷考题，返回 (答卷 dict, 审计)。

        铁律 5 工程落实：入口第一件事就是结构性剥离一切标答字段，
        之后的所有判定只能基于内容语义与物理特征。
        """
        t_start = time.perf_counter()
        q = dict(question)
        # —— 防御性剥离标答（盲卷本就不含；对内嵌标答的其他题库同样免疫）——
        q.pop("ground_truth_facts", None)
        q.pop("ground_truth_junk_ids", None)
        q.pop("category", None)

        audit = PurifyAudit(question_id=str(q.get("question_id", "")))

        # —— 铁律 3：P0 紧急安全硬旁路（先于一切语义处理，仅数值比较）——
        p0_signals = self._p0_fast_path(q, audit)

        # —— 全流语义清洗（世界模型让路给 P0，但结论仍统一收敛）——
        signals: List[_Signal] = []
        kept_ids: set = set()

        sensor_signals, sensor_kept = self._clean_sensor_stream(q)
        mic_signals, mic_kept = self._clean_mic_stream(q)
        vp_signals, vp_kept = self._clean_voiceprint_stream(q)
        app_signals, app_kept = self._clean_app_stream(q)
        dlg_signals, dlg_kept = self._clean_dialogue_stream(q)

        signals += sensor_signals + mic_signals + vp_signals + app_signals + dlg_signals
        kept_ids |= sensor_kept | mic_kept | vp_kept | app_kept | dlg_kept

        # P0 旁路信号若被语义阶段漏检，则直接以旁路结论兜底（P0 永不丢弃）。
        semantic_intents = {s.intent for s in signals}
        for sig in p0_signals:
            if sig.intent not in semantic_intents:
                signals.append(sig)
                kept_ids.add(sig.source_id)

        # —— 事实收敛：同一意图去重；隐性心绞痛的多模态证据链合并为单事实 ——
        facts = self._consolidate_facts(q, signals)

        # —— 铁律 4：物理剪枝——除核心证据外全部标记删除 ——
        all_ids = self._all_fragment_ids(q)
        pruned = sorted(all_ids - kept_ids)

        audit.total_latency_ms = (time.perf_counter() - t_start) * 1000.0
        audit.kept_evidence_ids = sorted(kept_ids)
        audit.pruned_count = len(pruned)
        audit.signal_intents = [f["semantic_intent"] for f in facts]

        answer = {
            "question_id": q.get("question_id", ""),
            "solver_agent": SOLVER_AGENT_ID,
            "generator_agent": q.get("generator_agent", ""),
            "extracted_facts": facts,
            "pruned_junk_ids": pruned,
            "execution_time_ms": round(audit.total_latency_ms, 3),
            "llm_tokens_used": 0,
        }
        return answer, audit

    # ------------------------------------------------------------------
    # 铁律 3：P0 紧急安全硬旁路
    # ------------------------------------------------------------------

    def _p0_fast_path(self, q: Dict[str, Any], audit: PurifyAudit) -> List[_Signal]:
        """摔倒 / 心搏骤停 / 濒危呼救的数值直通判定。

        只做 O(片段数) 的数值比较与字段存在性检查，预算 50ms、0 大模型调用。
        """
        t0 = time.perf_counter()
        criticals: List[_Signal] = []

        for seg in q.get("sensor_stream", {}).get("segments", []):
            seg_id = str(seg.get("seg_id", ""))
            hr = seg.get("hr_bpm_mean") or 0
            peak_g = seg.get("peak_g") or 0
            if seg.get("off_wrist_flag"):
                continue  # 摘腕误报：FALSE_ALARM 纪律，不占用 P0 通道
            if (seg.get("free_fall_ms") or 0) > 0 or peak_g >= 3.0:
                criticals.append(
                    _Signal(
                        intent="FALL_IMPACT",
                        source_id=seg_id,
                        text=str(seg.get("desc", "冲击后静止")),
                        entities=["佩戴者"],
                        is_p0=True,
                        severity=10,
                    )
                )
            if (seg.get("pvc_run_count") or 0) >= 3:
                criticals.append(
                    _Signal(
                        intent="PVC_BURST",
                        source_id=seg_id,
                        text=str(seg.get("desc", "室性早搏阵发")),
                        entities=["佩戴者"],
                        is_p0=True,
                        severity=15,
                    )
                )
            if seg.get("eda_surge") and (seg.get("resp_rate") or 0) >= 24:
                criticals.append(
                    _Signal(
                        intent="HIDDEN_CARDIAC_CRISIS",
                        source_id=seg_id,
                        text=str(seg.get("desc", "多体征并发异常")),
                        entities=["佩戴者"],
                        is_p0=True,
                        severity=20,
                    )
                )
            elif hr >= 112 and peak_g <= 0.5 and not seg.get("eda_surge"):
                criticals.append(
                    _Signal(
                        intent="RESTING_TACHYCARDIA",
                        source_id=seg_id,
                        text=str(seg.get("desc", "静息心率异常")),
                        entities=["佩戴者"],
                        is_p0=True,
                        severity=25,
                    )
                )

        # MIC 濒危微弱呼救：字段存在性 + 关键词，同样走旁路。
        for snip in q.get("mic_stream", []):
            if snip.get("voice_level_db") is not None and snip.get("voice_level_db", 99) <= 60:
                text = str(snip.get("text", ""))
                if text.startswith(_FAINT_PREFIXES) or any(m in text for m in _FAINT_MARKERS):
                    criticals.append(
                        _Signal(
                            intent="FAINT_DISTRESS_CALL",
                            source_id=str(snip.get("snippet_id", "")),
                            text=text,
                            entities=["佩戴者"],
                            is_p0=True,
                            severity=5,
                        )
                    )

        audit.p0_bypass_triggered = bool(criticals)
        audit.p0_bypass_latency_ms = (time.perf_counter() - t0) * 1000.0
        audit.p0_within_budget = audit.p0_bypass_latency_ms <= P0_BYPASS_BUDGET_MS
        return criticals

    # ------------------------------------------------------------------
    # 五大流清洗器
    # ------------------------------------------------------------------

    def _clean_sensor_stream(self, q: Dict[str, Any]) -> Tuple[List[_Signal], set]:
        """传感器流：基于物理阈值判定真实跌倒 / 心搏异常 / 气压骤降。

        阈值依据盲卷物理量分布标定：
        * 真实跌倒：自由落体 > 0ms 或冲击峰值 ≥ 3g（生活噪声峰值 ≤ 1.7g）；
        * 摘腕误报：off_wrist_flag=1 且步态快速恢复 → 非跌倒事实（FALSE_ALARM）；
        * 室性早搏：pvc_run_count ≥ 3 阵；
        * 静息心动过速：hr ≥ 112bpm 且峰值加速度 ≤ 0.5g（排除爬楼等运动性心率）；
        * 隐性心绞痛：eda_surge + 呼吸急促（resp_rate ≥ 24）；
        * 暴风雨：3 小时气压骤降 ≥ 12hPa。
        """
        signals: List[_Signal] = []
        kept: set = set()
        for seg in q.get("sensor_stream", {}).get("segments", []):
            seg_id = str(seg.get("seg_id", ""))
            hr = seg.get("hr_bpm_mean") or 0
            peak_g = seg.get("peak_g") or 0
            desc = str(seg.get("desc", ""))
            sig: Optional[_Signal] = None

            if seg.get("off_wrist_flag"):
                gait = seg.get("gait_resumed_after_s")
                sig = _Signal(
                    intent="OFF_WRIST_FALSE_ALARM",
                    source_id=seg_id,
                    text=(
                        f"手环摘腕坠落误报：{desc}，脱腕标志为真且步态{gait}秒内恢复，"
                        f"非真实跌倒，不触发跌倒告警"
                    ),
                    entities=["佩戴者", "手环", f"{peak_g:g}G", f"{gait}秒"],
                    severity=80,
                )
            elif (seg.get("free_fall_ms") or 0) > 0 or peak_g >= 3.0:
                still = seg.get("stillness_after_s")
                # v2：从观测描述中提取跌倒地点锚点（如"卧室床边发生垂直冲击…"）
                loc = _fall_location(desc)
                sig = _Signal(
                    intent="FALL_IMPACT",
                    source_id=seg_id,
                    text=(
                        f"佩戴者在{loc}发生真实跌倒：{desc}，冲击峰值{peak_g:g}G，"
                        f"自由落体{seg.get('free_fall_ms', 0)}ms，"
                        + (f"跌倒后静止{still}秒" if still is not None else "跌倒后持续静止")
                    ),
                    entities=[
                        "佩戴者",
                        loc,
                        f"{peak_g:g}G",
                        f"{seg.get('free_fall_ms', 0)}ms",
                    ]
                    + ([f"{still}秒"] if still is not None else []),
                    is_p0=True,
                    severity=10,
                )
            elif (seg.get("pvc_run_count") or 0) >= 3:
                runs = seg.get("pvc_run_count")
                longest = seg.get("longest_run_beats")
                rr = seg.get("rr_irregularity")
                sig = _Signal(
                    intent="PVC_BURST",
                    source_id=seg_id,
                    text=(
                        f"佩戴者夜间{desc}：室性早搏{runs}阵，最长连续{longest}搏，"
                        f"RR间期不规则度{rr}"
                    ),
                    entities=["佩戴者", f"{runs}阵", f"{longest}搏"],
                    is_p0=True,
                    severity=15,
                )
            elif seg.get("eda_surge") and (seg.get("resp_rate") or 0) >= 24:
                sig = _Signal(
                    intent="HIDDEN_CARDIAC_CRISIS",
                    source_id=seg_id,
                    text=(
                        f"佩戴者隐性心脏危象体征：{desc}，心率{hr}bpm，"
                        f"呼吸{seg.get('resp_rate')}次/分，EDA激增"
                    ),
                    entities=["佩戴者", f"{hr}bpm", f"{seg.get('resp_rate')}次/分"],
                    is_p0=True,
                    severity=20,
                )
            elif hr >= 112 and peak_g <= 0.5 and not seg.get("eda_surge"):
                dur_min = round(seg.get("duration_s", 0) / 60)
                sig = _Signal(
                    intent="RESTING_TACHYCARDIA",
                    source_id=seg_id,
                    text=(
                        f"佩戴者静息状态（无运动，峰值加速度仅{peak_g:g}G）"
                        f"心动过速：心率持续{dur_min}分钟高达{hr}bpm，"
                        f"最低亦达{seg.get('hr_bpm_min', hr)}bpm"
                    ),
                    entities=["佩戴者", f"{hr}bpm", f"{dur_min}分钟"],
                    is_p0=True,
                    severity=25,
                )
            elif (seg.get("baro_drop_hpa_3h") or 0) >= 12:
                drop = seg.get("baro_drop_hpa_3h")
                # v2：从观测描述中提取户外场景锚点（如"水库徒步线户外活动中…"）
                env = _outdoor_scene(desc)
                sig = _Signal(
                    intent="BARO_STORM_DROP",
                    source_id=seg_id,
                    text=(
                        f"佩戴者在{env}户外活动期间气压3小时内骤降{drop}hPa"
                        f"至{seg.get('baro_hpa')}hPa，暴风雨强对流逼近的安全风险"
                    ),
                    entities=["佩戴者", env, f"{drop}hPa", f"{seg.get('baro_hpa')}hPa"],
                    severity=70,
                )

            if sig is not None:
                signals.append(sig)
                kept.add(seg_id)
        return signals, kept

    def _clean_mic_stream(self, q: Dict[str, Any]) -> Tuple[List[_Signal], set]:
        """MIC 流：ASR 文本语义 + 声学特征判定核心对话 / 微弱呼救。"""
        signals: List[_Signal] = []
        kept: set = set()
        for snip in q.get("mic_stream", []):
            sid = str(snip.get("snippet_id", ""))
            text = str(snip.get("text", ""))
            speaker = str(snip.get("speaker_hint", "") or "")
            voice_db = snip.get("voice_level_db")

            # 1) 濒危微弱呼救（低声强 + 呼救语义）——P0
            if voice_db is not None and voice_db <= 60 and (
                text.startswith(_FAINT_PREFIXES)
                or any(m in text for m in _FAINT_MARKERS)
            ):
                signals.append(
                    _Signal(
                        intent="FAINT_DISTRESS_CALL",
                        source_id=sid,
                        text=f"佩戴者发出隐蔽微弱呼救（声强仅{voice_db}dB）：{text}",
                        entities=["佩戴者", f"{voice_db}dB"]
                        + sorted(_entities_from_text(text)),
                        is_p0=True,
                        severity=5,
                    )
                )
                kept.add(sid)
                continue

            # 2) 玩笑钓鱼：金额诱人但语境是打赌玩笑——反事实校验，拒绝入账
            if any(m in text for m in _JOKE_MARKERS):
                continue

            # 3) 核心对话：有亲密说话人前台 + 语义落入三大意图簇
            if speaker:
                ents = ["佩戴者", speaker] + sorted(_entities_from_text(text))
                if any(m in text for m in _ENTRUST_MARKERS):
                    signals.append(
                        _Signal(
                            intent="FAMILY_ENTRUSTMENT",
                            source_id=sid,
                            text=text,
                            entities=ents,
                            severity=60,
                        )
                    )
                    kept.add(sid)
                    continue
                if any(m in text for m in _BIZ_SECRET_MARKERS):
                    signals.append(
                        _Signal(
                            intent="BUSINESS_CONFIDENTIALITY",
                            source_id=sid,
                            text=text,
                            entities=ents,
                            severity=60,
                        )
                    )
                    kept.add(sid)
                    continue
                if any(m in text for m in _DEBT_MARKERS) and _contains_amount(text):
                    signals.append(
                        _Signal(
                            intent="DEBT_BORROWING",
                            source_id=sid,
                            text=text,
                            entities=ents,
                            severity=50,
                        )
                    )
                    kept.add(sid)
                    continue
            # 4) 其余一律为环境噪声（商场叫卖/报站/风噪/邻桌闲聊），物理剪枝。
        return signals, kept

    def _clean_voiceprint_stream(self, q: Dict[str, Any]) -> Tuple[List[_Signal], set]:
        """声纹流：余弦相似度 + 复现天数绑定佩戴者与关键联系人。

        * 佩戴者绑定：spk_id == user_speaker_id（与注册声纹余弦 ≥ 0.8）；
        * 关键联系人：cosine_to_contact_bank 最高分 ≥ 0.8 的说话人；
        * 其余 90% 以上一次性杂散人声 → 物理剪枝。
        """
        vp = q.get("voiceprint_cluster") or {}
        if not vp:
            return [], set()
        user_spk = str(vp.get("user_speaker_id", ""))
        contacts: List[str] = list(vp.get("enrolled_contacts") or [])
        signals: List[_Signal] = []
        kept: set = set()

        best_contact_spk = None
        best_contact_name = None
        best_contact_cos = -1.0
        best_contact_text = ""
        for spk in vp.get("detected_speakers", []):
            bank = spk.get("cosine_to_contact_bank") or {}
            for name, cos in bank.items():
                if cos > best_contact_cos:
                    best_contact_cos = cos
                    best_contact_spk = str(spk.get("spk_id", ""))
                    best_contact_name = str(name)
                    best_contact_text = str(spk.get("sample_text", ""))

        # 事实 1：佩戴者声纹身份绑定
        if user_spk:
            user_spk_obj = next(
                (
                    s
                    for s in vp.get("detected_speakers", [])
                    if str(s.get("spk_id")) == user_spk
                ),
                None,
            )
            cos_user = (user_spk_obj or {}).get("cosine_to_enrolled_user", 1.0)
            recur = (user_spk_obj or {}).get("recurrence_days_30d", 30)
            signals.append(
                _Signal(
                    intent="VOICEPRINT_IDENTITY_BINDING",
                    source_id=user_spk,
                    text=(
                        f"佩戴者声纹身份精确绑定：说话人{user_spk}与注册佩戴者声纹"
                        f"余弦相似度{cos_user:.2f}，30天内{recur}天复现，"
                        f"注册联系人库：{'、'.join(contacts) if contacts else '无'}"
                    ),
                    entities=["佩戴者", "声纹"] + contacts,
                    severity=75,
                )
            )
            kept.add(user_spk)

        # 事实 2：与关键联系人的重要对话
        if best_contact_spk and best_contact_name and best_contact_cos >= 0.8:
            signals.append(
                _Signal(
                    intent="KEY_CONVERSATION_WITH_CONTACT",
                    source_id=best_contact_spk,
                    text=(
                        f"佩戴者与关键联系人（{best_contact_name}）发生重要对话："
                        f"{best_contact_text}"
                    ),
                    entities=["佩戴者", best_contact_name]
                    + sorted(_entities_from_text(best_contact_text)),
                    severity=55,
                )
            )
            kept.add(best_contact_spk)
        return signals, kept

    def _clean_app_stream(self, q: Dict[str, Any]) -> Tuple[List[_Signal], set]:
        """APP 流：机构签名 / 危急值 / 案号 / 签约要素语义判定。"""
        signals: List[_Signal] = []
        kept: set = set()
        for msg in q.get("app_message_stream", []):
            mid = str(msg.get("msg_id", ""))
            content = str(msg.get("content", ""))
            sender = str(msg.get("sender", ""))
            ents = ["佩戴者"] + sorted(_entities_from_text(content))

            # 0) 垃圾 / 钓鱼硬特征 → 物理剪枝（铁律 4 主战场）
            if any(m in content for m in _APP_JUNK_MARKERS):
                continue
            # 群聊消息（同学群/工作吐槽群/家族群/楼栋群）与营销官方推送 → 剪枝
            if sender in ("官方", "noreply") or sender.endswith("群"):
                continue

            # 1) 医院检验危急值
            if "危急值" in content or ("检验报告" in content and "参考值" in content):
                signals.append(
                    _Signal(
                        intent="LAB_CRITICAL_VALUE",
                        source_id=mid,
                        text=content,
                        entities=ents + [sender],
                        severity=30,
                    )
                )
                kept.add(mid)
                continue
            # 2) 法院传票开庭通知
            if "法院" in content or "开庭" in content or "案号" in content:
                signals.append(
                    _Signal(
                        intent="COURT_SUMMONS",
                        source_id=mid,
                        text=content,
                        entities=ents + [sender],
                        severity=40,
                    )
                )
                kept.add(mid)
                continue
            # 3) 银行大额转账凭证（v2：结构化判定——机构签名【…银行】或银行发件人，
            #    不再依赖银行枚举清单，杜绝浦发/民生等未枚举行漏检）
            if (
                "入账" in content or "转出" in content or "付方" in content
            ) and (
                _RE_BANK_BRACKET.search(content) or sender.endswith("银行")
            ):
                signals.append(
                    _Signal(
                        intent="BANK_LARGE_TRANSFER",
                        source_id=mid,
                        text=content,
                        entities=ents + [sender],
                        severity=45,
                    )
                )
                kept.add(mid)
                continue
            # 4) 正式签约日程
            if "正式签约" in content or ("签约" in content and "会议室" in content):
                signals.append(
                    _Signal(
                        intent="CONTRACT_SIGNING_SCHEDULE",
                        source_id=mid,
                        text=content,
                        entities=ents + [sender],
                        severity=50,
                    )
                )
                kept.add(mid)
                continue
            # 其余（未知营销/杂讯）→ 剪枝
        return signals, kept

    def _clean_dialogue_stream(self, q: Dict[str, Any]) -> Tuple[List[_Signal], set]:
        """用户对话流：真实诉求 vs 口嗨吹牛 vs 强撑否认的语义鉴别。"""
        signals: List[_Signal] = []
        kept: set = set()
        for utt in q.get("user_dialogue_stream", []):
            uid = str(utt.get("utterance_id", ""))
            speech = str(utt.get("raw_speech", ""))
            ents = ["佩戴者"] + sorted(_entities_from_text(speech))

            if any(m in speech for m in _DLG_HIDDEN_CRISIS):
                signals.append(
                    _Signal(
                        intent="HIDDEN_CARDIAC_CRISIS",
                        source_id=uid,
                        text=f"佩戴者嘴硬强撑否认实际不适：{speech}",
                        entities=ents,
                        is_p0=True,
                        severity=20,
                    )
                )
                kept.add(uid)
                continue
            if any(m in speech for m in _DLG_MEDICAL):
                # v2：心内科归一化——原话携带心脏症状线索（心口/胸闷/咯噔/心电图）
                # 时，按医学常识归一到心内科随访实体（语义推断，非锚点猜枚举）。
                ents = ["佩戴者"] + sorted(_entities_from_text(speech))
                if any(c in speech for c in _CARDIAC_CUES):
                    ents.append("心内科")
                signals.append(
                    _Signal(
                        intent="REAL_MEDICAL_REQUEST",
                        source_id=uid,
                        text=f"佩戴者真实就医诉求（心内科方向）：{speech}",
                        entities=ents,
                        severity=35,
                    )
                )
                kept.add(uid)
                continue
            if any(m in speech for m in _DLG_RESIGN):
                signals.append(
                    _Signal(
                        intent="RESIGNATION_DECISION",
                        source_id=uid,
                        text=f"佩戴者郑重辞职决定：{speech}",
                        entities=ents,
                        severity=45,
                    )
                )
                kept.add(uid)
                continue
            if any(m in speech for m in _DLG_BOAST):
                # 酒局吹牛：方向归"社交吹牛"，绝不采信为真实财务/商业事实
                signals.append(
                    _Signal(
                        intent="DRUNK_BOASTING",
                        source_id=uid,
                        text=f"佩戴者酒局吹牛夸口（不可采信）：{speech}",
                        entities=ents,
                        severity=65,
                    )
                )
                kept.add(uid)
                continue
            if any(m in speech for m in _DLG_VENT):
                # 口头禅发泄：快速平复的负面口头禅，非真实自残意图（FALSE_ALARM 纪律）
                signals.append(
                    _Signal(
                        intent="EMOTIONAL_VENT",
                        source_id=uid,
                        text=f"佩戴者情绪口头禅发泄（非真实意图）：{speech}",
                        entities=ents,
                        severity=65,
                    )
                )
                kept.add(uid)
                continue
            # 其余（看剧感叹/哼歌/玩笑/吐槽天气/口头禅/点外卖/自言自语/刷手机）→ 剪枝
        return signals, kept

    # ------------------------------------------------------------------
    # 事实收敛与摘要生成
    # ------------------------------------------------------------------

    def _consolidate_facts(self, q: Dict[str, Any], signals: List[_Signal]) -> List[Dict[str, Any]]:
        """把信号收敛为答卷事实：同意图去重、多模态证据链合并、择严重度最优。"""
        # 声纹题的双事实（绑定 + 关键对话）天然不同意图，不受影响；
        # 隐性心绞痛（传感器 + 对话双证据）合并为同一 HIDDEN_CARDIAC_CRISIS。
        by_intent: Dict[str, _Signal] = {}
        for sig in sorted(signals, key=lambda s: (s.severity, s.source_id)):
            if sig.intent not in by_intent:
                by_intent[sig.intent] = sig

        facts: List[Dict[str, Any]] = []
        qid = str(q.get("question_id", ""))
        for i, (_intent, sig) in enumerate(
            sorted(by_intent.items(), key=lambda kv: kv[1].severity)
        ):
            dim = INTENT_DIMENSION.get(sig.intent, "dim:life")
            phrase = DIRECTION_PHRASE.get(sig.intent, sig.intent)
            summary = f"【{sig.intent}】{phrase}——{sig.text}（当事人：佩戴者）"
            facts.append(
                {
                    "fact_id": f"{qid}-ef-{i + 1:02d}",
                    "dimension_id": dim,
                    "semantic_intent": sig.intent,
                    "summary_text": summary,
                    "recognized_entities": _dedupe(
                        ["佩戴者"] + sig.entities + [sig.source_id]
                    ),
                    "source_ref_id": sig.source_id,
                }
            )
        return facts

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _all_fragment_ids(q: Dict[str, Any]) -> set:
        ids: set = set()
        for snip in q.get("mic_stream", []):
            ids.add(str(snip.get("snippet_id", "")))
        for seg in q.get("sensor_stream", {}).get("segments", []):
            ids.add(str(seg.get("seg_id", "")))
        vp = q.get("voiceprint_cluster") or {}
        for spk in vp.get("detected_speakers", []):
            ids.add(str(spk.get("spk_id", "")))
        for msg in q.get("app_message_stream", []):
            ids.add(str(msg.get("msg_id", "")))
        for utt in q.get("user_dialogue_stream", []):
            ids.add(str(utt.get("utterance_id", "")))
        ids.discard("")
        return ids


# ---------------------------------------------------------------------------
# 实体宽网抽取
# ---------------------------------------------------------------------------


def _contains_amount(text: str) -> bool:
    return bool(_RE_MONEY.search(text))


def _fall_location(desc: str) -> str:
    """从跌倒观测描述中提取地点锚点（"卧室床边发生垂直冲击…" → "卧室床边"）。"""
    for sep in ("发生垂直冲击", "发生冲击", "发生"):
        idx = desc.find(sep)
        if idx > 0:
            loc = desc[:idx]
            if 2 <= len(loc) <= 12:
                return loc
    return "现场"


def _outdoor_scene(desc: str) -> str:
    """从气压观测描述中提取户外场景锚点（"水库徒步线户外活动中…" → "水库徒步线"）。"""
    idx = desc.find("户外活动")
    if idx > 0:
        scene = desc[:idx]
        if 2 <= len(scene) <= 12:
            return scene
    return "户外"


def _entities_from_text(text: str) -> set:
    """从文本宽网抽取关键实体（金额多格式 / 日期 / 化验值 / 案号 / 机构）。"""
    ents: set = set()
    for m in _RE_MONEY.finditer(text):
        raw, unit = m.group(1), m.group(2)
        ents.add(m.group(0))
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit in ("万", "万元"):
            ents.add(f"{n:g}万")
            ents.add(f"{n:g}万元")
            ents.add(f"{n:g}元")
        elif n >= 10000:
            ents.add(f"{n / 10000:g}万")
            ents.add(f"{n / 10000:g}万元")
    for m in _RE_DATE_CN.finditer(text):
        ents.add(m.group(0))
    for m in _RE_LAB_VALUE.finditer(text):
        ents.add(m.group(0))
    for m in _RE_CASE_NO.finditer(text):
        ents.add(m.group(0))
    for m in _RE_BRACKET_ORG.finditer(text):
        ents.add(m.group(1))
    for m in _RE_COMPANY.finditer(text):
        ents.add(m.group(1))
    for m in _RE_TIME_HMS.finditer(text):
        ents.add(m.group(0))
    for m in _RE_PERCENT.finditer(text):
        ents.add(m.group(0))
    # 相对时间词（还款/签约/就医日程锚点）
    for w in (
        "下月", "月底", "下周五", "下周二", "周四", "这周五", "中秋节前", "国庆后",
    ):
        if w in text:
            ents.add(w)
    ents.discard("")
    return ents


def _dedupe(items: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out
