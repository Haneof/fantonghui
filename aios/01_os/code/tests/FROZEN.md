# tests/ 目录状态标注（宪法 V1.4-r0 §4.4 / §12.8）

- 生成：2026-09-11 ｜ 本文件**只标注、不删文件**：M0-M3.5 的验收裁判是已封账证据的取证入口，
  删掉等于切断 `STATUS.md`/`tasks.md` 里那些数字（829 条/秒、六跳金字塔、千题 90.6%）的可复现路径。
- §12.8 原文：「attentiond 按 §4.3 重写列为 P0 迁移缺口；**本地摘要/本地意图识别相关代码按 §4.4 冻结**。」

## 一、KEEP（V1.4 下仍是资产）

| 文件 | 为什么合宪 |
|---|---|
| `gate_rules.py` | 纯阈值/模式对比、零模型零语义 —— 正是 §4.3 attentiond 要的形态；已改可移植路径，2026-09-11 Linux 实测 636 题 100.0%，`run/bench1k/gate_rules_result.json` 与 Windows 时代证据逐字节相同。**Sprint 2 守门回归以它为准** |
| `gate_benchmark.py` | 门控基准口径，同上（含模型对照组，对照组部分见下方 FROZEN） |
| `test_s1_t5.py` | Event→World 链路 + 幂等/陈旧/非法 + 回放确定性；§12.3 允许保留的基础。刻意用可移植 API（Popen/signal），Linux/WSL2 可跑 |
| `gen_1k.py`、`run_1k.py`、`reconcile_dataset.py`、`report_dataset.py`、`push_dataset.py`、`push_tail.py`、`dump_readable.py` | 出题/对账/搬运的**基准流水线**本身不违宪——§13.6「本地出题迭代闭环」要的就是这套手法；但口径须按 §13.4 重写（从"答题正确率"改为意图理解 + 帮助效用） |
| `big_model_answers.py` | 大模型作答标准答案 —— §1.3/§4.4 把语义工作判给大模型，与本文件方向一致 |
| `test_m0.py`…`test_m35.py` | 已验收里程碑裁判，保留（但依赖 `taskkill`，Windows-only；见下方缺口） |

## 二、FROZEN（§4.4/§12.8 冻结，不得作为 V1.4 实现起点）

| 文件 | 冻结原因 |
|---|---|
| `rebuild_pyramid.py`、`rebuild_pyramid_v2.py`、`verify_pyramid.py` | 用本地小模型做**递归摘要**＝廉价层做语义判断，§4.4 第 2 条冻结。六跳金字塔的**结构与溯源**保留（memoryd 已验收），摘要生成方须改为大模型或纯 SQL 统计 |
| `grade_2b_4b.py`、`compare_big_local.py`、`compare_fixed.py`、`llama_probe.py`、`probe_4b_speed.py`、`probe_chain.py`、`finish_4b_and_bench.py`、`resume_4b.py`、`benchmark_cognition.py` | 全部服务于「本地 0.5B/1.5B/2B/4B 能否胜任认知」这条**已证伪路线**（千题实测 2B 31.1%、1.5B 33.5%；结论见 roadmap 末「本地参数量升级路线性价比证伪」）。V1.4 下不再追加投入 |
| `../run/bench1k/*`（基准产物） | 已验收证据，保留跟踪；**不是**待重跑的测试 |

## 三、已知环境缺口（清理时未越界修的，登记备查）

1. `test_m0.py`…`test_m35.py` 用 `taskkill /F /PID` 杀进程，Linux/WSL2 直接抛错 →
   「双环境复验」只能对 `test_s1_t5.py` 与 `gate_rules.py` 签字，M0-M3.5 的 Windows 裁判在 Linux 上不可复现。
   修法：改 `os.kill(pid, signal.SIGKILL)` 分派（`test_s1_t5.py` 已有可移植范式可抄）。属"改动已验收裁判"，需指挥官单独点头。
2. 上述 FROZEN 脚本里 8 个仍带 `ROOT = r"C:\Users\Administrator\..."` 绝对路径 —— 冻结件不必修，
   但**若将来解冻**（例如把摘要流水线切给大模型重跑），第一步就是替换为 `__file__` 推导。
