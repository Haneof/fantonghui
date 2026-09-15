#!/usr/bin/env python3
"""hash_registry.py 的版本化登记纪律 —— 规则①②③组合缺陷的回归守卫。

为什么需要这个文件
------------------
2026-09-16，我在把政策层从 v1.0.0 升到 v1.1.0 时撞上一个死结：

  规则②「已入库的行禁止改写，追加新版本行代替」
  规则③「任何已登记文件的实际哈希与表内不符即红检」

而 `check()` 会把**每一行**的哈希都拿去和**当前**文件内容比对。于是：
一份已登记文件只要合法演进，旧版本行就永久漂移、CI 永红；
而改写旧行的哈希格又被规则②明令禁止。

**规则②给出的唯一合法出路，恰好是规则③判红的唯一形态。**
注册表原本没有任何一条路径允许一份已登记文件演进。这不是实现瑕疵，
是三条规则的组合缺陷 —— 而且它只会在第一次有人认真修改一份已登记文件时暴露，
也就是恰好在治理开始起作用的那一刻。

处置（窄口径、防滥用、不改写任何哈希格）
----------------------------------------
状态格显式含机读标记 `HISTORICAL-ROW` 的行，视为"同一文件已被取代的历史版本"：
  · check() 不再拿它与当前文件内容比对（比对本就无意义）；
  · 其历史哈希仍完整留在表内，可审计、可回放（ADJ-004 版本链永存）；
  · 但**同一路径必须另有一行处于 CURRENT/REGISTERED 作为活继任者**，
    否则该标记立即判红 —— 不然它就成了把任意文件永久豁免出校验的后门；
  · --fill 拒绝向 HISTORICAL-ROW 的哈希格写入任何内容。

本文件用合成注册表逐条钉死上述行为。它守的不是哈希算法（那是 trivially 正确的），
而是**豁免权的边界** —— 一个能被滥用的豁免机制比没有豁免更危险。

纯标准库；pytest 与独立运行双入口。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "governance" / "hash_registry.py"
REAL_REGISTRY = REPO_ROOT / "governance" / "normative_versions" / "registry.md"

HIST = "HISTORICAL-ROW"


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("hash_registry_under_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None, f"无法加载 {TOOL_PATH}"
    mod = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules 再 exec：被测工具用 @dataclass 定义 Row，
    # 而 dataclasses._is_type 会反查 sys.modules[cls.__module__].__dict__；
    # 模块尚未入表时会抛 AttributeError: 'NoneType' object has no attribute '__dict__'。
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return mod


TOOL = _load_tool()


def _row(spec: str, rel: str, ver: str, hash_cell: str, status: str) -> str:
    return f"| {spec} | `{rel}` | {ver} | {hash_cell} | {status} | CONST-v3.0.1 |"


def _build(tmp: Path, rows: list[str]) -> tuple[Path, Path]:
    """在临时目录里搭一个最小仓库：一份被登记的文件 + 一份注册表。"""
    reg_dir = tmp / "governance" / "normative_versions"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg = reg_dir / "registry.md"
    reg.write_text(
        "# 规范版本注册表（合成）\n\n"
        "| 规范编号 | 文件路径 | 版本 | sha256 | 状态 | 来源 |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return reg, tmp


def _sandboxed(reg: Path, root: Path):
    """把工具的 REPO_ROOT / REGISTRY_PATH 指到临时目录。"""
    old_root, old_reg = TOOL.REPO_ROOT, TOOL.REGISTRY_PATH
    TOOL.REPO_ROOT, TOOL.REGISTRY_PATH = root, reg

    def restore() -> None:
        TOOL.REPO_ROOT, TOOL.REGISTRY_PATH = old_root, old_reg

    return restore


def _check(reg: Path, root: Path) -> tuple[list[str], list[str], list[str]]:
    restore = _sandboxed(reg, root)
    try:
        _lines, rows = TOOL.parse_rows(reg.read_text(encoding="utf-8"))
        return TOOL.check(rows)
    finally:
        restore()


def _fill(reg: Path, root: Path) -> tuple[list[str], list[str]]:
    restore = _sandboxed(reg, root)
    try:
        lines, rows = TOOL.parse_rows(reg.read_text(encoding="utf-8"))
        new_lines, filled, problems = TOOL.fill(lines, rows)
        reg.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return filled, problems
    finally:
        restore()


# ---------------------------------------------------------------------------
# 1. 基线行为必须保持不变（豁免机制不得削弱原有守卫）
# ---------------------------------------------------------------------------


def test_live_row_drift_is_still_red() -> None:
    """规则③：活行漂移必须判红。引入豁免机制不能顺手把这条主守卫弄钝。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"v": 2}', encoding="utf-8")
        stale = TOOL.sha256_of_bytes(b'{"v": 1}') if hasattr(TOOL, "sha256_of_bytes") else None
        if stale is None:
            import hashlib

            stale = hashlib.sha256(b'{"v": 1}').hexdigest()
        reg, root = _build(tmp, [_row("POLICY", "governance/policy.json", "2.0", f"`{stale}`", "**CURRENT**")])

        ok, drift, _skipped = _check(reg, root)
        assert not ok, "漂移行不应被判为 OK"
        assert len(drift) == 1 and "哈希漂移" in drift[0], f"漂移未被判红: {drift}"


def test_registered_file_missing_is_still_red() -> None:
    """已登记但文件消失，必须判红 —— 不能因为"读不到"就当"没要求"。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        import hashlib

        fake = hashlib.sha256(b"nothing").hexdigest()
        reg, root = _build(
            tmp, [_row("GONE", "governance/gone.json", "1.0", f"`{fake}`", "**CURRENT**")]
        )
        ok, drift, _skipped = _check(reg, root)
        assert not ok
        assert len(drift) == 1 and "文件缺失" in drift[0], f"文件缺失未判红: {drift}"


# ---------------------------------------------------------------------------
# 2. 新的合法演进路径
# ---------------------------------------------------------------------------


def test_historical_row_with_live_successor_is_green() -> None:
    """规则②的唯一合法出路：追加新版本行 + 旧行标 HISTORICAL-ROW → 全绿。

    这就是本轮 POLICY-RUNTIME 1.0.0 → 1.1.0 实际走的路径。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"policy_version": "1.1.0"}', encoding="utf-8")
        import hashlib

        old_hash = hashlib.sha256(b'{"policy_version": "1.0.0"}').hexdigest()
        new_hash = TOOL.sha256_of(f)
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{old_hash}`",
                     f"SUPERSEDED · {HIST}（历史哈希证据，规则②不改写）"),
                _row("POLICY", "governance/policy.json", "1.1.0", f"`{new_hash}`", "**CURRENT**"),
            ],
        )
        ok, drift, skipped = _check(reg, root)
        assert not drift, f"合法演进路径被判红: {drift}"
        assert not skipped
        assert len(ok) == 2, f"应两行都 OK（一行历史、一行活），实得 {ok}"
        assert any("historical" in o for o in ok), f"历史行未被标注为 historical: {ok}"
        assert any(new_hash[:16] in o for o in ok)


def test_historical_hash_is_preserved_verbatim_in_the_table() -> None:
    """ADJ-004 版本链永存：豁免比对不等于删除历史哈希。旧哈希必须逐字留在表内。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("new", encoding="utf-8")
        import hashlib

        old_hash = hashlib.sha256(b"old").hexdigest()
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{old_hash}`",
                     f"SUPERSEDED · {HIST}"),
                _row("POLICY", "governance/policy.json", "1.1.0",
                     f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        text = reg.read_text(encoding="utf-8")
        assert old_hash in text, "历史哈希被删掉了 —— 违反 ADJ-004 版本链永存"
        _ok, drift, _sk = _check(reg, root)
        assert not drift


# ---------------------------------------------------------------------------
# 3. 防滥用不变量（这是本机制最关键的部分）
# ---------------------------------------------------------------------------


def test_historical_row_without_successor_is_red() -> None:
    """没有活继任者的 HISTORICAL-ROW 必须判红。

    否则这个标记就是一个后门：给任何文件的状态格加上它，
    该文件就永久退出哈希校验 —— 而表看起来仍然"全绿"。
    **一个能被滥用的豁免机制，比没有豁免更危险。**
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("whatever", encoding="utf-8")
        import hashlib

        unrelated = hashlib.sha256(b"something else entirely").hexdigest()
        reg, root = _build(
            tmp, [_row("POLICY", "governance/policy.json", "1.0.0", f"`{unrelated}`",
                       f"SUPERSEDED · {HIST}（无继任者）")]
        )
        ok, drift, _skipped = _check(reg, root)
        assert not ok, "无继任者的历史行不该被判 OK"
        assert len(drift) == 1 and "无活继任者" in drift[0], f"防滥用不变量未开火: {drift}"


def test_successor_must_share_the_same_path_not_just_the_same_spec_id() -> None:
    """继任者必须是**同一路径**的活行。只认 spec_id 会让"改指向别的文件"蒙混过关。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("a.json", "b.json"):
            f = tmp / "governance" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(name, encoding="utf-8")
        reg, root = _build(
            tmp,
            [
                # 历史行指向 a.json；活行 spec_id 相同但指向 b.json —— 不构成继任
                _row("POLICY", "governance/a.json", "1.0.0",
                     f"`{TOOL.sha256_of(tmp / 'governance' / 'a.json')}`",
                     f"SUPERSEDED · {HIST}"),
                _row("POLICY", "governance/b.json", "2.0.0",
                     f"`{TOOL.sha256_of(tmp / 'governance' / 'b.json')}`", "**CURRENT**"),
            ],
        )
        _ok, drift, _sk = _check(reg, root)
        assert any("无活继任者" in d for d in drift), (
            f"仅凭 spec_id 相同就认作继任者 —— 路径校验被绕过: {drift}"
        )


def test_a_dead_status_does_not_qualify_as_successor() -> None:
    """继任者必须处于 CURRENT/REGISTERED。拿一条 ARCHIVED 行当继任者不算活。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
        import hashlib

        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0",
                     f"`{hashlib.sha256(b'old').hexdigest()}`", f"SUPERSEDED · {HIST}"),
                _row("POLICY", "governance/policy.json", "1.1.0",
                     f"`{TOOL.sha256_of(f)}`", "ARCHIVED（已归档，不再生效）"),
            ],
        )
        _ok, drift, _sk = _check(reg, root)
        assert any("无活继任者" in d for d in drift), f"ARCHIVED 行被误认为活继任者: {drift}"


# ---------------------------------------------------------------------------
# 4. --fill 的纪律
# ---------------------------------------------------------------------------


def test_fill_refuses_to_write_into_a_historical_hash_cell() -> None:
    """历史哈希格是证据，即使它是占位形态也不许被 --fill 写入。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("live", encoding="utf-8")
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", "（待回填）",
                     f"SUPERSEDED · {HIST}"),
                _row("POLICY", "governance/policy.json", "1.1.0", "（待回填）", "**CURRENT**"),
            ],
        )
        filled, problems = _fill(reg, root)
        assert len(filled) == 1, f"只应补登活行，实得 {filled}"
        assert any(HIST in pr for pr in problems), f"--fill 未拒绝改写历史格: {problems}"

        lines = [l for l in reg.read_text(encoding="utf-8").splitlines() if l.startswith("| POLICY")]
        hist_line = next(l for l in lines if HIST in l)
        assert "待回填" in hist_line, "历史行的占位格被写入了内容"
        live_line = next(l for l in lines if "CURRENT" in l)
        assert TOOL.sha256_of(f) in live_line, "活行未被正确补登"


def test_fill_never_rewrites_an_already_pinned_hash_cell() -> None:
    """规则②：--fill 只填空。已钉住的哈希格即使在文件演进后也绝不改写。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("v2 content", encoding="utf-8")
        import hashlib

        pinned = hashlib.sha256(b"v1 content").hexdigest()
        reg, root = _build(
            tmp, [_row("POLICY", "governance/policy.json", "1.0.0", f"`{pinned}`", "**CURRENT**")]
        )
        filled, _problems = _fill(reg, root)
        assert not filled, "--fill 改写了已钉住的哈希格 —— 违反规则②"
        assert pinned in reg.read_text(encoding="utf-8")


def test_rows_sharing_a_spec_id_are_checked_against_their_own_hash_cell() -> None:
    """同一 spec_id 多行时，必须逐行比对自己的哈希格。

    我在判决门里先犯过这个错：用 `startswith(f"| {spec} |")` 取第一个匹配行，
    结果把历史行的哈希拿去和当前文件比，制造了一条永远无法消除的假红。
    工具侧按行解析（cells[3]）本来就是对的 —— 这条断言把它钉住，防止将来
    有人"优化"成按 spec_id 查表。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("current", encoding="utf-8")
        import hashlib

        old = hashlib.sha256(b"previous").hexdigest()
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{old}`",
                     f"SUPERSEDED · {HIST}"),
                _row("POLICY", "governance/policy.json", "1.1.0",
                     f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        ok, drift, _sk = _check(reg, root)
        assert not drift, f"按 spec_id 而非按行比对会造成假红: {drift}"
        assert len(ok) == 2


# ---------------------------------------------------------------------------
# 5. 真实注册表的集成校验
# ---------------------------------------------------------------------------


def test_the_real_registry_is_green_and_has_legal_succession() -> None:
    """仓库里的真实 registry.md 必须全绿，且每条历史行都有同路径的活继任者。"""
    assert REAL_REGISTRY.is_file(), f"注册表缺失: {REAL_REGISTRY}"
    _lines, rows = TOOL.parse_rows(REAL_REGISTRY.read_text(encoding="utf-8"))
    ok, drift, skipped = TOOL.check(rows)
    assert not drift, "真实注册表存在哈希漂移（规则③）:\n" + "\n".join(drift)
    assert not skipped, f"真实注册表仍有占位未补登: {skipped}"

    live_paths: dict[str, list[str]] = {}
    for r in rows:
        if HIST not in r.status_cell and TOOL.LIVE_STATUS.search(r.status_cell):
            live_paths.setdefault(r.path_cell, []).append(r.spec_id)
    historical = [r for r in rows if HIST in r.status_cell]
    assert historical, (
        "真实注册表里没有任何 HISTORICAL-ROW —— 本轮 POLICY-RUNTIME 1.0.0→1.1.0 与 "
        "PLAN-R4-B R4→R4.1 两次演进应当留下历史行；若确实没有，说明历史被改写而非追加"
    )
    for r in historical:
        assert live_paths.get(r.path_cell), f"[{r.spec_id}] 历史行无活继任者: {r.path_cell}"


def test_the_real_policy_and_plan_rows_carry_both_versions() -> None:
    """演进必须留下两行（历史 + 活），而不是把一行改成新值。

    这条断言直接把规则②的"追加而非改写"钉在真实注册表上。
    """
    text = REAL_REGISTRY.read_text(encoding="utf-8")
    _lines, rows = TOOL.parse_rows(text)
    by_spec: dict[str, list[Any]] = {}
    for r in rows:
        by_spec.setdefault(r.spec_id, []).append(r)

    for spec, versions in (("POLICY-RUNTIME", ("1.0.0", "1.1.0")),
                           ("PLAN-R4-B", ("R4", "R4.1"))):
        got = by_spec.get(spec, [])
        cells = [r.cells[2].strip("*").strip() for r in got]
        for v in versions:
            assert v in cells, f"{spec} 缺少版本行 {v}（实得 {cells}）—— 疑似改写了已入库的行"
        hist = [r for r in got if HIST in r.status_cell]
        assert len(hist) == 1, f"{spec} 应恰有一条历史行，实得 {len(hist)}"


def test_the_tool_documents_the_rule_combination_defect() -> None:
    """工具必须在自己的文档里写明这个死结是怎么来的、怎么处置的。

    一个"看起来能用"的豁免标记，如果不在源码里说明它的边界与滥用后果，
    下一个人只会把它当成"让 CI 变绿的方法"来用。
    """
    src = TOOL_PATH.read_text(encoding="utf-8")
    for needle in (HIST, "无活继任者", "规则②给出的唯一合法出路"):
        assert needle in src, f"工具源码未记载 {needle!r} —— 豁免机制的边界没有被文档化"




def test_fill_preserves_row_padding_so_the_diff_stays_auditable() -> None:
    """--fill 只应改变哈希格，不得重排整行。

    实测发现的缺陷：fill() 原来用 strip 过的 cells 重新拼行，于是每次补登都把该行
    压扁成 |SPEC|`path`|ver|`hash`|，与表内其余行的 `| X | ` 排版不一致。
    后果不是美观问题：治理表是靠 diff 评审的，一次只改一格的补登若把整行重写，
    评审者就无法一眼看出动了哪一格 —— 而"看不出动了哪一格"正是篡改最想要的属性。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = tmp / "governance" / "policy.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("content", encoding="utf-8")
        reg, root = _build(
            tmp, [_row("POLICY", "governance/policy.json", "1.0.0", "（待回填）", "**CURRENT**")]
        )
        before = [l for l in reg.read_text(encoding="utf-8").splitlines() if l.startswith("| POLICY")]
        assert len(before) == 1
        filled, _problems = _fill(reg, root)
        assert len(filled) == 1
        after = [l for l in reg.read_text(encoding="utf-8").splitlines() if l.startswith("| POLICY")]
        assert len(after) == 1, f"补登后该行不再以 '| POLICY' 开头（排版被压扁）: {after}"

        b_cells = before[0].strip().strip("|").split("|")
        a_cells = after[0].strip().strip("|").split("|")
        assert len(b_cells) == len(a_cells) == 6
        for i, (b, a) in enumerate(zip(b_cells, a_cells)):
            if i == 3:
                assert b != a, "哈希格没有被写入"
                assert b.strip() != a.strip() or True
            else:
                assert b == a, f"第 {i} 格在补登时被改写：{b!r} → {a!r}（应只动哈希格）"
        # 每格的前导/尾随空白必须原样保留
        assert after[0].count("| ") == before[0].count("| ") == 6


if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures.append((name, str(exc)))
            print(f"  FAIL  {name}\n          {exc}")
        except Exception as exc:  # noqa: BLE001 - fail-closed
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed, {len(failures)} failed")
    print(f"tool:     {TOOL_PATH.relative_to(REPO_ROOT)}")
    print(f"registry: {REAL_REGISTRY.relative_to(REPO_ROOT)}")
    sys.exit(1 if failures else 0)
