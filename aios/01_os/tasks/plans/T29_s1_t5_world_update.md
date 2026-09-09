# T29 · Sprint 1 Task 5 —— Event → World Update → World State 进入主线 `aios/01_os`

- 签发依据：指挥官任务（2026-09-10）+ 根目录 `STATUS.md` §六 / `NEXT_TASK.md`（Sprint 1 Task 5）
- 执行者：AIOS Implementation Agent（Arena 会话分支 `arena/01a086b3-fantonghui`）
- 定位：**吸收能力，不复制体系**。把 arena 线已验证（192 项测试）的 World/State 能力收进主线 `stated`，
  不新建第二套 World Runtime，不搬 `core/` 目录结构。

## 1. 审计结论（按真实代码，不按文件名）

| Simulator（arena 线，已验证） | 主线载体 | 审计事实 | 判定 |
|---|---|---|---|
| `core/perception/perception_runtime.py`（原始信号→语义事件） | `services/perceptiond.py` | 已实装：授权检查 + 字段补全 → `evt.normalized`；**不做语义分类**（语义在 arena 线由 `core/perception/semantics.py` 承担） | 存在但不等价；属感知层，本任务不改（见冲突 1） |
| `core/event/event_runtime.py`（校验/排序/去重/持久化） | `services/hublinkd.py` + `bus/aios_busd.py` | 已实装：入口先落盘 `entry_queue.db` 后转发，启动重放，24h 保留；**无去重/窗口聚合/排序** | 存在，语义不同（至少一次投递）。本任务不补 Event 去重（STATUS 已排入 Sprint 2；禁止重做 Task 4）。World 侧只需自我防护=幂等 |
| `core/world/world_runtime.py` | `services/stated.py` | 23 行空壳，全仓 `grep -rn "world" code/services/*.py` = **0 命中** | **不存在** → 在 `stated` 内补齐（任务第二阶段 C 分支） |
| `core/world/state_runtime.py` | `stated` 内部（同一文件） | 空壳 | 不存在 → 吸收为快照/版本/diff 逻辑，不新增第三个服务 |
| `core/world/entity_runtime.py` | `services/entityd.py` | 23 行空壳 | 不存在 → 仅"轻量配合"：UNKNOWN 实体占位，不做身份推断 |
| `tools/simulator/player.py` | `code/simulator/simd.py` + `scripts/*.json` | 已实装：剧本回放（`ts=0` 自动填时间、`id` 空自动 uuid） | 存在且等价（播放能力）。复用，不新建第二个播放器 |
| `tools/mini_jsonschema.py` | 无（主线契约 §1 要求仅标准库） | — | 吸收"用 schema 校验"的能力：在 `stated.py` 内实现最小校验器，**不 import arena 线的 tools/** |
| `schemas/{event,world_state,world_change}.json` | `aios/01_os/schemas/*.proto.md` + 无 JSON | 主线只有 proto.md，且 `event.proto.md` 自称 Event 唯一权威 | 按 `NEXT_TASK` 落 JSON；三份文件是 canonical 的**逐字节副本**（`test_s1_t5.S1` 锁死），避免第二套定义 |
| `core/attention/*`（Relevance/Attention/Wake） | `attentiond` / `modelrouterd` | 部分完成（租约 v0 / 路由 v2） | **本任务禁止接入**：World 更新链路零模型 |

**重复实现（D 分支）核查**：主线内不存在第二套 World/State 实现；`entityd` 与 `stated` 原为逐字相同的空壳模板。
→ **无需删除或停用任何实现**，本任务删除文件清单 = NONE。

## 2. 实装内容

### 2.1 `code/services/stated.py`（空壳 → 实装）

- **入口**：订阅 `evt.#`（`NEXT_TASK` §2 要求）。`on_bus_frame()` 做**总线帧 → Canonical 03 Event** 的规范化：
  `ts(unix)` → ISO8601（固定 `+00:00`，不依赖机器时区，保证回放确定性）；`location_id` 只取事件自带证据
  （显式 `location_id`，否则 `entities` 里的 `place_*`），**不猜**；`raw_ref` 缺省指向 `aios://entry_queue#<id>`
  （hublinkd 入口队列行，24h 保留，符合 03"短生命周期原始引用、不表示长期存音频"）；主线独有字段
  （`speaker/mode_at_time/privacy_level`…）一律留在 context，**不进 Event 本体**（`event.json`
  `additionalProperties:false`）。
- **规则表 `RULES`**：与 arena 线已验证的确定性映射一致（arrival/person_enter/departure/
  contract_discussion/price_negotiation/silence/document_open/task_assigned/task_done/goal_set/goal_done）。
  零模型、零网络、零文本相似度；任务/目标的值只取 `task_*`/`goal_*` 实体 id，不解析自由文本。
- **World Update 边界对象**：`{id, rule, source_events, window, slots, trace}` + `validate_world_update()`：
  无证据拒绝、未知槽位拒绝、槽位值按 `world_state.json` 逐字段校验、`mode` 限宪法 §5.1 九种。
- **12 项能力落点**：
  | # | 要求 | 实现 |
  |---|---|---|
  | 1 | 时间更新 | 仅"真的应用了"才推进 `state.timestamp`（被拒/无变化不倒灌时间） |
  | 2 | location | `LOCATION_ARRIVAL/DEPARTURE` |
  | 3 | MODE | 规则给出；且**优先消费**事件 `mode_at_time`（docs/OS §S3：MODE 由 modemgrd→stated） |
  | 4 | people/entities | `PARTICIPANT_ENTER/LEAVE` + `entityd` 占位 |
  | 5 | activity/situation | `CONTRACT_DISCUSSION` → `active_situations` |
  | 6 | task/goal | `TASK_ASSIGNED/CLOSED`、`GOAL_OPENED/CLOSED` → `pending_tasks`/`active_goals` |
  | 7 | before/after | `world_change.before_json/after_json`（`StateRuntime.diff` 等价逻辑，只含真变化的槽位） |
  | 8 | event evidence / traceability | `evidence_events` + `verify_traceability()`（每个 change 的证据必须出现在 `applied_event`） |
  | 9 | idempotency | `applied_event(event_id PRIMARY KEY)`：同一 Event 只改世界一次；跨重启仍成立 |
  | 10 | stale protection | 早于当前快照时间戳 → `stale`，世界不倒退 |
  | 11 | invalid-event protection | `schemas/event.json` 校验 + 空 id + 时间戳不可解析 + Raw Signal 直喂 → `rejected`，状态一字不动且留痕 |
  | 12 | 不写 Cognition/Memory/Growth | `FORBIDDEN_SLOTS` 显式拒绝（9 个键）+ 库层面只写 `run/world_state.db`（`trees.sql.md` 隔离铁律 1/2） |
- **持久化**：SQLite WAL（`run/world_state.db`）四张表 `world_state(version,ts,ts_s,state_json,state_sha)` /
  `world_update(台账)` / `world_change` / `applied_event`。原子写入：一次应用 = 一个事务（快照+change+台账+幂等标记）。
  同时原子替换 `run/world_state.json`（docs/OS §3.2"内存 + 快照文件、毫秒级常备"给 AI 工作包 B 段读）。
- **下落 closed set**：`applied / no_rule / no_slot_change / stale / replay_skipped / rejected`，
  `verify_conservation()` 保证"每次尝试恰好一个下落、applied 台账 == change 行数 == 快照版本"。
- **回放接口**：`python services/stated.py --replay-jsonl <file>` —— 同一份事件流跑两遍，比对 `state_sha`。
- **常驻语义**：沿用 SDK 心跳/限频日志；`aiosd` 无需改动（`services.json` 里已有 stated 条目，order=2）。

### 2.2 `code/services/entityd.py`（仅轻量配合）

`run/entity_store.db`：事件 `entities` 引用到但库中没有 → 写 UNKNOWN 占位（`kind` 按 id 前缀粗类，
`name=null`，`confidence=0.0`，`refs` 计数，`evidence` 留最近 20 条 event id）。
已存在的行**不覆盖身份字段**（身份解析属 Identity/Cognition，绑定永远是推断：02 §5、宪法 6.2）。

### 2.3 新增 schema 文件（逐字节副本，非新定义）

`aios/01_os/schemas/{event,world_state,world_change}.json` —— 与 canonical `schemas/*.json` 完全一致，
由 `test_s1_t5.S1` 断言"逐字节相同"，任何漂移即红。**没有**新增第二套 Event 结构定义。

### 2.4 发布主题登记（`tasks/contracts.md` 是冻结契约，本文件只做登记，不改它）

| 主题 | 方向 | 载荷 |
|---|---|---|
| `world.state.updated` | stated → 下游 | `{version, ts, state_sha, changed_slots, event_id}` |
| `world.change` | stated → 下游 | 03 World Change 对象（`NEXT_TASK` §7 预告的主题，本任务已具备产出能力） |
| `world.update.rejected` | stated → 运维/测试 | `{event_id, code, detail}` |

命名刻意不带 `evt.` 前缀，因此现有任何订阅 `evt.#` 的服务都不会被新流量影响（已核对 15 个服务的订阅表）。

## 3. 验收记录（2026-09-10，Linux 沙箱，`python3`）

复现命令：
```
cd aios/01_os/code && python3 tests/test_s1_t5.py            # 22 项，含真总线集成
cd aios/01_os/code && python3 services/stated.py --replay-jsonl <day>.jsonl
cd aios/01_os/code && python3 aiosd/aiosd.py                 # 实跑栈，看 run/health.json
```

| 验收项 | 结果 | 证据 |
|---|---|---|
| `schemas/event.json`、`world_state.json` 落库且与 03 字段一致 | ✅ | 三份 JSON 与 canonical 逐字节一致（S1 PASS）；`event.json` 9 字段与 03 相同（S2 PASS）；`stated` 启动自检 schema 字段集合 |
| `stated.py` 实装并常驻：总线在线、心跳正常、health.json 中 state=up | ✅ | 实跑 `aiosd`：`bus up`，**15/15 服务 up**，`stated {"state":"up","restarts":0,"last_hb":1.4s 前}` |
| 示例日检查点全部正确 | ✅ | `location={id:place_004}`、`people=[person_017]`、`active_situations=[negotiation]`、`mode=WORK`、`user={talking:true,topic:price}`、`timestamp=09:15:00` |
| 回放确定性（两遍哈希一致） | ✅ | B/G：`world_change` v1..v7 与 arena 线一致；R1：`--replay-jsonl` 两遍 `state_sha` 相同 |
| 回归测试全绿 | ⚠️ 部分（环境所限） | 主线 `test_m0..m3/m35` 依赖 Windows `taskkill`，`gate_rules.py` 里 `ROOT` 是**硬编码的 `C:\Users\Administrator\...` 绝对路径** → 本 Linux 沙箱无法原样运行。已做等价核查：① `run/logs`、`socket` 直连扫描（A4 等价）由 G 段实跑覆盖；② `py_compile` 全部 15 个服务；③ arena 线 192 项测试 + 禁止扫描器全绿（Core 侧一行未改）。**需指挥官在 Windows/WSL2 补跑一次** |
| 零 LLM 调用 | ✅ | I1：`stated.py` 的 import 闭包 = `{copy,datetime,hashlib,json,os,sqlite3,sys,threading,time,aios_sdk}`，无网络/模型；I2：把 `socket.socket/create_connection` 换成触网即炸的 tripwire 后跑完整天事件流，调用计数 0，`expensive_model_call_count=0`；实跑栈期间 `modelrouterd` 未被 `stated` 触发（stated 不发 `sys.model.request`） |
| 双环境运行记录 | ❌ 未完成 | 本沙箱只有 Linux。**Windows 侧未验证**，不假装通过；`.ps1` 启动脚本未改动，预期可直接用 |
| `STATUS.md` 本行状态由"未完成（空壳）"改为"已完成" | ⏸ 未执行 | `STATUS.md`/`NEXT_TASK.md` 只存在于 `aios` 分支根目录，本会话被固定在 `arena/01a086b3-fantonghui`（其中无此文件）。为避免造出第二份状态表，**不新建不改动**，请指挥官在 `aios` 分支更新本行 |

额外实跑证据（真栈、非 mock）：`simd` 播放 7 条事件后
`world_update` 台账 = `applied 7 / replay_skipped 26`，`world_change` 仍只有 7 条、`applied_event` 7 行。
这 26 次是主线"至少一次投递"的真实重复（`evt.sim.*`→`evt.stream`→`evt.normalized` 三路 + hublinkd 启动重放），
**世界一次都没被重复改写** —— 正是本任务第 9 项能力的现场验证。

## 4. 冲突与待裁决（只标记，未擅自处置）

1. **语义类型词表归属**：`03` 的 `Event.type` 是自由字符串，主线权威枚举是 `schemas/event.proto.md` 的
   `SPEECH/MOTION/VITAL/…`，而世界规则需要 `arrival/person_enter/…` 这类语义类型。arena 线由
   `perception/semantics.py`（正则）产出；主线 `perceptiond` 目前只做字段补全。**stated 内不复制那套正则**
   （否则就是第二套语义分类 + World 越权判断）。因此主线目前必须由**事件源自带语义 type**（simd 剧本、
   未来的真实感知通道）驱动。请裁决：语义分类落 `perceptiond`（推荐）还是单列 classifier 服务。
2. **持久化介质**：docs/OS §3.2 写"内存 + 快照文件"，`NEXT_TASK` §2 写"SQLite 持久化（快照+版本）"。
   本实装两者都做（DB 为真相源 + `run/world_state.json` 原子快照）。请确认是否将"快照文件"从架构文档里
   正式改为"DB + 派生快照"。
3. **`World Change` 提前产出**：`NEXT_TASK` §7 把它排到 Task 6。指挥官任务书要求 before/after 与证据可追溯，
   故本任务已在 `stated` 内产出 `world_change` 表并发布 `world.change`。若要求严格分期，可保留产出、
   暂不发布主题（一行开关），请裁决。
4. **主线测试脚本的可移植性**：`test_m0..m3` 用 `taskkill`、`gate_rules.py` 硬编码 Windows 绝对路径
   → Linux/WSL2 无法原样跑。属"已存在测试文件"，本任务禁止修改，仅登记。（`test_s1_t5.py` 刻意只用
   可移植 API，两边都能跑。）
5. **MODE 双源**：`stated` 规则会写 `mode`，而 modemgrd（空壳）才是 MODE 引擎。当前实现让事件自带的
   `mode_at_time` **优先于**本地规则。modemgrd 实装后是否完全取消 stated 的 mode 规则？请裁决。
6. **忽略规则修正**：`aios/.gitignore` 里 `run/health.json` 是锚定在 `aios/` 的相对路径，匹配不到实际产物
   `aios/01_os/code/run/health.json`。本任务新增 `**/run/{world_state.json,entry_queue.db,entity_store.db,health.json}`
   把新产物的运行期数据排除在版本库外（不改任何已跟踪文件）。

## 5. 下一步

Task 6（World Change Delta 正式化：`world_change` 的窗口聚合与下游消费）→ Task 7（simd 剧本与
Canonical Event 的完整对接）→ Sprint 2（`hublinkd` 侧去重/窗口聚合，届时 `stated` 的 `replay_skipped`
计数应显著下降，可作为"重复在源头被消解"的度量）。
