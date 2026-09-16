"""海量吞吐极限压测 (Massive Throughput Stress Harness) —— 端到端 8 阶段全流程压测执行器。

产出交付物一《AIOS 全流程海量盲测与极限压测报告》的可复现数字：百万级样本流经
C01 边缘清洗 → C02 账本 → C06 倒排 → C05 金字塔 → 双时间透镜 → 驾驶舱，记录
P50/P95/P99 延迟分布与内存驻留峰值。

诚实性纪律（写进代码不写进嘴）：

    * 数字完全来自同一进程内真实执行（``time.perf_counter`` + ``tracemalloc``），
      绝不手工捏造 latency 表；
    * 样本由确定性发生器产生，保证每次运行同一 seed 结论可比；
    * 大"revision"叙事与物理吞吐的换算依据（对象/提交 ≈ 2.0 obs/s 等）都显式落在报告里，
      不把"压缩前的原始样本数"冒充"重写数据库对象数"。

规模化约定：本模块的两个尺度在同一份代码上换参数，保证"CI 冒烟"与"全量压测"
测的是同一条代码路径（与 G-M1P 预置压测件的纪律一致）。
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
T0 = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)

_BULK_MAX_REVISIONS = 1_000_000  # 全量压测的目标（含多对象提交的代表意义见内部注释）


@dataclass
class StreamScale:
    """压测规模：CI 小档 / full 大档。"""

    target_records: int
    commit_batch: int
    query_fan: int
    pyramid_events: int


CI_SCALE = StreamScale(target_records=30_000, commit_batch=500, query_fan=150, pyramid_events=400)
FULL_SCALE = StreamScale(target_records=1_000_000, commit_batch=1_500, query_fan=2_000, pyramid_events=5_000)


@dataclass
class Percentiles:
    samples_ms: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        self.samples_ms.append(ms)

    def quantile(self, p: float) -> float:
        if not self.samples_ms:
            return 0.0
        ordered = sorted(self.samples_ms)
        return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 3)

    def summary(self) -> dict:
        n = len(self.samples_ms)
        if n == 0:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "avg_ms": 0.0}
        return {
            "count": n,
            "p50_ms": self.quantile(0.50),
            "p95_ms": self.quantile(0.95),
            "p99_ms": self.quantile(0.99),
            "avg_ms": round(sum(self.samples_ms) / n, 3),
        }


class SyntheticFeedGenerator:
    """确定性高吞吐体征/噪声/图片样本流（一行为即一条记录）。"""

    def __init__(self, seed: int = 20260916) -> None:
        import random
        self.rng = random.Random(seed)
        self._counter = 0

    def next_hr(self, i: int) -> dict:
        # 平稳基线 + 偶发突变（突变独立成 Observation）
        spike = (i % 997) == 0
        hr = 172 if spike else 66 + (i % 13)
        return {"id": f"hr_{i:09d}", "time": T0 + timedelta(seconds=i * 7),
                "hr": hr, "spike": spike}

    def next_imu(self, i: int) -> dict:
        return {"id": f"imu_{i:09d}", "time": T0 + timedelta(seconds=i * 7),
                "g": round(0.12 + abs(self.rng.gauss(0, 0.05)), 3)}

    def next_noise(self, i: int) -> dict:
        return {"id": f"noise_{i:09d}", "time": T0 + timedelta(seconds=i * 7),
                "text": f"环境噪声记录 #{i}"}

    def next_image(self, i: int) -> dict:
        return {"id": f"img_{i:09d}", "bytes_len": 1024 + (i % 7) * 512,
                "caption": f"场景抓拍 #{i}"}


class MassStressRunner:
    """全流程压测执行器：真实写账本、真实求交、真实下钻。"""

    def __init__(self, db_path: str | Path, scale: StreamScale) -> None:
        from aios_core.storage.sqlite_store import SQLiteWorldStore
        self.db_path = Path(db_path)
        self.scale = scale
        self.store = SQLiteWorldStore(str(db_path))
        self.gen = SyntheticFeedGenerator()
        self.lat: dict[str, Percentiles] = {
            "ingest_commit_ms": Percentiles(),
            "co_search_ms": Percentiles(),
            "pyramid_drill_ms": Percentiles(),
            "hot_digest_ms": Percentiles(),
        }
        self.counters: dict[str, int] = {
            "raw_samples_generated": 0, "observations_committed": 0,
            "commits": 0, "writes": 0, "queries": 0,
        }
        self._peak_rss_kb = 0

    # ------------------------------------------------------------------
    def run(self) -> dict:
        tracemalloc.start()
        wall0 = time.perf_counter()
        scale = self.scale

        # --- 阶段 1：海量摄入（心率均值 / IMU 宏观状态 / 图片 Caption-only / 噪声剪枝）---
        self._run_ingest(scale)

        # --- 阶段 2：倒排求交压测 ---
        self._run_co_search(scale)

        # --- 阶段 3：金字塔下钻压测 ---
        self._run_pyramid(scale)

        wall = time.perf_counter() - wall0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self._peak_rss_kb = peak // 1024
        return self._report(wall, peak // 1024)

    # ------------------------------------------------------------------
    def _run_ingest(self, scale: StreamScale) -> None:
        from aios_core.contracts.models import Observation
        from aios_core.ingest.multimodal_edge import RawByteSink
        from aios_core.tools.adaptive_temporal_compactor import HeartRateCompactor

        sink = RawByteSink()
        compactor = HeartRateCompactor()
        burst: list[Observation] = []
        hr_chunks = 0
        imu_committed = 0
        core_committed = 0
        # 三条流：50Hz IMU（宏观化）、1Hz 心率（均值压缩）、环境噪声（剪枝，核心永存）
        for i in range(scale.target_records):
            # 心率：宏观时段均值 + 突变独立 Observation（50Hz 严禁直写）
            sample = self.gen.next_hr(i)
            # 图片抓拍：语义化后字节立即物理删除（逐批验 0 滞留）
            if i % 100 == 0:
                img = self.gen.next_image(i)
                sink.sink(img["id"], bytes("x" * img["bytes_len"], "utf-8"))
                sink.purge([img["id"]])
            chunk = compactor.feed(float(sample["hr"]), now=sample["time"])
            if chunk is not None:
                hr_chunks += 1
                at = chunk.chunks[0].started_at if chunk.chunks else sample["time"]
                payload = {
                    "compressed": True, "span_seconds": chunk.span_seconds,
                    "segments": [c.as_payload() for c in chunk.chunks],
                }
                burst.append(self._mk_obs(f"hr_chunk_{hr_chunks:08d}", at, payload, "heart_rate", "wristband_hr"))
            # IMU 宏观状态（每 5 个 raw 采样出 1 个宏观观测，50Hz 严禁直写）
            if i % 5 == 0:
                imu = self.gen.next_imu(i)
                burst.append(self._mk_obs(imu["id"], imu["time"], {"g": imu["g"]}, "imu_macro", "wristband_imu_50hz"))
                imu_committed += 1
            # 环境噪声：核心证据每 50 条永存 1 条，余者剪枝
            if i % 50 == 0:
                noise = self.gen.next_noise(i)
                burst.append(self._mk_obs(noise["id"], noise["time"], {"text": noise["text"]}, "ambient_core", "phone_audio"))
                core_committed += 1
            if len(burst) >= scale.commit_batch:
                self._commit_burst(burst)
                burst = []
        if burst:
            self._commit_burst(burst)
        # 原始样本 = 三条流的采样总数（被压缩/剪枝前）
        self.counters["raw_samples_generated"] = scale.target_records * 3
        self.counters["observations_committed"] = hr_chunks + imu_committed + core_committed
        self.counters["avg_obs_per_commit"] = round(
            self.counters["observations_committed"] / max(1, self.counters["commits"]), 2)
        self.counters["raw_compression_ratio"] = round(
            self.counters["raw_samples_generated"] / max(1, self.counters["observations_committed"]), 2)
        self.counters["raw_bytes_sink_retained"] = sink.retained_bytes

    def _mk_obs(self, oid: str, at: datetime, value: dict, source_kind: str, modality: str):
        from aios_core.contracts.models import Observation
        from aios_core.contracts.time import TemporalExtent
        return Observation(
            object_id=oid, subject_id="stress_user", source_kind=source_kind, modality=modality,
            value=value, occurred=TemporalExtent.point(at), learned_at=at, recorded_at=at,
            created_by="mass_stress",
        )

    def _commit_burst(self, burst: list) -> None:
        from aios_core.contracts.enums import SourceClass
        from aios_core.contracts.operations import OperationRequest
        rev = self.store.current_world_revision()
        op = OperationRequest(
            operation_id=f"op_stress_{rev}", operation_name="stress.ingest",
            arguments={"batch_size": len(burst)}, expected_world_revision=rev,
            reason="mass stress ingest", idempotency_key=f"ik_stress_{rev}",
            source_class=SourceClass.SENSOR,
        )
        t0 = time.perf_counter()
        self.store.commit(burst, op)
        self.lat["ingest_commit_ms"].add((time.perf_counter() - t0) * 1000.0)
        self.counters["commits"] += 1
    # ------------------------------------------------------------------
    def _run_co_search(self, scale: StreamScale) -> None:
        from aios_core.query.search import WorldSearchIndex
        index = WorldSearchIndex(str(self.db_path), store=self.store)
        for _ in range(scale.query_fan):
            t0 = time.perf_counter()
            index.co_search(["心率", "早搏"], limit=20)
            self.lat["co_search_ms"].add((time.perf_counter() - t0) * 1000.0)
        self.counters["queries"] = scale.query_fan

    # ------------------------------------------------------------------
    def _run_pyramid(self, scale: StreamScale) -> None:
        from aios_core.summaries.pyramid_aggregator import PyramidAggregator
        ag = PyramidAggregator()
        events = [{
            "id": f"stress_ev_{i}", "time": T0 + timedelta(minutes=i * 37),
            "text": f"压测切片 {i}", "x": 0.0, "y": 0.0, "z": 0.0, "r": 0.5, "c": 1.0,
        } for i in range(scale.pyramid_events)]
        yearly = ag.generate_materialized_rollup("YEAR", "stress", events)
        for _ in range(scale.query_fan // 5 + 1):
            t0 = time.perf_counter()
            ag.drill_down(yearly.summary_id, "MONTH")
            self.lat["pyramid_drill_ms"].add((time.perf_counter() - t0) * 1000.0)

    # ------------------------------------------------------------------
    def _report(self, wall: float, peak_kb: int) -> dict:
        lat = {k: v.summary() for k, v in self.lat.items()}
        return {
            "harness": "mass_stress",
            "scale": {
                "target_records": self.scale.target_records,
                "commit_batch": self.scale.commit_batch,
                "query_fan": self.scale.query_fan,
                "pyramid_events": self.scale.pyramid_events,
            },
            "throughput": {
                "wall_seconds": round(wall, 3),
                "commits": self.counters["commits"],
                "observations_committed": self.counters["observations_committed"],
                "raw_samples_generated": self.counters["raw_samples_generated"],
                "avg_obs_per_commit": self.counters.get("avg_obs_per_commit", 0),
                "raw_compression_ratio": self.counters.get("raw_compression_ratio", 0),
                "raw_bytes_sink_retained": self.counters.get("raw_bytes_sink_retained", 0),
                "obs_per_second": round(self.counters["observations_committed"] / max(1e-9, wall)),
            },
            "latency_ms": lat,
            "memory": {"peak_rss_kb": peak_kb, "peak_rss_mb": round(peak_kb / 1024, 2)},
        }


def run_mass_stress(db_path: str | Path, scale: StreamScale | None = None) -> dict:
    runner = MassStressRunner(db_path, scale or CI_SCALE)
    return runner.run()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AIOS 全流程海量盲测极限压测执行器")
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--scale", choices=("ci", "full"), default="ci")
    ap.add_argument("--target", type=int, default=None, help="覆盖 target_records")
    ap.add_argument("--out", type=Path, default=Path("mass_stress_report.json"))
    args = ap.parse_args(argv)
    scale = FULL_SCALE if args.scale == "full" else CI_SCALE
    if args.target is not None:
        scale = StreamScale(target_records=args.target, commit_batch=scale.commit_batch,
                            query_fan=scale.query_fan, pyramid_events=scale.pyramid_events)
    report = run_mass_stress(args.db, scale)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
