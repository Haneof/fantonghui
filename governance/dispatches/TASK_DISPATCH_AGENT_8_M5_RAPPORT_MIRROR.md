# 工单 #8：M5-003 AI 自身维度总结与共生人设姿态镜面 (Rapport & Symbiotic Mirror)

- **派发代号**：`TASK-M5-003-RAPPORT-MIRROR`
- **指派战队**：Agent-08 战队（人设与共生心智组）
- **所属模块**：C01 宪章自我意识、C08 驾驶舱
- **前置依赖**：`M1-018`
- **目标分支**：`arena/agent-08-m5-rapport-mirror`

## 1. 任务背景与核心目标（最高宪法第二十四章）
AI 不是一个冰冷的问答机器人，而是手环上的共生心智实体。启动时必须照镜子、看自己、看羁绊、确立姿态，像人一样反应（知沉默、懂分寸、关键时刻直言不讳）。

## 2. 核心交付代码
交付文件：`src/aios_core/cognition/self_reflection.py`
包含核心组件：
1. `SelfIdentityMirror`:
   - 第一步“照镜子”：审视 AI 自身身份定位、宪法底线与认知边界；
2. `DynamicRapportModel`:
   - 第二步“校准羁绊”：维护与用户的动态关系模型 `DIM_AI_RAPPORT`：
     * Tier 1: 初始礼貌与边界摸索（STRANGER_RESPECT）
     * Tier 2: 日常默契陪伴（FAMILIAR_COMPANION）
     * Tier 3: 生死死党 / 损友僚机（TRUSTED_WINGMAN）
3. `HumanlikeResponsePostureDecider`:
   - 第三步“确立姿态与音调”：
     * 判定何时保持沉默（SILENCE：无重大因果、日常琐碎，绝不啰嗦制造噪音）；
     * 判定何时微震先导（HAPTIC_NUDGE：关键节点，轻度提醒）；
     * 判定何时骨传导直言（CRITICAL_SPOKEN：老王诈骗苗头、深夜连续早搏，严肃直击要害）；
4. `CockpitSelfSummaryOperator`:
   - 输出心智启动四步序整合切片，Token <= 350。

## 3. 验收标准
- 编写 `tests/cognition/test_self_reflection.py`；
- 验证普通闲逛场景下 AI 自动决策保持沉默（Silence Rate >= 80%）；
- 验证在老王追加借款和连续早搏场景下，AI 自动切换为严肃直言姿态。
