"""SIM-FEEDER-001 海量虚拟人生底层数据直写入库与容量测算引擎.

依据最高指令长（老大）核心训示：
1. 坚决废除无意义中间压缩文件，千人千面 3 年底层基础数据直接注入 SQLiteWorldStore；
2. 五大底层基础数据源：
   - 传感器（SENSOR）：心率、步数、睡眠、体温等；
   - MIC 录音转文字（MIC_TRANSCRIPTION）：环境声音、对话切片转文字；
   - 环境照片转文本描述（CAMERA_CAPTION）：摄像头抓拍画面文字语义描述；
   - APP 真实数据（APP_DATA）：社交、消费、购物、日程、日历、记事本等；
   - 与用户的真实日常聊天（USER_CHAT）：日常吐槽、咨询、倾诉与互动；
3. 出题人核心度量：精确统计单人 3 年全量基础数据在 SQLite 数据库中的物理存储容量（MB/KB）与各类型占比；
4. 做题人接口：提供按日期切片与流式重放，供 AIOS 原生大脑逐日总结、高阶认知提炼与系统看板/Token 优化。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

from aios_core.contracts.enums import ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent, as_utc, utc_now
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


class RawStreamKind(str, Enum):
    """五大底层基础数据流类型（老大钦定）."""
    SENSOR = "sensor"                      # 物理传感器（心率、步数、睡眠、体温等）
    MIC_TRANSCRIPTION = "mic_transcription" # MIC 录音与环境对话转文字
    CAMERA_CAPTION = "camera_caption"       # 环境照片抓拍画面转文字语义描述
    APP_DATA = "app_data"                   # 社交、消费账单、购物、日程、日历、记事本等
    USER_CHAT = "user_chat"                 # 与用户的真实日常双向聊天流


@dataclass
class StorageCapacityReport:
    """单人基础数据落库存储容量测算报告."""
    subject_id: str
    db_path: str
    total_file_bytes: int
    total_file_kb: float
    total_file_mb: float
    total_observations: int
    total_commits: int
    category_counts: dict[str, int]
    category_payload_bytes: dict[str, int]
    time_span_days: int
    daily_avg_bytes: float
    daily_avg_observations: float

    def summary_markdown(self) -> str:
        """生成 Markdown 格式的存储容量测算报告."""
        md = [
            f"# 虚拟人 [{self.subject_id}] 3年存储容量测算报告",
            f"- **SQLite 数据库文件路径**: `{self.db_path}`",
            f"- **物理磁盘占用**: **{self.total_file_mb:.2f} MB** ({self.total_file_kb:.1f} KB / {self.total_file_bytes:,} 字节)",
            f"- **覆盖时间跨度**: **{self.time_span_days} 天**",
            f"- **基础观测总数**: **{self.total_observations:,} 条**",
            f"- **日均增量数据**: **{self.daily_avg_observations:.1f} 条/天** (~{self.daily_avg_bytes / 1024:.2f} KB/天)",
            "",
            "### 五大底层数据流分布与容量占比",
            "| 数据流类型 | 记录条数 | Payload 字节数 (Est) | 记录占比 | Payload 占比 |",
            "|---|:---:|:---:|:---:|:---:|",
        ]
        total_payload = sum(self.category_payload_bytes.values()) or 1
        total_cnt = self.total_observations or 1
        for cat in RawStreamKind:
            cnt = self.category_counts.get(cat.value, 0)
            p_bytes = self.category_payload_bytes.get(cat.value, 0)
            cnt_pct = (cnt / total_cnt) * 100
            byte_pct = (p_bytes / total_payload) * 100
            md.append(f"| `{cat.value}` | {cnt:,} | {p_bytes:,} B ({p_bytes/1024:.1f} KB) | {cnt_pct:.1f}% | {byte_pct:.1f}% |")
        
        return "\n".join(md)


class MassiveLifeStoreFeeder:
    """海量人生底层基础数据直写器与容量测算器."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteWorldStore(str(self.db_path))

    @staticmethod
    def resolve_subject_store_path(base_dir: str | Path, subject_id: str) -> Path:
        """根据 subject_id 映射独立的 SQLite 数据库路径 (一人一库硬隔离)."""
        return Path(base_dir) / "worlds" / f"{subject_id}.db"

    def record_raw_observation(
        self,
        *,
        subject_id: str,
        stream_kind: RawStreamKind | str,
        content: Any,
        occurred_at: datetime,
        modality: str = "text",
        unit: str | None = None,
        raw_metadata: dict[str, Any] | None = None,
        source_class: SourceClass | None = None,
    ) -> Observation:
        """记录单条原始基础观测并立即写入数据库."""
        obs = self._build_observation(
            subject_id=subject_id,
            stream_kind=stream_kind,
            content=content,
            occurred_at=occurred_at,
            modality=modality,
            unit=unit,
            raw_metadata=raw_metadata,
        )
        self.commit_observations(subject_id, [obs], source_class=source_class)
        return obs

    def _build_observation(
        self,
        *,
        subject_id: str,
        stream_kind: RawStreamKind | str,
        content: Any,
        occurred_at: datetime,
        modality: str,
        unit: str | None = None,
        raw_metadata: dict[str, Any] | None = None,
    ) -> Observation:
        kind_str = stream_kind.value if isinstance(stream_kind, RawStreamKind) else str(stream_kind)
        t_aware = as_utc(occurred_at, "occurred_at")
        meta = raw_metadata.copy() if raw_metadata else {}
        meta["raw_stream_kind"] = kind_str

        return Observation(
            object_id=new_object_id(ObjectType.OBSERVATION),
            subject_id=subject_id,
            revision=1,
            occurred=TemporalExtent.point(t_aware),
            learned_at=t_aware,
            recorded_at=t_aware,
            source_kind=kind_str,
            modality=modality,
            value=content,
            unit=unit,
            metadata=meta,
            created_by="life_stream_feeder",
        )

    def commit_observations(
        self,
        subject_id: str,
        observations: Sequence[Observation],
        *,
        reason: str = "Ingest raw multi-modal life stream",
        source_class: SourceClass | None = None,
    ) -> None:
        """批量提交观测对象到当前独立数据库 (事务级追加，绝不覆盖历史)."""
        if not observations:
            return

        inferred_source = source_class
        if inferred_source is None:
            kind = observations[0].source_kind
            if kind == RawStreamKind.SENSOR.value:
                inferred_source = SourceClass.SENSOR
            elif kind == RawStreamKind.USER_CHAT.value:
                inferred_source = SourceClass.USER
            else:
                inferred_source = SourceClass.AI_COGNITION

        # 分批 commit，避免单次事务过大 (每批最多 500 条)
        chunk_size = 500
        for i in range(0, len(observations), chunk_size):
            chunk = observations[i : i + chunk_size]
            op = OperationRequest(
                operation_id=new_operation_id(),
                operation_name="observation.bulk_ingest",
                expected_world_revision=self.store.current_world_revision(),
                reason=reason,
                idempotency_key=f"ingest_{subject_id}_{uuid.uuid4().hex[:12]}_{i}",
                source_class=inferred_source,
            )
            self.store.commit(chunk, op)

    def measure_storage_capacity(self, subject_id: str) -> StorageCapacityReport:
        """精准统计该虚拟人专属 SQLite 数据库的磁盘占用与容量指标 (老大切实关注项)."""
        if not self.db_path.exists():
            return StorageCapacityReport(
                subject_id=subject_id,
                db_path=str(self.db_path),
                total_file_bytes=0,
                total_file_kb=0.0,
                total_file_mb=0.0,
                total_observations=0,
                total_commits=0,
                category_counts={},
                category_payload_bytes={},
                time_span_days=0,
                daily_avg_bytes=0.0,
                daily_avg_observations=0.0,
            )

        file_bytes = self.db_path.stat().st_size
        # 兼容 WAL 模式下的 wal 与 shm 临时文件尺寸
        wal_path = self.db_path.with_suffix(".db-wal")
        shm_path = self.db_path.with_suffix(".db-shm")
        if wal_path.exists():
            file_bytes += wal_path.stat().st_size
        if shm_path.exists():
            file_bytes += shm_path.stat().st_size

        cat_counts: dict[str, int] = {}
        cat_payload_bytes: dict[str, int] = {}
        min_date: datetime | None = None
        max_date: datetime | None = None
        total_obs = 0

        # 从 SQLite 底层提取真实统计
        with self.store._connection() as conn:
            # 统计总 commits
            commits_row = conn.execute("SELECT COUNT(*) AS cnt FROM world_commits").fetchone()
            total_commits = commits_row["cnt"] if commits_row else 0

            # 统计 object_revisions 中各 raw_stream_kind 的分布
            rows = conn.execute(
                """
                SELECT payload_json, learned_at
                FROM object_revisions
                WHERE object_type = 'observation' AND subject_id = ?
                """,
                (subject_id,),
            ).fetchall()

            for row in rows:
                total_obs += 1
                payload_str = row["payload_json"]
                p_len = len(payload_str.encode("utf-8"))
                dt_str = row["learned_at"]
                try:
                    dt = datetime.fromisoformat(dt_str)
                    if min_date is None or dt < min_date:
                        min_date = dt
                    if max_date is None or dt > max_date:
                        max_date = dt
                except Exception:
                    pass

                try:
                    p = json.loads(payload_str)
                    sk = p.get("source_kind", "unknown")
                except Exception:
                    sk = "unknown"

                cat_counts[sk] = cat_counts.get(sk, 0) + 1
                cat_payload_bytes[sk] = cat_payload_bytes.get(sk, 0) + p_len

        days = 1
        if min_date and max_date and max_date > min_date:
            days = max(1, (max_date - min_date).days + 1)

        return StorageCapacityReport(
            subject_id=subject_id,
            db_path=str(self.db_path),
            total_file_bytes=file_bytes,
            total_file_kb=file_bytes / 1024.0,
            total_file_mb=file_bytes / (1024.0 * 1024.0),
            total_observations=total_obs,
            total_commits=total_commits,
            category_counts=cat_counts,
            category_payload_bytes=cat_payload_bytes,
            time_span_days=days,
            daily_avg_bytes=file_bytes / days if days else 0.0,
            daily_avg_observations=total_obs / days if days else 0.0,
        )

    def query_daily_observations(
        self,
        subject_id: str,
        target_date_iso: str,
    ) -> list[dict[str, Any]]:
        """为做题人 AIOS 大脑提供：查询指定日期（YYYY-MM-DD）的全量基础多模态事实流."""
        prefix = target_date_iso[:10]
        results = []
        with self.store._connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM object_revisions
                WHERE object_type = 'observation' 
                  AND subject_id = ?
                  AND learned_at LIKE ?
                ORDER BY learned_at ASC
                """,
                (subject_id, f"{prefix}%"),
            ).fetchall()
            for r in rows:
                try:
                    results.append(json.loads(r["payload_json"]))
                except Exception:
                    continue
        return results
