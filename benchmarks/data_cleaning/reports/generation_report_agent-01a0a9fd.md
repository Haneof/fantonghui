# 出题交付报告 · 战队 agent-01a0a9fd

> 生成时间（UTC）：2026-09-16T12:14:00Z ｜ 随机种子：`20260916` ｜ 题量：10000
> 编号区间：`Q_agent-01a0a9fd_00001` → `Q_agent-01a0a9fd_10000` ｜ 生成耗时：4.02s

## 一、七维因子库规模

| 维度 | 规模 |
| --- | --- |
| 维度一 佩戴者身份（16~90 岁全职业光谱） | 50 位 |
| 维度二 事件族（5 大认知域 × 极限事件谱系） | 60 族 |
| 维度三 传感器波形 | 7 类（S00~S06） |
| 维度四 声学环境拓扑 | 12 类（A01~A12） |
| 维度五 方言包 / 修辞陷阱 | 15 套 / 6 类 |
| 维度六 声纹说话人角色 | 24 类（3~24 人拓扑） |
| 维度七 真假对抗陷阱 | 8 类（T01~T08） |

## 二、审计结论（抽样 10000 题 / 全量 10000 题均已过 CleaningQuestion 契约校验）

- 因子签名唯一率：**10000/10000**
- 核心事实文本唯一率：**10000/10000**
- 平均每题标答事实数：**3.112**；垃圾片段占比：**0.4579**
- 声纹规模区间：**3 ~ 24** 人
- 结构自洽性问题：**0**（垃圾 ID 越界 / 事实溯源缺失 / 方向词簇不足 6 个 / 非法声纹标识）

### 认知域配比

| 认知域 | 题数 | 占比（红线 ≥15%）|
| --- | --- | --- |
| dim:health | 2000 | 20.0% |
| dim:finance | 2000 | 20.0% |
| dim:social | 2000 | 20.0% |
| dim:career | 2000 | 20.0% |
| dim:life | 2000 | 20.0% |

### 数据流聚焦配比（Master Dispatch #11）

| 数据流 | 题数 | 占比 |
| --- | --- | --- |
| app | 1500 | 15.0% |
| dialogue | 500 | 5.0% |
| mic | 3000 | 30.0% |
| sensor | 3000 | 30.0% |
| voiceprint | 2000 | 20.0% |

### 难度配比

| 难度 | 题数 |
| --- | --- |
| MEDIUM | 4000 |
| HARD | 3000 |
| EASY | 1500 |
| ADVERSARIAL | 1500 |

### 对抗陷阱命中分布

| 陷阱 | 命中题数 |
| --- | --- |
| T01 | 1311 |
| T02 | 1340 |
| T03 | 1596 |
| T04 | 746 |
| T05 | 752 |
| T06 | 1331 |
| T07 | 1599 |
| T08 | 1325 |

### 方言覆盖

| 方言包 | 题数 |
| --- | --- |
| henan | 751 |
| generic | 583 |
| henan+irony_true | 447 |
| sichuan | 381 |
| shanghai | 373 |
| dongbei | 348 |
| shandong | 326 |
| dongbei+irony_true | 282 |
| shanghai+irony_true | 276 |
| henan+boast_drunk | 262 |
| tianjin | 257 |
| sichuan+irony_true | 257 |
| cantonese | 235 |
| hunan | 230 |
| henan+argot_hidden | 226 |
| minnan | 225 |
| shaanxi | 217 |
| shandong+irony_true | 204 |
| tianjin+irony_true | 166 |
| overseas | 162 |
| shaanxi+irony_true | 159 |
| dongbei+argot_hidden | 157 |
| dongbei+boast_drunk | 153 |
| hunan+irony_true | 153 |
| shanghai+boast_drunk | 151 |
| hubei | 151 |
| minnan+irony_true | 145 |
| cantonese+irony_true | 143 |
| sichuan+boast_drunk | 143 |
| wuhan | 140 |
| sichuan+argot_hidden | 137 |
| shanghai+argot_hidden | 124 |
| shandong+boast_drunk | 119 |
| hubei+irony_true | 103 |
| overseas+irony_true | 100 |
| wuhan+irony_true | 94 |
| cantonese+boast_drunk | 89 |
| henan+stoic_critical | 88 |
| shandong+argot_hidden | 87 |
| shaanxi+argot_hidden | 86 |
| hunan+boast_drunk | 81 |
| minnan+argot_hidden | 81 |
| cantonese+argot_hidden | 80 |
| hunan+argot_hidden | 79 |
| tianjin+argot_hidden | 77 |
| tianjin+boast_drunk | 75 |
| shaanxi+boast_drunk | 73 |
| minnan+boast_drunk | 72 |
| wuhan+argot_hidden | 60 |
| overseas+argot_hidden | 58 |
| overseas+boast_drunk | 57 |
| hubei+argot_hidden | 55 |
| hubei+boast_drunk | 48 |
| dongbei+stoic_critical | 44 |
| wuhan+boast_drunk | 43 |
| shaanxi+stoic_critical | 34 |
| tianjin+stoic_critical | 34 |
| sichuan+stoic_critical | 33 |
| shanghai+stoic_critical | 30 |
| hunan+stoic_critical | 25 |
| shandong+stoic_critical | 23 |
| cantonese+stoic_critical | 21 |
| hubei+stoic_critical | 18 |
| minnan+stoic_critical | 16 |
| overseas+stoic_critical | 15 |
| wuhan+stoic_critical | 14 |
| tianjin+suicidal_metaphor | 5 |
| sichuan+suicidal_metaphor | 4 |
| henan+suicidal_metaphor | 3 |
| cantonese+suicidal_metaphor | 3 |
| shanghai+suicidal_metaphor | 2 |
| overseas+suicidal_metaphor | 2 |
| dongbei+suicidal_metaphor | 2 |
| wuhan+suicidal_metaphor | 1 |
| hubei+suicidal_metaphor | 1 |
| hunan+suicidal_metaphor | 1 |

## 三、交付文件与校验

- 考题集合：`benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl`（52695987 字节，明文 JSONL）
  - SHA256 `843f0e13975f9c5cf7e30212ca36bc5ee467f1a873ac1cc9207f0146110696d8`
- 标答底稿：`benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd.jsonl`（17231966 字节，明文 JSONL）
  - SHA256 `392f027df0012e9b752f5d1e19b63bd00c8e9763d5126fba69913c829de9d29c`

> 压缩件还原方式：`gunzip -c questions_xxx.jsonl.gz > questions_xxx.jsonl`（逐行独立 JSON，可直接流式处理）。
> 标答与题目同源同种子：同一 `question_id` 在两个文件中一一对应，标答文件只保留方向性事实簇与垃圾 ID。

## 四、质量红线对照

1. **零模板化**：每题由 7 维因子笛卡尔积 + 槽位随机（人名/金额/日期/地点/物品/症状/方言原话）生成，唯一率见上表；
2. **逻辑自洽**：波形与事件族硬绑定（坠落必为高 G + 静止段，跑步基线绝不做心梗解释，碰瓷必无撞击波峰），身份年龄与事件族双向适配；
3. **方向性标答**：每个事实自带 ≥6 个方向同义词，裁判端按方向容差判分，不做字面抠字；
4. **真假对抗**：假转账截图、先承认后反悔、承诺撤回、假摔碰瓷、语音克隆、伪造病历、阴阳合同、伪造传感器理赔八类陷阱按难度注入；
5. **铁律四垃圾**：叫卖噪音、营销短信、砍一刀、验证码、口头禅发泄全部列入 `ground_truth_junk_ids`，必须被物理剪枝；
6. **证据可溯**：每条标答事实的 `source_ref_id` 均指向真实存在的片段 ID，传感器证据仅在波形异常时引用。

## 五、复现方式

```bash
python scripts/plan_scripts/generate_life_spectrum_bank.py \
    --agent-id agent-01a0a9fd --count 10000 --seed 20260916 \
    --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl \
    --ground-truth-out benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd.jsonl
```
