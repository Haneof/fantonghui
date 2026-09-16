"""8 大阶段核心引擎的模块级语义测试（快速档，无大世界依赖）。

覆盖：时间金字塔结晶/穿透、时空共振与生命周期、认知运动学/相变、
沟通三防线、双工具（TP-001/TP-002）契约。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios_core.cognition.communication_evolution import (
    ActionFeedback,
    AIActionLog,
    CommunicationExperience,
    PreacherViolation,
    StyleGuard,
    SycophancyViolation,
    ZeroUIViolation,
    count_sentences,
)
from aios_core.contracts.enums import EventStatus
from aios_core.contracts.refs import ObjectRef
from aios_core.dimensions.kinematics import (
    InflectionDetector,
    LifeChapterDetector,
    SeverityPoint,
    compute_kinematics,
)
from aios_core.query.search import MindRecord, MultidimensionalSearchEngine
from aios_core.summaries.time_pyramid import TimePyramidCrystallizer
from aios_core.tools.adaptive_compressor import AdaptiveTemporalCompressor
from aios_core.tools.dual_lens_index import DualLensVirtualIndexProjector
from aios_core.world.event_resonance import (
    EventLifecycleError,
    EventLifecycleManager,
    SignalPing,
    SpatiotemporalResonator,
)

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


# ----------------------------------------------------------------------
# 阶段二：金字塔
# ----------------------------------------------------------------------

def _records(days: int) -> list[MindRecord]:
    out = []
    for d in range(days):
        out.append(MindRecord(
            record_id=f"rec-{d:04d}", record_type="claim",
            keywords=("纠纷", "流水") if d % 3 == 0 else ("日常",),
            content=f"事实切片 {d}", occurred_at=T0 + timedelta(days=d % 360, hours=9),
        ))
    return out


def test_pyramid_crystallizes_and_preserves_sources() -> None:
    recs = _records(400)
    engine = MultidimensionalSearchEngine()
    engine.register_all(recs)
    before = engine.record_count
    cryst = TimePyramidCrystallizer()
    pyramid = cryst.crystallize(recs)
    registered = cryst.register_into_engine(pyramid, engine)
    # 总结是新观察层：原始记录条数不变，增量 == 总结节点数
    assert engine.record_count == before + registered
    assert pyramid.source_record_count == len(recs)
    levels = {lv: len(pyramid.by_level(lv)) for lv in ("day", "week", "month", "quarter", "year")}
    assert levels["year"] >= 1 and levels["quarter"] >= 2 and levels["month"] >= 12


def test_pyramid_drill_through_breakage_zero() -> None:
    recs = _records(400)
    pyramid = TimePyramidCrystallizer().crystallize(recs)
    rate, paths = pyramid.audit(list(pyramid.leaves))
    assert rate == 0.0
    full = paths[0].chain
    assert full[0].startswith("py-year-") and full[-1].startswith("py-day-")
    assert len(full) == 5   # 年→季→月→周→日 五级链完整


# ----------------------------------------------------------------------
# 阶段三：共振与生命周期
# ----------------------------------------------------------------------

def _pings() -> list[SignalPing]:
    modal = [("gps", "出发"), ("heart_rate", "飙升"), ("audio", "原话"),
             ("gps", "到达"), ("bank", "流水")]
    return [
        SignalPing(at=T0 + timedelta(minutes=10 * i), modality=m, key="partner",
                   label=l, ref=ObjectRef(object_id=f"o{i}", revision=1))
        for i, (m, l) in enumerate(modal)
    ]


def test_resonator_requires_cross_modality() -> None:
    resonator = SpatiotemporalResonator()
    clusters = resonator.resonate(_pings())
    assert len(clusters) == 1
    assert len(clusters[0].modalities) == 4
    anchor = resonator.to_event_anchor(clusters[0], title="t", interpretation="i")
    assert anchor.event_status is EventStatus.CANDIDATE
    assert len(anchor.support_evidence_set_refs) == 5
    # 单模态：拒绝立锚
    solo = [SignalPing(at=T0 + timedelta(minutes=i), modality="gps", key="x", label=f"p{i}")
            for i in range(5)]
    solo_clusters = resonator.resonate(solo)
    assert solo_clusters == []
    with pytest.raises(EventLifecycleError, match="modalities"):
        resonator.to_event_anchor(
            type(clusters[0])("res-x", T0, T0, tuple(solo), frozenset({"gps"})),
            title="t", interpretation="i",
        )


def test_anchor_window_splitting_prevents_mega_cluster() -> None:
    """密集信号流：锚定窗口切分，跨窗即断（不链式并巨簇）。"""
    dense = [
        SignalPing(at=T0 + timedelta(minutes=10 * i), modality="gps" if i % 2 else "audio",
                   key="k", label=f"p{i}")
        for i in range(40)
    ]
    far = [SignalPing(at=T0 + timedelta(hours=72, minutes=10 * i),
                      modality="gps" if i % 2 else "audio", key="k", label=f"q{i}")
           for i in range(4)]
    resonator = SpatiotemporalResonator(window=timedelta(hours=1))
    clusters = resonator.resonate(dense + far)
    # 锚定切分：每 60 分钟一簇（40 条密集流 → 6 簇），72 小时后的 4 条另起 1 簇
    assert len(clusters) == 7
    assert clusters[-1].t_start == far[0].at
    for c in clusters:
        assert (c.t_end - c.t_start) <= timedelta(hours=1)
    assert all(clusters[i].t_end < clusters[i + 1].t_start for i in range(len(clusters) - 1))


def test_event_lifecycle_snapshots_and_stale() -> None:
    resonator = SpatiotemporalResonator()
    anchor = resonator.to_event_anchor(
        resonator.resonate(_pings())[0], title="合伙摊牌", interpretation="共振"
    )
    mgr = EventLifecycleManager()
    mgr.register(anchor)
    mgr.attach_dependency(dependent_key="claim:信任", event_id=anchor.object_id)
    mgr.activate(anchor.object_id, reason="证据成立", at=T0 + timedelta(days=1))
    mgr.revise(anchor.object_id, reason="新流水入账", at=T0 + timedelta(days=2), confidence=0.95)
    mgr.split(anchor.object_id, child_ids=["ev-c1", "ev-c2"], reason="分账", at=T0 + timedelta(days=3))
    current = mgr.event(anchor.object_id)
    assert current.event_status is EventStatus.SPLIT
    assert len(mgr.snapshots_of(anchor.object_id)) == 3          # activate+revise+split 全程快照
    assert mgr.revision_reasons(anchor.object_id)[1] == "新流水入账"
    assert mgr.stale_dependents() == ("claim:信任",)
    with pytest.raises(Exception):
        mgr.activate(anchor.object_id, reason="非法回跳", at=T0 + timedelta(days=4))


# ----------------------------------------------------------------------
# 阶段四：运动学 / 相变
# ----------------------------------------------------------------------

def test_kinematics_velocity_acceleration() -> None:
    series = [SeverityPoint(at=T0 + timedelta(days=d), value=40.0 + d * 1.0) for d in range(10)]
    steps = compute_kinematics(series)
    assert len(steps) == 9
    assert steps[-1].velocity == pytest.approx(1.0)
    assert steps[-1].acceleration == pytest.approx(0.0)   # 匀速 → 加速度 0


def test_inflection_early_warning_lead_time() -> None:
    vals = []
    for d in range(120):
        v = 40 + d * 0.3 + ((d - 60) ** 1.6 * 0.12 if d >= 60 else 0.0)
        vals.append(SeverityPoint(at=T0 + timedelta(days=d), value=min(v, 99)))
    infl = InflectionDetector(accel_threshold=0.02, severity_threshold=80.0).detect(vals)
    assert infl, "拐点必须被探测"
    assert infl[0].lead_time_days is not None and infl[0].lead_time_days > 10


def test_life_chapter_baseline_rupture_and_seal() -> None:
    pts = [SeverityPoint(at=T0 + timedelta(days=d), value=68 + (8 if d >= 400 else 0))
           for d in range(800)]
    chapters = LifeChapterDetector().detect(pts, metric="resting_hr")
    assert len(chapters) == 2
    old, new = chapters
    assert old.sealed and old.end is not None
    assert "基线断裂" in (old.end_reason or "")
    assert not new.sealed
    assert new.start == old.end


# ----------------------------------------------------------------------
# 阶段七：沟通三防线
# ----------------------------------------------------------------------

def test_anti_sycophancy_blocks_agreement_with_absurdity() -> None:
    guard = StyleGuard()
    with pytest.raises(SycophancyViolation):
        guard.govern_reply("你说得对，全仓押上肯定没问题。", user_absurd=True, at=T0)
    honest = guard.honest_reply_for_absurd("全仓押上没问题", evidence_pointer="2024 同款操作亏损记录")
    assert "不接" in honest or "对不上" in honest


def test_anti_preacher_blocks_lecturing_on_venting() -> None:
    guard = StyleGuard()
    with pytest.raises(PreacherViolation):
        guard.govern_reply("根据法律你应该明白你的责任。", user_venting=True, at=T0)
    ok = guard.govern_reply("先吃饭，账我来对。", user_venting=True, at=T0)
    assert count_sentences(ok) == 1


def test_zero_ui_blocks_questionnaire_and_backend() -> None:
    guard = StyleGuard()
    with pytest.raises(ZeroUIViolation):
        guard.govern_reply("请选择：选项A 起诉 / 选项B 和解，置信度 0.8。", at=T0)


def test_communication_experience_learns_taboo_and_budget() -> None:
    log = AIActionLog()
    exp = CommunicationExperience(log=log)
    guard = StyleGuard(experience=exp)
    at = T0
    rows = [
        ("亏损安慰", "别想了，都会好的。", -1, False, True),
        ("亏损安慰", "这页翻过去就行。", -1, False, True),
        ("亏损安慰", "这个月账是难看，但你在场都没慌过——我在。", 2, False, True),
        ("项目进展", "回款比上周提前四天。", 1, False, False),
        ("荒谬判断", "这句我不接：跟流水对不上。", 2, True, False),
    ]
    # 客服套话在倾诉场景先行被防线拦截（违宪样本根本到不了用户）
    with pytest.raises(PreacherViolation):
        guard.govern_reply("保持乐观心态！", user_venting=True, at=at)
    for i, (topic, reply, reaction, absurd, venting) in enumerate(rows):
        reply2 = guard.govern_reply(reply, user_absurd=absurd, user_venting=venting, at=at + timedelta(minutes=i))
        log.record(ActionFeedback(
            at=at + timedelta(minutes=i), action_kind="spoke",
            sentence_count=count_sentences(reply2), reply=reply2,
            user_reaction=reaction, topic=topic, user_absurd=absurd, user_venting=venting,
        ))
    exp.learn()
    assert "亏损安慰" in exp.taboo_topics()      # ≥2 次负反馈 → 自发雷区
    assert exp.sentence_budget() <= 3
    assert log.mean_reaction() == pytest.approx(0.6)   # 5 样本：-1,-1,1,2,-1


# ----------------------------------------------------------------------
# TP-001 / TP-002 工具
# ----------------------------------------------------------------------

def test_tp001_adaptive_compressor_conservation() -> None:
    comp = AdaptiveTemporalCompressor(window_size=50, spike_sigma=3.0)
    values = [70.0 + ((i * 7) % 5) * 0.3 for i in range(4000)] + [152.0, 168.0] + [71.0] * 500
    result = comp.compress(values)
    assert result.coverage == pytest.approx(1.0)          # 样本守恒，零静默丢点
    assert result.spike_values == (152.0, 168.0)          # 极值全部进入尖峰通道
    assert result.ratio > 6                                # 压缩比
    # 均值通道失真 <1%
    import statistics

    kept = list(values)
    reconstructed = []
    for m, n in zip(result.window_means, result.window_sizes):
        reconstructed.extend([m] * n)
    reconstructed.extend(result.spike_values)
    assert abs(statistics.mean(reconstructed) - statistics.mean(kept)) / statistics.mean(kept) < 0.01
    proposal = __import__("aios_core.tools.adaptive_compressor", fromlist=["x"]).tool_proposal_of_compressor()
    assert proposal.capability_gap and proposal.validation_plan


def test_tp002_dual_lens_virtual_index() -> None:
    subjects = {f"r{i}": "partner_zhou" for i in range(20000)}
    annotations = [
        {"record_id": "r19999", "subject_id": "partner_zhou", "kind": "overturn"},
        {"record_id": "r5", "subject_id": "partner_zhou", "kind": "note"},
        {"record_id": "r7", "subject_id": "partner_zhou", "kind": "note"},
    ]
    projector = DualLensVirtualIndexProjector(record_subjects=subjects, annotations=annotations)
    # O(注解) 构建：扫描量 == 注解数，与 2 万记录量解耦
    assert projector.build_scan_count == 3
    known = projector.view("partner_zhou", lens="as_known")
    noted = projector.view("partner_zhou", lens="annotated")
    assert len(known.visible_ids) == 20000
    assert len(noted.visible_ids) == 19999
    assert "r19999" not in noted.visible_ids
    assert projector.consistency_report()["consistent"] is True
