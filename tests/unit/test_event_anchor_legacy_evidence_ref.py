"""M0-012 compatibility guard for legacy EventAnchor.evidence_set_refs."""
from datetime import datetime, timezone
from typing import get_args, get_origin, get_type_hints

import pytest
from pydantic import ValidationError

from aios_core.contracts.enums import ObjectType
from aios_core.contracts.ids import new_object_id
from aios_core.contracts.models import EventAnchor
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import TemporalExtent


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_event_generic_evidence_refs_remain_exact_and_pinned():
    hints = get_type_hints(EventAnchor)
    annotation = hints["evidence_set_refs"]
    assert get_origin(annotation) is list
    assert get_args(annotation) == (ObjectRef,)

    with pytest.raises(ValidationError, match="evidence_set_refs requires pinned"):
        EventAnchor(
            object_id=new_object_id(ObjectType.EVENT),
            subject_id="user-1",
            learned_at=BASE,
            recorded_at=BASE,
            created_by="test",
            title="candidate",
            interpretation="candidate interpretation",
            event_time=TemporalExtent.point(BASE),
            confidence=0.4,
            evidence_set_refs=[
                ObjectRef(
                    object_id=new_object_id(ObjectType.EVIDENCE_SET),
                    revision=None,
                )
            ],
        )
