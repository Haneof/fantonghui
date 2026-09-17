"""SIM-FEEDER-001 海量虚拟人生底层数据直写入库与容量测算引擎.

该 feeder 只负责把底层原始生活流可靠写入 World/Data Plane；它不承担高阶认知。
关键纪律：
1. occurred_at（发生）/ learned_at（获知）/ recorded_at（写入）严格分离；
2. 原始 MIC/CAMERA/APP/SENSOR 流不得在缺省情况下冒充 AI_COGNITION；
3. 同一原始输入 replay 必须命中稳定 observation identity，而不是重复制造对象；
4. “某日生活流”按 occurred time 查询，不按 learned time 偷换时间语义。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from aios_core.contracts.enums import SourceClass
from aios_core.contracts.ids import new_operation_id
from aios_core.contracts.models import Observation
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.time import TemporalExtent, as_utc, utc_now
from aios_core.storage.idempotency import canonical_json_dumps
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc


class RawStreamKind(str, Enum):
    """五大底层基础数据流类型。"""

    SENSOR = "sensor"
    MIC_TRANSCRIPTION = "mic_transcription"
    CAMERA_CAPTION = "camera_caption"
    APP_DATA = "app_data"
    USER_CHAT = "user_chat"


@dataclass
class StorageCapacityReport:
    """单人基础数据落库存储容量测算报告。"""

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
            md.append(
                f"| `{cat.value}` | {cnt:,} | {p_bytes:,} B ({p_bytes/1024:.1f} KB) | "
                f"{cnt_pct:.1f}% | {byte_pct:.1f}% |"
            )
        return "\n".join(md)


class MassiveLifeStoreFeeder:
    """海量人生底层基础数据直写器与容量测算器。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteWorldStore(str(self.db_path))

    @staticmethod
    def resolve_subject_store_path(base_dir: str | Path, subject_id: str) -> Path:
        return Path(base_dir) / "worlds" / f"{subject_id}.db"

    @staticmethod
    def _stable_observation_identity(
        *,
        subject_id: str,
        stream_kind: str,
        content: Any,
        occurred_at: datetime,
        modality: str,
        unit: str | None,
        raw_metadata: dict[str, Any],
    ) -> tuple[str, str]:
        """Return deterministic object id + full digest for one raw fact.

        learned_at / recorded_at are deliberately excluded: replaying the same external
        fact tomorrow must still address the same raw observation rather than creating a
        second fact merely because ingestion happened at a different wall-clock time.
        """

        identity = {
            "subject_id": subject_id,
            "stream_kind": stream_kind,
            "content": content,
            "occurred_at": as_utc(occurred_at, "occurred_at"),
            "modality": modality,
            "unit": unit,
            "raw_metadata": raw_metadata,
        }
        digest = hashlib.sha256(canonical_json_dumps(identity).encode("utf-8")).hexdigest()
        return f"obs_{digest[:32]}", digest

    def record_raw_observation(
        self,
        *,
        subject_id: str,
        stream_kind: RawStreamKind | str,
        content: Any,
        occurred_at: datetime,
        learned_at: datetime | None = None,
        recorded_at: datetime | None = None,
        modality: str = "text",
        unit: str | None = None,
        raw_metadata: dict[str, Any] | None = None,
        source_class: SourceClass | None = None,
    ) -> Observation:
        """记录单条原始基础观测并立即写入数据库。

        `occurred_at` 表示世界何时发生；若调用方没有显式提供知识/写入时间，
        feeder 以当前 ingest 时刻作为 learned_at/recorded_at，而不是倒填为历史发生时刻。
        """

        obs = self._build_observation(
            subject_id=subject_id,
            stream_kind=stream_kind,
            content=content,
            occurred_at=occurred_at,
            learned_at=learned_at,
            recorded_at=recorded_at,
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
        learned_at: datetime | None,
        recorded_at: datetime | None,
        modality: str,
        unit: str | None = None,
        raw_metadata: dict[str, Any] | None = None,
    ) -> Observation:
        kind_str = stream_kind.value if isinstance(stream_kind, RawStreamKind) else str(stream_kind)
        occurred_utc = as_utc(occurred_at, "occurred_at")
        recorded_utc = as_utc(recorded_at or utc_now(), "recorded_at")
        learned_utc = as_utc(learned_at or recorded_utc, "learned_at")

        meta = raw_metadata.copy() if raw_metadata else {}
        meta["raw_stream_kind"] = kind_str

        object_id, digest = self._stable_observation_identity(
            subject_id=subject_id,
            stream_kind=kind_str,
            content=content,
            occurred_at=occurred_utc,
            modality=modality,
            unit=unit,
            raw_metadata=meta,
        )
        meta["ingest_identity_sha256"] = digest

        return Observation(
            object_id=object_id,
            subject_id=subject_id,
            revision=1,
            occurred=TemporalExtent.point(occurred_utc),
            learned_at=learned_utc,
            recorded_at=recorded_utc,
            source_kind=kind_str,
            modality=modality,
            value=content,
            unit=unit,
            metadata=meta,
            created_by="life_stream_feeder",
        )

    def _existing_observation_ids(self, observations: Sequence[Observation]) -> set[str]:
        ids = [obs.object_id for obs in observations]
        if not ids:
            return set()
        found: set[str] = set()
        # Stay comfortably below SQLite host-parameter limits.
        with self.store._connection() as conn:
            for offset in range(0, len(ids), 400):
                part = ids[offset : offset + 400]
                placeholders = ",".join("?" for _ in part)
                rows = conn.execute(
                    f"SELECT DISTINCT object_id FROM object_revisions WHERE object_id IN ({placeholders})",
                    part,
                ).fetchall()
                found.update(str(row["object_id"]) for row in rows)
        return found

    @staticmethod
    def _infer_raw_source_class(observations: Sequence[Observation]) -> SourceClass:
        kinds = {obs.source_kind for obs in observations}
        if kinds == {RawStreamKind.USER_CHAT.value}:
            return SourceClass.USER
        raw_external = {
            RawStreamKind.SENSOR.value,
            RawStreamKind.MIC_TRANSCRIPTION.value,
            RawStreamKind.CAMERA_CAPTION.value,
            RawStreamKind.APP_DATA.value,
        }
        if kinds and kinds.issubset(raw_external):
            # SourceClass.SENSOR is the existing deterministic non-AI raw-ingest class.
            # `source_kind` preserves the exact sensor/mic/camera/app provenance.
            return SourceClass.SENSOR
        # Unknown/custom streams must be explicitly classified by callers if they are
        # not AI-derived. Keep the compatibility fallback only for such custom paths.
        return SourceClass.AI_COGNITION

    def commit_observations(
        self,
        subject_id: str,
        observations: Sequence[Observation],
        *,
        reason: str = "Ingest raw multi-modal life stream",
        source_class: SourceClass | None = None,
    ) -> None:
        """批量提交原始观测；同一 deterministic raw identity 的 replay 是 no-op。"""

        if not observations:
            return

        existing = self._existing_observation_ids(observations)
        pending = [obs for obs in observations if obs.object_id not in existing]
        if not pending:
            return

        inferred_source = source_class or self._infer_raw_source_class(pending)

        chunk_size = 500
        for i in range(0, len(pending), chunk_size):
            chunk = pending[i : i + chunk_size]
            chunk_identity = hashlib.sha256(
                "|".join(sorted(obs.object_id for obs in chunk)).encode("utf-8")
            ).hexdigest()[:24]
            op = OperationRequest(
                operation_id=new_operation_id(),
                operation_name="observation.bulk_ingest",
                expected_world_revision=self.store.current_world_revision(),
                reason=reason,
                idempotency_key=f"ingest_{subject_id}_{chunk_identity}",
                source_class=inferred_source,
            )
            self.store.commit(chunk, op)

    @staticmethod
    def _occurred_start(payload: dict[str, Any]) -> datetime | None:
        occurred = payload.get("occurred")
        if not isinstance(occurred, dict) or occurred.get("unknown"):
            return None
        start = occurred.get("start")
        if not isinstance(start, str):
            return None
        try:
            return datetime.fromisoformat(start)
        except (TypeError, ValueError):
            return None

    def measure_storage_capacity(self, subject_id: str) -> StorageCapacityReport:
        """统计数据库占用与按现实发生时间计算的人生覆盖跨度。"""

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

        with self.store._connection() as conn:
            commits_row = conn.execute("SELECT COUNT(*) AS cnt FROM world_commits").fetchone()
            total_commits = commits_row["cnt"] if commits_row else 0
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
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    payload = {}

                dt = self._occurred_start(payload)
                if dt is None:
                    try:
                        dt = datetime.fromisoformat(row["learned_at"])
                    except Exception:
                        dt = None
                if dt is not None:
                    if min_date is None or dt < min_date:
                        min_date = dt
                    if max_date is None or dt > max_date:
                        max_date = dt

                sk = payload.get("source_kind", "unknown") if isinstance(payload, dict) else "unknown"
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
        """按现实发生日期查询生活流，而不是按系统获知日期查询。"""

        prefix = target_date_iso[:10]
        matched: list[tuple[datetime, dict[str, Any]]] = []
        with self.store._connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM object_revisions
                WHERE object_type = 'observation' AND subject_id = ?
                """,
                (subject_id,),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                except Exception:
                    continue
                occurred = self._occurred_start(payload)
                if occurred is None or occurred.date().isoformat() != prefix:
                    continue
                matched.append((occurred, payload))

        matched.sort(key=lambda item: item[0])
        return [payload for _, payload in matched]
