"""驾驶舱全景调度：单次加载的 CockpitManifest 与不可变四步心法顺序（阶段八核心算子）。

宪法依据
--------
* 第 30 章 / 第八十六条：驾驶舱是**单次加载**的最小看板 —— 一次读世界，绝不
  来回问用户"你最近怎么样 / 你想聊什么"；
* 心法四步（不可换序、不可跳过）：
  ① 照镜子看自己 → ② 校准羁绊看关系 → ③ 确立姿态定语调 → ④ 审视现场看世界；
  顺序本身就是防雪崩与防跑偏的结构：先自省、再关系、再姿态、最后才看外部现场；
* 第六条：零界面（black-box）—— 看板不向用户弹出任何问题、问卷或滑杆。

为什么既有实现不够
------------------
``CockpitPipeline`` 解决的是"对话中看板 Prompt 的 Token 预算"，但**世界全景的
一次装载**是另一件事：没有清单（Manifest），每个环节都要各自再去翻世界，既
浪费 I/O，也无法保证"四步心法"的顺序不被调用方随手打乱。

本模块给出：

1. :class:`MindOrderManifestLoader` —— **恰好一次**世界读取（``list_payloads``
   单次装载），把全部对象按四个透镜分桶，产出有硬 Token 上限的
   :class:`CockpitManifest`；
2. :class:`MindOrderSession` —— 心法四步的强制顺序执行器：跳步、回退、乱序
   一律 ``MindOrderViolation``，并统计"向用户提问次数"（必须恒为 0）。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aios_core.cockpit.pipeline import estimate_tokens
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import as_utc
from aios_core.query.search import derive_dimension
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

__all__ = [
    "CockpitManifest",
    "MANIFEST_TOKEN_BUDGET",
    "MIND_ORDER",
    "MIND_ORDER_TITLES",
    "MindLens",
    "MindOrderManifestLoader",
    "MindOrderSession",
    "MindOrderViolation",
    "ManifestHighlight",
    "ManifestSection",
]

#: 全景看板总 Token 上限（单次加载；其余预算留给对话本身，合起来 <= 1500）。
MANIFEST_TOKEN_BUDGET: int = 1000

#: 每个透镜的 Token 上限（四段之和等于总预算）。
LENS_TOKEN_BUDGET: dict[str, int] = {
    "self": 300,
    "bond": 230,
    "stance": 170,
    "scene": 300,
}

#: 每条高亮的字符上限（极简：手环一屏可扫）。
_HIGHLIGHT_CHARS = 48


class MindLens(StrEnum):
    """心法四步对应的四个透镜（顺序即宪法顺序）。"""

    SELF = "self"
    BOND = "bond"
    STANCE = "stance"
    SCENE = "scene"


#: 不可变心法顺序 —— 任何重排都是违宪。
MIND_ORDER: tuple[MindLens, ...] = (
    MindLens.SELF,
    MindLens.BOND,
    MindLens.STANCE,
    MindLens.SCENE,
)

MIND_ORDER_TITLES: dict[str, str] = {
    MindLens.SELF.value: "照镜子看自己",
    MindLens.BOND.value: "校准羁绊看关系",
    MindLens.STANCE.value: "确立姿态定语调",
    MindLens.SCENE.value: "审视现场看世界",
}

#: 每个透镜消费的对象类型（严格分区：同一对象只出现在一个透镜里，绝不重复计数）。
_LENS_OBJECT_TYPES: dict[str, tuple[ObjectType, ...]] = {
    MindLens.SELF.value: (
        ObjectType.OBSERVATION,
        ObjectType.DIMENSION_CURVE_POINT,
        ObjectType.LIFE_CHAPTER,
    ),
    MindLens.BOND.value: (
        ObjectType.ENTITY,
        ObjectType.RELATION,
        ObjectType.COMMUNICATION_EXPERIENCE,
    ),
    MindLens.STANCE.value: (
        ObjectType.CLAIM,
        ObjectType.REINTERPRETATION,
        ObjectType.TOOL_PROPOSAL,
    ),
    MindLens.SCENE.value: (
        ObjectType.EVENT,
        ObjectType.TASK,
        ObjectType.WAKE,
        ObjectType.SUMMARY,
        ObjectType.OBSERVATION,
    ),
}

#: 自省透镜只吃"自己的维度"（工作/健康），避免把全世界都当成镜子。
_SELF_DIMENSIONS = ("dim_health", "dim_work")


class MindOrderViolation(ValueError):
    """心法顺序违宪（跳步、乱序、回退）。"""


class ManifestHighlight(BaseModel):
    """看板高亮条目：极短文本 + 钉死修订号的证据指针。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    revision: int = Field(ge=1)
    object_type: str
    text: str
    tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_text(self) -> "ManifestHighlight":
        if not self.text.strip():
            raise ValueError("a manifest highlight must carry renderable text")
        if len(self.text) > _HIGHLIGHT_CHARS:
            raise ValueError(
                f"highlight text must fit the bracelet screen ({_HIGHLIGHT_CHARS} chars)"
            )
        return self


class ManifestSection(BaseModel):
    """一个透镜的看板段落（含被省条数，诚实声明裁剪量）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lens: MindLens
    title: str
    order_index: int = Field(ge=0, le=3)
    highlights: tuple[ManifestHighlight, ...] = ()
    candidates: int = Field(ge=0)
    elided: int = Field(ge=0)
    tokens: int = Field(ge=0)
    budget: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_section(self) -> "ManifestSection":
        expected = MIND_ORDER.index(self.lens)
        if self.order_index != expected:
            raise MindOrderViolation(
                f"section {self.lens.value} claims order_index {self.order_index}, "
                f"the immutable mind order fixes it at {expected}"
            )
        if self.title != MIND_ORDER_TITLES[self.lens.value]:
            raise MindOrderViolation("section title must be the constitutional step title")
        if self.tokens > self.budget:
            raise ValueError(f"section {self.lens.value} exceeds its token budget")
        if self.elided + len(self.highlights) > max(self.candidates, len(self.highlights)):
            raise ValueError("elided count cannot exceed the candidate pool")
        return self


class CockpitManifest(BaseModel):
    """单次加载的全景看板（零提问、零冗余往返）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_id: str
    world_revision: int = Field(ge=0)
    built_at: datetime
    sections: tuple[ManifestSection, ...]
    total_tokens: int = Field(ge=0)
    budget: int = Field(default=MANIFEST_TOKEN_BUDGET, ge=1)
    source_reads: int = Field(default=1, ge=1)
    load_ms: float = Field(ge=0.0)
    questions_to_user: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_manifest(self) -> "CockpitManifest":
        order = tuple(section.lens for section in self.sections)
        if order != MIND_ORDER:
            raise MindOrderViolation(
                f"manifest sections must follow the immutable mind order {[m.value for m in MIND_ORDER]}"
            )
        for index, section in enumerate(self.sections):
            if section.order_index != index:
                raise MindOrderViolation("section order_index must match its position")
        if self.total_tokens > self.budget:
            raise ValueError("manifest exceeds the single-load token budget")
        if self.questions_to_user != 0:
            raise ValueError("零界面：全景看板不得向用户提问")
        return self

    def section(self, lens: MindLens) -> ManifestSection:
        for item in self.sections:
            if item.lens is lens:
                return item
        raise KeyError(f"manifest has no section for {lens.value}")

    def highlight_refs(self) -> tuple[ObjectRef, ...]:
        return tuple(
            ObjectRef(object_id=hit.object_id, revision=hit.revision)
            for section in self.sections
            for hit in section.highlights
        )

    def render(self) -> str:
        """渲染为极简文本（四步顺序固定，供大模型单次读取）。"""

        lines: list[str] = []
        for section in self.sections:
            head = f"[{section.order_index + 1}/4] {section.title}"
            if not section.highlights:
                lines.append(f"{head}：今日无异常")
                continue
            body = "；".join(hit.text for hit in section.highlights)
            lines.append(f"{head}：{body}")
        return "\n".join(lines)


class MindOrderManifestLoader:
    """单次装载器：一次读世界 → 四透镜分桶 → 硬预算看板。"""

    def __init__(
        self,
        store: SQLiteWorldStore,
        *,
        budget: int = MANIFEST_TOKEN_BUDGET,
        highlights_per_lens: int = 6,
    ) -> None:
        self.store = store
        self.budget = budget
        self.highlights_per_lens = highlights_per_lens
        self._loads = 0

    @property
    def loads(self) -> int:
        """本装载器在全生命周期中读取世界的次数（单次加载的现场证据）。"""

        return self._loads

    # ------------------------------------------------------------------

    def load(self, *, subject_id: str = "user_1", now: datetime | None = None) -> CockpitManifest:
        stamp = as_utc(now or datetime.now(UTC), "now")
        started = time.perf_counter()

        # ---- 恰好一次世界读取：之后所有分桶都在这份快照上做 ----
        payloads = self.store.list_payloads()
        self._loads += 1
        world_revision = int(self.store.current_world_revision())

        buckets: dict[str, list[dict]] = {lens.value: [] for lens in MIND_ORDER}
        for payload in payloads:
            lens = self._lens_for(payload)
            if lens is None:
                continue
            buckets[lens.value].append(payload)

        sections: list[ManifestSection] = []
        for index, lens in enumerate(MIND_ORDER):
            sections.append(
                self._build_section(
                    lens=lens,
                    order_index=index,
                    candidates=buckets[lens.value],
                )
            )

        manifest = CockpitManifest(
            subject_id=subject_id,
            world_revision=world_revision,
            built_at=stamp,
            sections=tuple(sections),
            total_tokens=sum(section.tokens for section in sections),
            budget=self.budget,
            source_reads=1,
            load_ms=(time.perf_counter() - started) * 1000.0,
            questions_to_user=0,
        )
        return manifest

    # ------------------------------------------------------------------

    @staticmethod
    def _lens_for(payload: dict) -> MindLens | None:
        """把一条世界对象归入唯一透镜（自省只收身心/工作维度，其余观察进现场）。"""

        object_type = str(payload.get("object_type", ""))
        if object_type == ObjectType.OBSERVATION.value:
            dimension = derive_dimension(payload, object_type)
            if dimension in _SELF_DIMENSIONS:
                return MindLens.SELF
            return MindLens.SCENE
        for lens in MIND_ORDER:
            if object_type in {member.value for member in _LENS_OBJECT_TYPES[lens.value]}:
                return lens
        return None

    def _build_section(
        self, *, lens: MindLens, order_index: int, candidates: Sequence[dict]
    ) -> ManifestSection:
        budget = LENS_TOKEN_BUDGET[lens.value]
        ordered = sorted(candidates, key=self._rank, reverse=True)
        highlights: list[ManifestHighlight] = []
        used = 0
        for payload in ordered:
            if len(highlights) >= self.highlights_per_lens:
                break
            text = self._summarize(payload)
            if not text:
                continue
            tokens = estimate_tokens(text)
            if used + tokens > budget:
                continue
            highlights.append(
                ManifestHighlight(
                    object_id=str(payload["object_id"]),
                    revision=int(payload["revision"]),
                    object_type=str(payload["object_type"]),
                    text=text,
                    tokens=tokens,
                )
            )
            used += tokens
        return ManifestSection(
            lens=lens,
            title=MIND_ORDER_TITLES[lens.value],
            order_index=order_index,
            highlights=tuple(highlights),
            candidates=len(candidates),
            elided=max(0, len(candidates) - len(highlights)),
            tokens=used,
            budget=budget,
        )

    @staticmethod
    def _rank(payload: dict) -> tuple[int, int, str]:
        priority = int(payload.get("priority", 0) or 0)
        active = 1 if str(payload.get("status", "active")) == "active" else 0
        learned = str(payload.get("learned_at", ""))
        return (active, priority, learned)

    @staticmethod
    def _summarize(payload: dict) -> str:
        rendered = MindOrderManifestLoader._render_structured(payload)
        if rendered:
            return MindOrderManifestLoader._clip(rendered)
        for field in ("value", "title", "canonical_name", "content", "chapter_title"):
            raw = payload.get(field)
            if isinstance(raw, str) and raw.strip():
                return MindOrderManifestLoader._clip(" ".join(raw.split()))
        statement = payload.get("statement")
        if isinstance(statement, str) and statement.strip():
            return MindOrderManifestLoader._clip(" ".join(statement.split()))
        return ""

    @staticmethod
    def _render_structured(payload: dict) -> str:
        """把结构化观测（IMU/心率 JSON）渲染成一行可读高亮。"""

        value = payload.get("value")
        if not isinstance(value, str) or not value.startswith("{"):
            return ""
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return ""
        if not isinstance(data, dict):
            return ""
        source_kind = str(payload.get("source_kind", ""))
        if source_kind == "imu_macro_state":
            return (
                f"运动 {data.get('motion_state')} "
                f"{float(data.get('mean_magnitude_g', 0.0)):.2f}g"
            )
        if source_kind == "imu_impact":
            return (
                f"{data.get('impact_kind')} 峰值 "
                f"{float(data.get('peak_magnitude_g', 0.0)):.2f}g"
            )
        if source_kind == "heart_rate_summary":
            mean = data.get("mean_bpm")
            return f"心率均值 {mean:.0f}bpm" if isinstance(mean, (int, float)) else "心率时段均值"
        if source_kind == "heart_rate_anomaly":
            peak = data.get("peak_bpm")
            night = "夜间" if data.get("nighttime") else ""
            return (
                f"{night}心率异常峰值 {peak:.0f}bpm"
                if isinstance(peak, (int, float))
                else f"{night}心率异常"
            )
        tags = data.get("scene_tags")
        if isinstance(tags, list) and tags:
            return "画面 " + "/".join(str(tag) for tag in tags[:2])
        return ""

    @staticmethod
    def _clip(text: str) -> str:
        text = " ".join(text.split())
        return text if len(text) <= _HIGHLIGHT_CHARS else text[: _HIGHLIGHT_CHARS - 1] + "…"


class MindOrderSession:
    """心法四步的强制顺序执行器（乱序/跳步/回退一律拦截）。"""

    def __init__(self, *, subject_id: str = "user_1") -> None:
        self.subject_id = subject_id
        self._cursor = 0
        self._visited: list[MindLens] = []
        self._questions = 0
        self._steps: dict[str, Any] = {}

    # ------------------------------------------------------------------

    @property
    def visited(self) -> tuple[MindLens, ...]:
        return tuple(self._visited)

    @property
    def questions_to_user(self) -> int:
        return self._questions

    @property
    def next_step(self) -> MindLens | None:
        return MIND_ORDER[self._cursor] if self._cursor < len(MIND_ORDER) else None

    def run_step(self, lens: MindLens, producer: Callable[[MindLens], Any]) -> Any:
        """执行心法第 N 步；顺序不符立即 ``MindOrderViolation``。"""

        expected = self.next_step
        if expected is None:
            raise MindOrderViolation("all four mind steps are already sealed for this session")
        if lens is not expected:
            raise MindOrderViolation(
                f"mind order is immutable: expected {expected.value}, got {lens.value}"
            )
        result = producer(lens)
        self._visited.append(lens)
        self._steps[lens.value] = result
        self._cursor += 1
        return result

    def step_result(self, lens: MindLens) -> Any:
        if lens.value not in self._steps:
            raise MindOrderViolation(f"step {lens.value} has not been executed yet")
        return self._steps[lens.value]

    def ask_user(self) -> None:
        """零界面纪律：会话不得向用户提问（问卷/滑杆/往返确认都被视为提问）。"""

        self._questions += 1

    def seal(self) -> tuple[MindLens, ...]:
        """封印：四步全走完才算一次完整心法。"""

        if self._cursor != len(MIND_ORDER):
            missing = [lens.value for lens in MIND_ORDER[self._cursor :]]
            raise MindOrderViolation(f"mind session is incomplete; missing steps: {missing}")
        return self.visited

    # ------------------------------------------------------------------

    @staticmethod
    def order_is_legal(candidate: Iterable[MindLens]) -> bool:
        """顺序合法性检查（供外部审计调用，不修改任何状态）。"""

        return tuple(candidate) == MIND_ORDER
