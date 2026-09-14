# M0-009 REVIEW PACKET

日期：2026-09-14

任务：EvidenceSet（一等证据集合）契约冻结

起始commit：65f1dd2868dfa638b9090e6dea997edd63dc3e66 (M0-008 FINAL PASS 211 passed Python 3.12.14 SUCCESS)

## EvidenceSet schema

src/aios_core/contracts/models.py 修改后：

```
class EvidenceSet(WorldObject):
    object_type = EVIDENCE_SET
    purpose: str
    knowledge_window: KnowledgeWindow
    member_refs: list[ObjectRef]
    support_refs: list[ObjectRef]
    counter_refs: list[ObjectRef]
    context_refs: list[ObjectRef]
    selector: EvidenceSelector | None
    selection_method: str
    aggregation_method: str | None
    aggregation_version: str | None
    coverage: EvidenceCoverage
    stale: bool
    validator:
      - if not member_refs and selector None => ValueError
      - member_refs/support_refs/counter_refs/context_refs any revision None => ValueError "<field> requires pinned ObjectRef revisions"
      - selector.dimension_refs any revision None => ValueError "selector.dimension_refs requires pinned ObjectRef revisions"
      - knowledge_window.knowledge_cutoff <= learned_at per as_utc else ValueError
```

EvidenceSelector schema：

selector_type str, subject_id str, time_range TemporalExtent, dimension_refs list[ObjectRef], filters dict[str,Any], algorithm_version str, extra forbid

EvidenceCoverage schema：

expected_count int|None ge0, observed_count int|None ge0, coverage_ratio float|None ge0 le1, missing_description list[str]

## empty reject

E02: member_refs=[] selector=None purpose="综合多个维度判断" selection_method="AI认为如此" => ValidationError, 禁止只存自然语言

## explicit member模式

E03: Observation A rev1 B rev1 commit, EvidenceSet member_refs [A@1, B@1] selector None knowledge_window固定 commit成功 round-trip A@1 B@1

## selector模式

E07: EvidenceSelector dimension_interval subject user-1 time_range固定 dimension_refs [] filters {} algorithm v1, EvidenceSet member_refs [] selector=selector合法

## materialization capability

E08: rev1 selector存在 member [] commit, 同object_id rev2相同selector member [A@1,B@1] commit, 验证rev1仍[] rev2为A@1,B@1, 证明query结果可通过新revision材料化，不实现自动query

## pinned Evidence refs

- E04 member floating: ObjectRef revision None => ValidationError "member_refs requires pinned..."
- E05 support/counter/context floating分别测试 revision None => ValidationError
- E06 selector dimension floating: dimension_refs [ObjectRef revision None] => ValidationError, revision=1合法 model-level
- E19 exact annotation: member/support/counter/context list[ObjectRef] via get_type_hints origin list args (ObjectRef,)
- 总工裁决：EvidenceSet中的member/support/counter/context只允许pinned revision=N，禁止floating，历史证据不能随target latest变化

## fixed time_range

- E09: selector time_range 2026-09-01->2026-09-14 knowledge_cutoff 2026-09-14 23:59 UTC保存，然后写入2026-09-21新Observation，再读旧revision selector仍原区间 cutoff仍2026-09-14 新Observation不得自动出现在旧member_refs
- E10 dynamic time替代拒绝：EvidenceSelector time_range="now-14d" => ValidationError, extra forbid, 禁止relative_time/last_n_days/dynamic_window, TemporalExtent保存明确时间，filters保持dict不解析DSL
- 正式冻结：selector时间必须是固定绝对时间，一周后读取旧EvidenceSet仍原区间，绝不能自动变成now-14d

## frozen knowledge_cutoff

- E13: learned_at 10:00 UTC cutoff 11:00 UTC => ValidationError, cutoff 10:00合法, 09:00合法, as_utc比较, 原因系统不能在10:00创建EvidenceSet却声称快照允许知道11:00资料
- E14: KnowledgeWindow world_revision round-trip：knowledge_cutoff T world_revision 7 model dump后仍7，不自动改成当前world revision，M1-006 service以后负责真实赋值，保持int|None

## KnowledgeWindow world_revision round-trip

E14已述，world_revision 7 round-trip

## support/counter/context separation

E11: Observation S/C/X, EvidenceSet support [S@1] counter [C@1] context [X@1] round-trip后严格support==S counter==C context==X不得互相污染，不得合并成一个列表，不得只存支持

## coverage/missingness

E12: expected 10 observed 7 ratio 0.7 missing ["09:30-09:45 心率缺失","没有比赛名称"] model dump和SQLite读取保持，当前M0契约coverage+missingness，不要新增重复字段

E17: coverage_ratio 0.0/0.5/1.0合法 -0.01/1.01 ValidationError, expected/observed负数拒绝，不增加observed<=expected约束

## pinned history

E15: Observation target rev1 old, EvidenceSet member [target@1], 然后target rev2 new, 读取EvidenceSet member仍rev1，用member ref读取target必须old不能new，历史钉住不漂移，M0-006 pinned语义在EvidenceSet更严格

## stale/rebuild revision capability

E16: rev1 members [A@1] stale False, 迟到Observation B后 rev2同object_id revision2 members仍[A@1] stale True, rev3同object_id revision3新knowledge_window members [A@1,B@1] stale False, 验证rev1不变 rev2可读stale True rev3可读members+1，证明schema支持stale/rebuild通过新revision，不实现自动mark stale，完整生命周期属于M3

## object_type固定

E18: EvidenceSet object_type EVENT => ValidationError, 必须EVIDENCE_SET

## 生产文件允许范围

- 允许：src/aios_core/contracts/models.py 只修改EvidenceSet validator及必要最小契约
- 预期不修改：enums.py, time.py, refs.py, base.py, storage/sqlite_store.py
- 实际diff：仅models.py新增pinned checks和cutoff check，符合允许范围
- 其他src无diff

## 保护

- M0-008 Claim完全冻结，禁止修改Claim/ClaimType/KnowledgeState
- M0-006 ObjectRef pinned/floating通用语义保留，M0-009仅在EvidenceSet业务对象施加更严格规则，member/support/counter/context必须pinned，不得把全系统ObjectRef改成revision mandatory
- M0-005 append-only strict revision +1 object_type immutable等保持
- M0-007 Observation仍raw

## 对抗验证

- A: 删掉empty validator，E02必须失败，恢复，有效
- B: 允许member revision None，E04/E15必须失败或失去冻结语义，恢复，有效
- C: 允许support/counter/context floating，E05必须失败，恢复，有效
- D: 去掉knowledge_cutoff <= learned_at，E13必须失败，恢复，有效
- E: 让旧selector interval按当前时间重算，E09必须失败，恢复，有效
- F: 把support/counter/context合并成一个列表，E11必须失败，恢复，有效
- G: EvidenceSet rev2写入时覆盖rev1，E08/E16以及M0-005历史测试必须失败，恢复，有效
- 全部恢复，未提交攻击代码

## full pytest

230 passed (211+19), 0 failed

Python 3.11.2本地，GitHub Actions Python 3.12预期同样通过

## reference

15 passed

## CI状态

起始65f1dd2 SUCCESS Python 3.12.14 211 passed

新HEAD push后CI_PENDING_CHIEF_VERIFICATION，总工直接检查真实HEAD/diff/CI/tests

## production diff

- models.py：新增pinned checks和cutoff check，符合任务书允许范围
- 其他src：NO CHANGE

## 未解决问题

NONE，等待M0-009 CODE REVIEW，禁止M0-010

---

## R1 PATCH 2026-09-14 补齐durable write boundary Pydantic revalidation (PRODUCTION + TEST)

### 缺陷

- EvidenceSet validator只在模型验证时生效，WorldObject包含可变list和嵌套对象
- 合法创建后 member_refs.append(floating), selector.dimension_refs.append(floating), coverage变异, selector.time_range变异可形成未经重新验证状态
- SQLiteWorldStore.commit此前不重新model_validate完整对象图
- EvidenceSet pinned/frozen等contract存在持久化绕过

### 修复

- models.py NO CHANGE (已有pinned和cutoff逻辑PASS)
- 唯一允许生产修改：src/aios_core/storage/sqlite_store.py
- 增加generic persistence revalidation：
  from pydantic import ValidationError
  在commit中：BEGIN IMMEDIATE, idempotency replay, expected_world_revision check, 然后：
```
validated_objects = []
for obj in object_list:
    try:
        snapshot = obj.model_dump(mode="python", round_trip=True)
        validated = type(obj).model_validate(snapshot)
    except ValidationError as exc:
        raise StoreError(INVALID_ARGUMENT, "world object failed persistence validation",
            context={object_id, object_type, revision, reason="persistence_revalidation_failed"}) from exc
    validated_objects.append(validated)
object_list = validated_objects
```
  然后pending_pairs, revision validation, ref validation, INSERT
- generic：不认识EvidenceSet，不hardcode，不实现selector查询/materialize/stale传播
- 错误泄露：code INVALID_ARGUMENT, context object_id, object_type, revision, reason persistence_revalidation_failed, 禁止完整payload, raise from exc保留链
- 原子性：revalidation在任何world_commits/object_revisions/operations/idempotency success之前，失败rollback world revision不增加，无成功idempotency record
- idempotency顺序：已有成功replay优先返回，不被revalidation破坏，VERSION_CONFLICT继续优先

### E20 member mutation

- 初始：Observation target rev1 commit world 1, 合法EvidenceSet member [target@1]
- mutation：es.member_refs.append(ObjectRef(target, revision=None)) 确认revision None
- commit：StoreError INVALID_ARGUMENT reason persistence_revalidation_failed
- world revision：仍1
- 结果：EvidenceSet不存在 get_payload NOT_FOUND, 移除revalidation时旧Store会接受floating并提交，E20 FAIL

### E21 selector mutation

- 初始：DimensionDefinition rev1 commit world 1, selector dimension_refs [dim@1] + EvidenceSet selector member []
- mutation：es.selector.dimension_refs.append(floating None) 确认存在
- commit：INVALID_ARGUMENT
- 结果：world revision不增加，EvidenceSet不存在，移除revalidation则FAIL

### E22 coverage mutation

- 初始：Observation A commit, coverage expected 10 observed 7 ratio 0.7 + EvidenceSet member [A@1]
- mutation：es.coverage.coverage_ratio = 1.5 确认内存1.5
- commit：INVALID_ARGUMENT
- 结果：world revision不增加，EvidenceSet不存在，证明revalidation完整对象图非仅ObjectRef

### E23 time_range mutation

- 初始：合法selector time_range固定 start 2026-09-01 end 2026-09-14
- mutation：es.selector.time_range = "now-14d" 确认内存错误类型
- commit：INVALID_ARGUMENT不得持久化动态字符串
- 结果：world revision不增加，证明固定时间窗不能通过nested mutation绕过

### E01 exact

- selector union：set(args) == {EvidenceSelector, None} exact, 不是只包含
- filters：origin dict args (str, Any) exact
- aggregation：set {str, None} exact
- coverage：expected set {int, None}, observed set {int, None}, ratio set {float, None} exact

### E09 fixed interval

- start：as_utc(stored.start) == as_utc(expected_start 2026-09-01)
- end：as_utc(stored.end) == as_utc(expected_end 2026-09-14 23:59)
- cutoff：as_utc(stored cutoff) == as_utc(expected_cutoff 2026-09-14 23:59)
- world_revision：1
- new observation：2026-09-21新Observation不在旧member_refs, member_refs []

### E13

- 结果：明确检查"knowledge_window.knowledge_cutoff must not be after learned_at"在错误信息中，避免其他无关错误碰巧变绿

### 正式测试

- 234 passed (230+4 E20-E23), 0 failed, 1 warning (Pydantic serializer warning for time_range string expected but we test mutation)
- Reference 15 passed
- Production diff：models.py NO CHANGE, sqlite_store.py CHANGED generic revalidation, 其他src NO CHANGE

### 对抗

- A 移除revalidation E20 FAIL floating member被提交
- B 移除revalidation E21 FAIL nested floating dimension
- C 移除revalidation E22 FAIL coverage 1.5被提交
- D 移除revalidation E23 FAIL 动态字符串被提交
- E filters只检查第一个参数 dict[str,str] 严格test失败
- F 旧EvidenceSet返回漂移后start/end/cutoff 加强后E09失败
- 恢复正式代码

### CI

- 起始1deef8c SUCCESS Python 3.12.14 230 passed
- R1 push后CI_PENDING_CHIEF_VERIFICATION
