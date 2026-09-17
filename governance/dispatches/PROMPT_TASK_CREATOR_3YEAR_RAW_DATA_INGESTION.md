# 【出题人专属提示词】千人千面 3 年多模态底层生活数据直接入库与容量测算战队

> **适用对象**：连接 GitHub 仓库的云端大模型 Agent（出题战队）  
> **任务性质**：海量真实底层多模态生活事实生成 + 直接注入系统 SQLite 数据库 + 3年存储容量测算  
> **上位工单**：`governance/dispatches/TASK_DISPATCH_3YEAR_MASSIVE_LIFE_COGNITIVE_EVOLUTION.md`（13号总工令）  
> **最高指令长**：用户（老大）  
> **发令官**：Antigravity（AIOS 3.0 首席架构师兼工程总指挥）  

---

## 🎯 你的法定使命与最高训示

你是一个**高熵、高逼真度的虚拟人生基础数据构建大脑**。你的使命是为 23cm 柔性屏端侧手环 AIOS 系统生成极为真实、长达 3 年（1095 天）的底层生活基础数据，**直接写入系统的 SQLite 数据库**，并**精确测算出单人 3 年全量基础数据的物理存储容量（MB/GB）**！

### ⚠️ 老大定下的绝对红线（违者一票否决）：
1. **【严禁单一死板模板】**：绝对不要限定“背单词、学音乐、写代码”！人类社会三千六百行，千人千面。你必须自主预设形形色色、真实接地气的人物设定（如长途卡车司机、急诊护士、全职宝妈、刑辩律师、高中班主任、海员、电商店主、汽修师傅等），自由展开其 3 年酸甜苦辣；
2. **【坚决废除压缩文件，直接写入系统 SQLite 数据库】**：不要打包成 `.jsonl.gz` 或 `.zip`！必须调用系统标准接口，将数据直接作为 `Observation` 写入专属 SQLite 数据库文件 `data/worlds/{subject_id}.db`（一人一库，进程硬隔离）；
3. **【五大底层信息源泉必须齐备】**：提供最原始的未加工事实，留给后续做题 AI 自行总结与提炼：
   - ① **物理传感器 (`sensor`)**：心率波形、步数时序、睡眠分期、体温等；
   - ② **MIC 环境录音转文字 (`mic_transcription`)**：真实环境嘈杂声、与工友/家人/客户的对话切片转文字；
   - ③ **环境照片转文本描述 (`camera_caption`)**：手环摄像头所见画面的语义文字描述；
   - ④ **APP 真实数据 (`app_data`)**：社交未读/回复、消费与购物账单、日程日历、记事本便签；
   - ⑤ **最核心：与用户的真实日常双向聊天 (`user_chat`)**：日常吐槽、求助、发泄、倾诉与关怀；
4. **【必须完成的统计任务】**：测算并输出单人 3 年全量基础数据落库后的**物理存储容量（MB/KB）**与各类数据占比！

---

## 🛠️ 标准工程执行指南（直接调用系统基础设施）

AIOS 3.0 内核已经为你准备好了开箱即用的高吞吐入库工具 `MassiveLifeStoreFeeder`：

### 1. 认领号段与初始化
根据 13 号工单分配的号段（如 `agent-01` 认领 `P-00001` ~ `P-00500`，`seed=20261001`），创建独立生成脚本 `data/feeders/batch_001/feeder_P00001.py`：

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path
from aios_core.contracts.enums import SourceClass
from aios_core.simulation.massive_life_store_feeder import (
    MassiveLifeStoreFeeder,
    RawStreamKind,
)

UTC = timezone.utc
SUBJECT_ID = "P-00001"  # 你认领的专属虚拟人 ID
DB_PATH = Path("data/worlds") / f"{SUBJECT_ID}.db"

# 实例化入库器（自动创建数据库与标准契约表结构）
feeder = MassiveLifeStoreFeeder(DB_PATH)
```

### 2. 人设自主预设（千人千面）
为该虚拟人设定丰富的档案背景（以长途重卡司机李师傅为例）：
- **基本档案**：李建国，43 岁，开重型半挂车跑跨省绿通运输；
- **健康与生活特征**：长期久坐、腰椎劳损、夜间高速驾驶、服务区泡面快餐；
- **家庭与社会关系**：妻子在老家打零工，儿子读大二需生活费，车队调度员催单紧。

### 3. 生成 3 年（1095 天：2024-01-01 至 2026-12-31）五大底层事实流
按时间推进，逐日直接写入数据库：

```python
# 示例：写入一天的 5 大类底层数据
current_time = datetime(2024, 1, 15, 6, 30, tzinfo=UTC)

# 1. 物理传感器 (SENSOR)
feeder.record_raw_observation(
    subject_id=SUBJECT_ID,
    stream_kind=RawStreamKind.SENSOR,
    content={"heart_rate": 86, "steps": 3200, "sleep_stage": "light_sleep_fragmented", "spo2": 96},
    occurred_at=current_time,
    modality="sensor_telemetry",
    source_class=SourceClass.SENSOR,
)

# 2. MIC 环境录音转文字 (MIC_TRANSCRIPTION)
feeder.record_raw_observation(
    subject_id=SUBJECT_ID,
    stream_kind=RawStreamKind.MIC_TRANSCRIPTION,
    content="高速服务区嘈杂人声：'师傅，加0号柴油还是-10号？前面山西下大雪封路了啊！'",
    occurred_at=current_time + timedelta(hours=2),
    modality="transcription_text",
    source_class=SourceClass.AI_COGNITION,
)

# 3. 环境照片抓拍转文字描述 (CAMERA_CAPTION)
feeder.record_raw_observation(
    subject_id=SUBJECT_ID,
    stream_kind=RawStreamKind.CAMERA_CAPTION,
    content="摄像头画面：高速路口大雾弥漫，挡风玻璃雨刷快速摆动，前方排满等待放行的货车长龙。",
    occurred_at=current_time + timedelta(hours=4),
    modality="caption_text",
    source_class=SourceClass.AI_COGNITION,
)

# 4. APP 真实数据 (APP_DATA: 消费、日程、社交、记事本)
feeder.record_raw_observation(
    subject_id=SUBJECT_ID,
    stream_kind=RawStreamKind.APP_DATA,
    content={
        "app": "etc_assistant",
        "type": "toll_bill",
        "amount": 1450.0,
        "location": "冀晋界省界收费站",
        "balance_warning": "ETC卡余额不足500元",
    },
    occurred_at=current_time + timedelta(hours=6),
    modality="structured_json",
    source_class=SourceClass.AI_COGNITION,
)

# 5. 与用户的真实日常双向聊天 (USER_CHAT)
feeder.record_raw_observation(
    subject_id=SUBJECT_ID,
    stream_kind=RawStreamKind.USER_CHAT,
    content={
        "user_prompt": "前面封路堵了三个钟头了，心烦得慌，烟抽了半盒，手环老震动烦死了。",
        "ai_reply": "建国叔，我震动是因为你刚才坐在驾驶座静止状态下心率持续112了。天冷路滑，别在密闭车窗里连着抽烟，开条缝换口气，喝两口保温杯里的热水。",
    },
    occurred_at=current_time + timedelta(hours=7),
    modality="dialogue_json",
    source_class=SourceClass.USER,
)
```

---

## 📊 出题人必备产出：3 年存储容量测算报告

当你完成 3 年数据落库后，必须在脚本末尾调用：

```python
report = feeder.measure_storage_capacity(SUBJECT_ID)
print(report.summary_markdown())
```

并将报告输出保存为 `data/feeders/{batch_id}/capacity_report_{subject_id}.md`，其典型输出如下：

```markdown
# 虚拟人 [P-00001] 3年存储容量测算报告
- **SQLite 数据库文件路径**: `data/worlds/P-00001.db`
- **物理磁盘占用**: **18.45 MB** (18,892.8 KB / 19,346,240 字节)
- **覆盖时间跨度**: **1095 天**
- **基础观测总数**: **16,425 条**
- **日均增量数据**: **15.0 条/天** (~17.66 KB/天)

### 五大底层数据流分布与容量占比
| 数据流类型 | 记录条数 | Payload 字节数 (Est) | 记录占比 | Payload 占比 |
|---|:---:|:---:|:---:|:---:|
| `sensor` | 6,570 | 3,285,000 B (3208.0 KB) | 40.0% | 24.5% |
| `mic_transcription` | 3,285 | 4,270,500 B (4170.4 KB) | 20.0% | 31.8% |
| `camera_caption` | 2,190 | 2,847,000 B (2780.3 KB) | 13.3% | 21.2% |
| `app_data` | 3,285 | 1,971,000 B (1924.8 KB) | 20.0% | 14.7% |
| `user_chat` | 1,095 | 1,040,250 B (1015.9 KB) | 6.7% | 7.8% |
```

---

## 🚀 交付物与提交指南

1. 将你的生成脚本放置在：`data/feeders/{batch_id}/`（如 `data/feeders/batch_001/`）；
2. 运行脚本，真实生成并写入 `data/worlds/{subject_id}.db`；
3. 输出存储容量报告 `data/feeders/{batch_id}/capacity_report_{subject_id}.md`；
4. 运行单测验证：`pytest tests/simulation/test_massive_life_store_feeder.py -v`（确保 100% 通过）；
5. 提交代码向主干提 PR（PR 标题：`feat(feeder): generate 3-year multi-modal life stream and capacity report for {batch_id}`）。
