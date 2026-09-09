"""极简 JSON Schema 校验器(只覆盖本项目 schema 用到的关键字)。

不引入 jsonschema 依赖的原因见 06 "第一版真实实现建议":Simulator 要让非程序员能在自己
PC 上直接跑起来。因此 schema 只使用 draft-07 的 type / required / enum / properties /
items / additionalProperties / oneOf / minItems 这几个关键字;一旦将来需要更严格的
校验,换成 jsonschema 库即可,schema 文件本身不用改。
"""
from __future__ import annotations

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def validate(instance, schema, path="$") -> list[str]:
    """返回错误列表;空列表表示通过。"""
    errs: list[str] = []

    if "oneOf" in schema:
        branches = [e for e in (validate(instance, sub, path) for sub in schema["oneOf"]) if not e]
        if not branches:
            errs.append(f"{path}: 不满足 oneOf 任一分支")
        return errs

    t = schema.get("type")
    if t:
        py = TYPES[t]
        ok = isinstance(instance, py) and not (t in ("number", "integer") and isinstance(instance, bool))
        if not ok:
            return [f"{path}: 期望 {t},实际 {type(instance).__name__}"]

    if "enum" in schema and instance not in schema["enum"]:
        errs.append(f"{path}: {instance!r} 不在枚举 {schema['enum']} 中")

    if t == "object":
        for r in schema.get("required", []):
            if r not in instance:
                errs.append(f"{path}: 缺少必需字段 {r!r}")
        props = schema.get("properties", {})
        extra = set(instance) - set(props)
        if extra and schema.get("additionalProperties") is False:
            errs.append(f"{path}: 出现未定义字段 {sorted(extra)}(additionalProperties=false)")
        for k, v in instance.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
    elif t == "array":
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errs.append(f"{path}: 元素数 {len(instance)} < minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for i, v in enumerate(instance):
                errs += validate(v, item_schema, f"{path}[{i}]")
    return errs
