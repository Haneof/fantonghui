# M0 Parallel Audit Adjudication — B10 / B11

日期：2026-09-14  
角色：`chief-01`  
状态：**BLOCKERS ACCEPTED / M0 REMAINS OPEN**

## 1. 审查输入价值裁决

当前治理目录共有三份并行审计结果：

- `auditor-e.md` — `ARCHITECTURE PASS`
- `auditor-d.md` — `BLOCKER FOUND`
- `auditor-e-01.md` — `BLOCKER FOUND`

这三份不能按“2票 blocker 对 1票 pass”计票。`auditor-d` 与 `auditor-e-01` 使用同一 audit branch，后者包含前者 B10 probe commit 并继续追加 B11，因此应视为**同一条红队证据链的递进版本**，不是两个完全独立发现。

`auditor-e.md` 的 PASS 对 B1~B9 回归有参考价值，但它没有覆盖后来被实际红 CI 复现的 B10/B11，因此不能抵消后续反例。

Chief 独立检查当前 candidate source 后确认：B10、B11 的根因都直接存在于生产语义代码，并非报告误判。

## 2. B10 — ACCEPTED BLOCKER

`WorldObject` 基类可直接实例化并携带任意 `ObjectType`；当前 durable normalization 使用 `type(obj).model_validate(snapshot)`，因此调用者可用基础/自定义 `WorldObject` 声称自己是 `Dependency`、`EvidenceSet` 等 canonical type，却绕过对应 frozen subtype schema/validator。

影响：

- durable `object_type` 与 payload schema 可以不一致；
- EvidenceSet cutoff / Dependency graph 等 subtype-specific invariant 可因 runtime class masquerade 被绕过；
- malformed dependency-labelled row 后续可导致 raw Pydantic `ValidationError` 从 public store path 泄漏。

裁决：**High / M0 Blocker**。

重新打开/继续打开：M0-009、M0-015、M0-017、M0-019、M0-022。

最小修复边界：建立 authoritative `ObjectType -> canonical WorldObject model` registry，并在 durable boundary 按 declared object_type 选择 canonical model 做 revalidation；后续 subtype-specific checks 必须基于 canonical normalized object。已有 malformed canonical-type rows 的内部重解析失败必须映射为 protocol storage failure，而不是 raw Pydantic exception。

## 3. B11 — ACCEPTED BLOCKER

当前 `canonical_json_value()` 对 Mapping 使用 `str(key)`。输入 `{1: "a", "1": "b"}` 中两个不同 accepted Python keys 会折叠成同一个 JSON key `"1"`，造成静默数据丢失，并可能使 materially different request 得到相同 durable payload/fingerprint，破坏 M0-016 idempotency separation。

裁决：**High / M0 Blocker**。

重新打开/继续打开：M0-016、M0-017、M0-022。

最小修复边界：M0 durable JSON contract 采用 JSON object semantics，递归拒绝所有非字符串 Mapping key；不得通过 `str(key)` 做有损 coercion。相同 canonicalizer 必须用于 operation arguments、world-object durable payload 与 replay fingerprint。新写入应返回 protocol `INVALID_ARGUMENT`，existing-key invalid retry 不得 alias 原请求。

## 4. 对 auditor-e PASS 的处理

保留为 B1~B9 的辅助回归证据，不作为当前 Gate PASS 证据。其结论已被后续可复现反例 supersede。

## 5. 当前 Gate

M0：**NOT PASSED**。  
M1：**BLOCKED**。  
Parallel core development：**BLOCKED**。

下一步由 chief-01 直接修复 B10/B11、加入 adversarial regression、跑全量 exact-head CI，再交新的只读独立审计。