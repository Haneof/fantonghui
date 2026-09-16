# -*- 老谱系对照跑道：M1-001R 初代端侧清洗器（画质门+绝不存图+声纹180天墓碑），压平合并后 canonical 为新版并集本件；本件只为保住同代测试呈堂，合并时另行仲裁。 -*-
"""M1-001R 端侧多模态轻量摄入与声纹淘汰引擎。

宪法红线实现（机械强制，不依赖任何模型自觉）：

- 红线 1：画质取舍是**纯机械阈值**（``QUALITY_DROP_THRESHOLD``），大模型不参与
  删除判断；``quality < 0.4`` 直接丢弃（返回 ``None``）且原始字节物理删除。
- 红线 2：**绝不存二进制大图**。合格图片仅由轻量端侧模型提取纯文本 caption，
  提取完成后 ``raw_bytes`` 立即经 ``RawByteSink.purge`` 物理删除，
  ``ImageSemanticObservation.raw_image_bytes_retained`` 恒为 ``False``。
- 红线 3：未绑定实体的陌生声纹超过 180 天未接触，``is_tombstone=True``。

本模块位于 durable commit 之前（边缘铸币层），产出的 Observation 语义体后续经
Core ``commit()`` 入总账；此处不 import ``aios_core.storage``，保持 M0 冻结边界。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

#: 红线 1：机械画质阈值。低于即丢弃；等于不丢（严格小于才丢）。
QUALITY_DROP_THRESHOLD = 0.4

#: 红线 3：陌生声纹 TTL。
VOICEPRINT_TTL = timedelta(days=180)

CaptionFn = Callable[[bytes, "ImageMetadata"], tuple[str, list[str]]]


def _require_aware(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware (AIOS 唯一时间轴)")
    return dt


class ImageMetadata(BaseModel):
    """抓拍元数据。触发源必须是机械条件，不得引用语义事件（防循环定义）。"""

    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(min_length=1)
    quality_score: float = Field(ge=0.0, le=1.0)
    captured_at: datetime
    device_id: str = "band-01"
    trigger: str = Field(default="mechanical", pattern="^mechanical:.+")

    @property
    def quality_ok(self) -> bool:
        return self.quality_score >= QUALITY_DROP_THRESHOLD


class ImageSemanticObservation(BaseModel):
    """语义化产物：只有文字，没有图。"""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1)
    quality_score: float = Field(ge=0.0, le=1.0)
    semantic_caption: str = Field(min_length=1)
    scene_tags: list[str] = Field(default_factory=list)
    raw_image_bytes_retained: bool = False
    captured_at: datetime
    caption_model_version: str = Field(min_length=1)


class VoiceprintProfile(BaseModel):
    """声纹档案。``entity_id=None`` 表示尚未绑定实体的陌生声纹。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    voiceprint_id: str = Field(min_length=1)
    entity_id: str | None = None
    feature_hash: str = Field(min_length=1)
    first_detected_at: datetime
    last_contact_at: datetime
    is_tombstone: bool = False


class RawByteSink(Protocol):
    """原始字节物理删除口。端侧实现应真正 unlink/清零，而非缓存。"""

    def purge(self, image_id: str, data: bytes) -> None:  # pragma: no cover
        ...


class InMemoryPurgeSink:
    """测试/仿真用删除口：记录已删除 ID，且不保留任何字节引用。"""

    def __init__(self) -> None:
        self.purged: list[str] = []

    def purge(self, image_id: str, data: bytes) -> None:
        self.purged.append(image_id)
        del data  # 立即放弃引用，模拟物理删除


def default_lightweight_captioner(raw: bytes, meta: ImageMetadata) -> tuple[str, list[str]]:
    """确定性桩 captioner。真机替换为 <1W 端侧小模型；禁止替换为 LLM 删除裁判。"""
    digest = hashlib.sha256(raw).hexdigest()
    return f"edge-caption:{digest[:12]}", [f"scene:{digest[:2]}", f"q:{meta.quality_score:.2f}"]


class EdgeMultimodalCleaner:
    """端侧多模态清洗引擎：评估 → 语义化 → 物理删除原始字节。"""

    def __init__(
        self,
        captioner: CaptionFn = default_lightweight_captioner,
        sink: RawByteSink | None = None,
        caption_model_version: str = "edge-cap-v0",
    ) -> None:
        self._captioner = captioner
        self._sink = sink or InMemoryPurgeSink()
        self._caption_model_version = caption_model_version

    @property
    def sink(self) -> RawByteSink:
        return self._sink

    def evaluate_and_clean_image(
        self,
        image_metadata: ImageMetadata | dict,
        raw_bytes: bytes,
    ) -> ImageSemanticObservation | None:
        """红线 1/2 的机械执行点。

        返回 ``None`` 表示丢弃（画质不达标）；无论丢弃与否，``raw_bytes``
        都会经 sink 物理删除，本方法不向调用方之外泄漏任何字节引用。
        """
        meta = (
            image_metadata
            if isinstance(image_metadata, ImageMetadata)
            else ImageMetadata(**image_metadata)
        )
        _require_aware(meta.captured_at, "captured_at")

        if not meta.quality_ok:  # 机械阈值；LLM 无权改判
            self._sink.purge(meta.image_id, raw_bytes)
            return None

        caption, tags = self._captioner(raw_bytes, meta)
        self._sink.purge(meta.image_id, raw_bytes)  # 红线 2：提取后立即物理删除

        return ImageSemanticObservation(
            observation_id=f"observation:{meta.image_id}",
            quality_score=meta.quality_score,
            semantic_caption=caption,
            scene_tags=tags,
            raw_image_bytes_retained=False,
            captured_at=meta.captured_at,
            caption_model_version=self._caption_model_version,
        )


class VoiceprintLifecycleManager:
    """红线 3：陌生声纹 180 天 TTL 墓碑淘汰。"""

    def __init__(self, ttl: timedelta = VOICEPRINT_TTL) -> None:
        self._ttl = ttl

    def sweep_stale_voiceprints(
        self,
        profiles: Sequence[VoiceprintProfile],
        current_time: datetime,
    ) -> list[str]:
        """对**未绑定实体**且超 TTL 的声纹打墓碑；幂等；绝不触碰已绑定实体。

        返回本轮新打墓碑的 ``voiceprint_id`` 列表。墓碑≠遗忘：feature_hash 保留，
        供回归重识别（销户留底），由 M1a 身份服务消费。
        """
        _require_aware(current_time, "current_time")
        tombstoned: list[str] = []
        for p in profiles:
            _require_aware(p.last_contact_at, "last_contact_at")
            if p.entity_id is not None:
                continue  # 已绑定实体不走陌生声纹淘汰
            if p.is_tombstone:
                continue  # 幂等
            if (current_time - p.last_contact_at) > self._ttl:
                p.is_tombstone = True
                tombstoned.append(p.voiceprint_id)
        return tombstoned
