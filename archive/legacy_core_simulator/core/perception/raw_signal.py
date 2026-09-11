"""Raw Signal —— Perception Runtime 的标准输入合同(02 §0)。

这是整条链路上唯一"允许携带原始数据"的对象:它只存在于适配器和本模块的瞬态里,
变成 Semantic Event 之后原始体立即销毁(宪法 12.2)。因此这里没有对应的 canonical
schema —— docs/03 的 canonical 集合是 9 份(Sprint 1 Q4 裁决),Raw Signal 不属于
World 的持久对象,加 schema 文件等于改架构,故不做。

字段(5 个,全部必填):
    signal_id : 适配器内的唯一标识,用于 raw_ref 回溯
    timestamp : "HH:MM" / "HH:MM:SS" / 完整 ISO-8601
    source    : 设备/通道来源,例如 simulator / phone / office_hub
    modality  : text | audio_transcript | sensor | vision | calendar
    payload   : 按 modality 定型的字典(见 PAYLOAD_SPEC)

任何不合规输入都抛 PerceptionInputError(带 code/field),禁止静默吞错。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

#: 支持的感知模态。真实 VAD/ASR/Vision/IMU 适配器接入时在此扩展(Sprint 1 之后)。
MODALITIES: tuple[str, ...] = ("text", "audio_transcript", "sensor", "vision", "calendar")

#: 各模态 payload 的最小定型:required 决定"合法 payload"长什么样,optional 允许附带。
PAYLOAD_SPEC: dict[str, dict[str, dict[str, tuple[type, ...]]]] = {
    "text": {"required": {"text": (str,)}, "optional": {"channel": (str,)}},
    "audio_transcript": {
        "required": {"transcript": (str,)},
        "optional": {"speaker": (str,), "duration_ms": (int, float)},
    },
    "sensor": {
        "required": {"sensor": (str,), "state": (str,)},
        "optional": {"value": (int, float)},
    },
    "vision": {
        "required": {"objects": (list, tuple)},
        "optional": {"scene": (str,)},
    },
    "calendar": {
        "required": {"title": (str,)},
        "optional": {"starts_in_min": (int, float)},
    },
}

REQUIRED_FIELDS: tuple[str, ...] = ("signal_id", "timestamp", "source", "modality", "payload")

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)?$")


class PerceptionInputError(ValueError):
    """raw signal 不合法。code 让调用方能区分错误种类,而不是只看到一句 500。"""

    def __init__(self, code: str, detail: str, sig_field: str = "") -> None:
        self.code = code
        self.field = sig_field
        self.detail = detail
        super().__init__(f"[{code}] {sig_field and sig_field + ': ' or ''}{detail}")


@dataclass(frozen=True)
class RawSignal:
    """一次原始感知输入。frozen:Perception 之后的任何环节都不得改写它。"""

    signal_id: str
    timestamp: str
    source: str
    modality: str
    payload: Mapping[str, Any] = field(default_factory=dict, compare=True)

    @classmethod
    def from_dict(cls, obj: Any) -> "RawSignal":
        """严格解析。缺字段 / 类型错 / modality 不认识 / payload 不合规,一律明确抛错。"""
        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, Mapping):
            raise PerceptionInputError("BAD_RAW_TYPE", f"raw signal 必须是 dict,收到 {type(obj).__name__}")
        for name in ("signal_id", "source"):
            if name not in obj:
                raise PerceptionInputError("MISSING_FIELD", f"缺少 {name}", name)
            _ = cls._nonblank(obj[name], name)
        if "timestamp" not in obj:
            raise PerceptionInputError("MISSING_FIELD", "缺少 timestamp", "timestamp")
        ts = cls._nonblank(obj["timestamp"], "timestamp")
        if not (_TIME_RE.match(ts) or _ISO_RE.match(ts)):
            raise PerceptionInputError("BAD_TIMESTAMP", f"无法识别的时间戳 {ts!r}(需要 HH:MM[:SS] 或 ISO-8601)", "timestamp")
        if "modality" not in obj:
            raise PerceptionInputError("MISSING_FIELD", "缺少 modality", "modality")
        modality = cls._nonblank(obj["modality"], "modality")
        if modality not in MODALITIES:
            raise PerceptionInputError("BAD_MODALITY", f"不支持的 modality {modality!r},可选 {MODALITIES}", "modality")
        if "payload" not in obj:
            raise PerceptionInputError("MISSING_FIELD", "缺少 payload", "payload")
        payload = cls._payload(modality, obj["payload"])
        return cls(obj["signal_id"].strip(), ts, obj["source"].strip(), modality, payload)

    @staticmethod
    def _nonblank(value: Any, name: str) -> str:
        """三个错误等级要分清楚:没有(None)/类型错/空白,便于上游按 code 处理。"""
        if value is None:
            raise PerceptionInputError("MISSING_FIELD", f"{name} 不得为 None", name)
        if not isinstance(value, str):
            raise PerceptionInputError("BAD_TYPE", f"{name} 必须是字符串,收到 {type(value).__name__}", name)
        if not value.strip():
            raise PerceptionInputError("EMPTY_FIELD", f"{name} 不得为空白", name)
        return value.strip()

    @staticmethod
    def _payload(modality: str, payload: Any) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise PerceptionInputError(
                "BAD_PAYLOAD", f"payload 必须是 dict({modality} 需要 {sorted(PAYLOAD_SPEC[modality]['required'])}),"
                               f"收到 {type(payload).__name__}", "payload")
        spec = PAYLOAD_SPEC[modality]
        required, optional = spec["required"], spec["optional"]
        allowed = set(required) | set(optional)
        for key in sorted(allowed):
            if key not in payload:
                if key in required:
                    raise PerceptionInputError("BAD_PAYLOAD",
                                               f"{modality} 的 payload 缺少 {key}", f"payload.{key}")
                continue
            val = payload[key]
            types = {**required, **optional}[key]
            if isinstance(val, bool) or not isinstance(val, types):
                raise PerceptionInputError("BAD_PAYLOAD",
                                           f"payload.{key} 类型应为 {types},收到 {type(val).__name__}",
                                           f"payload.{key}")
            if isinstance(val, str) and not val.strip():
                raise PerceptionInputError("BAD_PAYLOAD", f"payload.{key} 不得为空", f"payload.{key}")
        for key in payload:
            if key not in allowed:
                raise PerceptionInputError("UNKNOWN_PAYLOAD_KEY",
                                           f"{modality} 不接受 payload.{key}(允许 {sorted(allowed)})",
                                           f"payload.{key}")
        if isinstance(payload.get("objects"), (list, tuple)) and not payload["objects"]:
            raise PerceptionInputError("BAD_PAYLOAD", "vision.objects 不得为空列表", "payload.objects")
        return dict(payload)

    @property
    def semantic_text(self) -> str:
        """把 payload 压成一行文本,供确定性规则表匹配。

        这一步只做"读内容",不做判断;判断在 semantics.classify。
        """
        p = self.payload
        if self.modality == "text":
            return str(p["text"]).strip()
        if self.modality == "audio_transcript":
            return str(p["transcript"]).strip()
        if self.modality == "sensor":
            return f"{p['sensor']}:{p['state']}"
        if self.modality == "vision":
            return f"{p.get('scene', '')} {' '.join(str(o) for o in p['objects'])}".strip()
        if self.modality == "calendar":
            return str(p["title"]).strip()
        return ""  # pragma: no cover - modality 已在 from_dict 处定型
