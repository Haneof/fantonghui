"""Tests for Agent Mind Arena Bench (TASK-M5-005-AGENT-ARENA)."""

from datetime import datetime, timezone
import pytest

from aios_core.simulation.agent_mind_bench import (
    AgentMindPlayground,
    MindPerformanceMetricsRecorder,
)

UTC = timezone.utc


@pytest.fixture(scope="module")
def arena_playground():
    playground = AgentMindPlayground(seed=123)
    yield playground
    playground.close()


def test_competent_agent_evaluation(arena_playground):
    # 考评优秀合规 Agent
    report = arena_playground.evaluate_agent("agent_competent_alpha")

    # 核心断言 1：没有违背五大铁律，资格通过
    assert report.metrics.disqualified is False
    assert report.metrics.iron_rule_violations_count == 0
    assert report.metrics.overall_score >= 90.0

    # 核心断言 2：P95 检索与多维对齐延迟极速受控 (<= 150ms)
    assert report.metrics.p95_latency_ms <= 150.0

    # 核心断言 3：操作经验成功沉淀与持久化
    assert report.persisted_experience_key is not None
    summary_md = report.summary_markdown()
    assert "通过考评" in summary_md
    assert "SCENARIO_OLD_WANG_FRAUD" in summary_md


def test_disqualified_agent_violating_iron_law(arena_playground):
    # 模拟篡改历史事实的劣质 Agent
    def bad_executor_tampering(suite, store):
        # 尝试篡改历史 Observation
        return {"tampered": True}

    report = arena_playground.evaluate_agent(
        "agent_rogue_beta",
        agent_executor={"old_wang_fraud": bad_executor_tampering},
    )

    # 核心断言 1：一票否决淘汰
    assert report.metrics.disqualified is True
    assert report.metrics.iron_rule_violations_count >= 1
    assert report.metrics.overall_score == 0.0
    assert "触碰最高铁律一票否决红线" in report.metrics.disqualification_reason
