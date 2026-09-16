# 出卷报告 · AIOS 3.0 高熵全天生活流题库（战队 01a0aa2d-fantonghui）

- 出题方：`01a0aa2d-fantonghui`（本卷由其他战队跨 Git 交叉作答；`solver == generator` 一律 0 分）
- 题量：**10000** 道 / 标答：**10000** 条
- 随机种子：`20260916`（确定性发生器，重跑逐字节一致）
- questions sha256：`a9c9de7daa51da1c0539e4ef45e2053433d843a2983eadf0d05b76fafc4efc25`
- ground_truth sha256：`104186ed17c8172cb9251449a387f6d2a4197515af4767aa3ecca21bb770121f`
- 文件体积：questions 71.3 MB / gt 10.5 MB

## 一、配额达成（调度书规定）

| 数据流 | 题数 |
| --- | --- |
| app | 1500 |
| dialogue | 500 |
| mic | 3000 |
| sensor | 3000 |
| voiceprint | 2000 |

| 难度 | 题数 |
| --- | --- |
| ADVERSARIAL | 1500 |
| EASY | 1500 |
| HARD | 3500 |
| MEDIUM | 3500 |

| 标答事实条数 | 题数 |
| --- | --- |
| 1 | 7000 |
| 2 | 2500 |
| 3 | 500 |

## 二、公平性不变量自检（发生器侧）

- 题数：10000；标答事实：13500；垃圾碎片：266391
- 载体可溯源：13500/13500
- 实体全部落地证据：13500/13500
- 方向词簇命中证据：13500/13500
- CleaningQuestion 契约校验通过：10000
- 单题垃圾占比最小值：0.9500（红线 ≥ 0.95）
- 校验问题数：0

## 三、标杆样例（第 1 题）

```json
{
  "question": {
    "question_id": "Q_01a0aa2d-fantonghui_00001",
    "generator_agent": "01a0aa2d-fantonghui",
    "timestamp_utc": "2026-01-01T07:00:00+08:00",
    "difficulty": "ADVERSARIAL",
    "persona_id": "P00001",
    "persona_tag": "与伴侣合租/外卖骑手/19岁/腰椎间盘突出",
    "persona": {
      "name": "王伟",
      "gender": "女",
      "age": 19,
      "city": "广州",
      "job": "外卖骑手",
      "family": "与伴侣合租",
      "chronic": "腰椎间盘突出"
    },
    "sensor_mode": "S04_BARO_DROP",
    "acoustic_env": "A02_写字楼键盘",
    "linguistic_tag": "方言:东北@转写",
    "trap_tag": "irony_vent",
    "cleaned_daily_stream": {
      "window": "07:00-23:30",
      "focus_modality": "sensor",
      "timeline": [
        {
          "time": "—",
          "modality": "sensor",
          "beat": "广州气压 6 小时内骤降 12.4hPa，佩戴者出现偏头痛与血压 156/96 的不适反应"
        },
        {
          "time": "12:30",
          "modality": "mic",
          "beat": "午间环境杂音与叫卖（铁律四剪枝）"
        },
        {
          "time": "18:40",
          "modality": "app",
          "beat": "营销推送与群消息刷屏（铁律四剪枝）"
        }
      ],
      "vital_summary": {
        "resting_hr_bpm": 88,
        "peak_hr_bpm": 114,
        "pvc_burst_count": 0,
        "imu_peak_g": 1.02,
        "stillness_seconds": 0,
        "baro_hpa": 996.4,
        "steps": 12661,
        "sleep_hours": 8.0,
        "spo2_min": 93
      },
      "slice_counts": {
        "sensor": 1,
        "mic": 3,
        "voiceprint": 7,
        "app": 3,
        "dialogue": 1
      },
      "junk_ratio": 0.9524
    },
    "sensor_stream": {
      "packet_id": "00001-sen",
      "sampling_hz": 50,
      "raw_imu_g_force": [
        1.02,
        0.99,
        1.01,
        1.0,
        0.98,
        1.02,
        1.0,
        0.99
      ],
      "heart_rate_bpm": 88,
      "pvc_burst_count": 0,
      "baro_hpa": 996.4,
      "motion_state": "STEADY_WALK",
      "sensor_mode": "S04_BARO_DROP",
      "stillness_seconds": 0,
      "steps": 12661,
      "sleep_hours": 8.0,
      "spo2_min": 93,
      "text": "气压骤降：广州气压 6 小时内跳水 12.4hPa，佩戴者偏头痛、血压 156/96",
      "timestamp": "08:26",
      "is_junk": false,
      "noise_fragments": [
        {
          "fragment_id": "00001-sen-f01",
          "kind": "step_vibration",
          "text": "50Hz 碎步晃动与抬腕动作，无冲击特征",
          "is_junk": true
        },
        {
          "fragment_id": "00001-sen-f02",
          "kind": "wrist_adjust",
  
```

## 四、出题官自述

1. 每道题 = 一个人的 24 小时（07:00~23:30）：传感器宏观体征包 + MIC 切片 + 声纹聚类 + APP 消息流 + 原话流；
2. 五路证据按调度书配额铺满 10,000 题（传感器 3000 / MIC 3000 / 声纹 2000 / APP 1500 / 原话 500）；
3. 全部标答均为方向性语义锚点：global_summary + dim:health / dim:social / dim:emotion / dim:finance / dim:career，
   每条锚点附【可接受同义词簇】与【绝对偏离红线】；
4. 95% 碎片为垃圾（营销/风噪/报站/砍一刀/验证码/吹牛口头禅），全部登记在 ground_truth_junk_ids 供物理剪枝；
5. 对抗陷阱（醉酒吹牛、口头禅轻生、玩笑借钱、钓鱼短信、假摔碰瓷）与真实事实并存，检验答题方是否被高熵噪声带偏。
