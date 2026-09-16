"""证据接地行动建议引擎（Evidence-Grounded Advisor，阶段六核心算子）。

宪法依据
--------
* 第四条 / 第五条：帮到什么程度，取决于世界的真实证据；沉默也是帮助；
* 铁律 1（输出质量绝对第一）：宁可多花时间做证据比对，**绝不吐半句劣质废话**；
  "没有证据支撑的建议"必须被拒绝输出，而不是靠语气包装；
* 第二十四条：任何高层结论必须能顺着指针下钻到 EvidenceSet → 原始 Observation；
* 第八十六条之一：一次建议的 Token 预算与证据条数都应可计量。

为什么既有实现不够
------------------
仓库既有的 ``symbiotic_advisor`` 三个 Advisor（生日礼物 / 防诈骗 / 疲劳熔断）返回的是
**硬编码结论 + 硬编码 ObjectRef**：它证明不了"建议来自真实世界检索"，也无法在证据
缺失时自动闭嘴。本引擎反过来：先检索、再判定接地率、接地不足直接拒答（
:class:`AdviceWithheld`），接地充分才产出一条由**真实证据文本**拼装的建议。

质量门（全部可断言）
--------------------
* ``min_evidence``：证据指针数量下限（默认 2）；
* ``max_sentences``：单轮输出句数上限（默认 3，铁律 1）；
* 反爹味词表：命中即拒绝整条建议（不是截断，是重写要求）；
* ``require_pinned_revision``：所有证据指针必须钉死在具体 revision（第 24 条）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.cognition.model_call_meter import ModelCallMeter
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.registry import canonical_model_for_object_type
from aios_core.contracts.time import as_utc
from aios_core.query.search import WorldSearchIndex
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "AdviceGate",
    "AdviceWithheld",
    "EvidenceGroundedAdvisor",
    "GroundedAdvice",
    "Playbook",
    "PLAYBOOKS",
]

_PREACHY_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"保持(一个)?积极(的)?心态"),
    re.compile(r"(建议)?您?(应该|需要)保持"),
    re.compile(r"(第一|第二|第三)[，,：:]"),
    re.compile(r"综上所述"),
    re.compile(r"心理疏导|情绪管理方案|心灵鸡汤"),
    re.compile(r"亲爱的用户"),
)
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])")
_EXCERPT_WRAPPERS = "'\"“”‘’` 	\n"


#: 句末终止符：证据摘录已收尾时不再补句号、也不再加分隔符。
_TERMINALS = "。！？!?"


def _clean_excerpt(text: str) -> str:
    """清洗检索摘录：去掉索引层加的单引号包裹与多余空白。"""

    cleaned = text.strip().strip(_EXCERPT_WRAPPERS)
    return " ".join(cleaned.split())


def _tidy(text: str) -> str:
    """标点卫生：去首部悬空分隔符、折叠重复标点、去尾部悬空分隔符。

    用户读到的每一句都必须像人话：``；银行流水…`` 这种从证据中间截出来的开头，
    以及 ``出资款。。`` 这种拼接产生的双句号，都不允许出现在最终结论里。
    """

    cleaned = text.strip()
    cleaned = cleaned.lstrip("；;，,。！？!? 、\t ")
    cleaned = re.sub(r"[；;]{2,}", "；", cleaned)
    cleaned = re.sub(r"[，,]{2,}", "，", cleaned)
    cleaned = re.sub(r"[。]{2,}", "。", cleaned)
    cleaned = re.sub(r"[！]{2,}", "！", cleaned)
    cleaned = re.sub(r"[？]{2,}", "？", cleaned)
    cleaned = re.sub(r"([。！？!?])[；;，,、]+", r"\1", cleaned)
    cleaned = re.sub(r"[；;，,、]+([。！？!?])", r"\1", cleaned)
    cleaned = re.sub(r"([！？!?])\{1,2}", r"\1", cleaned)
    cleaned = re.sub(r"([。！？!?])[。]+", r"\1", cleaned)
    return cleaned.strip()


def _compose(chain: Sequence[str], *, action: str, max_chars: int) -> str:
    """把证据摘录 + 可执行动作拼成 ≤ max_chars 的一到两句（证据优先保留）。"""

    room = max_chars - len(action) - 1  # 句号 + 动作
    picked: list[str] = []
    used = 0
    for excerpt in chain[:2]:
        remaining = room - used - (1 if picked else 0)  # 分隔符
        if remaining < 8:
            break
        piece = excerpt if len(excerpt) <= remaining else excerpt[: remaining - 1] + "…"
        picked.append(piece)
        used += len(piece) + (1 if len(picked) > 1 else 0)
    if not picked:
        return _tidy(f"{len(chain)} 条相关事实。{action}")
    body = ""
    for piece in picked:
        text = piece.rstrip("；;，,、").strip()
        if not text:
            continue
        if not body:
            body = text
        elif body[-1] in _TERMINALS:
            body += text
        else:
            body += f"；{text}"
    tail = "" if body.endswith(tuple(_TERMINALS)) else "。"
    return _tidy(f"{body}{tail}{action}")


class AdviceGate(BaseModel):
    """建议质量门（数字外置，可被经验提案修订）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_evidence: int = Field(default=2, ge=1)
    max_sentences: int = Field(default=3, ge=1)
    max_chars: int = Field(default=120, ge=16)
    require_pinned_revision: bool = True
    forbid_preachy: bool = True


class AdviceWithheld(BaseModel):
    """拒答回执：证据不足 / 触发质量门时，系统选择沉默并说明原因。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str
    reason: str = Field(min_length=1)
    evidence_found: int = Field(ge=0)
    required_evidence: int = Field(ge=1)
    model_calls: int = Field(ge=0)
    withheld_at: datetime

    @property
    def silent(self) -> bool:
        return True


class GroundedAdvice(BaseModel):
    """一条接地的可执行建议（结论由真实证据文本拼装，指针全部钉死修订号）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str
    conclusion: str = Field(min_length=1)
    action: str = Field(min_length=1)
    evidence_pointers: tuple[ObjectRef, ...] = Field(min_length=1)
    evidence_chain: tuple[str, ...] = ()
    grounding_ratio: float = Field(ge=0.0, le=1.0)
    sentence_count: int = Field(ge=1)
    token_estimate: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    produced_at: datetime

    @model_validator(mode="after")
    def validate_pins(self) -> "GroundedAdvice":
        for ref in self.evidence_pointers:
            if ref.revision is None:
                raise ValueError("every evidence pointer must pin an exact revision")
        if self.sentence_count > 3:
            raise ValueError("daily advice must stay within 3 sentences (铁律 1)")
        return self


def estimate_tokens(text: str) -> int:
    """保守 Token 估算（CJK 字符 1 token，ASCII 连续串 1 token）。"""

    tokens = 0
    run = False
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            if run:
                tokens += 1
                run = False
            tokens += 1
        elif ch.isascii() and ch.isalnum():
            run = True
        else:
            if run:
                tokens += 1
                run = False
    return tokens + (1 if run else 0)


class Playbook(BaseModel):
    """领域对策模板：只定义"怎么应对"（策略），绝不携带任何事实。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1)
    action: str = Field(min_length=1)
    keywords: tuple[str, ...] = Field(min_length=1)
    entity_id: str | None = None
    dimension: str | None = None


#: 内置对策模板（策略层，不含任何具体事实/结论）。
PLAYBOOKS: Mapping[str, Playbook] = {
    "partner_fraud_freezing_funds": Playbook(
        intent="合伙纠纷断粮风险",
        action="先把转账凭证、借据与聊天记录固定下来，再谈下一步的钱怎么走。",
        keywords=("合伙", "借款", "转账", "协议", "法院"),
    ),
    "overtime_arrhythmia_breaker": Playbook(
        intent="通宵加班伴随频发早搏",
        action="今晚别再上第二个版本了，天亮去把心电图做了。",
        keywords=("早搏", "心率", "通宵", "加班", "体检"),
    ),
    "family_thaw_followup": Playbook(
        intent="家庭长期矛盾后的破冰跟进",
        action="趁这口气还在，这个月把回家的日子定下来。",
        keywords=("妈妈", "道歉", "回家", "破冰", "旧事"),
    ),
    "relocation_stabilization": Playbook(
        intent="跨省搬家后的生活重构",
        action="先把社保和医保的接续办完，再谈交朋友的事。",
        keywords=("搬家", "户口", "社保", "租约", "新家"),
    ),
    "chronic_illness_adherence": Playbook(
        intent="慢性病用药与复查依从性",
        action="把药和血糖仪的提醒设成固定时段，复查时间现在就预约。",
        keywords=("医嘱", "血糖", "复查", "化验", "漏服"),
    ),
}


class EvidenceGroundedAdvisor:
    """先检索、后接地、再开口 —— 缺证据就闭嘴的建议引擎。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        index: WorldSearchIndex | None = None,
        gate: AdviceGate | None = None,
        meter: ModelCallMeter | None = None,
    ) -> None:
        self.store = store
        self.gate = gate or AdviceGate()
        self.meter = meter or ModelCallMeter(name="grounded-advisor")
        self.index = index or WorldSearchIndex(store.db_path, store=store)
        self._build_index()

    def _build_index(self) -> int:
        """把投影索引追平世界水位（分批 catch_up，直到零滞后）。"""

        applied = 0
        for _ in range(64):
            if self.index.lag() <= 0:
                break
            applied += self.index.catch_up(max_rows=2_000)
        if self.index.lag() > 0:
            applied += self.index.catch_up(max_rows=100_000)
        return applied

    # ------------------------------------------------------------------

    def advise(
        self,
        *,
        playbook: Playbook | str,
        now: datetime | None = None,
        extra_keywords: Sequence[str] = (),
        limit: int = 8,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> GroundedAdvice | AdviceWithheld:
        """产出（或拒答）一条接地建议。"""

        spec = PLAYBOOKS[playbook] if isinstance(playbook, str) else playbook
        stamp = as_utc(now or datetime.now(UTC), "now")
        keywords = tuple(dict.fromkeys((*spec.keywords, *extra_keywords)))

        # 多facet 并集召回：每个关键词各查一次再合并去重（真实世界里同一件事的
        # 证据往往分散在不同的原话里，交集式召回会把它们全部漏掉）。
        seen: set[str] = set()
        hits: list[Any] = []
        for keyword in keywords:
            page = self.index.search_mind(
                keywords=[keyword],
                dimension=spec.dimension,
                entity_id=spec.entity_id,
                time_range=time_range,
                limit=limit,
            )
            for hit in page.hits:
                if hit.object_id in seen:
                    continue
                seen.add(hit.object_id)
                hits.append(hit)
        hits = hits[:limit]
        pointers: list[ObjectRef] = []
        chain: list[str] = []
        for hit in hits:
            if hit.revision is None or int(hit.revision) < 1:
                raise ValueError(
                    "search projection returned an unpinned hit; evidence pointers must pin revisions"
                )
            pointers.append(ObjectRef(object_id=hit.object_id, revision=int(hit.revision)))
            excerpt = getattr(hit, "excerpt", "") or ""
            if excerpt:
                chain.append(excerpt.strip())

        if len(pointers) < self.gate.min_evidence:
            self.meter.charge(
                "advice_withheld",
                detail=f"{spec.intent}: evidence={len(pointers)}<{self.gate.min_evidence}",
            )
            return AdviceWithheld(
                intent=spec.intent,
                reason=(
                    f"证据不足：仅找到 {len(pointers)} 条相关事实，低于门槛 "
                    f"{self.gate.min_evidence}；宁可不说话，也不吐没有证据的建议。"
                ),
                evidence_found=len(pointers),
                required_evidence=self.gate.min_evidence,
                model_calls=self.meter.total,
                withheld_at=stamp,
            )

        grounding_ratio = min(1.0, len(pointers) / max(1, len(hits)))
        unique_chain: list[str] = []
        for excerpt in chain:
            cleaned = _clean_excerpt(excerpt)
            if cleaned and cleaned not in unique_chain:
                unique_chain.append(cleaned)
        conclusion = _compose(
            unique_chain, action=spec.action, max_chars=self.gate.max_chars
        )
        sentence_count = len([part for part in _SENTENCE_SPLIT.split(conclusion) if part.strip()])

        if self.gate.forbid_preachy:
            for pattern in _PREACHY_PATTERNS:
                if pattern.search(conclusion):
                    self.meter.charge("advice_rejected_preachy", detail=spec.intent)
                    return AdviceWithheld(
                        intent=spec.intent,
                        reason="输出触发反爹味质量门：建议被拒绝，需重写为老友口吻。",
                        evidence_found=len(pointers),
                        required_evidence=self.gate.min_evidence,
                        model_calls=self.meter.total,
                        withheld_at=stamp,
                    )
        if sentence_count > self.gate.max_sentences or len(conclusion) > self.gate.max_chars:
            conclusion = self._compress(conclusion, sentence_count)

        sentence_count = len([part for part in _SENTENCE_SPLIT.split(conclusion) if part.strip()])
        return GroundedAdvice(
            intent=spec.intent,
            conclusion=conclusion,
            action=spec.action,
            evidence_pointers=tuple(pointers),
            evidence_chain=tuple(unique_chain),
            grounding_ratio=grounding_ratio,
            sentence_count=sentence_count,
            token_estimate=estimate_tokens(conclusion),
            confidence=min(0.99, 0.5 + 0.1 * len(pointers)),
            produced_at=stamp,
        )

    # ------------------------------------------------------------------

    def _compress(self, conclusion: str, sentence_count: int) -> str:
        """压缩到 1~3 句、<= max_chars（按句边界裁剪，绝不切碎句子）。"""

        parts = [_tidy(part) for part in _SENTENCE_SPLIT.split(conclusion)]
        parts = [part for part in parts if part]
        if not parts:
            return "这事儿先别急，我这边还缺证据。"
        # 保留“最可执行的一句”（末尾的动作句），再向前尽量拼接证据句；
        # 绝不从中间截断句子，宁可少说一句也不留半句残句。
        kept: list[str] = [parts[-1]]
        for part in reversed(parts[:-1]):
            if len(kept) + 1 > self.gate.max_sentences:
                break
            if len("".join([part, *kept])) > self.gate.max_chars:
                break
            kept.insert(0, part)
        trimmed = _tidy("".join(kept))
        if len(trimmed) > self.gate.max_chars:
            shortened: list[str] = [parts[-1]]
            for part in reversed(parts[:-1]):
                if len("".join([part, *shortened])) > self.gate.max_chars:
                    break
                shortened.insert(0, part)
            trimmed = _tidy("".join(shortened))
        return trimmed

    # ------------------------------------------------------------------

    def verify_grounding(self, advice: GroundedAdvice) -> bool:
        """独立复核：每条证据指针都能在存储里取回（否则建议就是幻觉）。"""

        for ref in advice.evidence_pointers:
            try:
                payload = self.store.get_payload(ref.object_id, revision=ref.revision)
            except Exception:
                return False
            if not payload:
                return False
        return True

    def evidence_objects(self, advice: GroundedAdvice) -> tuple[dict, ...]:
        """把证据指针解引用为真实对象（供报告与看板渲染）。"""

        payloads: list[dict] = []
        for ref in advice.evidence_pointers:
            payloads.append(self.store.get_payload(ref.object_id, revision=ref.revision))
        return tuple(payloads)

    def evidence_object_types(self, advice: GroundedAdvice) -> tuple[str, ...]:
        return tuple(
            sorted({str(payload.get("object_type")) for payload in self.evidence_objects(advice)})
        )

    @staticmethod
    def canonical_models(object_types: Iterable[str]) -> tuple[str, ...]:
        """把 object_type 字符串映射到注册表里的规范模型名（下钻收口用）。"""

        names: list[str] = []
        for value in object_types:
            model = canonical_model_for_object_type(ObjectType(value))
            names.append(model.__name__)
        return tuple(names)
