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
