# M0-010 实现记录

状态：WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：Entity + Relation（实体与关系）契约正式冻结

起始commit：cda888f371fed812cda1b5e08d8a27db5e0c240a (M0-009 FINAL PASS 234 passed)

## 生产修改

src/aios_core/contracts/models.py仅允许Entity Relation最小validator：

- Entity validator：identity_claim_refs全部pinned，for ref in identity_claim_refs if ref.revision is None => ValueError "identity_claim_refs requires pinned ObjectRef revisions"，不要求min_length 1，未知Entity允许[]
- Relation validator：evidence_set_refs全部pinned，for ref in evidence_set_refs if revision None => ValueError "evidence_set_refs requires pinned ObjectRef revisions"，不要求非空，M1业务service以后控制
- 不修改Observation, Claim, EvidenceSet, Dimension*, Event*, Goal*, Task*, Wake*
- 不修改sqlite_store.py (M0-009 durable revalidation已冻结)
- 不修改refs.py, base.py, time.py, enums.py, ids.py
- 实际diff仅models.py两个validator，符合预期

## 测试文件 tests/unit/test_entity_relation.py 18 tests ER01-ER18

- ER01 exact schema：Entity entity_kind str, canonical_name str|None, aliases list[str], identity_claim_refs list[ObjectRef], object_type Literal ENTITY, Relation left ObjectRef, relation_type str, right ObjectRef, valid_time TemporalExtent, evidence_set_refs list[ObjectRef], confidence float, object_type Literal RELATION
- ER02 unknown entity合法：entity_kind person canonical_name None aliases [P001] identity [] SQLite commit成功，证明不知道名字也能先存在稳定ID
- ER03 unknown P001->妈妈：固定entity_id rev1 None P001 [] commit, identity Claim subject entity_id content P001对应妈妈 REPORTED commit, Entity rev2 same object_id canonical 妈妈 aliases P001妈妈 identity [Claim@1] commit, 验证object_id相同 rev1 None rev2 妈妈 history可读
- ER04 floating identity claim拒绝：revision None ValidationError, revision 1合法
- ER05同名小王不合并：Entity A 小王 Entity B 小王 object_id不同 一次commit两个成功 查询ENTITY 2个独立 不得自动merge
- ER06 canonical_name不是ID：相同名字不同ID，修改canonical_name通过revision object_id不变
- ER07 Relation schema/confidence：left EntityA@1 right EntityB@1 relation_type colleague valid_time明确 confidence 0.8合法，0.0/0.5/1.0合法 -0.01/1.01非法
- ER08 evidence_set_refs pinned：revision None ValidationError, revision 1合法
- ER09同名实体关系按ID绑定：user@1 right 小王B@1 colleague验证right精确等于小王B ID而非小王A
- ER10 colleague rev1：Entity A B Observation "与小王在同一公司工作" EvidenceSet member/support [Observation@1] KnowledgeWindow commit，Relation relation_id new rev1 left A@1 right B@1 colleague valid_time固定 evidence [EvidenceSet@1] confidence 0.8 commit成功记录world_revision_after_rev1
- ER11 colleague->former_colleague：新Observation/EvidenceSet，同一relation_id rev2 former_colleague新valid_time新EvidenceSet confidence fixture commit成功，验证object_id不变 rev1 colleague rev2 former_colleague旧可读
- ER12 historical world revision replay：as_of_world_revision world_after_rev1读取colleague，latest former_colleague，get_payload rev1/2同时验证
- ER13 valid_time exact round-trip：rev1 2026-01-01->08-31 as_utc严格比较不漂移，rev2另一个范围
- ER14 Entity历史revision可回放：unknown->妈妈 get_payload rev1 None P001 rev2 妈妈
- ER15 Relation不内嵌Entity：Entity schema无relations等，提交Relation后Entity payload不被隐式修改
- ER16 object_type固定：Entity object_type RELATION ValidationError, Relation object_type ENTITY ValidationError
- ER17 identity_claim post-validation mutation：真实Claim@1合法Entity identity [Claim@1]构造后append floating None，commit StoreError INVALID_ARGUMENT persistence_revalidation_failed world revision不增加，证明M0-010 validator受M0-009 durable boundary保护
- ER18 relation evidence post-validation mutation：真实EvidenceSet@1合法Relation evidence [EvidenceSet@1]构造后append floating None commit INVALID_ARGUMENT

## 保护

- 不做自动身份解析：无字符串相似度merge, embedding, LLM等，M0-010只冻结数据契约
- 不做Relation service：无world/entity.py RelationService等
- 不增加DB专用表：继续SQLiteWorldStore object_revisions统一时间轴
- 不做字符串搜索自动合并

## 对抗

A canonical_name作为ID ER05/06 FAIL, B 同名自动合并 ER05 FAIL, C identity floating ER04 FAIL, D evidence floating ER08 FAIL, E rev2覆盖rev1 ER11/12 FAIL, F Relation嵌入Entity ER15 FAIL, G 移除revalidation ER17/18 FAIL，恢复有效

## 测试

252 passed (234+18), 0 failed, 1 warning (E23 serializer warning预期), Reference 15 passed, Production diff仅models.py符合预期

## 证据

- src/aios_core/contracts/models.py Entity/Relation validator
- tests/unit/test_entity_relation.py 18 tests
- reviews/M0/M0-009_final_PASS_2026-09-14.md
- reviews/M0/evidence/M0_010_REVIEW_PACKET.md
- reviews/M0/evidence/M0_010_TEST_OUTPUT.txt 252+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-010 CODE REVIEW，禁止M0-011
