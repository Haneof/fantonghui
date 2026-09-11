"""Perception 的 Mock 语义规则表(确定性规则,零模型、零网络)。

这里只回答"这条信号在说什么"(事件类型 + 感知置信度 + 通道),不回答"它重不重要"。
重要性属于 Relevance Runtime(02 §6,Sprint 3),在本文件里做重要性判断即为越权。

规则按 modality 分组:命中即产出,首条命中优先(顺序=优先级,便于审查);
全部未命中 -> 降级为 unrecognized + 低置信度,绝不丢弃(08 E:未知输入降级而非丢弃)。
"""
from __future__ import annotations

import re

UNKNOWN_TYPE = "unrecognized"
UNKNOWN_CONFIDENCE = 0.40

#: (匹配式, Semantic Event 的 type, 感知通道 source, 置信度)
Rule = tuple[re.Pattern[str], str, str, float]

RULES: dict[str, tuple[Rule, ...]] = {
    "text": (
        (re.compile(r"到公司|到达|抵达"), "arrival", "gps", 0.98),
        (re.compile(r"进入|到场"), "person_enter", "mic", 0.90),
        (re.compile(r"提出降价|砍价|再次谈价格|谈价格"), "price_negotiation", "mic", 0.93),
        (re.compile(r"沉默|不说话"), "silence", "imu", 0.75),
        (re.compile(r"打开|查看"), "document_open", "screen", 0.95),
        (re.compile(r"合同"), "contract_discussion", "mic", 0.90),
    ),
    "audio_transcript": (
        (re.compile(r"接受不了|太高|太贵|便宜点|降价|砍价"), "price_negotiation", "asr", 0.91),
        (re.compile(r"合同|条款|交付"), "contract_discussion", "asr", 0.88),
        (re.compile(r"谈价格|价格"), "price_negotiation", "asr", 0.90),
        (re.compile(r"先这样|今天到这"), "silence", "asr", 0.60),
    ),
    "sensor": (
        (re.compile(r"entry_sensor:opened"), "person_enter", "sensor", 0.80),
        (re.compile(r"workspace_motion:active"), "person_enter", "sensor", 0.60),
        (re.compile(r"workspace_motion:idle"), "silence", "sensor", 0.55),
        (re.compile(r"workspace_motion:left"), "departure", "sensor", 0.70),
    ),
    "vision": (
        (re.compile(r"张总|客户|访客|visitor"), "person_enter", "vision", 0.72),
        (re.compile(r"合同|文件|document|paper"), "document_open", "vision", 0.68),
    ),
    "calendar": (
        (re.compile(r"谈判|合同|评审"), "contract_discussion", "calendar", 0.65),
    ),
}

#: Mock 实体解析表。真实实现里 entity/identity 绑定由 Identity Runtime 异步完成
#: (02 §5),这里只是让 Simulator 能跑通"事件带 entity"这条合同。
MOCK_ENTITIES: dict[str, str] = {"张总": "person_017", "小王": "person_021", "合同": "contract_003", "公司": "place_004"}


def classify(modality: str, text: str) -> tuple[str, float, str]:
    """(event_type, confidence, channel)。未命中不抛错:未知场景必须降级而非丢弃。"""
    for rx, name, channel, conf in RULES[modality]:
        if rx.search(text):
            return name, conf, channel
    return UNKNOWN_TYPE, UNKNOWN_CONFIDENCE, ""


def resolve_entities(text: str) -> list[str]:
    """按名称表解析 entity id,顺序稳定(按表内声明序),保证同输入同输出。"""
    return [eid for name, eid in MOCK_ENTITIES.items() if name in text]
