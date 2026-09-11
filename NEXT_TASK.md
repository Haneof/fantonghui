# NEXT TASK · V1.4 首批施工单（P0 迁移缺口）

- 签发：Arena Agent ｜ 2026-09-11 ｜ 生效前提：**宪法 V1.4-r0 已批准生效**（见 `docs/AIOS_Constitution_V1.4-r0.md` 文末【生效批准记录】）
- 本单取代 2026-09-10 版（那版三件事：Task 5 复验 / Task 6 收尾 / Curve-Evidence 契约冻结）。取代原因：V1.4 换了主范式，Curve 域已从"待冻结的下一层契约"升格为宪法第三章正文，且宪法 §4.3/§12.8 已点名 attentiond 为 P0
- 上一版遗留处置：任务 A（Task 5 双环境复验）**Linux 半边已签**——`test_s1_t5.py --fast` 18/18、`gate_rules.py` 636 题 100.0% 且结果与 Windows 证据逐字节相同；Windows 半边受新增 C（`taskkill` 依赖）限制，如实留 ❌。任务 B 的广播**已实装**（`stated.py:466` 发 `world.change`），缺验收测试，转为下方任务 D

## 执行纪律（每个任务都适用）

- 一律在 `aios/01_os/code/` 内落地；**不得**在 `archive/` 写代码，**不得**新建第二套总线/schema/时间轴
- §12.6：交付必须附实际命令、原始输出、失败项原文与未完成项清单；只写"测试通过"退回
- 已验收件禁止顺手改：总线帧协议、三件套 schema、`stated.py` 的守恒不变式与 22 项测试、`gate_rules.rule_gate` 的判分口径
- 每任务一个 commit，日志写 `aios/01_os/tasks/logs/`，状态回写根目录 `STATUS.md`

---

## 任务 A · Observation Store + Global Timeline 契约冻结（设计文档，不写业务代码｜1.5 天）

产出 `aios/01_os/docs/10_OBSERVATION_TIMELINE.md`，冻结八项（前三项是地基，后五项定接口）：

1. **Observation 结构**：`obs_id / observed_at / ingested_at / subject_ns / source / device / modality / raw_payload_ref / quality / privacy_level`。`raw_payload_ref` 沿用 03 的唯一引用规则（禁 `raw_data`）；`subject_ns` 承载 §1.1「AI 与用户共享时间轴但主体命名空间不同」
2. **十类对象同轴挂载**（§1.2）：Observation / Dimension Point / Trigger / AI Session / Inference Event / Memory / Task / Action / Outcome / AI Self Update 的 `timeline_seq` 分配与唯一性；**只有一条轴**，任何"局部时钟"违宪
3. **增量总结节点**（§5.3）：`summary_node_id / previous_summary_node_id / summary_sequence` 的落位（memoryd 现有六跳金字塔如何挂节点号而不改层结构）
4. **清洗边界**（§2.2、§2.3）：Normalization 只给可比较表示、不删原始值；只清洗"确定噪声"，可疑不删；原始证据保留期与冷热分层
5. **Data Cleaning Hub**：入口唯一化（模拟器/手机/手环/聊天都只是数据源，§3.12 注册制的前置）
6. **载体选型**：明确复用 `hublinkd` 持久队列（829 条/秒、kill-9 零丢失）作 Observation Store 底座，还是新建 `observedd`；结论必须给出吞吐/丢失/查询三组实测口径
7. **与 `stated` 的关系**：World State 降为时间轴的事实槽位投影（§12.3 保留但重标边界）；`evt.normalized` 兼容层保留、新代码不得以其为唯一输入（§12.2）
8. **Voiceprint 管线接口**（§2.4）：`speaker="unknown"` 从写死改为三态 A/B/C 待解析，与 §7 Unknown Identity 重投影共用一套 ID 演进规则（**重投影不得改原始观测与原始锚点版本**）

- 红线：本任务零模型零网络；不得为 Observation 另建总线协议（走现有帧）；曲线值一律 INFERRED，不得写事实槽位
- 完成后由 PM 审查冻结，才允许任务 B/C 编码

## 任务 B · attentiond 重写（P0，宪法点名违宪件｜2 天）

按 §4.3 只做四件机械事，**删语义、留配额**：

1. 输入：订阅 Observation/Dimension Point 派生的曲线点（任务 A 冻结后接线）；阈值来源 = 个人滚动基线，**禁止全局固定值**
2. 四类判定：`RISING / FALLING / SPIKE / DROP / PERSISTENT / RECOVERY`（§4.2-1）+ Inactivity 平线超时（§4.2-3）；单原始值不得脱离基线上下文触发
3. 唤醒派发 + Trigger Window（本次触发前后时间范围与证据切片引用，不复制证据正文）
4. **Trigger Audit**：每次触发落 `why_fired`（维度/阈值/基线窗口/证据引用），可审计可回滚
5. 租约降级为纯机械配额：保留 `budget_ms/deadline/EXPIRED` 与 `evt.lease.expired`，**删除任何"审核是否值得看"的语义**（现实现本就只发租约，重写后二者不再混名）
6. 六类 Trigger 的接线：Keyword/Entity、Schedule、User、Safety 四类**只做派发**，实现各归其主（`entityd`/`evolutiond`/`interactd`/`safetyd`），attentiond 不吞
- 允许改：`services/attentiond.py`、`tests/test_s2_t1_trigger.py`（新增）、`services.json`
- 禁止改：`aios_busd.py` 帧协议、`gate_rules.rule_gate` 内核逻辑（只许 import 复用）、`stated.py`
- **守门回归（硬门）**：`python3 tests/gate_rules.py` 必须仍 636 题 100.0% 且 `gate_rules_result.json` 逐字节不变；新增 `test_s2_t1_trigger.py` 至少覆盖：①无基线不触发 ②运动语境豁免心率 ③平线超时触发 ④触发审计字段齐备 ⑤零模型零网络 tripwire 计数 0 ⑥重复触发不重复派发
- 状态：Windows 侧不阻塞（本任务全纯规则，Linux 实跑即可）

## 任务 C · safetyd 实装（P0，与任务 B 同批｜1 天）

1. Safety Trigger 旁路（§4.2-6）：摔倒/撞击/严重生理异常/危险环境/长时间无响应 → 绕过曲线与交互偏好直接唤醒
2. **安全底线永久豁免学习**（§4.2-1、§10、NEXT_TASK 旧第 9 条）：`evolutiond` 的 Regret/阈值调节**不得**下调安全阈值——用可执行断言锁死，不是注释
3. 硬规则表落码 + `world.update.rejected` 式的拒绝留痕；EMERGENCY 走独立主题 `safety.emergency`（帧协议不变）
4. 它是三个逐字相同空壳之一，实装后须删掉 `README_V1.4_BOUNDARY.md` 里对应行
- 禁止：不做语义判断、不调模型；安全判定全为确定性规则
- 验收：注入 5 类安全信号 100% 旁路唤醒；人为让 `evolutiond` 放宽安全阈值 → 被断言拒绝并留痕

## 任务 D · 旧尾巴：T6 验收测试（0.5 天，可插队先做）

`world.change` 广播已在 `stated.py:466` 实装但零验收 → 新增 `tests/test_s1_t6.py`：①广播内容与 `world_change` 表逐字段一致 ②重复事件不产生重复广播（幂等）③memoryd/attentiond 各加一条订阅日志证可达（不改其逻辑）。
完成后 `STATUS.md` 第二节 Task 5/6 条目补"已验收"。**先做这个**：成本半天，能立刻关掉一个跨了两个宪法版本的悬案。

## 任务 E · 00-09 → v0.2 修订提案（待指挥官批准后才动手）

`docs/README_V14_CONFORMANCE.md` 已列出条款级 VOID/KEEP/REVISE 清单。v0.2 是**原地升版**（PM 治理裁决 6：禁止另起平行文档集），不得新建编号文档。批准前任何代码任务以宪法为准、不以 00-09 的 VOID 节为准。

---

## 完成后顺序

Observation/Timeline（A）→ Trigger 实装（B）+ Safety（C）→ Dimension Registry 与五维度注册（心率/睡眠/消费/社交频率/深夜指数，全部 SQL 可出）→ Inference Event + 关键词倒排索引与锚点选择（§6、§8.2）→ Unknown ID 重投影（§7）→ 定时自治闹钟本（§5.8）→ 1000 题规范重定义（§13.4）→ 之后才轮到 UI/App/Hardware（§12.5 保持空壳）。

---

# 追加批次（2026-09-11 第二批）：指挥官表述"我要的效果"→ 六项裁定

> 指挥官原话要点：①我们是跑在 Linux 上的操作系统 ②以多维可挂载曲线认知为核心 ③上为 App 服务、下接全部外界数据、持续维护用户世界模型 ④像谷歌框架之于安卓 ⑤**AIOS 不等于曲线这一块，它还包括 UI/交互/设置等整个系统结构** ⑥效果示例：教育 App 里大模型当老师，因为透彻了解用户，用他已经会的东西教，而不是用微积分教只会加减乘除的人。
> 第 ⑤ 点是本轮真正的增量：此前整个项目把 AIOS 当成"L1-L2 底座"，**没有为"系统结构"负责**。

## 裁定

| # | 裁定 | 依据与实测 | 落点 |
|---|---|---|---|
| D1 | AIOS = 跑在 Linux 之上的**用户认知系统服务层**，不是内核、不是曲线模块；分五层 L0-L4 | `docs/01_CORE_ARCHITECTURE.md` V0.2 §1-§2；§3 给出"OS 必备件 17 项：谁提供/谁自建/只定契约"清单 | 01 V0.2 |
| D2 | 19 条散落 `sys.*` 主题升格为**有编号有鉴权的 Syscall 表 v0（22 条）**，App 只能走它 | 实测：`grep -rhoE '"sys\.[a-z._]+"'` = 19 条无版本无鉴权；SDK 只有 `publish()`，App 问不到任何东西 | `aios/01_os/docs/10_AIOS_SYSCALLS_V0.md` |
| D3 | 新增两个**此前完全空白**的子系统：`settingsd`（设置面=用户主权面）与统一审计；配额/保留期进 L0 契约 | `grep -rni "settings\|设置\|audit\|审计\|quota" aios/01_os/code --include=*.py` → 设置 0、审计 0、配额 2（仅租约语境） | 任务 G |
| D4 | 教育场景固化为**验收 K（微积分反例）**，且要求"同模型同模板、只换世界模型，输出必须显著分叉" | 判分器已实装可跑：`bench/check_teaching_fit.py --grade` → 通用大模型式被判 K1 超纲×2 + K4 虚构证据 + K5 冒充事实，K3 极差 2 PASS | `docs/08` V0.2 §K + `code/bench/` |
| D5 | 批一个**只读 Dev 面板**（`aios_console.py`）作为验收夹具，解决"底座看不到效果"；它不是产品 UI，不违反 §12.5 | 实跑真栈（aiosd 起 bus+15 服务 + 播放已验收 G 段同一份 DAY）：在线 15/15、九槽位快照、applied 7 / replay_skipped 14 / rejected 1 合计 22（守恒成立）、L3 源授权 sim=已授权、V1.4 迁移进度红项 | 已在主线 |
| D6 | 负面清单写死：不写内核/驱动/文件系统/网络栈/桌面/输入法/应用商店/多模型编排平台 | 01 V0.2 §9 | 宪法外的执行边界 |

## 任务 F · Syscall 表第一步：SDK 有"问"的能力（1 天）

实测直接证明缺口：本轮写 demo 驱动时，`AIOSService` 无"只发不收"的公开入口，被迫调私有方法 `drv._connect()`（`aios_console` 演示脚本第 12 行注释已记录）。
1. `aios_sdk` 加 `call(name, args, timeout=2.0)` → `{"t":"call"}` + `sys.reply.<name>.<req_id>` 应答；错误码闭集 `E_*`；未连接/超时不得静默成功
2. 表内 8 条"现有/归并"项登记进 `services.json` 旁的 `syscalls.json`（名称→归属服务→是否需授权），加一致性测试：订阅了 `sys.*` 却没登记表内条目 = 失败
3. `test_s1_t5` 类验收从"读快照文件"升级为"走 call()"（新增并行路径，不改老断言）
- 禁止：不新建第二套 IPC；不改总线帧协议

## 任务 G · 设置面与审计（settingsd，2 天）

按 10 号文档 §三 的八组键（维度控制/触发控制/安全例外/记忆控制/AI 人格/隐私上云/配额保留/App 挂载）：
1. 每项 `(key,value,version,changed_by,changed_at,rollback_key)`，与 `evolutiond.strategy_versions` 同构，**不建第二套配置存储**
2. 安全底线项：`settings.set` 直接 `E_AUTH` 拒绝（服务端兜底，UI 灰化只是体验）——同时满足验收 S
3. `consent.export` / `consent.revoke`：撤销后被删记忆不得再被锚点/索引引用，但原始观测与其锚点版本一字不改（验收 Q/M）
4. 审计：每次 call 落 `audit_id`，`aios_console.py` 增一节显示"谁读了什么"（只读面板已有位置）

## 任务 H · 验收 K 接上真答案（随 AI Session 实装）

判分器已可跑（`--selfcheck` 绿）。AI Session（任务 B 之后）能产出 §5.4 结构化输出时：把 `answers_sample.json` 换成真模型产物重跑，**K1-K7 全过才算底座起作用**。桩文本必须删除或明确标 `is_stub=true`，禁止拿桩当验收证据。

## 修正后的推进顺序

D1-D6 已落文档 → **任务 D（半天，关旧尾巴）→ 任务 A（Observation/Timeline 契约）→ 任务 B（attentiond 重写）+ C（safetyd）→ 任务 F（SDK call）→ 任务 G（设置面）**。任务 F/G 不得排在 A/B 之前：没有可设置的运行时对象，设置面就是空壳表单。

---

# 追加批次（2026-09-11 第三批）：App=专业方向的处理环境，认知全在 AIOS

指挥官补充定义：一个教育 App 入口内含数学/化学/英语多条曲线；`interest_app` 教编程时 AI 用数学与英语曲线定教法；
社交/购物/娱乐等任何 App 开发出来即底层数据共通；情绪/压力/思想由 AI 自己注册曲线量化；买车后汽车数据"留好接口"接进来。
据此固化契约 `aios/01_os/docs/11_DIMENSION_MODEL_V0.md`（维度身份四段式、状态机、rubric、Transfer、SourceManifest、治理上限）。

## 任务 I · dimensiond（Dimension Registry + 曲线内核）实装（3 天，排在任务 A 之后）

1. 新服务 `code/services/dimensiond.py` + 独立库 `run/dimensiond.db`：`dim_meta / curve_point / rubric / transfer_belief / dim_proposal / source_manifest` 六表
2. `dim_id = producer/subject/family/axis` 四段式解析与注册制校验；`state ∈ {ABSENT,INSUFFICIENT,LIVE,STALE,SUSPENDED}` 为**必填显式字段**（禁止用 null/缺字段/0 隐式表达未知）
3. 供数只有一条路：`obs.attach → Observation → dimensiond 按 rubric 聚合 → curve_point`。**App 侧不得直接写 value**（违 §9.1 与 11 号文档 §3，评审打回项）
4. 趋势由内核统一算：`delta / direction / slope / span / volatility`（§3.4）；UI 与 App 不得自算斜率
5. 基线一律个人滚动窗口，禁止全局固定值；`rubric_version` 变更必须产生 `series_break` 标记
6. 治理：季度新增 ≤6 / 总量 ≤40、`periodic_exempt` 豁免衰减、`falsify_clause` 自毁、审批走 `evolutiond.strategy_versions`（不建第二套配置存储）
7. `statistical` 类维度必须实现**复算接口**：`recompute(dim_id, window)` 与库内值不一致即报错（不许静默取平均）
- 允许新增：`dimensiond.py`、`code/rubrics/*.md`、`tests/test_s2_t2_dimension.py`
- 禁止改：`stated.py` 的守恒不变式、总线帧协议、`gate_rules.rule_gate` 判分口径
- **验收**（把 docs/08 的判据变成跑得出的测试）：
  `test_s2_t2_dimension.py` 至少覆盖 ①ABSENT 不返回 0 而返回 state=ABSENT ②同一批 obs 两次 recompute 值全等 ③跨 rubric 版本查询必带 series_break ④App 调 `curve.point.write` 被 `E_AUTH` 拒绝 ⑤断供超 grace → state=STALE 且旧值不进入"当前"查询 ⑥Transfer 写回曲线被拒绝 ⑦注册第 41 条维度被上限拦下并给出建议下线项 ⑧零模型零网络 tripwire=0（除 `llm_scored` 类 rubric 走 `sys.model.request` 外，且必须落 basis_obs）
- 同步把判分器接上：`code/bench/check_teaching_fit.py` 的 K8/K9/K10 组已实装并可跑（当前用人工桩验证判分有效；真答案待 AI Session 实装，见任务 H）

## 新增红线（写进 STATUS 第七节同批生效）

> 第四批修订：措辞按**可变性分层**重标（`aios/01_os/docs/12_POLICY_AND_SAMPLING_V0.md` Part A）。
> "红线"这个词只留给 T0 结构不变量——它们是**结构**，不是数值，没有任何"调一调"的余地；
> 凡是数值一律属 T1 政策默认值（可调、可回滚、必须留痕），不得伪装成红线。

- **R1（T0）**：任何 App 计算并上报"用户水平/等级/画像分"= 违宪。App 只报观测，档位由 AIOS 按 rubric 算。
- **R2（T0）**：`ABSENT` 与 `0` 是两个不同的东西。任何"没有数据 → 按最低档处理"的代码路径，一律视为缺陷而非保守策略。
- **R3（T0 原则 + T1 参数）**：AI 自注册的维度必须可证伪（带退出条件）；不能证伪的自造曲线禁止上线。
  「证伪不了」是结构问题；**"几次算证伪"是旋钮**（`falsify_clause` 里的次数走注册表，不写死在 dimensiond）。
- **R4（T0）**：换 rubric 版本必须打断点标记；把跨口径区间的趋势画成连续线 = 对用户说谎。
- **R5（T1，本批新增）**：任何策略性数值未登记进 `code/policies_v0.json`（且无豁免理由）= 打回。
  机械执行器 = `python3 code/policy_scan.py --strict`。这条不是道德要求：它有退出码。
- **R6（T2，本批新增）**：`safety_linked=true` 的旋钮，AI 与自动学习一律无权放宽（`floor==ceiling` 由扫描器强制）；
  用户改可以，必须显式确认 + 看到漏报/隐私代价说明 + 永久留痕。


---

# 追加批次（2026-09-11 第四批）：把"没有任何东西写死"变成可执行的东西

指挥官裁定：**开发过程没有任何东西是写死的，哪怕标记了也可能会改**；总结**按时间段**做一次；触发频率与采集密度 **AI 有权调或设置里调，安全那些除外**。

## 裁定

1. 可变性分三层（T0 结构不变量 / T1 政策默认值 / T2 安全底线），变更协议见 `12_POLICY_AND_SAMPLING_V0.md` Part A。
2. 主动传感器**不许常开**：三层频率（常驻免费 / 按需提频 / 人配合）+ 四道闸门，提频必须由 Trigger 授权 —— Part B。
3. 曲线点密度 ≠ 采样密度：原始流短保留、曲线只存窗口统计；90 天曲线 2.6 万点，AI 一次读完。
4. 省电不得影响安全：`safety.fall_detect_hz` 不给自动区间；漏报风险必须在维度注册时**写出来**（`miss_profile`），不许假装 5 分钟采样能看见 20 秒的心动过速。

## 任务 J · 参数接线（1 天，紧接任务 B/C 之后）

现状诚实刻度：注册表 23 个旋钮**有户口、无人读**（`policy_scan` 明说 `1 个已被代码引用`，那 1 个是判分器）。**接线前"参数可调"这句话是假的。**

1. `services.json` 增 `policy` 段或由 `aiosd` 统一下发；服务侧只准通过一个读取入口取旋钮（禁 self.config 各自解析）
2. 优先替换扫描器已抓到的 3 个常量：`evolutiond.THRESHOLD_LOW/HIGH` → `evolve.tune_floor/tune_ceiling`；`hublinkd.BATCH_WINDOW/BATCH_SIZE` → `bus.batch_window_s/batch_size`
3. 用户覆盖粘住：`settingsd` 写入的用户值优先级高于 AI 值；AI 改不动用户钉住的那一项，只能提申请
4. 热更新语义：每个旋钮按 `hot_effect` 生效，不得要求重启；生效前后各写一条审计
5. 回滚：`evolutiond.strategy_versions` 存快照，一键回到上一个值

验收：`python3 code/policy_scan.py --strict` 退出码 0 且"已被代码引用"≥ 被接线数；
`evolutiond` 夹逼区间改配置后行为跟着变（用 `--replay-jsonl` 固定夹具复算，两侧数字必须不同）；
`hublinkd` 攒批窗口改 0 与 5s 时，实测时延/条数出现预期方向的变化（否则说明旋钮是假的）。

## 任务 K · 占空比执行器（1 天，模拟器先行，不等硬件）

`duty` 执行器：读活跃 Trigger 窗口 → 下发提频/回落指令；`escalate_confirm_s` 防抖、`deescalate_cooldown_s` 冷却；每次变更写 `audit=event`（谁要求、依据哪个触发、预计持续多久）。
模拟器用 `sample.hr_hz` 的倍率模拟提频，**不新增总线协议**；`dimensiond` 注册 L-B 维度时缺 `miss_profile` 直接拒绝。
