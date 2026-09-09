"""MockSimulatorAdapter —— Sprint 1 Task 2 的 Simulator 侧 raw signal 源。

它只负责"按时间线吐出原始信号",不做语义化(语义化在 Perception Runtime,02 §0)。
09 禁止事项第 5 条: 不得用 Simulator 绕过 Perception Runtime —— 因此本文件里没有任何
EventRuntime 调用,player 必须把这里产出的 raw signal 交给 PerceptionRuntime。
"""
from __future__ import annotations

from pathlib import Path


class MockSimulatorAdapter:
    """读取 "HH:MM 文本" 形式的时间线,产出 raw signal。"""

    def __init__(self, scenario_path: str | Path, channel: str = "simulator") -> None:
        self.path = Path(scenario_path)
        self.channel = channel

    def lines(self) -> list[str]:
        return [ln.strip() for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def read(self) -> list[dict]:
        signals: list[dict] = []
        for ln in self.lines():
            at, _, text = ln.partition(" ")
            signals.append({"at": at.strip(), "text": text.strip(), "channel": self.channel, "payload": ln})
        return signals

    def repeat_last(self, n: int) -> list[dict]:
        """制造连续重复噪音,用来验证 Event Runtime 的去重(Sprint 1 Task 4)。"""
        return [self.read()[-1] for _ in range(n)] if n > 0 else []
