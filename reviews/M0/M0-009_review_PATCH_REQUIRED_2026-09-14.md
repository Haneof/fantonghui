# M0-009 PATCH REQUIRED (TEST ONLY + durable boundary)

日期：2026-09-14

任务：EvidenceSet契约冻结

起始HEAD：1deef8c94ff105efc453ee461a19297ffa542a1b

GitHub Actions：SUCCESS Python 3.12.14 230 passed Reference 15 passed

生产代码：M0-009 schema方向PASS，但存在持久化绕过

## 生产审查

- models.py新增EvidenceSet validator逻辑：empty reject, member/support/counter/context pinned, selector.dimension_refs pinned, knowledge_cutoff <= learned_at via as_utc PASS
- 但validator只在模型验证时生效，WorldObject / nested models包含可变list和嵌套对象
- 合法EvidenceSet创建后 member_refs.append(floating) selector.dimension_refs.append(floating) coverage直接变异 selector.time_range直接变异 可以形成未经重新验证的对象状态
- SQLiteWorldStore.commit此前没有在durable write前重新model_validate完整对象图
- 因此EvidenceSet pinned/frozen等contract存在持久化绕过路径

## R1修复

- 唯一允许生产文件：src/aios_core/storage/sqlite_store.py
- 实现generic persistence revalidation：
  在durable commit边界重新验证WorldObject完整当前状态
  对object_list执行model_dump(mode="python", round_trip=True) + type(obj).model_validate(snapshot)
  若ValidationError => StoreError INVALID_ARGUMENT context object_id, object_type, revision, reason="persistence_revalidation_failed" from exc, 禁止泄露完整payload
  位置：BEGIN IMMEDIATE, idempotency replay检查, expected_world_revision检查, 然后revalidation, 然后revision/type validation, ref validation, 任何INSERT之前
  原子性：失败rollback，world revision不增加，非法对象不出现，不留下成功idempotency record
  generic：不能认识EvidenceSet业务类型，禁止isinstance EvidenceSet hardcode, 禁止selector业务查询等
- models.py本轮NO CHANGE
- 其他src NO CHANGE

## 新增测试 E20-E23

- E20 member_refs原地mutation攻击：Observation target rev1 commit world 1, 构造合法EvidenceSet member [target@1], 然后原地append floating revision None, 确认内存污染, commit必须StoreError INVALID_ARGUMENT reason persistence_revalidation_failed, world revision仍1, EvidenceSet不存在, target真实存在避免NOT_FOUND掩盖, 移除revalidation时必须失败因为旧Store会接受floating
- E21 selector.dimension_refs嵌套mutation：创建真实DimensionDefinition rev1 commit, 构造selector dimension_refs [dim@1] + EvidenceSet selector member [], 原地append floating, commit必须INVALID_ARGUMENT, world revision不增加
- E22 nested coverage mutation：Observation A commit, 构造合法coverage 0.7 + EvidenceSet member [A@1], 原地coverage_ratio=1.5, commit必须INVALID_ARGUMENT, 证明revalidation不是只针对ObjectRef而是完整对象图
- E23 selector.time_range mutation：合法selector time_range固定, EvidenceSet成功构造, 然后原地污染nested selector time_range="now-14d", commit必须INVALID_ARGUMENT不得持久化动态字符串, world revision不增加, 证明固定时间窗不能通过nested mutation绕过

## 加固E01/E09/E13

- E01 exact：selector union set == {EvidenceSelector, None}不能只检查包含, aggregation_method set {str, None}, aggregation_version同, filters exact (str, Any) origin dict, expected_count set {int, None}等，真正冻结exact schema不是只证明包含正确类型
- E09 exact fixed interval：保存expected_start 2026-09-01, expected_end 2026-09-14, expected_cutoff 2026-09-14 23:59, 一周后读取旧EvidenceSet用TemporalExtent.model_validate和KnowledgeWindow.model_validate严格as_utc equality, world_revision 1, member_refs [], 新Observation不在旧member_refs
- E13 strict error：不要or检查，改为明确检查"knowledge_window.knowledge_cutoff must not be after learned_at"必须出现在错误信息中

## 对抗

- A 移除revalidation E20 FAIL floating member被错误提交
- B 移除revalidation E21 FAIL nested floating dimension
- C 移除revalidation E22 FAIL coverage_ratio 1.5被提交
- D 移除revalidation E23 FAIL 动态字符串被提交
- E 把filters检查改回只检查第一个参数 dict[str,str] 严格test必须失败
- F 让旧EvidenceSet返回漂移后start/end/cutoff 加强后E09必须失败
- 恢复正式代码，禁止提交攻击版本

## 状态

PATCH REQUIRED -> R1 PATCH COMPLETE后等待FINAL REVIEW
