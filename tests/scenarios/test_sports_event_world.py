"""M1-016 贯穿案例骨架：运动会 → 体育测试修正（总工程师版 §M1-016 + R4 增装）。

治理定位：Gate 前立的**终局对拍对象**。两半结构——
- A 半：今天就在 store/契约/检索核公开面上点得亮（证明骨架不是死代码）；
- B 半：`xfail(strict=True)` 的**闹铃用例**——对应 POST_GATE_48H B2/B4/B5 交付
  物落地之日，XPASS 自动翻红逼人摘标记，"服务到了但场景没接上"无处遁形。

禁止事项照抄 I 条：本文件不得出现为过场景的特判；只调用公开接口。
验收对应 G 条六项 + H 条单脚本可跑（`python tests/scenarios/test_sports_event_world.py`）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aios_core.contracts import (
    AnnotationSlot,
    Claim,
    ClaimType,
    Entity,
    KnowledgeWindow,
    EventAnchor,
    EvidenceSet,
    KnowledgeState,
    ObjectRef,
    Observation,
    OperationRequest,
    Reinterpretation,
    SourceClass,
    TemporalExtent,
)
from aios_core.query.search import WorldSearchIndex
from aios_core.storage import SQLiteWorldStore

T0 = datetime(2026, 4, 10, 8, 30, tzinfo=timezone.utc)          # 运动会日上午
T_CORRECT = T0 + timedelta(hours=6)                              # "其实是体测" 诞生时刻
U = "u1"


def _op(store: SQLiteWorldStore, name: str, key: str, source: SourceClass = SourceClass.SENSOR) -> OperationRequest:
    return OperationRequest(operation_name=name, expected_world_revision=store.current_world_revision(),
                            reason="M1-016 throughline", idempotency_key=key, source_class=source)


def _obs(oid: str, value, at: datetime = T0) -> Observation:
    return Observation(object_id=oid, subject_id=U, occurred=TemporalExtent.point(at), learned_at=at,
                       recorded_at=at, created_by="m1_016_skeleton", source_kind="sensor_stream",
                       modality="json", value=value)


def build_sports_world(db_path, *, with_correction: bool = True) -> dict:
    """固定 fixture + service 面调用；全时间戳常量 → 可回放等价。"""

    store = SQLiteWorldStore(db_path)
    trace: list[dict] = []

    def note(step: str, **kw):
        trace.append({"step": step, "world_revision": store.current_world_revision(), **kw})

    # ① 摄入五源（profile 合规：心率是窗口平均线、IMU 仅宏观事件——IngestPolicy 硬线）
    obs = [
        _obs("observation_sports_gps", {"place": "school", "dwell_min": 75}),
        _obs("observation_sports_visual", {"text": "操场集结，横幅写着校运会加油"}),
        _obs("observation_sports_cheer", {"text": "看台喊加油，广播放运动员进行曲"}),
        _obs("observation_sports_hr", {"bpm_mean": 152, "window_seconds": 300}),
        _obs("observation_sports_imu", {"macro": "sprint_burst", "count": 2}),
    ]
    store.commit(obs, _op(store, "ingest.multi_source", "sp-obs"))
    note("ingest", object_ids=[o.object_id for o in obs])

    # ② 实体（"实体不变"的基准线）+ 用户自述 Claim
    entities = [
        Entity(object_id="entity_sports_user", subject_id=U, learned_at=T0, recorded_at=T0,
               created_by="m1_016_skeleton", entity_kind="person", canonical_name="我", aliases=["用户"]),
        Entity(object_id="entity_sports_class", subject_id=U, learned_at=T0, recorded_at=T0,
               created_by="m1_016_skeleton", entity_kind="group", canonical_name="三年级二班"),
    ]
    claim_first = Claim(object_id="claim_sports_first", subject_id=U, learned_at=T0, recorded_at=T0,
                        created_by="m1_016_skeleton", claimant_id=U, claim_type=ClaimType.DESIRE,
                        content="我在运动会跑步拿了第一名", asserted_at=T0,
                        knowledge_state=KnowledgeState.REPORTED, confidence=0.95)
    store.commit([*entities, claim_first], _op(store, "entity.claim.upsert", "sp-ent", SourceClass.USER))
    note("entities+claim", object_ids=["entity_sports_user", "entity_sports_class", "claim_sports_first"])

    # ③ EvidenceSet 冻结 + CANDIDATE 事件（只持引用——"Event 不复制数据"）
    evidence = EvidenceSet(object_id="evidence_sports_meeting", subject_id=U, learned_at=T0, recorded_at=T0,
                           created_by="m1_016_skeleton", purpose="运动会候选的证据链",
                           knowledge_window=KnowledgeWindow(knowledge_cutoff=T0, world_revision=1),
                           selection_method="manual_pin_by_ingest_service",
                           member_refs=[ObjectRef(object_id=o.object_id, revision=1) for o in obs])
    event = EventAnchor(object_id="event_sports_meeting", subject_id=U, learned_at=T0, recorded_at=T0,
                        created_by="m1_016_skeleton", title="操场运动会候选：横幅、加油与冲刺",
                        interpretation="校运会进行中，用户参加了跑步",
                        event_time=TemporalExtent.point(T0),
                        participant_refs=[ObjectRef(object_id="entity_sports_user", revision=1),
                                          ObjectRef(object_id="entity_sports_class", revision=1)],
                        primary_claim_refs=[ObjectRef(object_id="claim_sports_first", revision=1)],
                        evidence_set_refs=[ObjectRef(object_id="evidence_sports_meeting", revision=1)],
                        confidence=0.7)
    store.commit([evidence, event], _op(store, "event.candidate.open", "sp-ev", SourceClass.AI_COGNITION))
    note("evidence+event", object_ids=["evidence_sports_meeting", "event_sports_meeting"])

    if with_correction:
        # ④ 修正 = append-only 两件套：Reinterpretation 指认历史 + 用户更正断言；
        #    事件对象本体零改写（R4-01 形态）。
        reinterp = Reinterpretation(object_id="reinterpretation_sports_pe_test", subject_id=U,
                                    learned_at=T_CORRECT, recorded_at=T_CORRECT, created_by="m1_016_skeleton",
                                    target_ref=ObjectRef(object_id="event_sports_meeting", revision=1),
                                    slot=AnnotationSlot.MEANING,
                                    statement="其实是校内体育测试，不是校运会正赛", confidence=0.9)
        claim_fix = Claim(object_id="claim_sports_correction", subject_id=U, learned_at=T_CORRECT,
                          recorded_at=T_CORRECT, created_by="m1_016_skeleton", claimant_id=U,
                          claim_type=ClaimType.FACT, content="那是体育测试的 50 米项目", asserted_at=T_CORRECT,
                          knowledge_state=KnowledgeState.OBSERVED, confidence=0.9)  # 用户亲述更正
        store.commit([reinterp, claim_fix], _op(store, "reinterpretation.attach", "sp-rp", SourceClass.USER))
        note("correction", object_ids=["reinterpretation_sports_pe_test", "claim_sports_correction"])
    return {"store": store, "trace": trace}


# ------------------------------------------------------------------ A 半（今日即绿）


class TestPartA:
    def test_event_copies_no_data_and_evidence_complete(self, tmp_path):
        r = build_sports_world(tmp_path / "w.db", with_correction=False)
        store = r["store"]
        ev = store.get_payload("event_sports_meeting")
        assert "value" not in json.dumps(ev, ensure_ascii=False)  # 不内嵌观测载荷
        eset = store.get_payload("evidence_sports_meeting", revision=1)
        members = {m["object_id"] for m in eset["member_refs"]}
        assert members == {"observation_sports_gps", "observation_sports_visual", "observation_sports_cheer",
                           "observation_sports_hr", "observation_sports_imu"}
        for oid in members:  # EvidenceSet 完整 = 成员逐一可解且在场
            assert store.get_payload(oid, revision=1)["subject_id"] == U

    def test_old_cognition_replayable_via_store_cutoff_read(self, tmp_path):
        r = build_sports_world(tmp_path / "w.db")
        store = r["store"]
        before = store.get_payload("event_sports_meeting", as_of_world_revision=3)
        assert "体育测试" not in json.dumps(before, ensure_ascii=False)
        after = store.get_payload("event_sports_meeting", as_of_world_revision=4)
        assert after["title"] == before["title"]  # 历史零改写：两时点读事件本体完全一致

    def test_correction_never_rewrites_history(self, tmp_path):
        r = build_sports_world(tmp_path / "w.db")
        store = r["store"]
        # 事件本体：修正之后最新 revision 仍是 1（append-only 两件套不改它）
        assert store.get_payload("event_sports_meeting")["revision"] == 1
        # 实体不变：两个实体最新 revision 均为 1，命名未动
        for ent, name in (("entity_sports_user", "我"), ("entity_sports_class", "三年级二班")):
            payload = store.get_payload(ent)
            assert payload["revision"] == 1 and payload["canonical_name"] == name
        assert "体育测试" in store.get_payload("reinterpretation_sports_pe_test")["statement"]

    def test_keyword_recall_and_trigger_visibility(self, tmp_path):
        db = tmp_path / "w.db"
        r = build_sports_world(db)
        store = r["store"]
        idx = WorldSearchIndex(db, store=store)
        idx.rebuild()
        page = idx.co_search(["操场", "加油"])
        hit_ids = {h.object_id for h in page.hits}
        assert {"event_sports_meeting", "observation_sports_visual"} & hit_ids
        # 触发面：本场景四笔提交全可触发、无一 maintenance
        assert len(store.triggerable_commits_after(0)) == store.current_world_revision()

    def test_trace_is_replayable_json_bit_identical(self, tmp_path):
        a = build_sports_world(tmp_path / "a.db")
        b = build_sports_world(tmp_path / "b.db")
        ja = json.dumps(a["trace"], ensure_ascii=False, sort_keys=True)
        jb = json.dumps(b["trace"], ensure_ascii=False, sort_keys=True)
        assert ja == jb and json.loads(ja)[0]["step"] == "ingest"  # H 条：可回放 JSON

    def test_third_party_fact_promotion_rejected_by_contract(self, tmp_path):
        # R4-09.1 在本案例的在场证明：同学转述"老师说要补测"不得升 FACT
        now = T0 + timedelta(days=1)
        with pytest.raises(ValidationError, match="FACT"):
            Claim(object_id="claim_sports_rumor", subject_id=U, learned_at=now, recorded_at=now,
                  created_by="m1_016_skeleton", claimant_id="peer_x", claim_type=ClaimType.FACT,
                  content="同学转述：老师说明天补测", asserted_at=now,
                  knowledge_state=KnowledgeState.REPORTED, confidence=0.8,
                  corroboration_required=True)


# ------------------------------------------------------------------ B 半（strict-xfail 闹铃）

GATE = "POST_GATE_48H 出口判据落地后摘除本标记（XPASS 翻红即到期）"


class TestPartB:
    @pytest.mark.xfail(strict=True, reason=f"world_at(view=AS_KNOWN|ANNOTATED) 双透镜读面未接线：{GATE}")
    def test_dual_lens_fork_on_correction(self, tmp_path):
        r = build_sports_world(tmp_path / "w.db")
        from aios_core.world import view_at  # Gate B2 交付
        known = view_at(r["store"], at=T0, view="AS_KNOWN")
        annotated = view_at(r["store"], at=T0, view="ANNOTATED")
        assert "体育测试" not in json.dumps(known["event_sports_meeting"], ensure_ascii=False)
        assert "体育测试" in json.dumps(annotated["event_sports_meeting"], ensure_ascii=False)
        with pytest.raises(ValueError, match="cutoff"):
            view_at(r["store"], at=T0 + timedelta(days=1), view="AS_KNOWN", pin_revision=0)

    @pytest.mark.xfail(strict=True, reason=f"检索核视图感知（M1-012 服务层）未接线：{GATE}")
    def test_search_annotated_sees_pe_test_known_does_not(self, tmp_path):
        db = tmp_path / "w.db"
        r = build_sports_world(db)
        idx = WorldSearchIndex(db, store=r["store"])
        idx.rebuild()
        now = idx.co_search(["体育测试"], view="ANNOTATED")
        back = idx.co_search(["体育测试"], view="AS_KNOWN", as_of=T0)
        assert now.hits and not back.hits

    @pytest.mark.xfail(strict=True, reason=f"HotCard 管道（M1-020/020a-d）未实现：{GATE}")
    def test_hot_card_regenerates_after_correction_old_pointers_hold(self, tmp_path):
        db = tmp_path / "w.db"
        r = build_sports_world(db)
        from aios_core.query.hot_cards import fetch_hot_cards, build_cards  # Gate B4 交付
        old = fetch_hot_cards(r["store"], U, ["entity_sports_user"], day=T0)
        build_cards(r["store"], day=T_CORRECT)
        new = fetch_hot_cards(r["store"], U, ["entity_sports_user"], day=T_CORRECT)
        assert "体育测试" in json.dumps(new, ensure_ascii=False)
        assert old["digest"]["recent_event"]["object_id"] == "event_sports_meeting"  # 旧卡 pin 仍可解析

    @pytest.mark.xfail(strict=True, reason=f"world.prune 提交口（M1-019/019b）未实现：{GATE}")
    def test_pruned_cheer_audio_still_pinned_resolvable(self, tmp_path):
        db = tmp_path / "w.db"
        r = build_sports_world(db)
        store = r["store"]
        store.prune(object_id="observation_sports_cheer", authz_ref="ticket_user_042",
                    reason="raw_tier 超龄 + 零引用（除冻结证据集外）")  # Gate B4 交付
        assert store.get_payload("observation_sports_cheer", revision=1)  # pin 永远可解析
        assert store.is_latest_pruned("observation_sports_cheer") is True
        idx = WorldSearchIndex(db, store=store)
        idx.rebuild()
        assert not idx.co_search(["加油"], include_tombstones=False).hits
        assert store.current_world_revision() == 5 and len(store.triggerable_commits_after(0)) == 4  # prune 笔对触发面不可见
