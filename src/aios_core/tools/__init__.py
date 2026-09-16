"""AIOS 3.0 新机制发明工具箱（ToolProposal 契约实现层）。

当前收录：

* :class:`adaptive_compressor.AdaptiveTemporalCompressor` —— 自适应时序
  压缩算子（TP-001）：平稳窗聚合 + 尖峰保全，样本守恒账目公开；
* :class:`dual_lens_index.DualLensVirtualIndexProjector` —— 双透镜虚拟
  索引投影器（TP-002）：AsKnown/Annotated 双视图零拷贝叠加。

每个工具随附 :class:`ToolProposal` 契约实例的工厂（能力缺口 / 使用
场景 / 现有局限 / 接口 / 预期收益 / 验证方案六字段齐全）。
"""

from aios_core.tools.adaptive_compressor import (
    AdaptiveTemporalCompressor,
    CompressionResult,
    tool_proposal_of_compressor,
)
from aios_core.tools.dual_lens_index import (
    DualLensVirtualIndexProjector,
    LensView,
    tool_proposal_of_dual_lens,
)

__all__ = [
    "AdaptiveTemporalCompressor",
    "CompressionResult",
    "tool_proposal_of_compressor",
    "DualLensVirtualIndexProjector",
    "LensView",
    "tool_proposal_of_dual_lens",
]
