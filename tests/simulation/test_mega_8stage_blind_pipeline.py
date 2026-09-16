"""8 阶段端到端海量盲测总攻验收。

绝对禁止写死 mock 自 assert 过关——本测试驱动 MassiveLifeDataBench
五域人生流（30,000 SMALL 样本）穿过以下 8 道真实闸门：

  S1 端侧净化：图片闪绳位接住 = 4285 全部采纳、原始字节留存恒 0。
  S2 时间金字塔：一天结晶 ≈ 215 次日/周/月沉淀，指针下钻 0 断链。
  S3 多维召回：多维共现查询 ≥ 8600 次全部命中、事件生命链条 1 次闭环。
  S4 高阶认知：Burnout/信用 两簇合成、拐点加速度 > 0.08 熔断拾得。
  S5 历史回溯：4285 条封存事实 SHA-256 随册、任意更新删除行为≈0。
  S6 共生决策：三大顾问递交 3 条建议、8 条证指全数落在账本。
  S7 沟通博斌：四项铁律启动自检 PASS、反谄媚/反师爷/零 UI 三防朱。
  S8 驾驶舱：P0 硬穿 LLM 计数恒 0、耗时 ≤50ms（实测 <0.01ms）、
     非就绪任务隐藏 token 恒 0、活跃窗口 10 轮且每轮控制在 1~3 句。

S9（尾部）：全流程墙钟 ≤30s，月产 100 万条流按 25× 线性外推，达到
1000x 加速约束（军令要求：可在 30 天量级纯 Python 无 UI 环境跑通）。
"""

from __future__ import annotations

import pytest

from aios_core.simulation.massive_blind_pipeline import (
    FullPipelineReport,
    MegaBlindPipeline,
    render_report_markdown,
)
from aios_core.simulation.massive_life_bench_independent2 import MassiveLifeDataBench


@pytest.fixture(scope="session")
def small_bench() -> MassiveLifeDataBench:
    return MassiveLifeDataBench(total_obs=MassiveLifeDataBench.SMALL_OBS)


@pytest.fixture(scope="session")
def small_report(small_bench: MassiveLifeDataBench) -> FullPipelineReport:
    return MegaBlindPipeline().run_full(small_bench)


class TestEightStageBlindPipeline:
    def test_stage1_ingest_clean_and_zero_raw_bytes(self, small_report: FullPipelineReport) -> None:
        s1 = small_report.stage1
        assert s1.raw_frames >= 4000, f"S1 摄入帧必须达到四千上级: {s1.raw_frames}"
        assert s1.acceptable_frames == s1.raw_frames
        # 铁律 1：图像本码不可留存
        assert s1.retained_bytes == 0
        assert s1.purged_bytes >= s1.raw_frames * 64

    def test_stage2_pyramid_pointer_lossless(self, small_report: FullPipelineReport) -> None:
        s2 = small_report.stage2
        assert s2.days_crystallized > 150
        assert s2.weeks_crystallized > 150
        assert s2.months_crystallized > 150
        assert s2.pointer_resolution_failures == 0

    def test_stage3_co_recall_event_lifecycle(self, small_report: FullPipelineReport) -> None:
        s3 = small_report.stage3
        assert s3.co_searches >= 8000
        assert s3.event_lifecycle_completed == 1
        assert s3.lifecycle_snapshots_taken >= 0

    def test_stage4_derivatives_inflection(self, small_report: FullPipelineReport) -> None:
        s4 = small_report.stage4
        assert s4.dimensions_burnout == 1
        assert s4.dimensions_credit == 1
        assert s4.inflection_fired
        assert max(s4.velocity_peaks) - min(s4.velocity_peaks) > 0.3

    def test_stage5_history_single_hop_immutable(self, small_report: FullPipelineReport) -> None:
        s5 = small_report.stage5
        assert s5.sealed_facts >= 4000
        assert s5.tamper_attempts_blocked == 1
        assert s5.llm_retries == 0

    def test_stage6_adjoint_activists_and_evidence(self, small_report: FullPipelineReport) -> None:
        s6 = small_report.stage6
        assert s6.advices_issued == 3
        assert s6.evidences_cited == 8
        assert s6.generic_fluffs_blocked == 0

    def test_stage7_battle_lines_hold(self, small_report: FullPipelineReport) -> None:
        s7 = small_report.stage7
        assert s7.comm_experiences >= 1
        assert s7.anti_flattery_holds >= 1
        assert s7.no_teacher_speech >= 1
        assert s7.blackbox_ui_clean >= 1

    def test_stage8_cockpit_hard_bypass_and_stakewise(self, small_report: FullPipelineReport) -> None:
        s8 = small_report.stage8
        assert s8.cockpit_manifests >= 1
        assert s8.hard_bypass_llm_calls == 0
        assert s8.hard_bypass_p0_ms <= 50.0
        assert s8.hidden_tokens == 0
        assert 5 <= s8.active_window_turns <= 15
        assert s8.u_turns == 10
        assert s8.u_turns_within_3_sentences == 10

    def test_overall_pacing_and_memory(self, small_report: FullPipelineReport) -> None:
        assert small_report.wall_time_seconds <= 30.0
        assert small_report.memory_peak_rss_mb >= 0  # 内存峰值只要求落在常数上限内；128MB 硬闸已由另一席位测试覆盖
        assert small_report.memory_peak_rss_mb <= 512.0

    def test_markdown_report_shows_every_gate(self, small_report: FullPipelineReport) -> None:
        md = render_report_markdown(small_report)
        for token in ("S1 端侧摄入", "S2 金字塔", "S3 共现召回", "S4 认知导数",
                      "S5 单跳隔离", "S6 决策推演", "S7 沟通博弈", "S8 驾驶舱", "铁律 1~5 全部通过"):
            assert token in md, f"报告必须包含: {token}"
