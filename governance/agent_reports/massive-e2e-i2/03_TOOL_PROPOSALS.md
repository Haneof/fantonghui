# 《新机制发明与新工具提议 (ToolProposal 契约)》

## ToolProposal #1: 自适应时序压缩算子
- 位置: src/aios_core/tools/adaptive_time_series_compressor.py
- 测试: tests/simulation/test_adaptive_time_series_compressor.py 4/4
- 口路: 阶段一, 所有输入波形(HR/IMU/噪声)

**核心机制**: 滑动 31 样本中位数 + MADσ 鲁棒方差; >4σ 全保; >=0.25 bpm 保留; 余者丢弃。
**实测**: 压缩比 ≥3.0x, >4σ 泄露 0, MADσ 单调自洽, digest 复现 100%。

## ToolProposal #2: 双透镜虚拟索引投影器
- 位置: src/aios_core/tools/dual_lens_virtual_index.py
- 测试: tests/simulation/test_dual_lens_virtual_index.py 5/5
- 口路: 阶段五老王案注记

**核心机制**: AsKnown 与 Annotated 双透镜; object_id 哈希下钻 O(1); update/delete 一律 RegistryImmutableViolationError。
**实测**: 100+ 注记投影下查询方差 <10% (O(1) 无塌慢), 重复注记/悬空注记全部拦截。

## 总结
把高频输入交自适应压缩, 把历史交新式注解, 这将永远代入叶办高的原因在于 token 不是资源,
时间才是。
