"""战队 ``01a0aa2e`` 清洗提纯器的断言单测（Master Dispatch #11 第二阶段护栏）。

覆盖五条铁律里能被代码路径证明的部分：

* 铁律二（历史不可篡改）：:func:`purify_slice` 不得修改入参；
* 铁律三（P0 硬旁路）：急救判据耗时 ≤50ms 且大模型调用严格为 0；
* 铁律四（物理删除）：营销 / 验证码 / 风噪 / 砍一刀必须进 ``pruned_junk_ids``
  且不在保留集里；
* 铁律五（绝不自出自做）：跑批器遇到 ``solver == generator`` 必须直接中止；
* 反作弊（不许抄答案）：带答案字段与抹掉答案字段的两次调用输出必须完全一致。
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aios_core.ingest.purifier_01a0aa2e import (  # noqa: E402
    ANSWER_LEAK_FIELDS,
    SOLVER_AGENT_ID,
    emergency_triage,
    purify_slice,
    strip_answer_leak,
)
from aios_core.simulation.cleaning_arena_protocol import (  # noqa: E402
    CleaningAnswerSubmission,
    DirectionalSemanticMatcher,
)


def _mic_question() -> dict:
    """一道手工构造的高熵 MIC 考题：3 条垃圾 + 1 条借还款关键对话。"""
    return {
        "question_id": "Q_fixture_00001",
        "generator_agent": "agent-fixture",
        "timestamp_utc": "2026-09-16T08:00:00Z",
        "difficulty": "MEDIUM",
        "sensor_stream": {},
        "mic_stream": [
            {
                "snippet_id": "mic_01",
                "speaker_id": "spk_stranger_03",
                "ambient_noise_db": 82.0,
                "text": "13号线列车即将到达太平桥站，请下车的乘客提前做好准备",
                "is_background_chatter": True,
            },
            {
                "snippet_id": "mic_02",
                "speaker_id": "spk_stranger_11",
                "ambient_noise_db": 79.0,
                "text": "（邻桌/路人）健身房办卡吗，今天办送四节私教课",
                "is_background_chatter": True,
            },
            {
                "snippet_id": "mic_03",
                "speaker_id": "spk_user",
                "ambient_noise_db": 61.0,
                "text": "李姐：这8万拖得太久了，国庆后第一周一定给你结清，我给你打借条",
                "is_background_chatter": False,
                "speaker_hint": "李姐",
            },
        ],
        "voiceprint_cluster": {},
        "app_message_stream": [
            {
                "msg_id": "msg_01",
                "app": "短信",
                "sender": "10086",
                "content": "【屈臣氏】您的验证码是710641，34分钟内有效，请勿泄露给他人。",
            },
            {
                "msg_id": "msg_02",
                "app": "拼多多",
                "sender": "拼多多",
                "content": "帮我砍一刀！还差8分钱就能免费拿基围虾，点我助力→ https://url.cc/30794",
            },
            {
                "msg_id": "msg_03",
                "app": "短信",
                "sender": "工商银行",
                "content": "【工商银行】您尾号3833的账户09月07日入账人民币503,000.00元，付方：中鼎装饰。",
            },
        ],
        "user_dialogue_stream": [],
    }


def _stable(submission: dict) -> dict:
    """去掉两个必然抖动的耗时字段，其余必须逐字段一致。"""
    stable = dict(submission)
    stable.pop("execution_time_ms", None)
    stable.pop("emergency_triage_ms", None)
    return stable


def _fall_sensor_question() -> dict:
    """一道真实摔倒 + 室早连发的传感器考题。"""
    return {
        "question_id": "Q_fixture_00002",
        "generator_agent": "agent-fixture",
        "timestamp_utc": "2026-09-16T22:30:00Z",
        "difficulty": "HARD",
        "sensor_stream": {
            "segments": [
                {"seg_id": "imu_01", "kind": "walk_swing", "desc": "步行摆臂节律", "peak_g": 1.04, "hr_bpm_mean": 84},
                {
                    "seg_id": "imu_02",
                    "kind": "impact_then_stillness",
                    "desc": "卫生间发生垂直冲击后长时间静止",
                    "peak_g": 9.62,
                    "free_fall_ms": 333,
                    "stillness_after_s": 167,
                    "hr_bpm_mean": 128,
                },
            ]
        },
        "mic_stream": [],
        "voiceprint_cluster": {},
        "app_message_stream": [],
        "user_dialogue_stream": [],
    }


# ---------------------------------------------------------------------------
# 反作弊：清洗器必须对答案字段完全失明
# ---------------------------------------------------------------------------


def test_strip_answer_leak_removes_every_leak_field():
    payload = _mic_question()
    payload["ground_truth_facts"] = [{"fact_id": "F1", "dimension_id": "dim:finance"}]
    payload["ground_truth_junk_ids"] = ["mic_01"]
    payload["mic_stream"][0]["is_junk"] = True
    payload["mic_stream"][0]["junk_tag"] = "地铁报站"
    payload["trap_tag"] = "NONE"

    visible = strip_answer_leak(payload)
    dumped = json.dumps(visible, ensure_ascii=False)
    for field_name in ANSWER_LEAK_FIELDS:
        assert f'"{field_name}"' not in dumped, f"答案泄漏字段 {field_name} 未被剥离"


def test_purifier_is_blind_to_ground_truth():
    """带答案与抹答案两次调用必须产出逐字节相同的答案（不许抄答案）。"""
    blind = _mic_question()
    leaking = copy.deepcopy(blind)
    leaking["ground_truth_facts"] = [
        {
            "fact_id": "F1",
            "dimension_id": "dim:finance",
            "semantic_intent": "DEBT_BORROWING",
            "anchor_entities": ["李姐", "8万"],
            "directional_keywords": ["借款", "借条"],
            "core_content": "李姐承诺国庆后归还8万借款",
            "source_ref_id": "mic_03",
        }
    ]
    leaking["ground_truth_junk_ids"] = ["mic_01", "mic_02", "msg_01", "msg_02"]
    for item in leaking["mic_stream"]:
        item["is_junk"] = item["snippet_id"] != "mic_03"
    for item in leaking["app_message_stream"]:
        item["is_junk"] = item["msg_id"] != "msg_03"

    left = _stable(purify_slice(blind).as_submission())
    right = _stable(purify_slice(leaking).as_submission())
    assert json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right, ensure_ascii=False, sort_keys=True
    ), "清洗结果受答案字段影响，判定为抄答案"


def test_purify_does_not_mutate_input_payload():
    """铁律二：只读入参，绝不就地改写（历史不可篡改的最低要求）。"""
    payload = _mic_question()
    snapshot = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    purify_slice(payload)
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == snapshot, "入参被就地修改"


def test_purify_is_deterministic():
    payload = _mic_question()
    left = _stable(purify_slice(payload).as_submission())
    right = _stable(purify_slice(payload).as_submission())
    assert left == right, "同输入两次清洗结果不一致（引擎必须确定性）"


# ---------------------------------------------------------------------------
# 铁律四：垃圾必须物理剪枝
# ---------------------------------------------------------------------------


def test_junk_is_physically_pruned_and_key_facts_survive():
    result = purify_slice(_mic_question())
    pruned = set(result.pruned_junk_ids)
    retained = set(result.retained_item_ids)
    for junk_id in ("mic_01", "mic_02", "msg_01", "msg_02"):
        assert junk_id in pruned, f"{junk_id} 属营销/验证码/环境噪声，必须物理剪枝"
        assert junk_id not in retained, f"{junk_id} 仍被保留，未做到物理删除"
    assert "mic_03" in retained, "借还款关键对话被误删"
    assert "msg_03" in retained, "银行大额入账回执被误删"
    assert result.pruned_bytes > 0, "剪枝字节数为 0，物理删除未落地"


def test_fact_extraction_direction_and_entities():
    result = purify_slice(_mic_question())
    facts = {fact.semantic_intent: fact for fact in result.facts}
    assert "DEBT_BORROWING" in facts, "借还款约定未被提纯"
    debt = facts["DEBT_BORROWING"]
    assert debt.dimension_id == "dim:finance", "债务纠纷必须归入 dim:finance"
    assert "李姐" in debt.recognized_entities, "关键当事人李姐被张冠李戴或遗漏"
    assert debt.source_ref_id == "mic_03", "事实溯源必须指向借还款原声碎片"
    assert result.llm_tokens_used == 0, "清洗过程不得消耗大模型 token"


def test_multi_channel_mentions_collapse_into_one_fact():
    """同一真实事件在 MIC / APP / 自语三通道重复表述，提纯后只应留一条事实。"""
    payload = _mic_question()
    payload["user_dialogue_stream"] = [
        {
            "utterance_id": "ut_01",
            "raw_speech": "李姐那8万借款国庆后第一周结清，我得把借条收好",
            "context_scene": "家中客厅",
        }
    ]
    result = purify_slice(payload)
    debt_facts = [fact for fact in result.facts if fact.semantic_intent == "DEBT_BORROWING"]
    assert len(debt_facts) == 1, "同一借还款事件被重复提炼成多条事实（幻觉风险）"


# ---------------------------------------------------------------------------
# 铁律三：P0 紧急特权硬旁路
# ---------------------------------------------------------------------------


def test_p0_fall_triggers_within_budget_with_zero_model_calls():
    payload = _fall_sensor_question()
    latencies = []
    for _ in range(200):
        signal = emergency_triage(payload)
        latencies.append(signal.triage_ms)
    assert max(latencies) <= 50.0, f"P0 判据最坏耗时 {max(latencies):.3f}ms 超过 50ms 硬预算"
    signal = emergency_triage(payload)
    assert signal.triggered is True, "真实摔倒（9.62g 冲击 + 167s 静止）未触发 P0"
    assert signal.code == "P0_CRITICAL_SAFETY", "P0 标记编码不符"
    assert signal.llm_calls == 0, "P0 判据不得调用大模型"
    assert signal.source_ref_id == "imu_02", "P0 标记未溯源到冲击碎片"


def test_p0_pvc_burst_and_brady_pacer_paths():
    pvc = {
        "sensor_stream": {
            "segments": [
                {"seg_id": "imu_09", "kind": "nocturnal_pvc_burst", "pvc_run_count": 8, "hr_bpm_mean": 66}
            ]
        }
    }
    brady = {"sensor_stream": {"heart_rate_bpm": 31, "motion_state": "FALL_TILT_AFTER_PAUSE"}}
    assert emergency_triage(pvc).triggered is True, "室性早搏连续阵发未触发 P0"
    assert emergency_triage(brady).triggered is True, "缓慢性停搏（31bpm）未触发 P0"
    assert emergency_triage({"sensor_stream": {"segments": []}}).triggered is False, "空传感器流误触发 P0"


def test_off_wrist_impact_is_not_p0_but_kept_as_false_alarm():
    """脱腕伪冲击：不触发急救，但必须作为"非真实跌倒"事实保留。"""
    payload = {
        "question_id": "Q_fixture_00003",
        "generator_agent": "agent-fixture",
        "sensor_stream": {
            "fragments": [
                {
                    "fragment_id": "S00003K01",
                    "kind": "imu_impact",
                    "summary": "高g冲击但无自由落体前段，0.9秒内恢复自主运动",
                    "g_peak": 2.89,
                    "freefall_segment_ms": 0,
                    "post_impact_stillness_s": 0,
                    "resume_motion_ms": 876,
                }
            ]
        },
    }
    result = purify_slice(payload)
    assert result.emergency.triggered is False, "脱腕 / 无自由落体伪冲击不得触发急救"
    intents = {fact.semantic_intent for fact in result.facts}
    assert "FALL_IMPACT_FAKED" in intents, "伪冲击未被记录为'非真实跌倒'判定"


# ---------------------------------------------------------------------------
# 铁律五：绝不自出自做
# ---------------------------------------------------------------------------


def test_runner_refuses_self_solving(tmp_path):
    """跑批器遇到 solver == generator 必须立刻中止（一票否决）。"""
    import run_cleaning_arena_01a0aa2e as runner

    questions = tmp_path / "questions_self.jsonl"
    payload = _mic_question()
    payload["generator_agent"] = SOLVER_AGENT_ID
    payload["ground_truth_facts"] = []
    payload["ground_truth_junk_ids"] = ["mic_01"]
    questions.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        runner.main(
            [
                "--questions",
                str(questions),
                "--generator-id",
                SOLVER_AGENT_ID,
                "--solver",
                SOLVER_AGENT_ID,
                "--out-dir",
                str(tmp_path / "out"),
            ]
        )
    assert "自出自做" in str(excinfo.value), "自出自做未被拦截"


def test_answer_contract_rejects_self_solving_submission():
    """契约层同样守门：solver == generator 的提交被判违纪 0 分。"""
    from aios_core.simulation.cleaning_arena_protocol import CleaningQuestion

    payload = _mic_question()
    payload["generator_agent"] = SOLVER_AGENT_ID
    payload["ground_truth_facts"] = []
    payload["ground_truth_junk_ids"] = ["mic_01"]
    question = CleaningQuestion.model_validate(payload)
    submission = CleaningAnswerSubmission(
        question_id=question.question_id,
        solver_agent=SOLVER_AGENT_ID,
        generator_agent=SOLVER_AGENT_ID,
    )
    report = DirectionalSemanticMatcher.evaluate_submission(question, submission)
    assert report.is_self_solving_violation is True, "自出自做未被契约识别"
    assert report.final_score == 0.0, "自出自做必须判 0 分"


# ---------------------------------------------------------------------------
# 声纹聚类：本人锚定 + 一次性杂散人声剪枝
# ---------------------------------------------------------------------------


def test_voiceprint_binding_fact_and_transient_pruning():
    payload = {
        "question_id": "Q_fixture_00004",
        "generator_agent": "agent-fixture",
        "voiceprint_cluster": {
            "user_speaker_id": "vp_002",
            "total_detected_speakers": 4,
            "speakers": [
                {
                    "speaker_frag_id": "vp_001",
                    "role": "健身房会籍顾问(女)",
                    "cosine_to_user": 0.31,
                    "is_transient": True,
                    "ttl_policy": "expire_24h",
                    "n_fragments": 2,
                    "recurrence_days_30d": 0,
                },
                {
                    "speaker_frag_id": "vp_002",
                    "role": "佩戴者本人",
                    "cosine_to_user": 1.0,
                    "is_transient": False,
                    "ttl_policy": "permanent_anchor",
                    "n_fragments": 41,
                    "recurrence_days_30d": 30,
                },
                {
                    "speaker_frag_id": "vp_003",
                    "role": "核心亲友-马建军",
                    "voiceprint_match_to": "马建军",
                    "cosine_to_user": 0.79,
                    "is_transient": False,
                    "ttl_policy": "keep_90d",
                    "n_fragments": 5,
                    "sample_text": "合伙开店的分成比例谈拢了。",
                },
                {
                    "speaker_frag_id": "vp_004",
                    "role": "外卖员(男)",
                    "cosine_to_user": 0.12,
                    "is_transient": True,
                    "ttl_policy": "expire_24h",
                    "n_fragments": 1,
                    "recurrence_days_30d": 0,
                },
            ],
        },
    }
    result = purify_slice(payload)
    assert set(result.pruned_junk_ids) == {"vp_001", "vp_004"}, "一次性杂散人声必须按 24h TTL 剪枝"
    binding = [fact for fact in result.facts if fact.semantic_intent == "VOICE_BINDING_USER"]
    assert len(binding) == 1, "声纹本人锚定事实缺失"
    assert binding[0].dimension_id == "dim:social", "声纹绑定应归入 dim:social"
    assert "马建军" in binding[0].recognized_entities, "核心联系人未被绑定进实体锚点"
    assert "4人" in binding[0].recognized_entities, "说话人总数未进入实体锚点"
