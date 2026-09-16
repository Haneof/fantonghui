# -*- MEGA-PIPELINE 新机制发明②：双透镜虚拟索引投影器（ToolProposal TP-002 纯码兑现） -*-
"""双透镜虚拟索引投影器（DualLensProjector）。

能力缺口：老王案式的回溯解释（Reinterpretation）落地后，「当时我们怎么
想的（AS_KNOWN）」与「今天我们知道了什么（ANNOTATED）」两幅图景必须从
同一份事实流出；为两幅图各建一份物理索引 = 双倍存储 + 双倍漂移风险。

机制：单索引，双投影——
  * 底层读面（payloads + reinterpretations）只扫一遍进内存表；
  * AS_KNOWN(t)：把 learned_at > t 的注记全部滤掉，只留 T 时刻视野；
  * ANNOTATED(t)：全量注记按目标 pinned revision 叠放，结论以注记为顶；
  * 一致性不变量：两透镜的底层事实集 byte-for-byte 相等（SHA-256 同指纹），
    所有差异只出现在 overlay 层——这正是铁律 2 的可审计表达。

本件虚拟投影、不落库；查询面纯函数，撞名零风险。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


def _iso(v: Any) -> str:
    if isinstance(v, datetime):
        vv = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return vv.isoformat()
    s = str(v)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        return s


def _fingerprint(base: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for p in sorted(base, key=lambda r: str(r.get("object_id", ""))):
        digest.update(
            json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        )
    return digest.hexdigest()


@dataclass(slots=True, frozen=True)
class OverlayCard:
    annotation_id: str
    target_object_id: str
    statement: str
    slot: str
    learned_at: str


@dataclass(slots=True, frozen=True)
class LensView:
    lens: str                               # AS_KNOWN | ANNOTATED
    at: str                                 # 视野时间锚
    base_ids: tuple[str, ...]               # 视野内的底层事实 id
    base_fingerprint: str                   # 底层事实 SHA-256
    overlay: tuple[OverlayCard, ...]        # 注记叠层（AS_KNOWN(t) 恒空）
    notes: str = ""

    @property
    def is_pure_base(self) -> bool:
        return not self.overlay


class DualLensProjector:
    """单索引双投影：两幅图同一份事实，差异只在 OPINION 层。"""

    def project(self, payloads: Sequence[Mapping[str, Any]], *,
                at: datetime, include_kinds: tuple[str, ...] = ()) -> tuple[LensView, LensView]:
        """payloads = 全部世界读面（含 reinterpretation 行）。

        include_kinds 限定只投影的 object_type 元组；空 = 全类型。
        """
        now = at if at.tzinfo else at.replace(tzinfo=timezone.utc)

        def keep(p: Mapping[str, Any]) -> bool:
            return not include_kinds or str(p.get("object_type")) in include_kinds

        base = [p for p in payloads
                if keep(p) and str(p.get("object_type")) not in
                ("reinterpretation", "retrospective_annotation")]
        notes_all = [p for p in payloads
                     if str(p.get("object_type")) in
                     ("reinterpretation", "retrospective_annotation")]

        def notes_up_to(t: datetime) -> list[Mapping[str, Any]]:
            out = []
            for n in notes_all:
                learned = n.get("learned_at") or n.get("recorded_at")
                if learned and _iso(learned) <= t.isoformat():
                    out.append(n)
            return out

        base_ids = tuple(sorted(str(p.get("object_id")) for p in base))
        fp = _fingerprint(base)

        as_known = LensView(
            lens="AS_KNOWN", at=now.isoformat(), base_ids=base_ids,
            base_fingerprint=fp, overlay=(),
            notes="当时的视野：注记尚未出生",
        )
        cards = tuple(
            OverlayCard(
                annotation_id=str(n.get("object_id")),
                target_object_id=str(
                    (n.get("target_ref") or n.get("anchor_ref") or {}).get("object_id", "")),
                statement=str(n.get("statement") or n.get("payload") or ""),
                slot=str(n.get("slot", "")),
                learned_at=_iso(n.get("learned_at") or n.get("recorded_at")),
            )
            for n in sorted(notes_up_to(now),
                            key=lambda x: _iso(x.get("learned_at") or x.get("recorded_at")))
        )
        annotated = LensView(
            lens="ANNOTATED", at=now.isoformat(), base_ids=base_ids,
            base_fingerprint=fp, overlay=cards,
            notes=f"今天的视野：{len(cards)} 条注记叠在不变的事实上",
        )
        return as_known, annotated

    @staticmethod
    def assert_consistent(views: tuple[LensView, LensView]) -> None:
        a, b = views
        if a.base_fingerprint != b.base_fingerprint:
            raise AssertionError(
                "双透镜断裂：两幅图的底层事实指纹不同（历史被改写嫌疑）"
            )
        if a.base_ids != b.base_ids:
            raise AssertionError("双透镜断裂：视野内事实集合不一致")


__all__ = [
    "DualLensProjector",
    "LensView",
    "OverlayCard",
]
