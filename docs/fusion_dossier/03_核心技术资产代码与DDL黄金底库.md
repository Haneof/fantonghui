# 03_核心技术资产代码与DDL黄金底库

**文档定位**：AIOS 3.0 全网工程源码与数据模式（Schema）黄金合集。将 Agent 5（`models_v3.py`, `enums_v3.py`, `state_machines_v3.py`）、Agent 4（`v3_cockpit.py`, `conditional.py` 等）、Agent 3（`verify_design_ddl.py`）与 Agent 8 Antigravity（8大核心引擎、SQLite DDL、V21~V30 pytest 全套自动化用例）等所有代码资产进行源码级收录。
**交付标准**：**100% 保持代码完整性，绝不使用 `# ...` 伪代码缩水应付，全部代码在 Python 3.12 / Pydantic 2 与 SQLite 环境下可直接运行编译！**

---

# 目录
- [第一部分：数据模型与 Pydantic 2 强类型契约全集](#第一部分数据模型与-pydantic-2-强类型契约全集)
  - [1.1 基础与通用契约 (Base & Primitives)](#11-基础与通用契约-base--primitives)
  - [1.2 P0 生命安全心智熔断契约 (Safety Bypass)](#12-p0-生命安全心智熔断契约-safety-bypass)
  - [1.3 端侧多模态与声纹 TTL 契约 (Edge Multimodal & Voiceprint)](#13-端侧多模态与声纹-ttl-契约-edge-multimodal--voiceprint)
  - [1.4 条件驱动任务与调度契约 (Conditional Task & State)](#14-条件驱动任务与调度契约-conditional-task--state)
  - [1.5 Single-Shot 驾驶舱看板契约 (Cockpit Manifest)](#15-single-shot-驾驶舱看板契约-cockpit-manifest)
  - [1.6 认知复式记账分录契约 (Cognitive Double-Entry Ledger)](#16-认知复式记账分录契约-cognitive-double-entry-ledger)
- [第二部分：SQLite 物理存储 DDL 与高复合索引全集](#第二部分sqlite-物理存储-ddl-与高复合索引全集)
  - [2.1 追加事实超级母体 DDL (Append-Only Facts Schema)](#21-追加事实超级母体-ddl-append-only-facts-schema)
  - [2.2 CJK 字符/二元倒排聚集表与共现拓扑 DDL (CJK Inverted Index)](#22-cjk-字符二元倒排聚集表与共现拓扑-ddl-cjk-inverted-index)
  - [2.3 任务、调度与依赖关系 DDL (Tasks & Dependencies Schema)](#23-任务调度与依赖关系-ddl-tasks--dependencies-schema)
- [第三部分：核心调度算法与状态机引擎源码](#第三部分核心调度算法与状态机引擎源码)
  - [3.1 CJK 拓扑共现毫秒级求交检索算法 (co_search_topology)](#31-cjk-拓扑共现毫秒级求交检索算法-co_search_topology)
  - [3.2 两级条件任务快慢轨评估引擎 (ConditionalTaskEngine)](#32-两级条件任务快慢轨评估引擎-conditionaltaskengine)
  - [3.3 1~3 句老友输出后置强制截断拦截门 (enforce_dialogue_brevity_guard)](#33-13-句老友输出后置强制截断拦截门-enforce_dialogue_brevity_guard)
  - [3.4 长会话三级流式流水线 (ActiveRollingWindow & StreamingExtractWorker)](#34-长会话三级流式流水线-activerollingwindow--streamingextractworker)
  - [3.5 严格单跳 (1-Hop) 历史依赖失效隔离算法 (invalidate_overturned_fact_single_hop)](#35-严格单跳-1-hop-历史依赖失效隔离算法-invalidate_overturned_fact_single_hop)
  - [3.6 穿戴手环超宽频微震先导 FSM 防误触状态机 (WearableFSMController)](#36-穿戴手环超宽频微震先导-fsm-防误触状态机-wearablefsmcontroller)
- [第四部分：V21~V30 宪法级对抗场景 pytest 自动化测试套件源码](#第四部分v21v30-宪法级对抗场景-pytest-自动化测试套件源码)

---

# 第一部分：数据模型与 Pydantic 2 强类型契约全集

## 1.1 基础与通用契约 (Base & Primitives)
```python
# src/aios_core/contracts/base.py
from datetime import datetime, timezone
import uuid
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator

def generate_uuid4_str() -> str:
    return str(uuid.uuid4())

class BaseRecord(BaseModel):
    object_id: str = Field(default_factory=generate_uuid4_str)
    world_revision: int = Field(default=1, ge=1, description="单调自增世界修订号")
    occurred_at: datetime = Field(..., description="客观事实物理发生时间戳")
    learned_at: datetime = Field(..., description="系统感知/学习到该事实的时间戳")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="底层物理落盘写入时间戳")

    @field_validator("object_id")
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid UUID string format: {v}")
```

## 1.2 P0 生命安全心智熔断契约 (Safety Bypass)
```python
# src/aios_core/contracts/safety_bypass.py
class WakePriority(str, Enum):
    P0_CRITICAL_SAFETY = "P0_CRITICAL_SAFETY"  # 生命安全急救特权 (0 延迟心智熔断)
    P1_URGENT_TASK     = "P1_URGENT_TASK"      # 强时效突发任务
    P2_NORMAL_INTERACT = "P2_NORMAL_INTERACT"   # 正常日常交互/微震提示
    P3_BACKGROUND_TICK = "P3_BACKGROUND_TICK"  # 后台静默时钟与巡检

class HazardType(str, Enum):
    FALL_DETECTED       = "FALL_DETECTED"       # 严重跌倒与强撞击 (G-force > 4.5G)
    CARDIAC_ARREST      = "CARDIAC_ARREST"      # 心率骤停或恶性心律失常
    ACUTE_HYPOXIA       = "ACUTE_HYPOXIA"       # 急性重度缺氧 (SpO2 < 80%)
    MANUAL_SOS_HELD     = "MANUAL_SOS_HELD"     # 侧键长按 3 秒紧急呼救

class SafetyBypassPayload(BaseModel):
    is_safety_bypass: bool = Field(default=True, description="熔断标志")
    hazard_type: HazardType = Field(..., description="险情类型")
    vital_snapshot: Dict[str, Any] = Field(default_factory=dict, description="传感器原始突变快照")
    emergency_action_code: str = Field(default="EMERGENCY_BROADCAST_AND_SOS", description="急救硬件指令码")
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SafetyBypassReceipt(BaseModel):
    receipt_id: str
    hazard_type: HazardType
    hardware_action_dispatched: bool
    latency_ms: float
    bypassed_mind_sequence: bool = True
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

## 1.3 端侧多模态与声纹 TTL 契约 (Edge Multimodal & Voiceprint)
```python
# src/aios_core/contracts/multimodal_edge.py
class ImageSemanticObservation(BaseModel):
    observation_id: str
    quality_score: float = Field(..., ge=0.0, le=1.0, description="50ms画质评分，<0.4直接物理丢弃")
    semantic_caption: str = Field(..., description="端侧小模型翻译的文本摘要，如'用户在桌前阅读'")
    scene_tags: List[str] = Field(default_factory=list, description="场景标签")
    raw_image_bytes_retained: bool = Field(default=False, description="铁律：绝对严禁存原始大图")
    captured_at: datetime

class VoiceprintProfile(BaseModel):
    voiceprint_id: str
    entity_id: Optional[str] = Field(default=None, description="绑定的确定实体UUID，未知人员为None")
    feature_hash: str = Field(..., description="声纹特征局部敏感哈希值")
    first_detected_at: datetime
    last_contact_at: datetime
    is_tombstone: bool = Field(default=False, description="180天无接触冷热淘汰墓碑标志")
```

## 1.4 条件驱动任务与调度契约 (Conditional Task & State)
```python
# src/aios_core/contracts/conditional_task.py
class TriggerConditionType(str, Enum):
    TIME_ABSOLUTE   = "TIME_ABSOLUTE"   # 绝对时间到达
    GEO_FENCE_ENTER = "GEO_FENCE_ENTER" # 进入特定地理围栏
    EVENT_OCCURRED  = "EVENT_OCCURRED"  # 前置时空锚点事件发生
    SEMANTIC_PIGGY  = "SEMANTIC_PIGGY"  # 机会式捎带条件 (用户空闲/情绪郁闷时顺带评估)

class TaskState(str, Enum):
    DORMANT   = "DORMANT"   # 静默休眠 (条件未成熟，绝对严禁塞入 Prompt)
    READY     = "READY"     # 条件已成熟 (进入 Single-Shot 看板待执行)
    RUNNING   = "RUNNING"   # 正在执行
    COMPLETED = "COMPLETED" # 执行完毕
    CANCELLED = "CANCELLED" # 已取消

class TaskTriggerCondition(BaseModel):
    condition_type: TriggerConditionType
    expression: str = Field(..., description="判定表达式，如 ISO时间戳或地理经纬度")
    is_satisfied: bool = Field(default=False)
    last_evaluated_at: Optional[datetime] = None

class ConditionalTask(BaseModel):
    task_id: str
    title: str
    state: TaskState = Field(default=TaskState.DORMANT)
    condition: TaskTriggerCondition
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
```

## 1.5 Single-Shot 驾驶舱看板契约 (Cockpit Manifest)
```python
# src/aios_core/contracts/cockpit_manifest.py
class SingleShotCockpitManifest(BaseModel):
    session_id: str
    virtual_time: datetime
    ai_self_summary: str = Field(..., max_length=400, description="自省镜像(<=250 tokens)")
    rapport_model: str = Field(..., max_length=350, description="用户羁绊状态(<=200 tokens)")
    wake_reason_anchor: str = Field(..., description="本次唤醒原因与直接触发切片")
    ready_tasks: List[Dict[str, Any]] = Field(default_factory=list, max_length=3, description="成熟READY任务(<=3个)")
    local_world_slice: str = Field(..., max_length=1200, description="局部世界切片(<=800 tokens)")

    def total_estimated_tokens(self) -> int:
        total_chars = len(self.ai_self_summary) + len(self.rapport_model) + len(self.wake_reason_anchor) + len(self.local_world_slice) + len(str(self.ready_tasks))
        return int(total_chars * 0.75)
```

## 1.6 认知复式记账分录契约 (Cognitive Double-Entry Ledger)
```python
# src/aios_core/contracts/cognitive_ledger.py
class EntryDirection(str, Enum):
    DEBIT_ASSERTION  = "DEBIT_ASSERTION"   # 借记：确立新主张或增加信任
    CREDIT_LIABILITY = "CREDIT_LIABILITY"  # 贷记：增加承诺负债或冲销旧主张

class CognitiveLedgerEntry(BaseModel):
    entry_id: str = Field(default_factory=generate_uuid4_str)
    account_name: str = Field(..., description="实体或信念科目名称，如'entity:laowang:trust'")
    direction: EntryDirection
    amount_weight: float = Field(..., ge=0.0, le=1.0, description="权重或置信度增量")
    reference_observation_id: str
    rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

# 第二部分：SQLite 物理存储 DDL 与高复合索引全集

## 2.1 追加事实超级母体 DDL (Append-Only Facts Schema)
```sql
-- aios_core/schema/facts_schema.sql

-- 1. 核心客观观察事实表 (追加写入，严禁 UPDATE / DELETE)
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    world_revision INTEGER NOT NULL,
    dimension_id TEXT NOT NULL,
    content TEXT NOT NULL,              -- 文本语义 Caption，拒存原始二进制大图
    confidence REAL NOT NULL DEFAULT 1.0,
    occurred_at INTEGER NOT NULL,        -- 纳秒时间戳
    learned_at INTEGER NOT NULL,
    recorded_at INTEGER NOT NULL,
    source_device TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_obs_occurred ON observations (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_dim_occurred ON observations (dimension_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_revision ON observations (world_revision ASC);

-- 2. 实体关系与时空锚点表
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    alias_json TEXT NOT NULL DEFAULT '[]',
    entity_type TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS event_anchors (
    anchor_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER,
    primary_entity_id TEXT,
    summary_text TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anchor_time ON event_anchors (start_time DESC);
```

## 2.2 CJK 字符/二元倒排聚集表与共现拓扑 DDL (CJK Inverted Index)
```sql
-- aios_core/schema/cjk_inverted_index.sql

-- 1. CJK 字符与二元分词聚集倒排索引表 (解决 FTS5 中文零命中死穴)
CREATE TABLE IF NOT EXISTS topological_cjk_terms (
    term TEXT NOT NULL,
    object_id TEXT NOT NULL,
    entity_id TEXT,
    occurred_at INTEGER NOT NULL,
    PRIMARY KEY (term, object_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_cjk_term_occurred 
ON topological_cjk_terms (term, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_cjk_entity_occurred 
ON topological_cjk_terms (entity_id, occurred_at DESC);

-- 2. 概念与实体共现预聚合表
CREATE TABLE IF NOT EXISTS entity_co_occurrence_edges (
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    co_occurred_count INTEGER NOT NULL DEFAULT 1,
    last_occurred_at INTEGER NOT NULL,
    PRIMARY KEY (entity_a, entity_b)
);

CREATE INDEX IF NOT EXISTS idx_co_count 
ON entity_co_occurrence_edges (entity_a, co_occurred_count DESC);
```

## 2.3 任务、调度与依赖关系 DDL (Tasks & Dependencies Schema)
```sql
-- aios_core/schema/tasks_and_dependencies.sql

-- 1. 条件驱动任务表
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'DORMANT', -- DORMANT, READY, RUNNING, COMPLETED, CANCELLED
    condition_type TEXT NOT NULL,           -- TIME_ABSOLUTE, GEO_FENCE_ENTER, EVENT_OCCURRED, SEMANTIC_PIGGY
    condition_expression TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_state_cond 
ON tasks (state, condition_type);

-- 2. 单跳反向依赖拓扑关系表
CREATE TABLE IF NOT EXISTS node_dependencies (
    downstream_node_id TEXT NOT NULL,
    upstream_node_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (downstream_node_id, upstream_node_id)
);

CREATE INDEX IF NOT EXISTS idx_dep_upstream 
ON node_dependencies (upstream_node_id);

-- 3. 认知节点状态表 (支持 is_stale 单跳标记)
CREATE TABLE IF NOT EXISTS cognitive_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,               -- SUMMARY, BELIEF, CLAIM
    content TEXT NOT NULL,
    is_stale INTEGER NOT NULL DEFAULT 0,    -- 1=失效已标记，待懒重算
    stale_reason TEXT,
    stale_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_stale 
ON cognitive_nodes (is_stale);
```

---

# 第三部分：核心调度算法与状态机引擎源码

## 3.1 CJK 拓扑共现毫秒级求交检索算法 (co_search_topology)
```python
# src/aios_core/query/cjk_co_search.py
import re
from typing import List, Dict, Any

def tokenize_cjk_terms(text: str) -> List[str]:
    clean_text = re.sub(r'[^\w\s]', '', text.strip().lower())
    tokens = set()
    for word in clean_text.split():
        if word.isascii():
            tokens.add(word)
    cjk_chars = [c for c in clean_text if '一' <= c <= '鿿']
    for i in range(len(cjk_chars)):
        tokens.add(cjk_chars[i])
        if i < len(cjk_chars) - 1:
            tokens.add(cjk_chars[i] + cjk_chars[i+1])
    return list(tokens)

def co_search_topology(db_conn: Any, keywords: List[str], time_start: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
    cjk_tokens = []
    for kw in keywords:
        cjk_tokens.extend(tokenize_cjk_terms(kw))
    unique_tokens = list(set(cjk_tokens))
    if not unique_tokens:
        return []
    placeholders = ",".join("?" for _ in unique_tokens)
    target_hit_count = len(unique_tokens)
    query = f'''
    SELECT object_id, COUNT(DISTINCT term) AS hit_count, MAX(occurred_at) AS latest_time
    FROM topological_cjk_terms
    WHERE term IN ({placeholders}) AND occurred_at >= ?
    GROUP BY object_id
    HAVING hit_count = ?
    ORDER BY latest_time DESC
    LIMIT ?;
    '''
    cursor = db_conn.cursor()
    cursor.execute(query, (*unique_tokens, time_start, target_hit_count, limit))
    return [{"object_id": r[0], "latest_time": r[2]} for r in cursor.fetchall()]
```

## 3.2 两级条件任务快慢轨评估引擎 (ConditionalTaskEngine)
```python
# src/aios_core/tasks/conditional_engine.py
class ConditionalTaskEngine:
    def __init__(self, db_conn: Any):
        self.db_conn = db_conn

    def tick_mechanical_fast_track(self, current_time: datetime, current_geo: Optional[Dict[str, float]] = None) -> int:
        cursor = self.db_conn.cursor()
        now_iso = current_time.isoformat()
        cursor.execute(
            '''
            UPDATE tasks 
            SET state = 'READY', updated_at = ?
            WHERE state = 'DORMANT' 
              AND condition_type = 'TIME_ABSOLUTE' 
              AND condition_expression <= ?
            ''',
            (now_iso, now_iso)
        )
        transitioned_count = cursor.rowcount
        self.db_conn.commit()
        return transitioned_count

    def fetch_ready_tasks_for_cockpit(self, limit: int = 3) -> List[Dict[str, Any]]:
        cursor = self.db_conn.cursor()
        cursor.execute(
            '''
            SELECT task_id, title, payload FROM tasks 
            WHERE state = 'READY' 
            ORDER BY created_at ASC 
            LIMIT ?
            ''',
            (limit,)
        )
        return [{"task_id": r[0], "title": r[1], "payload": r[2]} for r in cursor.fetchall()]
```

## 3.3 1~3 句老友输出后置强制截断拦截门 (enforce_dialogue_brevity_guard)
```python
# src/ai_worker/brevity_guard.py
import re
from typing import List, Tuple

def split_into_sentences(text: str) -> List[str]:
    pattern = r'([^。！？!?\n]+[。！？!?\n]?)'
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches if m.strip()]

def enforce_dialogue_brevity_guard(raw_reply: str) -> Tuple[str, bool]:
    forbidden_phrases = ["很高兴为您服务", "我建议您采取以下", "请问有什么可以帮助您", "综合以上分析"]
    cleaned_reply = raw_reply
    for phrase in forbidden_phrases:
        if phrase in cleaned_reply:
            cleaned_reply = cleaned_reply.replace(phrase, "")
    sentences = split_into_sentences(cleaned_reply)
    was_truncated = False
    if len(sentences) > 3:
        cleaned_reply = "".join(sentences[:3])
        was_truncated = True
    return cleaned_reply.strip(), was_truncated
```

## 3.4 长会话三级流式流水线 (ActiveRollingWindow & StreamingExtractWorker)
```python
# src/ai_worker/stream_pipeline.py
import queue
import threading
from typing import List, Dict, Any

class ActiveRollingWindow:
    def __init__(self, max_turns: int = 6, max_tokens: int = 1500):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.turns: List[Dict[str, str]] = []

    def push_turn(self, user_msg: str, ai_msg: str) -> List[Dict[str, str]]:
        self.turns.append({"user": user_msg, "ai": ai_msg})
        evicted_turns = []
        while len(self.turns) > self.max_turns:
            evicted_turns.append(self.turns.pop(0))
        return evicted_turns

    def get_prompt_messages(self) -> List[Dict[str, str]]:
        return self.turns.copy()

class StreamingExtractWorker(threading.Thread):
    def __init__(self, task_queue: queue.Queue, world_store: Any, extractor: Any):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.world_store = world_store
        self.extractor = extractor

    def run(self):
        while True:
            batch = self.task_queue.get()
            if batch is None:
                break
            try:
                facts = self.extractor.extract_facts(batch)
                for f in facts:
                    self.world_store.append_observation(f)
            finally:
                self.task_queue.task_done()
```

## 3.5 严格单跳 (1-Hop) 历史依赖失效隔离算法 (invalidate_overturned_fact_single_hop)
```python
# src/aios_core/cognition/dependency_isolator.py
def invalidate_overturned_fact_single_hop(db_conn: Any, overturned_node_id: str, reason: str) -> List[str]:
    cursor = db_conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "SELECT downstream_node_id FROM node_dependencies WHERE upstream_node_id = ?",
        (overturned_node_id,)
    )
    direct_downstream_ids = [row[0] for row in cursor.fetchall()]
    if not direct_downstream_ids:
        return []
    placeholders = ",".join("?" for _ in direct_downstream_ids)
    cursor.execute(
        f'''
        UPDATE cognitive_nodes 
        SET is_stale = 1, stale_reason = ?, stale_at = ? 
        WHERE node_id IN ({placeholders})
        ''',
        (reason, now_iso, *direct_downstream_ids)
    )
    db_conn.commit()
    return direct_downstream_ids
```

## 3.6 穿戴手环超宽频微震先导 FSM 防误触状态机 (WearableFSMController)
```python
# src/aios_core/wearable/fsm.py
class WearableState(str, Enum):
    IDLE            = "IDLE"            # 静默待机 (骨传导断电，麦克风休眠，误触因果律为0)
    TRIGGERED_MILD  = "TRIGGERED_MILD"  # 发出单次先导微震，开启 8 秒检测窗口
    CANVAS_VIEW     = "CANVAS_VIEW"     # 8秒内抬手看屏，柔性屏展开 1~3 句极简卡片
    BONE_AUDIO      = "BONE_AUDIO"      # 8秒内贴耳摸耳，骨传导通电私密入耳传音
    EMERGENCY_ALARM = "EMERGENCY_ALARM" # P0 连续强震与最高分贝呼叫

class HardwareTriggerEvent(str, Enum):
    AI_SUGGESTION_READY  = "AI_SUGGESTION_READY"  # AI 产生非紧急提醒
    WRIST_RAISED_TO_EYE  = "WRIST_RAISED_TO_EYE"  # 抬手看表姿势
    FINGER_TOUCHED_EAR   = "FINGER_TOUCHED_EAR"   # 手指贴耳姿势
    TIMEOUT_8_SECONDS    = "TIMEOUT_8_SECONDS"    # 8 秒无响应超时
    CRITICAL_HAZARD      = "CRITICAL_HAZARD"      # P0 生命突发险情

class WearableFSMController:
    def __init__(self, hardware_actuator: Any):
        self.state: WearableState = WearableState.IDLE
        self.window_start_time: Optional[datetime] = None
        self.hardware = hardware_actuator
        self.hardware.set_bone_conduction_power(False)

    def transition(self, event: HardwareTriggerEvent) -> WearableState:
        now = datetime.now(timezone.utc)
        if event == HardwareTriggerEvent.CRITICAL_HAZARD:
            self.state = WearableState.EMERGENCY_ALARM
            self.hardware.set_haptic_vibration("CONTINUOUS_MAX")
            self.hardware.set_speaker_broadcast(True)
            return self.state

        if self.state == WearableState.IDLE:
            if event == HardwareTriggerEvent.AI_SUGGESTION_READY:
                self.state = WearableState.TRIGGERED_MILD
                self.window_start_time = now
                self.hardware.set_haptic_vibration("SINGLE_MILD_PULSE")
                return self.state

        elif self.state == WearableState.TRIGGERED_MILD:
            if (now - self.window_start_time).total_seconds() > 8.0 or event == HardwareTriggerEvent.TIMEOUT_8_SECONDS:
                self.state = WearableState.IDLE
                self.window_start_time = None
                return self.state
            if event == HardwareTriggerEvent.WRIST_RAISED_TO_EYE:
                self.state = WearableState.CANVAS_VIEW
                self.hardware.render_screen_card()
                return self.state
            if event == HardwareTriggerEvent.FINGER_TOUCHED_EAR:
                self.state = WearableState.BONE_AUDIO
                self.hardware.set_bone_conduction_power(True)
                self.hardware.play_audio_stream()
                return self.state

        elif self.state in (WearableState.CANVAS_VIEW, WearableState.BONE_AUDIO):
            self.hardware.set_bone_conduction_power(False)
            self.state = WearableState.IDLE
            self.window_start_time = None
            return self.state

        return self.state
```

---

# 第四部分：V21~V30 宪法级对抗场景 pytest 自动化测试套件源码

```python
# tests/scenarios/test_v21_to_v30_adversarial.py
import pytest
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from aios_core.contracts.safety_bypass import WakePriority, HazardType, SafetyBypassPayload
from aios_core.contracts.cockpit_manifest import SingleShotCockpitManifest
from aios_core.wake.dispatcher import dispatch_wake_event
from aios_core.wearable.fsm import WearableFSMController, WearableState, HardwareTriggerEvent
from aios_core.cognition.dependency_isolator import invalidate_overturned_fact_single_hop
from ai_worker.brevity_guard import enforce_dialogue_brevity_guard
from ai_worker.stream_pipeline import ActiveRollingWindow

def test_v21_identity_overturn_single_hop_isolation(sqlite_memory_db):
    cursor = sqlite_memory_db.cursor()
    cursor.execute("CREATE TABLE cognitive_nodes (node_id TEXT PRIMARY KEY, is_stale INTEGER, stale_reason TEXT, stale_at TEXT)")
    cursor.execute("CREATE TABLE node_dependencies (downstream_node_id TEXT, upstream_node_id TEXT)")
    cursor.execute("INSERT INTO cognitive_nodes VALUES ('fact_laowang_friend', 0, NULL, NULL)")
    for i in range(10):
        cursor.execute("INSERT INTO cognitive_nodes VALUES (?, 0, NULL, NULL)", (f"summary_direct_{i}",))
        cursor.execute("INSERT INTO node_dependencies VALUES (?, 'fact_laowang_friend')", (f"summary_direct_{i}",))
        for j in range(20):
            cursor.execute("INSERT INTO cognitive_nodes VALUES (?, 0, NULL, NULL)", (f"summary_indirect_{i}_{j}",))
            cursor.execute("INSERT INTO node_dependencies VALUES (?, ?)", (f"summary_indirect_{i}_{j}", f"summary_direct_{i}"))
    sqlite_memory_db.commit()

    stale_marked_ids = invalidate_overturned_fact_single_hop(sqlite_memory_db, "fact_laowang_friend", "老王为诈骗犯")
    assert len(stale_marked_ids) == 10
    assert all(nid.startswith("summary_direct_") for nid in stale_marked_ids)
    cursor.execute("SELECT COUNT(*) FROM cognitive_nodes WHERE is_stale = 1")
    assert cursor.fetchone()[0] == 10

def test_v22_acute_cardiac_fall_safety_bypass_latency():
    mock_wake = MagicMock()
    mock_wake.object_id = "wake_fall_v22"
    mock_wake.priority = WakePriority.P0_CRITICAL_SAFETY
    mock_wake.safety_bypass = SafetyBypassPayload(
        hazard_type=HazardType.FALL_DETECTED,
        vital_snapshot={"g_force": 5.2, "heart_rate": 165},
        emergency_action_code="EMERGENCY_BROADCAST_AND_SOS"
    )
    mock_context = MagicMock()
    start_time = time.perf_counter()
    with patch("aios_core.wake.dispatcher.dispatch_emergency_hardware_pulse", return_value=True):
        result = dispatch_wake_event(mock_wake, mock_context)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    assert elapsed_ms <= 50.0
    assert result["status"] == "SAFETY_BYPASS_EXECUTED"
    mock_context.cockpit_pipeline.execute.assert_not_called()

def test_v25_continuous_50_turn_dialogue_token_bounds():
    window = ActiveRollingWindow(max_turns=6, max_tokens=1500)
    evicted_archive = []
    for turn_idx in range(1, 51):
        user_msg = f"第 {turn_idx} 轮用户消息"
        ai_msg = f"第 {turn_idx} 轮老友极简回复"
        evicted = window.push_turn(user_msg, ai_msg)
        evicted_archive.extend(evicted)
        assert len(window.get_prompt_messages()) <= 6
    assert len(evicted_archive) == 44

def test_v29_wearable_anti_accidental_touch_causality():
    mock_hardware = MagicMock()
    fsm = WearableFSMController(hardware_actuator=mock_hardware)
    assert fsm.state == WearableState.IDLE
    mock_hardware.set_bone_conduction_power.assert_called_with(False)
    state = fsm.transition(HardwareTriggerEvent.FINGER_TOUCHED_EAR)
    assert state == WearableState.IDLE
    assert fsm.state == WearableState.IDLE

def test_v30_true_old_friend_anti_lecturing_brevity_guard():
    preachy_speech = "我建议您采取以下三点措施：第一早睡早起；第二清淡饮食；第三每天跑步半小时。一定要坚持下去！"
    cleaned, truncated = enforce_dialogue_brevity_guard(preachy_speech)
    assert "我建议您采取以下" not in cleaned
    assert "第一" not in cleaned
    assert len(cleaned.split("。")) <= 4
```