# archive/ —— 与宪法 V1.4-r0 不相干内容的归档区

- 执行：Arena Agent ｜ 2026-09-11 ｜ 指挥官 2026-09-11 裁决「V1.4-r0 生效 + 清理与最新宪法不相干的无用文件和代码，为重构做准备」
- **本目录是只读历史区，不是实现线。** 任何新代码、新 Runtime 一律不得写进这里（宪法 §12.4：一个 Runtime 只能有一个 Owner）。
- 归档全部用 `git mv` 完成，`git log --follow <文件>` 可查回原路径与全部历史。**没有 `rm -rf`，没有一行历史被丢弃。**

## 一、裁决依据（逐条对宪法）

| 宪法条款 | 原文要义 | 本目录如何执行 |
|---|---|---|
| §12.4 | 任何新 Runtime 只能有一个 Owner，**不得同时在 `core/` 和 `aios/01_os` 复制实现** | `legacy_core_simulator/`：根目录 `core/`+`tests/`+`tools/`+`adapters/`+`schemas/` 整簇迁出（实测：6 份 root schema 被主线引用数 = 0；`schemas/{event,world_state,world_change}.json` 与主线逐字节相同 = 纯重复） |
| §12.1 | V1.2-r1、V1.3-r0 **原文件保留，不删除** | 未删任何宪法。V1.2-r1 原件留在 `docs/`；本目录只放**根目录那份逐字节重复副本**（`diff -q` 已验证 IDENTICAL）与 989 行前身版 `AIOS宪法.md` |
| §4.4 / §12.7 | 《OS 总体架构设计 V0.1》冲突部分**冻结**，修订合宪前不得按旧设计推进 | 该文档留在原位 `aios/01_os/docs/` 并加冻结横幅（它仍是 M0-M3.5 已验收实现的说明书，移走会切断取证链） |
| §12.3 | 已实现的 World State/Change/Memory/Cognition/Privacy/Interaction **可以保留**，但须重新标注 V1.4 边界 | 主线 15 服务一个没删，逐个加 `COMPAT_IMPL` / `FROZEN` 标注（见 `aios/01_os/code/services/README_V1.4_BOUNDARY.md`） |
| §12.5 | UI、App、Hardware **先保持空壳** | `aios/02_hardware`、`03_ui`、`04_apps` 的占位目录原样保留——空壳是宪法要求，不是无用文件 |

## 二、清单

### `legacy_core_simulator/`（V1.2 体系 Core Simulator 线，Sprint 1 交付物）

```
core/      1946 行：ai attention capability event evolution identity interaction memory perception policy world
tests/     192 项单元测试（V1.2 布局与 02 契约 14 条的一致性裁判）
tools/     schema_check.py / forbidden_scan.py / mini_jsonschema.py / provenance.py / simulator/player.py
schemas/   9 份 draft-07 JSON
adapters/  simulator mock 源 + phone/wearable 空包
docs/      冻结快照：00-09（V0.1-r1，与当初验收时逐字节一致）+ AIOS_Constitution_V1.2-r1.md
```

**本包自包含、可复现**（不依赖活动工作区，实测于 2026-09-11）：

```bash
cd archive/legacy_core_simulator
python3 -m unittest discover -s tests -t .     # → Ran 192 tests ... OK
python3 tools/schema_check.py                    # → SPEC-CONFORMANCE OK
python3 tools/forbidden_scan.py                  # → 禁止事项 1-7 全部通过，宪法 sha256=9bb96cf0f0b3
python3 tools/simulator/player.py --fresh --noise 3   # → 7 事件 7 次 World Update，applied==changes==updated==7
```

> `docs/` 里放的是**验收时那一版**的 00-09（V0.1-r1），不是根目录旧副本。原因：这 192 项测试的 `ROOT = parents[2]` 指向包根，历史上一直读的是 `docs/`；若冻结成根目录 V0.1 原版，会出现 9 FAIL + 1 ERROR（契约编号、schema 集合、wake 枚举都对不上）。归档包必须冻结在"当初通过的那一版"，否则取证永久失真。

### `superseded_docs/`（被 V1.3/V1.4 取代的治理文档）

| 文件 | 取代者 |
|---|---|
| `AIOS宪法.md`（989 行） | V1.2-r1（STATUS 冲突 4 已判定为历史参考） |
| `AIOS_PROJECT_EXECUTION_MASTER_V1.0.md` | V1.4 第十二章迁移纪律 + `docs/07_DEVELOPMENT_PLAN.md` |
| `AIOS_V2.0_WORLD_OS_UPGRADE_SPEC.md` | V1.3-r0 / V1.4-r0 本体 |

实测全仓引用数 = 0（`grep -rn` 除自身与 archive 外无命中）。

### `reports_v1.2/`

5 份 HTML 评审报告（宪法终审/重构评审/架构蓝图/门控v2/M2.5-M3.5 阶段报告）。V1.2 体系的历史评审材料，DEVLOG 有引用，保留可查但不参与 V1.4 实施。

## 三、这里的东西什么时候该拿回来

- `core/world/world_runtime.py`（579 行）里**已验证的守恒不变式与幂等台账设计**（`applied/no_rule/no_slot_change/stale/replay_skipped/rejected` 恰好一个下落、`verify_traceability/conservation/ledger` 三自检）——V1.4 的 Observation Store 与 Timeline 写入同样需要这套不变式，重写 `stated` 为 Global Timeline 时**直接借鉴，不要从零想**。
- `tests/unit/test_prohibitions.py` 的"禁止事项必须是可执行断言"这个手法——V1.4 第十章安全底线照此实现机械扫描器。
- `schemas/` 里的 memory/cognition/decision/growth/relationship 五份 draft-07：V1.4 §5.4/§8.3 需要新的 Inference Event / Summary Node schema，字段可参考，但**必须按 V1.4 语义重写，不得原样搬回**（它们是 Semantic-Event-first 的产物）。
