"""MockSimulatorAdapter —— Sprint 1 Task 2 的 Simulator 侧 raw signal 源。

它只负责"按时间线吐出原始信号",不做语义化(语义化在 Perception Runtime,02 §0)。
09 禁止事项第 5 条: 不得用 Simulator 绕过 Perception Runtime —— 因此本文件里没有任何
EventRuntime / WorldRuntime 调用,player 必须把这里产出的 raw signal 交给 PerceptionRuntime。

支持两种场景文件:
    *.txt   每行 "HH:MM 文本"          -> modality=text(09 的谈判时间线原文,逐字不改)
    *.jsonl 每行一个完整 Raw Signal    -> 用来覆盖 audio_transcript / sensor / vision / calendar
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEXT_FILE_SUFFIXES = (".txt", ".text")


class MockSimulatorAdapter:
    """把场景文件读成 Raw Signal 列表(带 signal_id,便于 raw_ref 回溯)。"""

    def __init__(self, scenario_path: str | Path, source: str = "simulator") -> None:
        self.path = Path(scenario_path)
        self.source = source

    def lines(self) -> list[str]:
        return [ln.strip() for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def read(self) -> list[dict[str, Any]]:
        if self.path.suffix.lower() in TEXT_FILE_SUFFIXES:
            return list(self._from_timeline())
        if self.path.suffix.lower() in (".jsonl", ".ndjson"):
            return list(self._from_jsonl())
        raise ValueError(f"MockSimulatorAdapter 不支持的场景文件类型: {self.path.suffix!r}")

    def _from_timeline(self) -> list[dict[str, Any]]:
        stem = self.path.stem
        signals: list[dict[str, Any]] = []
        for idx, ln in enumerate(self.lines(), start=1):
            at, _, text = ln.partition(" ")
            signals.append({
                "signal_id": f"sim-{stem}-{idx:03d}",
                "timestamp": at.strip(),
                "source": self.source,
                "modality": "text",
                "payload": {"text": text.strip()},
            })
        return signals

    def _from_jsonl(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for idx, ln in enumerate(self.lines(), start=1):
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError as exc:  # 场景文件写坏了要立刻说清楚,不静默跳过
                raise ValueError(f"{self.path.name} 第 {idx} 行不是合法 JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{self.path.name} 第 {idx} 行必须是 JSON 对象")
            obj.setdefault("source", self.source)
            obj.setdefault("signal_id", f"sim-{self.path.stem}-{idx:03d}")
            signals.append(obj)
        return signals

    def repeat_last(self, n: int) -> list[dict[str, Any]]:
        """制造连续重复噪音,用来验证 Event Runtime 的去重(Sprint 1 Task 4)。

        重复噪音必须换 signal_id:否则它会在 Perception 的 signal_id 去重处就被拒,
        那就测不到 Task 4 的"内容级去重"了。
        """
        if n <= 0:
            return []
        last = self.read()[-1]
        return [{**last, "signal_id": f"{last['signal_id']}-noise{i:02d}"} for i in range(1, n + 1)]
