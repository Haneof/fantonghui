"""EventProvenance —— 中立的事件 id 登记册(mint authority)。它不属于任何 Runtime。

为什么需要它(09 禁止事项第 5 条): Event Runtime 必须能证明"这个 event id 是合法感知
路径铸出来的",否则任何人手搓一个 dict 就能往事件库里灌事实。但 Event Runtime 一旦
import Perception Runtime,两个 Runtime 就互相咬住(02 §0/§1 要求它们各自独立,只由调用方
串联),于是"证明"这件事需要一个双方都依赖的中立载体:

    Perception --- mint() ---> EventProvenance <--- is_minted() --- Event Runtime

方向是"两个 Runtime 各自依赖中立登记册",Runtime 之间零依赖、零调用。

刻意保持最小: 一个 set + 一个计数器。它不是 Runtime —— 没有契约编号、不进 core/、
不做任何业务判断、不读写世界状态、不参与 Relevance/Attention/Wake。位置选 tools/,
是因为 `tools/mini_jsonschema.py` 已经是"两个 Runtime 共用中立设施"的既有先例;
若日后架构层决定给它一个正式目录(例如 core/provenance/ 并写进 docs/06),
需要的是 Contract 裁决,不是本次 FIX 的顺手重构。
"""
from __future__ import annotations

import itertools


class EventProvenance:
    """事件 id 的铸造与登记。

    `mint()` 是权力: 只有被信任的生产方(感知路径)持有登记册实例时才该调用它。
    `is_minted()` 是证明: 纯查询,不改状态,也没有任何"补登记"的入口 ——
    伪造者拿不到 mint(),就没有办法把自己编的 id 塞进登记册。
    """

    def __init__(self, prefix: str = "evt", width: int = 3) -> None:
        self.prefix = prefix
        self.width = width
        self._seq = itertools.count(1)
        self._minted: set[str] = set()

    def mint(self) -> str:
        """铸造一个新 id 并立即登记。确定性: 同一登记册、同一顺序 => 同一批 id。"""
        eid = f"{self.prefix}_{next(self._seq):0{self.width}d}"
        self._minted.add(eid)
        return eid

    def is_minted(self, event_id: object) -> bool:
        return isinstance(event_id, str) and event_id in self._minted

    def reset(self) -> None:
        """测试/回放用: 清空计数与登记,使同一条时间线得到同一批 id。"""
        self._seq = itertools.count(1)
        self._minted.clear()

    def snapshot(self) -> tuple[str, ...]:
        return tuple(sorted(self._minted))

    def __len__(self) -> int:
        return len(self._minted)


#: 进程级默认登记册: 未显式注入时,Perception 与 Event Runtime 共享这一份。
#: 生产装配应显式注入(同一个实例传给双方),默认值只是让 Simulator/测试保持可跑。
default_provenance = EventProvenance()
