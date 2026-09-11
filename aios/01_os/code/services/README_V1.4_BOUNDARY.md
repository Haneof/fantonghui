# V1.4 边界标注登记表（迁移纪律 §12.2 / §12.3 / §4.3 / §4.4 的强制执行）

- 生成：2026-09-11 ｜ 依据：`docs/AIOS_Constitution_V1.4-r0.md`（当日批准生效）
- 用途：宪法要求"尚未迁移的旧 Runtime 必须标记为兼容实现，不得被误认为已符合 V1.4"（§12.2）、"已实现的 World State / World Change / Memory / Cognition / Privacy / Interaction 基础可以保留，但必须重新标注其在 V1.4 中的输入输出边界"（§12.3）。本表就是那份标注。
- **本表不修改任何已验收服务的逻辑**（NEXT_TASK 红线：已验收服务逻辑、总线帧协议、三件套 schema 不得改）。逐文件加横幅会污染 19 个已验收文件，故标注集中在此；唯一例外是 `attentiond.py`——宪法 §4.3 亲自点名 P0，必须让打开该文件的人第一眼看到。
- 图例：`KEEP` 保留且合宪 ｜ `COMPAT` 保留但属兼容适配层（新代码不得据其扩展旧语义）｜ `FROZEN` 违宪部分即刻冻结，停止推进 ｜ `SHELL` 空壳待实装 ｜ `P0` 宪法点名的迁移缺口

## 一、基础设施（宪法中立，传输与进程层）

| 载体 | 行数 | 判定 | V1.4 输入输出边界 |
|---|---|---|---|
| `bus/aios_busd.py` | 215 | KEEP | 帧协议 `{t,topic,msg}` 不变（STATUS 冲突 2 裁决）。V1.4 下它是 Observation/Trigger/Inference 共用的传输层，**不得承载语义**——任何"总线上先做筛选"的想法违 §4.1 |
| `aios_sdk/aios_sdk.py` | 162 | KEEP | 服务接入/心跳/收发。§4.3 的 Trigger Window 若需按时间窗取证据切片，走总线查询，不在 SDK 里加逻辑 |
| `aiosd/aiosd.py` | 160 | KEEP | 进程监督 + `services.json` 拉起。V1.4 新增 Runtime（Observation/Timeline/Trigger）只需在此注册，无架构改动 |

## 二、被 §4.4 冻结的部分（本地/廉价层做语义判断 = 即刻停止推进）

| 载体 | 判定 | 冻结依据与边界 |
|---|---|---|
| `services/perceptiond.py` | **FROZEN（语义部分）** | 现实现订阅 `evt.stream` → 补全 `speaker/entities/mode_at_time/privacy_level` → 发 `evt.normalized`，即 V1.2 的"感知层直接输出 Semantic Event"。§11 表第 1 行已改判为「底层先输出 Observation」。**保留**其授权前置检查（隐私丢弃+计数）——那是第十章要求；**冻结**其语义字段补全的扩展。迁移方向：降级为 Observation 采集与机械检测（IMU/VAD/声纹，§2.4），语义交 AI |
| `services/modelrouterd.py` | COMPAT | 本地 llama + 云端池的路由与断网降级（M3 验收✓）保留。但 §4.4 冻结"认知世界本地小模型先行，不够上云"：本地模型**零语义判断**，只可做格式规整/机械配额类工作；凡"小时摘要/意图识别交给 1.5B"一律不得推进 |
| `code/tests/rebuild_pyramid*.py`、`verify_pyramid.py`、`grade_2b_4b.py`、`compare_big_local.py`、`compare_fixed.py`、`llama_probe.py`、`probe_4b_speed.py`、`finish_4b_and_bench.py`、`resume_4b.py` | **FROZEN** | 本地小模型做摘要/打分的脚本，§12.8 点名冻结。已验收的历史证据（`run/benchmark_1.5B.json` 等）保留跟踪不动；这些脚本**不得作为 V1.4 的实现起点**，详见 `../tests/FROZEN.md` |
| `../docs/OS总体架构设计_V0.1.md` | **FROZEN（冲突部分）** | §4.4 + §12.7：L1 事件分类、本地小模型摘要、attentiond"过滤噪音决定是否升级"、"本地先行不够上云"四项设计已冻结；该文档已加横幅，修订合宪前不得据其推进 |

## 三、§12.3 允许保留、但须重标边界的基础

| 载体 | 行数 | 判定 | V1.4 下的重标注 |
|---|---|---|---|
| `services/stated.py` | 689 | COMPAT→KEEP 候选 | 输入边界变了：V1.4 里它是 Global Timeline 的**事实槽位投影**，不再是"Semantic Event → 世界"的第一站；`world_change.json` 三件套 schema 与幂等/陈旧/非法三重防护照用（archive/README §三说明了守恒不变式如何复用到 Observation Store）。缺口：须新增 `observation`/`trigger` 挂载，见登记表下方 |
| `services/memoryd.py` | 288 | COMPAT | 六跳金字塔 + 三树隔离保留（§8.1 原始记忆、§8.3 总结）。三处必改：① 措辞——"压缩"废止，改「全量语义保留 + 多维索引 + 多层观察」（指挥官×PM 裁决 1）；② 每次总结须带 `summary_node_id`/`previous_summary_node_id`/`summary_sequence`（§5.3）；③ 须长出 Event Anchor + Keyword Inverted Index（§8.2/§6）——现在完全没有 |
| `services/cognitiond.py` | 141 | KEEP | `EPISTEMIC_STATES`（KNOWN/INFERRED/HYPOTHESIS/UNKNOWN/CONFLICT）正好是 §5.5 真实度与知识状态的载体，**这块是主线里最合宪的一文件**。缺口：须接受 AI 生成的 Inference Event（§5.2）而非只接 `sys.cognition.assert` |
| `services/decisiond.py` | 173 | COMPAT | 三套非对称阈值 + 介入预算保留。须按 §5.9 AI 介入标准顺序重排（先看自己记忆树 → Attitude → 再看曲线），并把 §13.1 Help-First 与"沉默也是输出"接入 |
| `services/interactd.py` | 120 | KEEP+待补 | 五级介入通道（M3 验收✓）。§9.2 只定契约不实现：震动一次=简单通知、抬腕→文字+语音按钮、贴耳+IMU→骨传导、沉默=输出。补前四条的**语义枚举**即可，不做 UI |
| `services/privacyd.py` | 71 | KEEP+待补 | 授权状态机✓。第十章还要求：用户查看/删除/导出/撤销权、云端只收最小上下文——四项未实装 |
| `services/evolutiond.py` | 294 | KEEP+待补 | `strategy_versions` 版本链是 §4.2-1「阈值由 AI 自主调节、每次留痕、可回滚」的现成载体。两条硬约束须落码：安全底线阈值**永久豁免学习**、Regret 只按「曲线情境签名」沉默同类触发（禁止全局拉黑） |
| `services/entityd.py` | 117 | COMPAT | 现只做 UNKNOWN 占位。§7 Unknown Identity 全局重投影（解析后更新索引与投影、**不改原始观测与原始锚点版本**）是它的正式职责，未开始 |
| `services/hublinkd.py` | 144 | COMPAT | 持久化队列 + kill-9 零丢失（829 条/秒）是 Observation Store 的天然底座。方向：入队对象从 `evt.*` 改为 Observation，按 §1.2 挂到唯一 Global Timeline |
| `simulator/simd.py` + `../../simulator/gen_dataset.py` | 54/110 | KEEP | §3.12 维度注册制：模拟器只是**又一个数据源**，为它改曲线内核即违宪。31,399 条/90 天数据集继续作为曲线验证的真值源，不等硬件 |

## 四、P0：宪法点名的迁移缺口（本表是唯一登记处，不得口头带过）

| # | 缺口 | 宪法条款 | 现状证据 |
|---|---|---|---|
| 1 | `attentiond` 纯租约引擎 → 重写为多维度强制阈值触发器（阈值/方向变化触发、唤醒派发、触发窗口、触发审计四件机械事） | §4.3 明文「重写完成前，任何『租约审核代替触发』一律视为**违宪实现**」；§12.8 列 P0 | 实测该文件 = LeaseEngine 签发/释放/过期扫描，**无阈值、无曲线、无派发**；`grep -rni "Observation\|Trigger\|Inference\|Dimension\|timeline" aios/01_os/code --include=*.py` = **0 命中** |
| 2 | Observation Store + 唯一 Global Timeline（十类对象同轴挂载） | §1.2、§2.1 | 全仓无 `observation` 表/主题；主线只有 `evt.*` 与 `world.*` |
| 3 | Dimension Registry（维度注册表：来源事件类型/打分方式/基线策略三段声明后生效） | §3.1、§3.2 | 无；曲线只有 `run/` 里的基准统计，非运行时对象 |
| 4 | 六类 Trigger（阈值方向/关键词实体/无变化/定时/用户主动/安全） | §4.2 | 只有 `gate_rules.py` 原型在 `tests/`，且硬编码 Windows 路径无法在 Linux 跑 |
| 5 | Inference Event（AI 生成事件 + 真实度 + 知识状态）+ 关键词超链/倒排索引/锚点选择与重投影 | §5.2、§6、§8.2、§8.2.1、§8.2.2 | 无 |
| 6 | 定时任务自治（AI 自己设闹钟、维护闹钟本） | §5.8 | 无调度器 |
| 7 | `safetyd` 空壳（24 行，却是 `always_on: true`）：Safety Trigger 旁路 + 安全底线不受学习放宽 + EMERGENCY 硬规则 | §4.2-6、§10、验收 I | 空壳内容与 `abilityd.py`、`modemgrd.py` 逐字相同（仅服务名不同） |
| 8 | 声纹与说话人解析管线（IMU 判用户、A/B/C 待 AI 解析） | §2.4 | `perceptiond` 里 `speaker="unknown"` 是写死的 |
| 9 | 1000 题架构测试规范 + 本地出题迭代闭环 | §13.4、§13.6 | 旧千题基准是"答题正确率"口径，非 V1.4 的意图/帮助效用心法；须重定义 |
| 10 | `modemgrd` 空壳 | §3.6 | V1.4 把 MODE 降为「日常生活基础维度」之一 → **不再单独实装**，并入 Dimension Registry；本条为"按新宪法作废"而非待办 |

## 五、`core/` 的处置（STATUS 冲突 1、Task 5 任务书留待架构师裁定的那一件）

已按指挥官 2026-09-11「清理与最新宪法不相干的无用文件和代码」裁决，整簇 `git mv` 至 `archive/legacy_core_simulator/`：

- 依据是 §12.4「不得同时在 `core/` 和 `aios/01_os` 复制实现」——保留在活动树里就是持续诱惑第二套实现；
- **未删除、未合并、未复用一行**，归档包自包含且实测可复现（192 tests OK + 三把检查器绿）；
- 主线 `aios/01_os/` 自此为唯一实现线，`schemas/` 亦只剩主线一份（原根目录三份系逐字节重复）。

## 六、标注之后必须发生的事

新任务单见根目录 `NEXT_TASK.md`（已按 V1.4 重写）。**冻结清单外的任何"顺手优化"都属越界**；每个迁移任务须按 §12.6 附实际测试输出、原始错误与未完成项，不得以"测试通过"代替证据。
