# AIOS M2 接口契约（冻结版）· T14-T16

> 上位契约：tasks/contracts.md（总线/SDK/帧协议不变）。本契约只补 M2 三系统的消息与数据格式。
> 三棵树物理隔离：cognitiond 只写 cognitive_tree.db（认知树）；decisiond 只读它做校验；成长树写者 evolutiond 是 M3。

## 认知树存储（cognitive_tree.db · cognitiond 唯一写者）

```sql
CREATE TABLE IF NOT EXISTS cognition (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,   -- BELIEF / HYPOTHESIS / PREDICTION / UNKNOWN / SPEAKER_BINDING
  conclusion TEXT NOT NULL,
  confidence REAL NOT NULL,   -- 0.0–1.0，强制
  evidence   TEXT NOT NULL,   -- JSON array，引用人生树 raw_log.id 或其他认知 id
  status     TEXT NOT NULL,   -- ACTIVE / REVISED / INVALIDATED / CONFLICT
  epistemic  TEXT NOT NULL,   -- KNOWN / INFERRED / HYPOTHESIS / UNKNOWN / CONFLICT（认知五状态）
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
```

## T14 cognitiond（认知代理）

- 订阅：`evt.normalized`、`sys.cognition.assert`、`sys.query.cognition`
- `sys.cognition.assert` `{req_id, kind, conclusion, confidence, evidence:[...], epistemic}` → 校验 confidence∈[0,1]、epistemic 合法，落库 → 回 `evt.query.reply.<req_id>` `{id, status:"stored", confidence, epistemic}`；非法输入回 `{status:"rejected", reason}`
- `sys.query.cognition` `{req_id, q:{epistemic?}}` → 回 `{results:[{id,kind,conclusion,confidence,evidence,status,epistemic}]}`（可空过滤）
- 对 evt.normalized：v0 仅接收，不自动推导（自动推导是 M2 后续细化）

## T15 attentiond（租约代理）

- 订阅：`evt.stream`、`sys.lease.request`、`sys.lease.release`
- 租约表（内存）：`{lease_id: {event_id, deadline, state(ACTIVE/RELEASED)}}`
- `sys.lease.request` `{req_id, event_id, budget_ms}` → 签发 lease（uuid），`deadline=now+budget_ms/1000` → 回 `evt.query.reply.<req_id>` `{lease_id, deadline, budget_ms}`
- `sys.lease.release` `{lease_id}` → state=RELEASED → 回 `{released:true}`
- 后台每 0.2s：扫描 ACTIVE 且 now>deadline → 置 EXPIRED → 发布 `evt.lease.expired` `{lease_id, event_id}`，写 `run/lease_stats.json` `{granted, active, released, expired}`
- 对 evt.stream：v0 被动，不自动发租约

## T16 decisiond（决策代理）

- 订阅：`sys.decision.request`、`evt.normalized`
- 只读 cognitive_tree.db 做引用校验（read-only 连接，绝不写）
- `sys.decision.request` `{req_id, cites:[认知id...], risk_class, action}` → 判定顺序：
  1. cites 任一 id 在认知树查无 → `{verdict:"REJECT", reason:"CITATION_MISSING", ids:[...]}`
  2. cites 任一认知的 `epistemic != "KNOWN"` → `{verdict:"REJECT", reason:"INFERRED_AS_KNOWN", ids:[...]}`（宪法原则三落地：推断永不当事实用）
  3. `risk_class=="FINANCIAL"` 且 `action in ("pay","execute","transfer")` → `{verdict:"REQUIRE_CONFIRM", reason:"FINANCIAL_HIGH_RISK"}`
  4. 否则 → `{verdict:"ACCEPT"}`
- 回 `evt.query.reply.<req_id>`
- 对 evt.normalized：v0 仅接收

## M2 门禁（tests/test_m2.py，指挥官编写并执行）

1. 认知树物理隔离：cognitive_tree.db 独立文件存在
2. assert 一条 INFERRED + 一条 KNOWN → 落库且字段带 confidence/evidence/epistemic
3. decision 引用 INFERRED → REJECT(INFERRED_AS_KNOWN)；引用 KNOWN → ACCEPT
4. attentiond 租约 request(budget_ms=300) 不 release → 1s 内 evt.lease.expired 出现 + lease_stats.json expired>=1
5. decision risk_class=FINANCIAL action=pay → REQUIRE_CONFIRM；risk_class=SAFETY → ACCEPT

## 文件所有权

- 认知代理：`services/cognitiond.py`
- 租约代理：`services/attentiond.py`
- 决策代理：`services/decisiond.py`
- 指挥官：`tests/test_m2.py`（本契约即其判据）
