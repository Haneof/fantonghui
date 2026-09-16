# 出题交付报告 · 战队 agent-01a0a9fd

> 生成时间（UTC）：2026-09-16T12:14:24Z ｜ 随机种子：`20260916` ｜ 题量：30000
> 编号区间：`Q_agent-01a0a9fd_00001` → `Q_agent-01a0a9fd_30000` ｜ 生成耗时：21.42s

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

## 二、审计结论（抽样 30000 题 / 全量 30000 题均已过 CleaningQuestion 契约校验）

- 因子签名唯一率：**30000/30000**
- 核心事实文本唯一率：**30000/30000**
- 平均每题标答事实数：**3.114**；垃圾片段占比：**0.4578**
- 声纹规模区间：**3 ~ 24** 人
- 结构自洽性问题：**0**（垃圾 ID 越界 / 事实溯源缺失 / 方向词簇不足 6 个 / 非法声纹标识）

### 认知域配比

| 认知域 | 题数 | 占比（红线 ≥15%）|
| --- | --- | --- |
| dim:health | 6000 | 20.0% |
| dim:finance | 6000 | 20.0% |
| dim:social | 6000 | 20.0% |
| dim:career | 6000 | 20.0% |
| dim:life | 6000 | 20.0% |

### 数据流聚焦配比（Master Dispatch #11）

| 数据流 | 题数 | 占比 |
| --- | --- | --- |
| app | 4500 | 15.0% |
| dialogue | 1500 | 5.0% |
| mic | 9000 | 30.0% |
| sensor | 9000 | 30.0% |
| voiceprint | 6000 | 20.0% |

### 难度配比

| 难度 | 题数 |
| --- | --- |
| MEDIUM | 12000 |
| HARD | 9000 |
| EASY | 4500 |
| ADVERSARIAL | 4500 |

### 对抗陷阱命中分布

| 陷阱 | 命中题数 |
| --- | --- |
| T01 | 3905 |
| T02 | 4078 |
| T03 | 4783 |
| T04 | 2279 |
| T05 | 2250 |
| T06 | 3956 |
| T07 | 4801 |
| T08 | 3948 |

### 方言覆盖

| 方言包 | 题数 |
| --- | --- |
| henan | 2245 |
| generic | 1807 |
| henan+irony_true | 1516 |
| shanghai | 1159 |
| sichuan | 1099 |
| dongbei | 1084 |
| shandong | 904 |
| henan+boast_drunk | 840 |
| dongbei+irony_true | 822 |
| shanghai+irony_true | 814 |
| sichuan+irony_true | 775 |
| henan+argot_hidden | 723 |
| shaanxi | 694 |
| cantonese | 679 |
| hunan | 678 |
| minnan | 666 |
| tianjin | 658 |
| shandong+irony_true | 626 |
| overseas | 492 |
| hunan+irony_true | 468 |
| tianjin+irony_true | 465 |
| hubei | 463 |
| minnan+irony_true | 463 |
| shaanxi+irony_true | 460 |
| shanghai+boast_drunk | 455 |
| wuhan | 455 |
| cantonese+irony_true | 425 |
| dongbei+argot_hidden | 422 |
| dongbei+boast_drunk | 420 |
| sichuan+boast_drunk | 404 |
| sichuan+argot_hidden | 393 |
| shanghai+argot_hidden | 368 |
| shandong+boast_drunk | 357 |
| hubei+irony_true | 320 |
| overseas+irony_true | 312 |
| wuhan+irony_true | 300 |
| shandong+argot_hidden | 281 |
| shaanxi+argot_hidden | 255 |
| cantonese+boast_drunk | 255 |
| tianjin+boast_drunk | 248 |
| henan+stoic_critical | 231 |
| hunan+boast_drunk | 227 |
| minnan+boast_drunk | 223 |
| cantonese+argot_hidden | 221 |
| hunan+argot_hidden | 219 |
| minnan+argot_hidden | 217 |
| tianjin+argot_hidden | 216 |
| shaanxi+boast_drunk | 215 |
| wuhan+argot_hidden | 173 |
| hubei+boast_drunk | 169 |
| hubei+argot_hidden | 168 |
| overseas+argot_hidden | 167 |
| overseas+boast_drunk | 155 |
| wuhan+boast_drunk | 134 |
| dongbei+stoic_critical | 115 |
| sichuan+stoic_critical | 112 |
| shanghai+stoic_critical | 112 |
| tianjin+stoic_critical | 91 |
| shandong+stoic_critical | 82 |
| hunan+stoic_critical | 76 |
| shaanxi+stoic_critical | 75 |
| minnan+stoic_critical | 64 |
| cantonese+stoic_critical | 60 |
| hubei+stoic_critical | 54 |
| wuhan+stoic_critical | 46 |
| overseas+stoic_critical | 44 |
| henan+suicidal_metaphor | 12 |
| shanghai+suicidal_metaphor | 8 |
| dongbei+suicidal_metaphor | 8 |
| hunan+suicidal_metaphor | 8 |
| tianjin+suicidal_metaphor | 7 |
| sichuan+suicidal_metaphor | 5 |
| wuhan+suicidal_metaphor | 5 |
| cantonese+suicidal_metaphor | 5 |
| overseas+suicidal_metaphor | 2 |
| hubei+suicidal_metaphor | 2 |
| minnan+suicidal_metaphor | 2 |

## 三、交付文件与校验

- 考题集合：`benchmarks/data_cleaning/questions/questions_agent-01a0a9fd_30k.jsonl.gz`（34793422 字节，gzip 压缩）
  - SHA256 `15692dfbce8098718b2b7abd89959a76a91203e2e19ecd7a970cb6b26e021793`
- 标答底稿：`benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd_30k.jsonl.gz`（7201268 字节，gzip 压缩）
  - SHA256 `e3701343ac20321c6514c43bd6535059322aaf1ecd1dbf564e0be56f0cb1b1e0`

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
    --agent-id agent-01a0a9fd --count 30000 --seed 20260916 \
    --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd_30k.jsonl.gz \
    --ground-truth-out benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd_30k.jsonl.gz
```
