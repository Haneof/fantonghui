# 工单 #10：M5-005 独立 Agent 虚拟人生战训考场与全景诊断器 (Agent Mind Arena)

- **派发代号**：`TASK-M5-005-AGENT-ARENA`
- **指派战队**：Agent-10 战队（测试平台与战训评测组）
- **所属模块**：全系统集成测试与经验沉淀
- **前置依赖**：工单 6、7、8、9
- **目标分支**：`arena/agent-10-m5-agent-arena`

## 1. 任务背景与核心目标
让每一个独立的 Agent 程序员（各模型实例）面对长达 3 年真实虚拟人生，独立考评其在 AIOS 世界里的心智表现、检索效率与人设分寸。

## 2. 核心交付代码
交付文件：`src/aios_core/simulation/agent_mind_bench.py`
包含核心组件：
1. `AgentMindPlayground`:
   - 独立沙箱环境，加载 3 年高熵多维世界数据；
   - 包含 10 个典型生活危机与决策情境考验点（老王案、老妈生日、早搏危机、感情破裂、高阶维度衍生、P0跌倒硬旁路）；
2. `MindPerformanceMetricsRecorder`:
   - 记录该 Agent 全流程的：
     * 平均决策 Token 消耗（Token Budget Efficiency）
     * 证据检索延迟与准确率（Retrieval Latency & Recall）
     * 维度生命周期合规性（Dimension Compliance）
     * 人设分寸感评分（Human-like Resonance Score）
     * 宪法铁律一票否决检查（Iron Rules Guard: 改历史=0分, P0走大模型=0分）
3. `AgentMindDiagnosticReport`:
   - 自动生成该 Agent 的《AIOS 3.0 共生心智操作全景体检报告》，并持久化至 `operation_experiences` 经验库。

## 3. 验收标准
- 编写 `tests/simulation/test_agent_mind_bench.py`；
- 模拟优秀 Agent vs 劣质 Agent，断言诊断器能准确识别劣质 Agent 的违规与高能耗。
