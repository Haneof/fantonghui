"""战队 ``01a0aa2e`` 全天生活流出卷官的断言单测。

覆盖出卷铁律里能被代码路径证明的部分：

* 输出契约：``question_id`` / ``persona`` / ``cleaned_daily_stream`` / ``directional_ground_truth``；
* 六维标答齐全（全局日总结 + health/social/emotion/finance/career）；
* 每个标答都有【可接受的方向同义词】与【绝对偏离的红线判据】，且两者不相交；
* 反泄漏：题面不得出现任何答案字段；标答实体必须逐字出现在被引用的证据碎片里；
  红线词不得出现在题面里；
* 时间窗：所有事件落在 07:00~23:30 且各通道内按时间升序；
* 确定性：同种子逐字节可复现；不同题目互不重复；
* 32 条主线剧情全部能产出通过自查的完整试卷（逐条遍历，避免有主线是死代码）。
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "daily_life_summarization"
    / "generators"
    / "daily_life_generator_01a0aa2e.py"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("daily_life_generator_01a0aa2e", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["daily_life_generator_01a0aa2e"] = module
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _question(index: int = 1, seed: int = 20260916):
    return gen.build_question(random.Random(seed * 1_000_003 + index), index)


# ---------------------------------------------------------------------------
# 输出契约与六维标答
# ---------------------------------------------------------------------------
def test_question_and_ground_truth_schema():
    question, truth = _question()
    assert set(question) == {"question_id", "persona", "cleaned_daily_stream"}, "题面顶层字段必须符合出卷规范"
    assert set(truth) >= {"question_id", "persona", "cleaned_daily_stream", "directional_ground_truth"}, (
        "标答对象必须包含 question_id/persona/cleaned_daily_stream/directional_ground_truth"
    )
    stream = question["cleaned_daily_stream"]
    assert stream["coverage_window"] == "07:00-23:30", "生活流窗口必须是 07:00~23:30"
    assert stream["mic_slices"] and stream["app_notifications"], "MIC 与 APP 两个通道都不得为空"
    assert stream["sensor_summary"]["hr_events"] is not None, "体征宏观摘要缺失"


def test_six_dimensional_ground_truth_is_complete():
    question, truth = _question()
    payload = truth["directional_ground_truth"]
    assert "global_daily_summary" in payload, "缺少全局日总结标答"
    assert set(payload["dimensions"]) == set(gen.DIMENSIONS), "必须覆盖 health/social/emotion/finance/career 五个维度"
    assert question["question_id"] == truth["question_id"], "题面与标答的题目编号不一致"
    for dim, anchor in payload["dimensions"].items():
        for field_name in ("semantic_core", "acceptable_synonyms", "red_line_rejections", "evidence_ref_ids"):
            assert field_name in anchor, f"{dim} 标答缺少字段 {field_name}"


def test_every_anchor_carries_synonyms_and_red_lines():
    question, truth = _question(7)
    for dim, anchor in gen._iter_anchors(truth):
        assert len(anchor["acceptable_synonyms"]) >= gen.MIN_SYNONYMS, f"{dim} 方向同义词不足"
        assert len(anchor["red_line_rejections"]) >= gen.MIN_RED_LINES, f"{dim} 红线判据不足"
        assert not set(anchor["acceptable_synonyms"]) & set(anchor["red_line_rejections"]), (
            f"{dim} 同义词与红线自相矛盾"
        )
        assert anchor["evidence_ref_ids"], f"{dim} 标答没有可追溯证据"


def test_day_mixes_key_events_with_trivia():
    """一天必须同时有关键大事与海量琐碎日常。"""
    question, truth = _question(3)
    stream = question["cleaned_daily_stream"]
    total = len(stream["mic_slices"]) + len(stream["app_notifications"])
    assert total >= 40, "琐碎日常不足，单题事件数必须 >= 40"
    stream_refs = {i["snippet_id"] for i in stream["mic_slices"]} | {i["msg_id"] for i in stream["app_notifications"]}
    cited = {ref for _dim, a in gen._iter_anchors(truth) for ref in a["evidence_ref_ids"]} & stream_refs
    assert len(cited) >= 6, "承载标答证据的关键碎片太少，题目信息量不足"
    assert len(cited) <= 0.45 * total, "关键碎片占比过高，海量琐碎日常被当成了证据"


# ---------------------------------------------------------------------------
# 反泄漏与实体可见性
# ---------------------------------------------------------------------------
def test_payload_contains_no_answer_leak_fields():
    question, _truth = _question(5)
    dumped = json.dumps(question, ensure_ascii=False)
    for field_name in ("ground_truth", "directional_ground_truth", "is_junk", "semantic_core", "red_line", "spine_id"):
        assert field_name not in dumped, f"题面泄漏答案字段 {field_name}"


def test_key_entities_appear_verbatim_in_cited_evidence():
    """标答实体必须逐字出现在被引用的证据碎片里——对手题库的第一大缺陷，这里必须为 0。"""
    for index in range(1, 41):
        question, truth = _question(index)
        index_map = gen._ref_text_index(question)
        for dim, anchor in gen._iter_anchors(truth):
            evidence = "\n".join(index_map[ref] for ref in anchor["evidence_ref_ids"])
            for entity in anchor["key_entities"]:
                assert entity in evidence, f"第 {index} 题 {dim} 的实体 {entity} 不在证据中"


def test_red_lines_never_appear_in_payload():
    for index in range(1, 41):
        question, truth = _question(index)
        payload_text = gen._payload_text(question)
        for dim, anchor in gen._iter_anchors(truth):
            for red in anchor["red_line_rejections"]:
                assert red not in payload_text, f"第 {index} 题 {dim} 的红线词 {red} 出现在题面里"


def test_validator_rejects_injected_leak_field():
    """自查器必须真的会拦：往题面塞一个答案字段就抛 BankDefect。"""
    question, truth = _question(11)
    question["cleaned_daily_stream"]["mic_slices"][0]["is_junk"] = True
    with pytest.raises(gen.BankDefect):
        gen.validate_question(question, truth)


def test_validator_rejects_hallucinated_entity():
    """自查器必须真的会拦：标答写一个题面里没有的实体就抛 BankDefect。"""
    question, truth = _question(11)
    anchor = truth["directional_ground_truth"]["dimensions"]["dim:finance"]
    anchor["key_entities"] = ["一个题面里根本不存在的实体"]
    with pytest.raises(gen.BankDefect):
        gen.validate_question(question, truth)


# ---------------------------------------------------------------------------
# 时间窗、确定性与题库多样性
# ---------------------------------------------------------------------------
def test_events_stay_inside_the_daily_window_and_are_sorted():
    for index in range(1, 21):
        question, _truth = _question(index)
        stream = question["cleaned_daily_stream"]
        for name in ("mic_slices", "app_notifications"):
            stamps = [gen.minutes_of(item["ts"]) for item in stream[name]]
            assert stamps == sorted(stamps), f"第 {index} 题 {name} 时间戳未升序"
            assert min(stamps) >= gen.DAY_START_MIN, f"第 {index} 题 {name} 早于 07:00"
            assert max(stamps) <= gen.DAY_END_MIN, f"第 {index} 题 {name} 晚于 23:30"


def test_generation_is_deterministic_and_unique():
    left = [json.dumps(_question(i)[0], ensure_ascii=False, sort_keys=True) for i in range(1, 31)]
    right = [json.dumps(_question(i)[0], ensure_ascii=False, sort_keys=True) for i in range(1, 31)]
    assert left == right, "同种子两次生成结果不一致（出卷必须可复现）"
    assert len(set(left)) == len(left), "30 道题中出现重复题面，熵不足"


def test_all_spines_produce_valid_questions():
    """32 条主线逐条遍历：任何一条产不出合格试卷都算出卷缺陷。"""
    assert len(gen.SPINES) >= 30, "主线剧情数量不足，题库熵不够"
    for spine in gen.SPINES:
        persona = None
        for seed in range(1, 400):
            candidate = gen.build_persona(random.Random(seed), seed)
            if gen._eligible(spine, candidate):
                persona = candidate
                break
        assert persona is not None, f"{spine.spine_id} 找不到匹配的人物设定"
        ctx = gen.Ctx(random.Random(99), persona)
        anchors = spine.build(ctx)
        dims = {a.dim for a in anchors}
        assert "global" in dims, f"{spine.spine_id} 缺少全局日总结锚点"
        assert len(dims) >= 3, f"{spine.spine_id} 覆盖维度不足，跨维度冲突不成立"


def test_coherence_metrics_are_perfect_on_sample():
    pairs = [_question(i) for i in range(1, 61)]
    metrics = gen.coherence_metrics(pairs)
    assert metrics["key_entity_visible_in_evidence_ratio"] == 1.0, "存在实体不在证据中的标答"
    assert metrics["directional_keyword_visible_in_evidence_ratio"] == 1.0, "存在方向词不在证据中的标答"
    assert metrics["red_line_absent_from_payload_ratio"] == 1.0, "存在红线词出现在题面中的标答"
    assert metrics["anchor_has_traceable_evidence_ratio"] == 1.0, "存在无证据可追溯的标答"
    assert metrics["mean_events_per_question"] >= 40, "平均事件数不足"


def test_cli_dry_run_reports_metrics(capsys):
    """跑批入口（--dry-run）必须能在不落盘的情况下完成自查并输出指标。"""
    assert gen.main(["--count", "8", "--dry-run"]) == 0
    captured = capsys.readouterr().out
    metrics = json.loads(captured.strip().splitlines()[-1])
    assert metrics["questions"] == 8, "跑批器统计的题数不对"
    assert sum(metrics["spine_distribution"].values()) == 8, "主线分布计数与题数不一致"
