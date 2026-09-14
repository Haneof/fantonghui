# M0-006 审查证据包

## 起始commit
e15a0f9d5f180f953a1d26fb7898be54a34a2a70 (M0-005 FINAL PASS)
f04bd68 (M0-005 archive final pass and authorize M0-006)

## ObjectRef frozen contract
- BaseModel, extra="forbid", frozen=True
- object_id: 非空str min_length=1
- revision: int | None ge=1, None合法 (floating), 0/-1拒绝
- extra field拒绝, 赋值修改拒绝 (R01,R02)
- SourceRef同样: object_id, revision, source_locator, frozen, extra forbid (R03)

## SourceRef frozen contract
- 同ObjectRef + source_locator: str | None
- revision None/1合法, 0拒绝, extra拒绝, frozen

## pinned vs floating语义
- revision=N: PINNED / VERSION-PINNED REF, 永远指向该object_id第N版，目标后来产生N+1,N+2不得改变历史指向
- revision=None: FLOATING / LATEST-NAVIGATION REF, 追随可见最新版本，用于实体导航、当前状态导航、明确follow-latest接口，不是冻结历史证据
- R06: target rev1 old, holder保存 ref revision=1, 目标升级rev2 new后，holder ref仍1，解析仍得old，不漂移，M0-006最重要
- R07: floating ref revision=None，目标只有rev1时导航得rev1，目标增加rev2后同一floating ref仍None，按latest读取得rev2，证明pinned vs floating两种不同语义

## generic learned_at knowledge boundary
- 总工裁决: 正在写入的WorldObject的learned_at是通用知识边界，不得引用learned_at晚于自身的目标revision，否则09:00认知使用10:00才知道的信息，未来信息泄露
- 与KnowledgeWindow关系: WorldObject.learned_at是通用上限，未来EvidenceSet可能有更早knowledge_cutoff，业务对象可进一步收紧，M0-006不硬编码isinstance(EvidenceSet)，不让storage依赖业务模型，通用storage invariant: target learned_at <= referencing_object.learned_at
- 实现: _reference_exists(conn, ref, pending_pairs, pending_objects, *, knowledge_cutoff=obj.learned_at)
  - knowledge_cutoff由当前验证的obj.learned_at传入，不新增OperationRequest字段，不新增commit公共cutoff参数
  - pending结构: pending_pairs set[(object_id, revision)]保留，新增pending_objects dict[(object_id, revision)]->WorldObject用于检查pending learned_at
  - Explicit revision: 若在pending，需pending_target.learned_at <= referencing.learned_at (as_utc比较)，否则DB查询 object_id=X revision=N learned_at<=cutoff (canonical_utc_iso)
  - Floating revision=None: 存在性验证只要求cutoff以前至少一个可见revision，DB中 rev1 10:00 rev2 14:00 referencing 12:00 => 合法因为rev1可见，不因最新rev2是14:00拒绝，pending同样检查
  - 时间比较: pending对象使用as_utc，避免DST fold复发，DB TEXT cutoff继续canonical_utc_iso保持M0-004规则
  - Missing与Future-hidden统一NOT_FOUND，不返回不同错误暴露未来存在，context至少 referenced_object_id, referenced_revision, 允许reason=reference_not_visible_or_missing，禁止把未来target learned_at/payload/revision内容写进context

## 同事务互相引用
- R08: RefNode A rev1 learned_at T refs [B@1], B rev1 learned_at T refs [A@1], 同一commit [A,B]必须成功，World Revision只+1，继续支持任务书要求同事务合法互引，不因DB提交前不存在拒绝pending
- R13: 同事务 A learned 10:00 引用 B@1 B learned 11:00 => 非法，整个transaction拒绝，A、B都不得写入，world revision不得增加
- R16? Actually R08 already, R13 is pending future rejection
- 自引用禁止: object cannot cite its own current revision 已有逻辑保留

## 不扩大循环检测
- 当前self-current-revision已有禁止逻辑保留
- 本轮不开发任意深度环检测、Dependency graph cycle、Claim证明自身、SCC算法，属于后续M0-019/M1/M3
- 同事务合法互引不能被误当成全部禁止cycle

## R01-R15
- R01: object_id=""拒绝, revision 0/-1拒绝, None/1合法, extra拒绝
- R02: frozen赋值拒绝
- R03: SourceRef结构与frozen
- R04: nonexistent object missing_obj revision None => NOT_FOUND world不增加
- R05: nonexistent exact revision target rev1存在引用rev2 => NOT_FOUND不fallback
- R06: pinned historical ref不漂移 old/new测试
- R07: floating navigation语义
- R08: 同事务互相引用 A->B B->A 成功
- R09: future explicit ref拒绝 target 11:00 holder 10:00 ref target@1 => NOT_FOUND world不增加，错误不泄露target learned_at
- R10: visible historical explicit ref成功 target 09:00 holder 10:00 ref target@1 成功
- R11: floating ref有旧可见版本 target rev1 09:00 rev2 11:00 holder 10:00 floating => 允许
- R12: floating ref只有未来版本 target rev1 11:00 holder 10:00 floating => NOT_FOUND
- R13: pending future ref拒绝 A 10:00引用B@1 B 11:00 同事务 => 整个拒绝 world不增加
- R14: SourceRef版本验证 target rev1存在可见成功，rev2不存在NOT_FOUND，确保SourceRef不是只存字符串绕过验证
- R15: SourceRef future visibility target 11:00 holder 10:00 source_refs => NOT_FOUND
- Critical model ref field check: Claim support/counter, EventAnchor primary_claim/evidence_set, EvidenceSet member/support/counter/context, Dependency dependent/dependency 字段继续使用ObjectRef，否则STOP M0_006_CRITICAL_REF_FIELD_DIVERGED (检查通过)

## 不提前实现业务对象pin强制
- 本轮不规定 Claim所有ref必须revision非None, EvidenceSet member必须非None等，各对象更严格规则在后续M0-008/M0-009/M0-012等冻结

## 生产文件允许范围
- 允许: refs.py, sqlite_store.py, test_refs.py, reviews, TASK_PROGRESS
- refs.py: 当前语义已完全符合，NO CHANGE
- 禁止修改: base.py, models.py, time.py, ids.py, enums.py, operations.py, SQLite schema，如发现必须改则STOP (本轮仅修改sqlite_store.py)

## M0-005冻结保护
- 保留 revision严格+1, object_type immutable, subject_id NOT FROZEN, append-only, transaction atomicity, World Revision一次commit只+1, 本轮未破坏

## M0-004冻结保护
- 保留 aware datetime, canonical UTC, DST instant comparison, knowledge visibility由learned_at决定, 禁止按recorded_at判断引用可见性 (本轮使用learned_at)

## 对抗验证
- A 让不存在exact revision自动fallback latest => R05失败 (应NOT_FOUND但返回rev1)
- B 让pinned ref在目标rev2后改读latest => R06失败 (old变new)
- C 去掉pending refs支持 => R08失败 (同事务互引应成功)
- D 忽略knowledge visibility只查物理存在 => R09/R12/R13/R15失败 (未来泄露)
- E floating ref错误要求最新revision也必须<=cutoff => R11失败 (应允许但拒绝)
- F SourceRef不走引用验证 => R14/R15失败
- 恢复正式代码后全量测试 PASS

## 正式pytest
- 本地 Python 3.11.2, 179 passed (163 +16 M0-006)
- Reference 15 passed

## CI状态
- arena/* push自动触发Python 3.12 CI, 总工直接GitHub核验真实HEAD、diff、CI、tests
- 本地记录 CI_PENDING_CHIEF_VERIFICATION

## 未解决问题
NONE
- 关键模型ref字段检查通过，无M0_006_CRITICAL_REF_FIELD_DIVERGED
- 无剩余时间排序问题 (R2已修复)

---

## R1 PATCH 2026-09-14 强化版本化引用冻结测试 (TEST ONLY)

### 生产代码
NO CHANGE / PASS/FROZEN
- refs.py, sqlite_store.py 已通过审查，GitHub Actions SUCCESS Python 3.12 179 passed
- 本轮禁止修改生产代码，git diff ac83582..HEAD -- src/ 无输出

### 阻塞A: critical model ref field test仅检查字段名
- 原 test_critical_model_ref_fields 仅检查 "field" in Model.model_fields
- 若未来字段被改成 str / list[str] / dict / Any，测试仍通过，无法证明类型冻结
- 修复: 使用 get_type_hints, get_origin, get_args
  - assert_list_of_object_ref: annotation origin is list and args == (ObjectRef,)
  - assert_object_ref: annotation == ObjectRef or ObjectRef in Union args
  - 验证 Claim.support_evidence_set_refs, Claim.counter_evidence_set_refs, EventAnchor.primary_claim_refs, EventAnchor.evidence_set_refs, EvidenceSet.member_refs/support_refs/counter_refs/context_refs 全部 list[ObjectRef]
  - 验证 Dependency.dependent_ref, Dependency.dependency_ref 必须 ObjectRef
- 目标: 若字段改为 list[str] / str / dict / Any，测试必须失败，禁止修改models.py迎合测试

### 阻塞B: R09 future leakage断言OR逃逸
- 原: assert "future" not in ctx_str.lower() or "reference_not_visible" in ctx_str 可能在泄露future payload时仍false-green
- 修复: 删除OR逻辑，使用明确canary FUTURE_SECRET_8848
  - target value = FUTURE_SECRET_8848
  - 发生NOT_FOUND后验证 code==NOT_FOUND, context referenced_object_id==target_id, referenced_revision==1, reason==reference_not_visible_or_missing
  - serialized_error = str(err) + json.dumps(context)
  - 必须: FUTURE_SECRET_8848 not in serialized_error, "11:00" not in, "learned_at" not in, "payload" not in
  - 允许 referenced_revision 因为这是引用者自己请求的revision，不是未来泄露
  - 不使用 A or B 形式让泄露绕过

### 阻塞C: pending visibility DST fold integration test缺失
- pending reference visibility新增了datetime排序路径，但无DST fold integration test
- 新增 R16 pending DST false-accept防护:
  - ny = ZoneInfo("America/New_York")
  - referencing A learned 01:45 fold=0 = 05:45 UTC
  - pending target B learned 01:30 fold=1 = 06:30 UTC
  - 墙钟 01:30 <= 01:45 看起来B可见，但真实instant 06:30 > 05:45 B属于未来，必须 NOT_FOUND，同一commit [A,B] rollback，world仍0，A/B不存在，显式验证 as_utc(B) > as_utc(A)
- 新增 R17 pending DST false-reject防护:
  - target B 01:30 fold=0 = 05:30 UTC
  - referencing A 01:15 fold=1 = 06:15 UTC
  - 墙钟 01:30 > 01:15 错误直接比较会认为未来，但真实 05:30 < 06:15 B已可见，A引用B@1同一commit必须成功，验证 as_utc(B) < as_utc(A)，world_revision==1，A、B均可读

### 对抗验证 R1
- A 把critical field test中ObjectRef类型断言删掉，模拟字段改为list[str]的检查逻辑，强化后若字段改为list[str]测试失败，证明类型冻结有效
- B 在错误context中临时加入 "payload": "FUTURE_SECRET_8848"，R09严格canary检查必须失败
- C 把生产逻辑改成 pending_target.learned_at <= knowledge_cutoff (直接比较)，R16和R17至少失败，证明as_utc必要
- 禁止提交攻击代码，生产代码本轮不得正式修改

### 正式测试 R1
- 基线 179 passed
- 本轮修改已有critical/R09测试 + 新增R16/R17
- 实际 181 passed (179+2)
- Reference 15 passed
- Python 3.11.2本地，GitHub Actions Python 3.12预期同样181 passed

### 生产代码不变证明
- 开始前 git diff ac83582..HEAD -- refs.py sqlite_store.py 无diff
- 完成后 git diff ac83582..HEAD -- refs.py sqlite_store.py base.py models.py time.py ids.py enums.py operations.py 必须 NO CHANGE
- 实际: NO CHANGE，符合TEST ONLY要求

### CI状态
- 起始HEAD ac83582 GitHub Actions SUCCESS Python 3.12 179 passed
- R1新HEAD push后自动触发CI，施工方若看不到结果写 CI_PENDING_CHIEF_VERIFICATION，总工直接GitHub核验

---

## R2 PATCH 2026-09-14 严格冻结 Dependency ObjectRef 非Optional契约 (TEST ONLY)

### 生产代码
NO CHANGE / PASS/FROZEN
- 7c0355f HEAD生产代码已通过审查，GitHub Actions SUCCESS Python 3.12 181 passed
- R09 PASS, R16/R17 DST PASS
- 唯一剩余漏洞是Dependency exact annotation测试允许Optional，本轮TEST ONLY

### 修复 Dependency exact type test
- 原 assert_object_ref helper允许 Optional[ObjectRef] (检查 ObjectRef in Union args)
- 删除宽松逻辑，改为严格:
```
def assert_exact_object_ref(model, field_name):
    hints = get_type_hints(model)
    assert field_name in hints
    annotation = hints[field_name]
    assert annotation is ObjectRef, f"{model.__name__}.{field_name} must be exactly ObjectRef, got {annotation}"
```
- 验证 Dependency.dependent_ref: ObjectRef, Dependency.dependency_ref: ObjectRef
- 不能是 ObjectRef|None, Optional, list[ObjectRef], str, Any
- 正式冻结: Dependency.dependent_ref: ObjectRef, dependency_ref: ObjectRef

### list[ObjectRef]测试保持原样
- Claim.support_evidence_set_refs, counter_evidence_set_refs
- EventAnchor.primary_claim_refs, evidence_set_refs
- EvidenceSet.member_refs/support_refs/counter_refs/context_refs
- 它们继续必须 list[ObjectRef]，不得放宽

### 对抗验证 R2
- 临时将生产 models.py Dependency.dependent_ref: ObjectRef 改成 ObjectRef|None，仅本地攻击，运行critical ref test必须FAIL，然后完全恢复
- 再临时将 dependency_ref改成Optional，测试也必须FAIL，恢复
- 实际验证: 当前 dependent_ref annotation is ObjectRef True, 模拟Optional is ObjectRef False -> FAIL，攻击有效
- 不得提交攻击代码

### 正式测试 R2
- 181 passed (数量保持，因只是修正已有测试逻辑)
- Reference 15 passed
- Python 3.11.2本地，GitHub Actions Python 3.12预期181

### Production NO CHANGE证明
- git diff 7c0355f1148e715e86b3be7a1d37558d26b1f218..HEAD -- src/aios_core => NO CHANGE
- 实际执行无输出，符合TEST ONLY要求

### CI状态
- 起始HEAD 7c0355f GitHub Actions SUCCESS Python 3.12.14 181 passed
- R2新HEAD push后自动触发CI，施工方若看不到写 CI_PENDING_CHIEF_VERIFICATION
