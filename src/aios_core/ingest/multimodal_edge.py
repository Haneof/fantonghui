"""M1-001R / M1-001R-ADV 端侧多模态轻量摄入与声纹 180 天淘汰引擎（高熵工业/商务场景加固版）。

落实宪法第 33 条第 5 款与用户最高原则（端侧存储铁律）：

1. **画质退化亚毫秒粉碎**：昏暗 + 走动抖动场景下画质 < 0.4 的垃圾图片由
   ``RawByteSink.purge`` 物理删除（500 张 < 5ms），主存储与内存中原始字节
   保留量严格为 0 —— 端侧空间全部留给高价值结构化认知；
2. **严禁主库持久化原始二进制大图**：达标图像只产出纯文本 Caption 语义摘要
   （``ImageSemanticObservation.raw_image_bytes_retained = False``）；
3. **128 维声纹局部敏感哈希（LSH）**：``VoiceprintLSHIndex`` 支持 24 人高密
   交叉重叠音频流切片聚类，准确区分核心商务伙伴（实体绑定）与穿梭的服务员/路人；
4. **180 天 TTL 墓碑状态机**：``VoiceprintTTLRegistry`` —— 未绑定实体身份的
   背景人声声纹，在最后接触满 180 天的瞬间 ``is_tombstone`` 严格置 True，
   并从活跃匹配热表剥离至归档区；再次接触则复活回热表（状态机可逆、可审计）。

高熵场景：重型工业装配车间（85dB 持续背景机械低频噪音）+ 跨国供应链
24 人商务圆桌晚宴（中文/英文/方言交叉重叠混杂）+ 设备标牌与合同文本抓拍。
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

__all__ = [
    "FEATURE_DIM",
    "ImageSemanticObservation",
    "QualityGate",
    "RawByteSink",
    "VoiceprintLSHIndex",
    "VoiceprintLifecycleManager",
    "VoiceprintProfile",
    "VoiceprintTTLRegistry",
    "EdgeMultimodalCleaner",
    "assess_image_quality",
]

#: 声纹特征维度（宪法工单约定：128 维局部敏感哈希）。
FEATURE_DIM: int = 128

#: 声纹 TTL：未绑定实体身份的背景声纹，最后接触满 180 天自动墓碑。
VOICEPRINT_TTL_DAYS: int = 180

#: 画质初筛硬阈值（宪法第 33 条第 5 款：< 0.4 坚决丢弃）。
QUALITY_GARBAGE_THRESHOLD: float = 0.4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ----------------------------------------------------------------------
# 门禁 1：画质评估与垃圾图物理粉碎（RawByteSink）
# ----------------------------------------------------------------------


def assess_image_quality(image_metadata: Dict[str, Any]) -> float:
    """确定性画质评分（0~1）。

    显式 ``quality_score`` 优先（上游相机算法给出）；否则由传感器特征合成：
    - ``high_freq_energy``（清晰度，0~1）权重 0.45；
    - ``mean_luma``（平均亮度 0~255）权重 0.35；
    - ``motion_magnitude``（走动抖动，0~1，越大越糊）权重 0.20 反向；
    - 昏暗惩罚：``mean_luma < 40`` 时总分 × 0.3（昏暗场景画质崩塌）。
    """
    if "quality_score" in image_metadata:
        return _clamp01(float(image_metadata["quality_score"]))
    luma = float(image_metadata.get("mean_luma", 128.0))
    sharp = _clamp01(float(image_metadata.get("high_freq_energy", 0.5)))
    motion = _clamp01(float(image_metadata.get("motion_magnitude", 0.1)))
    luma_norm = _clamp01(luma / 255.0)
    score = 0.45 * sharp + 0.35 * luma_norm + 0.20 * (1.0 - motion)
    if luma < 40.0:
        score *= 0.3
    return _clamp01(score)


class RawByteSink:
    """端侧原始字节暂存池（宪法：只暂存、必粉碎，严禁长留主存储）。

    - ``sink`` 接收原始字节并计入保留量；
    - ``purge`` 物理删除（dict.pop，无删除标记、无墓碑残留）；
    - ``retained_bytes`` 是"主存储与内存原始字节保留量"的唯一审计口径。
    """

    def __init__(self) -> None:
        self._blobs: Dict[str, bytes] = {}
        self._retained: int = 0

    def sink(self, image_id: str, raw_bytes: bytes) -> None:
        if not isinstance(image_id, str) or not image_id:
            raise ValueError("image_id must be a non-empty string")
        if image_id in self._blobs:
            raise ValueError(f"image {image_id!r} already sunk; raw bytes are single-write")
        self._blobs[image_id] = bytes(raw_bytes)
        self._retained += len(self._blobs[image_id])

    def purge(self, image_ids: Sequence[str]) -> int:
        """物理删除指定原始字节，返回释放字节数（无标记删除）。"""
        freed = 0
        for image_id in image_ids:
            blob = self._blobs.pop(image_id, None)
            if blob is not None:
                freed += len(blob)
                self._retained -= len(blob)
        return freed

    @property
    def retained_bytes(self) -> int:
        return self._retained

    def __len__(self) -> int:
        return len(self._blobs)


class ImageSemanticObservation(BaseModel):
    """达标图像的纯文本语义观察（原始二进制绝不落主库）。"""

    model_config = {"frozen": True}

    observation_id: str
    quality_score: float = Field(ge=0.0, le=1.0)
    semantic_caption: str
    scene_tags: List[str] = Field(default_factory=list)
    raw_image_bytes_retained: bool = Field(default=False)
    captured_at: datetime = Field(default_factory=_utc_now)


class QualityGate:
    """画质初筛门禁：< 0.4 坚决抛弃。"""

    def __init__(self, threshold: float = QUALITY_GARBAGE_THRESHOLD) -> None:
        self.threshold = threshold

    def passes(self, quality: float) -> bool:
        return quality >= self.threshold


# ----------------------------------------------------------------------
# 端侧多模态清洗器（M1-001R 骨架契约 + ADV 画质评估）
# ----------------------------------------------------------------------


class EdgeMultimodalCleaner:
    """端侧多模态轻量清洗：画质初筛 + 纯文本 Caption，原始字节零保留。"""

    def __init__(self, quality_gate: Optional[QualityGate] = None) -> None:
        self.quality_gate = quality_gate or QualityGate()

    def evaluate_and_clean_image(
        self,
        image_metadata: Dict[str, Any],
        raw_bytes: bytes,
    ) -> Optional[ImageSemanticObservation]:
        """画质初筛：< 0.4 坚决抛弃（返回 None）；达标则只产 Caption。

        ``raw_bytes`` 参数仅用于端侧在内存中完成 Caption 提取，
        函数返回后调用方必须将其交还 ``RawByteSink.purge`` 粉碎。
        """
        _ = raw_bytes  # 原始字节绝不写入任何持久化字段
        score = assess_image_quality(image_metadata)
        if not self.quality_gate.passes(score):
            return None
        caption = image_metadata.get("caption", "日常活动场景")
        tags = image_metadata.get("tags", ["routine"])
        source = image_metadata.get("source", "")
        source_bytes = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        return ImageSemanticObservation(
            observation_id=(
                f"obs_img_{int(_utc_now().timestamp() * 1000)}_"
                f"{hashlib.sha1(source_bytes).hexdigest()[:8]}"
            ),
            quality_score=score,
            semantic_caption=caption,
            scene_tags=list(tags),
            raw_image_bytes_retained=False,
        )


# ----------------------------------------------------------------------
# 声纹 LSH（128 维特征 → 96 位局部敏感哈希签名）
# ----------------------------------------------------------------------


def lsh_signature(feature: Sequence[float], planes: Sequence[Sequence[float]]) -> int:
    """随机超平面 LSH：bit_i = 1 iff dot(feature, plane_i) >= 0。"""
    signature = 0
    for plane_index, plane in enumerate(planes):
        dot = 0.0
        for axis in range(len(plane)):
            dot += feature[axis] * plane[axis]
        if dot >= 0.0:
            signature |= 1 << plane_index
    return signature


def hamming_distance(signature_a: int, signature_b: int) -> int:
    return (signature_a ^ signature_b).bit_count()


def _normalize(feature: Sequence[float]) -> Tuple[float, ...]:
    norm = math.sqrt(sum(float(v) * float(v) for v in feature))
    if norm == 0.0:
        return tuple(0.0 for _ in feature)
    return tuple(float(v) / norm for v in feature)


class VoiceprintLSHIndex:
    """128 维声纹局部敏感哈希索引（24 人高密音频流切片聚类）。

    - ``add``：注册声纹（128 维特征归一化 + 96 位 LSH 签名 + 实体绑定）；
    - ``candidate_search``：查询特征 → 按汉明距离排序的候选声纹；
    - 核心商务伙伴与服务员/路人的区分 = LSH 聚类纯度 + 实体绑定元数据。
    """

    def __init__(self, seed: int = 20260916, lsh_planes: int = 96) -> None:
        if lsh_planes < 1:
            raise ValueError("lsh_planes must be >= 1")
        rng = random.Random(seed)
        self._planes: List[Tuple[float, ...]] = [
            tuple(rng.gauss(0.0, 1.0) for _ in range(FEATURE_DIM)) for _ in range(lsh_planes)
        ]
        self._features: Dict[str, Tuple[float, ...]] = {}
        self._signatures: Dict[str, int] = {}
        self._entity_ids: Dict[str, Optional[str]] = {}

    def add(self, voiceprint_id: str, feature: Sequence[float], entity_id: Optional[str] = None) -> None:
        if len(feature) != FEATURE_DIM:
            raise ValueError(f"feature must be {FEATURE_DIM}-dim, got {len(feature)}")
        if voiceprint_id in self._features:
            raise ValueError(f"voiceprint {voiceprint_id!r} already registered")
        normalized = _normalize(feature)
        self._features[voiceprint_id] = normalized
        self._signatures[voiceprint_id] = lsh_signature(normalized, self._planes)
        self._entity_ids[voiceprint_id] = entity_id

    def signature(self, voiceprint_id: str) -> int:
        try:
            return self._signatures[voiceprint_id]
        except KeyError:
            raise KeyError(f"unknown voiceprint_id: {voiceprint_id!r}") from None

    def entity_id(self, voiceprint_id: str) -> Optional[str]:
        try:
            return self._entity_ids[voiceprint_id]
        except KeyError:
            raise KeyError(f"unknown voiceprint_id: {voiceprint_id!r}") from None

    def candidate_search(self, feature: Sequence[float], k: int = 10) -> List[Tuple[str, int]]:
        """查询特征 → 汉明距离升序的 top-k 候选 (voiceprint_id, distance)。"""
        normalized = _normalize(feature)
        query_signature = lsh_signature(normalized, self._planes)
        ranked = sorted(
            (
                (vp_id, hamming_distance(query_signature, signature))
                for vp_id, signature in self._signatures.items()
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
        return ranked[:k]

    def assign_slice(self, feature: Sequence[float]) -> str:
        """将一条音频切片指派给最近的已注册声纹（聚类分配）。"""
        top = self.candidate_search(feature, k=1)
        return top[0][0]

    def __len__(self) -> int:
        return len(self._features)


# ----------------------------------------------------------------------
# 门禁 3：180 天 TTL 墓碑状态机（热表 / 归档区）
# ----------------------------------------------------------------------


class VoiceprintProfile(BaseModel):
    """声纹档案（M1-001R 骨架契约）。"""

    model_config = {"frozen": True}

    voiceprint_id: str
    entity_id: Optional[str] = None
    feature_hash: str
    first_detected_at: datetime
    last_contact_at: datetime
    is_tombstone: bool = False


class VoiceprintLifecycleManager:
    """M1-001R 骨架：批量清扫过期声纹（未绑定 + 超 180 天 → 墓碑）。"""

    def __init__(self, ttl_days: int = VOICEPRINT_TTL_DAYS) -> None:
        self.ttl_days = ttl_days

    def sweep_stale_voiceprints(
        self, profiles: List[VoiceprintProfile], current_time: datetime
    ) -> List[VoiceprintProfile]:
        current = _as_aware(current_time, "current_time")
        updated: List[VoiceprintProfile] = []
        for profile in profiles:
            if profile.is_tombstone:
                updated.append(profile)
                continue
            if profile.entity_id is None and (
                current - _as_aware(profile.last_contact_at, "last_contact_at")
                >= timedelta(days=self.ttl_days)
            ):
                updated.append(profile.model_copy(update={"is_tombstone": True}))
            else:
                updated.append(profile)
        return updated


class VoiceprintTTLRegistry:
    """180 天 TTL 墓碑状态机（M1-001R-ADV）。

    状态迁移（可审计）：
    - ``ACTIVE --最后接触满 180 天(仅未绑定实体)--> TOMBSTONED``：
      瞬间迁移（``>=`` 边界语义），同步从活跃匹配热表剥离至归档区；
    - ``TOMBSTONED --再次接触--> ACTIVE``：复活回热表并刷新 last_contact。
    已绑定实体身份的声纹（核心商务伙伴）不受 TTL 约束。
    """

    def __init__(self, ttl_days: int = VOICEPRINT_TTL_DAYS) -> None:
        self.ttl_days = ttl_days
        self._profiles: Dict[str, VoiceprintProfile] = {}

    def register(self, profile: VoiceprintProfile) -> None:
        if profile.voiceprint_id in self._profiles:
            raise ValueError(f"voiceprint {profile.voiceprint_id!r} already registered")
        self._profiles[profile.voiceprint_id] = profile

    def note_contact(self, voiceprint_id: str, at: datetime) -> VoiceprintProfile:
        """记录一次接触：刷新 last_contact；若已墓碑则复活回热表。"""
        profile = self._get(voiceprint_id)
        contact_time = _as_aware(at, "at")
        updated = profile.model_copy(
            update={
                "last_contact_at": contact_time,
                "is_tombstone": False,  # 再次接触 → 复活（状态机 TOMBSTONED -> ACTIVE）
            }
        )
        self._profiles[voiceprint_id] = updated
        return updated

    def sweep(self, now: datetime) -> List[str]:
        """推进时间至 ``now``，返回本次被墓碑化（并剥离出热表）的声纹 id 列表。"""
        current = _as_aware(now, "now")
        tombstoned: List[str] = []
        for voiceprint_id, profile in self._profiles.items():
            if profile.is_tombstone or profile.entity_id is not None:
                continue
            if current - _as_aware(profile.last_contact_at, "last_contact_at") >= timedelta(
                days=self.ttl_days
            ):
                self._profiles[voiceprint_id] = profile.model_copy(
                    update={"is_tombstone": True}
                )
                tombstoned.append(voiceprint_id)
        return sorted(tombstoned)

    # ---------------- 只读视图 ----------------

    def is_tombstone(self, voiceprint_id: str) -> bool:
        return self._get(voiceprint_id).is_tombstone

    @property
    def active_hot(self) -> Tuple[VoiceprintProfile, ...]:
        """活跃匹配热表（未墓碑）。"""
        return tuple(
            p for p in self._profiles.values() if not p.is_tombstone
        )

    @property
    def archived(self) -> Tuple[VoiceprintProfile, ...]:
        """归档区（已墓碑）。"""
        return tuple(p for p in self._profiles.values() if p.is_tombstone)

    def __len__(self) -> int:
        return len(self._profiles)

    def _get(self, voiceprint_id: str) -> VoiceprintProfile:
        try:
            return self._profiles[voiceprint_id]
        except KeyError:
            raise KeyError(f"unknown voiceprint_id: {voiceprint_id!r}") from None
