# 工单 #1：M1-001R 端侧多模态轻量摄入与声纹180天淘汰引擎

- **派发代号**：`TASK-M1-001R`
- **指派战队**：Agent-01 战队（多模型并行开发）
- **所属模块**：C01 多模态接入与边缘清洗层
- **前置依赖**：`M0-001`、`M0-023`
- **目标分支**：`arena/agent-01-m1-001r`

## 1. 任务背景与核心目标
手环穿戴场景下，摄像头可能产生大量晃动、模糊抓拍与环境杂音。旧方案把原始图片全部落库，一天产生 430 万条记录与几十兆图片把端侧撑死。
必须落实**宪法第 33 条第 5 款与用户最高原则**：
1. 大模型自主判断删除无意义垃圾切片；
2. 图像在端侧做 50ms 初筛（画质 < 0.4 直接丢弃）；
3. 达标图像由轻量模型提取纯文本 Caption 语义摘要（如“用户在书房阅读专业书籍”），**绝对严禁在主库中持久化原始二进制大图字节**；
4. 提取 128 维声纹局部敏感哈希（LSH），绑定对应实体；对于未绑定实体的陌生人声纹，超过 180 天未再接触自动标记 `is_tombstone = True`。

## 2. 必须实现的接口契约与代码骨架
在 `src/aios_core/ingest/multimodal_edge.py` 实现：

```python
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ImageSemanticObservation(BaseModel):
    observation_id: str
    quality_score: float = Field(..., ge=0.0, le=1.0)
    semantic_caption: str
    scene_tags: List[str] = Field(default_factory=list)
    raw_image_bytes_retained: bool = Field(default=False)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VoiceprintProfile(BaseModel):
    voiceprint_id: str
    entity_id: Optional[str] = None
    feature_hash: str
    first_detected_at: datetime
    last_contact_at: datetime
    is_tombstone: bool = False

class EdgeMultimodalCleaner:
    def evaluate_and_clean_image(self, image_metadata: Dict[str, Any], raw_bytes: bytes) -> Optional[ImageSemanticObservation]:
        # 画质初筛: < 0.4 坚决抛弃
        score = float(image_metadata.get("quality_score", 0.5))
        if score < 0.4:
            return None
        # 仅生成文字摘要，强制丢弃 raw_bytes
        caption = image_metadata.get("caption", "日常活动场景")
        tags = image_metadata.get("tags", ["routine"])
        return ImageSemanticObservation(
            observation_id=f"obs_img_{int(datetime.now(timezone.utc).timestamp()*1000)}",
            quality_score=score,
            semantic_caption=caption,
            scene_tags=tags,
            raw_image_bytes_retained=False
        )

class VoiceprintLifecycleManager:
    def sweep_stale_voiceprints(self, profiles: List[VoiceprintProfile], current_time: datetime) -> List[VoiceprintProfile]:
        # 超过 180 天未绑定的声纹标记 tombstone
        updated = []
        for p in profiles:
            if p.entity_id is None and (current_time - p.last_contact_at) > timedelta(days=180):
                p.is_tombstone = True
            updated.append(p)
        return updated
```

## 3. 验收标准与 pytest 断言代码
在 `tests/unit/test_m1_001r_edge_cleaner.py` 必须跑通：
```python
def test_edge_cleaner_discards_low_quality_and_never_stores_raw_bytes():
    cleaner = EdgeMultimodalCleaner()
    bad_res = cleaner.evaluate_and_clean_image({"quality_score": 0.3}, b"fake_bytes")
    assert bad_res is None
    
    good_res = cleaner.evaluate_and_clean_image({"quality_score": 0.85, "caption": "散步"}, b"fake_bytes")
    assert good_res is not None
    assert good_res.raw_image_bytes_retained is False
    assert good_res.semantic_caption == "散步"

def test_voiceprint_sweep_tombstone():
    mgr = VoiceprintLifecycleManager()
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    old = VoiceprintProfile(
        voiceprint_id="vp_001", feature_hash="hash123",
        first_detected_at=now - timedelta(days=200),
        last_contact_at=now - timedelta(days=190)
    )
    res = mgr.sweep_stale_voiceprints([old], now)
    assert res[0].is_tombstone is True
```
