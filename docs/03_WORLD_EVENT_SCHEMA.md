# AIOS World / Event Schema V0.1

## Event

```json

{

  "id": "evt_001",

  "timestamp": "2026-09-09T22:10:01+08:00",

  "source": "mic",

  "type": "speech",

  "content": "这个价格我们真的接受不了",

  "entities": ["person_017", "contract_003"],

  "location_id": "place_004",

  "confidence": 0.96,

  "raw_ref": null

}

```

## Entity

```json

{

  "id": "person_017",

  "type": "person",

  "identity": {

    "name": null,

    "aliases": [],

    "confidence": 0.00

  },

  "relationships": [],

  "evidence": []

}

```

## World State

```json

{

  "timestamp": "2026-09-09T22:10:01+08:00",

  "user": {},

  "location": {},

  "mode": "WORK",

  "people": [],

  "environment": {},

  "active_situations": [],

  "active_goals": [],

  "pending_tasks": []

}

```

## World Change

必须显式表示“发生了什么变化”：

```json

{

  "id": "chg_001",

  "window": {"start": "...", "end": "..."},

  "change_type": "NEGOTIATION_ESCALATION",

  "before": {},

  "after": {},

  "entities": ["person_017", "contract_003"],

  "evidence_events": ["evt_001", "evt_002"],

  "confidence": 0.88

}

```

## Memory

```json

{

  "id": "mem_001",

  "timestamp": "2026-09-09T22:10:01+08:00",

  "level": "RAW_LOG",

  "location": "place_004",

  "entities": ["person_017"],

  "domain": "WORK",

  "type": "EVENT",

  "content": "张总提出合同价格问题",

  "importance": 0.72,

  "tags": ["contract", "price"],

  "linked_memories": ["mem_002"]

}

```

`level` 枚举：`RAW_LOG / HOURLY / DAILY / WEEKLY / MONTHLY / QUARTERLY / HALF_YEARLY / YEARLY / 3YEAR`。

## Relationship

Relationship 是独立的一等对象。Entity 不永久嵌入完整 Relationship，仅保存 relationship IDs。

```json

{

  "id": "rel_001",

  "entity_a": "user",

  "entity_b": "person_017",

  "type": "CLIENT",

  "strength": 0.82,

  "status": "ACTIVE",

  "evidence": ["evt_021", "evt_044"]

}

```

## Cognition

```json

{

  "id": "cog_001",

  "type": "BELIEF",

  "conclusion": "张总更关注交付风险而非单纯价格",

  "confidence": 0.72,

  "evidence": ["evt_021", "evt_044"],

  "counter_evidence": ["evt_087"],

  "last_verified": "2026-09-08",

  "status": "ACTIVE"

}

```

## Growth

```json

{

  "id": "growth_001",

  "situation": "用户情绪低落",

  "judgment": "用户需要连续安慰",

  "action": "连续询问",

  "feedback": "别烦我",

  "outcome": "用户终止互动",

  "lesson": "用户低落时可能更需要空间",

  "confidence": 0.42,

  "rollback_key": "strategy_018"

}

```

Cognition `status` 枚举：`ACTIVE / REVISED / INVALIDATED / CONFLICT`。

## Decision

```json

{

  "id": "dec_001",

  "trigger_change": "chg_001",

  "judgment": "可能值得介入",

  "options": ["silent", "notify", "suggest", "execute"],

  "selected": "notify",

  "confidence": 0.78

}

```

## 绝对规则

- Event 是事实输入，不写 AI 推断。

- Cognition 不写进 Memory 的事实字段。

- Growth 不覆盖原始判断和结果。

- 每个推断必须能够追溯到证据。

## Canonical naming rule

`raw_ref` 是标准 Event 契约中的唯一原始数据引用字段。它只能引用短生命周期的原始感知数据，不表示把原始音频/图像长期存储；`raw_data` 如存在，只允许存在于感知适配器内部瞬态对象，不得进入标准 Event。

## Canonical schema set

标准对象共 9 个：`event / entity / relationship / world_state / memory / world_change / cognition / decision / growth`。
