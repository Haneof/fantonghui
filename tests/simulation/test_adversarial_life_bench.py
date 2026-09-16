"""对抗生命数据发生器单测：配额、独立性、可复现性、噪声/证据边界。"""

from __future__ import annotations

from datetime import datetime, timezone

from aios_core.contracts.enums import ObjectType
from aios_core.perception.edge_stream_purifier import (
    EdgeStreamPurifier,
    RawEnvironmentText,
    RawHeartSample,
    RawImuSample,
    RawVisionFrame,
)
from aios_core.simulation.adversarial_life_bench import (
    SAGA_SEEDS,
    LifeArchetype,
    MassiveSyntheticLifeBench,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


def test_generator_is_independent_of_any_runtime_engine() -> None:
    """发生器只依赖标准库与自身数据类：不得引用存储/检索/认知引擎。"""

    import inspect

    from aios_core.simulation import adversarial_life_bench as module

    source = inspect.getsource(module)
    for forbidden in ("sqlite_store", "WorldStore", "search", "cognition.", "aios_core.storage"):
        assert forbidden not in source
    assert all(
        name in source
        for name in ("LifeArchetype", "SAGA_SEEDS", "MassiveSyntheticLifeBench")
    )


def test_quota_is_million_scale_and_covers_five_archetypes() -> None:
    bench = MassiveSyntheticLifeBench(seed=20260916, scale=1.0)
    counts = bench.counts()
    assert counts.total == 1_131_330
    assert counts.imu == 1_050_000
    assert counts.heart == 76_800
    assert counts.vision == 540
    assert counts.audio == 1_580
    assert counts.text == 2_410
    assert len(SAGA_SEEDS) == 5
    assert {spec.archetype for spec in SAGA_SEEDS} == set(LifeArchetype)


def test_stream_matches_the_declared_quota_exactly() -> None:
    # scale=0.2 下每条切片的配额都高于"12 个心率 epoch × 60 样本"的形态下限，
    # 因此声明配额与实产条数必须逐通道严格相等。
    bench = MassiveSyntheticLifeBench(seed=7, scale=0.2)
    declared = bench.counts()
    produced = {"imu": 0, "heart": 0, "vision": 0, "audio": 0, "text": 0}
    for raw in bench.generate_stream():
        if isinstance(raw, RawImuSample):
            produced["imu"] += 1
        elif isinstance(raw, RawHeartSample):
            produced["heart"] += 1
        elif isinstance(raw, RawVisionFrame):
            produced["vision"] += 1
        elif isinstance(raw, RawEnvironmentText):
            produced["text"] += 1
        else:
            produced["audio"] += 1
    assert produced == {
        "imu": declared.imu,
        "heart": declared.heart,
        "vision": declared.vision,
        "audio": declared.audio,
        "text": declared.text,
    }


def test_same_seed_reproduces_the_same_stream() -> None:
    first = list(MassiveSyntheticLifeBench(seed=99, scale=0.002).generate_stream())
    second = list(MassiveSyntheticLifeBench(seed=99, scale=0.002).generate_stream())
    assert [repr(item) for item in first] == [repr(item) for item in second]


def test_noise_and_core_texts_never_overlap() -> None:
    noise = {text for spec in SAGA_SEEDS for text in spec.noise_texts}
    core = {text for spec in SAGA_SEEDS for text in spec.core_texts}
    assert noise
    assert core
    assert noise & core == set()


def test_timeline_spans_three_years() -> None:
    bench = MassiveSyntheticLifeBench(seed=1, scale=0.001)
    moments: list[datetime] = []
    for raw in bench.generate_stream():
        stamp = getattr(raw, "t_us", None)
        if stamp is not None:
            moments.append(datetime.fromtimestamp(stamp / 1_000_000, tz=UTC))
    assert min(moments).year == 2024
    assert max(moments).year >= 2026
    assert (max(moments) - min(moments)).days > 500


def test_generator_contains_no_assertions_of_its_own() -> None:
    """禁止自编自答：发生器内部不得有任何 assert（验收判据只在测试层）。"""

    import ast
    import inspect

    from aios_core.simulation import adversarial_life_bench as module

    tree = ast.parse(inspect.getsource(module))
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Assert)] == []


def test_archetype_lookup_is_exact() -> None:
    bench = MassiveSyntheticLifeBench(seed=5, scale=0.002)
    seen: set[str] = set()
    for raw in bench.generate_stream():
        label = bench.archetype_of(raw)
        if label:
            seen.add(label)
    assert seen <= {spec.archetype.value for spec in SAGA_SEEDS}
    assert seen


def test_bench_stream_survives_the_edge_purifier_round_trip(tmp_path) -> None:
    store = SQLiteWorldStore(str(tmp_path / "bench.db"))
    purifier = EdgeStreamPurifier(store)
    report = purifier.ingest_raw_stream(
        MassiveSyntheticLifeBench(seed=3, scale=0.01).generate_stream()
    )
    purifier.flush()
    assert report.raw_samples_ingested > 10_000
    assert report.compression_ratio > 0.9
    observations = store.list_payloads(object_type=ObjectType.OBSERVATION)
    assert observations
    assert report.raw_image_bytes_retained == 0
