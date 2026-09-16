import json
from pathlib import Path
import pytest
from aios_core.simulation.cleaning_arena_protocol import DirectionalSemanticMatcher

def test_cross_banks_reports():
    reports_dir = Path("benchmarks/data_cleaning/reports")
    rep1 = reports_dir / "report_01a0aa2c_on_fantonghui.json"
    rep2 = reports_dir / "report_01a0aa2c_on_01a0a9ff.json"
    
    assert rep1.exists()
    assert rep2.exists()
    
    data1 = json.loads(rep1.read_text(encoding="utf-8"))
    assert data1["solver_agent"] == "01a0aa2c-fantonghui"
    assert data1["total_questions"] == 10000
    assert data1["average_score"] >= 90.0
    assert data1["pass_rate_percent"] == 100.0
    assert data1["verdict"] == "PASS"

    data2 = json.loads(rep2.read_text(encoding="utf-8"))
    assert data2["solver_agent"] == "01a0aa2c-fantonghui"
    assert data2["total_questions"] == 10000
    assert data2["average_score"] >= 90.0
    assert data2["pass_rate_percent"] == 100.0
    assert data2["verdict"] == "PASS"

def test_no_self_solving_in_cleaning():
    for f in ["ans_01a0aa2c_on_fantonghui.jsonl", "ans_01a0aa2c_on_01a0a9ff.jsonl"]:
        path = Path("benchmarks/data_cleaning/answers") / f
        assert path.exists()
        with open(path, "r", encoding="utf-8") as fp:
            first_line = json.loads(fp.readline())
            assert first_line["solver_agent"] == "01a0aa2c-fantonghui"
            assert first_line["generator_agent"] != "01a0aa2c-fantonghui"
