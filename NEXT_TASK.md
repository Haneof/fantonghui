# NEXT TASK · Sprint 1 · Task 5 —— Event → World Update

- 签发：总体架构规划与工程审查 Agent ｜ 2026-09-10
- 执行者：本地 Coding Agent
- 前置：Task 4（World State，arena 线交付）不重做；本任务在主线 `aios/01_os/` 内补齐可运行的世界状态载体并实现 Event→World Update 管道
- 状态表依据：根目录 `STATUS.md`

## 1. 目标

让 Canonical 主链的前半段真正跑起来：

```text
Semantic Event（03 规范 JSON）
  → 规范化适配（总线帧 → canonical Event）
  → World State 更新（stated 实装）
  → 持久化 + 确定性回放
```

验收时能演示：注入一份"用户的一天"事件流，World State 随事件正确演化，且**同流重放两次结果逐字节一致**。

## 2. 修改文件范围（允许改/新增）

| 文件 | 动作 | 内容 |
|---|---|---|
| `aios/01_os/code/services/stated.py` | 实装（现为 17 行空壳） | 订阅 `evt.#`；维护 canonical World State（user/location/mode/people/environment/active_situations/active_goals/pending_tasks）；SQLite 持久化（快照+版本）；提供回放接口 |
| `aios/01_os/schemas/event.json` | 新增 | Canonical 03 Event schema（id/timestamp/source/type/content/entities/location_id/confidence/raw_ref） |
| `aios/01_os/schemas/world_state.json` | 新增 | Canonical 03 World State schema |
| `aios/01_os/code/tests/test_s1_t5.py` | 新增 | 本任务验收测试（见 §5） |
| `aios/01_os/tasks/plans/T29_s1_t5_world_update.md` | 新增 | 任务书 + 验收记录 |
| `aios/01_os/code/services/entityd.py` | 仅允许轻量配合 | 事件 `entities` 引用的实体缺位时写入 unknown-entity 占位（不做完整 Identity，那属于后续 Sprint） |

## 3. 禁止修改范围

- 根目录 00-09 Canonical 文档、`AIOS_Constitution_V1.2-r1.md`、`AIOS宪法.md`
- `aios/01_os/code/bus/aios_busd.py`（总线帧协议不动——规范化只在 stated 入口做）
- `aios/01_os/code/aiosd/aiosd.py`（看门狗/编排）
- 已验收服务：memoryd / cognitiond / decisiond / evolutiond / interactd / modelrouterd / hublinkd / attentiond / privacyd / perceptiond
- `run/` 全部运行时数据与 `api_keys.json`
- 任何已存在的测试文件（只许新增，不许改动 test_m0-m3、gate_rules 等）
- 不删除仓库中任何文件（含 arena 遗留内容）

## 4. 设计约束（来自 Canonical，必须遵守）

1. Event 是事实输入，不写 AI 推断（03 绝对规则）。
2. 本任务**零 LLM 调用**——纯确定性代码（04 §7：优先确定性算法）。
3. State 不只存值，要能回答"从什么变成什么"（02 §3）——本任务先保证快照链完整，Delta 输出属 Task 6。
4. 未知实体/未知场景不得丢弃，允许占位并保留证据（03/08-E）。
5. 时间戳一律 canonical ISO8601 格式（03）。

## 5. 测试要求（test_s1_t5.py）

1. **单元**：总线帧→canonical Event 规范化（含缺字段/坏 JSON/重复 id 处理）；World State 各字段的更新规则；未知实体占位。
2. **集成（Canonical 示例日）**：注入 09 文档示例事件流（09:00 到公司 / 09:05 张总进入 / 09:06 谈合同 / 09:08 张总提出降价 / 09:10 用户沉默 / 09:12 打开合同 / 09:15 再次谈价格），校验检查点：`location=公司`、`people 含张总`、`active_situations=合同谈判`。
3. **回放确定性**：同一事件流重放两遍，最终 World State 序列化哈希一致。
4. **回归**：`test_m0.py` `test_m1.py` `test_m2.py` `test_m3.py` `gate_rules.py` 全部保持通过。
5. **双环境**：Windows 与 WSL2（/opt/aios）各跑一遍并记录输出。

## 6. 验收标准（逐条打勾，全过才算过）

- [ ] schemas/event.json、world_state.json 落库且与 03 字段一致
- [ ] stated.py 实装并常驻：总线在线、心跳正常、health.json 中 state=up
- [ ] 示例日检查点全部正确
- [ ] 回放确定性（两遍哈希一致）
- [ ] 回归测试全绿
- [ ] 零 LLM 调用（代码审查确认无模型调用路径）
- [ ] 双环境运行记录写入 T29 验收记录
- [ ] STATUS.md 中本行状态由"未完成（空壳）"改为"已完成"

## 7. 完成后下一任务

**Sprint 1 · Task 6 —— World Change Delta**：在 stated 输出侧增加 `chg_*` 变更对象（change_type/before/after/entities/evidence_events/confidence，03 Schema），广播到 `world.change` 主题。再往后：Task 7 模拟器时间线播放规范化对接（simd.py 已具备回放能力，做 schema 对接即可）。
