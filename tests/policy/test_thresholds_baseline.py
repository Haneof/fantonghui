"""阈值出厂基线（governance/thresholds/baseline_v1.json）的守宪门 —— ADJ-008。

与 tests/policy/test_runtime_policy.py 同一品味：纯标准库、双入口、fail-closed。

执法点（逐条对应 ADJ-008 裁决文本）：
  (a) 宪法不写数值 —— 数值只能从本文件读取，本文件缺失/损坏直接红；
  (b) 出厂基线以参数文件形态冻结 —— drift 由 hash_registry --check 闸守；
  (c) 学习足迹账本式 —— 每个可学习参数必须带 learning 元数据与 change_protocol 要求的字段集；
  (d) 人身安全硬信号不进学习型下调通道 —— safety_lane=True 的参数 learn_channel
      必须是 STRICTER_ONLY 并声明 safer_direction，禁止 DUAL/NONE 之外的第三种可能。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "governance" / "thresholds" / "baseline_v1.json"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PARAM_ID = re.compile(r"^thr\.[a-z][a-z0-9_]*\.[a-z0-9_]+$")
_LEARN_CHANNELS = {"NONE", "STRICTER_ONLY", "DUAL"}


def load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        raise AssertionError(f"阈值基线缺失: {BASELINE_PATH}")
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"阈值基线不是合法 JSON: {exc}") from exc


BASELINE = load_baseline()
PARAMS = BASELINE["parameters"]


def test_identity_block() -> None:
    assert BASELINE["adjudication_ref"] == "ADJ-008"
    assert BASELINE["constitution_ref"], "每条法律都必须有宪法出处"
    assert BASELINE["schema_version"] == "1.0.0"


def test_params_nonempty_and_unique() -> None:
    assert len(PARAMS) >= 3, "出厂基线不得空心"
    ids = [p["param_id"] for p in PARAMS]
    assert len(ids) == len(set(ids)), "param_id 重复"
    for pid in ids:
        assert _PARAM_ID.match(pid), f"param_id 不合规: {pid}"


def test_every_param_carries_constitution_and_evidence() -> None:
    for p in PARAMS:
        assert p.get("constitution_ref"), f"{p['param_id']} 无宪法出处 = 私人偏好"
        assert p.get("evidence"), f"{p['param_id']} 无依据 = 愿望不是参数"
        assert p["learn_channel"] in _LEARN_CHANNELS, p["param_id"]


def test_values_within_hard_bounds() -> None:
    for p in PARAMS:
        b = p["bounds"]
        assert b["hard_min"] <= p["value"] <= b["hard_max"], (
            f"{p['param_id']}={p['value']} 越出硬界 [{b['hard_min']},{b['hard_max']}]"
        )


def test_safety_lane_never_learns_downward() -> None:
    """ADJ-008(d)：安全硬信号不许学习型下调，且必须声明更严方向。"""
    safety = [p for p in PARAMS if p["safety_lane"]]
    assert len(safety) >= 2, "人身安全基线数量异常（至少覆盖血氧/摔倒族两条）"
    for p in safety:
        assert p["learn_channel"] == "STRICTER_ONLY", (
            f"{p['param_id']} 是安全参数却开双向学习通道"
        )
        assert p["safer_direction"] in {"raise", "lower"}, p["param_id"]


def test_learnable_params_carry_full_learning_metadata() -> None:
    for p in PARAMS:
        if p["learn_channel"] != "NONE":
            lm = p.get("learning") or {}
            assert lm.get("cycle_days", 0) >= 1, p["param_id"]
            assert 0 < lm.get("max_delta_per_cycle_pct", 0) <= 25, p["param_id"]
            assert lm.get("window_min_samples", 0) >= 1, p["param_id"]
        else:
            assert p.get("learning") is None, f"{p['param_id']} 禁学却挂学习元数据"


def test_change_protocol_is_complete_and_machine_readable() -> None:
    proto = BASELINE["change_protocol"]
    assert proto["log_object"] == "threshold_change_log"
    required = set(proto["required_fields"])
    assert {"param_id", "prev_value", "next_value", "input_window",
            "learner_hash", "reversible"} <= required
    assert len(proto["rules"]) >= 4, "ADJ-008(c)/(d) 的规则必须逐条落字面"


def test_domain_coverage() -> None:
    """至少覆盖 vital/motion/system 三个触发域，防止基线被偷换成单域。"""
    domains = {p["param_id"].split(".")[1] for p in PARAMS}
    assert {"vital", "motion", "system"} <= domains, f"触发域不全: {domains}"


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}", file=sys.stderr)
    sys.exit(1 if failed else 0)
