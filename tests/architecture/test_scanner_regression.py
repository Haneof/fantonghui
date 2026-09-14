"""M0-001-R2 新增：architecture scanner 自身回归测试"""
import pathlib

import pytest

from tests.architecture.test_boundaries import (
    _has_import_sqlite3,
    _has_import_storage_internal,
    _has_import_evaluator,
    _parse_file_or_fail,
)

def _write_temp(tmp_path: pathlib.Path, code: str) -> pathlib.Path:
    p = tmp_path / "sample.py"
    p.write_text(code, encoding="utf-8")
    return p

def test_case1_import_sqlite3(tmp_path):
    f = _write_temp(tmp_path, "import sqlite3\n")
    assert _has_import_sqlite3(f) is True

def test_case2_from_sqlite3_import(tmp_path):
    f = _write_temp(tmp_path, "from sqlite3 import connect\n")
    assert _has_import_sqlite3(f) is True

def test_case3_import_aios_core_storage(tmp_path):
    f = _write_temp(tmp_path, "import aios_core.storage\n")
    assert _has_import_storage_internal(f) is True

def test_case4_from_aios_core_storage_import(tmp_path):
    f = _write_temp(tmp_path, "from aios_core.storage import SQLiteWorldStore\n")
    assert _has_import_storage_internal(f) is True

def test_case5_from_aios_core_import_storage(tmp_path):
    f = _write_temp(tmp_path, "from aios_core import storage\n")
    assert _has_import_storage_internal(f) is True

def test_case6_from_aios_core_import_storage_as(tmp_path):
    f = _write_temp(tmp_path, "from aios_core import storage as core_storage\n")
    assert _has_import_storage_internal(f) is True

def test_case7_import_evaluator(tmp_path):
    f = _write_temp(tmp_path, "import evaluator\n")
    assert _has_import_evaluator(f) is True

def test_case8_from_evaluator_import_truth(tmp_path):
    f = _write_temp(tmp_path, "from evaluator import truth\n")
    assert _has_import_evaluator(f) is True

def test_case9_legal_from_contracts(tmp_path):
    f = _write_temp(tmp_path, "from aios_core.contracts import Claim\n")
    assert _has_import_sqlite3(f) is False
    assert _has_import_storage_internal(f) is False
    assert _has_import_evaluator(f) is False

def test_case10_unparsable_file_must_fail(tmp_path):
    """CASE-10 无法 parse 的文件 => scanner 必须 fail-closed (抛 AssertionError)"""
    f = _write_temp(tmp_path, "def broken(:\n  this is not valid python !!!\n")
    with pytest.raises(AssertionError):
        _parse_file_or_fail(f)
    with pytest.raises(AssertionError):
        _has_import_sqlite3(f)

def test_case_extra_import_storage_submodule(tmp_path):
    f = _write_temp(tmp_path, "import aios_core.storage.sqlite_store\n")
    assert _has_import_storage_internal(f) is True

def test_case_extra_from_storage_submodule(tmp_path):
    f = _write_temp(tmp_path, "from aios_core.storage.sqlite_store import SQLiteWorldStore\n")
    assert _has_import_storage_internal(f) is True
