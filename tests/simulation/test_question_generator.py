"""Regression tests for the seven-dimensional cleaning-question generator."""

from __future__ import annotations

import json

from aios_core.simulation.question_generator import (
    EVENT_DOMAINS,
    SevenDimensionQuestionGenerator,
)


def _stream_ids(question):
    return {
        question.sensor_stream["sensor_packet_id"],
        *(item["snippet_id"] for item in question.mic_stream),
        *(item["msg_id"] for item in question.app_message_stream),
        *(item["utterance_id"] for item in question.user_dialogue_stream),
    }


def test_small_run_is_deterministic_and_uses_all_seven_dimensions():
    first = SevenDimensionQuestionGenerator("agent-01", seed=77).generate(40)
    second = SevenDimensionQuestionGenerator("agent-01", seed=77).generate(40)
    first_dump = [question.model_dump(mode="json") for question in first]
    second_dump = [question.model_dump(mode="json") for question in second]

    assert first_dump == second_dump
    assert len({row["question_id"] for row in first_dump}) == 40
    assert all(
        set(row["factor_ids"]) == {
            "demographic",
            "core_event",
            "sensor",
            "acoustic",
            "linguistic",
            "speaker_topology",
            "trap",
        }
        for row in first_dump
    )


def test_generated_records_have_resolvable_truth_and_speaker_refs():
    generator = SevenDimensionQuestionGenerator("agent-02", seed=3)
    for question in generator.generate(120):
        ids = _stream_ids(question)
        assert set(question.ground_truth_junk_ids) <= ids
        assert 3 <= question.voiceprint_cluster["speaker_count"] <= 24
        detected = set(question.voiceprint_cluster["detected_speakers"])
        assert question.voiceprint_cluster["user_speaker_id"] == "spk_user"
        for snippet in question.mic_stream:
            assert snippet["speaker_id"] in detected
        for fact in question.ground_truth_facts:
            assert fact.source_ref_id in ids
        for item in question.mic_stream + question.app_message_stream + question.user_dialogue_stream:
            if item.get("is_junk"):
                item_id = item.get("snippet_id") or item.get("msg_id") or item.get("utterance_id")
                assert item_id in question.ground_truth_junk_ids


def test_ten_thousand_schedule_covers_domains_and_has_no_factor_tuple_collision():
    generator = SevenDimensionQuestionGenerator("agent-03", seed=20260916)
    report = generator.validate_coverage(10_000)

    assert report["count"] == 10_000
    assert report["unique_question_ids"] == 10_000
    assert set(report["event_domain_counts"]) == set(EVENT_DOMAINS)
    assert min(report["event_domain_counts"].values()) >= 1_500
    assert {key: len(value) for key, value in report["factor_counts"].items()} == {
        "demographic_persona": 15,
        "core_event_spectrum": 26,
        "sensor_waveform": 6,
        "ambient_acoustic": 7,
        "linguistic_profile": 10,
        "speaker_topology": 8,
        "adversarial_trap": 4,
    }


def test_writer_emits_question_and_compact_ground_truth_jsonl(tmp_path):
    generator = SevenDimensionQuestionGenerator("agent-04", seed=9)
    paths = generator.write_dataset(tmp_path, count=4)

    question_lines = paths.questions.read_text(encoding="utf-8").splitlines()
    truth_lines = paths.ground_truth.read_text(encoding="utf-8").splitlines()
    assert paths.count == 4
    assert len(question_lines) == len(truth_lines) == 4
    question = json.loads(question_lines[0])
    truth = json.loads(truth_lines[0])
    assert question["question_id"] == truth["question_id"]
    assert truth["ground_truth_facts"] == question["ground_truth_facts"]
    assert "mic_stream" not in truth
