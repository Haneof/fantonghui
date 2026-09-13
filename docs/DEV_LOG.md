# AIOS 2.0 开发日志

## 2026-09-14 M0-001 仓库骨架、包边界与依赖方向

### 执行前检查

**A. 当前目录树**
- 根: 8个md规格 + README + aios_core_r2_reference + test_output
- 无 src/, 无 pyproject.toml, 有 .git, 有 reference

**B. 参考代码目录树**
- aios_core_r2_reference/src/aios_core/contracts/ 8文件
- storage/sqlite_store.py 459行
- services/state_machines.py
- tests/ 15 tests

**C. pyproject.toml**
- 根: 不存在
- reference: 存在, name=aios-core-r2-reference, requires-python>=3.12, pydantic>=2.10, pytest>=8

**D. .git**
- 存在, branch arena/01a09bc6-fantonghui, 已同步至 aios-2.0

**E. Python包结构**
- 仅 aios_core_r2_reference/src/aios_core/__init__.py

**F. 测试结构**
- 仅 aios_core_r2_reference/tests/

**G. pytest**
- 可执行, pytest 9.1.1, python 3.11.2

**H. 参考测试结果**
- 15 passed

**I. 冲突**
- 无 src/，符合M0-001预期，需新建

### 执行步骤

1. mkdir -p src/aios_core/{contracts,storage,services,query,world,dependency,tasks,wake,workspace,actions,summaries,dimensions} src/ai_worker src/console src/simulator src/evaluator tests/{unit,integration,architecture,fixtures} docs .github/workflows
2. cp reference contracts/storage/services -> src/aios_core/
3. 创建占位 __init__.py，写入边界红线说明
4. 创建 pyproject.toml src layout
5. 创建 tests/architecture/test_boundaries.py AST扫描
6. 复制 reference tests -> tests/unit/
7. 创建 docs/归档 + CI + README + TASK_PROGRESS_R2.md
8. pytest tests -v -> 21 passed
9. pytest reference -> 15 passed
10. git commit cb24f04

### 架构边界实现细节

- TEST-A/B: 扫描 ai_worker/*.py AST，禁止 sqlite3 和 aios_core.storage
- TEST-C: 扫描 aios_core/*.py 禁止 evaluator
- TEST-D: 扫描 ai_worker 禁止 evaluator
- TEST-E: importlib.import_module 8个包
- TEST-F: 检查 pyproject.toml 存在

### 验收

- 正式 src layout 已建立
- aios_core 唯一 Core 实现
- 5大运行单元物理隔离
- 架构测试6 + 单元15 =21 passed
- 原参考15 tests仍通过
- pytest根目录执行成功
- pyproject.toml可用
- README边界说明
- 未删宪法/架构文档
- 未开始M0-002

### 下一步

等待总工审查 M0-001，通过后进入 M0-002 统一错误码和协议级异常


## 2026-09-14 M0-001-R 总工复审修正

### 复审命令
M0-001 状态 CONDITIONAL PASS，禁止进入 M0-002，修正两个问题并制作审查包

### 发现问题
1. Python 基线：参考要求 >=3.12，正式项目误改为 >=3.11 以适配当前 3.11.2 环境
2. 文档双重副本：根目录与 docs/ 同时存在 8 份正式文档，违反单一真源

### 执行

**修正 Python 基线**
- 原始证据：aios_core_r2_reference/pyproject.toml:6 `requires-python = ">=3.12"`
- 正式项目恢复：pyproject.toml `>=3.12`
- 尝试获取 3.12：which python3.12 not found, apt Permission denied -> PYTHON_312_RUNTIME_UNAVAILABLE
- 保留正式要求，不降低，CI 已配置 3.12，记录兼容性说明

**解决文档双重副本**
- SHA256 校验根 vs docs/ 8份文件，全部 OK identical
  - AIOS宪法2.0.txt e74a45f139f2f8afabc5ed03bd369cd89dd666036fd70566be699c2afe21cf95
  - AIOS Core 系统架构图 9fb1b1cf...
  - AIOS认知工作台 c568d2ab...
  - AIOS虚拟世界 a5f90a1b...
  - R1 51c30801..., R2 4f725189..., R2拆分 2d60276d..., 总工版 314f94b3...
- 删除 docs/ 中 8 份重复正文
- 创建 docs/README.md 权威说明：根为唯一真源，docs不得保存第二份可编辑副本

**检查依赖边界测试**
- 确认 rglob 递归扫描 src/ai_worker/**/*.py 和 src/aios_core/**/*.py
- 覆盖 import sqlite3 / from sqlite3 / import aios_core.storage / from aios_core.storage.sqlite_store / import evaluator 等
- 无需修改测试，测试已覆盖

**修正 README 措辞**
- 原：“ai_worker 获得 Connection 即视为违规”
- 改为：“正式代码架构禁止AI Worker直接访问SQLite，并由自动架构测试阻止已定义的直接依赖方式” + 说明架构测试属于政策检查，非 OS 安全沙箱

**依赖版本纪律**
- pyproject.toml 已符合：pydantic>=2.10,<3, pytest>=8,<9，无大型框架

**重新运行测试**
- python3 --version: 3.11.2
- PYTHONPATH=src pytest tests -v: 21 passed
- PYTHONPATH=aios_core_r2_reference/src pytest reference: 15 passed

**生成审查包**
- M0_001_REVIEW_PACKET.md (含 commit hash, Python基线, pyproject, 目录树, 测试结果, 架构测试列表, 文档真源, 修改文件, git status, 偏差)
- M0_001_REVIEW_TEST_OUTPUT.txt (真实输出)
- AIOS_2.0_M0-001_review.zip (172K, SHA256 c33e64e745db457d23d719872033e61579e893f8f8037860bb75d7013b8340e0)
  - 包含：pyproject.toml, README.md, 8根正式文档, src/, tests/, .github/, TASK_PROGRESS_R2.md, REVIEW_PACKET, TEST_OUTPUT, reference, docs/

### 提交
- e36c365 M0-001-R fix python baseline and docs single source

### 结果
- Python 基线恢复 >=3.12
- 文档单一真源达成
- 架构测试递归确认
- README 措辞准确
- 21 + 15 tests passed
- 审查包已生成
- 未进入 M0-002，未修改世界对象语义


## 2026-09-14 M0-001-R2 harden repository boundary checks

### 触发
- 评审反馈：TEST-B 绕过 from aios_core import storage / as xxx, AST fail-closed缺失, scanner无回归测试, TEST-F命名误导, pyproject.toml MIT license未删除, .gitignore未进入zip

### 修复清单执行

**1. TEST-B 绕过修复**
- 修改 tests/architecture/test_boundaries.py: _has_import_storage_internal 新增检测 mod == "aios_core" 且 alias.name == "storage" 或 startswith "storage."
- 覆盖 6 种形式：import aios_core.storage, import aios_core.storage.sqlite_store, from aios_core.storage import, from aios_core.storage.sqlite_store import, from aios_core import storage, from aios_core import storage as xxx
- 验证：新增回归测试 CASE-5/6 均判违规

**2. AST fail-closed**
- 建立统一 _parse_file_or_fail(file_path) helper
- OSError/UnicodeError/SyntaxError 必须抛 AssertionError 带路径和原始异常，禁止 return False
- 所有检测函数复用该 helper，确保无法读取/解析文件时测试失败而非返回安全

**3. Scanner回归测试**
- 新增 tests/architecture/test_scanner_regression.py 12 cases (10 required + 2 extra)
- CASE-1 import sqlite3 => 违规
- CASE-2 from sqlite3 import connect => 违规
- CASE-3 import aios_core.storage => 违规
- CASE-4 from aios_core.storage import => 违规
- CASE-5 from aios_core import storage => 违规 (绕过)
- CASE-6 from aios_core import storage as core_storage => 违规
- CASE-7 import evaluator => 违规
- CASE-8 from evaluator import truth => 违规
- CASE-9 合法 from aios_core.contracts import Claim => 不误判
- CASE-10 无法parse文件必须失败 (AssertionError)
- extra import/from storage.sqlite_store => 违规

**4. TEST-F 修正**
- 原 test_f_pytest_runs_from_root 误导，改为 test_f_repository_test_configuration_present
- 检查 ROOT/pyproject.toml/tests/src 存在，README/review packet准确描述

**5. License**
- 删除 pyproject.toml license = {text="MIT"}, 不替换其他许可证，等待负责人决定

**6. .gitignore**
- 确认存在且包含 .venv/venv/__pycache__/*.pyc/.pytest_cache/build/dist/*.egg-info/.env/.env.*/*.db
- 已进入新 ZIP AIOS_2.0_M0-001_R2_review.zip

**7. Python 3.12 CI**
- 基线保持 >=3.12，本地 3.11.2 PYTHON_312_RUNTIME_UNAVAILABLE，CI已配置 3.12 (备份在 docs/workflow_backup/ci.yml.txt)

**8. 构建验证**
- python3 -m pip wheel . --no-deps -w dist_test --no-build-isolation --ignore-requires-python 成功
- 产物 aios_core-0.1.0-py3-none-any.whl 22K SHA256 1e2800e676e8efc1d1e7ad50de434a97eaf0512dd861de37fbe0c1e0223aebfc
- 使用 --ignore-requires-python 因正式要求 >=3.12 但本地 3.11.2，--no-build-isolation 因网络隔离，实际命令已报告
- 构建后删除 dist_test，未提交产物

**测试**
- 正式 33 passed (架构18 + 单元15)
- Reference 15 passed
- Wheel build success

**审查包**
- M0_001_R2_REVIEW_PACKET.md
- M0_001_R2_REVIEW_TEST_OUTPUT.txt
- AIOS_2.0_M0-001_R2_review.zip 181K SHA256 6e9dafa95060ad1c0aca2ac916e4a1433385e0374294fc397a35c3d8daccebb8
  - 包含 pyproject.toml/.gitignore/README.md/TASK_PROGRESS_R2.md/8根正式文档/src/tests/docs/.github/reference/review packet/test output
  - 排除 .git/.venv/__pycache__/.pytest_cache/build/dist/egg-info/临时db/secret

### 提交
- 待提交 M0-001-R2 harden repository boundary checks


## 2026-09-14 M0-001-R3 最终交付闭环、审查记录入库与云端同步

### 总工程师结论
- M0-001-R2 CODE REVIEW = PASS
- ZIP SHA256 6e9dafa95060ad1c0aca2ac916e4a1433385e0374294fc397a35c3d8daccebb8
- 独立验证: 33/33 + 15/15 PASS, Python 3.13.5, wheel构建+安装, storage绕过/fail-closed攻击测试通过

### 本轮任务
- Git提交冻结、云端同步、审查记录归档、项目状态一致性
- 禁止修改功能代码，功能Manifest必须保持 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803

### 执行

**1. 功能Manifest校验 Before**
- 计算: printf .gitignore pyproject.toml + find src tests reference/src reference/tests -name *.py | sort -u | sha256sum
- 结果: 8ea4a102954f0d3f82bd2bb14a84aefe076b14675af304f9f493c7a619dee803 PASS

**2. 建立正式审查档案目录**
- mkdir -p reviews/M0/evidence
- 创建 reviews/README.md (工程审查档案规则)

**3. 写入第一次总工程师审查记录**
- reviews/M0/M0-001_review_PATCH_REQUIRED_2026-09-14.md (阻塞问题: storage绕过, fail-open, TEST-F命名, MIT license, 状态记录)

**4. 写入本轮R2总工程师复审**
- reviews/M0/M0-001_review_R2_CODE_PASS_DELIVERY_PENDING_2026-09-14.md (CODE PASS / DELIVERY PENDING, ZIP SHA256, 独立验证, 功能Manifest, 裁决)

**5. 整理证据文件**
- 创建 reviews/M0/evidence/
- 移动 M0_001_REVIEW_PACKET.md, M0_001_REVIEW_TEST_OUTPUT.txt, M0_001_R2_REVIEW_PACKET.md, M0_001_R2_REVIEW_TEST_OUTPUT.txt -> reviews/M0/evidence/

**6. README 状态修正**
- 原 “M0-001 验收” [x] 改为 “M0-001 执行程序员施工自检”
- 增加: 总工程师代码复审: CODE PASS (R2 SHA256..., 33/33+15/15, Python 3.13.5, wheel+攻击测试)
- 增加: 总工程师最终项目验收: PENDING DELIVERY CLOSURE
- 增加: 下一任务: M0-002 HOLD

**7. TASK_PROGRESS_R2.md**
- M0-001: CODE PASS / DELIVERY CLOSURE
- M0-001-R2: CODE PASS
- M0-001-R3: IN PROGRESS -> COMPLETED
- M0: 进行中 CODE PASS / DELIVERY CLOSURE
- M0-002: TODO / HOLD
- 禁止自行写 FINAL PASS

**8. 提交R2代码和R3行政记录**
- 分支检查: arena/01a09bc6-fantonghui PASS
- R2已提交 2f5ebe8, R3待提交

**9. GitHub workflow权限**
- 检查远端是否存在 .github/workflows/ci.yml: 不存在 (因权限限制)
- 本地存在 .github/workflows/ci.yml (python 3.12)
- 备份 docs/workflow_backup/ci.yml.txt SHA256 待记录
- 结论: GITHUB_WORKFLOW_PERMISSION_BLOCKED, PYTHON_312_CI_RESULT_UNAVAILABLE, 不认定代码失败

**10. Push云端**
- 待执行

**11. 功能Manifest After**
- 待验证必须仍为 8ea4a102...

**12. 测试**
- 待执行 33 + 15


## 2026-09-14 M0-002 统一错误码、协议级错误结构与机器可恢复异常契约

### 起始
- 冻结 commit 8197c4f, Manifest 8ea4a102..., M0-001 FINAL PASS 已归档
- 分支 arena/01a09bc6-fantonghui clean

### 实现
- 新建 src/aios_core/contracts/errors.py: ErrorResponse
- 新建 src/aios_core/errors.py: AIOSProtocolError
- 修改 src/aios_core/contracts/__init__.py: 导出 ErrorResponse
- 修改 src/aios_core/storage/sqlite_store.py: StoreError 继承 AIOSProtocolError + 结构化 context (empty_commit, world revision, object revision, self ref, reference not found, get_payload not found, operation not found)
- 新建 tests/unit/test_errors.py 24 tests (E01-E20 + message独立性 + 安全序列化 + 其他错误码 + operation not found)
- README 增加 M0-002 错误协议说明
- TASK_PROGRESS 更新为 CODE COMPLETE / WAITING CHIEF REVIEW

### 测试
- 57 passed (33原 + 24新增)
- 15 reference passed
- 对抗验证 A-E 有效

### 未实现
- 未新增 ErrorCode, 未修改字符串值
- 完整幂等检测 -> M0-016
- 完整 Action Runtime -> 后续
- HTTP mapping -> 后续接口层
- 完整 logging -> 后续

### 提交
- 待提交 M0-002 define protocol error contract
- 待提交 M0-002 archive implementation evidence

