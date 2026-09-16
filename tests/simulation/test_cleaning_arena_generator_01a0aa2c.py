"""出卷官（``01a0aa2c-fantonghui``）题库契约测试。

覆盖四类红线：

1. **协议合规**：每道题都能通过主干 ``CleaningQuestion`` 校验，标答合并后可直接进入
   ``DirectionalSemanticMatcher`` 阅卷；
2. **防泄漏**：题面绝不携带 ``ground_truth_*`` 与任何"分类器答案"字段（is_junk/junk_tag/...）；
3. **公平可解**：标答锚点与方向近义词必须能在题面证据里逐字溯源（绝不臆造）；
4. **出卷纪律**：五大认知域配比 ≥15%、垃圾占比 ≥90%、跨维度冲突、真假对抗陷阱齐备、
   零空占位符、片段 ID 唯一、方言/佩戴者谱系覆盖、确定性可复算。
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.simulation import cleaning_arena_generator_01a0aa2c as GEN  # noqa: E402
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    CleaningQuestion,
    DirectionalSemanticMatcher,
)

SAMPLE = 160
QUESTIONS_FILE = (
    REPO_ROOT / "benchmarks" / "data_cleaning" / "questions"
    / f"questions_{GEN.GENERATOR_AGENT}{GEN.OUTPUT_SUFFIX}.jsonl"
)
GT_FILE = (
    REPO_ROOT / "benchmarks" / "data_cleaning" / "ground_truth"
    / f"gt_{GEN.GENERATOR_AGENT}{GEN.OUTPUT_SUFFIX}.jsonl"
)


@pytest.fixture(scope="module")
def items() -> list[GEN.BankItem]:
    return list(GEN.build_bank(SAMPLE, seed=GEN.DEFAULT_SEED))


# ---------------------------------------------------------------------------
# 一、确定性与协议合规
# ---------------------------------------------------------------------------


def test_generation_is_deterministic() -> None:
    a = list(GEN.build_bank(12, seed=7))
    b = list(GEN.build_bank(12, seed=7))
    c = list(GEN.build_bank(12, seed=8))
    assert [i.question for i in a] == [i.question for i in b]
    assert [i.gt for i in a] == [i.gt for i in b]
    assert [i.question["question_id"] for i in a] != [i.question["question_id"] for i in c] or a[0] != c[0]


def test_items_validate_against_cleaning_question_contract(items: list[GEN.BankItem]) -> None:
    for item in items:
        merged = {
            **item.question,
            "ground_truth_facts": item.gt["ground_truth_facts"],
            "ground_truth_junk_ids": item.gt["ground_truth_junk_ids"],
        }
        question = CleaningQuestion.model_validate(merged)
        assert question.question_id.startswith("Q_01a0aa2c_")
        assert merged["persona"]["name"]
        assert merged["cleaned_daily_stream"]["slices_total"]
        assert question.generator_agent == GEN.GENERATOR_AGENT
        assert question.ground_truth_facts, "标答事实不得为空"
        assert question.ground_truth_junk_ids, "垃圾 ID 集合不得为空"


def test_question_ids_are_sequential_and_unique(items: list[GEN.BankItem]) -> None:
    ids = [item.question["question_id"] for item in items]
    assert len(set(ids)) == len(ids)
    assert ids[0].endswith("00001")
    assert ids[1].endswith("00002")


# ---------------------------------------------------------------------------
# 二、防泄漏：题面绝不能出现标答与分类器答案
# ---------------------------------------------------------------------------


def test_question_payload_has_no_leak_fields(items: list[GEN.BankItem]) -> None:
    for item in items:
        keys = [str(k) for k in GEN._walk_keys(item.question)]
        assert "ground_truth_facts" not in keys
        assert "ground_truth_junk_ids" not in keys
        for forbidden in GEN.FORBIDDEN_QUESTION_KEYS:
            assert forbidden not in keys, f"{item.question['question_id']} 泄漏字段 {forbidden}"


def test_ground_truth_ids_exist_and_are_unique(items: list[GEN.BankItem]) -> None:
    for item in items:
        ids = [fid for _, fid, _ in GEN.iter_question_slices(item.question)]
        assert len(set(ids)) == len(ids), f"{item.question['question_id']} 片段 ID 重复"
        junk = item.gt["ground_truth_junk_ids"]
        assert len(set(junk)) == len(junk)
        assert set(junk) <= set(ids), "垃圾 ID 必须指向真实片段"
        sources = {f["source_ref_id"] for f in item.gt["ground_truth_facts"]}
        assert sources and sources <= set(ids), "事实证据源必须指向真实片段"


# ---------------------------------------------------------------------------
# 三、公平可解：锚点/方向词可溯源（绝不臆造）
# ---------------------------------------------------------------------------


def test_every_item_passes_self_audit(items: list[GEN.BankItem]) -> None:
    problems = [
        (item.question["question_id"], issue)
        for item in items
        for issue in GEN.audit_item(item)
    ]
    assert problems == [], f"出卷自检未通过：{problems[:5]}"


def test_anchor_entities_are_grounded_in_evidence(items: list[GEN.BankItem]) -> None:
    for item in items:
        evidence = " ".join(text for _, _, text in GEN.iter_question_slices(item.question))
        for fact in item.gt["ground_truth_facts"]:
            concrete = [a for a in fact["anchor_entities"] if a != GEN.WEARER]
            assert concrete, "每条事实至少有一个具体锚点实体"
            assert any(a in evidence for a in concrete), (
                f"{fact['fact_id']} 锚点无法溯源：{concrete}"
            )


def test_directional_keywords_have_synonym_clusters(items: list[GEN.BankItem]) -> None:
    for item in items:
        evidence = " ".join(text for _, _, text in GEN.iter_question_slices(item.question))
        for fact in item.gt["ground_truth_facts"]:
            keywords = fact["directional_keywords"]
            assert len(keywords) >= 4, "方向容差簇至少 4 个近义词"
            hits = [kw for kw in keywords if kw and kw in evidence]
            assert len(hits) >= 2, f"{fact['fact_id']} 证据内方向词不足：{hits}"


def test_junk_never_echoes_fact_anchors(items: list[GEN.BankItem]) -> None:
    for item in items:
        anchors = {
            a for fact in item.gt["ground_truth_facts"]
            for a in fact["anchor_entities"] if a != GEN.WEARER and len(a) >= 2
        }
        junk = set(item.gt["ground_truth_junk_ids"])
        for _, fid, text in GEN.iter_question_slices(item.question):
            if fid in junk and text:
                assert not any(a in text for a in anchors), f"垃圾片段复述锚点：{fid}"


# ---------------------------------------------------------------------------
# 四、出卷纪律：配比、陷阱、噪声密度、谱系覆盖
# ---------------------------------------------------------------------------


def test_five_domains_are_balanced_and_above_floor(items: list[GEN.BankItem]) -> None:
    share = GEN.bank_statistics(items)["primary_domain_share"]
    assert set(share) == {
        "dim:health", "dim:finance", "dim:social", "dim:career", "dim:life",
    }
    for domain, value in share.items():
        assert value >= 0.15, f"{domain} 占比 {value} 低于 15% 红线"
    fact_share = GEN.bank_statistics(items)["dimension_share"]
    for domain, value in fact_share.items():
        assert value >= 0.15, f"{domain} 事实级占比 {value} 低于 15% 红线"


def test_data_flow_modality_shares_follow_dispatch(items: list[GEN.BankItem]) -> None:
    """派工单规定的五大数据流配比：传感器 30% / MIC 30% / 声纹 20% / APP 15% / 用户原话 5%。"""
    share = GEN.bank_statistics(items)["modality_share"]
    assert set(share) == {"sensor", "mic", "voiceprint", "app", "utterance"}
    expected = {"sensor": 0.30, "mic": 0.30, "voiceprint": 0.20, "app": 0.15, "utterance": 0.05}
    for modality, target in expected.items():
        assert abs(share[modality] - target) <= 0.03, f"{modality} 配比 {share[modality]} 偏离 {target}"
    for item in items:
        assert item.question["modality_tag"] in expected


def test_role_contract_fields_present(items: list[GEN.BankItem]) -> None:
    """出卷官 V3 契约：question_id / persona / cleaned_daily_stream / directional_ground_truth 齐备。"""
    for item in items:
        q, gt = item.question, item.gt
        persona = q["persona"]
        for key in ("name", "age", "city", "occupation", "life_stage", "key_relations"):
            assert persona[key], f"{q['question_id']} persona 缺字段 {key}"
        stream = q["cleaned_daily_stream"]
        assert stream["slices_total"] == sum(1 for _ in GEN.iter_question_slices(q))
        assert q["day_span"] == GEN.DAY_WINDOW
        start, end = stream["time_span"].split("~")
        to_min = lambda t: int(t[:2]) * 60 + int(t[3:])  # noqa: E731
        assert GEN.DAY_START_MIN <= to_min(start) < to_min(end) <= GEN.DAY_START_MIN + GEN.DAY_SPAN_MIN
        assert to_min(end) - to_min(start) >= 14 * 60, "全天生活流跨度不足 14 小时"
        assert gt["directional_ground_truth"]["dimensions"]


def test_six_directions_with_synonyms_and_red_lines(items: list[GEN.BankItem]) -> None:
    """六维方向性标答：全局日总结 + health/social/emotion/finance/career，且同义词与红线齐备。"""
    for item in items:
        block = item.gt["directional_ground_truth"]
        dims = {d["dimension_id"]: d for d in block["dimensions"]}
        for required in GEN.ROLE_DIMENSIONS:
            assert required in dims, f"{item.question['question_id']} 缺维度 {required}"
        facts_by_dim = {f["dimension_id"]: f for f in item.gt["ground_truth_facts"]}
        facts_by_id = {f["fact_id"]: f for f in item.gt["ground_truth_facts"]}
        for dim_id, entry in dims.items():
            has_summary = bool(entry.get("direction_summary"))
            has_ref = entry.get("fact_ref") in facts_by_id
            assert has_summary or has_ref, f"{dim_id} 缺少方向性要点（既无摘要也无事实引用）"
            assert len(entry["acceptable_synonyms"]) >= 2, f"{dim_id} 可接受方向同义词不足"
            assert entry["absolute_red_lines"], f"{dim_id} 缺少绝对偏离红线判据"
            if dim_id in facts_by_dim:
                assert entry["fact_ref"] == facts_by_dim[dim_id]["fact_id"]
                assert entry["acceptable_synonyms"] == list(facts_by_dim[dim_id]["directional_keywords"])[:3]
        # 事实维度与单维总结必须一一对齐（不张冠李戴）
        for dim_id, fact in facts_by_dim.items():
            if dim_id in dims:
                assert dims[dim_id]["fact_ref"] == fact["fact_id"]


def test_red_line_families_cover_every_intent(items: list[GEN.BankItem]) -> None:
    """每一条事实都必须落入一个红线判据族（不允许无语义去向的裸事实）。"""
    families = {
        GEN.INTENT_VETO_FAMILY.get(fact["semantic_intent"], "GENERIC")
        for item in items
        for fact in item.gt["ground_truth_facts"]
    }
    assert "GENERIC" not in families
    assert len(families) >= 10, "红线判据族过少，覆盖面不足"


def test_conflict_truth_never_accepts_flirtation(items: list[GEN.BankItem]) -> None:
    """老大点名的判例：事实是吵架/决裂时，标"打情骂俏/甜蜜互动"必须一票否决。"""
    checked = 0
    for item in items:
        block = item.gt["directional_ground_truth"]
        dims = {d["dimension_id"]: d for d in block["dimensions"]}
        for fact in item.gt["ground_truth_facts"]:
            if GEN.INTENT_VETO_FAMILY.get(fact["semantic_intent"]) != "CONFLICT_RUPTURE":
                continue
            entry = dims[fact["dimension_id"]]
            assert any("打情骂俏" in line for line in entry["absolute_red_lines"]), (
                f"{fact['fact_id']} 缺少（打情骂俏=一票否决）红线"
            )
            assert dims["dim:emotion"]["direction_summary"] == GEN.EMOTION_ARCS["NEGATIVE"]["arc"]
            checked += 1
    assert checked > 0, "样本里应当包含吵架/决裂类事实"


def test_junk_density_follows_iron_law_four(items: list[GEN.BankItem]) -> None:
    stats = GEN.bank_statistics(items)
    assert stats["junk_ratio_min"] >= 0.90
    assert stats["junk_ratio_mean"] >= 0.92


def test_adversarial_traps_are_present(items: list[GEN.BankItem]) -> None:
    intents = {
        fact["semantic_intent"]
        for item in items
        for fact in item.gt["ground_truth_facts"]
    }
    for trap_intent in (
        "TRANSFER_FAILED_COUNTERPARTY",     # T01 假借条对冲
        "PROMISE_REVERSAL_CONFLICT",        # T02 先承认后反悔
        "EVIDENCE_WITHDRAWAL_DENIAL",       # T03 撤回与销毁证据
        "STAGED_FALL_CLAIM",                # T04 假摔诈伤（体动证据）
        "STAGED_FALL_COMPENSATION",         # T04 假摔诈伤（索赔冲突）
    ):
        assert trap_intent in intents, f"缺少对抗陷阱：{trap_intent}"


def test_cross_domain_conflict_never_shares_a_dimension(items: list[GEN.BankItem]) -> None:
    for item in items:
        dims = [f["dimension_id"] for f in item.gt["ground_truth_facts"]]
        assert len(set(dims)) == len(dims), f"{item.question['question_id']} 事实维度重叠"


def test_multimodal_streams_are_populated(items: list[GEN.BankItem]) -> None:
    for item in items:
        q = item.question
        assert q["mic_stream"], "MIC 流不得为空"
        assert q["app_message_stream"], "APP 消息流不得为空"
        assert q["user_dialogue_stream"], "用户原话流不得为空"
        assert q["sensor_stream"]["fragments"], "传感器流不得为空"
        assert len(q["voiceprint_cluster"]["speakers"]) >= 3, "声纹簇至少 3 个碎片"
        assert q["voiceprint_cluster"]["user_speaker_id"] == "spk_user"
        for slice_item in (*q["mic_stream"], *q["app_message_stream"], *q["user_dialogue_stream"]):
            text = slice_item.get("text") or slice_item.get("content") or slice_item.get("raw_speech")
            assert text and text.strip(), "零空占位符红线"


def test_sensor_evidence_windows_are_physically_consistent(items: list[GEN.BankItem]) -> None:
    seen = 0
    for item in items:
        facts = {f["source_ref_id"] for f in item.gt["ground_truth_facts"]}
        for frag in item.question["sensor_stream"]["fragments"]:
            if frag["fragment_id"] not in facts:
                continue
            seen += 1
            assert "summary" in frag and frag["summary"], "传感器证据窗必须有事件描述"
            assert frag["kind"] != "household_chores"
            if "g_peak" in frag:
                assert frag["g_peak"] >= 1.0
    assert seen > 0, "样本中应包含传感器类事实"


def test_persona_region_dialect_coverage(items: list[GEN.BankItem]) -> None:
    personas = {str(item.question["persona_tag"]).split("_")[0] for item in items}
    assert len(personas) >= 10, "佩戴者谱系覆盖不足"
    device_ids = {str(item.question["sensor_stream"]["device_id"]) for item in items}
    assert len(device_ids) >= 10, "设备/地域覆盖不足"


def test_core_content_is_unique_and_readable(items: list[GEN.BankItem]) -> None:
    stats = GEN.bank_statistics(items)
    assert stats["core_unique_rate"] >= 0.97
    for item in items:
        for fact in item.gt["ground_truth_facts"]:
            core = fact["core_content"]
            assert len(core) >= 20 and "TODO" not in core
            assert "意图方向" in core or any(
                a in core for a in fact["anchor_entities"] if a != GEN.WEARER
            )


def test_answered_by_ground_truth_scores_full_marks(items: list[GEN.BankItem]) -> None:
    """公平性回归：逐字抄标答必须满分（证明题面与标答自洽、无不可解事实）。"""
    for item in items[:60]:
        merged = {
            **item.question,
            "ground_truth_facts": item.gt["ground_truth_facts"],
            "ground_truth_junk_ids": item.gt["ground_truth_junk_ids"],
        }
        question = CleaningQuestion.model_validate(merged)
        submission = CleaningAnswerSubmission.model_validate({
            "question_id": item.question["question_id"],
            "solver_agent": "agent-probe",
            "generator_agent": GEN.GENERATOR_AGENT,
            "extracted_facts": [
                {
                    "fact_id": fact["fact_id"],
                    "dimension_id": fact["dimension_id"],
                    "semantic_intent": fact["semantic_intent"],
                    "summary_text": fact["core_content"],
                    "recognized_entities": fact["anchor_entities"],
                    "source_ref_id": fact["source_ref_id"],
                }
                for fact in item.gt["ground_truth_facts"]
            ],
            "pruned_junk_ids": item.gt["ground_truth_junk_ids"],
        })
        report = DirectionalSemanticMatcher.evaluate_submission(question, submission)
        assert report.final_score == 100.0, (
            f"{item.question['question_id']} 标答自评未满分：{report.final_score} "
            f"{report.critique_notes[:2]}"
        )


def test_self_solving_is_vetoed(items: list[GEN.BankItem]) -> None:
    """铁律五：自出自做一票否决。"""
    item = items[0]
    question = CleaningQuestion.model_validate({
        **item.question,
        "ground_truth_facts": item.gt["ground_truth_facts"],
        "ground_truth_junk_ids": item.gt["ground_truth_junk_ids"],
    })
    submission = CleaningAnswerSubmission.model_validate({
        "question_id": item.question["question_id"],
        "solver_agent": GEN.GENERATOR_AGENT,
        "generator_agent": GEN.GENERATOR_AGENT,
        "extracted_facts": [],
        "pruned_junk_ids": item.gt["ground_truth_junk_ids"],
    })
    report = DirectionalSemanticMatcher.evaluate_submission(question, submission)
    assert report.is_self_solving_violation is True
    assert report.final_score == 0.0


# ---------------------------------------------------------------------------
# 五、落盘产物（题库已生成时校验；未生成则跳过，保证 CI 可独立运行）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not QUESTIONS_FILE.exists(), reason="题库尚未生成")
def test_question_file_has_no_ground_truth_and_matches_manifest() -> None:
    manifest_path = QUESTIONS_FILE.with_name(f"manifest_{GEN.GENERATOR_AGENT}{GEN.OUTPUT_SUFFIX}.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["count"] == 10000
    assert GEN.sha256_file(QUESTIONS_FILE) == manifest["questions_sha256"]
    assert GEN.sha256_file(GT_FILE) == manifest["ground_truth_sha256"]
    with QUESTIONS_FILE.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= 300:
                break
            payload = json.loads(line)
            assert "ground_truth_facts" not in payload
            assert "ground_truth_junk_ids" not in payload


@pytest.mark.skipif(not GT_FILE.exists(), reason="标答尚未生成")
def test_ground_truth_file_is_clean_and_complete() -> None:
    counts = collections.Counter()
    with GT_FILE.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            payload = json.loads(line)
            counts["questions"] += 1
            counts["facts"] += len(payload["ground_truth_facts"])
            counts["junk"] += len(payload["ground_truth_junk_ids"])
            assert payload["ground_truth_junk_ids"], "标答垃圾集合不得为空"
    assert counts["questions"] == 10000
    assert counts["facts"] >= 10000          # 至少一条核心事实/题（高熵卷可含跨域冲突的双事实）
    with GT_FILE.open(encoding="utf-8") as handle:
        first = json.loads(handle.readline())
    assert first["directional_ground_truth"]["dimensions"], "标答必须携带六维方向性要点"
    assert counts["junk"] >= 200000          # 铁律四：海量垃圾必须被标记物理剪枝
