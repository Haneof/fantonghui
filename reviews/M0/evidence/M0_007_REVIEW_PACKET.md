# M0-007 REVIEW PACKET

日期：2026-09-14

任务：Observation（基础观测）契约正式冻结

起始commit：eacd160a08e0c3aefa9e3d04354a8ece86599ccb (M0-006 FINAL PASS 181 passed)

当前Observation生产schema：src/aios_core/contracts/models.py

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

加上WorldObject公共11字段：object_id, object_type, subject_id, revision, occurred, learned_at, recorded_at, source_refs, created_by, status, metadata

为什么NO CHANGE：
- 生产Observation已完全符合任务书：source_kind str, modality str, value Any, unit Optional, data_quality dict, raw_locator Optional, object_type Literal OBSERVATION, extra forbid继承自WorldObject
- 未新增SourceKind/Modality enum，保持str扩展性
- 未新增event_type/emotion/claim_type等高层语义字段
- value正式语义：允许标量/字符串/结构化JSON，不解释焦虑/分手等
- raw_locator只保存位置，不实现blob store
- data_quality保持dict[str, Any]，不放语义推理
- 符合O01-O12全部验收

四种Observation fixture：
- Heart rate O02: source_kind=device_sensor modality=heart_rate value=82 unit=bpm data_quality signal_quality good, occurred aware, learned_at稍后, commit成功, value round-trip
- GPS O03: device_sensor gps value {lat,lon,accuracy_m} unit None, 结构化round-trip, 不产生地点事件
- Conversation O04: chat text value "我今天有点累" raw_locator conversation://..., 原文完整保存, 不产生emotion/event_type
- App answer O05: app quiz_answer value {question_id,answer,correct}, 不推断ability

同一时间轴测试 O09：
- 同一SQLiteWorldStore一次或多次commit写入 heart rate, GPS, chat text, App answer 4条Observation
- 全部 object_type=OBSERVATION, 都有 occurred/learned_at/recorded_at
- store.list_payloads(object_type=OBSERVATION)返回4条
- 证明不同来源进入同一统一时间轴，不是每种来源一套对象体系

event_type拒绝 O06：
- Observation(..., event_type="breakup") => ValidationError extra forbid
- 原始文本"我们分手了"可以保存为value，但不能直接存event_type，必须由Claim/Event层表达

其他semantic extra拒绝 O07：
- emotion="anxious" => ValidationError
- claim_type="FACT" => ValidationError
- relationship_state="conflict" => ValidationError
- 冻结Observation不是语义结论容器，现有extra forbid自然完成约束

object_type Literal冻结 O08：
- Observation(object_type=ObjectType.EVENT, ...) => ValidationError
- 必须 Literal[OBSERVATION], annotation = typing.Literal[<ObjectType.OBSERVATION: 'observation'>]
- 防止伪装

raw_locator roundtrip O11：
- Observation device audio_metadata value {format, duration_seconds} raw_locator file:///raw/audio/session-1.wav
- commit并读取保持不变
- 不塞bytes/bytearray/memoryview入value，不实现blob

Observation != Wake O10：
- 提交Observation后 store.list_payloads(WAKE) == [] 0条Wake
- 确认底层Store没有 Observation->Wake 隐式副作用
- 不要修改Wake, 不要添加trigger

Observation不会自动生成Claim/Event/Goal O12：
- 提交单独Observation, 事务返回object_refs只包含该Observation
- 查询 CLAIM, EVENT, GOAL, WAKE均为空
- Core存储Observation本身不得凭空制造衍生对象

保护M0-006/M0-005/M0-004：
- ObjectRef/SourceRef pinned/floating, knowledge visibility, pending refs, Dependency exact ObjectRef不变
- revision +1, append-only, object_type immutable, subject_id NOT FROZEN, transaction atomicity不变
- occurred/learned_at/recorded_at timezone-aware canonical UTC DST instant ordering不变

对抗验证：
- A: WorldObject extra="forbid", 临时改allow => O06/O07失败 (Relaxed模型接受event_type), 恢复
- B: Observation.object_type Literal[OBSERVATION]临时放宽为ObjectType => O08失败 (FakeObservation允许EVENT), 恢复
- C: 模拟Store在Observation commit后自动创建Wake => O10/O12失败, 当前无此副作用, 恢复
- D: 让不同source_kind必须使用不同对象class => O02-O05/O09设计证明无此要求, 同一Observation class处理所有来源, 统一时间轴

local pytest：
- 193 passed (基线181 + 12新增), 0 failed
- Python 3.11.2本地, 预期GitHub Actions Python 3.12同样通过

reference pytest：
- 15 passed

CI状态：
- 起始HEAD eacd160 GitHub Actions SUCCESS Python 3.12.14 181 passed
- R2新HEAD push后自动触发CI, 施工方看不到写 CI_PENDING_CHIEF_VERIFICATION
- 总工程师直接核验

production NO CHANGE proof：
- git diff eacd160a08e0c3aefa9e3d04354a8ece86599ccb..HEAD -- src/aios_core => NO CHANGE
- 预期src/aios_core无diff

未解决问题：
- NONE, 等待总工程师 M0-007 CODE REVIEW, 禁止M0-008

---

## R1 PATCH 2026-09-14 消除false-green与helper时间语义回退 (TEST ONLY)

### 生产代码
PASS/FROZEN NO CHANGE, 670c009 GitHub Actions SUCCESS 193 passed Python 3.12.14

### helper直接datetime比较问题
- 原make_observation:
```
recorded = recorded_at or learned
if recorded < learned:
    recorded = learned
```
- 直接datetime比较，M0-004已冻结instant语义应使用as_utc，helper不应引入直接比较
- 删除if块

### helper静默修复非法fixture问题
- 原helper静默修正非法时间，测试无法暴露非法输入
- 改为：
```
recorded = (recorded_at if recorded_at is not None else learned)
```
- 直接交给Observation WorldObject validator，非法应ValidationError
- 新增O13验证：learned 10:00 UTC, recorded 09:59 UTC => must raise ValidationError
- 目的不是重开发M0-004，而是证明M0-007 fixture没有绕过已冻结时间不变量
- 不在helper中修复时间

### O05永真断言false-green
- 原：
```
assert "confidence" not in payload or isinstance(...) is False or True
```
- 永真，无法检测confidence泄漏
- 改为严格：
```
assert "confidence" not in payload
```
- 加上ability, learning_problem严格无
- 若未来Observation声明confidence，O05必须失败

### O13新增
- learned_at 2026-09-14 10:00 UTC, recorded_at 09:59 UTC
- make_observation必须raise ValidationError
- 证明helper不掩盖非法公共时间

### 其余O01-O12保持
- schema, heart-rate, GPS, conversation, app answer, event_type forbidden, semantic extras, object_type literal, unified timeline 4 obs, !=Wake 0, raw_locator, no derived均保持不削弱

### 对抗验证
- A: 临时恢复O05 or True永真，证明无法检测confidence，恢复严格断言，有效
- B: 临时恢复if recorded < learned修复，O13必须失败（非法被修正），恢复正式，有效
- 不提交攻击版本

### 测试
- 194 passed (193+1 O13), 0 failed
- Reference 15 passed
- Production NO CHANGE proof: git diff 670c009..HEAD -- src/aios_core => NO CHANGE

### CI
- 起始670c009 SUCCESS Python 3.12.14 193 passed
- R1 push后CI_PENDING_CHIEF_VERIFICATION
