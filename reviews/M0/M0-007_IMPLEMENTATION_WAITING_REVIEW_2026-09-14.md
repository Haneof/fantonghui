# M0-007 实现记录

状态：WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：Observation（基础观测）契约正式冻结

起始commit：eacd160a08e0c3aefa9e3d04354a8ece86599ccb (M0-006 FINAL PASS)

## 生产Observation已正确，无需修改

当前 src/aios_core/contracts/models.py:

```
class Observation(WorldObject):
    object_type: Literal[ObjectType.OBSERVATION] = ObjectType.OBSERVATION
    source_kind: str
    modality: str
    value: Any = None
    unit: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    raw_locator: str | None = None
```

符合任务书：
- WorldObject subclass, 11公共字段 + 6观测字段
- object_type默认 OBSERVATION, Literal冻结
- source_kind/modality保持str，不新增enum
- 不新增event_type/emotion/claim_type/knowledge_state/relationship_state/goal_type等高层语义字段
- value允许标量/字符串/结构化JSON，不解释焦虑/分手等
- raw_locator指向原始大文件，不实现blob store
- data_quality dict[str, Any]保存质量信息，不放语义推理
- Observation != Wake, 单独写入不自动创建Wake

## 测试文件

新建 tests/unit/test_observation.py 独立正式契约测试，12 tests:

- O01 Schema contract: WorldObject subclass, 11+6字段, object_type default
- O02 Heart-rate: device_sensor heart_rate 82 bpm signal_quality good
- O03 GPS: device_sensor gps {lat,lon,accuracy_m} round-trip, 不产生事件
- O04 Conversation: chat text "我今天有点累" raw_locator conversation://..., 不产生emotion/event_type
- O05 App answer: app quiz_answer {question_id,answer,correct}, 不推断ability
- O06 禁止event_type: event_type="breakup" => ValidationError extra forbid
- O07 Semantic extra: emotion/claim_type/relationship_state => ValidationError
- O08 Object type不可伪装: object_type=EVENT => ValidationError
- O09 多来源同一时间轴: 4 obs same store, list_payloads OBSERVATION 4条, 证明统一时间轴
- O10 Observation默认不Wake: list_payloads WAKE [] 0条
- O11 raw_locator round-trip: audio_metadata file:///raw/audio/... 保持
- O12 底层观测不产生衍生对象: object_refs仅1条, CLAIM/EVENT/GOAL/WAKE均空

## 保护

- M0-006: ObjectRef/SourceRef pinned/floating, knowledge visibility, pending refs, Dependency exact ObjectRef不变
- M0-005: revision +1, append-only, object_type immutable, transaction atomicity不变
- M0-004: occurred/learned_at/recorded_at timezone-aware canonical UTC DST instant ordering不变
- 不提前做M0-008: 无Claim拆分, 无LLM, 无情绪模型, 无事件识别

## 对抗验证

- A: WorldObject extra forbid临时allow => O06/O07失败, 恢复, 有效
- B: Observation.object_type Literal放宽为ObjectType => O08失败, 恢复, 有效
- C: 模拟Store Observation后自动创建Wake => O10/O12失败, 当前无副作用, 有效
- D: 不同source_kind必须不同class => O02-O05/O09证明无此要求, 统一Observation, 有效
- 未提交攻击代码

## 测试

- 本地 193 passed (181+12), 0 failed
- Reference 15 passed
- Production NO CHANGE: git diff eacd160..HEAD -- src/aios_core => NO CHANGE

## 证据

- tests/unit/test_observation.py
- reviews/M0/M0-006_final_PASS_2026-09-14.md (M0-006 FINAL PASS归档)
- reviews/M0/evidence/M0_007_REVIEW_PACKET.md
- reviews/M0/evidence/M0_007_TEST_OUTPUT.txt 193+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-007 CODE REVIEW，禁止开始M0-008。
