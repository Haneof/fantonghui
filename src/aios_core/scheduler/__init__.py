"""Scheduler —— 条件驱动任务调度（M2-005R）。

本包刻意**不**重导出 ``conditional_engine`` 的成员：调用方按模块路径显式导入
（``from aios_core.scheduler.conditional_engine import ConditionalEngine``），
以免在包 ``__init__`` 里再造一层与法定契约并列的别名面。
"""
