# M0 Gate — B10 / B11 修复记录

日期：2026-09-14  
角色：`chief-01`  
状态：**PATCH APPLIED / WAITING EXACT CI — NOT FINAL PASS**

## 1. 输入

并行红队后续反例：

- B10：canonical `object_type` 可由基础/自定义 `WorldObject` 冒充，绕过冻结 subtype schema 与 subtype-specific durable invariant；
- B11：durable JSON canonicalization 对 Mapping key 使用 `str(key)`，使 `1` 与 `"1"` 折叠，造成数据丢失和幂等 alias。

Chief 已独立核验源码，接受两项为 High / M0 blocker。

## 2. B10 修复

新增 authoritative `ObjectType -> canonical WorldObject model` registry。

Durable boundary 不再以调用方 runtime `type(obj)` 作为契约权威，而是：

1. 从 `obj.object_type` 选择 frozen canonical model；
2. 用 canonical model 重新验证 round-trip snapshot；
3. 后续 EvidenceSet cutoff、Dependency graph、reference collection 与 durable serialization 均基于 canonical normalized object。

这意味着基础或自定义 `WorldObject` 如果声称自己是 `Dependency`、`EvidenceSet`、`Task`、`Event`、`Claim`、`Relation`、Dimension 等 canonical type，却不满足该 canonical schema，将在 durable write 前得到 `INVALID_ARGUMENT / persistence_revalidation_failed`。

同时，若历史/外部损坏数据库中已经存在 `object_type='dependency'` 但 payload 不能解析成 Dependency 的行，Dependency graph rebuild 不再泄漏 raw Pydantic `ValidationError`，而是 `STORAGE_FAILURE / corrupt_dependency_payload`。

## 3. B11 修复

M0 durable JSON contract 冻结为 JSON object semantics：**所有 Mapping key 必须是 string**。

递归 canonicalizer 不再 `str(key)`；任何层级的非字符串 mapping key 都在持久化前被拒绝。

- 新写入：`INVALID_ARGUMENT / durable_json_validation_failed`
- 已使用 idempotency key 的非法 retry：`IDEMPOTENCY_CONFLICT / request_revalidation_failed`
- 合法字符串 key 保持无损、排序稳定、跨进程稳定。

同一 canonicalizer 继续用于：

- OperationRequest.arguments durable audit JSON；
- WorldObject durable payload；
- idempotency fingerprint。

## 4. M0-019 边界调整

旧 M0-019 测试使用自定义 `WorldObject` subclass 并声明 `ObjectType.ENTITY` 来承载任意 refs。B10 证明这种测试 helper 本身会鼓励 canonical-type masquerade。

测试已改用正式 canonical `Relation` / `Observation` 模型重新覆盖：

- missing ref 拒绝；
- same-tx EvidenceSet→Observation；
- distinct-object mutual refs 合法；
- current/floating self-ref 拒绝；
- historical pinned self-link 合法；
- no public ref-validation bypass；
- pending future ref 在 cutoff 下拒绝。

因此并未放弃 M0-019 原 invariant，只移除了不再允许的伪 canonical helper。

## 5. 新增对抗测试

`tests/unit/test_m0_gate_fifth_followup.py`

覆盖：

- 7 个 canonical type masquerade；
- legacy poisoned dependency row protocol mapping；
- `1` vs `"1"` mapping-key collision；
- nested non-string key；
- existing-key invalid retry 不得 alias；
- OperationRequest.arguments nested key；
- legal string-key lossless round-trip。

## 6. Candidate

语义修复 commit：

`d342015b96e62a31e240971c9f9d010613282743`

本 review commit 只用于归档和触发 source-equivalent exact-head CI，不改变生产语义。

M0 仍未通过；必须等待全量 formal + Reference CI 全绿，并继续独立红队复审。