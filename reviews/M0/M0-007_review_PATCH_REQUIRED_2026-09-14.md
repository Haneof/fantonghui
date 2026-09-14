# M0-007 PATCH REQUIRED (TEST ONLY)

日期：2026-09-14

任务：Observation（基础观测）契约正式冻结

起始HEAD：670c0094d03121e3621f9a34a9df5c12c594f254

GitHub Actions：SUCCESS Python 3.12.14 193 passed Reference 15 passed

生产代码：PASS / FROZEN, NO CHANGE

## 生产审查

- src/aios_core/contracts/models.py Observation已符合任务书：WorldObject subclass, Literal[OBSERVATION], source_kind str, modality str, value Any, unit Optional, data_quality dict, raw_locator Optional, 11公共字段, extra forbid
- 未新增enum, 未新增高层语义字段event_type/emotion等
- value语义正确, raw_locator round-trip, Observation != Wake, 无衍生对象
- 生产契约PASS/FROZEN

## 测试漏洞 R1

### helper直接datetime比较问题

- make_observation helper中存在：
```
recorded = recorded_at or learned
if recorded < learned:
    recorded = learned
```
- 这是直接aware datetime instant比较，M0-004已冻结必须使用as_utc/canonical比较，虽然WorldObject validator内部已用as_utc，但helper不应引入直接比较
- 更严重是silent repair问题

### helper静默修复非法fixture问题

- helper静默把非法时间（recorded_at < learned_at）修正为合法，导致测试无法暴露非法输入
- 测试fixture必须暴露非法输入，不能替生产模型“帮忙修好”
- 因此删除if recorded < learned块，改为：
```
recorded = (recorded_at if recorded_at is not None else learned)
```
- 直接交给Observation自身的WorldObject validator验证，必须raise ValidationError

### O05 `or True` false-green

- 存在：
```
assert "confidence" not in payload or isinstance(payload.get("confidence"), (int, float)) is False or True
```
- 最后`or True`导致永真，无论payload是否包含confidence都通过，false-green
- 若未来有人给Observation声明confidence字段，O05无法失败
- 改为严格：
```
assert "confidence" not in payload
```

## R1为TEST ONLY

- 禁止修改src/aios_core/**，包括models.py, base.py, time.py, sqlite_store.py
- 仅修复tests/unit/test_observation.py helper和O05, 新增O13
- M0-008 HOLD

## 修复后预期

- 194 passed (193+1 O13)
- Reference 15 passed
- Production NO CHANGE proof: git diff 670c009..HEAD -- src/aios_core => NO CHANGE
- 对抗验证A/B有效

## 状态

PATCH REQUIRED -> R1 PATCH COMPLETE后等待FINAL REVIEW
