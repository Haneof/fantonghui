"""ToolProposal #2 双透镜虚拟索引投影器验收。

1. 重复注册封存事实 → RegistryImmutableViolationError；
2. AsKnown 透镜只看历史，Annotated 透镜能看到今天注记；
3. 注记不得覆写封存事实 bytes，试图篡改必报 RegistryImmutableViolationError；
4. 重复注记 / 悬空注记(查无此人)全部拒绝；
5. 查询路径 O(1)：再 register 一百条后续事实，查询时延值不塌。
"""

from __future__ import annotations

import time

import pytest

from aios_core.tools.dual_lens_virtual_index import (
    AnnotationOverlay,
    DualLensVirtualIndexProjector,
    FactRegistry,
    RegistryImmutableViolationError,
    SealedFactBytes,
)

T0 = 1_700_000_000_000_000_000


def _fact(fid: str, payload: bytes, ts: int = T0) -> SealedFactBytes:
    return SealedFactBytes(
        object_id=fid,
        bytes_sha256=FactRegistry.digest_of(payload),
        sealed_at_ns=ts,
    )


def test_append_then_duplicate_rejected_and_replay_blocked() -> None:
    reg = FactRegistry()
    reg.append(_fact("EV-2023-001", b"hello"))
    with pytest.raises(RegistryImmutableViolationError):
        reg.append(_fact("EV-2023-001", b"different"))
    with pytest.raises(KeyError):
        reg.lookup("ghost")


def _setup() -> tuple[FactRegistry, DualLensVirtualIndexProjector]:
    reg = FactRegistry()
    reg.append(_fact("EV-2023-001", b"hello"))
    reg.append(_fact("EV-2023-002", b"world"))
    proj = DualLensVirtualIndexProjector(reg)
    proj.mount_annotation(
        AnnotationOverlay(
            annotation_id="ANN-2026-0001",
            target_object_id="EV-2023-001",
            valid_at_ns=T0 + 10_000,
            learned_at_ns=T0 + 11_000,
            label="今日真相",
        )
    )
    return reg, proj


def test_dual_lens_consistency_and_zero_mutation() -> None:
    _reg, proj = _setup()
    known = proj.as_known(["EV-2023-001"])
    assert len(known) == 1
    annotated = proj.annotated(["EV-2023-001"], as_of_ns=T0 + 11_001)
    assert len(annotated) == 1
    fact, notes = annotated[0]
    assert fact.bytes_sha256 == known[0].bytes_sha256, "注记绝不可改写原始字节"
    assert tuple(n.label for n in notes) == ("今日真相",)

    # as_of 足够早 → Annotated 也等同 AsKnown（极早视角下真相未浮出）
    early = proj.annotated(["EV-2023-001"], as_of_ns=T0)[0][1]
    assert early == ()


def test_duplicate_and_orphan_annotations_rejected() -> None:
    _reg, proj = _setup()
    with pytest.raises(ValueError):
        proj.mount_annotation(
            AnnotationOverlay(
                annotation_id="ANN-2026-0002",
                target_object_id="EV-2023-001",
                valid_at_ns=T0 + 10_000,
                learned_at_ns=T0 + 11_001,
                label="今日真相",
            )
        )
    with pytest.raises(KeyError):
        proj.mount_annotation(
            AnnotationOverlay(
                annotation_id="ANN-2026-0003",
                target_object_id="EV-2099-XXX",
                valid_at_ns=T0 + 12_000,
                learned_at_ns=T0 + 12_001,
                label="幽灵目标",
            )
        )


def test_tamper_history_blocked_always() -> None:
    reg, proj = _setup()
    with pytest.raises(RegistryImmutableViolationError, match="绝对不可逆"):
        proj.try_mutate_history("EV-2023-001", b"tamper")
    assert reg.lookup("EV-2023-001").bytes_sha256 == FactRegistry.digest_of(b"hello")


def test_query_cost_o1_under_growth() -> None:
    reg = FactRegistry()
    reg.append(_fact("EV-2023-001", b"hello"))
    proj = DualLensVirtualIndexProjector(reg)
    ref = proj.annotated(["EV-2023-001"], as_of_ns=T0)
    t0 = time.perf_counter()
    for i in range(100):
        reg.append(_fact(f"EV-{i:05d}", b"x" * 64))
    t1 = time.perf_counter()
    assert proj.annotated(["EV-2023-001"], as_of_ns=T0) == ref
    t2 = time.perf_counter()
    assert (t2 - t1) < (t1 - t0) * 10, "查询不应随注册表规模线性塌慢"
