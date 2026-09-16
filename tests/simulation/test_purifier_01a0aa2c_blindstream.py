"""做题战队 ``01a0aa2c-fantonghui`` 盲卷清洗提纯器验收单测。

覆盖五大铁律的工程判据（Master Dispatch #11 第二/三阶段验收）：

* 铁律 2：提纯器纯函数、不篡改输入、不产出任何历史回写；
* 铁律 3：P0 紧急安全硬旁路 ≤50ms、0 大模型调用；
* 铁律 4：推销/风噪/验证码/钓鱼垃圾 100% 物理剪枝，零误剪核心证据；
* 铁律 5：结构性剥离内嵌标答字段（防偷看、防自编自答）；
* 语义鉴别：真摔 vs 摘腕误报、借款 vs 玩笑钓鱼、真实就医 vs 口嗨吹牛。
"""

from __future__ import annotations

import copy
import time

import pytest

from aios_core.ingest.purifier_01a0aa2c_fantonghui_blindstream import (
    P0_BYPASS_BUDGET_MS,
    PURIFIER_VERSION,
    SOLVER_AGENT_ID,
    BlindStreamPurifier,
)


@pytest.fixture()
def purifier() -> BlindStreamPurifier:
    return BlindStreamPurifier()


def _mic(qid: str, idx: int, **kw) -> dict:
    snip = {
        "snippet_id": f"{qid}-mic-{idx:03d}",
        "text": "邻桌：他们家酸菜鱼一般，还不如楼下那家",
        "ambient_noise_db": 80,
        "duration_s": 10,
        "is_background_chatter": True,
    }
    snip.update(kw)
    return snip


def _question(qid: str, **streams) -> dict:
    q = {
        "question_id": qid,
        "generator_agent": "agent-a9f6",
        "timestamp_utc": "2026-09-16T00:00:00Z",
        "difficulty": "HARD",
        "sensor_stream": {},
        "mic_stream": [],
        "voiceprint_cluster": {},
        "app_message_stream": [],
        "user_dialogue_stream": [],
    }
    q.update(streams)
    return q


# ---------------------------------------------------------------------------
# 铁律 5：结构性剥离标答，防偷看、防自编自答
# ---------------------------------------------------------------------------


class TestBlindDiscipline:
    def test_embedded_ground_truth_is_structurally_stripped(self, purifier):
        """即使题库把标答内嵌在题目里，提纯器也绝不读取（输出与盲卷一致）。"""
        qid = "Q_test_001"
        base = _question(
            qid,
            mic_stream=[
                _mic(qid, 1, text="父亲：存折密码是你生日倒过来，万一我有个三长两短就找它",
                     speaker_hint="父亲", is_background_chatter=False),
                _mic(qid, 2),
            ],
        )
        leaked = copy.deepcopy(base)
        leaked["ground_truth_facts"] = [
            {
                "fact_id": "FAKE", "dimension_id": "dim:finance",
                "semantic_intent": "DEBT_BORROWING", "anchor_entities": ["1亿元"],
                "directional_keywords": ["转账"], "core_content": "钓鱼标答",
                "source_ref_id": "x",
            }
        ]
        leaked["ground_truth_junk_ids"] = [f"{qid}-mic-001"]

        a1, _ = purifier.purify(base)
        a2, _ = purifier.purify(leaked)
        # 计时字段天然波动，不参与纯函数等值断言
        a1.pop("execution_time_ms"), a2.pop("execution_time_ms")
        assert a1 == a2, "内嵌标答不得影响清洗结论（防偷看纪律）"
        # 钓鱼标答里的意图与实体绝不出现
        assert a2["extracted_facts"][0]["semantic_intent"] == "FAMILY_ENTRUSTMENT"
        assert "1亿元" not in str(a2["extracted_facts"])

    def test_solver_identity_never_equals_generator(self, purifier):
        q = _question("Q_test_002", mic_stream=[_mic("Q_test_002", 1)])
        answer, _ = purifier.purify(q)
        assert answer["solver_agent"] == SOLVER_AGENT_ID
        assert answer["generator_agent"] == "agent-a9f6"
        assert answer["solver_agent"] != answer["generator_agent"]  # 严禁自出自做


# ---------------------------------------------------------------------------
# 铁律 2：历史不可篡改（纯函数、不改动输入）
# ---------------------------------------------------------------------------


class TestHistoryImmutability:
    def test_purify_is_pure_and_does_not_mutate_input(self, purifier):
        q = _question(
            "Q_test_010",
            mic_stream=[
                _mic("Q_test_010", 1, text="李姐：这8万拖得太久了，国庆后第一周一定给你结清，我给你打借条",
                     speaker_hint="李姐", is_background_chatter=False),
                _mic("Q_test_010", 2),
            ],
        )
        frozen = copy.deepcopy(q)
        a1, _ = purifier.purify(q)
        assert q == frozen, "提纯器不得改动题目原文（历史不可篡改）"
        # 事实只新增挂载，不存在任何 UPDATE/DELETE 语义字段
        assert set(a1.keys()) == {
            "question_id", "solver_agent", "generator_agent",
            "extracted_facts", "pruned_junk_ids", "execution_time_ms", "llm_tokens_used",
        }
        a2, _ = purifier.purify(q)
        a1.pop("execution_time_ms"), a2.pop("execution_time_ms")
        assert a1 == a2, "同一输入必须产出同一答卷（纯函数，无隐藏状态）"


# ---------------------------------------------------------------------------
# 铁律 3：P0 紧急安全硬旁路（≤50ms、0 大模型调用）
# ---------------------------------------------------------------------------


class TestP0HardBypass:
    def test_real_fall_bypass_latency_and_zero_llm(self, purifier):
        qid = "Q_test_020"
        q = _question(
            qid,
            sensor_stream={
                "segments": [
                    {"seg_id": f"{qid}-imu-001", "kind": "walk_swing", "desc": "步行摆臂节律",
                     "peak_g": 1.1, "hr_bpm_mean": 96, "duration_s": 300},
                    {"seg_id": f"{qid}-imu-002", "desc": "卧室床边发生垂直冲击后长时间静止",
                     "peak_g": 8.4, "free_fall_ms": 310, "stillness_after_s": 140,
                     "hr_bpm_mean": 110, "duration_s": 200},
                ]
            },
        )
        t0 = time.perf_counter()
        answer, audit = purifier.purify(q)
        wall = (time.perf_counter() - t0) * 1000
        assert audit.p0_bypass_triggered is True
        assert audit.p0_bypass_latency_ms <= P0_BYPASS_BUDGET_MS  # ≤50ms 硬门禁
        assert wall < 1000  # 全链路也是毫秒级
        assert answer["llm_tokens_used"] == 0  # 大模型调用严格为 0
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "FALL_IMPACT"
        assert fact["dimension_id"] == "dim:health"
        assert "卧室床边" in fact["recognized_entities"]  # 地点锚点从观测描述提取
        assert "佩戴者" in fact["recognized_entities"]

    def test_off_wrist_trap_is_false_alarm_not_p0(self, purifier):
        """摘腕伪冲击必须走 FALSE_ALARM 纪律，不得挤占 P0、不得误报跌倒。"""
        qid = "Q_test_021"
        q = _question(
            qid,
            sensor_stream={
                "segments": [
                    {"seg_id": f"{qid}-imu-001", "desc": "摘腕后坠落硬质地面",
                     "peak_g": 7.2, "off_wrist_flag": 1, "gait_resumed_after_s": 15,
                     "hr_bpm_mean": 78, "duration_s": 60},
                ]
            },
        )
        answer, audit = purifier.purify(q)
        assert audit.p0_bypass_triggered is False  # 摘腕误报不占用 P0 通道
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "OFF_WRIST_FALSE_ALARM"
        assert "手环" in fact["recognized_entities"]
        assert "非真实跌倒" in fact["summary_text"]

    def test_cardiac_burst_bypass(self, purifier):
        qid = "Q_test_022"
        q = _question(
            qid,
            sensor_stream={
                "segments": [
                    {"seg_id": f"{qid}-imu-001", "desc": "夜间睡眠期室性早搏连续阵发",
                     "pvc_run_count": 9, "longest_run_beats": 5, "rr_irregularity": 0.31,
                     "hr_bpm_mean": 64, "peak_g": 0.02, "duration_s": 1600},
                ]
            },
        )
        answer, audit = purifier.purify(q)
        assert audit.p0_bypass_triggered is True
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "PVC_BURST"
        assert "9阵" in fact["recognized_entities"]

    def test_faint_distress_call_bypass(self, purifier):
        qid = "Q_test_023"
        q = _question(
            qid,
            mic_stream=[
                _mic(qid, 1),
                _mic(qid, 2, text="（气声）……喘不上气……谁来搭把手……",
                     voice_level_db=41, speaker_hint="佩戴者",
                     is_background_chatter=False),
            ],
        )
        answer, audit = purifier.purify(q)
        assert audit.p0_bypass_triggered is True
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "FAINT_DISTRESS_CALL"
        assert fact["dimension_id"] == "dim:health"


# ---------------------------------------------------------------------------
# 铁律 4：物理剪枝
# ---------------------------------------------------------------------------


class TestIronLawFourPruning:
    def test_promo_wind_verification_junk_all_pruned(self, purifier):
        qid = "Q_test_030"
        q = _question(
            qid,
            mic_stream=[
                _mic(qid, 1, text="（呼呼——风噪压过人声，无有效语义）"),
                _mic(qid, 2, text="各位顾客请注意，名创优品限时秒杀开始了，仅限今天仅限今天"),
                _mic(qid, 3, text="新鲜的桃子十块钱三斤，不甜不要钱嘞"),
                _mic(qid, 4, text="李姐：这8万拖得太久了，国庆后第一周一定给你结清，我给你打借条",
                     speaker_hint="李姐", is_background_chatter=False),
            ],
            app_message_stream=[
                {"msg_id": f"{qid}-app-001", "app_name": "拼多多", "sender": "同学群",
                 "content": "帮我砍一刀！就差0.9%就能免费拿空气炸锅啦", "minute_offset": 10},
                {"msg_id": f"{qid}-app-002", "app_name": "短信", "sender": "优衣库",
                 "content": "【优衣库】您的验证码为482913，5分钟内有效，请勿泄露", "minute_offset": 20},
                {"msg_id": f"{qid}-app-003", "app_name": "短信", "sender": "+85261xxxx",
                 "content": "【法院通知】您有一份传票未领取，加微信fk8899处理（诈骗）", "minute_offset": 30},
                {"msg_id": f"{qid}-app-004", "app_name": "短信", "sender": "12368",
                 "content": "【江岸区人民法院】您涉及的劳动争议一案定于11月3日上午9时30分开庭，"
                            "请携带身份证件及证据材料准时出庭。案号（2026）民初3881号。",
                 "minute_offset": 40},
            ],
        )
        answer, _ = purifier.purify(q)
        pruned = set(answer["pruned_junk_ids"])
        # 环境风噪 / 商场叫卖 / 砍一刀 / 验证码 / 钓鱼传票 全部物理删除
        assert {f"{qid}-mic-001", f"{qid}-mic-002", f"{qid}-mic-003",
                f"{qid}-app-001", f"{qid}-app-002", f"{qid}-app-003"} <= pruned
        # 核心证据（借款约定 + 真法院传票）绝不误剪
        assert f"{qid}-mic-004" not in pruned
        assert f"{qid}-app-004" not in pruned
        assert len(answer["extracted_facts"]) == 2  # DEBT + COURT，无幻觉
        intents = {f["semantic_intent"] for f in answer["extracted_facts"]}
        assert intents == {"DEBT_BORROWING", "COURT_SUMMONS"}

    def test_stray_voiceprints_pruned_keep_user_and_contact(self, purifier):
        qid = "Q_test_031"
        q = _question(
            qid,
            voiceprint_cluster={
                "user_speaker_id": f"{qid}-vp-spk-01",
                "enrolled_contacts": ["丈夫"],
                "n_detected_speakers": 4,
                "detected_speakers": [
                    {"spk_id": f"{qid}-vp-spk-01", "n_fragments": 40,
                     "cosine_to_enrolled_user": 0.96, "sample_text": "好，那就这么定。",
                     "recurrence_days_30d": 30},
                    {"spk_id": f"{qid}-vp-spk-02", "n_fragments": 3,
                     "cosine_to_enrolled_user": 0.12, "sample_text": "快递员：新店开业进来看看",
                     "recurrence_days_30d": 0},
                    {"spk_id": f"{qid}-vp-spk-03", "n_fragments": 2,
                     "cosine_to_enrolled_user": 0.05, "sample_text": "外卖员：办卡吗今天有活动",
                     "recurrence_days_30d": 1},
                    {"spk_id": f"{qid}-vp-spk-04", "n_fragments": 38,
                     "cosine_to_enrolled_user": 0.33,
                     "cosine_to_contact_bank": {"丈夫": 0.91},
                     "sample_text": "合伙开店的分成比例谈拢了。", "recurrence_days_30d": 16},
                ],
            },
        )
        answer, _ = purifier.purify(q)
        pruned = set(answer["pruned_junk_ids"])
        assert pruned == {f"{qid}-vp-spk-02", f"{qid}-vp-spk-03"}  # 杂散声纹物理剪枝
        assert {f["semantic_intent"] for f in answer["extracted_facts"]} == {
            "VOICEPRINT_IDENTITY_BINDING", "KEY_CONVERSATION_WITH_CONTACT",
        }
        key_fact = next(
            f for f in answer["extracted_facts"]
            if f["semantic_intent"] == "KEY_CONVERSATION_WITH_CONTACT"
        )
        assert "丈夫" in key_fact["recognized_entities"]


# ---------------------------------------------------------------------------
# 语义鉴别：反讽 / 反事实 / 强撑否认（FALSE_ALARM 纪律）
# ---------------------------------------------------------------------------


class TestSemanticDiscrimination:
    def test_joke_bait_never_becomes_debt_fact(self, purifier):
        """打赌玩笑里的"一百万/一个亿"绝不能入账为借款事实（反事实校验）。"""
        qid = "Q_test_040"
        q = _question(
            qid,
            mic_stream=[_mic(qid, 1, text="邻桌：哈哈你再抢我薯条就欠我一个亿，明天就还！")],
        )
        answer, _ = purifier.purify(q)
        assert answer["extracted_facts"] == []
        assert answer["pruned_junk_ids"] == [f"{qid}-mic-001"]

    def test_drunk_boasting_not_financial_fact(self, purifier):
        qid = "Q_test_041"
        q = _question(
            qid,
            user_dialogue_stream=[
                {"utterance_id": f"{qid}-utt-001", "raw_speech": "累了累了，躺平躺平",
                 "context_scene": "口头禅", "emotional_tone": "平淡"},
                {"utterance_id": f"{qid}-utt-002",
                 "raw_speech": "（酒局，含混）跟你们说，下个月我必收购腾讯，谁拦我跟谁急！",
                 "context_scene": "酒局吹牛", "emotional_tone": "亢奋"},
            ],
        )
        answer, _ = purifier.purify(q)
        assert len(answer["extracted_facts"]) == 1
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "DRUNK_BOASTING"
        assert fact["dimension_id"] == "dim:social"
        assert "不可采信" in fact["summary_text"]

    def test_emotional_vent_no_false_alarm(self, purifier):
        """"想跳楼"口头禅 + 快速平复 → 情绪宣泄，非 P0 自残告警。"""
        qid = "Q_test_042"
        q = _question(
            qid,
            user_dialogue_stream=[
                {"utterance_id": f"{qid}-utt-001",
                 "raw_speech": "烦死了烦死了，想跳楼的心都有了……算了点个奶茶压压惊",
                 "context_scene": "口头禅发泄", "emotional_tone": "烦躁后迅速平复"},
            ],
        )
        answer, audit = purifier.purify(q)
        assert audit.p0_bypass_triggered is False  # FALSE_ALARM 纪律：不触发 P0
        assert answer["extracted_facts"][0]["semantic_intent"] == "EMOTIONAL_VENT"
        assert answer["extracted_facts"][0]["dimension_id"] == "dim:social"

    def test_hidden_cardiac_crisis_detected_with_denial(self, purifier):
        qid = "Q_test_043"
        q = _question(
            qid,
            sensor_stream={
                "segments": [
                    {"seg_id": f"{qid}-imu-001", "desc": "多体征并发异常",
                     "hr_bpm_mean": 126, "eda_surge": 1, "resp_rate": 28, "duration_s": 300},
                ]
            },
            user_dialogue_stream=[
                {"utterance_id": f"{qid}-utt-001", "raw_speech": "我没事，你们先吃……（捂胸口，呼吸急促）",
                 "context_scene": "强撑否认", "emotional_tone": "虚弱嘴硬"},
            ],
        )
        answer, _ = purifier.purify(q)
        assert len(answer["extracted_facts"]) == 1  # 多模态证据链合并为单事实，无幻觉
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "HIDDEN_CARDIAC_CRISIS"
        assert fact["dimension_id"] == "dim:health"
        assert "126bpm" in fact["recognized_entities"]

    def test_bank_transfer_structural_detection(self, purifier):
        """v2：银行凭证结构化判定（不依赖枚举清单，任意银行名均可识别）。"""
        qid = "Q_test_044"
        q = _question(
            qid,
            app_message_stream=[
                {"msg_id": f"{qid}-app-001", "app_name": "短信", "sender": "宁波银行",
                 "content": "【宁波银行】您尾号2210的账户09月12日入账人民币88,600.00元，付方：老王。",
                 "minute_offset": 50},
            ],
        )
        answer, _ = purifier.purify(q)
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "BANK_LARGE_TRANSFER"
        assert fact["dimension_id"] == "dim:finance"
        assert "88,600.00元" in fact["recognized_entities"]

    def test_medication_entrustment_detected(self, purifier):
        """v2：降压药/取药类家人嘱托（v1 曾漏检的模板族）。"""
        qid = "Q_test_045"
        q = _question(
            qid,
            mic_stream=[
                _mic(qid, 1, text="母亲：你爸的降压药吃完了，明天记得去中山医院帮他取药",
                     speaker_hint="母亲", is_background_chatter=False),
            ],
        )
        answer, _ = purifier.purify(q)
        fact = answer["extracted_facts"][0]
        assert fact["semantic_intent"] == "FAMILY_ENTRUSTMENT"
        assert fact["dimension_id"] == "dim:family"
        assert "母亲" in fact["recognized_entities"]

    def test_version_and_identity_constants(self):
        assert PURIFIER_VERSION == "v2"
        assert SOLVER_AGENT_ID == "01a0aa2c-fantonghui"
