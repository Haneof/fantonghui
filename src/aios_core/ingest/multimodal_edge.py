"""M1-001R-ADV 高熵工业/商务场景多模态边缘摄入。

实战场景：佩戴者连续穿梭于重型工业装配车间（85dB 持续机械低频噪音）
与跨国供应链 24 人商务圆桌晚宴（中英文与方言交叉重叠），并持续抓拍
设备标牌与合同文本。

三大铁律（V3 §33 边缘轻量化摄入规范）：

1. **画质退化亚毫秒粉碎**：画质分 < 0.4 的昏暗/抖动垃圾抓拍，经
   ``RawByteSink.purge`` 物理删除原始字节（主存储与内存保留量严格
   为 0），仅保留删除审计记录（谁、何时、为何、释放多少字节）——
   对齐 M0-028/R3-ARCH 的「可清洗类 + 永久审计」纪律；
2. **128 维 SimHash-LSH 声纹**：24 个声源同流切片，随机超平面签名
   + 16 band 分桶召回 + 汉明距离核验，区分核心商务伙伴与穿梭的
   服务员/路人；纯本地信号处理，不做任何语义判断（V3 §106）；
3. **180 天 TTL 墓碑状态机**：未绑定实体身份的背景人声声纹，最后
   接触满 180 天的瞬间 ``is_tombstone`` 置 True，从活跃匹配热表剥离
   至归档区（V3 §33-3 声纹冷淘汰）；已绑定核心关系的声纹豁免。
"""

from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

__all__ = [
    "CaptureFrame",
    "PurgeRecord",
    "PurgeReport",
    "RawByteSink",
    "TombstoneSweepReport",
    "TTL_DAYS",
    "VoiceprintLSHEngine",
    "VoiceprintObservation",
    "VoiceprintRecord",
    "assess_capture_quality",
]

#: 画质粉碎阈值：低于此分为垃圾抓拍（昏暗/走动抖动场景）
CAPTURE_PURGE_THRESHOLD = 0.4
#: 声纹维度与 LSH 参数（128 维指纹，16 band × 8 bit 分桶）
VOICEPRINT_DIM = 128
LSH_BANDS = 16
LSH_BAND_BITS = 8
#: 同簇核验的汉明距离上限（128 位签名）
VOICEPRINT_MATCH_HAMMING = 24
#: 声纹冷淘汰 TTL（宪法 §33-3：连续半年以上未接触且未建立核心关系）
TTL_DAYS = 180


# ======================================================================
# 门禁一：画质退化亚毫秒粉碎（RawByteSink）
# ======================================================================

def assess_capture_quality(
    *, brightness: float, sharpness: float, jitter: float
) -> float:
    """抓拍画质评分 ∈ [0,1]：清晰度为主，亮度次之，抖动反向加权。

    纯机械公式（本地信号处理，V3 §106 允许本地做「基础视觉描述」级
    计算），阈值 0.4 为可测试参数而非语义判断。
    """

    def clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    b, s, j = clamp01(brightness), clamp01(sharpness), clamp01(jitter)
    return clamp01(0.55 * s + 0.30 * b + 0.15 * (1.0 - j))


class CaptureFrame(BaseModel):
    """单帧抓拍元数据（原始字节永不入契约，只入 RawByteSink 物理层）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: StrictStr = Field(min_length=1)
    quality: float = Field(ge=0.0, le=1.0)
    brightness: float = Field(ge=0.0, le=1.0)
    sharpness: float = Field(ge=0.0, le=1.0)
    jitter: float = Field(ge=0.0, le=1.0)
    scene_tag: StrictStr = Field(default="unlabeled")
    captured_at: datetime


class PurgeRecord(BaseModel):
    """单帧删除审计记录（审计永存，内容本体不保留）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: StrictStr
    quality: float
    reason: Literal["LOW_QUALITY_GARBAGE"] = "LOW_QUALITY_GARBAGE"
    bytes_freed: StrictInt = Field(ge=0)
    purged_at: datetime


class PurgeReport(BaseModel):
    """一次粉碎批次的报告：删除了什么、释放多少、剩余多少。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    purged_ids: tuple[StrictStr, ...] = Field(default=())
    purged_count: StrictInt = Field(ge=0)
    bytes_freed_total: StrictInt = Field(ge=0)
    retained_count: StrictInt = Field(ge=0)
    raw_bytes_retained_for_purged: StrictInt = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)


class RawByteSink:
    """抓拍原始字节的物理 sink：只存原始字节与元数据，支持亚毫秒粉碎。

    ``purge`` 是**物理删除**（del 字典键，字节对象引用计数即时归零），
    绝无软删除副本；删除行为仅以审计记录形式留痕。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._raw: dict[str, bytes] = {}
        self._meta: dict[str, CaptureFrame] = {}
        self._audit: list[PurgeRecord] = []

    def store(self, frame: CaptureFrame, raw: bytes) -> None:
        with self._lock:
            self._meta[frame.frame_id] = frame
            self._raw[frame.frame_id] = raw

    def raw_size_of(self, frame_id: str) -> int | None:
        """原始字节保留量：0 = 已粉碎，None = 从未入库。

        判定依据：元数据仍在而原始字节键已消失 = 已被物理粉碎。
        """
        with self._lock:
            data = self._raw.get(frame_id)
            if data is not None:
                return len(data)
            return 0 if frame_id in self._meta else None

    def purge(
        self,
        threshold: float = CAPTURE_PURGE_THRESHOLD,
        *,
        now: datetime | None = None,
    ) -> PurgeReport:
        """粉碎画质低于阈值帧的原始字节（物理删除 + 审计留痕）。"""
        started = time.perf_counter()
        purged: list[str] = []
        freed = 0
        with self._lock:
            for frame_id in sorted(self._meta):
                if frame_id not in self._raw:
                    continue  # 已粉碎帧绝不重复审计（幂等）
                frame = self._meta[frame_id]
                if frame.quality >= threshold:
                    continue
                data = self._raw.pop(frame_id, None)
                freed += len(data) if data is not None else 0
                purged.append(frame_id)
                self._audit.append(
                    PurgeRecord(
                        frame_id=frame_id,
                        quality=frame.quality,
                        bytes_freed=len(data) if data is not None else 0,
                        purged_at=now or datetime.now().astimezone(),
                    )
                )
            report = PurgeReport(
                purged_ids=tuple(purged),
                purged_count=len(purged),
                bytes_freed_total=freed,
                retained_count=sum(
                    1 for f in self._meta.values() if f.quality >= threshold
                ),
                raw_bytes_retained_for_purged=sum(
                    len(self._raw.get(fid, b"")) for fid in purged
                ),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
        return report

    @property
    def audit_trail(self) -> tuple[PurgeRecord, ...]:
        with self._lock:
            return tuple(self._audit)

    @property
    def live_frame_count(self) -> int:
        with self._lock:
            return len(self._raw)


# ======================================================================
# 门禁二：24 人高密声纹 SimHash-LSH
# ======================================================================

class VoiceprintObservation(BaseModel):
    """单切片的声纹聚类观测结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: StrictStr
    is_new_cluster: bool
    hamming_to_centroid: StrictInt = Field(ge=0, le=VOICEPRINT_DIM)


class VoiceprintLSHEngine:
    """128 维声纹指纹的 SimHash-LSH 在流聚类引擎。

    - 签名：128 个随机超平面（固定种子，可重放）， bit_i = sign(<v, w_i>)；
    - 召回：128 位签名切 16 band × 8 bit，任一 band 桶命中即为候选；
    - 核验：候选簇质心汉明距离 ≤ 24 判为同源；质心随切片增量平均；
    - 全程本地信号处理，零语义模型调用。
    """

    def __init__(
        self,
        *,
        dim: int = VOICEPRINT_DIM,
        bands: int = LSH_BANDS,
        band_bits: int = LSH_BAND_BITS,
        match_hamming: int = VOICEPRINT_MATCH_HAMMING,
        seed: int = 20260915,
    ) -> None:
        if bands * band_bits != dim:
            raise ValueError("bands * band_bits must equal dim")
        self._dim = dim
        self._bands = bands
        self._band_bits = band_bits
        self._match_hamming = match_hamming
        rng = random.Random(seed)
        # 超平面矩阵：dim 行 × dim 列（行 = 一个超平面法向量）
        self._planes = [
            [rng.gauss(0.0, 1.0) for _ in range(dim)] for _ in range(dim)
        ]
        self._lock = threading.RLock()
        self._centroids: dict[str, list[float]] = {}
        self._sizes: dict[str, int] = {}
        self._buckets: dict[str, set[str]] = {}
        self._cluster_counter = 0

    # -- 签名与召回 -------------------------------------------------------

    def _signature(self, vec: list[float]) -> int:
        bits = 0
        for i, plane in enumerate(self._planes):
            projection = 0.0
            for a, b in zip(plane, vec):
                projection += a * b
            if projection >= 0.0:
                bits |= 1 << i
        return bits

    def _band_keys(self, signature: int) -> list[str]:
        keys = []
        mask = (1 << self._band_bits) - 1
        for band in range(self._bands):
            chunk = (signature >> (band * self._band_bits)) & mask
            keys.append(f"b{band:02d}:{chunk:02x}")
        return keys

    @staticmethod
    def _hamming(a: int, b: int) -> int:
        return bin(a ^ b).count("1")

    @staticmethod
    def _merge_centroid(
        centroid: list[float], vec: list[float], size: int
    ) -> list[float]:
        weight = 1.0 / (size + 1)
        return [
            c * (1.0 - weight) + v * weight for c, v in zip(centroid, vec)
        ]

    # -- 主入口 ------------------------------------------------------------

    def observe(self, vec: list[float]) -> VoiceprintObservation:
        """流式观测一个声纹切片：归入既有簇或开新簇（零语义判断）。"""
        if len(vec) != self._dim:
            raise ValueError(f"voiceprint vector must be {self._dim}-dim")
        signature = self._signature(vec)
        with self._lock:
            candidates: set[str] = set()
            for key in self._band_keys(signature):
                candidates |= self._buckets.get(key, set())
            best_id: str | None = None
            best_distance = self._match_hamming + 1
            for cluster_id in sorted(candidates):
                centroid_sig = self._signature(self._centroids[cluster_id])
                distance = self._hamming(signature, centroid_sig)
                if distance < best_distance:
                    best_id, best_distance = cluster_id, distance
            if best_id is not None and best_distance <= self._match_hamming:
                cluster_id = best_id
                size = self._sizes[cluster_id]
                self._centroids[cluster_id] = self._merge_centroid(
                    self._centroids[cluster_id], vec, size
                )
                self._sizes[cluster_id] = size + 1
                for key in self._band_keys(
                    self._signature(self._centroids[cluster_id])
                ):
                    self._buckets.setdefault(key, set()).add(cluster_id)
                return VoiceprintObservation(
                    cluster_id=cluster_id,
                    is_new_cluster=False,
                    hamming_to_centroid=best_distance,
                )
            self._cluster_counter += 1
            cluster_id = f"spk_temp_{self._cluster_counter:03d}"
            self._centroids[cluster_id] = list(vec)
            self._sizes[cluster_id] = 1
            for key in self._band_keys(signature):
                self._buckets.setdefault(key, set()).add(cluster_id)
            return VoiceprintObservation(
                cluster_id=cluster_id,
                is_new_cluster=True,
                hamming_to_centroid=0,
            )

    @property
    def cluster_count(self) -> int:
        with self._lock:
            return len(self._centroids)


# ======================================================================
# 门禁三：180 天 TTL 墓碑状态机
# ======================================================================

class VoiceprintRecord(BaseModel):
    """声纹生命周期记录：热表（活跃匹配）或归档区（墓碑）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: StrictStr
    first_contact: datetime
    last_contact: datetime
    entity_binding: StrictStr | None = None
    is_tombstone: bool = False
    tombstoned_at: datetime | None = None


class TombstoneSweepReport(BaseModel):
    """一次冷淘汰巡检的报告。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    swept_at: datetime
    tombstoned_ids: tuple[StrictStr, ...] = Field(default=())
    hot_table_size: StrictInt = Field(ge=0)
    archive_size: StrictInt = Field(ge=0)


class VoiceprintTTLRegistry:
    """声纹活跃热表 + 180 天 TTL 墓碑状态机。

    状态机：``ACTIVE（热表）`` → 满足「未绑定实体 && now - last_contact
    ≥ TTL」→ ``TOMBSTONED``（剥离至归档区）。已绑定核心关系的声纹
    永不冷淘汰（V3 §33-3 / R2-07 低频高价值不误清理）。
    """

    def __init__(self, ttl_days: int = TTL_DAYS) -> None:
        if ttl_days <= 0:
            raise ValueError("ttl_days must be positive")
        self._ttl = timedelta(days=ttl_days)
        self._lock = threading.RLock()
        self._hot: dict[str, VoiceprintRecord] = {}
        self._archive: dict[str, VoiceprintRecord] = {}

    def register(
        self,
        cluster_id: str,
        *,
        first_contact: datetime,
        last_contact: datetime | None = None,
        entity_binding: str | None = None,
    ) -> None:
        if last_contact is None:
            last_contact = first_contact
        with self._lock:
            if cluster_id in self._hot or cluster_id in self._archive:
                raise ValueError(f"cluster already registered: {cluster_id}")
            self._hot[cluster_id] = VoiceprintRecord(
                cluster_id=cluster_id,
                first_contact=first_contact,
                last_contact=last_contact,
                entity_binding=entity_binding,
            )

    def touch(self, cluster_id: str, at: datetime) -> None:
        """更新最后接触时间（接触即续命）。"""
        with self._lock:
            record = self._hot.get(cluster_id)
            if record is None:
                raise ValueError(f"cluster not in hot table: {cluster_id}")
            self._hot[cluster_id] = record.model_copy(
                update={"last_contact": at}
            )

    def bind_entity(self, cluster_id: str, entity_id: str) -> None:
        """绑定实体身份：豁免冷淘汰（核心关系声纹永存）。"""
        with self._lock:
            record = self._hot.get(cluster_id)
            if record is None:
                raise ValueError(f"cluster not in hot table: {cluster_id}")
            self._hot[cluster_id] = record.model_copy(
                update={"entity_binding": entity_id}
            )

    def sweep(self, now: datetime) -> TombstoneSweepReport:
        """冷淘汰巡检：到期瞬间置墓碑、剥离热表、移入归档区。"""
        with self._lock:
            expired = [
                cluster_id
                for cluster_id, record in self._hot.items()
                if record.entity_binding is None
                and now - record.last_contact >= self._ttl
            ]
            for cluster_id in sorted(expired):
                record = self._hot.pop(cluster_id)
                self._archive[cluster_id] = record.model_copy(
                    update={"is_tombstone": True, "tombstoned_at": now}
                )
            return TombstoneSweepReport(
                swept_at=now,
                tombstoned_ids=tuple(sorted(expired)),
                hot_table_size=len(self._hot),
                archive_size=len(self._archive),
            )

    def state(self, cluster_id: str) -> VoiceprintRecord:
        with self._lock:
            if cluster_id in self._hot:
                return self._hot[cluster_id]
            if cluster_id in self._archive:
                return self._archive[cluster_id]
            raise ValueError(f"unknown cluster: {cluster_id}")

    @property
    def hot_table_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._hot))

    @property
    def archive_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._archive))
