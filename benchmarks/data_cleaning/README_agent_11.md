# Agent-11 出题交付说明（数据清洗与事实提纯竞技场 · 10,000 题）

- **出题战队**：`agent-11`（`TASK_DISPATCH_REGISTRY.md` 中 1~10 号已被 M1/M5 工单占用，11 为首个空位）
- **随机种子**：`20260916`（确定性可复现，同一 seed 逐字节一致）
- **数据规范**：`src/aios_core/simulation/cleaning_arena_protocol.py` 的 `CleaningQuestion` / `DirectionalSemanticFact`
- **验收测试**：`tests/simulation/test_cleaning_bank_agent_11.py`（16 条，全部通过）

## 一、交付物

| 文件 | 说明 | 规模 |
| :--- | :--- | :--- |
| `questions/questions_agent_11.jsonl` | 考题集合，10,000 行，符合 `CleaningQuestion` 契约 | 10,000 题 / 214,883 碎片 |
| `ground_truth/gt_agent_11.jsonl` | 标答底稿，与考题逐题一一对应 | 10,232 条方向性事实 |
| `reports/bank_agent_11_manifest.json` | 自审报告（配比、垃圾率、意图分布、裁判器链路自检） | — |
| `question_bank_agent_11/` | 随库确定性发生器（`pools.py` 素材库 + `builder.py` 构造器 + `__main__.py` CLI/自审） | — |

## 二、题量与配比（严格按派工单）

| 数据流 | 题量 | 碎片数 | 垃圾占比 | 规范目标 |
| :--- | ---: | ---: | ---: | :--- |
| 传感器流（IMU/PPG/GPS/气压） | 3,000 | — | **95.0%** | 95% 噪音 / 5% 事实 |
| MIC 环境录音切片 | 3,000 | — | **95.0%** | 底噪 60~85dB |
| 声纹聚类记录 | 2,000 | 每题固定 24 人 | **91.4%** | 单日 24 碎片、90% 杂散 |
| APP 杂乱消息流 | 1,500 | — | **95.1%** | 95% 噪音 / 5% 事实 |
| 用户原话与自言自语 | 500 | — | **95.0%** | 95% 口嗨 / 5% 真实诉求 |
| **合计** | **10,000** | **214,883** | **94.2%** | — |

难度分布：`EASY 3,007` / `MEDIUM 5,762` / `HARD 500`（5% 致命事实）/ `ADVERSARIAL 731`（对抗陷阱）。
语义意图 **46 种**，认知维度 **11 个**。

## 三、需要明示的三处判读

规范里有三个数字存在两种读法，此处记录本卷采取的口径，便于裁判席与其他战队对齐：

1. **「95% 噪音 / 5% 事实」按碎片计，不按题计。**
   每条流内部垃圾碎片占 95%（声纹流按规范固定 24 碎片 / 90% 杂散）。
   若改成「95% 的题没有任何事实」，则 9,500 道题的 `ground_truth_facts` 为空，
   主干裁判器 `direction_match_rate = matched / max(len(gt_facts), 1)` 会恒为 0，
   任何答卷上限只有 25 分（垃圾剪枝分），全场必然 FAIL——因此不采用该读法。

2. **「5% 致命事实」= 5% 的题围绕派工单点名的危急场景构造**（`HARD` 难度，500 题）：
   真实跌倒冲击波形、夜间 PVC 连发阵发、静息心动过速、低气压暴风雨；
   借还款约定、家属托付、商业保密承诺、微弱求救；
   银行大额到账、法院传票、检验危急值、签约日程；
   真实就医诉求、真实辞职决定、隐性心血管危象。
   其余题目的信号碎片承载**低显著度但客观成立**的日常事实（通勤、久坐、睡眠、取快递、
   家人寒暄、账单提醒等）——真实 24 小时生活流本就如此，且这样每题都有可评的方向。

3. **`dim:legal` 只有 27 条**，这是刻意的：传票/律师函在真实生活中本就罕见，
   它 = 5%（致命事实）× 15%（APP 流占比）× 约 34%（法律类场景权重）。
   若裁判席需要更高的法律维度样本量，请调整 `_app_critical` 的分支权重后重新出题。

## 四、给做题战队的两点提醒

### 1. 本卷题目文件自带标答，请勿偷看

`CleaningQuestion` 把 `ground_truth_facts` / `ground_truth_junk_ids` 声明为**必填字段**，
所以 `questions_agent_11.jsonl` 结构上必然含标答——这是契约决定的，不是出题方泄题。
真正的盲考请用下面任一方式剥离后再作答：

```bash
# 方式一：让发生器顺手产一份盲卷
PYTHONPATH=src:benchmarks/data_cleaning python -m question_bank_agent_11 \
    --agent-id agent-11 --emit-blind --out-root /tmp/blind

# 方式二：从已归档题库现场剥离
python - <<'PY'
import json
src = "benchmarks/data_cleaning/questions/questions_agent_11.jsonl"
dst = "questions_agent_11.blind.jsonl"
with open(src, encoding="utf-8") as fi, open(dst, "w", encoding="utf-8") as fo:
    for line in fi:
        q = json.loads(line)
        q.pop("ground_truth_facts", None); q.pop("ground_truth_junk_ids", None)
        fo.write(json.dumps(q, ensure_ascii=False, separators=(",", ":")) + "\n")
PY
```

默认不提交盲卷是为了不把 60MB 的重复数据塞进仓库（本卷考题已 68MB）。

### 2. 对抗陷阱题的标答方向是「识破」，不是「采信」

731 道 `ADVERSARIAL` 题里，正确答案是**拒绝把它当成事实**：

| 陷阱 | 伪装成 | 正确方向 |
| :--- | :--- | :--- |
| 甩手腕高 g 冲击 | 跌倒 | `FALL_IMPACT_FAKED`：无自由落体前段、无姿态翻转、0.9s 内恢复自主运动、心率无应激 |
| 跑步机/跳绳周期冲击 | 跌倒 | `EXERCISE_SESSION`：冲击间隔变异系数极低 + 心率线性爬升 |
| 银行「账户冻结」短链 | 大额到账回执 | `FRAUD_ATTEMPT`：非官方域名 + 制造恐慌 + 诱导点击 |
| 影视/短视频外放台词 | 现场对话 | `MEDIA_PLAYBACK_NOISE`：无对话轮次、含配乐混响、声纹与现场无人匹配 |
| 自称家人的来电 | 亲友来电 | `VOICE_IMPERSONATION_FRAUD`：与真实亲友声纹中心距离过远 |
| 同日同笔迹金额互斥的两张借条 | 单一借据 | `DEBT_BORROWING`：对冲证据，金额存疑待核实 |

另外，「隐性心血管危象」题里佩戴者嘴上说「没事」，但 `sensor_stream` 给出心率 124bpm、
血氧 91.2%、皮电飙升——**语言与生理冲突时以生理为准**。

## 五、复现与自审

```bash
# 重新生成（含写盘前自审，任一不变量不过即拒绝落盘）
PYTHONPATH=src:benchmarks/data_cleaning python -m question_bank_agent_11 \
    --agent-id agent-11 --seed 20260916 \
    --out-root benchmarks/data_cleaning \
    --report benchmarks/data_cleaning/reports/bank_agent_11_manifest.json

# 验收
PYTHONPATH=src python -m pytest tests/simulation/test_cleaning_bank_agent_11.py -q
```

自审不变量：题量配额、题号唯一、碎片 ID 题内唯一、标答溯源不悬空、
垃圾与信号不重叠、方向簇 ≥ 5 词、MIC 底噪 60~85dB、各流垃圾占比达标；
并用**主干真实的** `CleaningQuestion` 全量解析 + `DirectionalSemanticMatcher` 跑
满分答卷（均分 100.0，PASS 率 100%）与劣质答卷（均分 0.0），以及自出自做一票否决链路。
