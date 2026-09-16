"""MEGA-PIPELINE 新机制发明件单测：

  TP-001 AdaptiveTemporalCompactor —— 平稳塌缩均值、突变逐拍、保护环、
    不达标段诚实退化（粘性真值 > 压缩率）；
  TP-002 DualLensProjector —— AS_KNOWN/ANNOTATED 双透镜同源同指纹，
    铁律 2 的可审计表达；
  ToolProposal 一等对象本身过契约校验（R4 lingua：object_type=tool_proposal）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_core.contracts.models import ToolProposal
from aios_core.query.adaptive_temporal_compactor import (
    AdaptiveTemporalCompactor,
    Beat,
    GUARD_RING,
    MIN_BUCKET_BEATS,
    SPIKE_DELTA_BPM,
)
from aios_core.query.dual_lens_projector import DualLensProjector
from tests.unit.conftest import world_kwargs

T0 = datetime(2026, 9, 10, 6, 0, 0, tzinfo=timezone.utc)


def _steady_beats(n: int, bpm: float = 63.0) -> list[Beat]:
    return [
        Beat(ts=(T0 + timedelta(seconds=30 * i)).isoformat(),
             kind="heart_rate", value=bpm + (0.3 if i % 2 else -0.3))
        for i in range(n)
    ]


def test_steady_stream_collapses_into_one_mean_bucket():
    plan = AdaptiveTemporalCompactor().compact(_steady_beats(240))
    assert len(plan.buckets) == 1
    bucket = plan.buckets[0]
    assert bucket.beat_count == 240
    assert 62.0 <= bucket.mean <= 64.0
    assert plan.spikes == ()
    assert plan.compression_ratio >= 200, "平稳期必须兑现铁律 4 的省存储面"


def test_spike_beats_survive_individually_with_guard_ring():
    beats = _steady_beats(200)
    mid = 100
    spikes = _steady_beats(4)
    for k, b in enumerate(spikes):
        beats[mid + k] = Beat(ts=b.ts, kind="heart_rate", value=110 + k)
    plan = AdaptiveTemporalCompactor().compact(beats)
    spike_values = {round(b.value) for b in plan.spikes}
    assert {110, 111, 112, 113} <= spike_values, "突变拍一拍不许丢"
    # 保护环：峰值前后 GUARD_RING 拍也被独立保留
    assert len(plan.spikes) >= 4 + 2 * min(GUARD_RING, mid)
    assert plan.buckets, "剩余平稳段仍应塌缩"
    sum_parts = plan.stats["bucket_beats"] + len(plan.spikes)
    assert sum_parts == plan.input_beats, "不重不漏恒等式"


def test_imu_shock_is_always_independent():
    beats = _steady_beats(60)
    beats[30] = Beat(ts=beats[30].ts, kind="imu_shock", value=9.8, shock=True)
    plan = AdaptiveTemporalCompactor().compact(beats)
    assert any(b.shock for b in plan.spikes), "跌倒冲击绝不进均值"
    assert any(b.kind == "imu_shock" for b in plan.spikes)


def test_short_nonconforming_segment_degrades_honestly():
    # 不足 MIN_BUCKET_BEATS 的短段：压不成桶便逐拍保真
    plan = AdaptiveTemporalCompactor().compact(_steady_beats(MIN_BUCKET_BEATS - 1))
    assert plan.buckets == ()
    assert len(plan.spikes) == MIN_BUCKET_BEATS - 1
    assert plan.stats["spill_beats"] == MIN_BUCKET_BEATS - 1


def test_compaction_identity_over_random_flux():
    beats = _steady_beats(500)
    for i in range(0, 500, 37):
        beats[i] = Beat(ts=beats[i].ts, kind="heart_rate",
                        value=beats[i].value + SPIKE_DELTA_BPM + 5)
    plan = AdaptiveTemporalCompactor().compact(beats)
    assert (plan.stats["bucket_beats"] + len(plan.spikes)) == 500


# ---------------------------------------------------------------------------
# TP-002 双透镜
# ---------------------------------------------------------------------------


def _world_rows(now: datetime) -> list[dict]:
    return [
        {"object_id": "c-1", "object_type": "claim",
         "content": "王建国承诺年底还款 50 万", "learned_at": "2024-03-01T09:00:00+00:00"},
        {"object_id": "c-2", "object_type": "claim",
         "content": "王建国微信说过两天工程款到就还", "learned_at": "2025-06-01T10:00:00+00:00"},
        {"object_id": "rip-1", "object_type": "reinterpretation",
         "target_ref": {"object_id": "c-1", "revision": 1},
         "slot": "meaning", "statement": "朝阳法院判合同诈骗罪成立，",
         "learned_at": "2026-09-16T08:00:00+00:00"},
    ]


def test_dual_lenses_share_identical_base_with_overlay_differing():
    rows = _world_rows(datetime.now(timezone.utc))
    views = DualLensProjector().project(rows, at=datetime(2026, 9, 16, 12, 0,
                                                          tzinfo=timezone.utc))
    as_known, annotated = views
    DualLensProjector.assert_consistent(views)
    assert as_known.is_pure_base, "AS_KNOWN 不该看见 2026 的注记"
    assert len(annotated.overlay) == 1
    assert annotated.overlay[0].target_object_id == "c-1"
    assert "诈骗" in annotated.overlay[0].statement
    # 铁律 2 的算法表达：两透镜底层指纹同，且底层不含 rip-1
    assert "rip-1" not in as_known.base_ids and "rip-1" not in annotated.base_ids


def test_as_known_lens_respects_time_anchor():
    rows = _world_rows(datetime.now(timezone.utc))
    # 视野锚在注记诞生前：两透镜都看不见
    views = DualLensProjector().project(rows, at=datetime(2025, 1, 1,
                                                          tzinfo=timezone.utc))
    assert all(len(v.overlay) == 0 for v in views)


# ---------------------------------------------------------------------------
# ToolProposal 一等对象契约
# ---------------------------------------------------------------------------


def test_tool_proposal_objects_pass_contract_validation():
    tp1 = ToolProposal(
        object_id="tp-001", capability_gap="IMU/心率全量直写死于存储爆炸",
        use_cases=["心率平稳期塌缩时段均值", "跌倒冲击逐拍永存"],
        current_limitations=["等间隔死采样磨平唯一重要的突变波形"],
        proposed_interface={"entry": "AdaptiveTemporalCompactor.compact",
                            "input": "Sequence[Beat]", "output": "CompactionPlan"},
        expected_benefit="平稳流压缩比 ≥200:1，突变 0 丢失",
        validation_plan="tests/e2e/test_tool_proposals.py 六件全绿",
        **world_kwargs(subject_id="director", learned_at=T0, recorded_at=T0),
    )
    tp2 = ToolProposal(
        object_id="tp-002", capability_gap="AS_KNOWN/ANNOTATED 双视图双索引双倍漂移",
        use_cases=["老王案回溯解释一致性审计", "当时视野回放取证"],
        current_limitations=["为两幅图各建物理索引 = 双倍存储双倍漂移"],
        proposed_interface={"entry": "DualLensProjector.project",
                            "input": "payloads", "output": "(AS_KNOWN, ANNOTATED)"},
        expected_benefit="单索引双投影，零存储增量，SHA-256 指纹审计",
        validation_plan="tests/e2e/test_tool_proposals.py 透镜组全绿",
        **world_kwargs(subject_id="director", learned_at=T0, recorded_at=T0),
    )
    assert tp1.object_type.value == "tool_proposal"
    assert tp2.validation_plan
