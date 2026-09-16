"""Scheduler - 条件驱动任务调度（M2-005R 双轨引擎）。

宪法级工程规约：

1. DORMANT 隐形：未成熟任务在看板组装与常规会话中绝对物理隐形，
   Token 消耗严格为 0，严禁把未成熟任务灌入 LLM Prompt；
2. Level-1 机械快轨：纯时间到期 / 地理围栏 / 心率阈值等客观物理条件
   由底层调度器 1ms 内纯 Python 判定，大模型调用次数严格为 0；
3. Level-2 机会式捎带：语义任务只在用户主动唤醒且场景相关时顺路评估，
   绝不为休眠任务自主唤醒大模型；
4. 状态机铁律：DORMANT -> READY -> RUNNING -> COMPLETED 单向流转，
   非法跃迁 100% 抛 IllegalStateTransitionError。
"""

from .conditional_engine import (
    ConditionalTask,
    ConditionalTaskEngine,
    ConditionalTaskState,
    ConditionKind,
    IllegalStateTransitionError,
    LEGAL_TASK_TRANSITIONS,
)

__all__ = [
    "ConditionalTask",
    "ConditionalTaskEngine",
    "ConditionalTaskState",
    "ConditionKind",
    "IllegalStateTransitionError",
    "LEGAL_TASK_TRANSITIONS",
]
