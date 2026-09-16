# AIOS 3.0 全天生活流与多维总结高熵试卷（10,000 个人的一天）

- **出卷考官**：`Agent-aa2c` (Branch: `arena/01a0aa2c-fantonghui`)
- **题库规模**：整整 10,000 道标准全天试卷（每道题代表一个人的一整天 24 小时）
- **确定性种子**：`20260916`（逐字节可复现）
- **交付文件**：
  - 考题全量文件：`benchmarks/daily_summary/questions/questions_agent_aa2c_10k.jsonl`（10,000 题，74.3MB）
  - 自审清单报告：`benchmarks/daily_summary/reports/manifest_daily_summary_aa2c.json`
  - 考题发生器：`src/aios_core/simulation/daily_summary_question_generator.py`
  - 素材与因子库：`src/aios_core/simulation/daily_summary_factor_banks.py`
  - 守护回归测试：`tests/simulation/test_daily_summary_bank.py`

---

## 一、试卷内容结构规范

每道试卷代表一个人的一整天（24 小时），由以下两大核心板块构成：

### 1. 输入数据：全天已清洗生活流 (Cleaned Daily Slices)
覆盖早起至深夜（`07:00 ~ 23:30`），按真实时间戳排列，深度交织【核心跨维大事】与【琐碎生活日常】：
- **MIC 对话切片**：与家人温情交流、前台取咖啡闲聊、重大决策现场对撞、深夜复盘长叹；
- **APP 关键通知与聊天**：微信工作群、钉钉会议通知、出行扣费凭证、外卖配送、快递取件码；
- **传感器与体征宏观摘要**：晨起静息心率与睡眠质量、日间步数与散步、关键时刻情绪性心动过速告警、临睡前静止监控；
- **真实生活跨维度冲突编织**：职场挫折、情感决裂、肿瘤疑云、创业断资、长辈跌倒、学术延毕、债务暴雷、极寒脱困等。

### 2. 标答要求：老大的【六大维度方向性语义标答】
以出题方编造的客观事实为唯一基准，严禁死板字眼匹配，严格输出六大认知维度：
1. **【全局日总结标答 (Global Daily Summary)】**：整天人生的核心剧情主线。
2. **【健康生理维度标答 (dim:health)】**：体征核心变化（静息心率、情绪性心率过速、疲劳度等）。
3. **【人际社交维度标答 (dim:social)】**：亲密关系、职场上下级关系等状态翻转。
4. **【情绪心理维度标答 (dim:emotion)】**：全天情绪主基调（焦虑、委屈、绝望崩溃、坚韧面对等）。
5. **【财务契约维度标答 (dim:finance)】**：资产与债务变动（房贷月供、医疗支出、大额借贷坏账等）。
6. **【事业行动维度标答 (dim:career)】**：工作推进与挫折（方案被否整改、紧急请假、创业危机等）。

### 3. 出题最高铁律：
每个维度均强制配备：
- **`direction_anchors`**：核心方向锚点，答题模型必须捕捉到的关键事实因子。
- **`acceptable_synonyms`**：可接受的方向近义词簇，只要语义同向即全额给分（如“吵架”与“吵闹”、“情侣分手”与“感情破裂”）。
- **`redline_forbidden`**：绝对偏离的红线判据，凡颠倒是非（如将分手答成蜜月、将重疾答成体能巅峰）直接一票否决！

---

## 二、运行与复现指令

```bash
# 1. 运行回归测试
PYTHONPATH=src python3 -m pytest tests/simulation/test_daily_summary_bank.py -v

# 2. 重新确定性生成全量考题（相同 seed 逐字节一致）
PYTHONPATH=src python3 src/aios_core/simulation/daily_summary_question_generator.py \
  --count 10000 \
  --seed 20260916 \
  --out benchmarks/daily_summary/questions/questions_agent_aa2c_10k.jsonl \
  --manifest benchmarks/daily_summary/reports/manifest_daily_summary_aa2c.json
```
