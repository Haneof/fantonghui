"""盲测诊断仪：把八阶段实测数字折算成"瓶颈 / 缺陷 / 铁律证据"。

本模块只做三件事，且只做**测量与折算**，不制造任何数字：

1. :class:`StorageIOProfiler` —— 给真实 ``SQLiteWorldStore`` 加一层透明只读探针，
   按阶段归因每一条 SQL 的**扫描行数**与**语句耗时**（不改变任何语义，
   退出上下文时立刻还原 ``sqlite3.connect``）；
2. :func:`token_ledger` / :func:`bottleneck_diagnosis` —— 把阶段实测事实折算成
   "哪个阶段最烧 Token / 哪条查询最烧 I/O / 哪个认知抽象扭曲最多"；
3. :func:`iron_rule_assertions` —— 五条铁律的机器可复核判据（每条都附实测数字，
   报告里的"PASS"必须能逐条追到具体字段）。

为什么探针要独立于压测台
------------------------
压测台一旦自己统计 I/O，就等于"自己给自己打分"。探针是外部仪器：它挂在
``sqlite3`` 驱动层，压测台代码完全不知道自己被测量，测出来的行数无法被伪造。
"""

from __future__ import annotations

import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Sequence

from aios_core.operations.world_operator import estimate_token_count
from aios_core.simulation.blind_bench_harness import BenchRunResult

__all__ = [
    "StorageIOProfiler",
    "IOAttribution",
    "abstraction_fidelity",
    "bottleneck_diagnosis",
    "iron_rule_assertions",
    "token_ledger",
]

#: SQL 分组签名：动词 + 表名（同一条语句不同参数会被归到同一组）
_SQL_VERB = re.compile(r"^\s*(select|insert|update|delete|create|pragma|begin|commit|savepoint)")
_SQL_TABLE = re.compile(
    r"\b(?:from|into|update|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
)
_WRITE_VERBS = frozenset({"insert", "update", "delete", "create", "drop", "alter"})


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _signature(sql: str) -> str:
    """把 SQL 归结成稳定的分组键：``SELECT object_revisions`` 之类。"""

    flat = _normalize_sql(sql)
    verb_match = _SQL_VERB.match(flat)
    verb = verb_match.group(1).upper() if verb_match else flat.split(" ", 1)[0][:12].upper()
    tables = _SQL_TABLE.findall(flat)
    if not tables:
        return verb
    return f"{verb} {','.join(sorted({table.lower() for table in tables}))}"


# ---------------------------------------------------------------------------
# 存储 I/O 探针
# ---------------------------------------------------------------------------


class _CountingCursor:
    """游标代理：记录"这条 SQL 返回了多少行"（只读统计，不改语义）。"""

    __slots__ = ("_cursor", "_profiler", "_sql", "_started", "_recorded")

    def __init__(self, cursor: sqlite3.Cursor, profiler: "StorageIOProfiler", sql: str) -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_profiler", profiler)
        object.__setattr__(self, "_sql", sql)
        object.__setattr__(self, "_started", time.perf_counter())
        object.__setattr__(self, "_recorded", False)

    # --- 透传 ---------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_cursor"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_cursor"), name, value)

    def __iter__(self) -> Iterator[sqlite3.Row]:
        rows = 0
        for row in object.__getattribute__(self, "_cursor"):
            rows += 1
            yield row
        self._count(rows)

    # --- 读数 ---------------------------------------------------------------

    def _count(self, rows: int) -> None:
        if object.__getattribute__(self, "_recorded"):
            return
        object.__setattr__(self, "_recorded", True)
        profiler = object.__getattribute__(self, "_profiler")
        profiler.record(
            object.__getattribute__(self, "_sql"),
            rows=rows,
            elapsed_ms=(time.perf_counter() - object.__getattribute__(self, "_started"))
            * 1000.0,
        )

    def fetchall(self) -> list[Any]:
        rows = object.__getattribute__(self, "_cursor").fetchall()
        self._count(len(rows))
        return rows

    def fetchone(self) -> Any:
        row = object.__getattribute__(self, "_cursor").fetchone()
        self._count(0 if row is None else 1)
        return row

    def fetchmany(self, size: int = 1) -> list[Any]:
        rows = object.__getattribute__(self, "_cursor").fetchmany(size)
        self._count(len(rows))
        return rows

    @property
    def rowcount(self) -> int:
        value = object.__getattribute__(self, "_cursor").rowcount
        if value and value > 0:
            self._count(value)
        return value


class _CountingConnection:
    """连接代理：把每条语句交给计数器游标（``row_factory`` 等属性全部透传）。"""

    __slots__ = ("_conn", "_profiler")

    def __init__(self, conn: sqlite3.Connection, profiler: "StorageIOProfiler") -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_profiler", profiler)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def __enter__(self) -> "_CountingConnection":
        object.__getattribute__(self, "_conn").__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return object.__getattribute__(self, "_conn").__exit__(*exc)

    def _wrap(self, cursor: sqlite3.Cursor, sql: str) -> _CountingCursor:
        profiler = object.__getattribute__(self, "_profiler")
        proxy = _CountingCursor(cursor, profiler, sql)
        flat = _normalize_sql(sql)
        verb = flat.split(" ", 1)[0].lower() if flat else ""
        if verb in _WRITE_VERBS:
            # 写语句没有 fetch，行数只能靠 rowcount 拿到；这里立刻结算一次，
            # 随后 rowcount 属性再触发也不会重复计数。
            profiler.record(_signature(sql), rows=0, elapsed_ms=0.0)
            rowcount = cursor.rowcount
            if rowcount and rowcount > 0:
                profiler.add_rows(_signature(sql), rowcount)
                object.__setattr__(proxy, "_recorded", True)
        return proxy

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> _CountingCursor:
        cursor = object.__getattribute__(self, "_conn").execute(sql, *args, **kwargs)
        return self._wrap(cursor, sql)

    def executemany(self, sql: str, seq: Iterable[Any]) -> _CountingCursor:
        cursor = object.__getattribute__(self, "_conn").executemany(sql, seq)
        return self._wrap(cursor, sql)

    def executescript(self, sql: str) -> _CountingCursor:
        cursor = object.__getattribute__(self, "_conn").executescript(sql)
        return self._wrap(cursor, sql)

    def cursor(self) -> _CountingCursor:
        return self._wrap(object.__getattribute__(self, "_conn").cursor(), "cursor()")

    def close(self) -> None:
        object.__getattribute__(self, "_conn").close()


@dataclass(frozen=True, slots=True)
class IOHotspot:
    """一条 SQL 签名在整轮盲测里的 I/O 战绩。"""

    signature: str
    statements: int
    rows_scanned: int
    total_ms: float

    def render(self) -> str:
        return (
            f"{self.signature}: {self.statements} 次 / 扫描 {self.rows_scanned} 行 / "
            f"{self.total_ms:.2f} ms"
        )


@dataclass(frozen=True, slots=True)
class IOAttribution:
    """按阶段归因的存储 I/O 账单。"""

    per_stage: Mapping[str, tuple[IOHotspot, ...]]
    overall: tuple[IOHotspot, ...]
    unassigned_statements: int

    def top(self, count: int = 1) -> IOAttribution:
        return IOAttribution(
            per_stage={key: value[:count] for key, value in self.per_stage.items()},
            overall=self.overall[:count],
            unassigned_statements=self.unassigned_statements,
        )

    def hottest(self) -> IOHotspot:
        return self.overall[0]

    def heaviest_stage(self) -> tuple[str, int]:
        totals = {
            stage: sum(hotspot.rows_scanned for hotspot in hotspots)
            for stage, hotspots in self.per_stage.items()
        }
        if not totals:
            return ("(none)", 0)
        stage = max(totals, key=lambda key: totals[key])
        return (stage, totals[stage])

    def render(self, *, top: int = 5) -> str:
        lines: list[str] = []
        for stage, hotspots in self.per_stage.items():
            rows = sum(hotspot.rows_scanned for hotspot in hotspots)
            statements = sum(hotspot.statements for hotspot in hotspots)
            lines.append(f"[{stage}] SQL 语句 {statements} 条 / 扫描 {rows} 行")
            for hotspot in hotspots[:top]:
                lines.append(f"    · {hotspot.render()}")
        if self.unassigned_statements:
            lines.append(f"[启动/收尾] 未归因阶段语句 {self.unassigned_statements} 条")
        return "\n".join(lines)


class StorageIOProfiler:
    """挂在 ``sqlite3.connect`` 上的只读探针（阶段归因靠压测台的墙钟区间）。"""

    def __init__(self) -> None:
        self._statements: list[tuple[float, str, int, float]] = []
        self._pending: dict[str, list[int]] = {}
        self._patched = False

    # ------------------------------------------------------------------

    def record(self, sql: str, *, rows: int, elapsed_ms: float) -> None:
        signature = _signature(sql)
        self._statements.append((time.perf_counter(), signature, rows, elapsed_ms))

    def add_rows(self, signature: str, rows: int) -> None:
        self._statements.append((time.perf_counter(), signature, rows, 0.0))

    # ------------------------------------------------------------------

    @contextmanager
    def install(self) -> Iterator["StorageIOProfiler"]:
        """在上下文内给存储驱动加探针；退出时无条件还原。"""

        import aios_core.storage.sqlite_store as store_module

        original = store_module.sqlite3.connect
        profiler = self

        def counting_connect(*args: Any, **kwargs: Any) -> _CountingConnection:
            return _CountingConnection(original(*args, **kwargs), profiler)

        store_module.sqlite3.connect = counting_connect  # type: ignore[assignment]
        self._patched = True
        try:
            yield self
        finally:
            store_module.sqlite3.connect = original  # type: ignore[assignment]
            self._patched = False

    # ------------------------------------------------------------------

    def attribute(self, marks: Sequence[tuple[str, float, float]]) -> IOAttribution:
        """把每条语句按时间戳归入阶段区间（区间外的归入"启动/收尾"）。"""

        per_stage: dict[str, dict[str, list[float]]] = {}
        unassigned = 0
        for stamp, signature, rows, elapsed_ms in self._statements:
            hit = None
            for stage_id, started, ended in marks:
                if started <= stamp <= ended:
                    hit = stage_id
                    break
            if hit is None:
                unassigned += 1
                continue
            bucket = per_stage.setdefault(hit, {}).setdefault(signature, [0.0, 0.0, 0.0])
            bucket[0] += 1
            bucket[1] += rows
            bucket[2] += elapsed_ms

        def _hotspots(table: Mapping[str, list[float]]) -> tuple[IOHotspot, ...]:
            spots = [
                IOHotspot(
                    signature=signature,
                    statements=int(values[0]),
                    rows_scanned=int(values[1]),
                    total_ms=round(values[2], 4),
                )
                for signature, values in table.items()
            ]
            spots.sort(key=lambda item: (item.rows_scanned, item.statements), reverse=True)
            return tuple(spots)

        overall_table: dict[str, list[float]] = {}
        for stage_table in per_stage.values():
            for signature, values in stage_table.items():
                bucket = overall_table.setdefault(signature, [0.0, 0.0, 0.0])
                bucket[0] += values[0]
                bucket[1] += values[1]
                bucket[2] += values[2]

        return IOAttribution(
            per_stage={stage: _hotspots(table) for stage, table in per_stage.items()},
            overall=_hotspots(overall_table),
            unassigned_statements=unassigned,
        )


# ---------------------------------------------------------------------------
# Token 账单
# ---------------------------------------------------------------------------

#: 每个阶段的 Token 来源字段（报告的每个数字都能追到这几个实测字段）
_TOKEN_SOURCES: Mapping[str, tuple[str, ...]] = {
    "S1": (),
    "S2": ("year_synthesis_tokens",),
    "S3": ("cooccurrence_tokens",),
    "S4": (),
    "S5": (),
    "S6": ("advice_tokens",),
    "S7": ("actions_token_cost",),
    "S8": ("manifest_total_tokens", "conversation_total_tokens"),
}


@dataclass(frozen=True, slots=True)
class TokenLedgerRow:
    stage_id: str
    tokens: int
    sources: tuple[tuple[str, int], ...]

    def render(self) -> str:
        parts = ", ".join(f"{name}={value}" for name, value in self.sources) or "机械阶段：0"
        return f"{self.stage_id}: {self.tokens} Token（{parts}）"


def token_ledger(result: BenchRunResult) -> tuple[TokenLedgerRow, ...]:
    """把每个阶段实测的 Token 消耗折算成账单（数字全部来自阶段事实）。"""

    rows: list[TokenLedgerRow] = []
    for report in result.stages:
        sources: list[tuple[str, int]] = []
        for field_name in _TOKEN_SOURCES.get(report.stage_id, ()):
            value = report.facts.get(field_name, 0)
            sources.append((field_name, int(value or 0)))
        rows.append(
            TokenLedgerRow(
                stage_id=report.stage_id,
                tokens=sum(value for _, value in sources),
                sources=tuple(sources),
            )
        )
    return tuple(rows)


def _token_hotspot(rows: Sequence[TokenLedgerRow]) -> TokenLedgerRow:
    return max(rows, key=lambda row: row.tokens)


def stage_facts(result: BenchRunResult, stage_id: str) -> Mapping[str, Any]:
    """取某阶段的事实字典；该阶段没跑就返回空表（部分运行不伪造数字）。"""

    try:
        return result.stage(stage_id).facts
    except KeyError:
        return {}


def executed_stages(result: BenchRunResult) -> tuple[str, ...]:
    return tuple(report.stage_id for report in result.stages)


# ---------------------------------------------------------------------------
# 认知抽象失真度
# ---------------------------------------------------------------------------


def abstraction_fidelity(result: BenchRunResult) -> tuple[dict[str, Any], ...]:
    """逐个认知抽象层量化"信息丢失 + 可恢复性"。

    失真度口径（每一行都能从阶段实测字段复算）：

    * ``edge_macro``（S1）：误差界占用率 = 最大重建误差 / 该通道 ε。宏观观察一旦落盘，
      原始 50Hz 流按铁律 4 不得保留，因此这是**唯一不可逆**的抽象层，
      必须靠"误差有界"来兜底；
    * ``time_pyramid``（S2）：文本保留比 = 1 - 年总结 Token / 年原始 Token。
      文字被极度浓缩，但证据链断链率为 0 —— 损失只发生在"叙事"上，不发生在"事实"上；
    * ``event_synthesis``（S3）：失真度 = 1 - 同窗覆盖率（窗内样本被多少进了合成事件）；
    * ``dimension_curve``（S4）：按天聚合把日内时间分辨率抹平，失真度 =
      1 - 曲线点数 / 事件数（事件比曲线点少时无损，因为曲线比数据更粗的反面更细）。
    """

    s1 = stage_facts(result, "S1")
    s2 = stage_facts(result, "S2")
    s3 = stage_facts(result, "S3")
    s4 = stage_facts(result, "S4")

    imu_error = float(s1.get("imu_max_reconstruction_error", 0.0))
    heart_error = float(s1.get("heart_max_reconstruction_error", 0.0))
    imu_eps = float(s1.get("edge_policy_imu_epsilon", 1.0)) or 1.0
    heart_eps = float(s1.get("edge_policy_heart_epsilon", 1.0)) or 1.0
    edge_distortion = max(imu_error / imu_eps, heart_error / heart_eps)

    keep_ratio = float(s2.get("summary_text_keep_ratio", 1.0))
    pyramid_distortion = max(0.0, 1.0 - keep_ratio)

    coverage = float(s3.get("synthesis_coverage_ratio", 0.0))
    synthesis_distortion = max(0.0, 1.0 - coverage)

    days = max(1, int(s4.get("curve_days", 1)))
    events = max(1, int(s2.get("year_source_events", 1)))
    curve_distortion = max(0.0, 1.0 - days / events)

    rows: list[dict[str, Any]] = []
    if s1:
        rows.append({
            "abstraction": "端侧宏观化（50Hz → 宏观观察）",
            "stage": "S1",
            "distortion": round(edge_distortion, 6),
            "recoverable": "不可逆（原始高频流按铁律 4 不落盘）",
            "basis": (
                f"IMU 误差 {imu_error:.4f}/{imu_eps:.1f}g，"
                f"心率误差 {heart_error:.4f}/{heart_eps:.1f}bpm → 误差界占用率 "
                f"{edge_distortion:.4%}"
            ),
            "compensation": "误差有界（ε 硬约束）+ 冲击点以原值单独成 Observation，波形不被平均抹平",
        })
    if s2:
        rows.append({
            "abstraction": "时间金字塔文本抽象（年总结）",
            "stage": "S2",
            "distortion": round(pyramid_distortion, 8),
            "recoverable": (
                f"事实可 100% 下钻恢复（断链率 {float(s2.get('evidence_chain_break_rate', 1.0)):.1%}），"
                "叙事文字本身不可恢复"
            ),
            "basis": (
                f"年总结 {int(s2.get('year_synthesis_tokens', 0))} Token / 年原始 "
                f"{int(s2.get('year_source_tokens', 0))} Token，保留比 {keep_ratio:.6f}"
            ),
            "compensation": "证据指针（evidence_ids）与原始原话逐字节可比，抽象只发生在阅读面",
        })
    if s3:
        rows.append({
            "abstraction": "跨维事件合成（同窗样本 → 1 个 EventAnchor）",
            "stage": "S3",
            "distortion": round(synthesis_distortion, 6),
            "recoverable": "可逆（来源样本修订号全部钉死，可反向解引用）",
            "basis": (
                f"共振窗覆盖 {int(s3.get('aligned_samples', 0))}/"
                f"{int(s3.get('window_samples_available', 0))} 个样本，覆盖率 {coverage:.4f}"
            ),
            "compensation": "合成事件携带维度清单与证据集，任何结论都能回到采样点",
        })
    if s4:
        rows.append({
            "abstraction": "维度曲线按天聚合",
            "stage": "S4",
            "distortion": round(curve_distortion, 6),
            "recoverable": "可逆（曲线是附加物化视图，原始 Observation 一字未动）",
            "basis": (
                f"{events} 条年度事件 vs {days} 个曲线点；"
                "曲线只保留日内聚合值，日内时刻只能在原始 Observation 上看到"
            ),
            "compensation": "曲线仅用于趋势/拐点机械判定；要时刻精度必须回落到原始事实",
        })
    return tuple(rows)


# ---------------------------------------------------------------------------
# 五条铁律的机器判据
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IronRuleAssertion:
    """一条铁律的现场判据：逐项列出「实测值 / 要求 / 是否通过」。"""

    rule: str
    checks: tuple[tuple[str, Any, str, bool], ...]

    @property
    def passed(self) -> bool:
        return all(check[3] for check in self.checks)

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        details = "; ".join(
            f"{name}={actual}（要求 {requirement}）" for name, actual, requirement, _ in self.checks
        )
        return f"[{status}] {self.rule} —— {details}"


def _check(actual: Any, requirement: str, predicate: Any) -> tuple[Any, str, bool]:
    ok = bool(predicate(actual)) if callable(predicate) else bool(actual == predicate)
    return (actual, requirement, ok)


def iron_rule_assertions(result: BenchRunResult) -> tuple[IronRuleAssertion, ...]:
    """五条铁律的现场判据（每条都引用阶段实测字段，可被独立复算）。

    所需阶段没跑（例如 `--stage S1` 的部分运行）时，**不放宽、不伪造**：
    该条铁律直接不出结论，宁可少一条 PASS 也不给假 PASS。
    """

    s1 = stage_facts(result, "S1")
    s4 = stage_facts(result, "S4")
    s5 = stage_facts(result, "S5")
    s6 = stage_facts(result, "S6")
    s8 = stage_facts(result, "S8")
    ran = set(executed_stages(result))
    sentences = [
        int(item) for item in str(s8.get("conversation_sentence_counts", "")).split(",") if item
    ] or [0]

    assertions: list[IronRuleAssertion] = []

    if {"S6", "S8"} <= ran:  # 需要 S6 与 S8 同时在场
        assertions.append(
            IronRuleAssertion(
                rule="铁律1 输出质量绝对第一（≤3 句 / 有证据 / 0 说教）",
                checks=(
                    ("S6 建议句数", s6["advice_sentence_count"], "≤ 3",
                     _check(s6["advice_sentence_count"], "≤ 3", lambda value: value <= 3)[2]),
                    ("S6 建议接地复核", s6["advice_grounding_verified"], "True",
                     _check(s6["advice_grounding_verified"], "True", True)[2]),
                    ("S6 证据指针数", s6["advice_evidence_pointers"], "≥ 2",
                     _check(s6["advice_evidence_pointers"], "≥ 2", lambda value: value >= 2)[2]),
                    ("S8 单轮句数上限", max(sentences), "≤ 3",
                     _check(max(sentences), "≤ 3", lambda value: value <= 3)[2]),
                    ("S8 单轮句数下限", min(sentences), "≥ 1",
                     _check(min(sentences), "≥ 1", lambda value: value >= 1)[2]),
                    ("S8 说教命中", s8["conversation_preach_hits"], "== 0",
                     _check(s8["conversation_preach_hits"], "== 0", 0)[2]),
                    ("S8 单轮 Token 峰值", s8["conversation_max_round_tokens"], "≤ 1500",
                     _check(s8["conversation_max_round_tokens"], "≤ 1500",
                            lambda value: value <= 1500)[2]),
                ),
            )
        )

    if "S5" in ran:
        checks = (
            ("真值表前后一致", s5["truth_digest_unchanged"], "True", s5["truth_digest_unchanged"] is True),
            ("历史 payload 字节不变", s5["target_payload_bytes_unchanged"], "True",
             s5["target_payload_bytes_unchanged"] is True),
            ("历史未墓碑", s5["target_tombstoned"], "False", s5["target_tombstoned"] is False),
            ("观测条数前后相等", s5["observations_after"],
             f"== {s5['observations_before']}", s5["observations_after"] == s5["observations_before"]),
            ("隔离路径大模型调用", s5["isolation_llm_calls"], "== 0", s5["isolation_llm_calls"] == 0),
            ("隔离遍历深度", s5["traversal_depth_reached"], "≤ 1",
             s5["traversal_depth_reached"] <= 1),
            ("多跳下游零触碰", s5["multi_hop_untouched"], "True", s5["multi_hop_untouched"] is True),
        )
        assertions.append(
            IronRuleAssertion(rule="铁律2 历史绝不篡改，只在今天打标签（单跳隔离）", checks=checks)
        )

    if "S8" in ran:
        checks = (
            ("P0 首行动作", s8["p0_first_action"], "hardware_pulse",
             s8["p0_first_action"] == "hardware_pulse"),
            ("P0 大模型介入", s8["p0_llm_calls"], ">= 1", s8["p0_llm_calls"] >= 1),
            ("P0 P99 时延", s8["p0_p99_ms"], "≤ 50ms", s8["p0_p99_ms"] <= 50.0),
            ("P0 最大时延", s8["p0_max_ms"], "≤ 50ms", s8["p0_max_ms"] <= 50.0),
            ("P0 审计回执", s8["p0_audit_receipts"], "== 50", s8["p0_audit_receipts"] == 50),
        )
        assertions.append(
            IronRuleAssertion(
                rule="铁律3 紧急触发大模型直接研判中枢（首动作=硬件脉冲 / 大模型现场研判 / ≤50ms）", checks=checks
            )
        )

    if "S1" in ran:
        checks = (
            ("复盘后噪声可见数", s1["noise_visible_after_review"], "== 0",
             s1["noise_visible_after_review"] == 0),
            ("核心原话留存", s1["core_texts_retained_after_review"],
             f"== {s1['core_texts_total']}",
             s1["core_texts_retained_after_review"] == s1["core_texts_total"]),
            ("原始图像字节留存", s1["raw_image_bytes_retained"], "== 0",
             s1["raw_image_bytes_retained"] == 0),
            ("50Hz 原始行直写", s1["raw_imu_rows_persisted"], "== 0",
             s1["raw_imu_rows_persisted"] == 0),
            ("删除审计链自检", s1["purge_ledger_chain_ok"], "True",
             s1["purge_ledger_chain_ok"] is True),
            ("噪声边缘拦截数", s1["noise_dropped_at_edge"], "> 0", s1["noise_dropped_at_edge"] > 0),
        )
        assertions.append(
            IronRuleAssertion(
                rule="铁律4 大模型自主判断删除（噪声物理删、证据 100% 留）", checks=checks
            )
        )

    if "S4" in ran:
        checks = (
            ("门限一机械拒绝不成熟模式", s4["immature_pattern_rejected"], "True",
             s4["immature_pattern_rejected"] is True),
            ("同日第二次自省被拦", s4["same_day_second_reflection_blocked"], "True",
             s4["same_day_second_reflection_blocked"] is True),
            ("弱预测候选结局", s4["trial_weak_prediction_outcome"], "expired",
             s4["trial_weak_prediction_outcome"] == "expired"),
            ("断档候选结局", s4["trial_patchy_outcome"], "expired",
             s4["trial_patchy_outcome"] == "expired"),
            ("熔断大模型调用", s4["circuit_break_llm_calls"], "== 0",
             s4["circuit_break_llm_calls"] == 0),
            ("硬件维度导数被拒", s4["hardware_dimension_rejected"], "True",
             s4["hardware_dimension_rejected"] is True),
        )
        assertions.append(
            IronRuleAssertion(rule="铁律5 自问自答与新维度衍生有严苛门槛", checks=checks)
        )

    return tuple(assertions)


# ---------------------------------------------------------------------------
# 瓶颈诊断
# ---------------------------------------------------------------------------

#: 缺陷目录：条目只在**被实测数字命中**时才进入诊断书（不命中就不写）
_DEFECT_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "D1",
        "severity": "高",
        "title": "端侧宏观化的重建误差贴满 ε 上限（误差界被用尽，没有安全余量）",
        "stage": "S1",
        "mechanism": (
            "自适应窗口在平稳段持续增长直到曲率预算耗尽，最大重建误差逼近 ε 而不是远小于 ε；"
            "由于原始 50Hz 流按铁律 4 不落盘，这一层的损失不可逆，误差界就是唯一兜底"
        ),
        "fix": (
            "窗口增长前预留误差裕度（例如只用 0.7ε 判定可合并），"
            "或对疑似生理突变段把 ε 收紧一档，用少量存储换可证明的安全边际"
        ),
    },
    {
        "id": "D2",
        "severity": "中",
        "title": "年总结文本保留比极低（叙事层几乎是空壳）",
        "stage": "S2",
        "mechanism": (
            "物化年总结只保留 synthesis_text 的一段高度浓缩叙事，"
            "真正的人生故事全在 evidence_ids 指针里；一旦上层没有下钻能力，"
            "阅读体验就退化成'只有索引没有内容'"
        ),
        "fix": (
            "为年总结增加'主题句 + 3~5 个关键片段'的分层叙事（仍 ≤ 预算），"
            "并把片段指针与 evidence_ids 一起物化"
        ),
    },
    {
        "id": "D3",
        "severity": "中",
        "title": "共振窗内可用样本过少：维度够、丰度不够，合成事件的置信底座偏薄",
        "stage": "S3",
        "mechanism": (
            "共振只要求同窗 ≥3 个维度，不要求每维度有多少样本；实际世界里"
            "「三域各命中一条」就能合成事件，稀疏时段合成出的事件与密集时段的"
            "事件共享同一置信口径，噪声下容易过判"
        ),
        "fix": (
            "把「同窗样本丰度」写进合成事件的置信度（样本少 → 置信度下压、"
            "先登记为候选），并把 2 维度的弱共振也纳入候选池，"
            "等第三维度到齐再升级为 ACTIVE"
        ),
    },
    {
        "id": "D4",
        "severity": "低",
        "title": "维度曲线按天聚合，日内时间分辨率在曲线上不可恢复",
        "stage": "S4",
        "mechanism": (
            "日粒度曲线把同一天的多次异常合并成一个计数点，"
            "拐点检测因此只能定位到'哪一天'；时刻精度必须回落到原始 Observation 才可见"
        ),
        "fix": (
            "对高价值拐点自动回落到小时粒度重算（局部细化），"
            "曲线主体仍保持天粒度以控制点数"
        ),
    },
    {
        "id": "D5",
        "severity": "高",
        "title": "单跳隔离把注解自身计入直接消费者，口径需要显式区分",
        "stage": "S5",
        "mechanism": (
            "新增注解既是'今天的新认知'又是被标记 STALE 的对象，"
            "若不区分，审计口径会把'1 条新注解 + 3 个直接下游'说成'4 个直接消费者'"
        ),
        "fix": (
            "在 InvalidationReport 中把 annotation_id 与历史下游分成两个字段，"
            "报告分别引用（已在本轮盲测中以 annotation_counts_as_single_hop 显式区分）"
        ),
    },
    {
        "id": "D6",
        "severity": "中",
        "title": "证据召回以 Observation 为主，高阶对象（Claim/EventAnchor）未充分参与建议",
        "stage": "S6",
        "mechanism": (
            "建议的证据类型统计只出现 observation：检索层对 Claim/EventAnchor 的投影"
            "尚未与 Observation 同权重，导致'已经推理过的结论'在建议里没有被复用"
        ),
        "fix": (
            "把 Claim/EventAnchor 纳入同一召回面，并在建议里标注证据层级，"
            "让'事实 → 结论 → 建议'的链条显式可见"
        ),
    },
    {
        "id": "D7",
        "severity": "低",
        "title": "沟通风格推荐必须与回避清单互斥，否则会'矮子里拔将军'踩雷",
        "stage": "S7",
        "mechanism": (
            "旧实现只在'得分最高'里挑风格，被用户抵触过的风格若恰好是唯一有样本的风格，"
            "仍会被推荐；已改为回避优先过滤（无合格风格时回落基础人设）"
        ),
        "fix": "已在 experience_tracker.get_effective_style 落地：先剔除回避清单，再按接受率择优",
    },
    {
        "id": "D8",
        "severity": "中",
        "title": "驾驶舱单轮 Token 峰值仍显著高于建议值，说明看板装载仍未完全分片",
        "stage": "S8",
        "mechanism": (
            "全景看板一次性装载四透镜亮点，单轮峰值虽然远低于 1500 预算，"
            "但相对'1~3 句'的输出仍有大量结构性开销"
        ),
        "fix": (
            "按透镜懒装载（只装本轮需要的透镜），把被折叠条目的计数（elided）"
            "作为'可继续追问'的钩子而不是全量装载"
        ),
    },
)

#: 每个缺陷的命中判据文字（写进诊断书，让读者知道它是被哪条实测数字触发的）
_DEFECT_TRIGGERS: Mapping[str, str] = {
    "D1": "误差界占用率 > 0.9",
    "D2": "年总结文本保留比 < 0.05",
    "D3": "同窗覆盖率 < 1.0 或同窗样本 < 6",
    "D4": "曲线量化失真度 > 0.05",
    "D5": "直接消费者 ≥ 3 且新注解被计入其中",
    "D6": "建议证据类型集合仅含 observation",
    "D7": "推荐风格出现在回避清单里",
    "D8": "单轮 Token 峰值 / 预算 > 0.2",
}


def _defect_hits(result: BenchRunResult) -> dict[str, tuple[bool, str]]:
    s1 = stage_facts(result, "S1")
    s2 = stage_facts(result, "S2")
    s3 = stage_facts(result, "S3")
    s4 = stage_facts(result, "S4")
    s5 = stage_facts(result, "S5")
    s6 = stage_facts(result, "S6")
    s7 = stage_facts(result, "S7")
    s8 = stage_facts(result, "S8")

    bound_use = max(
        float(s1.get("imu_error_bound_utilization", 0.0)),
        float(s1.get("heart_error_bound_utilization", 0.0)),
    )
    max_error = max(
        float(s1.get("imu_max_reconstruction_error", 0.0)),
        float(s1.get("heart_max_reconstruction_error", 0.0)),
    )
    keep_ratio = float(s2.get("summary_text_keep_ratio", 1.0))
    coverage = float(s3.get("synthesis_coverage_ratio", 0.0))
    days = max(1, int(s4.get("curve_days", 1)))
    events = max(1, int(s2.get("year_source_events", 1)))
    curve_ratio = max(0.0, 1.0 - days / events)
    consumers = int(s5.get("direct_consumers", 0))
    annotation_included = bool(s5.get("annotation_counts_as_single_hop", False))
    evidence_types = str(s6.get("advice_evidence_types", ""))
    avoid = str(s7.get("case_avoid_styles", ""))
    recommended = str(s7.get("case_predicted_style", ""))
    peak_ratio = float(s8.get("conversation_max_round_tokens", 0)) / max(
        1.0, float(s8.get("conversation_single_shot_budget", 1500))
    )

    if not (s1 or s2 or s3 or s4 or s5 or s6 or s7 or s8):
        return {key: (False, "(该阶段未执行)") for key in _DEFECT_TRIGGERS}

    return {
        "D1": (
            bound_use > 0.9,
            f"最大重建误差 {max_error:.4f}，误差界占用率 {bound_use:.4%}"
            f"（IMU ε={float(s1.get('edge_policy_imu_epsilon', 0.0)):.1f}g，"
            f"心率 ε={float(s1.get('edge_policy_heart_epsilon', 0.0)):.1f}bpm）",
        ),
        "D2": (bool(s2) and keep_ratio < 0.05, f"年总结/年原文 Token 保留比 {keep_ratio:.6f}"),
        "D3": (
            bool(s3) and (coverage < 1.0 or int(s3.get("window_samples_available", 0)) < 6),
            f"同窗样本覆盖率 {coverage:.4f}，同窗可用样本仅 "
            f"{int(s3.get('window_samples_available', 0))} 条（共振丰度低）",
        ),
        "D4": (
            bool(s2 and s4) and curve_ratio > 0.05,
            f"{events} 条年度事件 vs {days} 个曲线点 → 日内时刻不可在曲线上恢复"
            f"（量化失真度 {curve_ratio:.4f}）",
        ),
        "D5": (
            bool(s5) and annotation_included and consumers >= 3,
            f"直接消费者 {consumers} 条（其中含新注解自身：{annotation_included}）",
        ),
        "D6": (
            bool(s6) and evidence_types == "observation",
            f"建议证据类型集合 = {evidence_types or '(空)'}",
        ),
        "D7": (
            bool(s7) and bool(avoid) and recommended in avoid.split(","),
            f"回避清单 {avoid or '(空)'} 与推荐风格 {recommended} 是否冲突",
        ),
        "D8": (bool(s8) and peak_ratio > 0.2, f"单轮峰值 {int(s8.get('conversation_max_round_tokens', 0))} Token / 预算 {int(s8.get('conversation_single_shot_budget', 1500))} Token = {peak_ratio:.2%}"),
    }


def bottleneck_diagnosis(
    result: BenchRunResult,
    attribution: IOAttribution,
    *,
    microbench: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把实测数字折算成四张诊断结论 + 一份缺陷清单。"""

    ledger = token_ledger(result)
    token_hotspot = _token_hotspot(ledger)
    total_tokens = sum(row.tokens for row in ledger)
    hot_stage, hot_rows = attribution.heaviest_stage()
    hottest_query = attribution.hottest() if attribution.overall else None
    fidelity = abstraction_fidelity(result)
    worst = (
        max(fidelity, key=lambda row: float(row["distortion"]))
        if fidelity
        else {
            "abstraction": "(未执行相应阶段)",
            "stage": "(none)",
            "distortion": 0.0,
            "recoverable": "(unknown)",
            "basis": "(none)",
            "compensation": "(none)",
        }
    )
    hits = _defect_hits(result)
    defects = [
        {**entry, "measured": hits[entry["id"]][1]}
        for entry in _DEFECT_CATALOG
        if hits[entry["id"]][0]
    ]

    stage_seconds = {
        report.stage_id: round(
            sum(
                mark[2] - mark[1]
                for mark in result.stage_marks
                if mark[0] == report.stage_id
            ),
            4,
        )
        for report in result.stages
    }
    slowest = max(stage_seconds.items(), key=lambda item: item[1]) if stage_seconds else ("(none)", 0.0)

    return {
        "token_ledger": ledger,
        "token_total": total_tokens,
        "token_hotspot": token_hotspot,
        "io_attribution": attribution,
        "io_hotspot": hottest_query,
        "io_hot_stage": (hot_stage, hot_rows),
        "abstraction_fidelity": fidelity,
        "worst_abstraction": worst,
        "defects": defects,
        "stage_seconds": stage_seconds,
        "slowest_stage": slowest,
        "missing_stages": [
            stage
            for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
            if stage not in executed_stages(result)
        ],
        "microbench": dict(microbench or {}),
    }


def render_bottleneck_summary(diagnosis: Mapping[str, Any]) -> str:
    """诊断结论的一屏摘要（报告与 PR 描述共用同一份数字）。"""

    hotspot = diagnosis["token_hotspot"]
    io_hotspot = diagnosis["io_hotspot"]
    worst = diagnosis["worst_abstraction"]
    lines = [
        f"Token 热点：{hotspot.stage_id} 烧掉 {hotspot.tokens} Token"
        f"（全轮 {diagnosis['token_total']} Token）",
        "I/O 热点：" + (io_hotspot.render() if io_hotspot is not None else "(无采样)"),
        f"失真最大抽象：{worst['abstraction']} —— 失真度 {worst['distortion']:.6f}",
        f"最慢阶段：{diagnosis['slowest_stage'][0]} —— {diagnosis['slowest_stage'][1]:.3f} s",
        f"命中缺陷：{len(diagnosis['defects'])} 项（{', '.join(item['id'] for item in diagnosis['defects']) or '无'}）",
    ]
    return "\n".join(lines)
