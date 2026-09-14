from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing anchor in {path}: {old[:100]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"non-unique anchor in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# B5-b: reopen M0-002 with a machine-distinct internal storage failure.
replace_once(
    "src/aios_core/contracts/enums.py",
    '    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"\n',
    '    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"\n    STORAGE_FAILURE = "STORAGE_FAILURE"\n',
)

# B6: one canonical normalization path is shared by replay identity and persistence.
Path("src/aios_core/storage/idempotency.py").write_text('''from __future__ import annotations\n\nimport hashlib\nimport json\nimport sqlite3\nfrom collections.abc import Iterable\nfrom typing import Any, TypeVar, cast\n\nfrom aios_core.contracts.base import WorldObject\nfrom aios_core.contracts.operations import OperationRequest\n\nTWorldObject = TypeVar("TWorldObject", bound=WorldObject)\n\n\ndef _json_round_trip(value: Any) -> Any:\n    """Normalize values exactly like the durable operation audit representation."""\n\n    return json.loads(json.dumps(value, ensure_ascii=False, default=str))\n\n\ndef _canonical_json(value: Any) -> str:\n    return json.dumps(\n        value,\n        ensure_ascii=False,\n        sort_keys=True,\n        separators=(",", ":"),\n    )\n\n\ndef normalize_operation_for_persistence(operation: OperationRequest) -> OperationRequest:\n    """Return a newly validated snapshot of a possibly mutated request instance.\n\n    Pydantic assignment validation can raise after an assignment has already changed\n    an instance. Durable boundaries therefore never trust the live instance directly.\n    """\n\n    snapshot = operation.model_dump(mode="python", round_trip=True)\n    return OperationRequest.model_validate(snapshot)\n\n\ndef normalize_world_object_for_persistence(obj: TWorldObject) -> TWorldObject:\n    """Return the same canonical object representation used for durable storage."""\n\n    snapshot = obj.model_dump(mode="python", round_trip=True)\n    return cast(TWorldObject, type(obj).model_validate(snapshot))\n\n\ndef _object_entries(objects: Iterable[WorldObject]) -> list[dict[str, Any]]:\n    entries: list[dict[str, Any]] = []\n    for obj in objects:\n        normalized = normalize_world_object_for_persistence(obj)\n        entries.append(\n            {\n                "object_id": normalized.object_id,\n                "revision": normalized.revision,\n                "payload": json.loads(normalized.model_dump_json()),\n            }\n        )\n    entries.sort(key=lambda entry: (entry["object_id"], entry["revision"]))\n    return entries\n\n\ndef request_fingerprint(\n    operation: OperationRequest,\n    objects: Iterable[WorldObject],\n) -> str:\n    """Return canonical identity for one logical durable commit request.\n\n    Replay identity is calculated from the same normalized representation that is\n    persisted. This closes the B6 gap where a coercible post-construction mutation\n    could be accepted, persisted in normalized form, and then fail exact replay.\n    """\n\n    normalized_operation = normalize_operation_for_persistence(operation)\n    payload = {\n        "operation_id": normalized_operation.operation_id,\n        "session_id": normalized_operation.session_id,\n        "operation_name": normalized_operation.operation_name,\n        "arguments": _json_round_trip(normalized_operation.arguments),\n        "expected_world_revision": normalized_operation.expected_world_revision,\n        "reason": normalized_operation.reason,\n        "idempotency_key": normalized_operation.idempotency_key,\n        "objects": _object_entries(objects),\n    }\n    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()\n\n\ndef stored_request_fingerprint(\n    conn: sqlite3.Connection,\n    *,\n    operation_id: str,\n    world_revision: int,\n) -> str:\n    """Rebuild the normalized original request identity from durable records."""\n\n    operation_row = conn.execute(\n        """\n        SELECT operation_id, session_id, operation_name, arguments_json,\n               expected_world_revision, reason, idempotency_key\n        FROM operations\n        WHERE operation_id=?\n        """,\n        (operation_id,),\n    ).fetchone()\n    if operation_row is None:\n        raise RuntimeError(\n            f"idempotency record references missing operation: {operation_id}"\n        )\n\n    object_rows = conn.execute(\n        """\n        SELECT object_id, revision, payload_json\n        FROM object_revisions\n        WHERE world_revision=?\n        ORDER BY object_id ASC, revision ASC\n        """,\n        (world_revision,),\n    ).fetchall()\n\n    payload = {\n        "operation_id": operation_row["operation_id"],\n        "session_id": operation_row["session_id"],\n        "operation_name": operation_row["operation_name"],\n        "arguments": json.loads(operation_row["arguments_json"]),\n        "expected_world_revision": operation_row["expected_world_revision"],\n        "reason": operation_row["reason"],\n        "idempotency_key": operation_row["idempotency_key"],\n        "objects": [\n            {\n                "object_id": row["object_id"],\n                "revision": row["revision"],\n                "payload": json.loads(row["payload_json"]),\n            }\n            for row in object_rows\n        ],\n    }\n    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()\n''', encoding="utf-8")

STORE = "src/aios_core/storage/sqlite_store.py"

replace_once(
    STORE,
    "from aios_core.contracts.models import Dependency\n",
    "from aios_core.contracts.models import Dependency, EvidenceSet\n",
)
replace_once(
    STORE,
    "from aios_core.storage.idempotency import request_fingerprint, stored_request_fingerprint\n",
    "from aios_core.storage.idempotency import (\n"
    "    normalize_operation_for_persistence,\n"
    "    normalize_world_object_for_persistence,\n"
    "    request_fingerprint,\n"
    "    stored_request_fingerprint,\n"
    ")\n",
)

# B5-a/B5-b: include connect/setup in the mapped capability boundary and classify
# non-request storage faults separately from INVALID_ARGUMENT.
replace_once(
    STORE,
    '''    @contextmanager\n    def _connection(self) -> Iterator[sqlite3.Connection]:\n        conn = sqlite3.connect(\n            self.db_path,\n            timeout=self.SQLITE_BUSY_TIMEOUT_MS / 1000.0,\n        )\n        conn.row_factory = sqlite3.Row\n        try:\n            conn.execute("PRAGMA foreign_keys = ON")\n            conn.execute(f"PRAGMA busy_timeout = {self.SQLITE_BUSY_TIMEOUT_MS}")\n            conn.execute("PRAGMA journal_mode = WAL")\n            yield conn\n        except sqlite3.IntegrityError as exc:\n            raise StoreError(\n                ErrorCode.INVALID_ARGUMENT,\n                "SQLite integrity constraint rejected the operation",\n                context={"reason": "sqlite_integrity_error"},\n            ) from exc\n        except sqlite3.OperationalError as exc:\n            message = str(exc).lower()\n            if "locked" in message or "busy" in message:\n                raise StoreError(\n                    ErrorCode.VERSION_CONFLICT,\n                    "world store is busy; retry from a fresh snapshot",\n                    context={"reason": "storage_busy"},\n                ) from exc\n            raise StoreError(\n                ErrorCode.INVALID_ARGUMENT,\n                "SQLite operational failure",\n                context={"reason": "sqlite_operational_error"},\n            ) from exc\n        finally:\n            conn.close()\n''',
    '''    @contextmanager\n    def _connection(self) -> Iterator[sqlite3.Connection]:\n        conn: sqlite3.Connection | None = None\n        try:\n            conn = sqlite3.connect(\n                self.db_path,\n                timeout=self.SQLITE_BUSY_TIMEOUT_MS / 1000.0,\n            )\n            conn.row_factory = sqlite3.Row\n            conn.execute("PRAGMA foreign_keys = ON")\n            conn.execute(f"PRAGMA busy_timeout = {self.SQLITE_BUSY_TIMEOUT_MS}")\n            conn.execute("PRAGMA journal_mode = WAL")\n            yield conn\n        except sqlite3.IntegrityError as exc:\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                "SQLite integrity failure",\n                context={"reason": "sqlite_integrity_error"},\n            ) from exc\n        except sqlite3.OperationalError as exc:\n            message = str(exc).lower()\n            if "locked" in message or "busy" in message:\n                raise StoreError(\n                    ErrorCode.VERSION_CONFLICT,\n                    "world store is busy; retry from a fresh snapshot",\n                    context={"reason": "storage_busy"},\n                ) from exc\n            reason = "storage_unavailable" if conn is None else "sqlite_operational_error"\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                "SQLite storage operation failed",\n                context={"reason": reason},\n            ) from exc\n        except sqlite3.DatabaseError as exc:\n            raise StoreError(\n                ErrorCode.STORAGE_FAILURE,\n                "SQLite database failure",\n                context={"reason": "sqlite_database_error"},\n            ) from exc\n        finally:\n            if conn is not None:\n                conn.close()\n''',
)

# Existing-key replay may need normalization to compare identity. Invalid mutated
# retries are a key conflict, not a stale-world check or a new durable write.
replace_once(
    STORE,
    '''        incoming_fingerprint = request_fingerprint(operation, objects)\n        original_fingerprint = stored_request_fingerprint(\n''',
    '''        try:\n            incoming_fingerprint = request_fingerprint(operation, objects)\n        except ValidationError as exc:\n            raise StoreError(\n                ErrorCode.IDEMPOTENCY_CONFLICT,\n                "idempotency key retry is not a valid equivalent request",\n                context={\n                    "idempotency_key": operation.idempotency_key,\n                    "operation_id": operation.operation_id,\n                    "reason": "request_revalidation_failed",\n                },\n            ) from exc\n        original_fingerprint = stored_request_fingerprint(\n''',
)

# B7: new writes revalidate OperationRequest at the durable boundary after the
# frozen replay and optimistic-version checks but before any durable insert.
replace_once(
    STORE,
    '''                if operation.expected_world_revision != current_world_revision:\n                    raise StoreError(\n                        ErrorCode.VERSION_CONFLICT,\n                        f"expected world revision {operation.expected_world_revision}, current is {current_world_revision}",\n                        context={\n                            "expected_world_revision": operation.expected_world_revision,\n                            "current_world_revision": current_world_revision,\n                            "operation_id": operation.operation_id,\n                        },\n                    )\n\n                validated_objects: list[WorldObject] = []\n''',
    '''                if operation.expected_world_revision != current_world_revision:\n                    raise StoreError(\n                        ErrorCode.VERSION_CONFLICT,\n                        f"expected world revision {operation.expected_world_revision}, current is {current_world_revision}",\n                        context={\n                            "expected_world_revision": operation.expected_world_revision,\n                            "current_world_revision": current_world_revision,\n                            "operation_id": operation.operation_id,\n                        },\n                    )\n\n                try:\n                    operation = normalize_operation_for_persistence(operation)\n                except ValidationError as exc:\n                    raise StoreError(\n                        ErrorCode.INVALID_ARGUMENT,\n                        "operation request failed persistence validation",\n                        context={\n                            "operation_id": operation.operation_id,\n                            "reason": "operation_persistence_revalidation_failed",\n                        },\n                    ) from exc\n\n                validated_objects: list[WorldObject] = []\n''',
)
replace_once(
    STORE,
    '''                        snapshot = obj.model_dump(\n                            mode="python",\n                            round_trip=True,\n                        )\n                        validated = type(obj).model_validate(snapshot)\n''',
    '''                        validated = normalize_world_object_for_persistence(obj)\n''',
)

# R4: EvidenceSet declared refs are judged against the EvidenceSet's frozen
# knowledge cutoff, not its wider learned_at. This also covers selector refs.
replace_once(
    STORE,
    '''                for obj in object_list:\n                    for ref in self._collect_refs(obj):\n                        if ref.object_id == obj.object_id and (\n''',
    '''                for obj in object_list:\n                    reference_cutoff = (\n                        obj.knowledge_window.knowledge_cutoff\n                        if isinstance(obj, EvidenceSet)\n                        else obj.learned_at\n                    )\n                    for ref in self._collect_refs(obj):\n                        if ref.object_id == obj.object_id and (\n''',
)
replace_once(
    STORE,
    '''                            knowledge_cutoff=obj.learned_at,\n''',
    '''                            knowledge_cutoff=reference_cutoff,\n''',
)

# M0-002 exact enum freeze now includes STORAGE_FAILURE.
replace_once(
    "tests/unit/test_errors.py",
    '''# CASE E01: 所有10个 ErrorCode 可以构造 ErrorResponse\n''',
    '''# CASE E01: 所有11个 ErrorCode 可以构造 ErrorResponse\n''',
)
replace_once(
    "tests/unit/test_errors.py",
    '''    assert len(list(ErrorCode)) == 10\n''',
    '''    assert len(list(ErrorCode)) == 11\n''',
)
replace_once(
    "tests/unit/test_errors.py",
    '''        "IDEMPOTENCY_CONFLICT",\n    }\n''',
    '''        "IDEMPOTENCY_CONFLICT",\n        "STORAGE_FAILURE",\n    }\n''',
)

# M0-018 fault injection now proves atomic rollback through the corrected storage
# failure protocol category.
replace_once(
    "tests/unit/test_world_revision_atomicity.py",
    '''    assert exc.value.code is ErrorCode.INVALID_ARGUMENT\n    assert exc.value.context["reason"] == "sqlite_integrity_error"\n''',
    '''    assert exc.value.code is ErrorCode.STORAGE_FAILURE\n    assert exc.value.context["reason"] == "sqlite_integrity_error"\n''',
)

# Focused adversarial regression suite for the second independent re-review.
Path("tests/unit/test_m0_gate_third_followup.py").write_text('''from __future__ import annotations\n\nimport sqlite3\nimport warnings\nfrom datetime import datetime, timedelta, timezone\n\nimport pytest\nfrom pydantic import ValidationError\n\nfrom aios_core.contracts import (\n    EvidenceSet,\n    KnowledgeWindow,\n    ObjectRef,\n    ObjectType,\n    Observation,\n    OperationRequest,\n    TemporalExtent,\n    new_object_id,\n)\nfrom aios_core.contracts.enums import ErrorCode\nfrom aios_core.storage import SQLiteWorldStore, StoreError\n\nT = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)\n\n\ndef op(expected: int, key: str, *, operation_id: str | None = None) -> OperationRequest:\n    return OperationRequest(\n        operation_id=operation_id or f"op-{key}",\n        session_id="gate-third-followup",\n        operation_name="world.commit",\n        arguments={"gate": "third-followup"},\n        expected_world_revision=expected,\n        reason="M0 Gate B6/B7/B5/R4 follow-up",\n        idempotency_key=key,\n    )\n\n\ndef obs(object_id: str, *, learned_at: datetime = T) -> Observation:\n    return Observation(\n        object_id=object_id,\n        subject_id="gate-user",\n        revision=1,\n        occurred=TemporalExtent.point(learned_at),\n        learned_at=learned_at,\n        recorded_at=learned_at,\n        created_by="m0-gate-third-followup",\n        source_kind="test",\n        modality="text",\n        value="payload",\n    )\n\n\ndef db_state(path) -> tuple[list[tuple], ...]:\n    with sqlite3.connect(path) as conn:\n        return tuple(\n            conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()\n            for table in (\n                "world_meta",\n                "world_commits",\n                "object_revisions",\n                "operations",\n                "idempotency_records",\n            )\n        )\n\n\ndef test_b6_coercible_nested_mutation_replays_from_same_normalized_identity(tmp_path):\n    path = tmp_path / "world.db"\n    store = SQLiteWorldStore(path)\n    observation_id = new_object_id(ObjectType.OBSERVATION)\n    store.commit([obs(observation_id)], op(0, "seed"))\n\n    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)\n    evidence = EvidenceSet(\n        object_id=evidence_id,\n        subject_id="gate-user",\n        revision=1,\n        occurred=TemporalExtent.point(T),\n        learned_at=T,\n        recorded_at=T,\n        created_by="m0-gate-third-followup",\n        purpose="B6 normalized retry",\n        knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=1),\n        member_refs=[ObjectRef(object_id=observation_id, revision=1)],\n        selection_method="explicit",\n    )\n    evidence.coverage.observed_count = "1"  # type: ignore[assignment]\n    request = op(1, "b6")\n\n    with warnings.catch_warnings():\n        warnings.filterwarnings("ignore", message="Pydantic serializer warnings:")\n        first = store.commit([evidence], request)\n        replay = SQLiteWorldStore(path).commit([evidence], request)\n\n    assert first.world_revision == replay.world_revision == 2\n    assert replay.idempotent_replay is True\n    assert SQLiteWorldStore(path).get_payload(evidence_id)["coverage"]["observed_count"] == 1\n    assert SQLiteWorldStore(path).current_world_revision() == 2\n\n\n@pytest.mark.parametrize(\n    ("field", "bad_value"),\n    [\n        ("operation_id", " "),\n        ("session_id", " "),\n        ("operation_name", " "),\n        ("reason", " "),\n        ("idempotency_key", " "),\n    ],\n)\ndef test_b7_failed_assignment_cannot_persist_dirty_operation(tmp_path, field, bad_value):\n    path = tmp_path / "world.db"\n    store = SQLiteWorldStore(path)\n    request = op(0, f"b7-{field}", operation_id=f"b7-op-{field}")\n\n    with pytest.raises(ValidationError):\n        setattr(request, field, bad_value)\n    assert getattr(request, field) == bad_value\n\n    before = db_state(path)\n    with pytest.raises(StoreError) as exc:\n        store.commit([obs(new_object_id(ObjectType.OBSERVATION))], request)\n    assert exc.value.code is ErrorCode.INVALID_ARGUMENT\n    assert exc.value.context["reason"] == "operation_persistence_revalidation_failed"\n    assert db_state(path) == before\n\n\ndef test_b5_connect_failure_is_storage_failure_not_raw_sqlite(tmp_path):\n    with pytest.raises(StoreError) as exc:\n        SQLiteWorldStore(tmp_path / "missing-parent" / "world.db")\n    assert exc.value.code is ErrorCode.STORAGE_FAILURE\n    assert exc.value.context["reason"] == "storage_unavailable"\n    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)\n\n\ndef test_b5_internal_schema_failure_is_storage_failure(tmp_path):\n    path = tmp_path / "world.db"\n    store = SQLiteWorldStore(path)\n    with sqlite3.connect(path) as conn:\n        conn.execute("DROP TABLE operations")\n        conn.commit()\n\n    with pytest.raises(StoreError) as exc:\n        store.commit([obs(new_object_id(ObjectType.OBSERVATION))], op(0, "schema-fault"))\n    assert exc.value.code is ErrorCode.STORAGE_FAILURE\n    assert exc.value.context["reason"] == "sqlite_operational_error"\n    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)\n\n\n@pytest.mark.parametrize("role", ["member_refs", "support_refs", "counter_refs", "context_refs"])\ndef test_r4_evidence_refs_must_be_visible_at_frozen_cutoff(tmp_path, role):\n    path = tmp_path / "world.db"\n    store = SQLiteWorldStore(path)\n    old_id = new_object_id(ObjectType.OBSERVATION)\n    later_id = new_object_id(ObjectType.OBSERVATION)\n    old_time = T - timedelta(hours=2)\n    cutoff = T - timedelta(hours=1)\n    store.commit(\n        [obs(old_id, learned_at=old_time), obs(later_id, learned_at=T)],\n        op(0, f"seed-{role}"),\n    )\n\n    kwargs = {\n        "member_refs": [ObjectRef(object_id=old_id, revision=1)],\n        role: [ObjectRef(object_id=later_id, revision=1)],\n    }\n    if role == "member_refs":\n        kwargs["member_refs"] = [ObjectRef(object_id=later_id, revision=1)]\n\n    evidence = EvidenceSet(\n        object_id=new_object_id(ObjectType.EVIDENCE_SET),\n        subject_id="gate-user",\n        revision=1,\n        occurred=TemporalExtent.point(T),\n        learned_at=T,\n        recorded_at=T,\n        created_by="m0-gate-third-followup",\n        purpose=f"R4 {role}",\n        knowledge_window=KnowledgeWindow(knowledge_cutoff=cutoff, world_revision=1),\n        selection_method="explicit",\n        **kwargs,\n    )\n\n    before = db_state(path)\n    with pytest.raises(StoreError) as exc:\n        store.commit([evidence], op(1, f"evidence-{role}"))\n    assert exc.value.code is ErrorCode.NOT_FOUND\n    assert exc.value.context["referenced_object_id"] == later_id\n    assert db_state(path) == before\n\n\ndef test_r4_same_transaction_member_visible_at_cutoff_remains_legal(tmp_path):\n    path = tmp_path / "world.db"\n    store = SQLiteWorldStore(path)\n    observation_id = new_object_id(ObjectType.OBSERVATION)\n    evidence_id = new_object_id(ObjectType.EVIDENCE_SET)\n    observation = obs(observation_id, learned_at=T)\n    evidence = EvidenceSet(\n        object_id=evidence_id,\n        subject_id="gate-user",\n        revision=1,\n        occurred=TemporalExtent.point(T),\n        learned_at=T,\n        recorded_at=T,\n        created_by="m0-gate-third-followup",\n        purpose="same transaction frozen evidence",\n        knowledge_window=KnowledgeWindow(knowledge_cutoff=T, world_revision=None),\n        member_refs=[ObjectRef(object_id=observation_id, revision=1)],\n        selection_method="explicit",\n    )\n\n    result = store.commit([observation, evidence], op(0, "same-tx-evidence"))\n    assert result.world_revision == 1\n    assert {ref[0] for ref in result.object_refs} == {observation_id, evidence_id}\n''', encoding="utf-8")

# Remove one-shot machinery from the semantic patch commit.
Path(".github/workflows/m0-gate-b6-b7-r4-patch.yml").unlink(missing_ok=True)
Path("tools/apply_m0_gate_b6_b7_r4.py").unlink(missing_ok=True)
try:
    Path("tools").rmdir()
except OSError:
    pass
