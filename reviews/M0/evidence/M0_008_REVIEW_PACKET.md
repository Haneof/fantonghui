# M0-008 REVIEW PACKET

日期：2026-09-14

任务：Claim（主张）语义模型正式冻结

起始commit：9bee623850ce39701ec624a7b45fa1dba349cbca (M0-007 FINAL PASS 194 passed Python 3.12.14 SUCCESS)

## 当前Claim schema

src/aios_core/contracts/models.py:

```
class Claim(WorldObject):
    object_type: Literal[ObjectType.CLAIM] = ObjectType.CLAIM
    claimant_id: str
    claim_type: ClaimType
    content: str
    valid_time: TemporalExtent
    asserted_at: datetime
    knowledge_state: KnowledgeState
    confidence: float ge=0 le=1
    support_evidence_set_refs: list[ObjectRef] = []
    counter_evidence_set_refs: list[ObjectRef] = []
    unknown_items: list[str] = []
```

加上WorldObject公共字段：subject_id, source_refs, revision, occurred, learned_at, recorded_at, status, metadata等

为什么NO CHANGE：当前生产已完全符合任务书，ClaimType包含11 required，KnowledgeState独立，confidence bounds，asserted_at aware，valid_time TemporalExtent，source_refs pin，unknown_items等，无需修改

## ClaimType required set

ClaimType至少包含：FACT, OPINION, BELIEF, DESIRE, INTENTION, PLAN, PREDICTION, PROMISE, PREFERENCE, INFERENCE, HYPOTHESIS = 11个

测试C02验证required subset of set(ClaimType)，不是完全相等，未来可增加新类型

当前实际：FACT, OPINION, BELIEF, DESIRE, INTENTION, PLAN, PREDICTION, PROMISE, PREFERENCE, INFERENCE, HYPOTHESIS 全部存在，PASS

## claim_type vs knowledge_state

必须独立，禁止删除knowledge_state或用claim_type同时表达“是什么类型”和“系统以什么状态看它”

例如：FACT + REPORTED合法，含义是“事实性命题但目前只知道有人这样报告”，不等于confirmed fact

C08验证组合：FACT+REPORTED, BELIEF+REPORTED, PREDICTION+REPORTED, INFERENCE+INFERRED, HYPOTHESIS+HYPOTHESIS均可存在，Core不自动映射

## FACT != confirmed truth

C05“明天生日”：base 2026-09-14 10:00 UTC，用户说“明天是我的生日”，构造Claim claimant user-1 subject user-1 claim_type FACT content “2026-09-15是用户生日” asserted_at 2026-09-14 10:00 UTC valid_time 2026-09-15 point knowledge_state REPORTED confidence 0.70

验证：claim_type FACT, knowledge_state REPORTED, confidence 0.70, valid_time在asserted_at未来

锁死：FACT类型命题 != 已证实事实，confidence不自动1，knowledge_state不自动OBSERVED

C03也验证FACT confidence 0.37保持0.37不变成1.0

## confidence独立

Core只做0.0<=confidence<=1.0结构验证

禁止根据claim_type自动赋值、根据claimant_id自动赋值、根据“用户说得很肯定”自动变高、根据FACT自动1.0

C03验证0.0,0.37,1.0合法，-0.01,1.01非法ValidationError

## birthday fixture

C05已述，明天生日FACT+REPORTED 0.70，valid_time未来，asserted_at今天

## “一定考上”多Claim fixture

原始Observation chat text “我明天一定能考上某校” rev1

人工构造：

Claim A speech_fact：content “用户说出了‘我明天一定能考上某校’” claimant aios-observer subject user-1 claim_type FACT knowledge_state OBSERVED confidence 0.99 source_refs SourceRef(obs_id, rev1)

Claim B prediction：content “用户将考上某校” claimant user-1 subject user-1 claim_type PREDICTION knowledge_state REPORTED confidence 0.35 same SourceRef

可选Claim C belief：content “用户相信自己将考上某校” claim_type BELIEF REPORTED 0.90

验证：object_id不同，都是CLAIM，引用同一raw Observation rev1，A 0.99 B 0.35绝不能相等，不能因为“一定”自动变1

## “妈妈生气”BELIEF fixture

Observation “我觉得妈妈生气了”

Claim claimant user-1 subject mother-subject claim_type BELIEF content “用户认为妈妈正在生气” knowledge_state REPORTED confidence 0.80

验证BELIEF不是自动变成FACT+OBSERVED，更不能自动创建Event(type=anger) relationship_state emotion

用户belief和现实真相两回事，不要求AI自动产生“妈妈真的生气了”的现实Claim

## claimant vs subject

至少一个例子明确 claimant user-1 subject mother-subject BELIEF，两个字段独立保存，不要新增 claimant==subject约束

当前测试C07, C15等使用mother-subject验证独立

## same utterance independent revision

C09：先commit Observation rev1，然后同一world commit写入speech_fact rev1 prediction rev1，两者object_id不同 source_refs都pin Observation@1

然后只修订prediction同一object_id revision=2 confidence 0.35->0.20，speech_fact完全不修改

commit后验证prediction latest rev2 0.20, rev1仍可读0.35, speech_fact latest仍rev1 0.99, world revision按正常事务增加

证明同一句话拆出的不同Claim可单独修正，禁止修改一个时覆盖另一个

## hypothesis->fact revision能力

C10：Claim rev1 HYPOTHESIS/HYPOTHESIS 0.55，后续同object_id rev2 FACT/REPORTED 0.95，旧revision仍可读

只验证Claim字段可随revision修正，不实现claim.revise服务

## unknown_items

C11构造unknown_items ["具体学校","录取结果确认来源"]，model dump和SQLite round-trip保持，用于显式保存当前仍不知道什么，不要塞入content自由文本

## evidence ref fields

C12验证schema存在support_evidence_set_refs, counter_evidence_set_refs，可保存ObjectRef(evidence_set_id, rev1)版本信息，model-level，不commit假引用避免M0-006 NOT_FOUND，M0-009再测EvidenceSet业务

## content+confidence禁止

C13尝试只提供WorldObject必要字段+content+confidence但缺claimant_id, claim_type, asserted_at, knowledge_state必须ValidationError

目的Claim不能退化成{content, confidence}

## object_type固定

C14 Claim(object_type=EVENT)必须ValidationError，Claim必须CLAIM

## no semantic side effects

C15提交BELIEF“用户认为妈妈生气了”后查询EVENT, GOAL必须为空，不要因为Claim存在自动生成事件，同时不要凭空生成“妈妈真的生气了”的FACT Claim，本轮无语义推理副作用

## 保护M0-007

Observation仍只是raw/base observation，未增加claim_type/knowledge_state/confidence/event_type

## 保护M0-006

versioned SourceRef/ObjectRef, knowledge visibility, pinned refs, pending refs, future leakage protections保持，Claim测试中Observation引用必须pin revision

## 保护M0-005

append-only, strict revision +1, object_type immutable, World Revision与Object Revision独立

## 对抗验证

- A: 让FACT自动confidence=1，C03/C05必须失败（0.37/0.70被强制1），恢复，有效
- B: 删除knowledge_state或合并进claim_type，C01/C08/C13必须失败，有效
- C: 允许confidence 1.1或-0.1，C03必须失败，有效
- D: 让naive asserted_at通过，C04必须失败，有效
- E: 把“一定考上”speech_fact 0.99复制成prediction 0.99，C06必须失败，有效
- F: 修订prediction时同时覆盖speech_fact，C09必须失败，有效
- G: 把Claim简化成content+confidence其余可缺省，C13必须失败，有效
- 恢复正式代码后全量测试，不提交攻击代码

## local pytest

210 passed (194+16), 0 failed

Python 3.11.2本地，GitHub Actions Python 3.12预期同样通过

## reference

15 passed

## CI

起始9bee623 SUCCESS Python 3.12.14 194 passed

R1新HEAD push后CI_PENDING_CHIEF_VERIFICATION，总工直接核验真实HEAD/diff/CI/tests

## production NO CHANGE proof

git diff 9bee623850ce39701ec624a7b45fa1dba349cbca..HEAD -- src/aios_core => NO CHANGE

预期src/aios_core无diff

## 未解决问题

NONE，等待M0-008 CODE REVIEW，禁止M0-009
