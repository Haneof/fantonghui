# M0-008 实现记录

状态：WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：Claim（主张）语义模型正式冻结

起始commit：9bee623850ce39701ec624a7b45fa1dba349cbca (M0-007 FINAL PASS 194 passed)

## 生产Claim已符合任务书 NO CHANGE

当前 src/aios_core/contracts/models.py Claim schema:

- WorldObject subclass, object_type Literal[CLAIM] default CLAIM
- claimant_id str, claim_type ClaimType, content str, valid_time TemporalExtent, asserted_at datetime aware, knowledge_state KnowledgeState, confidence float 0-1, support/counter list[ObjectRef], unknown_items list[str]
- 加上WorldObject公共字段

enums.py ClaimType至少11个：FACT, OPINION, BELIEF, DESIRE, INTENTION, PLAN, PREDICTION, PROMISE, PREFERENCE, INFERENCE, HYPOTHESIS，子集测试

KnowledgeState独立enum：OBSERVED, REPORTED, INFERRED, HYPOTHESIS, UNKNOWN, CONFLICT，禁止合并

FACT != truth：FACT只描述命题性质，不意味着confidence 1或OBSERVED或已确认，C05生日例子验证

confidence独立：Core只验证0-1，不自动赋值

不实现语义解析器：无LLM, embedding, classifier，人工构造fixture

不实现claim.create/revise服务：无ClaimService，SQLiteWorldStore验证revision即可

不提前实现EvidenceSet业务：保留support/counter引用能力，不增加聚合等，M0-009再测

## 测试文件 tests/unit/test_claim.py 16 tests C01-C15

- C01 schema: WorldObject subclass, 10 claim fields + public, object_type CLAIM default
- C02 ClaimType required set subset 11个
- C03 confidence bounds 0.0/0.37/1.0合法 -0.01/1.01非法，FACT 0.37保持不变成1.0
- C04 asserted_at aware合法 naive非法
- C05 明天生日 FACT+REPORTED 0.70 valid_time未来
- C06 一定考上多Claim拆分：Observation raw + speech_fact FACT OBSERVED 0.99 + prediction PREDICTION REPORTED 0.35 + optional belief BELIEF 0.90，object_id不同同一Observation@1，confidence不自动相等
- C07 妈妈生气 BELIEF mother-subject REPORTED，不是FACT+OBSERVED，不自动Event
- C08 独立组合 FACT+REPORTED, BELIEF+REPORTED, PREDICTION+REPORTED, INFERENCE+INFERRED, HYPOTHESIS+HYPOTHESIS
- C09 同一句话独立Revision：Observation rev1 + speech rev1 + prediction rev1同事务，修订prediction rev2 0.35->0.20 speech不变，验证history可读
- C10 Revision认知修正：HYPOTHESIS 0.55 -> FACT 0.95同object_id rev2，旧可读
- C11 unknown_items ["具体学校","录取结果确认来源"] round-trip
- C12 support/counter字段存在可保存ObjectRef，model-level不commit假引用
- C13 禁止content+confidence简化缺claimant_id等必须ValidationError
- C14 object_type固定 EVENT必须ValidationError
- C15 Core不自动产生现实真相：BELIEF提交后EVENT/GOAL空，无自动FACT
- claimant vs subject独立 mother-subject例子
- source_refs pin Observation@1

## 保护

- M0-007 Observation仍raw，未增加claim_type等
- M0-006 versioned refs, knowledge visibility, pinned, pending, future leakage
- M0-005 append-only revision +1 object_type immutable

## 对抗

A FACT auto 1 => C03/C05 FAIL, B delete knowledge_state => C01/C08/C13 FAIL, C confidence 1.1 => C03 FAIL, D naive asserted_at => C04 FAIL, E speech 0.99 copy prediction => C06 FAIL, F revise prediction overwrite speech => C09 FAIL, G simplify content+confidence => C13 FAIL，恢复后全量测试

## 测试

210 passed (194+16), 0 failed, Reference 15 passed, Production NO CHANGE proof git diff 9bee623..HEAD -- src/aios_core => NO CHANGE

## 证据

- tests/unit/test_claim.py
- reviews/M0/M0-007_final_PASS_2026-09-14.md M0-007 FINAL PASS归档
- reviews/M0/evidence/M0_008_REVIEW_PACKET.md
- reviews/M0/evidence/M0_008_TEST_OUTPUT.txt 210+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-008 CODE REVIEW，禁止M0-009
