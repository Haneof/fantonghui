"""23cm×5~6cm 柔性屏环形长条画布布局约束模拟器 (CurvedCanvasLayoutSimulator).

贯彻宪法第五编第一百零四条之一（手环呈现与三层 UI 结构）与第三编第十四条之一（1~3句老友短表达）：
1. 物理屏体规格：230mm (长) × 55mm (宽) 环形贴腕柔性屏；
2. 显示排版基准：
   - 超宽带状画布（Ribbon Canvas），视口水平滑动展开；
   - 强行约束：日常单屏交互文本严禁超过 60 个汉字（1~3 句老友语调，防长篇说教刷屏）；
3. 三大微视口形态：
   - SITUATION_CAPSULE（态势胶囊）：生理稳态、心率色环、未读胶囊；
   - AI_BUBBLE（老友气泡）：极简口语关怀与决策洞见；
   - EMERGENCY_BANNER（P0 紧急突发红条）：最高优先级穿透，双色高对比告警。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional

UTC = timezone.utc


class ViewportCardType(StrEnum):
    """微卡片形态枚举。"""

    SITUATION_CAPSULE = "situation_capsule"   # 态势胶囊（生理健康、状态指示）
    AI_BUBBLE = "ai_bubble"                   # 老友气泡（1~3句极简交流）
    EMERGENCY_BANNER = "emergency_banner"     # P0 紧急报警红色横幅
    SKILL_PLUGIN_CARD = "skill_plugin_card"   # 二层轻量技能卡片


@dataclass
class RenderedCardView:
    """渲染后的手环微卡片视图。"""

    card_id: str
    card_type: ViewportCardType
    text_content: str
    character_count: int
    is_overflow: bool
    priority_level: int
    visual_theme: str
    rendered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CurvedCanvasLayoutSimulator:
    """23cm 环形长条屏布局约束模拟器。"""

    SCREEN_LENGTH_MM: int = 230
    SCREEN_WIDTH_MM: int = 55
    MAX_CHAR_PER_VIEWPORT: int = 60  # 铁律：日常单屏 <= 60 汉字

    def __init__(self) -> None:
        self.active_rendered_cards: List[RenderedCardView] = []

    def render_card(
        self,
        card_type: ViewportCardType,
        text: str,
        *,
        card_id: Optional[str] = None,
        priority: int = 1,
        force_allow_overflow: bool = False,
    ) -> RenderedCardView:
        """渲染微卡片并执行严格字符与排版溢出检查。"""
        char_len = len(text.strip())
        is_overflow = False

        # P0 紧急横幅豁免字符长度限制（生命第一），其余卡片严格受限
        if card_type == ViewportCardType.EMERGENCY_BANNER or force_allow_overflow:
            is_overflow = False
        elif char_len > self.MAX_CHAR_PER_VIEWPORT:
            is_overflow = True

        visual_theme = "DARK_SLATE"
        if card_type == ViewportCardType.EMERGENCY_BANNER:
            visual_theme = "CRITICAL_RED_ALERT"
        elif card_type == ViewportCardType.AI_BUBBLE:
            visual_theme = "COMPANION_CYAN_BUBBLE"
        elif card_type == ViewportCardType.SITUATION_CAPSULE:
            visual_theme = "HEALTH_AMBER_CAPSULE"

        view = RenderedCardView(
            card_id=card_id or f"card_{int(datetime.now().timestamp()*1000)}",
            card_type=card_type,
            text_content=text.strip(),
            character_count=char_len,
            is_overflow=is_overflow,
            priority_level=priority,
            visual_theme=visual_theme,
        )
        self.active_rendered_cards.append(view)
        return view

    def get_highest_priority_card(self) -> Optional[RenderedCardView]:
        """获取当前画布顶层最高优先级微卡片（同优先级取最新）。"""
        if not self.active_rendered_cards:
            return None
        return max(self.active_rendered_cards, key=lambda c: (c.priority_level, c.rendered_at))

    def clear(self) -> None:
        self.active_rendered_cards.clear()


__all__ = [
    "CurvedCanvasLayoutSimulator",
    "RenderedCardView",
    "ViewportCardType",
]
