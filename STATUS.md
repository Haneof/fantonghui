# AIOS 当前开发状态表（唯一权威状态源）

- 生成：2026-09-11 ｜ 维护者：Arena Agent（依最高指挥官 2026-09-11 裁决执行）
- **对照基准：`docs/AIOS_Constitution_V1.4-r0.md`（本日批准生效，唯一最高实施依据）**
- 上一版基准：V1.3-r0 / V1.2-r1（保留为历史版本，§12.1）
- 本表取代 2026-09-10 版（那版以 V1.2-r1 为基准，其运行时对照表已随宪法换代失效；历史内容见 `git log -p STATUS.md`）
- 规则：本表是唯一状态源 ｜ 禁止依据本表重建项目 ｜ 不重做 Task 4 ｜ 不建第二套实现

## 〇、一句话现状

**宪法已换到 V1.4（Observation → Trigger → AI Interpretation），代码 0% 迁移，但主线资产一件未丢。**
实测凭据：`grep -rniE "Observation|Trigger|Inference|Dimension|timeline" aios/01_os/code --include=*.py` = **0 命中**。

## 一、V1.4 迁移看板（本表是唯一登记处，§12.2 要求）

| # | 缺口 | 宪法条款 | 优先级 | 现状证据（实测，非引用） |
|---|---|---|---|---|
| 1 | `attentiond` 重写：纯租约引擎 → 多维度强制阈值触发器（阈值/方向触发、唤醒派发、触发窗口、触发审计） | §4.3、§12.8 | **P0** | 现 130 行只有 LeaseEngine 签发/释放/0.2s 过期扫描；宪法原文判「违宪实现」 |
| 2 | Observation Store + 唯一 Global Timeline（十类对象同轴） | §1.2、§2.1 | **P0** | 主线只有 `evt.*` / `world.*` 主题，无 observation 表；hublinkd 持久队列是现成底座 |
| 3 | Dimension Registry（来源事件类型/打分方式/基线策略三段声明即注册生效） | §3.1、§3.2 | **P0** | 无。曲线只有 `run/` 里的基准统计，非运行时对象 |
| 4 | 六类 Trigger（阈值方向/关键词实体/无变化/定时/用户主动/安全） | §4.2 | **P0** | 仅 `tests/gate_rules.py` 原型（2026-09-11 已改为可移植，Linux 636 题 100.0%） |
| 5 | `safetyd` 实装：Safety Trigger 旁路 + 安全底线永久豁免学习 + EMERGENCY 硬规则 | §4.2-6、§10 | **P0** | 24 行空壳，内容与 `abilityd.py`/`modemgrd.py` 逐字相同，却挂 `always_on: true` |
| 6 | Inference Event + 真实度/知识状态；关键词超链 + 倒排索引 + 锚点选择/重投影 | §5.2、§5.5、§6、§8.2 | P1 | cognitiond 只有 `sys.cognition.assert` 入口；memoryd 无 anchor/index |
| 7 | 定时任务自治（AI 自己设、自己维护闹钟本） | §5.8 | P1 | 全仓无调度器 |
| 8 | Summary Node 增量总结（`summary_node_id`/`previous_…`/`summary_sequence`） | §5.3 | P1 | memoryd 六跳金字塔有层级无节点号 |
| 9 | Unknown Identity 全局重投影（解析后更新索引与投影，不改原始观测） | §7 | P1 | entityd 只做 UNKNOWN 占位、confidence 0.0 |
| 10 | 声纹与说话人管线（IMU 判用户、A/B/C 待 AI 解析） | §2.4 | P1 | `perceptiond.py` 里 `speaker="unknown"` 是写死的 |
| 11 | 1000 题架构测试规范 + 本地出题迭代闭环（意图/帮助效用心法） | §13.1-13.6 | P1 | 旧千题是"答题正确率"口径；`gate_benchmark` 判分器可复用其形，不可复用其心法 |
| 12 | 数据主权四项（查看/删除/导出/撤销）+ 云端最小上下文 | §10 | P2 | privacyd 71 行只有授权状态机 |
| 13 | `modemgrd`：不再单独实装，MODE 并入维度注册表 | §3.6 | 作废 | 23 行空壳保持原样，不补功能 |
| 14 | `abilityd`：Capability→Permission→Audit 链 | §10 | P2 | 23 行空壳；旧验收 I（越权必须被拦）仍无载体 |

## 二、可保留的已验收资产（§12.3 明确允许，一件没删）

| 资产 | 载体 | 状态 | 实测/历史证据 |
|---|---|---|---|
| 总线 + SDK + 进程监督 | `bus/aios_busd.py` 215 行 / `aios_sdk` 162 / `aiosd` 160 | KEEP | 829 条/秒、kill -9 零丢失（M2.5 封账）；帧协议 `msg{ts,source,content,confidence}` 不变（STATUS 冲突 2 裁决仍有效） |
| Event → World 链路 | `stated.py` 689 行 | KEEP-COMPAT | 2026-09-11 本沙箱实跑 `tests/test_s1_t5.py --fast` → **18/18 通过**，含 `--replay-jsonl` 两遍 state_sha 逐字节一致；六项下落守恒（applied/no_rule/no_slot_change/stale/replay_skipped/rejected 恰好一个） |
| 三件套 canonical schema | `aios/01_os/schemas/{event,world_state,world_change}.json` | KEEP | 与 03 文档逐字节一致（S1 验收锁定）；清理后**全仓只剩这一份** |
| 三棵树隔离 + 六跳金字塔 | `memoryd.py` 288 / `cognitiond.py` 141 | KEEP | 31,032→1 六跳全通；INFERRED 当 KNOWN 被拒（旧验收 G ✓）。cognitiond 的 epistemic 五状态恰好是 §5.5 的载体，**主线最合宪的一文件** |
| 模型可换路由 | `modelrouterd.py` 109 + `api_pool/gemini_pool.py` | KEEP（语义职责冻结） | M3 断网降级 ✓、千题四档实测；V1.4 下本地模型零语义判断 |
| 五级介入通道 | `interactd.py` 120 | KEEP | M3 最低打扰选择 ✓；须补 §9.2 语义枚举 |
| Regret 闭环 + 策略回退 | `evolutiond.py` 294 | KEEP | M3 回退验收 ✓；`strategy_versions` 是 §4.2-1 阈值调节留痕/回滚的现成载体 |
| 门控规则内核 | `tests/gate_rules.py` | KEEP | **2026-09-11 Linux 实测 636 题 100.0%，`gate_rules_result.json` 与 Windows 时代证据逐字节相同** → 跨环境复现成立 |
| 数据集与模拟器 | `simulator/` + 31,399 条/90 天 | KEEP | §3.12 维度注册制下模拟器只是又一个数据源，曲线验证不等硬件 |

## 三、2026-09-11 清理执行记录（指挥官裁决「清理与最新宪法不相干者」）

**手法：全程 `git mv` 归档，零删除；历史可 `git log --follow` 反查。**

| 动作 | 对象 | 依据 | 验证 |
|---|---|---|---|
| 整簇归档 | 根 `core/`(1946 行) `tests/`(192 项) `tools/` `adapters/` `schemas/`(9 份) → `archive/legacy_core_simulator/` | §12.4「不得同时在 `core/` 和 `aios/01_os` 复制实现」；实测 6 份 root schema 被主线引用数 0，3 份与主线逐字节相同 | 归档包自包含复现：**192 tests OK** + `schema_check` SPEC-CONFORMANCE OK + `forbidden_scan` 禁止事项 1-7 通过 + `player.py` 7 事件全 applied |
| 文档去重 | 根目录 00-09（V0.1）+ 根 V1.2-r1 副本 + `AIOS宪法.md`(989 行) + `AIOS_PROJECT_EXECUTION_MASTER_V1.0` + `AIOS_V2.0_WORLD_OS_UPGRADE_SPEC` → archive | 10 份 00-09 与 `docs/` 那份**全部 DIFFERS**（双权威源）；V1.2-r1 两份 `diff -q` IDENTICAL；后三者全仓引用数 0 | `docs/` 为唯一规范文档集；legacy 包内测试仍绿 |
| 报告归档 | 5 份 V1.2 时代 HTML 评审报告 → `archive/reports_v1.2/` | 属 V1.2 评审材料，不参与 V1.4 实施 | DEVLOG 引用链 intact |
| 运行态去跟踪 | `run/` 下 `bus_stats`/`lease_stats`/`privacy_snapshot`/`privacy_state`/`m1_day`/`model_degrade`/`tail_990`/`zai_channel`.json | DEVLOG 2026-09-10 记录「任何实跑都会改写它们」= 脏工作区固定来源 | `git check-ignore` 逐条确认；重写 `.gitignore` |
| 垃圾删除 | `run/bench1k/` 的 `*.bak`、`_dump*`、`_gen_b2.py`（含硬编码路径）、`all_q.txt`、`*_readable.txt` | 派生可再生文件，非证据 | 基准**证据**文件（questions/blind_b*/results*/benchmark_*）14 份全部保留跟踪 |
| 可移植修复 | `gate_rules.py`：Windows 绝对路径 → `__file__` 推导 + 跑批移入 `main()` 可 import | §12.8 重写 attentiond 需要它当守门回归 | 见第二节 |
| 宪法状态位 | V1.4 第 3-4 行 DRAFT → APPROVED + 文末【生效批准记录】 | §1120 生效声明自带的状态机（批准即生效） | **正文逐字节未改**：排除第 3-4 行后 sha256[:16] 前后同为 `5fd1adec64f19e8c`（脚本核验，非声明） |
| 边界标注 | `services/README_V1.4_BOUNDARY.md`（19 个载体逐个 KEEP/COMPAT/FROZEN/SHELL/P0）+ `attentiond.py` 头部横幅 + `tests/FROZEN.md` + `OS总体架构设计_V0.1.md` 冻结横幅 + `docs/README_V14_CONFORMANCE.md` | §12.2、§12.3、§4.3、§4.4、§12.7、§12.8 | 未改任何已验收服务逻辑；`attentiond.py` 只加注释，`py_compile` OK |

## 四、旧冲突清单的结案

| # | 2026-09-10 版冲突 | V1.4 后的结案 |
|---|---|---|
| 1 | 仓库布局双实现（`core/` vs `aios/01_os`） | **已闭合**：§12.4 + 本次归档，`aios/01_os/code/` 为唯一实现线，`core/` 不再存在于活动树 |
| 2 | Schema 字段 `id/timestamp/...` vs 总线帧 `{t,topic,msg{ts,...}}` | **仍有效**：传输帧不动，世界边界用 03 JSON。V1.4 须在同一边界上再加 Observation/Trigger/InferenceEvent 三份 |
| 3 | Wake 四级 vs 三态 IGNORE/LOCAL/ESCALATE | **作废重判**：四级命名整体作废，改 §4.2 六类 Trigger；`gate_rules` 的三态输出改为触发/沉默 + 触发原因，不再叫 Wake 分级 |
| 4 | 宪法双文件（V1.2-r1 与 989 行版并存） | **已闭合**：V1.4 为最高权威，V1.3/V1.2 为历史版本，989 行版进 `archive/superseded_docs/` |
| 5 | 「Task 4 已交付」vs 主线 stated 空壳 | **已闭合**：stated 689 行实装 + 18/18 复验通过；不重做 Task 4 的红线保留 |
| 新增 A | 00-09 仍是 V1.2 措辞，与新宪法冲突 | 不重写、不改写；以 `docs/README_V14_CONFORMANCE.md` 做条款级 VOID/KEEP/REVISE 索引，待指挥官批准 v0.2 原地升版 |
| 新增 B | 《OS 总体架构设计 V0.1》四项设计被 §4.4 冻结 | 已在该文档顶部加冻结横幅；修订合宪前不得据其推进（§12.7） |
| 新增 C | 主线 `test_m0…m35` 依赖 `taskkill`（Windows-only） | 未越界修改（属"改动已验收裁判"）。**后果如实登记：M0-M3.5 的验收在 Linux/WSL2 不可复现**，"双环境"只能对 `test_s1_t5.py` 与 `gate_rules.py` 签字。修法见 `tests/FROZEN.md §三` |
| 新增 D | Qwen3.5-4B × llama.cpp 0.4.0 兼容性挂起 | 维持挂起，且 V1.4 下**不再追加投入**（§4.4：本地模型零语义判断，千题 2B 31.1% 已证伪该路线） |

## 五、阻塞清单

| 项 | 类型 | 影响 |
|---|---|---|
| GitHub git 协议间歇性连接重置 | 运维 | 推送需重试；不影响本地 |
| 上述新增 C（Windows-only 裁判） | 技术债 | 阻塞"双环境"签字；解除须指挥官批准改裁判 |

## 六、下一个实际开发任务

→ 见 `NEXT_TASK.md`：**P0-1 Observation Store + Global Timeline 契约**，与 **P0-2 attentiond 重写（§4.3）** 同批推进（重写触发器必须先有可扫的曲线/时间轴）。

## 七、红线重申（V1.4 版）

1. 不重做 Task 4/Task 5（已验收）；
2. 不建第二套实现：新 Runtime 只能有一个 Owner，且必须在 `aios/01_os/code/` 内（§12.4）；
3. 不批量删除主线文件；归档区 `archive/` 只读，不得往里写新代码；
4. 不改宪法正文（V1.4 生效只动状态行，须留哈希凭据）；
5. 底层零语义：本地/廉价层不得做语义分类、摘要、意图识别（§1.3、§4.4）；
6. 安全底线不受学习放宽、EMERGENCY 永久豁免 Regret 反馈（§4.2-6、§10）；
7. 曲线值 = INFERRED，永不写 World State 事实槽位；
8. UI / App / Hardware 在底层闭环与 1000 题冻结前保持空壳（§12.5）；
9. 每个迁移任务必须附实际测试输出、原始错误与未完成项，不得以"测试通过"代替证据（§12.6）。
