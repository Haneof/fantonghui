"""
V3 Edge Lightweight Ingest Contracts
M0-007R + M1-018 + M0-023 + M1-019

独立首席架构师重构：防存储爆炸核心
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from enum import StrEnum
from typing import Optional, List
from datetime import datetime

class SignalQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOISE = "NOISE"

class IMUState(StrEnum):
    STILL = "STILL"
    WALK = "WALK"
    RUN = "RUN"
    FALL_SUSPECTED = "FALL_SUSPECTED"

class SourceKind(StrEnum):
    GPS = "GPS"
    HR = "HR"
    IMU = "IMU"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    CHAT = "CHAT"
    APP = "APP"

class ObservationEdge(BaseModel):
    """M0-007R: 边缘轻量化后的Observation，物理层永存"""
    object_id: str
    object_type: str = "observation"
    subject_id: str
    occurred_at: datetime
    learned_at: datetime
    recorded_at: datetime
    source_kind: SourceKind
    modality: str
    source_confidence: float = Field(ge=0, le=1, description="端侧模型置信")
    signal_quality: SignalQuality
    value: dict = Field(description="宏观状态+显著波形，非原始高频")
    unit: Optional[str] = None
    data_quality: str = "RAW"
    raw_locator: Optional[str] = Field(default=None, description="原始大文件locator，不直接存DB")
    voiceprint_ref: Optional[str] = None
    image_semantic: Optional[str] = None
    deletion_log_ref: Optional[str] = None
    revision: int = 1
    status: str = "ACTIVE"

class Voiceprint(BaseModel):
    """M0-023: 声纹d-vector 256维≈1KB，6个月冷热淘汰"""
    voiceprint_id: str
    d_vector: List[float] = Field(min_length=256, max_length=256)
    speaker_ref: Optional[str] = None  # P001
    first_seen: datetime
    last_seen: datetime
    contact_count: int = 0
    is_core_protected: bool = Field(default=False, description="被FACT/RELATION引用永不淘汰")
    tombstone_until: Optional[datetime] = Field(default=None, description="淘汰后墓碑128维24个月")

class VoiceprintTombstone(BaseModel):
    """淘汰后墓碑，128维，24个月"""
    tombstone_id: str
    original_voiceprint_id: str
    d_vector_128: List[float] = Field(min_length=128, max_length=128)
    speaker_ref: Optional[str]
    created_at: datetime
    expires_at: datetime

class DeletionLog(BaseModel):
    """M1-019: 清洗审计，防误删"""
    log_id: str
    deleted_object_ids: List[str]
    reason: str  # daily_purification_noise / expired_raw_ring
    evidence_set_id: Optional[str]
    model_version: str
    created_at: datetime
    archived_locators: List[str] = Field(description="归档位置，非物理删除")

class InterpretationLayer(BaseModel):
    """M0-024: 解释层，修复93条vs31条之一矛盾，物理层永不改"""
    interpretation_id: str
    target_object_id: str  # 指向过去时空切片
    target_time_range: tuple[datetime, datetime]  # 过去区间
    content: dict  # {"emotion": "极度憋屈与愤怒"}
    valid_time: tuple[datetime, datetime]  # 过去区间
    learned_at: datetime  # T_now
    asserted_at: datetime  # T_now
    recorded_at: datetime  # T_now
    source_refs: List[str]  # 今天原话
    created_by: str = "ai"

# SQL DDL as constants for reference
SQL_DDL = """
CREATE TABLE observations_edge (
  object_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  learned_at TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  source_kind TEXT NOT NULL,
  modality TEXT NOT NULL,
  source_confidence REAL,
  signal_quality TEXT,
  value_json JSONB NOT NULL,
  voiceprint_ref TEXT,
  image_semantic TEXT,
  raw_locator TEXT,
  revision INT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_obs_edge_time ON observations_edge(subject_id, occurred_at);
CREATE INDEX idx_obs_edge_kind ON observations_edge(source_kind, signal_quality);

CREATE TABLE voiceprints (
  voiceprint_id TEXT PRIMARY KEY,
  speaker_ref TEXT,
  d_vector BLOB,
  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  contact_count INT,
  is_core_protected BOOLEAN DEFAULT FALSE,
  tombstone_until TIMESTAMPTZ
);

CREATE TABLE voiceprint_tombstones (
  tombstone_id TEXT PRIMARY KEY,
  original_voiceprint_id TEXT,
  d_vector_128 BLOB,
  speaker_ref TEXT,
  created_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

CREATE TABLE deletion_logs (
  log_id TEXT PRIMARY KEY,
  deleted_ids JSONB,
  reason TEXT,
  evidence_set_id TEXT,
  model_version TEXT,
  created_at TIMESTAMPTZ,
  archived_locators JSONB
);

CREATE TABLE interpretation_layer (
  interpretation_id TEXT PRIMARY KEY,
  target_object_id TEXT,
  target_time_range TSTZRANGE,
  content JSONB,
  valid_time TSTZRANGE,
  learned_at TIMESTAMPTZ,
  asserted_at TIMESTAMPTZ,
  recorded_at TIMESTAMPTZ,
  source_refs JSONB,
  created_by TEXT
);
CREATE INDEX idx_interp_target ON interpretation_layer(target_object_id);
CREATE INDEX idx_interp_valid ON interpretation_layer USING GIST (valid_time);
"""
