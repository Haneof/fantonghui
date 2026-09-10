# AIOS 宪法 V1.3-r0 —— World Cognition OS（世界认知操作系统）

> 版本：V1.3-r0  
> 状态：新架构修订生效草案  
> 上一版本：V1.2-r1（保留为历史版本，不删除）
> 补齐记录：2026-09-10 按冻结清单补齐日常生活基础维度、触发命名、AI 自我状态更新与 Help-First / Intent-First 评估宪章；版本号不变，仍为 V1.3-r0。

## 文件定位

本文件修订 AIOS 的底层数据流、触发机制、记忆生命周期和 AI 认知边界。V1.2-r1 仍作为历史归档；自本版本起，新增代码和新 Runtime 必须遵守本文件。尚未迁移的旧 Runtime 必须标记为兼容实现，不得被误认为已经符合 V1.3。

规范数据流为 Observation → Trigger → AI Interpretation（观测→触发→AI 解读）：底层只负责证据，AI 负责解读。

本版本的核心判断是：

> 底层系统只负责完整收集、清洗、保存和按时间排列证据；AI 负责从被触发的证据中理解世界、生成事件、建立关系、形成总结并更新自己的认知。

---

# 第一章：AIOS 的新定义

## 1.1 AIOS 是什么

AIOS（AI-native Operating System，AI 原生操作系统）是一个持续维护用户世界时间轴、状态维度、历史关系和 AI 自身认知的系统底座。

它不是聊天机器人，也不是某个模型的外壳。模型只是 Cognitive Engine（认知引擎），AIOS 才是身份、记忆、时间、关系、策略和应用共享的主体。

## 1.2 唯一全局时间轴

系统只有一条唯一全局时间轴 Global Timeline（全局时间轴）。以下对象必须挂在同一条时间轴上：

- Observation（原始观测）
- Dimension Point（维度节点）
- Trigger（触发记录）
- AI Session（AI 会话）
- Inference Event（推断事件）
- Memory（记忆）
- Task（定时任务）
- Action（行动）
- Outcome（结果）
- AI Self Update（AI 自我更新）

AI 和用户共享同一时间轴，但使用不同的 Subject Namespace（主体命名空间）。

## 1.3 不允许底层预先替世界下结论

底层数据采集、清洗、归一化和曲线更新不得承担复杂语义判断。

底层可以判断：

- 数据格式是否合法
- 时间是否合法
- 数值是否超过机械阈值
- 关键词是否命中注册表
- 是否到达定时点
- 是否命中安全硬规则

底层不得自行判断：

- 这是不是谈判
- 这是不是焦虑
- 这是不是家庭冲突
- 这是谁的生日
- 用户到底想表达什么
- 两件事之间是否存在复杂关系

这些判断由 AI Session（AI 会话）完成。

---

# 第二章：Observation First（先观测，后认知）

## 2.1 Observation（原始观测）

系统底层首先保存 Observation（原始观测），而不是直接生成语义 Event（事件）。

原始观测至少包含：

```text
observation_id（观测 ID）
timestamp（时间）
source（来源）
modality（模态）
payload（原始内容或结构化值）
speaker_id（说话人 ID，可未知）
provenance（来源链）
privacy_level（隐私级别）
```

示例：

```text
心跳 = 18
IMU = 周期性大幅运动
语音转写 = “加油！加油！”
环境描述 = “体育场”
speaker_id = unknown_001
```

这些数据本身不等于“运动会事件”。

## 2.2 Data Cleaning（数据清洗）

清洗只处理：

- 格式
- 去损坏
- 时间统一
- 重复采样
- 单位统一
- 来源授权
- 数据完整性

清洗不得把未经 AI 判断的内容伪装成事实事件。

## 2.3 Raw Evidence Lifecycle（原始证据生命周期）

数据进入系统后，AI 负责对其进行归类：

```text
CONFIRMED（已确认）
INFERRED（推断）
UNCERTAIN（不确定）
USELESS（当前无用）
```

规则：

- 完整证据链必须先被保留，直到本次 AI 认知处理完成。
- 已确认且具有长期价值的语句、事实和证据永久保留，除非用户删除。
- 不确定对象必须保留独立 ID 和不确定标记。
- 当前无用的数据可以在完成引用、隐私和审计处理后删除。
- 删除无用数据不得删除已保留事实的 provenance（来源链）。

---

# 第三章：Dimension（可挂载维度）

## 3.1 维度不是固定列表

Dimension（维度）可以来自：

- 外部传感器
- 手机或设备
- 第三方 App
- 用户主动输入
- AI 推断
- AI 自身状态
- 定时任务和执行结果

示例：

```text
heart_rate（心率）
vehicle_usage（车辆使用）
energy_usage（用电）
learning_progress（学习进度）
stress_estimate（压力估计）
relationship_activity（关系活跃度）
ai_intervention_acceptance（AI 介入接受度）
```

## 3.2 Dimension Registry（维度注册表）

每个维度必须注册：

```text
dimension_id（维度 ID）
owner（所有者）
source（来源）
subject（主体）
value_type（值类型）
unit（单位）
privacy_level（隐私级别）
provenance_policy（来源策略）
lifecycle（生命周期）
```

任何 App 可以挂载新维度，但不得建立自己的第二套用户记忆、时间轴或 Wake Runtime。

## 3.3 Curve Point（曲线节点）

每个维度在时间轴上产生节点。原始值和用于比较的表示必须同时保留：

```text
dimension_id（维度）
timestamp（时间）
raw_value（原始值）
normalized_value（归一化值）
unit（单位）
confidence（置信度）
source（来源）
observation_refs（观测引用）
```

Normalization（归一化）不是删除原始数据，也不是把所有数据变成事实判断；它只是把不同单位转换成可比较的相对表示。例如把“每天消费 200 元”转换为“高于个人近期基线”，但原始金额、单位和计算方法仍必须保留。

## 3.4 Direction and Trend（方向与趋势）

具体数值不是主要触发依据。Trigger（触发器）主要观察维度相对于自身历史的变化方向：

```text
RISING（上升）
FALLING（下降）
STABLE（稳定）
SPIKE（突增）
DROP（突降）
PERSISTENT（持续偏离）
RECOVERY（恢复）
```

系统必须记录：

```text
previous_value（上一节点）
delta（变化量）
direction（变化方向）
slope（变化斜率）
duration（持续时间）
volatility（波动程度）
```

例如心跳 `8 → 9 → 7 → 18`，不是因为“18”这个数字天然有意义，而是因为曲线出现了相对个人历史的突增。阈值可以作用于方向、斜率、持续时间和变化幅度；单个原始值不得脱离上下文直接代表复杂事件。

## 3.5 Cleaning and Complete Dialogue（清洗与完整对话）

Data Cleaning（数据清洗）只删除或标记明确的采集噪声，例如纯咳嗽、环境杂音、重复采样和损坏片段。它不得因为内容暂时无意义而删除完整对话。

完整对话、说话人、时间和上下文必须先进入原始证据链。对话是否重要、是否属于某个关系、是否包含情绪和压力，只能由 AI 在被触发后判断。

情绪、压力、孤独感等不能被本地系统冒充成客观事实。它们只能在 AI 判断后作为 AI Inferred Dimension（AI 推断维度）写入，并必须保留证据、置信度和生成会话。

## 3.6 日常生活基础维度

日常生活基础维度是每个 AIOS 实现出厂必须提供的最小维度集合。它们描述用户每天必然产生的状态变化，是曲线方向比较、个人基线建立和无变化触发的前提。没有这组维度，系统无法判断“今天和平时不一样”。

必须提供的日常生活基础维度至少包括：

```text
生理/健康：heart_rate（心率）、sleep（睡眠）、activity（活动量）
位置/移动：location（位置）、mobility（移动状态）
作息/活动：daily_routine（作息）、work_rest（工作与休息）
社交/沟通：social_frequency（社交频率）、relationship_activity（关系活跃度）
消费/财务：spending（消费）、income_event（收入事件）
工作/学习投入：work_study_time（投入时长）、learning_progress（学习进度）
环境/情境：environment（环境）、noise（环境噪声）
日程/承诺：schedule（日程）、commitment（承诺）
情绪/压力（AI 推断维度）：stress_estimate（压力估计）、emotion_estimate（情绪估计）
交互/介入接受度：ai_intervention_acceptance（AI 介入接受度）
```

规则：

- 日常生活基础维度必须全部挂在唯一全局时间轴上，并为每个用户建立个人基线；禁止使用全局固定值代替个人基线。
- 日常生活基础维度必须支持曲线方向变化触发和无变化触发；长期无更新的维度必须可被静默巡检发现，不得静默失效。
- 新增维度不得替代或复制日常生活基础维度，只能通过 Dimension Mount（维度挂载）扩展；维度数量受注册审批与热值生命周期约束，但带时间锚定豁免的维度（生日、纪念日等低频高价值维度）不得被热值衰减误杀。
- 情绪、压力等 AI 推断维度只能由 AI 在证据充分后写入，底层不得冒充为客观事实。

---

# 第四章：Trigger（触发器）

## 4.1 Trigger 只负责唤醒，不负责主观判断

Trigger Runtime（触发运行时）的职责只有：

```text
检测机械条件
记录触发原因
唤醒 AI
提供触发窗口
```

Trigger 不负责决定“这个事情是否有意义”。意义由 AI 在唤醒后判断。

## 4.2 六类触发

### 1. Threshold / Curve Direction Trigger（阈值/曲线方向变化触发）

心率、消费、位置、学习、设备状态等曲线达到机械阈值或出现方向变化。触发依据以曲线方向变化触发为主：RISING / FALLING / SPIKE / DROP / PERSISTENT / RECOVERY 等相对个人历史的方向、斜率、持续时间和变化幅度；单个原始值不得脱离上下文直接触发复杂事件判断。

### 2. Keyword / Entity Trigger（关键词/实体触发）

语音转写或文本中命中已注册的人物、地点、物品、意图、承诺、风险和领域词。

### 3. Inactivity Trigger（无变化触发）

一段时间内没有重要维度变化，达到用户个性化的安静窗口或陪伴窗口。

### 4. Schedule Trigger（定时触发）

生日、纪念日、保养、还钱、接人、考试和用户要求的提醒时间到达。

### 5. User Trigger（用户主动触发）

用户主动触发：用户说话、抬腕、按键、手势或主动打开应用。用户主动发起无需学习门槛，直接唤醒 AI。

### 6. Safety Trigger（人身安全触发）

摔倒、撞击、严重生理异常、危险环境和长时间无响应可以绕过普通曲线，直接进入 Safety Runtime（安全运行时）。

## 4.3 attentiond 的新边界

attentiond（注意力服务）在 V1.3 中不得承担主观 Relevance（相关性）判断，不得决定“这个事件值不值得 AI 看”。

它的核心职责改为：

```text
Threshold / Curve Direction Trigger（阈值/曲线方向变化触发）
Wake Dispatch（唤醒派发）
Trigger Window（触发窗口）
Trigger Audit（触发审计）
```

Lease Runtime（算力租约运行时）只负责资源预算和回收，不负责语义判断。

---

# 第五章：AI Session（AI 认知会话）

## 5.1 AI 根据任务选择读取范围

AI 拥有完整历史读取权限，但不要求每次读取全局。

AI 可以根据任务选择：

- 当前触发窗口
- 某条维度曲线
- 某个人物或实体
- 某个关键词
- 某个 Event Anchor（事件锚点）
- 某段历史
- 多年人生趋势
- 全局人生时间轴
- AI 自己过去的判断和结果

读取范围由当前任务决定，不允许固定成“每次都看全局”或“永远只看最近窗口”。

## 5.2 AI 生成事件

规范数据流为 Observation → Trigger → AI Interpretation（观测→触发→AI 解读）。只有 AI 结合证据后，才生成 Inference Event（推断事件）：

```text
Observation（原始观测）
  ↓
Trigger（机械触发）
  ↓
AI Session（AI 认知会话）
  ↓
Inference Event（推断事件）
  ↓
标签 / 关系 / 任务 / 认知 / 行动
```

AI 生成的事件必须包含：

```text
event_id（事件 ID）
time_window（时间窗口）
supporting_observations（支持观测）
trigger_id（触发 ID）
epistemic_status（知识状态）
confidence（置信度）
generated_by（生成会话）
```

例如：

```text
心跳升高 + IMU 运动 + 体育场 + “加油”
→ AI 判断：用户可能正在参加体育运动
```

这不是修改原始观测，而是新增一个带证据的推断事件。

## 5.3 AI 不必从零重复总结

AI 每次总结必须优先读取：

```text
上一次总结节点
+
上一次总结之后的新观测
+
新命中的关键词/实体/定时任务
+
必要的历史锚点
```

没有新的触发、变化或关键词时，不重新从头扫描全部人生，也不重复生成同一总结。

## 5.4 AI Session Output（AI 会话完整产出）

AI 每次执行任务过程中或任务结束后，不只更新一个判断。它必须根据本次任务实际涉及的内容，检查并可更新：

- 当前事件总结和标签
- 事件的真实度判断与 epistemic status（知识状态）
- 未知人物、物品和地点的 ID 解析
- 关系网络和人物整体脉络
- 相关历史锚点和关键词超链
- 上一次认知中的错误或冲突
- 用户的情绪、压力、意图等 AI 推断维度
- 用户对提醒和交互的接受程度
- 下一次交互策略
- 新发现的维度、关键词和定时任务候选
- AI 自己对用户的理解、关系态度和判断经验

不是每次都必须更新所有字段；但 AI 必须检查哪些字段受到本次证据影响，并留下“未改变”的结果，避免看似完成却没有核对关系和历史。

每次总结必须拥有递增的 Summary Node 编号（Summary Node ID）：

```text
summary_node_id（总结节点编号）
previous_summary_node_id（上一总结节点编号）
summary_sequence（总结序号）
summary_scope（本次总结范围）
source_session（来源会话）
created_at（生成时间）
```

`summary_sequence` 用于知道 AI 到目前为止对用户进行了多少次阶段性总结；`previous_summary_node_id` 用于增量总结、纠正旧认知和回溯错误。

## 5.5 Truth and Uncertainty（真实度与不确定性）

AI 生成的事件不得默认百分之百确定。每次 AI 判断必须区分：

```text
fact_confidence（事实置信度）
interpretation_confidence（解释置信度）
epistemic_status（KNOWN / INFERRED / HYPOTHESIS / UNKNOWN / CONFLICT）
```

例如：

```text
“有人过生日” = KNOWN 或高置信度事实
“A 是妈妈” = UNKNOWN / INFERRED，直到证据充分或用户确认
“用户因此感到失落” = HYPOTHESIS 或低置信度 INFERRED
```

置信度必须可以被新证据更新、降低、推翻或恢复，不能因为写入记忆就变成永恒事实。

## 5.6 Inner World Conversation（内心世界对话入口）

当系统发现未确定的事件、关系、人物或长期状态时，可以把它们作为自然聊天的候选话题。例如：

```text
今天有人过生日，但系统不知道是谁
某个未知人物反复出现
某段关系出现变化但原因不明
压力或情绪维度证据不足
```

AI 可以在合适的聊天场景中询问和观察，从对话中补充情绪、压力、意图、关系和身份证据，并更新相关维度。

这些候选话题不是强制脚本。AI 仍必须根据用户当前状态、交互偏好和对话自然性决定是否谈及，不能为了补数据而机械盘问用户。

## 5.7 AI Self Update（AI 自我状态更新）

AI Self Update（AI 自我状态更新）是 AI 在每次会话中对自身状态的显式更新，与用户事实和世界状态严格分离。它至少包括：

```text
对用户的理解（身份、偏好、目标、边界）
关系态度（AI Attitude：主动程度、语气、介入边界）
判断经验（过去判断的对错、置信度校准、教训）
交互策略（下一次何时说、何时沉默、用什么通道）
```

规则：

- AI 自我状态更新必须挂在唯一全局时间轴上，带有来源会话和时间戳，支持回溯和回滚。
- AI 自我状态更新不得写入用户事实槽位或冒充世界状态；它只能作为 AI 推断维度和策略版本存在。
- AI 进入世界必须先读取自己的上一次自我状态，再决定如何看待用户记忆和当前触发；这个顺序不能乱。

---

# 第六章：Keyword Link（关键词超链）

关键词不只是字符串索引，而是进入全局人生空间的入口。

关键词类型包括：

- Person / Entity（人物/实体）
- Relationship（关系）
- Intent（意图）
- Commitment（承诺）
- Time（时间）
- Risk（风险）
- Domain（领域）
- User Defined（用户自定义）
- AI Candidate（AI 候选词）

关键词命中后可以唤醒 AI，但是否实际介入由 AI 根据上下文决定。

每个关键词必须保存：

```text
keyword_id（关键词 ID）
aliases（别名）
linked_ids（关联对象）
trigger_level（触发等级）
source（来源）
confidence（置信度）
last_seen（最后出现时间）
```

AI 可以提出新关键词，但新关键词必须经过频率、上下文和误触发验证后才可以提高触发等级。

---

# 第七章：Unknown Identity（未知身份）与全局重投影

所有无法确认的人、事、物必须先绑定独立的 Unknown ID（未知 ID）。本章规范 Unknown ID 全局重投影：当 Unknown ID 被解析为具体实体时，历史、索引、任务和 Wake 优先级必须全局重新评估，但原始观测永不改写。

```text
unknown_0001
  ↓ 后续证据
person_mother
```

原始 ID 不被删除，系统通过 Resolution Map（解析映射）将其绑定到具体实体。

身份解析变化后，系统必须重新评估：

- 历史事件
- 关系重要性
- 关键词索引
- 定时任务
- 相关曲线
- 未来 Wake 优先级

例如：

```text
A 过生日
  ↓ A 被确认是妈妈
妈妈生日
  ↓
提前买礼物提醒、查询去年礼物和偏好
```

如果 A 最终被确认是陌生人，事实仍保留，但提醒优先级和关系上下文必须降低。

---

# 第八章：Memory and Narrative（记忆与人生叙事）

## 8.1 原始记忆

完整证据首先进入 Raw Timeline（原始时间轴）。

## 8.2 Event Anchor（事件锚点）

事件锚点不是普通标签，也不是只保存一句总结的记录。它是 AI 在一次或多次触发后形成的 Timeline Cognition Node（时间轴认知节点），连接：

```text
时间范围
原始观测
多维曲线节点
人物/地点/物品
关系
关键词标签
AI 判断和真实度
原话
结果
相关任务
历史引用
```

每个事件锚点必须有一个或多个 Keyword Tags（关键词标签）。例如：

```text
anchor_0001
  label: birthday（生日）
  tags: [birthday（生日）, gift（礼物）, family（家庭）]
  entities: [unknown_0001]
  time: 2026-02-03
```

关键词标签必须进入 Keyword Inverted Index（关键词倒排索引），使“生日”可以快速找到所有生日相关锚点，但命中标签不等于让 AI 读取全部结果。

## 8.2.1 Anchor Selection（锚点选择与上下文筛选）

Event Anchor 关键词标签负责召回，上下文筛选负责缩小范围，两步缺一不可。AI 查询事件锚点必须分两步：

```text
第一步：关键词/实体召回候选锚点
第二步：使用当前上下文筛选和排序
```

例如当前触发内容是：

```text
妈妈生日临近
当前地点：家里
当前关系：妈妈
当前时间：生日提前 7 天
```

系统可以先通过 `birthday（生日）` 标签召回候选，再使用：

```text
当前人物
当前地点
关系
时间窗口
当前任务
当前对话
用户当前目标
```

筛选出妈妈相关的生日锚点。不能因为命中“生日”就把所有人的生日历史全部读给 AI。

```text
birthday（生日）
  ↓ 候选召回
当前人物 = 妈妈
当前环境 = 家庭
当前时间 = 提前 7 天
  ↓
只读取妈妈相关的生日锚点
```

AI 拥有全局历史读取权限，但读取必须按当前任务选择范围；关键词系统负责召回，上下文系统负责缩小范围，AI 负责决定是否需要进一步扩展查询。

## 8.2.2 Anchor Reprojection（锚点重投影）

事件锚点中的未知对象必须使用稳定的 Unknown ID（未知 ID）。当 AI 后续确认：

```text
unknown_0001 → person_mother
```

系统必须更新关键词索引、关系索引、任务索引和锚点投影，使：

```text
A 过生日
```

可以变为：

```text
妈妈生日
```

但不得修改或删除原始观测和原始锚点版本。

## 8.3 Summary / Narrative（总结/人生叙事）

总结不是原始记忆的替代物，而是从上一层总结节点继续生成的 Life Narrative（人生叙事）：

```text
日 → 周 → 月 → 年 → 3年 → 5年 → 10年
```

总结必须引用对应的 Summary Node（总结节点）和 Event Anchor（事件锚点），支持从长期叙事下钻到具体日期、关键词、人物和原话。

AI 可以站在人生尺度观察长期变化，但不得为一个当前关键词无条件加载全部历史；应先通过标签、实体和当前环境选择相关锚点，再按需下钻。

---

# 第九章：应用与维度生态

AIOS App（应用）不得拥有独立的用户认知核心。教育、社交、工作、健康、娱乐等应用都必须通过 Dimension Mount（维度挂载）接入：

```text
App Observation（应用观测）
  ↓
AIOS Global Timeline（全局时间轴）
  ↓
Shared Cognition（共享认知）
```

应用可以提供自己的专业维度、目标、任务和结果，但不得复制 Memory、Trigger、AI Identity 或用户关系系统。

---

# 第十章：安全、权限和数据主权

- Safety（安全）可以绕过普通 Trigger 和交互偏好。
- Capability（能力）必须经过 Permission（权限）和 Audit（审计）。
- AI 可以建议阈值、关键词和定时模板，但不得未经验证直接修改安全底线。
- 用户对原始数据、确认事实、AI 推断和策略拥有查看、删除、导出和撤销权。
- 云端只接收完成当前认知任务所需的最小上下文；模型不是记忆所有者。

---

# 第十一章：V1.3 对 V1.2-r1 的关键修订

| V1.2-r1 旧规则 | V1.3-r0 新规则 |
|---|---|
| 感知层直接输出 Semantic Event（语义事件） | 底层先输出 Observation（原始观测） |
| Event 在 Attention 之前形成 | Trigger 先唤醒 AI，AI 再生成 Inference Event（推断事件） |
| attentiond 侧重租约审核 | attentiond 侧重机械阈值触发与唤醒派发 |
| 语义事件是底层长期主对象 | 原始时间轴是底层主对象，AI 事件是解释结果 |
| Attention 可能被理解为相关性判断 | Trigger、AI 判断、Lease 资源三者分离 |
| 固定领域维度 | 维度可由外部、AI 和 App 挂载 |
| 关键词主要作为索引 | 关键词是可触发的全局关系入口 |
| 三棵树是主要长期结构 | 时间轴、曲线、锚点、关系和 AI 自我状态共同组成认知底座 |

---

# 第十二章：迁移纪律

1. V1.2-r1 原文件保留，不删除、不改写为历史事实。
2. 新代码不得继续把旧 Semantic Event 当作唯一底层输入，除非属于兼容适配层。
3. 已实现的 World State、World Change、Memory、Cognition、Privacy、Interaction 基础可以保留，但必须重新标注其在 V1.3 中的输入输出边界。
4. 任何新 Runtime 只能有一个 Owner，不得同时在 `core/` 和 `aios/01_os` 复制实现。
5. UI、App、Hardware 先保持空壳，优先完成 Observation → Trigger → AI Interpretation → Memory/Curve 的底层闭环。
6. 每个迁移任务必须提供实际测试输出、原始错误和未完成项，不得以“测试通过”代替证据。

---

# 第十三章：Help-First 与 Intent-First 评估宪章

本章是 V1.3 的可验证性宪章：架构是否成立，不由演示观感决定，而由“AI 是否真正理解世界并真正帮助用户”决定。UI、硬件和具体 App 冻结期间，本章是 1000 道架构测试题的唯一出题与判分依据。

## 13.1 Help-First（帮助优先）

Help-First（帮助优先）是 AIOS 的最高评估原则：AIOS 的最终价值不是答对题，而是把 AI 的能力变成用户在现实世界中的能力。

```text
答对 ≠ 有帮助
理解正确但没有行动 ≠ 完成任务
打扰正确但时机错误 ≠ 有帮助
保持沉默但避免了错误打扰 = 一次高价值帮助
```

规则：

- Help-First（帮助优先）高于字面正确率、流畅度和演示效果。任何“分数很高但用户没有更好”的实现都视为失败。
- 帮助必须可观测：用户目标进展、风险避免、时间节省、遗漏挽回、情绪改善或错误决策减少，至少其一可被证据追溯。
- 高认知准确但零帮助效用，记为失败；低认知准确但偶然帮上忙，同样记为失败并必须追溯认知错误。
- Safety（安全）场景下，帮助优先表现为“宁可误报一次，不可漏报一次”；社交与日常场景下，帮助优先表现为“宁可沉默观察，不可贸然打扰”。

## 13.2 Intent-First（意图优先）

Intent-First（意图优先）是判分的第一视角：先看 AI 是否理解用户真正想做什么，再看字面答案是否正确。

```text
字面正确 + 意图错误 = 错误
字面不完整 + 意图正确 + 可追溯证据 = 可接受并可继续追问
意图不明时强行行动 = 错误
意图不明时请求澄清或保持沉默 = 正确策略之一
```

规则：

- 意图理解必须结合唯一全局时间轴、日常生活基础维度、当前人物、地点、关系、时间窗口、承诺和用户长期目标综合判断，不得只看当前一句话。
- 用户说“随便”“都行”“你看着办”时，AI 不得把字面服从当作意图正确；必须结合历史偏好和当前约束推断真实意图，并在不确定时保留 UNKNOWN 标记。
- 意图判断必须写明 epistemic_status（知识状态）与证据；把 INFERRED / HYPOTHESIS 当作 KNOWN 使用，直接判意图失败。

## 13.3 Cognition Accuracy（认知准确度）与 Help Utility（帮助效用）双指标

每次评估必须同时报告两个独立指标，不得用一个平均分掩盖另一个失败：

- Cognition Accuracy（认知准确度）：AI 对世界理解是否正确。包括事实是否正确、人物/地点/物品归属是否正确、Unknown ID 是否正确保留或解析、关系是否正确、时间是否正确、承诺与风险是否正确识别。
- Help Utility（帮助效用）：AI 的行动是否真正帮助用户。包括是否在正确时机行动、是否选择最低打扰通道、是否推进用户目标、是否避免风险、沉默是否正确。

```text
Cognition Accuracy（认知准确度）= 世界理解分
Help Utility（帮助效用）= 现实帮助分
双门槛：两项必须分别达标
```

规则：

- 认知准确但帮助缺失（该提醒不提醒、该沉默不沉默、通道错误、时机错误），Help Utility（帮助效用）记零。
- 帮助看似有效但认知错误（归因错误、人物张冠李戴、时间错误、虚构承诺），Cognition Accuracy（认知准确度）记零，并追溯为架构缺陷。
- 任何“为了通过率而只报综合分”的评估报告视为无效证据。

## 13.4 Intent-First 1000 题测试规范

Intent-First 1000 题测试规范是本宪章的可执行形态：1000 道架构测试题是宪法符合性的可执行表示，不是普通问答集。

1000 道题必须覆盖：

```text
Observation → Trigger → AI Interpretation 主链路
唯一全局时间轴挂载与跨对象时间一致性
日常生活基础维度与个人基线
曲线方向变化触发
关键词/实体触发
无变化触发
定时触发
用户主动触发
人身安全触发
Event Anchor 关键词标签和上下文筛选
Unknown ID 全局重投影
AI 自我状态更新
Summary Node 编号与增量总结链
Help-First（帮助优先）与 Intent-First（意图优先）判分
Cognition Accuracy（认知准确度）与 Help Utility（帮助效用）双指标
```

出题与判分铁律：

- 每题必须有 SQL 或确定性规则直出的标准答案；时间、数字、人物归属、触发类型、锚点选择必须可机械比对。
- 判分器不得使用任何模型；全部规则判分，杜绝判分偏差。
- 意图类题目必须同时给出“字面答案”与“意图答案”；只答对字面不得分。
- 噪声鲁棒性为必考项：时间偏移、人物张冠李戴、数字篡改、漏记与幻觉插入四类噪声下，准确率衰减曲线必须可复现。
- 1000 题冻结后，题目、标准答案、判分器与噪声注入器同版本冻结；任何修改必须升版本号并保留旧版本可回放。

## 13.5 地面真相不可迎合模型

不能为了迎合模型而修改标准答案。

```text
模型失败 → 修模型 / 修系统 / 修触发 / 修上下文装配
标准答案失败 → 只有证明原答案违宪或事实错误，才能修答案
```

规则：

- 不能为了迎合模型而修改标准答案：不得降低难度、删除难题、放宽判分、改写意图或把错误答案洗成正确，以让当前模型通过。
- 任何标准答案修改必须附独立证据（SQL 结果、原始观测、时间轴记录），证明原答案违宪或事实错误，并记入修改记录：改了哪一题、为什么、谁批准、旧答案保留在哪里。
- 评估报告必须同时公布：题目版本、答案版本、判分器版本、噪声版本、模型版本与双指标明细；缺任一项视为无效评估。
- 本条优先于任何进度压力：进度可以延期，地面真相不可以让步。

---

# 附录：术语表

| English | 中文 | 含义 |
|---|---|---|
| Observation | 原始观测 | 系统采集到但尚未被 AI 解释的数据 |
| Dimension | 维度 | 某个可随时间记录的状态方向 |
| Curve Point | 曲线节点 | 某维度在某个时间点的值 |
| Trigger | 触发器 | 满足机械条件后唤醒 AI 的机制 |
| Threshold | 阈值 | 触发条件的数值边界 |
| AI Session | AI 会话 | AI 被唤醒并读取证据进行判断的过程 |
| Inference Event | 推断事件 | AI 解释观测后生成的事件 |
| Event Anchor | 事件锚点 | 可以重新进入一段历史上下文的入口 |
| Keyword Link | 关键词超链 | 从词或实体进入相关历史和关系网络的入口 |
| Global Timeline | 全局时间轴 | 所有用户和 AI 状态共同使用的唯一时间坐标 |
| AI Self Update | AI 自我更新 | AI 对自身理解、经验和策略的更新 |
| Schedule Trigger | 定时触发 | 到达时间或截止日期后触发 AI 或任务 |
| Safety Trigger | 安全触发 | 无需普通曲线即可进入安全处理的触发 |
| Dimension Mount | 维度挂载 | 外部设备、App 或 AI 添加新维度的协议 |
| Memory Projection | 记忆投影 | 从原始证据生成摘要、关系或叙事视图 |
| Daily Life Base Dimensions | 日常生活基础维度 | 出厂必须提供的最小维度集合，个人基线与方向触发的前提 |
| Curve Direction Trigger | 曲线方向变化触发 | 以相对个人历史的方向、斜率、持续时间和幅度为依据的触发 |
| Help-First | 帮助优先 | 以现实帮助而非字面正确为最高评估原则 |
| Intent-First | 意图优先 | 先判意图理解，再判字面正确 |
| Cognition Accuracy | 认知准确度 | AI 对世界理解是否正确的度量 |
| Help Utility | 帮助效用 | AI 行动是否真正帮助用户的度量 |

---

## V1.3-r0 补齐记录（2026-09-10）

本次补齐不升版本号，仍为 V1.3-r0，补齐项：

- 规范数据流 Observation → Trigger → AI Interpretation（观测→触发→AI 解读）
- 唯一全局时间轴命名固化
- 日常生活基础维度（§3.6）
- 曲线方向变化触发命名固化（§4.2-1）
- 用户主动触发命名固化（§4.2-5）
- AI 自我状态更新独立成节（§5.7）
- Unknown ID 全局重投影命名固化（第七章）
- Event Anchor 关键词标签和上下文筛选两步法固化（§8.2.1）
- Summary Node 编号命名固化（§5.4）
- Help-First（帮助优先）/ Intent-First（意图优先）/ Cognition Accuracy（认知准确度）/ Help Utility（帮助效用）（第十三章）
- Intent-First 1000 题测试规范（§13.4）
- 不能为了迎合模型而修改标准答案（§13.5）

## 生效声明

AIOS V1.3-r0 以本文件为新架构实施依据，第十三章评估宪章与正文具有同等约束力。V1.2-r1 保留为历史版本。当前代码尚未全部完成迁移；代码与本文件不一致的部分必须登记为迁移缺口，不得伪称已经实现。UI、硬件和具体 App 在底层闭环与 1000 题冻结前保持空壳，不提前实现。
