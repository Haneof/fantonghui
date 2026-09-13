# AIOS Core R2 Reference Implementation

这是 AIOS Core R2 的**总工程师参考实现**，目的是冻结最关键的底层契约，避免后续编码代理自行改变项目核心世界模型。

当前已经亲自实现：

- 稳定对象 ID。
- 唯一世界对象基类。
- `occurred_at / learned_at / recorded_at` 三类时间语义。
- Claim（主张）类型与 KnowledgeState（知识状态）分离。
- EvidenceSet（证据集合）一等对象。
- EventAnchor（事件锚点）生命周期字段。
- DimensionDefinition / Membership / Derivation 三层结构。
- Goal 与 Task 分离。
- Wake、Session、Action、Outcome 等冻结契约。
- SQLite 追加式对象版本库。
- 全局 World Revision（世界版本）。
- optimistic concurrency（乐观并发检查）。
- idempotency（幂等写入）。
- 版本化引用验证。
- 历史世界读取与 knowledge cutoff（当时可知边界）。
- Task / Event 状态转换校验。
- 关键契约测试。

## 运行

```bash
cd aios_core_r2_reference
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## 重要边界

这不是完整 AIOS，也不是“已经完成 M0”的声明。它是第一批必须由总工程师亲自固定的底层参考代码。后续模块应围绕这些契约扩展，不应绕过 Core 直接写 SQLite。
