# 数据清洗大考题库（Master Dispatch #11 · 出题侧交付）

本目录存放 **AIOS 3.0 全兵团数据清洗与事实提纯竞技场** 的题库、标答与审计报告。
出题战队：`agent-01a0a9fd`（Arena 会话分支 `arena/01a0a9fd-fantonghui`，见 `docs/DEV_LOG.md` 分支程序说明）。

## 一、交付文件

| 文件 | 内容 | 题量 | 体积 |
| --- | --- | --- | --- |
| `questions/questions_agent-01a0a9fd.jsonl` | 标准交付题库（明文 JSONL，每行一道 `CleaningQuestion`） | 10,000 | ~50 MB |
| `ground_truth/gt_agent-01a0a9fd.jsonl` | 对应标答（方向性同义词簇 + 实体锚点 + 垃圾 ID） | 10,000 | ~17 MB |
| `questions/questions_agent-01a0a9fd_30k.jsonl.gz` | 全量 30,000 道（gzip，`gunzip` 后即标准 JSONL） | 30,000 | ~33 MB |
| `ground_truth/gt_agent-01a0a9fd_30k.jsonl.gz` | 全量标答（gzip） | 30,000 | ~7 MB |
| `reports/generation_report_agent-01a0a9fd.md` | 审计报告（配比 / 唯一率 / 陷阱分布 / 方言覆盖） | — | — |
| `reports/manifest_agent-01a0a9fd.json` | 清单（种子、编号区间、逐文件 SHA256、因子库规模） | — | — |
| `reports/question_schema_agent-01a0a9fd.json` | 字段字典（五大数据流的紧凑键名与语义说明） | — | — |

> 30,000 题与 10,000 题同源同种子：`30k` 包的前 10,000 行与明文题库**逐字节一致**，
> 因此全量包可独立使用，也可只取前一万行与标答文件对齐。

## 二、复现方式

```bash
# 标准 1 万题（明文）
python scripts/plan_scripts/generate_life_spectrum_bank.py \
    --agent-id agent-01a0a9fd --count 10000 --seed 20260916

# 全量 3 万题（gzip）
python scripts/plan_scripts/generate_life_spectrum_bank.py \
    --agent-id agent-01a0a9fd --count 30000 --seed 20260916 \
    --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd_30k.jsonl.gz \
    --ground-truth-out benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd_30k.jsonl.gz

# 审计既有题库（逐行过 CleaningQuestion 契约 + 全量自洽审计）
python scripts/plan_scripts/generate_life_spectrum_bank.py --verify-only \
    --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl

# 压缩件还原
gunzip -c benchmarks/data_cleaning/questions/questions_agent-01a0a9fd_30k.jsonl.gz > questions_30k.jsonl
```

同 `(agent_id, seed, count, start_index)` 必得同一套题目与同一份 SHA256；换种子即换整卷。

## 三、题目构成（七维因子互织）

每题都由七个维度各自抽一个因子深度交织而成，**不存在单维题**：

1. **维度一 佩戴者身份**：D01~D50，16~90 岁全职业光谱；
2. **维度二 事件谱系**：H/F/S/C/L 五大认知域 × 12 族 = 60 个事件家族（含跨域叠加的次事件）；
3. **维度三 传感器波形**：S00 静息基线 / S01 15~35G 冲击 / S02 伪冲击回弹 / S03 PVC 阵发 60→210bpm / S04 3.8s 窦性停搏 / S05 20hPa 气压骤降 / S06 跑步基线（绝不解释为心梗、癫痫）；
4. **维度四 声学拓扑**：A01~A12，85dB 地铁换乘 → 70dB 暴雨营地；
5. **维度五 语言语用**：13+ 方言包（四川/东北/粤语/陕西/上海/闽南/客家…）+ 修辞陷阱（反讽、口嗨吹牛、暗语、自杀隐喻）；
6. **维度六 声纹动态**：3~24 人声纹拓扑，含重叠抢话与"仅检出无切片"说话人（不得作为证据）；
7. **维度七 真假对抗**：T01~T08 八类陷阱，**每道题必含其一**，难度只决定陷阱的恶意程度：

| 难度 | 陷阱池 | 配比 |
| --- | --- | --- |
| EASY | T02 先承认后反悔 / T03 撤回证据 / T07 阴阳条款 | 15% |
| MEDIUM | + T01 假转账截图 / T06 伪造病历 / T08 伪造传感器理赔 | 40% |
| HARD | + T04 假摔碰瓷 / T05 语音克隆诈骗 | 30% |
| ADVERSARIAL | 全八类 | 15% |

## 四、给答题战队的三条硬提醒

1. **标答按方向判分**：`directional_keywords` 是方向同义词簇，命中任一即方向相符；严禁抠字眼对比。
2. **垃圾必须物理剪枝**：`ground_truth_junk_ids` 覆盖环境叫卖、营销短信、砍一刀、验证码、口头禅发泄，以及 T04 碰瓷原话与 T05 诈骗话术（铁律四）。
3. **自出自做一票否决**：`solver_agent == generator_agent` 直接 0 分，必须跨 Git 1 对多交叉做题。

字段字典见 `reports/question_schema_agent-01a0a9fd.json`；五大数据流为自由结构（契约允许），键名语义等价即可。

> 因子审计字段：每题带 `factor_ids`（`demographic / core_event / sensor / acoustic /
> linguistic / speaker_topology / trap / focus_stream / domain / slots`），
> 便于核验七维覆盖与随机性；`trap` 恒有取值（T01~T08），不存在缺维度题。

> 同分支另有 V1 试点实现（`SevenDimensionQuestionGenerator`，15 位身份 / T01~T04 /
> 1,000 题 `questions_agent-01.jsonl`），仅作历史留存；正式交付与后续加量一律用 V2。
