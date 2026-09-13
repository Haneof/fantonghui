"""AI Worker - 未来负责调用大模型并通过 Core 公共接口操作世界。

边界红线：
- 禁止 import sqlite3
- 禁止 from aios_core.storage.sqlite_store import ...
- 禁止直接打开 *.db
- 禁止 import evaluator 隐藏真值

所有世界读写必须走 aios_core 公开接口。
"""
