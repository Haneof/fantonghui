"""维度曲线系统：记录、查询、趋势分析。

宪法第七章：不在底层硬件做导数计算，在崩溃、精力消耗等高维认知趋势上
标注Velocity与Acceleration趋势属性，形成维度演化的时序曲线。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.models import DimensionCurvePoint
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import utc_now


class DimensionCurveTracker:
    """维度曲线追踪器：记录、查询、趋势分析。"""

    def __init__(self, subject_id: str):
        self._subject_id = subject_id
        self._points: dict[str, list[DimensionCurvePoint]] = {}  # dimension_id -> sorted points
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"dcp-{self._subject_id}-{self._counter:06d}"

    def record_point(
        self,
        dimension_ref: ObjectRef,
        value: float,
        point_time: datetime,
        *,
        granularity: str = "day",
        source_summary_ref: ObjectRef | None = None,
        source_evidence_set_ref: ObjectRef | None = None,
        confidence: float = 0.5,
        now: datetime | None = None,
    ) -> DimensionCurvePoint:
        """记录一个维度曲线数据点，自动计算速度和加速度。"""
        ts = now or utc_now()
        dim_id = dimension_ref.object_id

        # 获取该维度已有的点
        existing = self._points.get(dim_id, [])

        # 计算 velocity（与上一个点的差值/时间差）
        velocity = None
        acceleration = None
        if existing:
            prev = existing[-1]
            dt_seconds = (point_time - prev.point_time).total_seconds()
            if dt_seconds > 0:
                velocity = (value - prev.value) / dt_seconds
                if prev.velocity is not None:
                    acceleration = (velocity - prev.velocity) / dt_seconds

        # 检测异常
        anomaly_flag = False
        anomaly_desc = None
        if len(existing) >= 3:
            recent_values = [p.value for p in existing[-3:]]
            avg = sum(recent_values) / len(recent_values)
            std = (sum((v - avg) ** 2 for v in recent_values) / len(recent_values)) ** 0.5
            if std > 0 and abs(value - avg) > 3 * std:
                anomaly_flag = True
                anomaly_desc = f"值 {value:.2f} 偏离近3点均值 {avg:.2f} 超过3倍标准差 {std:.2f}"

        point = DimensionCurvePoint(
            object_id=self._next_id(),
            subject_id=self._subject_id,
            learned_at=ts,
            recorded_at=ts,
            created_by="dimension_curve_tracker",
            dimension_ref=dimension_ref,
            point_time=point_time,
            value=value,
            velocity=velocity,
            acceleration=acceleration,
            confidence=confidence,
            source_summary_ref=source_summary_ref,
            source_evidence_set_ref=source_evidence_set_ref,
            anomaly_flag=anomaly_flag,
            anomaly_description=anomaly_desc,
            granularity=granularity,
        )

        if dim_id not in self._points:
            self._points[dim_id] = []
        self._points[dim_id].append(point)
        # 保持时间排序
        self._points[dim_id].sort(key=lambda p: p.point_time)

        return point

    def get_curve(
        self,
        dimension_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[DimensionCurvePoint]:
        """获取某个维度在指定时间范围内的曲线点。"""
        points = self._points.get(dimension_id, [])
        if start is not None:
            points = [p for p in points if p.point_time >= start]
        if end is not None:
            points = [p for p in points if p.point_time <= end]
        return points

    def get_latest_point(self, dimension_id: str) -> DimensionCurvePoint | None:
        """获取某个维度的最新曲线点。"""
        points = self._points.get(dimension_id, [])
        return points[-1] if points else None

    def detect_trend(
        self, dimension_id: str, *, window_size: int = 7
    ) -> dict[str, Any]:
        """检测维度趋势：上升/下降/平稳/拐点。
        
        返回结构：
        {
            "trend": "rising" | "falling" | "stable" | "inflection",
            "velocity_avg": float,
            "acceleration_avg": float,
            "data_points": int,
            "anomaly_count": int,
        }
        """
        points = self._points.get(dimension_id, [])
        if len(points) < 2:
            return {
                "trend": "insufficient_data",
                "velocity_avg": 0.0,
                "acceleration_avg": 0.0,
                "data_points": len(points),
                "anomaly_count": 0,
            }

        window = points[-window_size:]
        velocities = [p.velocity for p in window if p.velocity is not None]
        accelerations = [p.acceleration for p in window if p.acceleration is not None]
        anomaly_count = sum(1 for p in window if p.anomaly_flag)

        v_avg = sum(velocities) / len(velocities) if velocities else 0.0
        a_avg = sum(accelerations) / len(accelerations) if accelerations else 0.0

        # 判断趋势
        threshold = 1e-6
        if accelerations and any(a > 0 for a in accelerations[:len(accelerations)//2]) and any(a < 0 for a in accelerations[len(accelerations)//2:]):
            trend = "inflection"
        elif v_avg > threshold:
            trend = "rising"
        elif v_avg < -threshold:
            trend = "falling"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "velocity_avg": v_avg,
            "acceleration_avg": a_avg,
            "data_points": len(window),
            "anomaly_count": anomaly_count,
        }

    def get_anomalies(
        self,
        dimension_id: str | None = None,
    ) -> list[DimensionCurvePoint]:
        """获取异常曲线点。"""
        if dimension_id:
            points = self._points.get(dimension_id, [])
        else:
            points = [p for ps in self._points.values() for p in ps]
        return [p for p in points if p.anomaly_flag]

    def get_all_dimensions(self) -> list[str]:
        """获取所有有曲线数据的维度ID。"""
        return list(self._points.keys())
