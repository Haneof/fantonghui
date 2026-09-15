"""
V3 Cockpit Manifest + Four-Step + Three-Level Pipeline Contracts
M2-009R + M2-012R + M2-016 + M2-017 + M2-018/019/020

独立首席架构师重构：1秒首字核心，解决多轮ReAct+无三级流水线
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class WakeSlice(BaseModel):
    type: str
    rule: str
    evidence_refs: List[str]
    first_hit: datetime
    last_hit: datetime
    count: int
    peak_value: Optional[float] = None

class IdentitySlice(BaseModel):
    dim_ai_identity: dict
    dim_ai_promises: dict
    bottom_line: List[str]  # 底线原则

class RapportModel(BaseModel):
    """DIM_AI_RAPPORT 动态关系模型"""
    user_id: str
    thickness: float = Field(ge=0, le=1, description="关系厚度")
    is_in_conflict: bool = False
    last_conflict_at: Optional[datetime] = None
    tacit_coefficient: float = Field(ge=0, le=1, description="默契系数")
    recent_attitude: str = Field(description="热情倾诉/抵触不耐烦")
    interaction_count: int = 0

class CapabilityItem(BaseModel):
    capability_id: str
    input_schema: dict
    output_schema: dict
    permission: str
    side_effect: str

class TriggerCriteria(BaseModel):
    """M2-005R: 条件驱动DSL"""
    type: str = Field(description="time_reached / context_matched / event_occurred / dependency_ready")
    params: dict
    created_at: datetime

class TaskConditional(BaseModel):
    task_id: str
    task_type: str
    goal: str
    reason: str
    trigger_criteria: TriggerCriteria
    priority: int
    status: str
    next_wake_time: Optional[datetime] = None
    deadline: Optional[datetime] = None
    review_interval: str = "14d"
    max_wait: str = "30d"
    related_event_ids: List[str] = []
    execution_log: List[dict] = []

class CockpitManifest(BaseModel):
    """M2-009R: Single-Shot Cockpit Manifest，一次性交付"""
    wake_reason: WakeSlice = Field(description="第一指针，严禁无差别全量扫描")
    ai_identity_slice: IdentitySlice = Field(description="mirror第一步")
    rapport_model: RapportModel = Field(description="rapport第二步")
    attitude_instruction: dict = Field(description="attitude第三步，姿态基调")
    time_location: dict = Field(description="world第四步，时间/地点/人物/主事件，带age/stale")
    capability_registry: List[CapabilityItem]
    ready_tasks: List[TaskConditional] = Field(description="已过滤就绪任务，仅2-3条，禁止全量")
    mind_steps: List[str] = Field(default=["mirror", "rapport", "attitude", "world"], description="四步法则强制顺序，不可颠倒")
    token_budget: dict = Field(default={"trigger":1500,"work":2000,"recall":5000,"rolling":2500,"identity":1000,"total":12000}, description="硬预算12K")
    world_revision: int
    knowledge_cutoff: datetime
    context_4_layers: dict = Field(description="触发指针1.5K→工作状态2K→主动检索记忆5K→近期缓冲2.5K")

class FourStepComplianceLog(BaseModel):
    session_id: str
    step1_mirror: bool
    step2_rapport: bool
    step3_attitude: bool
    step4_world: bool
    order_valid: bool
    violations: List[str]
    token_in: int
    token_out: int
    is_multi_round: bool = Field(description="是否≥2次串行模型往返，若是则违宪")

class RollingWindow(BaseModel):
    """M2-016: 前台活跃滑动窗口"""
    window_id: str
    messages: List[dict]  # 最近5-8轮，约1500 tokens
    token_count: int = Field(le=1500)
    created_at: datetime

class StreamingSlice(BaseModel):
    """M2-017: 后台增量切片萃取"""
    slice_id: str
    source_message_ids: List[str]
    extracted_claims: List[str]
    extracted_events: List[str]
    dimension_refs: List[str]
    created_at: datetime

class CommunicationExperience(BaseModel):
    """M2-020: 沟通经验维度"""
    experience_id: str
    method: str = Field(description="损友/正经/幽默/调侃")
    tone: str
    user_reaction: str = Field(description="积极/抵触/无视/大笑/反感")
    context: dict
    created_at: datetime

class MotorFSMState(BaseModel):
    """M2-018: 马达震动先导FSM零误触"""
    state: str = Field(description="IDLE / TRIGGERED / CHANNEL_A / CHANNEL_B / TIMEOUT")
    triggered_at: Optional[datetime] = None
    window_until: Optional[datetime] = None
    priority: str = Field(description="NORMAL / EMERGENCY")
    vibration_semantic: str = Field(description="单次微震=常规，连续强震=紧急")
    channel: Optional[str] = None  # A抬手看屏 / B按耳骨传导 / C超时

# Algorithms

COCKPIT_ALGORITHM = """
def assemble_cockpit(wake: Wake, now: datetime, context: dict) -> CockpitManifest:
    # 1. 机械触发判定 + Wake形成 ≤20ms 本地SQLite
    # 2. 上下文组装四层，硬预算12K，召回结果在Wake形成时预计算，非在语音路径上
    wake_slice = get_wake_slice(wake)  # 300 tokens
    work_slice = get_work_slice(now, context)  # 800 tokens
    recall_slice = co_search_with_budget(wake, budget=5000)  # 2000 tokens，并行
    rolling_slice = get_rolling_window(limit=8, budget=2500)  # 1500 tokens
    identity_slice = get_identity_slice()  # 500 tokens
    rapport_slice = get_rapport_slice()  # 500 tokens
    ready_tasks = inspect_ready(now, context)  # 仅2-3条，400 tokens
    caps = get_capability_registry()
    manifest = CockpitManifest(
        wake_reason=wake_slice,
        ai_identity_slice=identity_slice,
        rapport_model=rapport_slice,
        attitude_instruction=infer_attitude(identity_slice, rapport_slice),
        time_location=work_slice,
        capability_registry=caps,
        ready_tasks=ready_tasks,
        mind_steps=["mirror","rapport","attitude","world"],
        token_budget={...},
        world_revision=current_world_revision(),
        knowledge_cutoff=now,
        context_4_layers={"trigger":wake_slice,"work":work_slice,"recall":recall_slice,"rolling":rolling_slice}
    )
    compliance = check_four_step_order(manifest)
    if not compliance.order_valid or compliance.is_multi_round:
        raise ViolationError("Four-step order violated or multi-round", compliance.violations)
    return manifest

def check_four_step_order(manifest: CockpitManifest) -> FourStepComplianceLog:
    violations=[]
    if manifest.mind_steps != ["mirror","rapport","attitude","world"]:
        violations.append("mind_steps order must be mirror->rapport->attitude->world")
    if manifest.time_location and not manifest.ai_identity_slice:
        violations.append("world loaded before identity, violates mirror first")
    # 检查是否≥2次串行模型往返
    is_multi_round = count_model_roundtrips() >= 2
    if is_multi_round:
        violations.append("multi-round ReAct violates Single-Shot Cockpit, P50>1s impossible")
    return FourStepComplianceLog(..., order_valid=len(violations)==0, violations=violations, is_multi_round=is_multi_round)
"""

PIPELINE_ALGORITHM = """
def active_rolling_window_assembler(conversation: List[Message]) -> RollingWindow:
    recent = conversation[-8:]
    token_count = sum(count_tokens(m) for m in recent)
    while token_count > 1500 and len(recent) > 5:
        recent = recent[1:]
        token_count = sum(count_tokens(m) for m in recent)
    return RollingWindow(...)

def background_streaming_extractor(conversation: List[Message], last_extracted_idx: int):
    if len(conversation) - last_extracted_idx >= 5 or is_topic_shift(conversation):
        slice_to_extract = conversation[last_extracted_idx:]
        claims = llm_batch_extract_claims(slice_to_extract)  # 一次性批处理，非每轮一次
        events = llm_batch_extract_events(slice_to_extract)
        for c in claims:
            dimension_id = route_to_dimension(c)
            membership_add(dimension_id, c)
        return StreamingSlice(...)
    return None

def proactive_associative_recall(query: str) -> List[dict]:
    entities = co_search([query], limit=5)
    events = co_search([query, "事件"], limit=5)
    promises = query_promises(query)
    psych = get_psych_baseline()
    return [{"type":"entity","data":entities},{"type":"event","data":events},{"type":"promise","data":promises},{"type":"psych","data":psych}]
"""

SQL_DDL = """
CREATE TABLE tasks_conditional (
  task_id TEXT PRIMARY KEY,
  task_type TEXT,
  trigger_type TEXT,
  trigger_params JSONB,
  priority INT,
  status TEXT,
  next_wake_time TIMESTAMPTZ,
  deadline TIMESTAMPTZ,
  review_interval INTERVAL DEFAULT '14 days',
  max_wait INTERVAL DEFAULT '30 days',
  created_at TIMESTAMPTZ,
  last_checked TIMESTAMPTZ
);
CREATE INDEX idx_task_condition ON tasks_conditional(trigger_type, next_wake_time, status);
CREATE INDEX idx_task_geo ON tasks_conditional USING GIN ((trigger_params->'geo_fence'));
CREATE INDEX idx_task_event ON tasks_conditional USING GIN ((trigger_params->'event_type'));

CREATE TABLE cockpit_compliance_logs (
  session_id TEXT PRIMARY KEY,
  step1_mirror BOOLEAN,
  step2_rapport BOOLEAN,
  step3_attitude BOOLEAN,
  step4_world BOOLEAN,
  order_valid BOOLEAN,
  violations JSONB,
  token_in INT,
  token_out INT,
  is_multi_round BOOLEAN,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE rolling_windows (
  window_id TEXT PRIMARY KEY,
  messages JSONB,
  token_count INT,
  created_at TIMESTAMPTZ
);

CREATE TABLE communication_experiences (
  experience_id TEXT PRIMARY KEY,
  method TEXT,
  tone TEXT,
  user_reaction TEXT,
  context JSONB,
  created_at TIMESTAMPTZ
);

CREATE TABLE wearable_fsm (
  state TEXT PRIMARY KEY,
  triggered_at TIMESTAMPTZ,
  window_until TIMESTAMPTZ,
  priority TEXT,
  vibration_semantic TEXT,
  channel TEXT
);
"""
