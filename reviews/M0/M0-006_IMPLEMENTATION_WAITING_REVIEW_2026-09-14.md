# M0-006 实现记录

状态：

WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性冻结

起始commit：

e15a0f9d5f180f953a1d26fb7898be54a34a2a70 (M0-005 FINAL PASS)
f04bd68 (M0-005 archive final pass and authorize M0-006)

## 已通过部分 (M0-005 FINAL PASS)

- WorldObject 11字段, revision严格+1, object_type immutable, append-only, World vs Object Revision分离, 163 passed, Python 3.12 CI PASS, e15a0f9

## M0-006 正式冻结

- ObjectRef: BaseModel extra forbid frozen, object_id非空, revision int|None ge1, None合法 floating, 0/-1拒绝, extra拒绝, frozen (R01,R02)
- SourceRef: 同ObjectRef + source_locator, frozen, extra forbid (R03)
- revision=N: PINNED, 永远指向第N版, 目标后来N+1/N+2不得改变历史
- revision=None: FLOATING, 追随可见最新版本，用于导航，不是冻结历史证据
- 证据/历史认知/Dependency等需可回放引用优先明确revision，Entity等跟随当前身份可revision=None，M0-006不提前修改Claim/EvidenceSet/Event/Dependency业务字段强制pin
- SourceRef同样遵守版本语义，source_locator保留，不得当revision替代品
- Generic knowledge visibility: 正在写入对象的learned_at是通用知识边界，不得引用learned_at晚于自身的目标revision，否则未来信息泄露
- 与KnowledgeWindow关系: WorldObject.learned_at通用上限，未来EvidenceSet可能有更早cutoff，业务对象可进一步收紧，M0-006不硬编码isinstance(EvidenceSet)，不让storage依赖业务模型，通用storage invariant: target learned_at <= referencing.learned_at
- Missing与Future-hidden统一NOT_FOUND, context至少referenced_object_id, referenced_revision, 允许reason=reference_not_visible_or_missing, 禁止泄露未来target learned_at/payload/revision内容

## 实现

- refs.py: 已符合冻结设计，NO CHANGE
- sqlite_store.py:
  - import as_utc
  - 新增 _reference_exists签名: (conn, ref, pending_pairs, pending_objects, *, knowledge_cutoff) -> bool, cutoff_canonical = canonical_utc_iso(knowledge_cutoff)
  - Explicit revision: pending中检查 as_utc(pending_target.learned_at) <= as_utc(cutoff), DB中 SELECT WHERE object_id=? AND revision=? AND learned_at<=? LIMIT 1
  - Floating: pending中任意同object_id且learned_at<=cutoff即合法，DB中 SELECT WHERE object_id=? AND learned_at<=? LIMIT 1
  - 时间比较: pending用as_utc, DB用canonical_utc_iso, 保持M0-004规则
  - 同事务互相合法引用继续支持，只要revision合法、object_type合法、learned_at互相可见、不是自引用当前revision，则commit成功
  - 同事务未来引用必须拒绝: A 10:00引用B@1 B 11:00 => 非法整个事务拒绝
  - 不扩大循环检测，保留self-current-revision禁止，任意深度环检测属于后续M0-019/M1/M3
  - pending结构: pending_pairs保留, 新增pending_objects dict[(object_id, revision)]->WorldObject

## 新增测试

- tests/unit/test_refs.py 16 tests:
  R01 ObjectRef结构, R02 frozen, R03 SourceRef结构frozen, R04 nonexistent object, R05 nonexistent exact revision不fallback, R06 pinned历史不漂移old/new, R07 floating navigation, R08同事务互相引用A<->B, R09 future explicit拒绝, R10 visible historical成功, R11 floating有旧可见版本, R12 floating只有未来版本, R13 pending future拒绝, R14 SourceRef版本验证, R15 SourceRef future visibility, critical model ref字段检查

## 检查

- 关键模型ref字段: Claim support/counter, EventAnchor primary_claim/evidence_set, EvidenceSet member/support/counter/context, Dependency dependent/dependency 继续使用ObjectRef，检查通过，无M0_006_CRITICAL_REF_FIELD_DIVERGED

## 测试

- 正式 179 passed (163+16), 0 failed
- Reference 15 passed
- 对抗 A-F 有效

## 证据

- reviews/M0/M0-005_final_PASS_2026-09-14.md
- reviews/M0/evidence/M0_006_REVIEW_PACKET.md
- reviews/M0/evidence/M0_006_TEST_OUTPUT.txt
- tests/unit/test_refs.py

## 下一步

等待总工程师 M0-006 CODE REVIEW，签发 FINAL PASS 后才允许进入 M0-007。
