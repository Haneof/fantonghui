"""数据清洗提纯引擎测试：盲审契约、跨队约束、垃圾剪枝、不可篡改性。"""

from __future__ import annotations

import copy

import pytest

from aios_core.perception.cleaning_solver import (
    CleaningSolver,
    LeakageError,
    SolverConfig,
    assert_blind,
    assert_cross_team,
    blind_view,
)


def make_question() -> dict:
    return {
        "question_id": "Q_rival_00001",
        "generator_agent": "rival-team",
        "difficulty": "HARD",
        "timestamp_utc": "2026-09-16T10:00:00Z",
        "sensor_stream": {"heart_rate_bpm": 88, "pvc_burst_count": 0, "motion_state": "WALKING"},
        "mic_stream": [
            {
                "snippet_id": "mic_01",
                "speaker_id": "spk_stranger",
                "text": "煎饼果子！热乎的煎饼果子！加蛋加肠现摊现卖！",
                "ambient_noise_db": 78.0,
                "is_junk": True,
            },
            {
                "snippet_id": "mic_02",
                "speaker_id": "spk_landlord",
                "text": "租的房子下水管道倒灌，数万元名贵物品全被泡了，找房东索赔",
                "ambient_noise_db": 62.0,
                "is_junk": False,
            },
        ],
        "app_message_stream": [
            {
                "msg_id": "msg_01",
                "app": "拼多多",
                "sender": "砍一刀互助群",
                "content": "【帮我点一下】我只差0.01元就能提现100元现金！",
                "is_junk": True,
            },
            {
                "msg_id": "msg_02",
                "app": "SMS",
                "sender": "垃圾短信",
                "content": "您的验证码是4829，5分钟内有效，请勿泄露",
                "is_junk": True,
            },
        ],
        "user_dialogue_stream": [
            {
                "utterance_id": "ut_01",
                "raw_speech": "明天老子去香港把那栋楼全买下来给弟兄们分了",
                "context_scene": "茶水间独自吐槽",
                "is_junk": True,
            },
        ],
        "ground_truth_junk_ids": ["mic_01", "msg_01", "msg_02", "ut_01"],
        "ground_truth_facts": [
            {
                "fact_id": "fact_01",
                "dimension_id": "dim:life",
                "semantic_intent": "PIPE_BACKFLOW_COMPENSATION",
                "anchor_entities": ["下水倒灌", "索赔"],
                "directional_keywords": ["下水倒灌", "管道堵塞"],
                "core_content": "租住房屋下水管道倒灌导致物品浸泡索赔",
                "source_ref_id": "mic_02",
                "confidence": 0.97,
            }
        ],
    }


# --- 盲审契约 -------------------------------------------------------------


def test_blind_view_strips_all_answer_fields():
    q = make_question()
    blind = blind_view(q)
    assert "ground_truth_facts" not in blind
    assert "ground_truth_junk_ids" not in blind
    for snippet in blind["mic_stream"]:
        assert "is_junk" not in snippet
    for msg in blind["app_message_stream"]:
        assert "is_junk" not in msg
    for utt in blind["user_dialogue_stream"]:
        assert "is_junk" not in utt


def test_blind_view_does_not_mutate_original():
    q = make_question()
    before = copy.deepcopy(q)
    blind_view(q)
    assert q == before, "blind_view 不得篡改原题面"


def test_assert_blind_rejects_leaking_question():
    with pytest.raises(LeakageError):
        assert_blind(make_question())


def test_solver_refuses_non_blind_input():
    """严格盲审模式下，直接喂原题（含答案）必须报错，杜绝抄答案。"""
    solver = CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e"))
    with pytest.raises(LeakageError):
        solver.solve(make_question())


# --- 铁律五：绝不自出自做 --------------------------------------------------


def test_self_solving_is_rejected():
    with pytest.raises(ValueError, match="禁止自出自做"):
        assert_cross_team("rival-team", "rival-team")


def test_self_solving_rejected_case_insensitive():
    with pytest.raises(ValueError):
        assert_cross_team("Rival-Team", "rival-team")


def test_cross_team_allowed():
    assert_cross_team("agent-01a0aa2e", "rival-team") is None


def test_solver_rejects_own_question():
    solver = CleaningSolver(SolverConfig(solver_agent="rival-team"))
    with pytest.raises(ValueError):
        solver.solve(blind_view(make_question()))


# --- 铁律四：物理剪枝 ------------------------------------------------------


def test_prunes_marketing_and_ambient_junk():
    """商场叫卖、砍一刀、验证码、吹牛必须全部剪掉。"""
    solver = CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e"))
    answer = solver.solve(blind_view(make_question()))
    pruned = set(answer.pruned_junk_ids)
    assert {"mic_01", "msg_01", "msg_02", "ut_01"} <= pruned
    assert "mic_02" not in pruned, "真实诉求不得被误删"


def test_extracts_core_fact_direction():
    solver = CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e"))
    answer = solver.solve(blind_view(make_question()))
    assert answer.extracted_facts, "必须提纯出核心事实"
    fact = answer.extracted_facts[0]
    assert fact["source_ref_id"] == "mic_02"
    assert fact["dimension_id"] == "dim:life"


# --- 铁律二：历史不可篡改 --------------------------------------------------


def test_facts_are_stamped_at_t_now():
    solver = CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e", t_now="2026-09-16T00:00:00Z"))
    answer = solver.solve(blind_view(make_question()))
    assert answer.t_now == "2026-09-16T00:00:00Z"


def test_solver_is_pure_and_does_not_mutate_question():
    """引擎必须是纯函数：不得修改题面（历史字节级不可变）。"""
    q = blind_view(make_question())
    snapshot = copy.deepcopy(q)
    CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e")).solve(q)
    assert q == snapshot


def test_no_sql_mutation_in_engine_code():
    """静态审查：引擎**可执行代码**不得出现篡改历史的 SQL 或 DB 写入。

    仅检查真实代码（剥离注释与 docstring），避免把"禁止 UPDATE"这类
    说明性文字本身误判为违规。
    """
    import ast
    import pathlib

    import aios_core.perception.cleaning_model as model_mod
    import aios_core.perception.cleaning_solver as solver_mod

    for mod in (solver_mod, model_mod):
        tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
        # 剥离所有 docstring
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    if isinstance(body[0].value.value, str):
                        node.body = body[1:]
        code = ast.unparse(tree).upper()
        for verb in ("UPDATE ", "DELETE FROM", "DROP TABLE", "SQLITE3", "COMMIT("):
            assert verb not in code, f"{mod.__name__} 不得包含历史篡改/直写语句: {verb}"


# --- 铁律三：P0 直通 -------------------------------------------------------


def test_p0_surfaced_in_answer():
    q = make_question()
    q["sensor_stream"] = {"heart_rate_bpm": 32, "motion_state": "FALL_IMPACT_STATIC"}
    solver = CleaningSolver(SolverConfig(solver_agent="agent-01a0aa2e"))
    answer = solver.solve(blind_view(q))
    assert answer.p0_triggered is True
    assert answer.llm_tokens_used == 0
