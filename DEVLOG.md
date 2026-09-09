# AIOS Core 开发日志（DEVLOG）

本文件是 **Agent 侧执行日志**，不是规范文档。规范只在 `docs/`（12 份，唯一规范目录，Q2 裁决）。
把日志放仓库根而不放 `docs/`，是为了不污染 canonical 文档集合。

## 维护规则（每个任务必须遵守）

1. **每次执行结束先更新本日志，再 commit + push**；一个任务至少一条日志、至少一个 commit。
2. 条目字段固定，缺项写"无"，不得省略字段：
   `任务 / commit / 修改文件 / 执行命令 / 测试结果(数字) / 原始输出摘要 / 发现的冲突 / 未完成项 / 待架构师裁决`
3. **只记事实与可复现证据**（命令、文件、数字、commit hash）。
   禁止写 PASS / READY / ARCHITECTURE CORRECT / SPRINT COMPLETE / 验收通过 —— 那是架构师的判定权（MASTER PROMPT V1.0 Authority 顺序）。
4. 测试有红项时：红项全名必须原样进日志，不许用"测试通过"替代。
5. 与规范冲突时：**停止改动 → 记在"发现的冲突" → 等裁决**，不得自行 reinterpret（09 禁止事项 1/2/7）。
6. 新条目**追加在文件末尾**（时间正序），不改写历史条目；写错就补一条"更正"条目。

## 条目模板

```
## YYYY-MM-DD HH:MM  · Sprint N / Task M — 标题
- commit: <hash> (分支 arena/01a086b3-fantonghui)
- 修改文件: path(+a/-d), ...
- 执行命令: cmd1 ; cmd2
- 测试结果: Ran X / ok Y / failures Z / errors E / exit N
- 原始输出摘要: 关键几行原文
- 发现的冲突: 无 / 描述
- 未完成项: ...
- 待架构师裁决: ...
```

---

## 2026-09-09 15:31 · 前置 — 仓库重置与规范落库

- commit: `09e3652`（历史已重写为单提交，`.git` 27M→163K，`git push --force`）
- 修改文件: 全仓（旧项目内容清空）
- 执行命令: `git rm -r .` / `git commit` / 历史重写 / `git push --force`
- 测试结果: 无测试（当时尚无代码）
- 原始输出摘要: 远端 `arena/01a086b3-fantonghui` = `09e3652`
- 发现的冲突: 附件通道不可用（`sandbox:/mnt/data/AIOS_Core_v0.1-r1.zip` 沙箱不可达），改用聊天粘贴
- 未完成项: 无
- 待架构师裁决: 仓库是否转私有 → 架构师答"不用转私有"

## 2026-09-09 15:41 · Q2 裁决落地 — docs/ 唯一规范目录

- commit: `cd05d19 chore: apply Q2 ruling — docs/ is the only normative dir`
- 修改文件: 12（`git mv` 11 份规范入 `docs/`，旧宪法改名入 `archive/AIOS_Constitution_V1.2.md`）
- 执行命令: `git mv` / `git commit` / `git push`
- 测试结果: 无测试
- 原始输出摘要: 0 insertions/deletions（纯移动）
- 发现的冲突: 无
- 未完成项: 无
- 待架构师裁决: 无

## 2026-09-09 15:54 · 规范同步 V0.1-r1（13 文件）

- commit: `354b685 docs: sync AIOS Core V0.1-r1 ruling set into docs/ (13 files)`
- 修改文件: 10（+324/−25）：`docs/00,01,02,03,04,06,07,08,09` + 宪法 V1.2-r1 + MASTER PROMPT V1.0
- 执行命令: 逐份写入 / `for f in *.md; do wc -l; grep -c '^```'; grep -c '&gt;'`（完整性核对）
- 测试结果: 无测试；23 项同步验收 = 21✓ / 2✗（当时 `03` Entity 示例与 `04` §10.2 未同步）
- 原始输出摘要: 归一报备：HTML 实体还原、去外层围栏、`02` 重复 `## 8.` 中 Wake 改 `## 9.`、拆 `08` 粘连标识符、补 8 处被吞中文冒号、还原 `06` 树 12 行链接污染
- 发现的冲突: D1 `03` Entity 用 `relationships` vs schema `relationship_ids`；D2 `04` §10.2 与 §11 双口径；D3 去重归属；D4 token 口径
- 未完成项: 4 条冲突待裁决
- 待架构师裁决: D1–D4 → 架构师已全部定稿（改文档 / 引用 §11 唯一口径 / 入 Sprint 1 Task 4 / output tokens）

## 2026-09-09 15:58 · Sprint 1 / Task 1 — 目录 + 骨架 + 9 份 canonical schema

- commit: `d69f31c feat(sprint1/task1): project skeleton + 9 canonical schemas + spec-conformance tests`
- 修改文件: 54（+1524）：`core/` 11 子系统 21 个 Runtime 骨架、`schemas/` 9 份 draft-07、`tools/{schema_check,mini_jsonschema}.py`、`tests/unit/{test_schemas,test_spec_conformance}.py`、根 `.gitignore`
- 执行命令: 生成脚本按 `06`+`02` 建骨架 / `python3 tools/schema_check.py` / `python3 -m unittest discover -s tests -t . -v`
- 测试结果: Ran 14 / 13 pass / **1 fail** / exit 1
- 原始输出摘要: 唯一红项 `test_examples_validate` → `$[Entity]: 缺少必需字段 'relationship_ids'` + `出现未定义字段 ['relationships']`（即 D1 矛盾的机械证据）
- 发现的冲突: 生成器 bug：骨架 docstring 里 `f"{cls}"` 作用域错 → `NameError` 而非 `NotImplementedError`（已修）
- 未完成项: D1 未落地 → 后续由裁决修复
- 待架构师裁决: 无（D1 已裁决）

## 2026-09-09 16:12 · Sprint 1 / Task 2–9 — Event + World 主链

- commit: `b264045 feat(sprint1/task2-9): perception->event->world pipeline + timeline player`
- 修改文件: 23（+1355/−108）：`core/{perception,event,world}/*`、`adapters/simulator/{mock_adapter.py,negotiation_timeline.txt}`、`tools/{simulator/player.py,forbidden_scan.py}`、`tests/unit/{test_event_runtime,test_perception,test_world,test_prohibitions}.py`、`tests/integration/test_replay.py`、`tests/scenario/helpers.py`、`tests/constitution_v1.2-r1.sha256`，另含 `docs/{00,01,02,03,04,09}` 的 D1–D4 同步
- 执行命令: `python3 tools/schema_check.py` / `python3 tools/forbidden_scan.py` / `python3 -m unittest discover -s tests -t . -v` / `python3 tools/simulator/player.py --fresh --noise 3`
- 测试结果: Ran 59 / ok 59 / failures 0 / errors 0 / exit 0（中途曾 Ran 57 → failures=1 errors=16，全部记录在下）
- 原始输出摘要: `raw signal=10 → Semantic Event=7 → 去重后落库=7(丢 3) → World Update=7 → World Change=7`；`ratio=0.00%`；`raw_still_held=0`；`回放一致性: 一致`
- 发现的冲突: 本轮修掉 3 个自身 bug：① `forbidden_scan.py` 的 `ROOT=parents[2]` 少算一层 → `FileNotFoundError`；② `WorldRuntime._append` 调用未定义 → 11 项 `AttributeError`；③ `09:15` 连续同内容价格事件不产生 Change（测试序列写错，改为含 `09:10 沉默` 的真实序列并补 `test_identical_repeat_makes_no_world_change`）
- 未完成项: `active_goals`/`pending_tasks` 无规则会产生；关系仅由 `EntityRuntime.link()` 显式建立，事件不自动推断；去重只处理"窗口内完全相同内容"
- 待架构师裁决: Task 1 的"全骨架"旧断言随 Sprint 推进被改写成两条（`sprint1_runtimes_are_live` / `out_of_sprint_runtimes_are_still_skeleton`）是否接受
- 备注: Task 2 的代码与 Task 3–9 同批提交，未拆分

## 2026-09-09 16:23 · Sprint 1 / Task 2 定稿 — Raw Signal 合同严格化 + 多模态 Simulator

- commit: `161fd3c feat(sprint1/task2): strict Raw Signal contract + multimodal mock perception`
- 修改文件: 9（+731/−79）：`core/perception/{raw_signal.py(新),semantics.py(新),perception_runtime.py}`、`adapters/simulator/{mock_adapter.py,mock_multimodal.jsonl(新)}`、`tests/unit/{test_perception.py,test_perception_contract.py(新)}`、`tests/integration/test_perception_loop.py(新)`、`tests/unit/test_world.py`(1 处)
- 执行命令: `python3 -m unittest discover -s tests -t . -v` / `python3 -m unittest tests.unit.test_perception tests.unit.test_perception_contract tests.integration.test_perception_loop -v` / `python3 tools/schema_check.py` / `python3 tools/forbidden_scan.py` / `python3 tools/simulator/player.py --fresh --noise 3`
- 测试结果: 全套 Ran 96 / ok 96 / failures 0 / errors 0 / exit 0；Task 2 三模块 Ran 45 / OK / exit 0；spec-check exit 0；forbidden scan exit 0；player exit 0
- 原始输出摘要: `Ran 96 tests in 0.077s / OK`；`SPEC-CONFORMANCE OK`；`扫描 43 个源文件,宪法 sha256[:12]=9bb96cf0f0b3 / 禁止事项 1-7: 全部通过`；`emitted=7 unknown=1 rejected=0 raw_still_held=0`
- 发现的冲突: ① 任务书字段名 `event_id/event_type/payload/attributes` vs `docs/03` 的 `id/type/content/entities`（`additionalProperties:false` 禁 payload/raw_data）→ 服从 schema，`schemas/**` 零改动；② Raw Signal 无 canonical schema，加文件=改架构 → 落在 `core/perception/raw_signal.py`；③ `Event.type` 无枚举，新引入 `departure`；④ 路径偏差：`tests/unit/perception/` 不存在；⑤ `adapters/simulator/**` 与 `tests/unit/test_world.py` 在任务书允许清单外，为满足"实现要求三"与严格合同连带修改
- 未完成项: 见上一条与本条"发现的冲突"②③④；真实 VAD/ASR/Vision/IMU/Phone 适配器未接（Sprint 1 范围外）；`confidence` 为规则常量非概率
- 待架构师裁决: ①–⑤ 五项 + 越界改动是否接受

## 2026-09-09 16:40 · Sprint 1 / Task 2 — 验收材料导出（只读审计）

- commit: 无（本轮禁止修改：未改代码/测试/文档，未提交）
- 修改文件: 无
- 执行命令: `git status --short` / `git diff --stat` / `git log -1 --oneline` / CMD-1..6（见上一条的测试命令 + `git show 161fd3c -- tests/unit/test_world.py` + 只读执行 Raw→Event 样例 + 全仓 import 扫描）
- 测试结果: Ran 45 / ok 45 / failures 0 / exit 0；Ran 96 / ok 96 / failures 0 / exit 0；定向边界测试 Ran 6 / ok / exit 0
- 原始输出摘要: `Ran 96 tests in 0.128s / OK`；grep `FAIL|ERROR|Traceback` → 0 命中；工作区与 `161fd3c` blob 逐字节一致（sha256 前 12 位 8 个文件全部一致）
- 发现的冲突: 本轮无新增；披露一项事实：unittest 的 verbose 输出走 **stderr**，stdout 为 0 字节，故审计材料里 stdout 空、stderr 全文
- 未完成项: 无（导出任务本身不含实现）
- 待架构师裁决: A–M 全部判定 + 上一条 ①–⑤

## 2026-09-09 16:44 · Sprint 1 / Task 3 — Event Runtime 最小可运行实现

- commit: `984792c feat(sprint1/task3): Event Runtime contract gates, resume, ordering, lineage`
  （本条日志单独成提交，保持"一任务=一代码 commit"以便 bisect/revert；前置裁决：Task 2 ✅ PASS）
- 修改文件: 2
  - `core/event/event_runtime.py`（重写：闸门/恢复/顺序/lineage/留痕）
  - `tests/unit/test_event_runtime.py`（10 → 33 项，原 10 项一字未改）
- 执行命令:
  `python3 -m unittest tests.unit.test_event_runtime -v` ;
  `python3 -m unittest discover -s tests -t . -v` ;
  `python3 tools/schema_check.py` ; `python3 tools/forbidden_scan.py` ;
  `python3 tools/simulator/player.py --fresh --noise 3` ; `git status --short`
- 测试结果: Event 定向 Ran 33 / ok 33 / exit 0；全套 **Ran 119 / ok 119 / failures 0 / errors 0 / exit 0**
  （96 → 119，净增 23；未删任何历史测试，未改任何既有断言）；spec-check exit 0；forbidden scan exit 0；player exit 0
- 原始输出摘要:
  `Ran 119 tests in 0.159s / OK`
  `扫描 43 个源文件,宪法 sha256[:12]=9bb96cf0f0b3 / 禁止事项 1-7: 全部通过`
  落盘：`var/run/events/events.jsonl`(7 条) + `var/run/events/dropped.jsonl`(3 条留痕,
  `reason=DUPLICATE_WITHIN_WINDOW`)；lineage 实例
  `"raw_ref":"perception://temp/evt_001?signal_id=sim-negotiation_timeline-001"`
  player 漏斗不变：raw=10 → event=7 → 去重后=7 → World Update=7 → Change=7
- 本轮实现的关键决策:
  1. Event Store 对 Perception 的唯一依赖是 `is_minted` 纯谓词（09 禁止事项 5 的闸门），
     并新增 AST 测试锁死"names 只允许 is_minted"+ monkeypatch 把感知四个入口打断仍能写读，
     以此同时满足"不得绕过 Perception"与"不得调用 Perception"两条要求。
  2. 相同 timestamp 用"到达顺序"而非 id 二次排序，理由是可回放性；已写成测试。
  3. 去重丢弃改为写 `dropped.jsonl` 留痕：满足"不得静默丢失"，且不改 02 的去重语义。
  4. `resume()` 默认开启：重启后去重窗口也从磁盘重建（否则重放会二次入库）。
     副作用：不带 `--fresh` 重跑 player 会把整条时间线判为重复（此前是重复追加，更坏）。
- 发现的冲突:
  1. **`confidence` 区间无规范约束**——`schemas/event.json` 只有 `type: number`，无
     `minimum/maximum`，故 `confidence: 12` 会被 Store 收下。0..1 目前只由 Perception 侧
     保证。修它=改 schema（本任务禁止项 17），因此我把它写成显式测试
     `test_confidence_range_is_a_spec_gap_not_our_invention`，让缺口可见而非被掩盖。
  2. **字段命名**：任务书用 `event_id / entity_ids / attributes`，canonical 是
     `id / entities / content(+location_id)`，且 `additionalProperties:false` 明确拒绝
     `attributes`。按"不得重新定义第二套 Schema"服从现有 schema，`schemas/**` 零改动。
  3. **02 §1 的三项职责尚未实现**：时间窗口聚合、空间关联、Entity 关联、Event Cluster /
     World Update Request 输出——Task 3 明确不做 Event→World，Fusion/Patterns 保持骨架。
- 未完成项: 上述 1、3；以及 `patterns.py`/`fusion.py` 属 Sprint 3 Task 1。
- 待架构师裁决: ①`confidence` 0..1 是否写进 docs/03 + schema；②相同 timestamp 的排序键
  （到达序 vs id）是否升为 Contract；③`dropped.jsonl` 留痕是否是 Event Store 的正式产物；
  ④Raw Signal 特征字段判定（`signal_id/modality/payload`）作为"拒收原始输入"的判据是否可接受。

## 2026-09-09 17:12 · Sprint 1 / Task 3 FIX-01 — 解耦 Event→Perception 反向依赖 + 分支并入

- 架构裁决: Task 3 **❌ FAIL → 需 FIX**。两条实质理由:
  ① `core/event` 直接 `from core.perception... import is_minted` = 真实运行时反向依赖;
  ② `origin="perception"` 只是调用方自述(声明),`is_minted` 才是证明 → 要解决的是
     provenance / mint authority,不是 origin 字符串。
  另两条登记但不阻断: tests/unit/perception 路径偏差(保持现状,不做形式主义重构);
  source fallback 只是实现约定(暂不写进 docs/02)。治理要求: 从现在起一任务=一 commit。
  架构师原话登记: "不能把'测试全绿'当成架构正确的充分条件"。
- commit: `5c761d4` (FIX 本体) + `e6007b0` (merge, 见下)
- 修改文件: 5 —— `tools/provenance.py`(新,中立登记册) /
  `core/event/event_runtime.py` / `core/perception/perception_runtime.py` /
  `tests/unit/test_event_runtime.py` / `tests/unit/test_perception.py`
- 方案: Perception --mint()--> EventProvenance <--is_minted()-- Event Runtime。
  放 `tools/` 是沿用 `tools/mini_jsonschema.py` 既有先例(两 Runtime 共用中立设施),
  不进 core/、不新增 Runtime、不占契约编号。双方 `provenance=` 可注入,默认共享进程级实例。
  公开面只有 mint/is_minted/reset/snapshot,无"补登记"后门(测试锁死);
  并如实写明 Python 无私有封装 → 该机制防结构性绕过,不是防同进程恶意代码(需签名才是,
  属架构裁决,未做)。
- 执行命令: 冒烟(默认登记册/注入隔离/跨册拒绝/伪造拒绝) ;
  `python3 -m unittest tests.unit.test_event_runtime tests.unit.test_perception` ;
  `python3 -m unittest discover -s tests -t . -v` ; `python3 tools/forbidden_scan.py` ;
  `python3 tools/schema_check.py` ; `python3 tools/simulator/player.py --fresh --noise 3` ;
  `git grep -n "core.perception" -- core/event` ;
  `git grep -nE "importlib|__import__|sys.path.*perception|import_module" -- core/event` ;
  `git grep -n "core.event" -- core/perception`
- 测试结果: 定向 `Ran 37 / ok 37 / exit 0`;全套 **Ran 124 / ok 124 / exit 0**(96→119→124,
  历史测试删除 0 项);spec-check exit 0;forbidden scan exit 0(未改该脚本);player exit 0
  (漏斗 raw=10→event=7→去重后=7→World Update=7→Change=7 未变)
- 原始输出摘要: 三查全空(`core/event→perception` exit 1、动态 import exit 1、
  `core/perception→core.event` exit 1);冒烟四行
  `默认登记册 7/7 / 注入同一登记册 7/7 / 换登记册后全部被拒 7/7 / 伪造 id: ID_NOT_MINTED`
- 本轮红项(我写歪的断言,未蒙混): `test_registry_has_no_backdoor` 断言
  `reg._minted.add(...)` 应抛 AttributeError → `AssertionError: AttributeError not raised`。
  处置: 改为 `test_registry_has_no_public_backdoor`,断言"公开面无补登记入口 + 登记只能经 mint()",
  并把拦不住私有写入这一事实写进测试文档串。
- 既有断言放松(报备): `test_perception.test_only_stdlib_and_local_imports` 白名单加
  `tools.provenance`(Perception 现在要用中立登记册,必然结果)。
- 分支事件(重要): push 被拒 → 远端有架构师 17:05 推的 `c68e8a6
  "feat(aios): AIOS 腕上AI操作系统全量代码与文档"`(136 files, +26034, 0 deletions,
  新增 `aios/` 131 文件 + `reports/` 5 份 HTML)。分叉点 `9e95b24`。
  `git merge-tree` 预演干净 → 停止并上报(未擅自动历史)。架构师裁"远端并入本分支":
  执行 `git merge --no-ff` → `e6007b0`,无 rebase/无 force push/无改写历史。
  合并后回归仍 124/124,三查仍为空。远端已同步 `e6007b0`。
- 已知并存(未裁决,不阻断): `aios/01_os/schemas/event.proto.md` 自称 Event 唯一权威,
  与 `docs/03` + `schemas/*.json` 并存;`aios/01_os/code/api_pool/gemini_pool.py` 属云端 LLM,
  且 `tools/forbidden_scan.py` 只扫 core/tools/adapters 故不会命中;`aios/01_os/code/run/bench1k/`
  把基准数据放进了 git。架构师裁决: "先不管,继续 Task 4" → 已按此登记,未纳入扫描、未修改。
- 未完成项: `tools/forbidden_scan.py` 禁止#5 文案仍写"is_minted…绕过 Perception Runtime"
  (语义对、措辞过时,改它越出本次窄边界,待批准);player 仍用默认登记册;
  Task 3 前 4 项待裁决(confidence min/max、同刻排序键、dropped.jsonl 地位、
  Raw Signal 判据)仍挂;`docs/02 §1` 的窗口聚合/空间关联/Entity 关联未实现(属 Sprint 3)。
- 待架构师裁决: 上述文案改动 + Task 3 最终复核(现在可以做了:124/124 且边界三查为空)。

---

### [2026-09-10] Task 4 — Event Deduplication 契约固化

- **任务**：按架构师裁决执行"契约固化"7 项；明确**不**新增第二套去重实现、**不**做语义相似度/"意思差不多"判重。
- **commit**：`d544105`（父 `8c3d833`）
- **修改文件**：`core/event/event_runtime.py`(M)、`tools/forbidden_scan.py`(M)、`tests/unit/test_dedupe_contract.py`(新增, 24 项) —— 共 3 个文件，**新增去重算法 0 行**
- **执行命令**：`python3 -m unittest discover -s tests -t .` / `python3 tools/forbidden_scan.py` / `python3 tools/schema_check.py` / 一次性台架 `/tmp/bench.py`（真实管线，未入库）/ `git add … && git commit && git push origin arena/…`
- **测试与门禁数字**：`Ran 148 tests … OK`（124 → 148，+24，历史测试 0 删）；`forbidden_scan` exit 0（扫描 44 文件，禁止事项 1–7 全通过）
- **原始输出摘要（红→绿）**：
  - `test_dropped_record_fields …`：`AssertionError: Items in the first set but the second: 'dropped_at_event' / Items in the second …: 'reason'` → **我的实现写的是 reason，是测试把字段名写错了**；同时我原本还断言"键顺序也是契约"，而 `_append` 用 `sort_keys=True` 必然规范化顺序 → **顺序当契约是假契约**，改为 frozenset 集合语义并改正测试字段名。
  - `test_module_fingerprint …`：`AttributeError: 'function' object has no attribute '__func__'` → 类属性经解析已是普通函数；改为 `EventRuntime.fingerprint is fingerprint`（真断言，不是放宽）。
  - `test_three_at_same_instant …`：`AssertionError: [1, 2] != [1, 1]` → **是我算错了**：120s 窗口下第 2 条被丢后窗口不刷新，第 3 条距第 1 条 0s 仍 ≤120s，故应丢 2 条。实现正确，测试改对了。
  - 扫描器扩展后首跑 `tools/forbidden_scan.py` exit 1：`[3] 读写 'dropped.jsonl' 的文件不在 core/event/ : tools/forbidden_scan.py`、`[4] core/** 出现语义相似度/模糊匹配工具 … : tools/forbidden_scan.py` → **门禁把自己定义了这些字面量当成违规**。处置：仅对"字面量规则"豁免扫描器自身文件（def/调用规则仍查它），并用 4 个 decoy 变异测试（在 `core/world`、`core/memory`、`core/event` 造第二套实现）证明它没有被调瞎 → 转绿。
- **发现的冲突（两条）**：
  1. **`aios/` 与"全仓唯一实现"的正面冲突仍在**（架构师已裁"暂不纳入 Core 验收体系"，本任务按其指示**未触碰** `aios/`）：机械计数 `aios/` 内 LLM 调用点 41 个文件、`difflib`/相似度 1 个文件（`aios/01_os/services/event_dedup/tests/test_dedup.py`，其 `core/event/dedup.py` 本体不在版本控制内）。`tools/forbidden_scan.py` 的 `CODE_DIRS` 仍只扫 `core|tools|adapters`，故这些不会被门禁命中 —— 如实登记，不擅自扩范围。
  2. **沙箱工作区被重建，导致一次 git 记账错位（重要，非代码问题）**：本轮开始时环境重新 `clone` 了仓库；因 GitHub **默认分支仍是旧项目 `main`（`02a072c`）** 且 clone 是单分支，HEAD 被落到 `02a072c`，索引变成旧项目的树。我第一次的 Task 4 提交 `d1c05a0` 因此被压在**错误基线**上（`git push` 被拒、`git merge-tree` 报 `refusing to merge unrelated histories`）。处置：先逐 blob 比对证明**磁盘内容零丢失**（`8c3d833` 的 221 个文件全部在位，差异恰好只有 Task 4 的 3 个文件），再用 `git reset --mixed 8c3d833`（只改 HEAD/索引、不写任何文件）把记账拉回远端尖端，重跑全量 148/OK + 扫描器 exit 0 后重新提交为 `d544105` 并推送成功。**未使用 `--hard`、未 amend、未 force push、未删任何文件**；错误基线的 `d1c05a0` 保留在本地 reflog 可查。**风险仍在**：只要默认分支是旧 `main`，每次沙箱重建都可能重复此错位 → 建议架构师考虑把仓库默认分支改为 `arena/01a086b3-fantonghui`，或在 Task 2/3/4 验收后整体并入 `main`。
- **压缩率实测（一次性台架，真实管线 Perception→Event→Dedup→World，非手工构造）**：
  - 高密度（2s 间隔、N=50000）：raw 50000 → 语义事件 50000 → 去重后入库 **4794**（丢弃留痕 45206，event→stored = 0.096）→ World 真正变化 **1375**（stored→change = 0.287，无变化尝试 3419）→ 端到端 **1/36**。
  - 低密度（17s 间隔、N=5000）：5000 → 5000 → 入库 4679（丢 321）→ 变化 1341 → 端到端 **1/4**。
  - **诚实结论**：`stored` 那一层的压缩率几乎完全由"合成流的重复密度 × 120s 窗口"决定（同一套代码 1/36 vs 1/4），**不是架构的功劳**；`change` 层（1375/4794 = 0.287）才是逻辑产生的（只在槽位真变化时产 Change）。Perception 本身不做过滤（by design），所以 raw→event = 1:1。`expensive_model_call_count = 0` 是因为 **Wake 尚未实现**，不是被过滤出来的。此台架未入库（属 Task 4 之外），如需长期化见待裁决。
- **未完成项**：`fusion.py` / `patterns.py` 仍是骨架（本次只钉 `event_runtime.py` 的去重契约）；`core/world/world_runtime.py` 的 Change 判定仍是"整块槽位值比较"。
- **待架构师裁决（新增）**：① `120s` 窗口是否正式升为 Contract 值（现为实现默认值）；② 是否把压缩率台架升格为 `tools/bench/compression.py` 入库，作为 Sprint 3 的 Relevance/Awake 验收底座（我倾向要，因为它暴露了"stored 层压缩是数据属性"这一事实，能防止后续拿假压缩率邀功）；③ 是否把 GitHub 默认分支从旧 `main` 改为工作分支（见上冲突 2）。**Task 4 不宣布 PASS，等待验收。**
