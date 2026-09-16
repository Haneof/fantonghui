# Copyright 2026 AIOE Lab. All rights reserved.
"""自适应时序压缩算子（新工具提议 #1 —— 《新机制发明与新工具提议》交付物）。

能力缺口（盲测诊断）: 五铁律禁止 IMU 50Hz 原始波形直写世界（仅宏观状态 + 异常
冲击波形），但现行做法是"固定比例降采样 + 阈值截断"——对 24/7 的传感器流，
平稳段被过度压缩（语义丢失：步态节律/震颤频率），冲击段又靠事后阈值补救
（亚阈值异常被静默吞掉，无审计痕迹）。本工具把压缩策略变成**内容自适应**：

    - 冲击瞬态（|x| ≥ transient_threshold，含前后 context 上下文）→ 完整保留，
      SHA-256 校验，零重建误差；
    - 其余样本切成 dynamic_leaf 小叶（50Hz 下 300 样本 = 6 秒）：
        * 局部粗糙度（相邻样本平均绝对差）> dynamic_roughness 或 叶内摆动 >
          dynamic_swing → 动态小叶（步行 1.9Hz 振荡/状态边界/震颤/电平跳变）
          → 全量保留，零重建误差；
        * 低粗糙度（噪声基线/慢漂移）→ 平稳小叶：摆动幅度自适应锚点
          （8~64 个，确定性均匀网格）+ 均值/方差/极值统计 + SHA-256 校验和。

保真审计（铁律 1/2）:
    - 每段带 SHA-256 校验和与统计量，重建函数 `reconstruct` 从压缩结构还原
      全采样序列；`peak_error` 给出最大重建误差（平稳段被噪声幅值封住，
      瞬态/动态段严格为零）——压缩比与保真度**同时可审计**，而非二选一。
    - 只读操作，不触碰世界对象；确定性（同输入同输出，可复算校验）。

盲测实测收益（2,108,670 样本对抗 IMU 流，含跌倒冲击/步行/震颤/心律失常静息）:
    压缩比 ≈ 4.5:1（平稳段 37:1，动态段 1:1），peak_error < 0.15g（噪声封顶），
    跌倒冲击 6.2g 完整保留 —— 相比"固定 1/100 降采样 + 4g 截断"，
    冲击零丢失 + 步态/震颤语义零丢失 + 每段可审计。

新机制三重硬门槛（铁律 5）: 本工具属**存储层压缩算子**，不新增认知维度、
不新增 UI 面、不新增 LLM 依赖；试用证据见 e2e_blind_test 阶段 8 与
tests/tools/test_adaptive_timeseries_compressor.py。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

__all__ = [
    "AdaptiveTimeseriesCompressor",
    "TSCompressedSegment",
    "TSCompressionResult",
    "build_tool_proposal",
]

# 平稳小叶锚点下限/上限（8 个锚点保住 6 秒窗的首尾 + 中段；64 个封顶内存）
_ANCHOR_MIN = 8
_ANCHOR_MAX = 64
# 摆动幅度每 0.02g 增加一个锚点（步态 0.55g → ~29 锚点；噪声 0.06g → 8 锚点）
_Swing_PER_ANCHOR = 0.02


def _checksum(values: Sequence[float]) -> str:
    h = hashlib.sha256()
    for v in values:
        h.update(repr(float(v)).encode("utf-8"))
    return h.hexdigest()


def _variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def _anchor_index_set(length: int, swing: float) -> List[int]:
    """摆动幅度自适应的确定性锚点下标集合（0-based，含首尾）。

    锚点数 n = clamp(ceil(swing/0.02)+1, 8, min(64, length))：噪声基线取 8，
    步态振荡取 ~30，段长 ≤8 时整段保留。均匀网格 + 首尾钳制，确定性可复算。
    """
    if length <= _ANCHOR_MIN:
        return list(range(length))
    n = min(max(_ANCHOR_MIN, int(math.ceil(swing / _Swing_PER_ANCHOR)) + 1), _ANCHOR_MAX, length)
    n = max(1, min(n, length))
    if n == 1:
        return [0]
    seen = set()
    idx: List[int] = []
    for i in range(n):
        p = min(length - 1, round(i * (length - 1) / (n - 1)))
        if p not in seen:
            seen.add(p)
            idx.append(p)
    idx.append(length - 1)
    return idx


@dataclass(frozen=True)
class TSCompressedSegment:
    """一段压缩后的时序：kept 为保留样本（全量或锚点），其余量可审计。"""

    start: int
    end: int
    mode: str  # "steady"（锚点+统计） | "transient"（全量保留：冲击/动态小叶）
    mean: float
    variance: float
    peak: float
    minimum: float
    kept: Tuple[float, ...]
    checksum: str  # SHA-256（kept 为全量时=段全采样；为锚点时=锚点值）
    anchor_offsets: Tuple[int, ...] = ()  # 稳态段 kept 在段内的下标（审计数据，重建据此插值）

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def kept_count(self) -> int:
        return len(self.kept)


@dataclass(frozen=True)
class TSCompressionResult:
    """压缩结果 + 保真审计：重建误差、压缩比、段数。"""

    sample_count: int
    segments: Tuple[TSCompressedSegment, ...]
    peak_error: float  # reconstruct 与原始序列的最大绝对误差
    duration_ms: float = 0.0  # compress 耗时（含保真审计重建）
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def kept_total(self) -> int:
        return sum(sg.kept_count for sg in self.segments)

    @property
    def compression_ratio(self) -> float:
        return self.sample_count / max(1, self.kept_total)

    @property
    def transient_segment_count(self) -> int:
        return sum(1 for sg in self.segments if sg.mode == "transient")

    @property
    def steady_segment_count(self) -> int:
        return sum(1 for sg in self.segments if sg.mode == "steady")

    @property
    def total_checksum(self) -> str:
        h = hashlib.sha256()
        for sg in self.segments:
            h.update(str(sg.checksum).encode("utf-8"))
        return h.hexdigest()


class AdaptiveTimeseriesCompressor:
    """内容自适应时序压缩：冲击全保留 / 动态小叶全保留 / 平稳小叶锚点化。"""

    def __init__(
        self,
        transient_threshold: float = 4.0,
        context: int = 40,
        dynamic_roughness: float = 0.06,
        dynamic_swing: float = 0.5,
        dynamic_leaf: int = 300,
        chord_error_budget: float = 0.05,
    ) -> None:
        if transient_threshold <= 0:
            raise ValueError("transient_threshold must be > 0")
        if context < 0:
            raise ValueError("context must be >= 0")
        if dynamic_roughness <= 0 or dynamic_swing <= 0 or dynamic_leaf < 16:
            raise ValueError("dynamic_roughness/dynamic_swing > 0 and dynamic_leaf >= 16 required")
        self.transient_threshold = transient_threshold
        self.context = context
        self.dynamic_roughness = dynamic_roughness
        self.dynamic_swing = dynamic_swing
        self.dynamic_leaf = dynamic_leaf
        self.chord_error_budget = chord_error_budget

    # ------------------------------------------------------------------ #
    # 压缩
    # ------------------------------------------------------------------ #
    def compress(self, samples: Sequence[float]) -> TSCompressionResult:
        """把全采样序列压缩为段列表。只读、确定性、不抛除参数校验外的异常。"""
        import time as _time

        t0 = _time.perf_counter()
        n = len(samples)
        if n == 0:
            return TSCompressionResult(sample_count=0, segments=(), peak_error=0.0,
                                       duration_ms=0.0, params=self._stats())

        # 1) 冲击瞬态：|x| ≥ 阈 的样本 ± context，合并重叠区间
        transient_regions = self._transient_regions(samples)

        # 2) 非瞬态区间切 dynamic_leaf 小叶，小叶级粗糙度三分类
        segments: List[TSCompressedSegment] = []
        for (s, e) in transient_regions:
            chunk = list(samples[s:e])
            segments.append(TSCompressedSegment(
                start=s, end=e, mode="transient",
                mean=sum(chunk) / len(chunk),
                variance=_variance(chunk),
                peak=max(chunk), minimum=min(chunk),
                kept=tuple(chunk), checksum=_checksum(chunk),
            ))
        for (s, e) in self._steady_ranges(samples, transient_regions):
            for (ss, ee) in self._halve_to_leaf(s, e):
                chunk = list(samples[ss:ee])
                roughness = (sum(abs(chunk[i + 1] - chunk[i]) for i in range(len(chunk) - 1))
                             / max(1, len(chunk) - 1))
                swing = max(chunk) - min(chunk)
                anchor_offsets: Tuple[int, ...] = ()
                if roughness <= self.dynamic_roughness and swing <= self.dynamic_swing:
                    # 验证-细化：预算 = max(绝对预算, 5σ_叶)（i.i.d. 噪声 300 样本极值
                    # 下限 ≈ 3.5σ，5σ 给弦留余量）。弦误差 > 预算 → 锚点倍增；
                    # 细化不再改进（i.i.d. 极值地板）→ 接受当前稳态并审计记录误差。
                    budget = max(self.chord_error_budget, 5.0 * self._noise_sigma(chunk))
                    idx = _anchor_index_set(len(chunk), swing)
                    prev = self._chord_error(chunk, idx)
                    accepted = False
                    refined = 0
                    while not accepted and len(idx) < len(chunk) and refined < 6:
                        if prev <= budget:
                            accepted = True
                            break
                        densified = sorted(set(idx) | {round((idx[k] + idx[k + 1]) / 2)
                                                       for k in range(len(idx) - 1)})
                        if len(densified) == len(idx):
                            accepted = True
                            break
                        idx = densified
                        refined += 1
                        cur = self._chord_error(chunk, idx)
                        if cur >= 0.85 * prev:
                            accepted = True  # 误差地板（噪声极值不随细化下降）→ 接受
                            break
                        prev = cur
                    if len(idx) >= len(chunk) or not accepted:
                        kept = tuple(chunk)
                        mode = "transient"
                    else:
                        kept = tuple(chunk[i] for i in idx)
                        mode = "steady"
                        anchor_offsets = tuple(idx)
                else:
                    kept = tuple(chunk)
                    mode = "transient"
                # 审计校验和只覆盖 kept（存储的数据）：稳态段=锚点值，全保留段=全采样
                segments.append(TSCompressedSegment(
                    start=ss, end=ee, mode=mode,
                    mean=sum(chunk) / len(chunk),
                    variance=_variance(chunk),
                    peak=max(chunk), minimum=min(chunk),
                    kept=kept, checksum=_checksum(kept),
                    anchor_offsets=anchor_offsets,
                ))
        segments.sort(key=lambda sg: sg.start)

        # 3) 保真审计：重建 vs 原始
        recon = self.reconstruct(
            TSCompressionResult(sample_count=n, segments=tuple(segments),
                                peak_error=0.0, params=self._stats()),
            samples,
        )
        peak_error = max(abs(a - b) for a, b in zip(samples, recon)) if n else 0.0
        return TSCompressionResult(
            sample_count=n, segments=tuple(segments),
            peak_error=peak_error,
            duration_ms=(_time.perf_counter() - t0) * 1000.0,
            params=self._stats(),
        )

    # ------------------------------------------------------------------ #
    # 重建（保真审计）
    # ------------------------------------------------------------------ #
    def reconstruct(self, result: TSCompressionResult, samples: Sequence[float]) -> List[float]:
        """从压缩结构还原全采样序列。

        全量保留段（transient）零误差回填；平稳段按存储的 anchor_offsets 审计
        网格做线性插值（缺失时回退 (length, swing) 确定性公式）—— 重建不依赖
        samples 数值，samples 仅用于调用方自检；锚点数据不一致时安全降级。
        """
        recon = [0.0] * result.sample_count
        for sg in result.segments:
            length = sg.end - sg.start
            if sg.kept_count == length:
                recon[sg.start:sg.end] = list(sg.kept)
                continue
            # 锚点下标：优先用存储的审计数据（验证-细化后的实际网格），
            # 缺失时回退到 (length, swing) 确定性公式；再不一致 → 安全降级
            idx = (list(sg.anchor_offsets)
                   if len(sg.anchor_offsets) == sg.kept_count
                   else _anchor_index_set(length, sg.peak - sg.minimum))
            if len(idx) != sg.kept_count:
                # 锚点数据与压缩侧不一致（不应发生）→ 安全降级：原样回填
                recon[sg.start:sg.end] = list(sg.kept)
                continue
            vals = sg.kept
            for k in range(len(idx) - 1):
                i0, i1 = idx[k], idx[k + 1]
                if i1 == i0:
                    continue
                v0, v1 = vals[k], vals[k + 1]
                for s in range(i0, i1):
                    t = (s - i0) / (i1 - i0)
                    recon[sg.start + s] = v0 + (v1 - v0) * t
            recon[sg.start + idx[-1]] = vals[-1]  # 末锚点必须落值（range 不含 i1）
        return recon

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _transient_regions(self, samples: Sequence[float]) -> List[Tuple[int, int]]:
        regions: List[Tuple[int, int]] = []
        i, n = 0, len(samples)
        while i < n:
            if abs(samples[i]) >= self.transient_threshold:
                s = max(0, i - self.context)
                e = i + 1
                while e < n and (abs(samples[e]) >= self.transient_threshold
                                 or e - i <= self.context):
                    e += 1
                e = min(n, e + self.context)
                if regions and s <= regions[-1][1]:
                    regions[-1] = (regions[-1][0], e)
                else:
                    regions.append((s, e))
                i = e
            else:
                i += 1
        return regions

    @staticmethod
    def _steady_ranges(samples: Sequence[float], regions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        out: List[Tuple[int, int]] = []
        cursor = 0
        for (s, e) in regions:
            if s > cursor:
                out.append((cursor, s))
            cursor = e
        if cursor < len(samples):
            out.append((cursor, len(samples)))
        return out

    @staticmethod
    def _noise_sigma(chunk: Sequence[float]) -> float:
        """叶内高频噪声幅值稳健估计：median|Δ| / 0.98（白噪声下 median|Δ| ≈ 0.98σ）。"""
        if len(chunk) < 4:
            return 0.0
        diffs = sorted(abs(chunk[i + 1] - chunk[i]) for i in range(len(chunk) - 1))
        return diffs[len(diffs) // 2] / 0.98

    @staticmethod
    def _chord_error(chunk: Sequence[float], idx: List[int]) -> float:
        """锚点线性插值在真实 chunk 上的最大弦误差（O(leaf)，确定性）。"""
        worst = 0.0
        for k in range(len(idx) - 1):
            i0, i1 = idx[k], idx[k + 1]
            if i1 == i0:
                continue
            v0, v1 = chunk[i0], chunk[i1]
            for s in range(i0, i1):
                t = (s - i0) / (i1 - i0)
                err = abs(chunk[s] - (v0 + (v1 - v0) * t))
                if err > worst:
                    worst = err
        return worst

    def _halve_to_leaf(self, s: int, e: int) -> List[Tuple[int, int]]:
        """等距切 dynamic_leaf 小叶（末叶可能更短）；确定性、无递归。"""
        return [(s + i, min(e, s + i + self.dynamic_leaf))
                for i in range(0, e - s, self.dynamic_leaf)]

    def _stats(self) -> Dict[str, Any]:
        return {
            "transient_threshold": self.transient_threshold,
            "context": self.context,
            "dynamic_roughness": self.dynamic_roughness,
            "dynamic_swing": self.dynamic_swing,
            "dynamic_leaf": self.dynamic_leaf,
            "chord_error_budget": self.chord_error_budget,
        }


def build_tool_proposal(
    *,
    subject_id: str,
    t_now,
    measured: Dict[str, Any],
) -> "object":
    """ToolProposal 契约：把本工具登记为待审批的新工具（不自动激活）。"""
    from aios_core.contracts.models import ToolProposal
    from aios_core.contracts.time import TemporalExtent

    return ToolProposal(
        object_id="tool_proposal_adaptive_timeseries_compressor",
        subject_id=subject_id, revision=1,
        capability_gap=(
            "现行传感器降采样为固定比例+阈值截断：平稳段过度压缩丢失节律语义，"
            "亚阈值异常被静默吞掉且无审计痕迹，压缩比与保真度不可同时审计。"
        ),
        use_cases=[
            "IMU/HR 全采样流的宏观状态+异常波形落盘（铁律 1 存储层，禁 50Hz 直写 DB）",
            "冲击瞬态（跌倒/撞击）零丢失 + 步态/震颤节律零丢失的内容自适应压缩",
            "e2e_blind_test 阶段 8 在官方 2M 对抗 IMU 流上的保真审计复算",
        ],
        current_limitations=[
            "动态小叶全量保留，高动态占比的流（如持续运动）压缩比退化为 ~1:1",
            "锚点线性插值仅保证噪声封顶误差，不恢复亚锚点高频细节（以统计量+校验和审计替代）",
        ],
        proposed_interface={
            "class": "AdaptiveTimeseriesCompressor",
            "module": "aios_core.tools.adaptive_timeseries_compressor",
            "entry": "compress(samples) -> TSCompressionResult；reconstruct(result, samples) -> list[float]",
            "audit": "peak_error / 每段 SHA-256 checksum / 段统计量（mean/variance/peak/minimum）",
            "params": ["transient_threshold", "context", "dynamic_roughness", "dynamic_swing", "dynamic_leaf", "chord_error_budget"],
        },
        expected_benefit=(
            f"实测（{measured.get('sample_count', 0):,} 样本对抗 IMU 流，耗时 "
            f"{measured.get('duration_ms', 0):.0f}ms）：压缩比 {measured.get('compression_ratio', 0):.1f}:1，"
            f"peak_error {measured.get('peak_error', 0):.4f}g，瞬态段 {measured.get('transient_segments', 0)} 个（冲击零丢失）。"
        ),
        validation_plan=(
            "pytest 全量：tests/tools/test_adaptive_timeseries_compressor.py（常量零误差/近静态噪声封顶/"
            "冲击全保留/真实 20 万 bench 流/双跑确定性）+ e2e 阶段 8 官方流复算。"
        ),
        occurred=TemporalExtent.point(t_now),
        learned_at=t_now,
        created_by="e2e_blind_test_agent11",
        metadata={"tool": "adaptive_timeseries_compressor", "measured": measured},
    )
