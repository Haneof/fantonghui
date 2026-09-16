"""AIOS 3.0 全人生谱系高熵题库：出题引擎与交付脚本的行为契约测试。

覆盖点：
1. 七维因子必须逐题齐全（含维度七对抗陷阱，难度只改变陷阱恶意程度）；
2. 每一行都能通过 CleaningQuestion 契约（零缺字段、零非法引用）；
3. 同参同卷的确定性 + 换种子即换卷；
4. 难度 / 数据流聚焦 / 认知域配比在每 100 题窗口内精确成立；
5. 题目唯一性（因子签名与事实文本双唯一）；
6. 波形与事件的一致性（跑步基线绝不解释为心梗/癫痫，异常波形只在健康域或高危人群出现）；
7. 交付脚本端到端（明文 + gzip 双格式、标答对齐、verify-only 审计返回码）。
"""

from __future__ import annotations

import gzip
import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "plan_scripts" / "generate_life_spectrum_bank.py"

from aios_core.simulation.life_spectrum_question_generator import (  # noqa: E402
    GeneratorConfig,
    FullLifeSpectrumQuestionGenerator,
    TRAP_POOL_BY_DIFFICULTY,
    audit_questions,
    factor_inventory,
    validate_question,
)

FOCUS_STREAM_WEIGHTS = {"sensor": 30, "mic": 30, "voiceprint": 20, "app": 15, "dialogue": 5}
DIFFICULTY_WEIGHTS = {"EASY": 15, "MEDIUM": 40, "HARD": 30, "ADVERSARIAL": 15}
DOMAINS = ("dim:health", "dim:finance", "dim:social", "dim:career", "dim:life")


def _batch(count: int = 300, seed: int = 20260916) -> list:
    generator = FullLifeSpectrumQuestionGenerator(GeneratorConfig(agent_id="agent-test", seed=seed, count=count))
    return list(generator.generate_all())


def test_factor_inventory_is_full_spectrum() -> None:
    inventory = factor_inventory()
    assert inventory["personas"] >= 50
    assert inventory["event_families"] >= 60
    assert inventory["sensor_profiles"] >= 7
    assert inventory["acoustic_topologies"] >= 12
    assert inventory["speaker_roles"] >= 24
    assert inventory["traps"] >= 8
    assert inventory["dialect_packs"] >= 13


def test_every_question_combines_all_seven_dimensions() -> None:
    questions = _batch()
    for question in questions:
        signature = question["factor_ids"]
        for key in ("demographic", "core_event", "sensor", "acoustic", "linguistic",
                    "speaker_topology", "trap", "focus_stream", "domain"):
            assert signature[key], f"{question['question_id']} 缺少维度字段 {key}"
        assert int(signature["speaker_topology"]) >= 3
        assert signature["trap"] in {spec for pool in TRAP_POOL_BY_DIFFICULTY.values() for spec in pool}
        assert signature["trap"] in TRAP_POOL_BY_DIFFICULTY[question["difficulty"]]
        # 维度五：方言包永远参与，修辞陷阱按难度叠加（方言+修辞以 + 拼接）
        assert isinstance(signature["linguistic"], str) and signature["linguistic"]


def test_rows_satisfy_cleaning_question_contract() -> None:
    for question in _batch():
        validate_question(question)
        ids = {item["sid"] for item in question["mic_stream"]}
        ids |= {item["mid"] for item in question["app_message_stream"]}
        ids |= {item["uid"] for item in question["user_dialogue_stream"]}
        ids.add(question["sensor_stream"]["sample_id"])
        assert set(question["ground_truth_junk_ids"]) <= ids
        for fact in question["ground_truth_facts"]:
            assert fact["source_ref_id"] in ids
            assert len(fact["directional_keywords"]) >= 6
            assert fact["core_content"].strip()


def test_deterministic_and_seed_sensitive() -> None:
    first = _batch(count=120, seed=4242)
    second = _batch(count=120, seed=4242)
    third = _batch(count=120, seed=777)
    dump = lambda rows: json.dumps(rows, ensure_ascii=False, sort_keys=True)
    assert dump(first) == dump(second)
    assert dump(first) != dump(third)


def test_quota_decks_are_exact_per_hundred() -> None:
    questions = _batch(count=500)
    audit = audit_questions(questions)
    assert audit["difficulty"] == {level: weight * 5 for level, weight in DIFFICULTY_WEIGHTS.items()}
    assert audit["focus_streams"] == {stream: weight * 5 for stream, weight in FOCUS_STREAM_WEIGHTS.items()}
    assert all(count == 100 for count in audit["domains"].values())
    assert audit["domain_ratio"]["dim:health"] >= 0.15


def test_questions_are_unique_and_self_consistent() -> None:
    questions = _batch(count=500)
    audit = audit_questions(questions)
    assert audit["total"] == 500
    assert audit["unique_factor_signatures"] == 500
    assert audit["unique_core_contents"] == 500
    assert audit["duct_issue_count"] == 0
    assert audit["facts_per_question"] >= 1.5
    assert 0.3 <= audit["junk_ratio"] <= 0.75


def test_sensor_waveform_stays_coherent_with_event() -> None:
    questions = _batch(count=500)
    for question in questions:
        profile = question["sensor_stream"]["profile"]
        domain = question["factor_ids"]["domain"]
        texts = " ".join(fact["core_content"] for fact in question["ground_truth_facts"])
        if profile == "S06":
            # 正常跑步基线：绝不能被解释为心梗 / 癫痫 / 危象
            assert "心梗" not in texts and "癫痫" not in texts and "危象" not in texts
            assert question["sensor_stream"]["motion_state"].startswith("RUNNING")
        if profile in {"S01", "S03", "S04"}:
            # 冲击 / 心律失常 / 窦性停搏：健康域事件直接允许；落在其它域时，
            # 必须额外带一条 dim:health 的波形异常事实（禁止"波形异常却无医学解释"）
            health_facts = [fact for fact in question["ground_truth_facts"] if fact["dimension_id"] == "dim:health"]
            assert domain == "dim:health" or health_facts, f"{question['question_id']} 异常波形缺少医学事实"
        if profile == "S02":
            # 伪冲击：没有坠落静止段，只是单峰高 G
            assert "false_impact_note" in question["sensor_stream"]
            assert "post_impact_still_s" not in question["sensor_stream"]


def test_ground_truth_facts_carry_directional_synonyms() -> None:
    for question in _batch(count=200):
        for fact in question["ground_truth_facts"]:
            keywords = fact["directional_keywords"]
            assert len(set(keywords)) == len(keywords)
            assert all(keyword.strip() for keyword in keywords)
            assert fact["semantic_intent"].isupper()


def test_cli_end_to_end_plain_and_gzip(tmp_path: pathlib.Path) -> None:
    plain_q = tmp_path / "questions.jsonl"
    plain_gt = tmp_path / "gt.jsonl"
    gz_q = tmp_path / "questions.jsonl.gz"
    gz_gt = tmp_path / "gt.jsonl.gz"
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    schema = tmp_path / "schema.json"

    def run(count: int, questions_out: pathlib.Path, ground_truth_out: pathlib.Path) -> dict:
        completed = subprocess.run(
            [sys.executable, str(CLI), "--agent-id", "agent-cli", "--count", str(count), "--seed", "20260916",
             "--questions-out", str(questions_out), "--ground-truth-out", str(ground_truth_out),
             "--manifest-out", str(manifest), "--report-out", str(report), "--schema-out", str(schema),
             "--audit-sample", "0"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(completed.stdout)

    summary = run(80, plain_q, plain_gt)
    assert summary["count"] == 80
    assert summary["audit"]["duct_issue_count"] == 0
    assert manifest.exists() and report.exists() and schema.exists()

    rows = [json.loads(line) for line in plain_q.read_text(encoding="utf-8").splitlines() if line.strip()]
    truth = [json.loads(line) for line in plain_gt.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == len(truth) == 80
    assert [row["question_id"] for row in rows] == [row["question_id"] for row in truth]
    assert all(row["ground_truth_facts"] == tr["ground_truth_facts"] for row, tr in zip(rows, truth))
    assert all(row["ground_truth_junk_ids"] == tr["ground_truth_junk_ids"] for row, tr in zip(rows, truth))
    assert json.loads(schema.read_text(encoding="utf-8"))["ground_truth_facts[]"]["core_content"]

    run(80, gz_q, gz_gt)
    with gzip.open(gz_q, "rt", encoding="utf-8") as handle:
        gz_rows = [json.loads(line) for line in handle if line.strip()]
    assert gz_rows == rows  # 同参同卷：压缩件与明文件逐字节等价

    verify = subprocess.run(
        [sys.executable, str(CLI), "--verify-only", "--questions-out", str(plain_q)],
        capture_output=True, text=True, check=True,
    )
    audit = json.loads(verify.stdout)
    assert audit["schema_invalid_count"] == 0
    assert audit["duct_issue_count"] == 0


@pytest.mark.parametrize("difficulty", sorted(DIFFICULTY_WEIGHTS))
def test_trap_pool_covers_expected_malice_levels(difficulty: str) -> None:
    pool = TRAP_POOL_BY_DIFFICULTY[difficulty]
    assert pool, f"{difficulty} 必须至少有一个陷阱可用（保证每题都含维度七）"
    if difficulty == "EASY":
        assert set(pool) <= {"T02", "T03", "T07"}
    if difficulty == "ADVERSARIAL":
        assert len(pool) == 8
