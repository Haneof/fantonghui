from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from aios_core.contracts import (
    EvidenceSet,
    KnowledgeWindow,
    ObjectRef,
    Observation,
    OperationRequest,
    SourceRef,
    TemporalExtent,
)
from aios_core.contracts.enums import ErrorCode, ObjectType
from aios_core.contracts.models import EvidenceSelector
from aios_core.storage import SQLiteWorldStore, StoreError


T0 = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
TABLES = (
    "world_commits",
    "object_revisions",
    "operations",
    "idempotency_records",
)


class ExtraCarrier(BaseModel):
    model_config = ConfigDict(extra="allow")
    known: str


def base_fields(object_id: str, **updates: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "object_id": object_id,
        "subject_id": "independent-review",
        "learned_at": T0,
        "recorded_at": T0,
        "created_by": "independent-quality-review-b9b5921c",
    }
    data.update(updates)
    return data


def obs(object_id: str = "obs", **updates: Any) -> Observation:
    return Observation(
        **base_fields(object_id, **updates),
        source_kind="review",
        modality="json",
    )


def op(key: str, expected: int = 0, **updates: Any) -> OperationRequest:
    data: dict[str, Any] = {
        "operation_id": f"op-{key}",
        "operation_name": "world.commit",
        "arguments": {},
        "expected_world_revision": expected,
        "reason": "independent robustness review",
        "idempotency_key": key,
    }
    data.update(updates)
    return OperationRequest(**data)


def snapshot(path: str | Path) -> tuple[int, int, int, int, int]:
    with sqlite3.connect(path) as conn:
        revision = int(
            conn.execute(
                "SELECT value FROM world_meta WHERE key='world_revision'"
            ).fetchone()[0]
        )
        counts = tuple(
            int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for table in TABLES
        )
    return (revision, *counts)


def assert_protocol_failure_unchanged(
    store: SQLiteWorldStore,
    objects: list[Any],
    request: OperationRequest,
    expected_code: ErrorCode,
) -> StoreError:
    before = snapshot(store.db_path)
    with pytest.raises(StoreError) as exc:
        store.commit(objects, request)
    assert exc.value.code is expected_code
    assert snapshot(store.db_path) == before
    return exc.value


def ref_pair(kind: str) -> tuple[ObjectRef | SourceRef, dict[str, Any]]:
    if kind == "object":
        return (
            ObjectRef(object_id="target", revision=1),
            {"object_id": "target", "revision": 1},
        )
    return (
        SourceRef(object_id="target", revision=1, source_locator="src://target"),
        {
            "object_id": "target",
            "revision": 1,
            "source_locator": "src://target",
        },
    )


def case_for_value(
    *,
    key: str,
    placement: str,
    value: Any,
    expected: int = 1,
) -> tuple[list[Any], OperationRequest]:
    request = op(key, expected)
    object_id = f"reader-{key}"
    if placement == "metadata":
        return [obs(object_id, metadata={"nested": {"ref": value}})], request
    if placement == "value":
        return [obs(object_id, value={"nested": [{"ref": value}]})], request
    if placement == "arguments":
        request = op(key, expected, arguments={"nested": {"ref": value}})
        return [obs(object_id, value="stable")], request
    if placement == "filters":
        selector = EvidenceSelector(
            selector_type="review",
            subject_id="independent-review",
            time_range=TemporalExtent.unknown_time(),
            filters={"nested": {"ref": value}},
            algorithm_version="v1",
        )
        evidence = EvidenceSet(
            **base_fields(object_id),
            purpose="review selector identity",
            knowledge_window=KnowledgeWindow(
                knowledge_cutoff=T0,
                world_revision=1,
            ),
            member_refs=[ObjectRef(object_id="target", revision=1)],
            selector=selector,
            selection_method="explicit",
        )
        return [evidence], request
    raise AssertionError(f"unknown placement: {placement}")


def strip_semantic_fingerprint(path: str | Path, key: str) -> None:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT result_json FROM idempotency_records WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload.pop("_request_fingerprint", None)
        conn.execute(
            "UPDATE idempotency_records SET result_json=? WHERE idempotency_key=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), key),
        )
        conn.commit()


# A. Typed reference identity.
@pytest.mark.parametrize("kind", ["object", "source"])
@pytest.mark.parametrize("placement", ["metadata", "value", "arguments", "filters"])
@pytest.mark.parametrize("direction", ["plain-to-typed", "typed-to-plain"])
def test_typed_and_plain_reference_identity_never_aliases(
    tmp_path: Path,
    kind: str,
    placement: str,
    direction: str,
) -> None:
    path = tmp_path / "typed-identity.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))
    typed, plain = ref_pair(kind)
    first_value, second_value = (
        (plain, typed) if direction == "plain-to-typed" else (typed, plain)
    )
    key = f"identity-{kind}-{placement}-{direction}"
    first_objects, first_request = case_for_value(
        key=key,
        placement=placement,
        value=first_value,
    )
    first = store.commit(first_objects, first_request)
    assert first.world_revision == 2
    assert first.idempotent_replay is False
    before = snapshot(path)

    second_objects, second_request = case_for_value(
        key=key,
        placement=placement,
        value=second_value,
    )
    with pytest.raises(StoreError) as exc:
        SQLiteWorldStore(path).commit(second_objects, second_request)
    assert exc.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert snapshot(path) == before


@pytest.mark.parametrize("kind", ["object", "source"])
@pytest.mark.parametrize("placement", ["metadata", "value", "arguments", "filters"])
def test_exact_typed_reference_retry_replays_after_reopen(
    tmp_path: Path,
    kind: str,
    placement: str,
) -> None:
    path = tmp_path / "typed-replay.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))
    typed, _ = ref_pair(kind)
    key = f"typed-replay-{kind}-{placement}"
    objects, request = case_for_value(key=key, placement=placement, value=typed)
    first = store.commit(objects, request)
    before = snapshot(path)

    retry_objects, retry_request = case_for_value(
        key=key,
        placement=placement,
        value=ref_pair(kind)[0],
    )
    replay = SQLiteWorldStore(path).commit(retry_objects, retry_request)
    assert replay.world_revision == first.world_revision == 2
    assert replay.idempotent_replay is True
    assert snapshot(path) == before


@pytest.mark.parametrize("placement", ["metadata", "value", "arguments", "filters"])
def test_exact_plain_reference_shaped_dict_retry_replays_after_reopen(
    tmp_path: Path,
    placement: str,
) -> None:
    path = tmp_path / "plain-replay.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))
    _, plain = ref_pair("object")
    key = f"plain-replay-{placement}"
    objects, request = case_for_value(key=key, placement=placement, value=plain)
    first = store.commit(objects, request)
    before = snapshot(path)

    retry_objects, retry_request = case_for_value(
        key=key,
        placement=placement,
        value={"object_id": "target", "revision": 1},
    )
    replay = SQLiteWorldStore(path).commit(retry_objects, retry_request)
    assert replay.world_revision == first.world_revision == 2
    assert replay.idempotent_replay is True
    assert snapshot(path) == before


# B. Serialization and persistence boundary.
def invalid_value(kind: str) -> Any:
    if kind == "invalid-bytes":
        return b"\xff"
    if kind == "surrogate":
        return "bad-\ud800-text"
    if kind == "cycle":
        value: list[Any] = []
        value.append(value)
        return value
    if kind == "deep":
        value: Any = 0
        for _ in range(140):
            value = [value]
        return value
    if kind == "huge-int":
        return 10**5000
    if kind == "nan":
        return math.nan
    if kind == "infinity":
        return math.inf
    if kind == "unsupported":
        return object()
    raise AssertionError(kind)


SERIALIZATION_CASES = [
    ("invalid-bytes-object", "object", "invalid-bytes"),
    ("invalid-bytes-arguments", "arguments", "invalid-bytes"),
    ("surrogate-object", "object", "surrogate"),
    ("cycle-arguments", "arguments", "cycle"),
    ("deep-object", "object", "deep"),
    ("huge-int-arguments", "arguments", "huge-int"),
    ("nan-object", "object", "nan"),
    ("infinity-arguments", "arguments", "infinity"),
    ("unsupported-object", "object", "unsupported"),
]


@pytest.mark.parametrize("case_name,placement,kind", SERIALIZATION_CASES)
@pytest.mark.parametrize("existing_key", [False, True])
def test_non_durable_values_are_protocol_errors_and_atomic(
    tmp_path: Path,
    case_name: str,
    placement: str,
    kind: str,
    existing_key: bool,
) -> None:
    path = tmp_path / f"serialization-{case_name}-{existing_key}.db"
    store = SQLiteWorldStore(path)
    key = f"serialization-{case_name}-{existing_key}"
    good_object = obs("boundary", value="good")
    good_request = op(key, arguments={"value": "good"})
    if existing_key:
        store.commit([good_object], good_request)

    bad = invalid_value(kind)
    if placement == "object":
        bad_object = good_object.model_copy(update={"value": bad})
        bad_request = good_request
    else:
        bad_object = good_object
        bad_request = good_request.model_copy(update={"arguments": {"value": bad}})

    expected = (
        ErrorCode.IDEMPOTENCY_CONFLICT
        if existing_key
        else ErrorCode.INVALID_ARGUMENT
    )
    assert_protocol_failure_unchanged(store, [bad_object], bad_request, expected)


# C. Pydantic model data preservation.
def test_allowed_extra_fields_inside_any_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "allowed-extra.db"
    store = SQLiteWorldStore(path)
    carrier = ExtraCarrier.model_validate(
        {"known": "declared", "extra_a": {"n": 1}}
    )
    assert carrier.__pydantic_extra__ is not None
    carrier.__pydantic_extra__["extra_b"] = [1, 2, 3]
    carrier = carrier.model_copy(update={"extra_c": "copied"})
    store.commit(
        [obs("carrier", value={"nested_model": carrier})],
        op("allowed-extra"),
    )
    payload = store.get_payload("carrier")
    nested = payload["value"]["nested_model"]
    assert nested["known"] == "declared"
    assert nested["extra_a"] == {"n": 1}
    assert nested["extra_b"] == [1, 2, 3]
    assert nested["extra_c"] == "copied"


def test_dirty_nested_schema_forbidden_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "nested-forbid.db"
    store = SQLiteWorldStore(path)
    selector = EvidenceSelector(
        selector_type="review",
        subject_id="independent-review",
        time_range=TemporalExtent.unknown_time(),
        filters={"ok": True},
        algorithm_version="v1",
    ).model_copy(update={"rogue": "must-not-disappear"})
    evidence = EvidenceSet(
        **base_fields("ev-dirty"),
        purpose="dirty nested model",
        knowledge_window=KnowledgeWindow(knowledge_cutoff=T0),
        selector=selector,
        selection_method="selector",
    )
    assert_protocol_failure_unchanged(
        store,
        [evidence],
        op("nested-forbid"),
        ErrorCode.INVALID_ARGUMENT,
    )


def test_dirty_canonical_object_extra_is_rejected_not_dropped(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "canonical-extra.db")
    dirty = obs("dirty-extra").model_copy(
        update={"rogue": {"must": "survive-or-reject"}}
    )
    assert_protocol_failure_unchanged(
        store,
        [dirty],
        op("canonical-extra"),
        ErrorCode.INVALID_ARGUMENT,
    )


def test_dirty_canonical_extra_cannot_false_replay_existing_key(tmp_path: Path) -> None:
    path = tmp_path / "canonical-extra-retry.db"
    store = SQLiteWorldStore(path)
    request = op("canonical-extra-retry")
    clean = obs("dirty-extra-retry")
    store.commit([clean], request)
    dirty = clean.model_copy(update={"rogue": "not-part-of-schema"})
    assert_protocol_failure_unchanged(
        store,
        [dirty],
        request,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    )


def test_model_copy_valid_field_update_is_preserved(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "model-copy-preserve.db")
    copied = obs("copied", value={"before": 1}).model_copy(
        update={"value": {"after": {"nested": [1, 2, 3]}}}
    )
    store.commit([copied], op("model-copy-preserve"))
    assert store.get_payload("copied")["value"] == {
        "after": {"nested": [1, 2, 3]}
    }


# D. Frozen reference revalidation.
def dirty_ref(kind: str, mutation: str) -> ObjectRef | SourceRef:
    if kind == "object":
        ref: ObjectRef | SourceRef = ObjectRef(object_id="target", revision=1)
    else:
        ref = SourceRef(
            object_id="target",
            revision=1,
            source_locator="src://target",
        )
    if mutation == "revision-string":
        return ref.model_copy(update={"revision": "1"})
    if mutation == "malformed":
        return ref.model_copy(update={"revision": "not-an-int"})
    if mutation == "negative":
        return ref.model_copy(update={"revision": -1})
    if mutation == "unknown-field":
        return ref.model_copy(update={"rogue": "forbidden"})
    raise AssertionError(mutation)


@pytest.mark.parametrize("kind", ["object", "source"])
def test_dirty_string_revision_is_canonicalized_before_persistence_and_replay(
    tmp_path: Path,
    kind: str,
) -> None:
    path = tmp_path / f"ref-string-{kind}.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))
    key = f"ref-string-{kind}"
    bad_typed_ref = dirty_ref(kind, "revision-string")
    reader = obs(
        "ref-reader",
        metadata={"level1": {"level2": {"ref": bad_typed_ref}}},
    )
    request = op(key, 1)
    first = store.commit([reader], request)
    persisted = store.get_payload("ref-reader")
    revision = persisted["metadata"]["level1"]["level2"]["ref"]["revision"]
    assert revision == 1
    assert isinstance(revision, int)
    before = snapshot(path)

    canonical_ref = ref_pair(kind)[0]
    canonical_reader = obs(
        "ref-reader",
        metadata={"level1": {"level2": {"ref": canonical_ref}}},
    )
    replay = SQLiteWorldStore(path).commit([canonical_reader], request)
    assert replay.world_revision == first.world_revision == 2
    assert replay.idempotent_replay is True
    assert snapshot(path) == before


@pytest.mark.parametrize("kind", ["object", "source"])
@pytest.mark.parametrize("mutation", ["malformed", "negative", "unknown-field"])
@pytest.mark.parametrize("existing_key", [False, True])
def test_dirty_reference_invalid_forms_fail_closed_and_atomic(
    tmp_path: Path,
    kind: str,
    mutation: str,
    existing_key: bool,
) -> None:
    path = tmp_path / f"dirty-ref-{kind}-{mutation}-{existing_key}.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("target")], op("seed"))
    key = f"dirty-ref-{kind}-{mutation}-{existing_key}"
    request = op(key, 1)
    if existing_key:
        valid_reader = obs(
            "dirty-ref-reader",
            metadata={"nested": {"ref": ref_pair(kind)[0]}},
        )
        store.commit([valid_reader], request)

    invalid_reader = obs(
        "dirty-ref-reader",
        metadata={"nested": {"deeper": [{"ref": dirty_ref(kind, mutation)}]}},
    )
    expected = (
        ErrorCode.IDEMPOTENCY_CONFLICT
        if existing_key
        else ErrorCode.INVALID_ARGUMENT
    )
    assert_protocol_failure_unchanged(store, [invalid_reader], request, expected)


# E. OperationRequest normalization.
def test_dirty_expected_world_revision_string_normalizes_and_replays(tmp_path: Path) -> None:
    path = tmp_path / "dirty-world-revision.db"
    store = SQLiteWorldStore(path)
    canonical = op("dirty-world-revision")
    dirty = canonical.model_copy(update={"expected_world_revision": "0"})
    first = store.commit([obs("dirty-world-reader")], dirty)
    record = store.operation_record(canonical.operation_id)
    assert record["expected_world_revision"] == 0
    before = snapshot(path)
    replay = SQLiteWorldStore(path).commit(
        [obs("dirty-world-reader")],
        canonical,
    )
    assert replay.world_revision == first.world_revision == 1
    assert replay.idempotent_replay is True
    assert snapshot(path) == before


def test_dirty_operation_id_bytes_normalizes_before_sqlite(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "dirty-operation-id.db")
    request = op("dirty-operation-id").model_copy(
        update={"operation_id": b"op-dirty-operation-id"}
    )
    result = store.commit([obs("dirty-operation-id-reader")], request)
    assert result.operation_id == "op-dirty-operation-id"
    assert store.operation_record("op-dirty-operation-id")["operation_id"] == (
        "op-dirty-operation-id"
    )


def test_dirty_idempotency_key_bytes_normalizes_and_exact_replays(tmp_path: Path) -> None:
    path = tmp_path / "dirty-key-bytes.db"
    store = SQLiteWorldStore(path)
    canonical = op("dirty-key-bytes")
    dirty = canonical.model_copy(update={"idempotency_key": b"dirty-key-bytes"})
    first = store.commit([obs("dirty-key-reader")], dirty)
    before = snapshot(path)
    replay = SQLiteWorldStore(path).commit([obs("dirty-key-reader")], canonical)
    assert replay.world_revision == first.world_revision == 1
    assert replay.idempotent_replay is True
    assert snapshot(path) == before


@pytest.mark.parametrize("bad_key", [["not", "a", "string"], None, "   "])
def test_dirty_invalid_idempotency_lookup_values_are_invalid_argument_and_atomic(
    tmp_path: Path,
    bad_key: Any,
) -> None:
    store = SQLiteWorldStore(tmp_path / "dirty-key-invalid.db")
    request = op("dirty-key-invalid").model_copy(update={"idempotency_key": bad_key})
    assert_protocol_failure_unchanged(
        store,
        [obs("dirty-key-invalid-reader")],
        request,
        ErrorCode.INVALID_ARGUMENT,
    )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("expected_world_revision", "not-an-int"),
        ("operation_id", ["not", "a", "string"]),
        ("arguments", {"bad": object()}),
    ],
)
def test_existing_key_dirty_operation_has_conflict_priority_and_is_atomic(
    tmp_path: Path,
    field: str,
    bad_value: Any,
) -> None:
    path = tmp_path / f"dirty-existing-{field}.db"
    store = SQLiteWorldStore(path)
    request = op(f"dirty-existing-{field}")
    obj = obs(f"dirty-existing-reader-{field}")
    store.commit([obj], request)
    dirty = request.model_copy(update={field: bad_value})
    assert_protocol_failure_unchanged(
        store,
        [obj],
        dirty,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    )


# F. Legacy idempotency records.
def test_legacy_unambiguous_json_exact_replay_remains_compatible(tmp_path: Path) -> None:
    path = tmp_path / "legacy-json.db"
    store = SQLiteWorldStore(path)
    request = op(
        "legacy-json",
        arguments={"plain": {"alpha": [1, 2, 3], "beta": True}},
    )
    obj = obs("legacy-json-reader", metadata={"plain": {"x": 1, "y": "z"}})
    store.commit([obj], request)
    strip_semantic_fingerprint(path, request.idempotency_key)
    before = snapshot(path)
    replay = SQLiteWorldStore(path).commit([obj], request)
    assert replay.idempotent_replay is True
    assert replay.world_revision == 1
    assert snapshot(path) == before


@pytest.mark.parametrize(
    "plain_value",
    [
        {"object_id": "opaque-id", "revision": 1},
        {
            "object_id": "opaque-source",
            "revision": 1,
            "source_locator": "src://opaque",
        },
    ],
)
def test_legacy_ambiguous_ref_shaped_plain_json_fails_closed(
    tmp_path: Path,
    plain_value: dict[str, Any],
) -> None:
    path = tmp_path / "legacy-ambiguous-plain.db"
    store = SQLiteWorldStore(path)
    request = op("legacy-ambiguous-plain")
    obj = obs("legacy-ambiguous-reader", metadata={"value": plain_value})
    store.commit([obj], request)
    strip_semantic_fingerprint(path, request.idempotency_key)
    assert_protocol_failure_unchanged(
        SQLiteWorldStore(path),
        [obj],
        request,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    )


@pytest.mark.parametrize("kind", ["object", "source"])
def test_legacy_row_never_guesses_typed_reference_equal_to_opaque_dict(
    tmp_path: Path,
    kind: str,
) -> None:
    path = tmp_path / f"legacy-typed-{kind}.db"
    store = SQLiteWorldStore(path)
    request = op(f"legacy-typed-{kind}")
    typed, plain = ref_pair(kind)
    opaque_obj = obs("legacy-typed-reader", metadata={"value": plain})
    store.commit([opaque_obj], request)
    strip_semantic_fingerprint(path, request.idempotency_key)
    typed_obj = obs("legacy-typed-reader", metadata={"value": typed})
    assert_protocol_failure_unchanged(
        SQLiteWorldStore(path),
        [typed_obj],
        request,
        ErrorCode.IDEMPOTENCY_CONFLICT,
    )


# G. Reference consistency.
def test_missing_reference_is_not_found_and_atomic(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "missing-ref.db")
    reader = obs(
        "missing-reader",
        metadata={"ref": ObjectRef(object_id="missing", revision=1)},
    )
    assert_protocol_failure_unchanged(
        store,
        [reader],
        op("missing-ref"),
        ErrorCode.NOT_FOUND,
    )


@pytest.mark.parametrize("revision", [None, 1])
def test_current_or_floating_self_reference_is_dependency_invalid(
    tmp_path: Path,
    revision: int | None,
) -> None:
    store = SQLiteWorldStore(tmp_path / "self-ref.db")
    reader = obs(
        "self-reader",
        metadata={"ref": ObjectRef(object_id="self-reader", revision=revision)},
    )
    assert_protocol_failure_unchanged(
        store,
        [reader],
        op(f"self-ref-{revision}"),
        ErrorCode.DEPENDENCY_INVALID,
    )


def test_pinned_self_reference_to_prior_revision_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "pinned-self-prior.db"
    store = SQLiteWorldStore(path)
    store.commit([obs("self-history", value="r1")], op("self-history-r1"))
    second = obs(
        "self-history",
        revision=2,
        value="r2",
        metadata={"prior": ObjectRef(object_id="self-history", revision=1)},
    )
    result = store.commit([second], op("self-history-r2", 1))
    assert result.world_revision == 2
    assert store.get_payload("self-history")["revision"] == 2


def test_same_transaction_reference_is_visible_when_time_consistent(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "same-transaction.db")
    target = obs("same-target", learned_at=T0, recorded_at=T0)
    reader_time = T0 + timedelta(minutes=1)
    reader = obs(
        "same-reader",
        learned_at=reader_time,
        recorded_at=reader_time,
        metadata={"ref": ObjectRef(object_id="same-target", revision=1)},
    )
    result = store.commit([reader, target], op("same-transaction"))
    assert result.world_revision == 1
    assert snapshot(store.db_path) == (1, 1, 2, 1, 1)


def test_evidence_set_cutoff_excludes_future_known_reference(tmp_path: Path) -> None:
    path = tmp_path / "evidence-cutoff.db"
    store = SQLiteWorldStore(path)
    target_time = T0 + timedelta(hours=1)
    store.commit(
        [obs("cutoff-target", learned_at=target_time, recorded_at=target_time)],
        op("cutoff-seed"),
    )
    evidence_time = T0 + timedelta(hours=2)
    evidence = EvidenceSet(
        **base_fields(
            "cutoff-evidence",
            learned_at=evidence_time,
            recorded_at=evidence_time,
        ),
        purpose="cutoff check",
        knowledge_window=KnowledgeWindow(
            knowledge_cutoff=T0,
            world_revision=1,
        ),
        member_refs=[ObjectRef(object_id="cutoff-target", revision=1)],
        selection_method="explicit",
    )
    assert_protocol_failure_unchanged(
        store,
        [evidence],
        op("cutoff-evidence", 1),
        ErrorCode.NOT_FOUND,
    )


def test_generic_future_known_reference_is_not_visible(tmp_path: Path) -> None:
    path = tmp_path / "future-known.db"
    store = SQLiteWorldStore(path)
    target_time = T0 + timedelta(hours=1)
    store.commit(
        [obs("future-target", learned_at=target_time, recorded_at=target_time)],
        op("future-seed"),
    )
    reader = obs(
        "future-reader",
        metadata={"ref": ObjectRef(object_id="future-target", revision=1)},
    )
    assert_protocol_failure_unchanged(
        store,
        [reader],
        op("future-reader", 1),
        ErrorCode.NOT_FOUND,
    )


def test_stale_expected_world_revision_is_version_conflict_and_atomic(
    tmp_path: Path,
) -> None:
    store = SQLiteWorldStore(tmp_path / "stale-world.db")
    store.commit([obs("stale-seed")], op("stale-seed"))
    assert_protocol_failure_unchanged(
        store,
        [obs("stale-reader")],
        op("stale-reader", 0),
        ErrorCode.VERSION_CONFLICT,
    )


# H. Canonical object identity and mapping keys.
def test_canonical_object_type_persists_as_declared(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "canonical-type.db")
    store.commit([obs("canonical-type")], op("canonical-type"))
    payload = store.get_payload("canonical-type")
    assert payload["object_type"] == ObjectType.OBSERVATION.value


def test_wrong_concrete_model_claiming_other_canonical_type_is_rejected(
    tmp_path: Path,
) -> None:
    store = SQLiteWorldStore(tmp_path / "wrong-model-type.db")
    dirty = obs("wrong-model-type").model_copy(
        update={"object_type": ObjectType.DEPENDENCY}
    )
    assert_protocol_failure_unchanged(
        store,
        [dirty],
        op("wrong-model-type"),
        ErrorCode.INVALID_ARGUMENT,
    )


def test_dirty_equivalent_object_type_string_normalizes(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "dirty-type-string.db")
    dirty = obs("dirty-type-string").model_copy(update={"object_type": "observation"})
    store.commit([dirty], op("dirty-type-string"))
    assert store.get_payload("dirty-type-string")["object_type"] == "observation"


def test_unknown_dirty_object_type_is_invalid_argument_and_atomic(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "unknown-type.db")
    dirty = obs("unknown-type").model_copy(update={"object_type": "not-a-type"})
    assert_protocol_failure_unchanged(
        store,
        [dirty],
        op("unknown-type"),
        ErrorCode.INVALID_ARGUMENT,
    )


@pytest.mark.parametrize(
    "value",
    [
        {1: "integer-key"},
        {1: "integer-key", "1": "string-key"},
    ],
)
def test_non_string_mapping_keys_are_rejected_without_silent_collision(
    tmp_path: Path,
    value: dict[Any, Any],
) -> None:
    store = SQLiteWorldStore(tmp_path / "mapping-keys.db")
    dirty = obs("mapping-keys").model_copy(update={"value": value})
    assert_protocol_failure_unchanged(
        store,
        [dirty],
        op("mapping-keys"),
        ErrorCode.INVALID_ARGUMENT,
    )


def test_non_string_mapping_key_in_operation_arguments_is_atomic(tmp_path: Path) -> None:
    store = SQLiteWorldStore(tmp_path / "mapping-key-arguments.db")
    request = op("mapping-key-arguments").model_copy(
        update={"arguments": {"outer": {1: "integer", "1": "string"}}}
    )
    assert_protocol_failure_unchanged(
        store,
        [obs("mapping-key-arguments")],
        request,
        ErrorCode.INVALID_ARGUMENT,
    )
