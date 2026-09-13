"""AIOS Core - 唯一世界读写与规则实现。

此包是 AIOS 世界的唯一正式实现，所有世界修改最终必须经过此包的 storage / services。
禁止 ai_worker / console / simulator / evaluator 直接操作 SQLite。
"""
