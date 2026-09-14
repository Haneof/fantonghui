"""M0-011 exact DimensionLifecycle freeze from R2."""
from aios_core.contracts.enums import DimensionLifecycle


def test_dimension_lifecycle_exact_r2_members():
    assert [member.name for member in DimensionLifecycle] == [
        "CANDIDATE",
        "TRIAL",
        "ACTIVE",
        "LOW_ACTIVITY",
        "DORMANT",
        "MERGED",
        "SPLIT",
        "REVISED",
        "REJECTED",
        "REACTIVATED",
    ]
    assert [member.value for member in DimensionLifecycle] == [
        "candidate",
        "trial",
        "active",
        "low_activity",
        "dormant",
        "merged",
        "split",
        "revised",
        "rejected",
        "reactivated",
    ]
