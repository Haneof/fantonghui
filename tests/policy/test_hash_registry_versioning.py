#!/usr/bin/env python3
"""hash_registry.py 的版本化登记纪律 —— 规则①②③组合缺陷的回归守卫。

为什么需要这个文件
------------------
2026-09-16，**两条互不知情的工作线在同一天各自撞上了同一个死结**：

  规则②「已入库的行禁止改写，追加新版本行代替」
  规则③「任何已登记文件的实际哈希与表内不符即红检」

而 `check()` 若把**每一行**的哈希都拿去和**当前**文件内容比对，则：
一份已登记文件只要合法演进，旧版本行就永久漂移、CI 永红；
而改写旧行的哈希格又被规则②明令禁止。

**规则②给出的唯一合法出路，恰好是规则③判红的唯一形态。**
注册表原本不存在任何一条路径允许一份已登记文件演进。这不是实现瑕疵，
是三条规则的组合缺陷 —— 而且它只会在第一次有人认真修改一份已登记文件时暴露，
也就是恰好在治理开始起作用的那一刻。在此之前它一直绿，因为它从未被使用过。

两条独立解法
------------
· **标记语义**（本工作线先提出）：状态格写 `HISTORICAL-ROW`，并要求同路径存在
  CURRENT/REGISTERED 的活继任者行，否则判红。
· **位置语义**（另一条工作线先落地）：追加序即时间序，同一组只有**表内最后一行**
  参与漂移比对，更早的行 archived、哈希封存。

合并时采纳**位置语义**，理由：不需要人工填写标记（少一个人为字段就少一种填错方式）；
不存在"豁免权"这个概念，因而不需要防滥用不变量 —— 最后一行永远被校验，
没有任何一行能靠自我声明退出比对；且与规则①「一行 = 一份规范的一个版本」天然一致。

但位置语义有两条必须显式限定的边界，都是实测踩出来的，本文件逐条钉死：

  边界一：**归组键是 (spec_id, path)，不是 path。**
    复合行取 "+" 之后的路径段，于是 CONST-v3.0.1（宪法原文 + 裁决集）与
    ADJ-v3.0.1（裁决集）指向同一个文件。若按 path 归组，**当前生效的宪基
    CONST-v3.0.1 会被判成"已被后续版本行取代"而 archived**，静默移出哈希校验，
    且 archived 落在 skipped 桶里不判红。实测触发过。

  边界二：**某组最后一行若是未补登的占位，必须判红而不是跳过。**
    否则在表尾追加一行占位，就能让任意已登记文件静默退出校验：
    旧行 archived 不再比对，新行占位被"待补登"跳过，--check 依然 exit 0。

另有一处可审计性缺陷（本工作线发现并修复）：fill() 原用 strip 过的 cells 重拼整行，
每次补登都把该行排版压扁，与表内其余行不一致。治理表靠 diff 评审 ——
一次只改一格的补登若把整行重写，评审者就看不出动了哪一格，
而"看不出动了哪一格"正是篡改最想要的属性。

本文件守的不是哈希算法（那 trivially 正确），而是**版本语义的边界**。
纯标准库；pytest 与独立运行双入口。
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "governance" / "hash_registry.py"
REAL_REGISTRY = REPO_ROOT / "governance" / "normative_versions" / "registry.md"


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


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _build(tmp: Path, rows: list[str]) -> tuple[Path, Path]:
    """在临时目录里搭一个最小仓库：注册表 + 需要时被登记的文件。"""
    reg_dir = tmp / "governance" / "normative_versions"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg = reg_dir / "registry.md"
    reg.write_text(
        "# 规范版本注册表（合成）\n\n"
        "| 规范编号 | 文件路径 | 版本 | sha256 | 状态 | 来源 |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return reg, tmp


def _mkfile(tmp: Path, rel: str, content: str) -> Path:
    f = tmp / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


def _sandboxed(reg: Path, root: Path):
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
# 1. 位置语义：合法演进路径
# ---------------------------------------------------------------------------


def test_appending_a_new_version_row_is_the_legal_evolution_path() -> None:
    """规则②的唯一合法出路：追加新版本行 → 全绿，旧行封存。

    这就是本轮 POLICY-RUNTIME 1.0.0 → 1.1.0 → 1.2.0 实际走的路径。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", '{"policy_version": "1.2.0"}')
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{_sha(b'v1.0.0')}`", "SUPERSEDED"),
                _row("POLICY", "governance/policy.json", "1.1.0", f"`{_sha(b'v1.1.0')}`", "SUPERSEDED"),
                _row("POLICY", "governance/policy.json", "1.2.0", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        ok, drift, skipped = _check(reg, root)
        assert not drift, f"合法演进路径被判红: {drift}"
        assert len(ok) == 1, f"只应有活行被判 OK，实得 {ok}"
        assert len(skipped) == 2, f"两条旧行应 archived，实得 {skipped}"
        assert all("archived" in s for s in skipped), skipped


def test_archived_rows_keep_their_historical_hash_verbatim() -> None:
    """ADJ-004 版本链永存：豁免比对不等于删除历史哈希。

    archived 行记录的是"该版本曾以此哈希签署"这一不可变事实，
    而不承诺"文件现在仍是这个内容"。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", "current")
        old_hash = _sha(b"an older content that no longer exists on disk")
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{old_hash}`", "SUPERSEDED"),
                _row("POLICY", "governance/policy.json", "2.0.0", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        _ok, drift, _sk = _check(reg, root)
        assert not drift
        assert old_hash in reg.read_text(encoding="utf-8"), "历史哈希被删掉了——违反 ADJ-004 版本链永存"


def test_live_row_drift_is_still_red() -> None:
    """规则③：活行漂移必须判红。引入位置语义不能顺手把这条主守卫弄钝。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _mkfile(tmp, "governance/policy.json", '{"v": 2}')
        stale_pin = _sha(b'{"v": 1}')  # Python 3.11：f-string 表达式内不得含反斜杠
        reg, root = _build(
            tmp, [_row("POLICY", "governance/policy.json", "2.0", f"`{stale_pin}`", "**CURRENT**")]
        )
        ok, drift, _sk = _check(reg, root)
        assert not ok, "漂移行不应被判为 OK"
        assert len(drift) == 1 and "哈希漂移" in drift[0], f"漂移未被判红: {drift}"


def test_registered_file_missing_is_still_red() -> None:
    """已登记但文件消失必须判红 —— 不能因为"读不到"就当"没要求"。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        reg, root = _build(
            tmp, [_row("GONE", "governance/gone.json", "1.0", f"`{_sha(b'nothing')}`", "**CURRENT**")]
        )
        ok, drift, _sk = _check(reg, root)
        assert not ok
        assert len(drift) == 1 and "文件缺失" in drift[0], f"文件缺失未判红: {drift}"


# ---------------------------------------------------------------------------
# 2. 边界一：归组键必须是 (spec_id, path)，不能是 path
# ---------------------------------------------------------------------------


def test_two_specs_sharing_one_file_are_both_checked() -> None:
    """不同 spec_id 即使指向同一文件，也各自是独立的规范工件，都必须被校验。

    实测反例：CONST-v3.0.1 是复合行（宪法v3.0.md + 裁决集），target_path 取"+"之后
    的裁决集；ADJ-v3.0.1 也指向裁决集。按 path 归组会把 CONST-v3.0.1 判成
    "已被后续版本行取代"而 archived —— **当前生效的宪基被静默移出哈希校验**。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        adj = _mkfile(tmp, "governance/adj.md", "adjudication set")
        reg, root = _build(
            tmp,
            [
                # 复合行：宪法原文 + 裁决集，target_path 取裁决集
                _row("CONST-v3.0.1", "governance/const.md + `governance/adj.md`", "3.0.1",
                     f"同上 + `{TOOL.sha256_of(adj)}`", "**CURRENT**（唯一生效宪基）"),
                _row("ADJ-v3.0.1", "governance/adj.md", "3.0.1",
                     f"`{TOOL.sha256_of(adj)}`", "**CURRENT**"),
            ],
        )
        ok, drift, skipped = _check(reg, root)
        assert not drift, f"共享文件的两个规范被判红: {drift}"
        assert not skipped, (
            f"按 path 归组会把宪基行 archived 掉（落在不判红的 skipped 桶里）: {skipped}"
        )
        assert len(ok) == 2, f"两个 spec 都应被校验，实得 {ok}"


def test_a_superseded_composite_spec_is_archived_while_the_other_stays_live() -> None:
    """同一 spec_id 的多行才构成版本链；跨 spec_id 不构成。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/adj.md", "v2 of the adjudication set")
        reg, root = _build(
            tmp,
            [
                _row("ADJ", "governance/adj.md", "3.0.1", f"`{_sha(b'v1')}`", "SUPERSEDED"),
                _row("ADJ", "governance/adj.md", "3.0.2", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
                _row("OTHER-SPEC", "governance/adj.md", "1.0", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        ok, drift, skipped = _check(reg, root)
        assert not drift
        assert len(skipped) == 1 and "ADJ 3.0.1" in skipped[0], f"只有同 spec 的旧版本该 archived: {skipped}"
        assert len(ok) == 2, f"ADJ 3.0.2 与 OTHER-SPEC 都应被校验，实得 {ok}"


# ---------------------------------------------------------------------------
# 3. 边界二：末行占位必须判红（防滥用不变量）
# ---------------------------------------------------------------------------


def test_trailing_placeholder_row_is_drift_not_skip() -> None:
    """某组最后一行是占位 → 该文件当前不受任何哈希保护 → 必须判红。

    否则在表尾追加一行占位即可让任意已登记文件静默退出校验：
    旧行 archived 不再比对，新行占位被"待补登"跳过，--check 依然 exit 0。
    **这是位置语义引入的唯一新风险，也是本机制最重要的防滥用不变量。**
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", "tampered content")
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
                _row("POLICY", "governance/policy.json", "2.0.0", "（待回填）", "**CURRENT**"),
            ],
        )
        # 先把文件改成与 1.0.0 登记值不同的内容，证明它已脱离保护
        f.write_text("content that matches no pinned hash", encoding="utf-8")
        ok, drift, _sk = _check(reg, root)
        assert not ok, "末行占位时不该有任何行被判 OK"
        assert len(drift) == 1 and "不受哈希保护" in drift[0], f"占位豁免洞未堵: {drift}"


def test_a_placeholder_in_a_non_final_row_does_not_mask_drift() -> None:
    """占位行若不在末位，则末行仍被校验 —— 顺序不能被用来藏漂移。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", "current")
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", "（待回填）", "SUPERSEDED"),
                _row("POLICY", "governance/policy.json", "2.0.0", f"`{_sha(b'stale')}`", "**CURRENT**"),
            ],
        )
        _ok, drift, _sk = _check(reg, root)
        assert len(drift) == 1 and "哈希漂移" in drift[0], f"末行漂移未被判红: {drift}"


# ---------------------------------------------------------------------------
# 4. --fill 的纪律
# ---------------------------------------------------------------------------


def test_fill_never_rewrites_an_already_pinned_hash_cell() -> None:
    """规则②：--fill 只填空。已钉住的哈希格即使在文件演进后也绝不改写。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _mkfile(tmp, "governance/policy.json", "v2 content")
        pinned = _sha(b"v1 content")
        reg, root = _build(
            tmp, [_row("POLICY", "governance/policy.json", "1.0.0", f"`{pinned}`", "**CURRENT**")]
        )
        filled, _problems = _fill(reg, root)
        assert not filled, "--fill 改写了已钉住的哈希格——违反规则②"
        assert pinned in reg.read_text(encoding="utf-8")


def test_fill_preserves_row_padding_so_the_diff_stays_auditable() -> None:
    """--fill 只应改变哈希格，不得重排整行。

    实测发现的缺陷：fill() 原来用 strip 过的 cells 重新拼行，于是每次补登都把该行
    压扁成 |SPEC|`path`|ver|`hash`|，与表内其余行的 `| X | ` 排版不一致
    （真实注册表曾有两行中招，另一条工作线追加的 1.1.0 行也是压扁形态）。
    后果不是美观问题：治理表靠 diff 评审，一次只改一格的补登若把整行重写，
    评审者就无法一眼看出动了哪一格 —— 而"看不出动了哪一格"正是篡改最想要的属性。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", "content")
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
            else:
                assert b == a, f"第 {i} 格在补登时被改写：{b!r} → {a!r}（应只动哈希格）"
        assert after[0].count("| ") == before[0].count("| ") == 6
        assert TOOL.sha256_of(f) in after[0]


def test_rows_sharing_a_spec_id_are_checked_against_their_own_hash_cell() -> None:
    """同一 spec_id 多行时，必须逐行比对自己的哈希格。

    我在判决门里先犯过这个错：用 startswith(f"| {spec} |") 取第一个匹配行，
    结果把历史行的哈希拿去和当前文件比，制造了一条永远无法消除的**假红**。
    工具侧按行解析（cells[3]）本来就是对的 —— 这条断言把它钉住，
    防止将来有人"优化"成按 spec_id 查表。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f = _mkfile(tmp, "governance/policy.json", "current")
        reg, root = _build(
            tmp,
            [
                _row("POLICY", "governance/policy.json", "1.0.0", f"`{_sha(b'previous')}`", "SUPERSEDED"),
                _row("POLICY", "governance/policy.json", "2.0.0", f"`{TOOL.sha256_of(f)}`", "**CURRENT**"),
            ],
        )
        ok, drift, _sk = _check(reg, root)
        assert not drift, f"按 spec_id 而非按行比对会造成假红: {drift}"
        assert len(ok) == 1


# ---------------------------------------------------------------------------
# 5. 真实注册表的集成校验
# ---------------------------------------------------------------------------


def test_the_real_registry_is_green() -> None:
    """仓库里的真实 registry.md 必须全绿：无漂移、无占位。"""
    assert REAL_REGISTRY.is_file(), f"注册表缺失: {REAL_REGISTRY}"
    _lines, rows = TOOL.parse_rows(REAL_REGISTRY.read_text(encoding="utf-8"))
    ok, drift, skipped = TOOL.check(rows)
    assert not drift, "真实注册表存在哈希漂移（规则③）:\n" + "\n".join(drift)
    placeholders = [s for s in skipped if "占位" in s]
    assert not placeholders, f"真实注册表仍有占位未补登: {placeholders}"


def test_the_constitutional_baseline_is_actually_hash_verified() -> None:
    """当前生效的宪基 CONST-v3.0.1 必须真的被哈希校验，不能被位置语义 archived 掉。

    这是边界一的真实注册表版本。宪基若静默退出校验，整套治理就失去了根。
    """
    _lines, rows = TOOL.parse_rows(REAL_REGISTRY.read_text(encoding="utf-8"))
    ok, drift, skipped = TOOL.check(rows)
    assert not drift
    ok_specs = [o.split("]")[0].lstrip("[") for o in ok]
    assert "CONST-v3.0.1" in ok_specs, (
        f"CONST-v3.0.1（唯一生效宪基）未被哈希校验。archived 列表: {skipped}"
    )
    for s in skipped:
        assert "CONST-v3.0.1" not in s, f"宪基被 archived: {s}"


def test_the_real_policy_rows_form_a_legal_version_chain() -> None:
    """POLICY-RUNTIME 必须有完整的版本链，且只有一个活行。

    本轮实际情况：两条工作线各自产出一个"1.1.0"（内容不同、版本号相同）。
    已提交的那条按规则②原样封存，合并后的工件升为 1.2.0 ——
    使任何一个版本号都不同时指代两份不同内容。
    """
    _lines, rows = TOOL.parse_rows(REAL_REGISTRY.read_text(encoding="utf-8"))
    pol = [r for r in rows if r.spec_id == "POLICY-RUNTIME"]
    versions = [r.cells[2].strip("*").strip() for r in pol]
    for v in ("1.0.0", "1.1.0", "1.2.0"):
        assert v in versions, f"POLICY-RUNTIME 缺版本行 {v}（实得 {versions}）——疑似改写了已入库的行"
    # 版本号不得重复：一个号指代两份不同内容，正是注册表要消灭的东西
    assert len(versions) == len(set(versions)), f"POLICY-RUNTIME 版本号重复: {versions}"
    # 只有末行是活行
    _ok, drift, skipped = TOOL.check(rows)
    assert not drift
    archived_pol = [s for s in skipped if "POLICY-RUNTIME" in s]
    assert len(archived_pol) == len(versions) - 1, (
        f"POLICY-RUNTIME 应恰有 {len(versions)-1} 行 archived，实得 {archived_pol}"
    )


def test_the_real_plan_r4b_rows_form_a_legal_version_chain() -> None:
    """PLAN-R4-B 同理：R4 初版封存，R4.1 为活行。"""
    _lines, rows = TOOL.parse_rows(REAL_REGISTRY.read_text(encoding="utf-8"))
    plan = [r for r in rows if r.spec_id == "PLAN-R4-B"]
    versions = [r.cells[2].strip("*").strip() for r in plan]
    assert versions == ["R4", "R4.1"], f"PLAN-R4-B 版本链异常: {versions}"
    assert len(versions) == len(set(versions))


def test_the_tool_documents_the_rule_combination_defect() -> None:
    """工具必须在自己的文档里写明这个死结的成因、两条解法与采纳理由。

    一个"看起来能用"的位置语义，如果不在源码里说明它的两条边界，
    下一个人只会把它当成"让 CI 变绿的方法"来用 —— 然后在表尾追加一行占位，
    让某个已登记文件静默退出校验。
    """
    src = TOOL_PATH.read_text(encoding="utf-8")
    for needle in (
        "规则②给出的唯一合法出路",   # 死结的成因
        "(spec_id, path)",            # 边界一：归组键
        "不受哈希保护",               # 边界二：末行占位判红
        "位置语义",                   # 采纳的方案
        "标记语义",                   # 被舍弃的方案（留下取舍理由）
        "--fill 必须是**提交前的最后一步**",  # 作业顺序陷阱
    ):
        assert needle in src, f"工具源码未记载 {needle!r} —— 机制的边界没有被文档化"


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
