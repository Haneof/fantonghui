"""M5 evidence-bound symbiotic action advisors.

Advisors never mint evidence identifiers.  Every pointer in an
:class:`ActionableAdvice` is resolved from the caller's repository, pinned to a
revision, and semantically used by a deterministic scenario rule.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import require_aware


class AdviceScenario(StrEnum):
    MOM_BIRTHDAY_GIFT = "mom_birthday_gift"
    FRAUD_PREVENTION = "fraud_prevention"
    HEALTH_FATIGUE_BREAKER = "health_fatigue_breaker"


class EvidenceIntegrityError(ValueError):
    """A pointer is unpinned, missing, conflicting, or not repository-backed."""


class InsufficientEvidenceError(ValueError):
    """The available facts do not support the requested causal conclusion."""


class EvidenceFact(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    ref: ObjectRef
    object_type: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=100_000)
    occurred_at: datetime | None = None
    source_kind: str = Field(default="world_store", min_length=1, max_length=120)
    verified: bool = True

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime | None) -> datetime | None:
        require_aware(value, "occurred_at")
        return value

    @model_validator(mode="after")
    def evidence_must_be_pinned_and_verified(self) -> EvidenceFact:
        if self.ref.revision is None:
            raise ValueError("evidence ObjectRef must pin a revision")
        if not self.verified:
            raise ValueError("evidence fact must be repository-verified")
        return self


class ActionableAdvice(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    scenario: AdviceScenario
    conclusion: str = Field(min_length=1, max_length=1_000)
    evidence_pointers: tuple[ObjectRef, ...] = Field(min_length=1, max_length=8)
    action_steps: tuple[str, ...] = Field(min_length=1, max_length=8)
    alternatives: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    expected_benefit: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def causal_pointers_must_be_pinned_and_unique(self) -> ActionableAdvice:
        identities = []
        for pointer in self.evidence_pointers:
            if pointer.revision is None:
                raise ValueError("all causal evidence pointers must pin revisions")
            identities.append((pointer.object_id, pointer.revision))
        if len(identities) != len(set(identities)):
            raise ValueError("causal evidence pointers must be unique")
        return self


@runtime_checkable
class EvidenceRepository(Protocol):
    def resolve(self, ref: ObjectRef) -> EvidenceFact: ...

    def list_facts(self) -> tuple[EvidenceFact, ...]: ...


class InMemoryEvidenceRepository:
    """Deterministic repository used by Linux simulations and unit tests."""

    def __init__(self, facts: Iterable[EvidenceFact]) -> None:
        self._facts: dict[tuple[str, int], EvidenceFact] = {}
        self._lock = RLock()
        for fact in facts:
            self.add(fact)

    def add(self, fact: EvidenceFact) -> bool:
        normalized = EvidenceFact.model_validate(fact)
        assert normalized.ref.revision is not None
        key = (normalized.ref.object_id, normalized.ref.revision)
        with self._lock:
            previous = self._facts.get(key)
            if previous is not None:
                if previous != normalized:
                    raise EvidenceIntegrityError(
                        f"evidence revision has conflicting content: {key}"
                    )
                return False
            self._facts[key] = normalized
            return True

    def resolve(self, ref: ObjectRef) -> EvidenceFact:
        normalized = _require_pinned(ref)
        assert normalized.revision is not None
        with self._lock:
            fact = self._facts.get((normalized.object_id, normalized.revision))
        if fact is None:
            raise EvidenceIntegrityError(
                f"evidence pointer not found: {normalized.object_id}@{normalized.revision}"
            )
        return fact

    def list_facts(self) -> tuple[EvidenceFact, ...]:
        with self._lock:
            return tuple(
                self._facts[key]
                for key in sorted(self._facts, key=lambda item: (item[0], item[1]))
            )


class WorldEvidenceRepository:
    """Resolve immutable facts from SQLiteWorldStore's public read surface."""

    _TEXT_FIELDS = (
        "content",
        "value",
        "title",
        "description",
        "interpretation",
        "statement",
        "canonical_name",
        "purpose",
        "reinterpretation_claim",
    )

    def __init__(self, store: Any) -> None:
        if not hasattr(store, "get_payload") or not hasattr(store, "list_payloads"):
            raise TypeError("world evidence repository requires a world store")
        self.store = store
        self.db_path = str(getattr(store, "db_path", ""))

    def resolve(self, ref: ObjectRef) -> EvidenceFact:
        normalized = _require_pinned(ref)
        assert normalized.revision is not None
        try:
            payload = self.store.get_payload(
                normalized.object_id,
                revision=normalized.revision,
            )
        except Exception as exc:
            annotation = self._resolve_annotation(normalized)
            if annotation is not None:
                return annotation
            raise EvidenceIntegrityError(
                f"evidence pointer not found: "
                f"{normalized.object_id}@{normalized.revision}"
            ) from exc
        fact = self._from_payload(payload)
        if fact.ref != normalized:
            raise EvidenceIntegrityError("world store returned a different revision")
        return fact

    def list_facts(self) -> tuple[EvidenceFact, ...]:
        from aios_core.contracts.enums import ObjectType

        facts: dict[tuple[str, int], EvidenceFact] = {}
        for object_type in ObjectType:
            try:
                payloads = self.store.list_payloads(object_type=object_type)
            except (AttributeError, TypeError, ValueError):
                continue
            for payload in payloads:
                try:
                    fact = self._from_payload(payload)
                except (EvidenceIntegrityError, TypeError, ValueError):
                    continue
                assert fact.ref.revision is not None
                facts[(fact.ref.object_id, fact.ref.revision)] = fact
        for fact in self._annotation_facts():
            assert fact.ref.revision is not None
            facts[(fact.ref.object_id, fact.ref.revision)] = fact
        return tuple(
            facts[key] for key in sorted(facts, key=lambda item: (item[0], item[1]))
        )

    def _from_payload(self, payload: Mapping[str, Any]) -> EvidenceFact:
        if not isinstance(payload, Mapping):
            raise TypeError("world payload must be a mapping")
        object_id = payload.get("object_id")
        revision = payload.get("revision")
        if not isinstance(object_id, str) or not object_id.strip():
            raise EvidenceIntegrityError("world payload has no object_id")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise EvidenceIntegrityError("world payload has no pinned revision")
        text_parts: list[str] = []
        for field_name in self._TEXT_FIELDS:
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
            elif field_name == "value" and value is not None:
                text_parts.append(
                    json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                )
        if not text_parts:
            raise EvidenceIntegrityError(
                "world payload has no admissible evidence text"
            )
        occurred_at = _payload_time(payload)
        return EvidenceFact(
            ref=ObjectRef(object_id=object_id, revision=revision),
            object_type=str(payload.get("object_type", "unknown")),
            text="；".join(text_parts),
            occurred_at=occurred_at,
            source_kind=str(payload.get("source_kind", "world_store")),
            verified=True,
        )

    def _annotation_facts(self) -> tuple[EvidenceFact, ...]:
        if not self.db_path or not Path(self.db_path).is_file():
            return ()
        try:
            with sqlite3.connect(self.db_path) as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(retrospective_annotations)"
                    )
                }
                required = {
                    "annotation_id",
                    "reinterpretation_claim",
                    "created_at",
                }
                if not required <= columns:
                    return ()
                rows = connection.execute(
                    "SELECT annotation_id, reinterpretation_claim, created_at "
                    "FROM retrospective_annotations"
                ).fetchall()
        except (OSError, sqlite3.DatabaseError):
            return ()
        facts = []
        for annotation_id, text, created_at in rows:
            try:
                facts.append(
                    EvidenceFact(
                        ref=ObjectRef(object_id=str(annotation_id), revision=1),
                        object_type="annotation",
                        text=str(text),
                        occurred_at=_parse_time(created_at),
                        source_kind="retrospective_annotation",
                    )
                )
            except (TypeError, ValueError):
                continue
        return tuple(facts)

    def _resolve_annotation(self, ref: ObjectRef) -> EvidenceFact | None:
        return next(
            (fact for fact in self._annotation_facts() if fact.ref == ref),
            None,
        )


class _EvidenceBoundAdvisor:
    def __init__(
        self,
        evidence_source: EvidenceRepository
        | Iterable[EvidenceFact]
        | Any
        | None = None,
    ) -> None:
        if evidence_source is None:
            self.repository: EvidenceRepository | None = None
        elif isinstance(evidence_source, EvidenceRepository):
            self.repository = evidence_source
        elif hasattr(evidence_source, "get_payload"):
            self.repository = WorldEvidenceRepository(evidence_source)
        else:
            try:
                self.repository = InMemoryEvidenceRepository(evidence_source)
            except TypeError as exc:
                raise TypeError("unsupported evidence source") from exc

    def _facts(
        self,
        evidence: Iterable[ObjectRef | EvidenceFact] | None,
    ) -> tuple[EvidenceFact, ...]:
        if self.repository is None:
            raise InsufficientEvidenceError(
                "advisor requires caller-supplied or persisted evidence; "
                "hardcoded pointers are forbidden"
            )
        if evidence is None:
            facts = self.repository.list_facts()
        else:
            facts_list: list[EvidenceFact] = []
            for item in evidence:
                supplied = item if isinstance(item, EvidenceFact) else None
                ref = supplied.ref if supplied is not None else item
                resolved = self.repository.resolve(_require_pinned(ref))
                if supplied is not None and supplied != resolved:
                    raise EvidenceIntegrityError(
                        f"supplied evidence conflicts with repository: {supplied.ref}"
                    )
                facts_list.append(resolved)
            facts = tuple(facts_list)
        if not facts:
            raise InsufficientEvidenceError("no verified evidence was supplied")
        return facts


class MomBirthdayGiftAdvisor(_EvidenceBoundAdvisor):
    def advise(
        self,
        budget_cny: float | None = None,
        *,
        evidence: Iterable[ObjectRef | EvidenceFact] | None = None,
    ) -> ActionableAdvice:
        budget = _positive_money(budget_cny, "budget_cny")
        facts = self._facts(evidence)
        selected = _select_distinct(
            facts,
            (
                (
                    "2023 scarf non-use",
                    lambda fact: (
                        _in_year(fact, 2023)
                        and _has(fact, ("丝巾", "饰品"))
                        and _has(fact, ("落灰", "闲置", "没用", "未使用"))
                    ),
                ),
                (
                    "2024 footbath burden",
                    lambda fact: (
                        _in_year(fact, 2024)
                        and _has(fact, ("足浴盆",))
                        and _has(fact, ("笨重", "倒水", "腰疼", "腰痛", "闲置"))
                    ),
                ),
                (
                    "2025 massage-chair success",
                    lambda fact: (
                        _in_year(fact, 2025)
                        and _has(fact, ("按摩椅",))
                        and _has(fact, ("极佳", "很好", "喜欢", "常用", "满意"))
                    ),
                ),
                (
                    "2026 knee cold sensitivity",
                    lambda fact: (
                        _in_year(fact, 2026)
                        and _has(fact, ("膝盖", "老寒腿"))
                        and _has_asserted(
                            fact,
                            ("受凉", "冷", "疼", "痛"),
                            ("不疼", "不痛", "未受凉", "没有不适"),
                        )
                    ),
                ),
            ),
        )
        if budget < 300:
            conclusion = (
                f"预算 {budget:g} 元不足以可靠购买气囊理疗仪；先选轻便可退换的"
                "保暖护膝，严禁足浴盆等笨重水洗家电及饰品。"
            )
            alternatives = ("增加预算后再选有正规资质的膝盖气囊热敷理疗仪",)
        else:
            conclusion = (
                f"预算 {budget:g} 元内，优先选轻便、可退换的膝盖气囊热敷理疗仪；"
                "明确排除足浴盆等笨重水洗家电和丝巾饰品。"
            )
            alternatives = ("轻便保暖护膝", "可退换的无水热敷带")
        return ActionableAdvice(
            scenario=AdviceScenario.MOM_BIRTHDAY_GIFT,
            conclusion=conclusion,
            evidence_pointers=tuple(fact.ref for fact in selected),
            action_steps=(
                "核对正规器械资质、重量与退换条件",
                "让母亲试戴后再保留，避免再次闲置",
            ),
            alternatives=alternatives,
            expected_benefit=(
                "避开已验证的闲置与搬水负担，针对膝盖受凉需求提升实际使用率。"
            ),
        )


class FraudPreventionAdvisor(_EvidenceBoundAdvisor):
    def advise(
        self,
        request_text: str | None = None,
        *,
        evidence: Iterable[ObjectRef | EvidenceFact] | None = None,
    ) -> ActionableAdvice:
        if not isinstance(request_text, str) or not request_text.strip():
            raise ValueError("request_text is required")
        normalized_request = request_text.casefold()
        if not any(
            term in normalized_request
            for term in ("借款", "贷款", "合伙", "投资", "转账")
        ):
            raise ValueError("request_text is not a loan or partnership decision")
        facts = self._facts(evidence)
        selected = _select_distinct(
            facts,
            (
                (
                    "court fraud ruling",
                    lambda fact: (
                        fact.object_type.casefold()
                        in {"claim", "event", "annotation", "document"}
                        and _has(fact, ("法院", "判决", "裁判"))
                        and _has_asserted(
                            fact,
                            ("诈骗", "合同诈骗"),
                            (
                                "不构成诈骗",
                                "未认定诈骗",
                                "排除诈骗",
                                "诈骗罪不成立",
                                "无罪",
                            ),
                        )
                    ),
                ),
                (
                    "historical delay chat",
                    lambda fact: (
                        _has(fact, ("微信", "聊天", "消息"))
                        and _has_asserted(
                            fact,
                            ("拖延", "延期", "不还", "失联", "推脱"),
                            ("没有拖延", "从未拖延", "按时归还", "已经还清"),
                        )
                    ),
                ),
            ),
        )
        return ActionableAdvice(
            scenario=AdviceScenario.FRAUD_PREVENTION,
            conclusion=(
                "立即阻击新增借款、转账或合伙出资，不再追加资金；保存本次沟通并"
                "带法院材料和历史拖延记录咨询律师，启动合法资产追偿。"
            ),
            evidence_pointers=tuple(fact.ref for fact in selected),
            action_steps=(
                "拒绝付款、担保和签署新协议",
                "固化聊天、判决与既有债权凭证",
                "由律师核验执行状态并选择追偿路径",
            ),
            alternatives=("只做书面拒绝并持续监测账户",),
            expected_benefit="阻断二次受骗与新增敞口，同时保全可执行的追偿证据。",
        )


class HealthFatigueBreakerAdvisor(_EvidenceBoundAdvisor):
    def advise(
        self,
        *,
        evidence: Iterable[ObjectRef | EvidenceFact] | None = None,
    ) -> ActionableAdvice:
        facts = self._facts(evidence)
        selected = _select_distinct(
            facts,
            (
                (
                    "overnight fatigue",
                    lambda fact: (
                        _has(fact, ("通宵", "熬夜", "整夜未睡"))
                        and _has(fact, ("周四", "连续", "工作", "加班"))
                    ),
                ),
                (
                    "ventricular premature beats",
                    lambda fact: _has_asserted(
                        fact,
                        ("室性早搏", "室早", "早搏", "pvc"),
                        (
                            "未发现早搏",
                            "无早搏",
                            "排除室性早搏",
                            "未见室早",
                            "pvc 阴性",
                        ),
                    ),
                ),
            ),
        )
        return ActionableAdvice(
            scenario=AdviceScenario.HEALTH_FATIGUE_BREAKER,
            conclusion=(
                "立即触发疲劳熔断：停止工作并休息；尽快联系医生复查心电图/动态"
                "心电图。若胸痛、晕厥、呼吸困难或症状持续，立即呼叫急救。"
            ),
            evidence_pointers=tuple(fact.ref for fact in selected),
            action_steps=(
                "停止继续通宵并避免自行服用刺激性抗疲劳药",
                "记录早搏时间、频率与伴随症状",
                "联系医疗机构安排心电图或动态心电图复查",
            ),
            alternatives=("由家人陪同前往急诊或心内科",),
            expected_benefit="减少疲劳叠加心律异常的风险，并把诊断交给真实医疗检查。",
        )


def _require_pinned(ref: ObjectRef) -> ObjectRef:
    try:
        normalized = ObjectRef.model_validate(ref)
    except (TypeError, ValueError) as exc:
        raise EvidenceIntegrityError("invalid evidence pointer") from exc
    if normalized.revision is None:
        raise EvidenceIntegrityError("evidence ObjectRef must pin a revision")
    return normalized


def _payload_time(payload: Mapping[str, Any]) -> datetime | None:
    occurred = payload.get("occurred")
    candidates = []
    if isinstance(occurred, Mapping):
        candidates.extend((occurred.get("start"), occurred.get("end")))
    candidates.extend(
        (
            payload.get("learned_at"),
            payload.get("created_at"),
            payload.get("recorded_at"),
        )
    )
    for candidate in candidates:
        parsed = _parse_time(candidate)
        if parsed is not None:
            return parsed
    return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _positive_money(value: float | None, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return normalized


def _text(fact: EvidenceFact) -> str:
    return fact.text.casefold()


def _has(fact: EvidenceFact, alternatives: Sequence[str]) -> bool:
    text = _text(fact)
    return any(term.casefold() in text for term in alternatives)


def _has_asserted(
    fact: EvidenceFact,
    alternatives: Sequence[str],
    negations: Sequence[str],
) -> bool:
    text = _text(fact)
    return not any(negation.casefold() in text for negation in negations) and any(
        term.casefold() in text for term in alternatives
    )


def _in_year(fact: EvidenceFact, year: int) -> bool:
    return str(year) in fact.text or (
        fact.occurred_at is not None and fact.occurred_at.year == year
    )


def _select_distinct(
    facts: Sequence[EvidenceFact],
    requirements: Sequence[tuple[str, Any]],
) -> tuple[EvidenceFact, ...]:
    ordered = sorted(
        facts,
        key=lambda fact: (
            fact.occurred_at or datetime.min.replace(tzinfo=UTC),
            fact.ref.object_id,
            fact.ref.revision or 0,
        ),
    )
    selected: list[EvidenceFact] = []
    used: set[tuple[str, int]] = set()
    missing: list[str] = []
    for label, predicate in requirements:
        match = next(
            (
                fact
                for fact in ordered
                if (fact.ref.object_id, fact.ref.revision or 0) not in used
                and predicate(fact)
            ),
            None,
        )
        if match is None:
            missing.append(label)
            continue
        assert match.ref.revision is not None
        used.add((match.ref.object_id, match.ref.revision))
        selected.append(match)
    if missing:
        raise InsufficientEvidenceError(
            "missing verified causal evidence: " + ", ".join(missing)
        )
    return tuple(selected)
