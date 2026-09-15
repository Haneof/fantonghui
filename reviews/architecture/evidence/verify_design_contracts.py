import sys; sys.path.insert(0,'/home/user/fantonghui/src')
from datetime import datetime, timezone
from typing import Any, Literal, Union
from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator, Discriminator, field_validator
from aios_core.contracts.base import WorldObject
from aios_core.contracts.enums import ObjectType
from aios_core.contracts.time import TemporalExtent

now = datetime.now(timezone.utc)

# ---- A. 三个新对象（沿用设计书原文） ----
class Prediction(WorldObject):
    statement: str = Field(min_length=1, max_length=500)
    claimant: Literal["user","ai","external"]
    epistemic_status: Literal["said","believed","predicted","observed"]
    due: TemporalExtent
    falsification_test: str = Field(min_length=1)
    outcome: Literal["pending","confirmed","falsified","undecidable"] = "pending"
    decided_at: datetime | None = None
    decided_by: str | None = None
    downstream_refs: list[str] = Field(default_factory=list)

class CommunicationExperience(WorldObject):
    channel: Literal["speech","haptic","canvas","text"]
    sentences_emitted: int = Field(ge=0)
    tokens_emitted: int = Field(ge=0)
    user_interrupted: bool = False
    user_reply_latency_ms: int | None = Field(default=None, ge=0)
    style_tags: list[str] = Field(default_factory=list)
    didactic_flag: bool = False
    rapport_delta: float = Field(default=0.0, ge=-1.0, le=1.0)

def mk(cls, **kw):
    base = dict(object_id="pred_x", object_type=ObjectType.CLAIM, subject_id="u1",
                learned_at=now, created_by="tester")
    base.update(kw); return cls(**base)

p = mk(Prediction, statement="下周会下雨", claimant="user", epistemic_status="predicted",
       due=TemporalExtent.unknown_time(), falsification_test="7日内无降水记录")
print("A1 Prediction 构造 OK; extra=forbid ->", end=" ")
try:
    mk(Prediction, statement="x", claimant="user", epistemic_status="predicted",
       due=TemporalExtent.unknown_time(), falsification_test="t", bogus=1); print("FAIL(未拦截)")
except Exception: print("拦截成功")
print("A2 非法 epistemic_status ->", end=" ")
try:
    mk(Prediction, statement="x", claimant="user", epistemic_status="fact",
       due=TemporalExtent.unknown_time(), falsification_test="t"); print("FAIL(未拦截)")
except Exception: print("拦截成功")
c = mk(CommunicationExperience, object_id="comm_x", channel="speech",
       sentences_emitted=2, tokens_emitted=40, rapport_delta=0.1)
print("A3 rapport_delta 越界 ->", end=" ")
try:
    mk(CommunicationExperience, object_id="c", channel="speech", sentences_emitted=1,
       tokens_emitted=1, rapport_delta=2.0); print("FAIL(未拦截)")
except Exception: print("拦截成功")

# ---- C. TriggerExpression 判别式联合 ----
class TimeReached(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["time_reached"] = "time_reached"
    at: datetime | None = None
    relative_to: str | None = None
    offset_seconds: int | None = None
    timezone_name: str = "Asia/Shanghai"
class ContextMatched(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["context_matched"] = "context_matched"
    predicate: str = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list)
    min_duration_seconds: int = 0
    @field_validator("predicate")
    @classmethod
    def predicate_must_be_nonblank(cls, v):
        if not v.strip(): raise ValueError("predicate must not be blank")
        return v
class EventOccurred(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["event_occurred"] = "event_occurred"
    subject_id: str | None = None
    event_types: list[str] = Field(default_factory=list)
    object_type_filter: list[str] = Field(default_factory=list)
class DependencyReady(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["dependency_ready"] = "dependency_ready"
    dependency_ids: list[str] = Field(min_length=1)
    require_all: bool = True
TriggerClause = Annotated[Union[TimeReached,ContextMatched,EventOccurred,DependencyReady],
                          Discriminator("kind")]
class TriggerExpression(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    expression_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    op: Literal["and","or"] = "and"
    clauses: list[TriggerClause] = Field(min_length=1, max_length=8)
    ttl: datetime | None = None
    compiled_at: datetime | None = None
    subscribed_terms: list[str] = Field(default_factory=list)

te = TriggerExpression(expression_id="te1", task_id="task1", op="and", clauses=[
    {"kind":"context_matched","predicate":'gps.in("商圈A")',"dimensions":["location"]},
    {"kind":"time_reached","at":now},
    {"kind":"dependency_ready","dependency_ids":["dep1"]},
])
print("C1 判别式联合分派 OK ->", [type(c).__name__ for c in te.clauses])
print("C2 clauses 为空 ->", end=" ")
try:
    TriggerExpression(expression_id="e",task_id="t",clauses=[]); print("FAIL(未拦截)")
except Exception: print("拦截成功")
print("C3 未知 kind ->", end=" ")
try:
    TriggerExpression(expression_id="e",task_id="t",clauses=[{"kind":"vibes"}]); print("FAIL(未拦截)")
except Exception: print("拦截成功")
print("C4 空 predicate ->", end=" ")
try:
    TriggerExpression(expression_id="e",task_id="t",
                      clauses=[{"kind":"context_matched","predicate":"  "}]); print("FAIL(未拦截)")
except Exception: print("拦截成功")

# ---- D. CockpitManifest 段序与预算校验 ----
class CockpitTier(str):
    pass
from enum import Enum
class Tier(str, Enum):
    SAFETY="safety"; ROUTINE="routine"; REVIEW="review"
TIER_TOKEN_BUDGET = {Tier.SAFETY:512, Tier.ROUTINE:2048, Tier.REVIEW:8192}
class ManifestSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Literal[1,2,3,4]
    name: Literal["self_slice","rapport_model","stance_tone","wake_and_world"]
    tokens: int = Field(ge=0)
    payload: dict[str, Any]
    refs: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
class CockpitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    manifest_id: str; session_id: str; wake_id: str
    tier: Tier
    sections: list[ManifestSection] = Field(min_length=4, max_length=4)
    ready_task_ids: list[str] = Field(default_factory=list)
    capability_registry: list[str] = Field(default_factory=list)
    total_tokens: int = Field(ge=0)
    budget_truncated: bool = False
    assembled_at: datetime
    @model_validator(mode="after")
    def validate_step_order(self):
        expected = [(i, STEP_NAMES[i]) for i in (1,2,3,4)]
        got = [(s.step, s.name) for s in self.sections]
        if got != expected:
            raise ValueError(f"四步序段序不可颠倒：期望 {expected}，实得 {got}")
        limit = TIER_TOKEN_BUDGET[self.tier]
        if self.total_tokens > limit and not self.budget_truncated:
            raise ValueError(f"超出 {self.tier} 档预算 {limit} 却未标记截断")
        return self
STEP_NAMES={1:"self_slice",2:"rapport_model",3:"stance_tone",4:"wake_and_world"}
names=["self_slice","rapport_model","stance_tone","wake_and_world"]
def sec(step,name,tok): return ManifestSection(step=step,name=name,tokens=tok,payload={})
good = CockpitManifest(manifest_id="m1",session_id="s1",wake_id="w1",tier=Tier.ROUTINE,
    sections=[sec(1,names[0],300),sec(2,names[1],300),sec(3,names[2],200),sec(4,names[3],600)],
    total_tokens=1400, assembled_at=now)
print("D1 正确段序+预算内 OK; total_tokens =", good.total_tokens)
print("D2 段序颠倒(语调置于第1步) ->", end=" ")
try:
    CockpitManifest(manifest_id="m",session_id="s",wake_id="w",tier=Tier.ROUTINE,
        sections=[sec(1,"stance_tone",100),sec(2,names[1],100),sec(3,names[0],100),sec(4,names[3],100)],
        total_tokens=400, assembled_at=now); print("FAIL(未拦截)")
except Exception: print("拦截成功")
print("D3 ROUTINE 超 2048 未标截断 ->", end=" ")
try:
    CockpitManifest(manifest_id="m",session_id="s",wake_id="w",tier=Tier.ROUTINE,
        sections=[sec(i+1,names[i],900) for i in range(4)], total_tokens=3600, assembled_at=now)
    print("FAIL(未拦截)")
except Exception: print("拦截成功")
print("D4 超预算但已标 truncated ->", end=" ")
m=CockpitManifest(manifest_id="m",session_id="s",wake_id="w",tier=Tier.SAFETY,
    sections=[sec(i+1,names[i],200) for i in range(4)], total_tokens=800,
    budget_truncated=True, assembled_at=now)
print("放行 OK (budget_truncated =", m.budget_truncated, ")")
print("D5 缺一个 section ->", end=" ")
try:
    CockpitManifest(manifest_id="m",session_id="s",wake_id="w",tier=Tier.ROUTINE,
        sections=[sec(i+1,names[i],100) for i in range(3)], total_tokens=300, assembled_at=now)
    print("FAIL(未拦截)")
except Exception: print("拦截成功")
