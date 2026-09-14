# M0-010 REVIEW PACKET

日期：2026-09-14

任务：Entity + Relation（实体与关系）契约正式冻结

起始commit：cda888f371fed812cda1b5e08d8a27db5e0c240a (M0-009 FINAL PASS 234 passed Python 3.12.14 SUCCESS)

## Entity schema

```
class Entity(WorldObject):
    object_type: Literal[ENTITY]
    entity_kind: str
    canonical_name: str | None
    aliases: list[str]
    identity_claim_refs: list[ObjectRef]
    validator: identity_claim_refs each revision != None else ValueError "identity_claim_refs requires pinned ObjectRef revisions"
```

- entity_kind str, canonical_name str|None, aliases list[str], identity_claim_refs list[ObjectRef] exact
- object_type Literal ENTITY
- 不要增加name作为ID, canonical_name unique, aliases unique, identity resolver
- identity_claim_refs属于provenance，为什么认为这个实体是谁，历史身份认知必须可回放，未知Entity允许[]合法

## Relation schema

```
class Relation(WorldObject):
    object_type: Literal[RELATION]
    left: ObjectRef
    relation_type: str
    right: ObjectRef
    valid_time: TemporalExtent
    evidence_set_refs: list[ObjectRef]
    confidence: float 0..1
    validator: evidence_set_refs each revision != None else ValueError "evidence_set_refs requires pinned ObjectRef revisions"
```

- left ObjectRef, relation_type str, right ObjectRef, valid_time TemporalExtent, evidence_set_refs list[ObjectRef] exact, confidence float
- object_type Literal RELATION
- 关系必须独立对象，拥有自己object_id/revision/occurred/learned_at/valid_time/evidence/confidence，禁止Entity(relations=[...])或永久JSON列表，原因关系会随时间变化纠错
- left/right本轮不强制revision，仍遵守M0-006 pinned vs floating，稳定性来自object_id不是名字，历史fixture优先Entity@revision但不禁止floating endpoint
- relation_type允许随revision修正，object_type永远RELATION但relation_type可colleague->former_colleague，旧rev不覆盖

## stable ID

- Entity支持未知人物/物品先获得稳定object_id，以后名字/身份变清楚时修改revision但绝不能换object_id，例如未知P001后来知道是妈妈仍同一object_id
- 名字不是身份：canonical_name不是主键，aliases不是主键，字符串相同不代表同一实体，两个不同人都叫小王必须允许A.object_id != B.object_id，Core不得因名字相同自动合并
- canonical_name不是ID：object_id不是由"小王"派生，验证两个相同canonical_name不同stable object_id，修改canonical_name通过revision object_id不变

## unknown P001->妈妈

- 固定entity_id new_object_id ENTITY
- rev1: object_id=entity_id revision1 entity_kind person canonical_name None aliases [P001] identity_claim_refs [] commit
- 人工创建identity Claim subject_id=entity_id claimant user-1 claim_type FACT content "P001对应用户的妈妈" knowledge_state REPORTED confidence fixture revision1 commit
- Entity rev2: 同一object_id revision2 canonical_name "妈妈" aliases [P001,妈妈] identity_claim_refs [Claim@1] commit
- 验证rev1.object_id==rev2.object_id, rev1 canonical_name None, rev2 妈妈, rev1仍可读, identity_claim_ref revision 1

## identity Claim provenance

- identity_claim_refs表示为什么认为实体是谁，属于provenance，必须pinned Claim@1非法Claim@latest，Entity rev2不能未来静默变成由Claim rev4支持，历史身份认知可回放
- ER04 floating identity claim拒绝：ObjectRef claim_id revision None => ValidationError, revision 1合法
- ER17 durable mutation：真实Claim@1合法Entity identity [Claim@1]构造后原地append floating None确认污染，store.commit必须StoreError INVALID_ARGUMENT reason persistence_revalidation_failed world revision不增加，证明M0-010 validator受M0-009 durable boundary保护

## identity_claim_refs pinned

- ER04, ER17已述，E? exact annotation list[ObjectRef]

## 同名小王不合并

- ER05创建Entity A canonical_name 小王 Entity B canonical_name 小王 entity_kind person, 必须A.object_id != B.object_id, 一次commit两个Entity成功，查询ENTITY能看到两个独立对象，不得自动merge/选择/覆盖
- ER06 canonical_name不是ID：两个相同名字不同ID，修改canonical_name小王->王某通过revision object_id不变
- ER09同名实体关系必须按ID绑定：使用ER05两个小王或独立fixture，再创建第三个Entity用户自己，创建Relation left=user@1 right=小王B@1 relation_type colleague验证right精确等于小王B ID而不是小王A，canonical_name相同不得自动绑定错误实体

## Relation独立对象

- ER15 Relation不内嵌Entity：Entity schema/model dump不得新增relations/relation_list/embedded_relations等永久关系列表，提交Relation后再次读取Entity payload Entity内容不得因Relation commit被隐式修改
- ER10/ER11等使用独立Relation object_id

## relation left/right按object_id

- ER09已述，按object_id绑定非名字

## Relation evidence pinned

- ER08 evidence_set_refs pinned：ObjectRef evidence_id revision None => ValidationError, revision 1合法model-level
- ER18 durable mutation：真实EvidenceSet@1合法Relation evidence [EvidenceSet@1]构造后原地append floating None，commit必须StoreError INVALID_ARGUMENT reason persistence_revalidation_failed world revision不增加，不得落盘
- 属于认知provenance，旧Relation revision不能随未来EvidenceSet版本漂移

## colleague->former_colleague

- ER10准备两个真实Entity和真实Observation "与小王在同一公司工作"和EvidenceSet member [Observation@1] support [Observation@1]固定KnowledgeWindow commit EvidenceSet，创建Relation relation_id new_object_id RELATION revision1 left EntityA@1 right EntityB@1 relation_type colleague valid_time固定区间 evidence [EvidenceSet@1] confidence 0.8 commit成功记录world_revision_after_rev1
- ER11创建新Observation/EvidenceSet表达关系变化，同一relation_id revision2 relation_type former_colleague valid_time新区间 evidence [新EvidenceSet@1] confidence fixture commit成功，验证object_id不变 rev1 colleague rev2 former_colleague旧rev1仍可读取

## world revision history replay

- ER12使用ER10/11，在as_of_world_revision=world_revision_after_rev1读取relation必须colleague，当前/latest读取former_colleague，或get_payload revision1/2同时验证，证明关系历史可回放不是覆盖旧关系

## valid_time exact

- ER13设置rev1 valid_time明确start 2026-01-01 UTC end 2026-08-31 UTC SQLite round-trip后TemporalExtent.model_validate(payload["valid_time"]) as_utc严格比较start/end不漂移，rev2另一个明确范围

## confidence

- ER07验证合法Relation confidence 0.8，0.0/0.5/1.0合法，-0.01/1.01 ValidationError

## durable mutation ER17/ER18

- ER17 identity_claim_refs原地mutation后StoreError INVALID_ARGUMENT persistence_revalidation_failed world revision不增加
- ER18 relation evidence原地mutation后同理
- 证明M0-010 validator受M0-009 durable boundary保护，post-validation mutation不可持久化

## adversarial A-G

- A: 临时把canonical_name作为ID来源，ER05/ER06必须失败，恢复有效
- B: 临时模拟两个同名小王自动合并，ER05必须失败，恢复有效
- C: 允许identity_claim_refs floating，ER04必须失败，恢复有效
- D: 允许Relation evidence floating，ER08必须失败，恢复有效
- E: Relation rev2覆盖rev1，ER11/ER12必须失败，恢复有效
- F: 把Relation永久嵌入Entity JSON，ER15必须失败，恢复有效
- G: 移除durable persistence revalidation，ER17/ER18必须失败 floating provenance错误持久化，恢复有效
- 全部恢复，未提交攻击代码

## local tests

252 passed (234+18), 0 failed, 1 warning (E23 serializer warning for time_range string adversarial fixture预期)

Python 3.11.2本地，GitHub Actions Python 3.12预期同样通过

## Reference

15 passed

## CI

起始cda888f SUCCESS Python 3.12.14 234 passed

新HEAD push后CI_PENDING_CHIEF_VERIFICATION，总工直接验证真实HEAD/diff/CI/tests

## production diff

- 开始commit cda888f371fed812cda1b5e08d8a27db5e0c240a
- 预期：src/aios_core/contracts/models.py仅Entity validator和Relation validator
- 实际：仅models.py新增两个validator，符合预期
- sqlite_store.py NO CHANGE (M0-009 durable revalidation已冻结)
- 其他src NO CHANGE
- 若超出则BLOCKED

## unresolved issues

NONE，等待M0-010 CODE REVIEW，禁止M0-011
