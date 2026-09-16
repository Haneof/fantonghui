"""新工具提案（ToolProposal）契约与交付质量测试。

老大定的是"不要 PPT、要能用的东西"，所以这里的断言分两层：

1. 每件工具都必须按 ``ToolProposal`` 契约提交，并且能在真实管线上走完
   DRAFT → SUBMITTED → APPROVED → EXECUTED（可评审、可执行）；
2. 提案内容不许空转：接口签名必须指向**真实存在**的模块/类/方法，
   不得出现 ``TODO`` / ``FIXME`` / ``pass`` 之类占位符。
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import re

from aios_core.bench.tool_catalog import (
    build_catalog,
    catalog_digest,
    submit_catalog,
)
from aios_core.contracts.enums import ProposalStatus
from aios_core.tools.proposal_pipeline import ToolProposalPipeline

PLACEHOLDER_PATTERN = re.compile(r"\bTODO\b|\bFIXME\b|NotImplementedError|待补充|待实现|pass\s*#\s*stub")


def test_catalog_has_both_new_tools_and_optimisers() -> None:
    proposals = build_catalog()
    assert len(proposals) >= 8, f"至少交付 8 件新工具/优化器，实际 {len(proposals)}"
    tool_ids = {proposal.object_id for proposal in proposals}
    assert len(tool_ids) == len(proposals), "工具 object_id 必须唯一"


def test_every_proposal_field_is_substantive() -> None:
    for proposal in build_catalog():
        assert proposal.capability_gap.strip(), f"{proposal.object_id} 缺少能力缺口描述"
        assert proposal.use_cases, f"{proposal.object_id} 缺少用例"
        assert proposal.current_limitations, f"{proposal.object_id} 缺少现状局限"
        assert proposal.proposed_interface, f"{proposal.object_id} 缺少接口定义"
        assert proposal.expected_benefit.strip(), f"{proposal.object_id} 缺少预期收益"
        assert proposal.validation_plan.strip(), f"{proposal.object_id} 缺少验证计划"
        blob = " ".join(
            [
                proposal.capability_gap,
                proposal.expected_benefit,
                proposal.validation_plan,
                *proposal.use_cases,
                *proposal.current_limitations,
            ]
        )
        assert not PLACEHOLDER_PATTERN.search(blob), (
            f"{proposal.object_id} 含占位符/未完成标记"
        )


def test_proposals_reference_real_modules_and_classes() -> None:
    expectations = {
        "adaptive_temporal_compressor": (
            "aios_core.tools.adaptive_temporal_compressor",
            "AdaptiveTemporalCompressor",
        ),
        "multiscale_crystal_index": (
            "aios_core.tools.multiscale_crystal_index",
            "MultiScaleCrystalIndex",
        ),
        "dual_lens_projection_index": (
            "aios_core.tools.dual_lens_projection_index",
            "DualLensProjectionIndex",
        ),
        "lightweight_condition_evaluator": (
            "aios_core.tools.lightweight_condition_evaluator",
            "LightweightConditionEvaluator",
        ),
        "resonance_synthesizer": (
            "aios_core.tools.resonance_synthesizer",
            "CrossDomainResonanceSynthesizer",
        ),
        "cooccurrence_recall_bus": (
            "aios_core.query.cooccurrence_recall_bus",
            "CoOccurrenceRecallBus",
        ),
        "persona_guard": ("aios_core.communication.persona_guard", "PersonaGuard"),
        "mind_sequence_guard": (
            "aios_core.cognition.mind_sequence",
            "MindSequenceRunner",
        ),
    }
    for proposal in build_catalog():
        tool_id = proposal.object_id.removeprefix("tool_proposal_")
        module_name, class_name = expectations[tool_id]
        module = importlib.import_module(module_name)
        assert hasattr(module, class_name), f"{module_name} 必须真的导出 {class_name}"


def test_documented_methods_exist_on_the_classes() -> None:
    module = importlib.import_module("aios_core.tools.adaptive_temporal_compressor")
    compressor = module.AdaptiveTemporalCompressor
    assert callable(getattr(compressor, "compress")), "提案里承诺的 compress 必须存在"
    assert callable(getattr(compressor, "verify_reconstruction")), (
        "提案里承诺的 verify_reconstruction 必须存在"
    )

    bus_module = importlib.import_module("aios_core.query.cooccurrence_recall_bus")
    recall = getattr(bus_module.CoOccurrenceRecallBus, "recall")
    signature = inspect.signature(recall)
    assert "query_terms" in signature.parameters, "recall 的入参名必须与提案一致"

    guard_module = importlib.import_module("aios_core.communication.persona_guard")
    assert callable(getattr(guard_module.PersonaGuard, "review")), "review 必须存在"


def test_pipeline_accepts_and_executes_the_catalog() -> None:
    pipeline, proposals = submit_catalog()
    assert len(proposals) == len(build_catalog()), "提交不得丢件"
    for proposal in proposals:
        assert proposal.status == ProposalStatus.SUBMITTED, (
            f"{proposal.object_id} 提交后状态必须是 SUBMITTED"
        )
        pipeline.review_proposal(proposal.object_id, "approve")
        executed = pipeline.execute_proposal(proposal.object_id)
        assert executed.status == ProposalStatus.EXECUTED, (
            f"{proposal.object_id} 必须在真实管线上可执行"
        )
    assert len(pipeline.list_proposals(ProposalStatus.EXECUTED)) == len(proposals)


def test_catalog_digest_is_machine_readable() -> None:
    pipeline, proposals = submit_catalog()
    digest = catalog_digest(proposals)
    assert digest["count"] == len(proposals), "摘要数量必须与提案数一致"
    assert digest["object_type"] == "tool_proposal", "对象类型必须是 tool_proposal"
    assert "signature" in digest["interface_keys"] or "methods" in digest["interface_keys"], (
        "接口定义必须包含签名或方法清单"
    )
    assert pipeline is not None, "管线对象必须可复用"


def test_no_placeholder_markers_in_new_bench_and_tool_sources() -> None:
    root = pathlib.Path("src/aios_core")
    targets = [
        root / "bench" / "adversarial_life_bench.py",
        root / "bench" / "blind_bench_harness.py",
        root / "bench" / "blind_bench_cognition.py",
        root / "bench" / "blind_bench_dialogue.py",
        root / "bench" / "blind_bench_metrics.py",
        root / "bench" / "blind_bench_results.py",
        root / "bench" / "blind_bench_cli.py",
        root / "bench" / "tool_catalog.py",
        root / "tools" / "adaptive_temporal_compressor.py",
        root / "tools" / "multiscale_crystal_index.py",
        root / "tools" / "dual_lens_projection_index.py",
        root / "tools" / "lightweight_condition_evaluator.py",
        root / "tools" / "resonance_synthesizer.py",
        root / "query" / "cooccurrence_recall_bus.py",
        root / "communication" / "persona_guard.py",
        root / "cognition" / "mind_sequence.py",
        root / "ingest" / "edge_stream_purifier.py",
    ]
    offenders = []
    for path in targets:
        assert path.exists(), f"交付文件缺失：{path}"
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER_PATTERN.search(text):
            offenders.append(str(path))
    assert offenders == [], f"交付源码中不得出现占位符：{offenders}"
