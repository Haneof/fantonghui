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

## Cognition

```json

{

  "id": "cog_001",

  "type": "BELIEF",

  "conclusion": "张总更关注交付风险而非单纯价格",

  "confidence": 0.72,

  "evidence": ["evt_021", "evt_044"],

  "counter_evidence": ["evt_087"],

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
