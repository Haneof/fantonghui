# AIOS 总工程师审查档案

本目录保存 AIOS 各开发任务的正式工程审查记录。

规则：

- reviews/ 记录“为什么某项任务通过或被打回”
- `reviews/M0/` 保存开发任务级评审；`reviews/architecture/` 与 `reviews/constitution/`
  保存架构级（宪法/契约级）评审及其证据，其裁决针对文档与契约，
  不得被引用为任何开发任务的 FINAL_PASS
- 同一对象存在多份架构评审时，以 `reviews/architecture/AIOS_V3_MULTI_REVIEW_META_AUDIT_NO_GO_2026-09-16.md`
  的统一元裁决为准；后到的评审必须声明与既有档案的收敛/增量关系，不得另立裁决口径
- **派单编号唯一来源 = 文件，不是文档**：`governance/issue_registry/v3_issue_registry.json`。
  同一 `M*-***` 号段已被 **5 套方案**重复分配（D+统一母表 / E / F+P3 / P1 / P2），实际争用面 **66 个号**
  （交叉矩阵见 `reviews/architecture/AIOS_V3_UNIFIED_BACKLOG_AND_AS_BUILT_VERIFICATION_2026-09-16.md` §9.2）。
  规则：①**任何评审/方案文档都不得自我宣告编号唯一性**，只能向 registry 提交候选 slug；
  ②派单必须携带 `slug` + `source_docs`，号仅作显示；③`governance/issue_registry/check_issue_registry.py`
  （临时号 `NUMCI-001`）为 CI 门，当前实跑 **GATE = RED**（`RULE_A 0 / UNREGISTERED 0 / CONFLICT 39 / UNRATIFIED 21 / RULE_D 0 / GATE_DISPUTE_OPEN 2`，registry `0.3.0-PROPOSAL`），
  **转绿之前禁止按任何一套号位开工**；④裸 `V` 前缀与 `GAP-` 前缀停用（前者被 5 套语义占用，
  后者被两份报告双占用），审计发现用 `V3G-*`、工程任务用 `M*-*`，两者以 `traces_to` 关联
- **临时命名空间 `RC-*`（重构设计书标签）规则**：文档可以自带 `RC-***` 标签便于阅读，但**标签不等于号**。
  ①每条必须带 `slug`，**同 slug ⇒ 判定为同语义收敛 ⇒ 登记为既有号的 `alias`，绝不发第二个号**；
  ②每条必须声明 `maps_to`（映射既有 `M*` 号）或 `origin=NEW_NO_PRIOR_CLAIM`；③`status` 只能是 `PROPOSAL*`；
  ④门位判断不同 ⇒ 写入 owner 的 `gate_disputes{status: OPEN}` 由治理方裁决，**不得私改 registry 的 gate**；
  ⑤`check_issue_registry.py` 的规则 `A6/A7/D1~D6/E1~E2` 强制以上全部（含"alias 必须在文档中真实出现"的反虚构检查），
  并已做**负向自测**（注入 9 类违规全部被捕获，exit=1）：`governance/issue_registry/evidence/negative_self_test_2026-09-16.log`。
  当前实跑：`RC` 条目 30 个 / alias 11 个 / OPEN gate 分歧 2 处（`M2-024`、`M2-026`）
- **证据门（`PROBE-CI-002` 的可执行形态）**：`governance/ci/run_gates.py`（stdlib-only，六道门）
  把"文档 ↔ registry ↔ 探针工件"三者的一致性变成 CI 断言：
  `CG-1` 工件哈希 + **溯源**（工件内嵌 `script_sha256` 必须等于当前脚本字节哈希；脚本改了没重跑 ⇒ fail）；
  as-built 审计工件另做**双向溯源**：`subject_sha256` 必须等于当前**被测源码**哈希——别人改了被测代码（哪怕是把 gap 修好了），
  旧审计工件的实测数就不得再被引用下结论、
  `CG-2` 调用编号门 + **治理债棘轮**（`CONFLICT/UNRATIFIED/gate 争议`只许减少）、
  `CG-3` 文档↔registry（RC 标签必须已注册/已登记 alias、slug 逐字相同、门位一致或有 OPEN 争议）、
  `CG-4` 当场跑探针 CI 档（100k，含 I7 非空转四项复核）、
  `CG-5` 数字可追溯（1M 工件的每个数值事实必须能在设计书正文定位；旧运行值不得回潮，
  历史值只允许出现在 `HISTORICAL-RUN-VALUES` 哨兵区内）、
  `CG-6` **交付物存在性**（派工单注册表声明的"核心交付源码"必须存在且行数 ≥ 50；缺口数对 baseline 棘轮，只许减少；
  本轮 `blocking=false` —— 真实缺口 2 项时直接阻断会挡住所有其他工作，补齐后翻成阻断）。
  实跑 **VERDICT = PASS**；负向自测 **15 场景 15/15 命中预期规则**（含两条反后门：允许清单外的字面量号、超闸的哨兵区；
  S11 篡改审计工件 / S12 改被测源码不重跑 / S13 派工单多声明一个不存在的交付物 /
  S14 改另一支探针的被测源码 ⇒ 只判该模块工件失效，用 `expect_absent` 断言**不得牵连**其他模块）
  （`governance/ci/negative_self_test.py`，工件在 `governance/ci/evidence/`）。
  **治理债不算 hard fail**：号位未裁决造成的红色只能由治理方消除，把它设成 hard fail 会让门永久红而被绕过。
  workflow 模板：`governance/ci/governance-gates.workflow.yml`（push/PR 跑 100k + 自测；`workflow_dispatch` 可跑 1M 放行档）。
  ⚠️ **尚未安装到 `.github/workflows/`**：本会话的 GitHub App 令牌缺 `workflows` 权限，远端拒绝该类推送；
  需有权限者 `cp` 过去并提交（模板头部写了两种安装方式）。未安装期间门仍可本机/任何 CI 直接调用。
- **as-built 审查（`M1-001R` 端侧摄入与声纹 TTL）**：`reviews/architecture/AIOS_Core_as_built_审查报告_M1_001R_端侧摄入与声纹TTL_2026-09-16.md`，
  新增 **`V3G-009`（隐私计量撒谎，已修）/ `V3G-010`（循环内不变量，已修 3.66×）/ `V3G-011`（180 天双口径，待治理裁决）**。
  裁定**交付成立**：三条违宪红线全部可执行地满足（探针 10/10 门通过）——画质 < 0.4 丢弃且 **0.4 本身保留**；
  输出模型**类型上不可能**持有字节（`Literal[False]` + 校验器 + `extra=forbid`），可变帧在成功/丢弃/**非法**三条路径都被真擦除；
  陌生声纹 > 180 天墓碑召回 **1.0**（10,000/10,000）、已绑定实体误伤 **0**（0/2,000）。
  实测：单帧清洗（含 2 MB 擦除）p95 **0.173 ms** vs 工单"50ms 初筛"⇒ 289× 余量；128 维 LSH 单次哈希 **0.797 ms**；
  10 万档案 sweep **437.408 ms** / advance **550.465 ms**；声纹绑定 100 万次比较 **748.6 → 204.3 ms**（`bound_count` 前后同为 969）。
  单测 22 → **41**，全仓 `650 → 669 passed`。证据：`verify_landed_m1_001r_edge.py`(v1.3.0) + 修复前/后两份工件
  （修复前那份标 `HISTORICAL`：`subject_sha256` 指向已不存在的字节状态，故进清单防篡改但**不参与**当前代码溯源）。
  两条一般化教训已写进设计书 §3.7.6：①合规类指标必须能**自证区分度**（"做不到"可接受，"做不到但指标看起来做到了"不可接受）；
  ②"只改性能不改语义"的重构，验收断言必须是**与旧实现的行为差分**——本轮漏写 `.bit_count()` 使 178/300 个绑定结果改变，
  而 650 个既有测试全绿放行（既有测试只钉住 fail-closed 分支，没钉住"成功绑定"正路）。
- **as-built 审查（第一批派工交付）**：`reviews/architecture/AIOS_Core_as_built_审查报告_第一批派工交付_2026-09-16.md`，
  新增审计发现号 **`V3G-001 ~ V3G-008`**（已入 registry `0.3.3-PROPOSAL`，以 `traces_to` 关联 Issue）。
  方法：**不读文档自述，只读仓库现状 + 现场实测**；每个性能结论绑定"规模档 + fixture + profile + 工件哈希"四元组。
  实测（1M 实体、枢纽词覆盖 33%、门 p95 ≤ 50 ms）：已落地的 CJK 多词共搜 `co_search` **382.074 ms（超门 7.64×）**、
  `co_search_scored(limit=200)` **543.899 ms（10.9×）**、`partial_search` **740.660 ms（14.8×）**；
  机理 = `EXPLAIN QUERY PLAN` 的 `USE TEMP B-TREE FOR GROUP BY`；**同 schema 换计划**（选择性升序两两求交 + LIMIT 早停，
  选择性走 planner 缓存）实测 **2.744 ms = 139×** ⇒ 是查询计划问题，不是 schema/分词问题。
  另：`index_many()` 峰值 RSS = O(总 postings)，1M 档建索引**实测 OOM（SIGKILL/137）**，分批后 390.2 MB vs 单批 1,019.1 MB；
  宪法 §89.2 别名覆盖实测缺失 96.7%（查 `母亲` 命中 10,990 vs 查 `妈妈` 333,334）；
  **5 张派工单只交付 3 张**（`pyramid_aggregator.py`、`hyperlink_traverser.py` 不存在），且号位整条链**错位一格**
  （CJK 共搜占了 `M1-017`=端侧降采样管线的号，回溯标注占了 `M1-018`=中文混合共搜的号），5/5 派工单**不带 slug**（违反 R6）。
  证据：`reviews/architecture/evidence/verify_landed_m1_017_cjk.py`（v1.1.0）+ 10k/100k/1M 三份工件与日志（均入 SHA256SUMS）。
  测试与环境裁决（`governance/issue_registry/evidence/pytest_environment_ruling_2026-09-16.log`）：
  `pytest --collect-only` = **650**（unit 626 / integration 4 / architecture 20），`PYTHONPATH=src` 下 **650 passed**；
  历史争议值 558 与 433 **均已过期**。唯一失败 `test_b8_cross_process_…` 是**夹具环境依赖缺陷**（子进程不继承 pytest 的 pythonpath），非产品缺陷。
- **性能数字唯一来源与三态规则**：Issue 验收只允许引用该文件 §5.2「可引用数字表」（as-built 探针与
  A 的 3.6M 探针，脚本+输出+日志+SHA256 均已入库）。三态见其 §9.4：**可引用**（有工件）／
  **可复现但未取证**（脚本已入库但无运行工件，如 B 的三支探针 ⇒ 暂不得写入验收，须由 `PROBE-CI-002`
  跑一次留工件后转态）／**不可引用**（仅正文数字，永久替换）
- 宪法/R1/R2/架构规格仍以仓库根目录正式文件为唯一权威
- reviews/ 不修改系统定义，只保存工程裁决
- 每个重大任务至少保留 PATCH_REQUIRED / FINAL_PASS 等关键审查记录
- 不允许开发代理自行伪造 FINAL_PASS
- FINAL_PASS 只能依据项目总工程师明确裁决创建
- 测试输出、review packet等证据放入对应 milestone/evidence 目录
