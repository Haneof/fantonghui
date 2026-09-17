"""轻量化技能插件容器与 App Manifest 规范 (C14 / §99~104).

贯彻最高宪法第二十八章（App 与外部生态）：
1. 外部 App 仅作为呈现专业界面的轻量容器，完全共享 AIOS 认知底座；
2. 绝对红线：任何 App 严禁私建独立用户画像（allows_isolated_profile 必须为 False）；
3. 跨 App 智识复用与能力沉淀。
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppManifest(BaseModel):
    """外部应用与技能插件清单。"""

    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=1)
    app_name: str = Field(min_length=1)
    version: str = Field(default="1.0.0")
    category: str = Field(default="utility")
    required_dimensions: List[str] = Field(default_factory=list)
    allows_isolated_user_profile: bool = Field(
        default=False,
        description="是否允许独立私建用户画像（宪法第 100 条严禁，必须为 False）"
    )

    @model_validator(mode="after")
    def validate_constitution_no_isolated_profile(self) -> "AppManifest":
        if self.allows_isolated_user_profile:
            raise ValueError(
                f"违宪拦截：App '{self.app_id}' 试图私建独立用户画像，严重违背宪法第 100 条！"
            )
        return self


class AppManifestRegistry:
    """App 清单注册表。"""

    def __init__(self) -> None:
        self._registry: Dict[str, AppManifest] = {}

    def register_app(self, manifest: AppManifest) -> None:
        """注册技能插件。"""
        self._registry[manifest.app_id] = manifest

    def get_app(self, app_id: str) -> Optional[AppManifest]:
        return self._registry.get(app_id)

    def list_installed_apps(self) -> List[AppManifest]:
        return list(self._registry.values())

    def unregister_app(self, app_id: str) -> bool:
        if app_id in self._registry:
            del self._registry[app_id]
            return True
        return False


__all__ = [
    "AppManifest",
    "AppManifestRegistry",
]
