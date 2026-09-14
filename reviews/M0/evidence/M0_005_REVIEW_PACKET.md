# M0-005 审查证据包

## 起始commit
3678ab8cebe1769e0b8170e34780ef51d4bcc23c (M0-004 FINAL PASS)
经过 M0-004 archive final pass commit 38058fa 后开始 M0-005

## WorldObject公共字段
WorldObject.model_fields 包含 11项冻结字段：
- object_id: 非空字符串
- object_type: ObjectType
- subject_id: 非空字符串
- revision: int >=1 default 1
- occurred: TemporalExtent default unknown_time
- learned_at: 必须显式提供 must aware
- recorded_at: default utc_now() must aware, as_utc(recorded_at) >= as_utc(learned_at) (DST safe)
- source_refs: list[SourceRef]
- created_by: 非空字符串
- status: 通用字符串状态字段
- metadata: 通用metadata字段

不得删除，不得由子模型重造同义字段。当前 base.py 完全符合，无需重写。

## Durable models数量
通过 reflection 在 src/aios_core/contracts/models.py 中找到所有 WorldObject subclass：
- Observation, Entity, Relation, DimensionDefinition, DimensionMembership, DimensionDerivation, Claim, EvidenceSet, EventAnchor, Summary, Goal, Dependency, Task, Wake, Session, Action, Outcome, OperationExperience, ToolProposal
- 共 19个，全部继承WorldObject，全部包含11个公共字段
- 辅助结构 EvidenceSelector, EvidenceCoverage 不是durable world object，不要求继承

## Revision起点规则
- Pydantic层: revision >=1, default 1, 0和-1拒绝 (W03)
- Store层: 首次持久化必须revision=1
  - _latest_revision: SELECT MAX(revision) FROM object_revisions WHERE object_id=?
  - expected_revision = 1 if latest is None else latest+1
  - 若 obj.revision != expected_revision => VERSION_CONFLICT with context object_id, expected_revision, actual_revision
- 新object_id直接提交 revision=2 => 模型可构造但 store.commit 拒绝 VERSION_CONFLICT expected=1 actual=2 (W04)
- 分层设计：不把数据库历史状态塞进Pydantic验证器

## Revision +1规则
- 必须严格+1，禁止 rev1->rev3, rev2->rev4
- 尝试 rev4 当已有 rev1, rev2 => expected=3 actual=4 VERSION_CONFLICT (W08)
- 禁止覆盖原revision，禁止UPDATE旧payload，禁止DELETE旧revision作为普通修订，禁止INSERT OR REPLACE
- 修改对象正确行为是写入新revision

## Append-only证明
- object_revisions 真相对象表，INSERT新revision
- 动态测试:
  - W05 rev1 写入 未知人物A world_revision 1
  - W06 rev2 写入 妈妈 world_revision 2, latest 妈妈
  - W07 rev1仍可精确读取 未知人物A, rev2 妈妈, latest 妈妈，证明修订没有覆盖历史
  - W11 直接SQL SELECT object_id, revision, payload_json WHERE object_id=? ORDER BY revision 必须得到两行 rev1=未知人物A rev2=妈妈
  - W09 rev4失败后 current_world_revision仍2, latest仍rev2, rev4不存在, object_revisions仍只有rev1,rev2, 无半写
  - W10 失败后rev3仍可正常写入 world_revision 3, latest rev3
- 源码证据: grep -RniE "UPDATE\s+object_revisions|REPLACE\s+INTO\s+object_revisions|INSERT\s+OR\s+REPLACE\s+INTO\s+object_revisions" src/aios_core => 无结果 (W14)
- 真正保证来自动态rev1/rev2历史回放测试，而非仅grep

## Rev1/Rev2/Rev4/Rev3结果
- W04: 新对象rev2直接创建 => VERSION_CONFLICT expected 1 actual 2, world_revision仍0, 失败事务不得消耗World Revision
- W05: rev1 未知人物A commit成功 world_revision 1, 读取latest rev1
- W06: rev2 妈妈 expected_world_revision 1 成功 world_revision 2, latest 妈妈
- W07: rev1仍可精确读取 未知人物A, rev2 妈妈, latest 妈妈
- W08: rev4 gap => VERSION_CONFLICT expected 3 actual 4
- W09: rev4失败后 world_revision仍2, 数据库revision集合 [1,2], 无半写
- W10: 失败后rev3正常写入 world_revision 3, latest rev3
- W11: 数据库row 2行 rev1旧payload仍存在 未知人物A
- 历史回放验收: 现在latest是妈妈，但revision=1仍是未知人物A，必须检查旧payload内容而非仅row count

## Failed transaction rollback
- W09 验证 current_world_revision仍2, latest仍rev2, rev4不存在, object_revisions仍只有rev1,rev2
- 原子回滚由 SQLiteWorldStore commit中 BEGIN IMMEDIATE + try/except rollback 实现

## World Revision vs Object Revision
- W12: 空store, 一个commit同时提交 Entity A rev1 + Entity B rev1 expected_world_revision 0 => CommitResult.world_revision=1, current_world_revision=1, 两个object revision都=1, object_revisions中两行world_revision都=1, 证明一次世界事务只产生一个全局world revision, 不能因为写两个对象 world revision +2
- W13: 只修改 Entity A rev2 第二次commit => World Revision 1->2, Entity A rev2, Entity B仍rev1, 再次证明 World Revision != Object Revision, Object A revision 5 并不意味着 World Revision=5
- 测试明确证明二者独立

## Object_id与Revision职责
- object_id: 对象身份, M0-003稳定ID规则继续有效, 禁止为修改名称重新生成新object_id
- revision: 该身份在某个版本上的内容
- 例如 Entity rev1 canonical_name=未知人物A, rev2 妈妈, object_id相同, revision 1->2, 旧rev1继续存在

## 不新增未授权身份规则
- 同一object_id跨revision时 object_type是否必须永久相同, subject_id是否必须永久相同, 任务书当前没有明确规定
- 本轮禁止擅自新增这两个生产约束
- 未发现必要性，未实现，仅记录本段说明，等待总工单独裁决
- 无ARCHITECTURE_PROPOSAL，认为当前设计合理

## 对抗验证
- A 把首次revision expected从1改成允许2 => W04失败 (新对象rev2应被拒绝但被允许) 攻击有效
- B 把 expected_revision = latest+1 改成允许 >= latest+1 => W08失败 (允许跳版本) 攻击有效
- C 模拟将rev2写入时覆盖rev1 payload (UPDATE) => W07/W11失败 (rev1旧payload丢失) 攻击有效
- D revision失败后错误增加world_revision => W09失败 (world_revision错误增加) 攻击有效
- E 一次commit两个对象时每个对象都增加一次world revision (next = current + len(objects)) => W12失败 (world_revision应1得2) 攻击有效
- 攻击后恢复正式代码，未提交破坏版本

## 正式pytest
- Python 3.11.2 (formal >=3.12, PYTHON_312_CI_RESULT_UNAVAILABLE)
- 160 passed (146 M0-004R2 +14 M0-005)
- Reference 15 passed

## time.py SHA
0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 必须保持不变，本轮未修改

## Python版本
- 正式最低 >=3.12
- 本地 3.11.2
- 报告 PYTHON_312_CI_RESULT_UNAVAILABLE，待CI补

## 未解决问题
NONE
- Wake DST已在R2修复，本轮扫描无剩余直接wall-clock比较
- object_type/subject_id immutable 未新增，等待总工裁决，但当前无必要

## 源码grep
- UPDATE object_revisions / REPLACE INTO object_revisions / INSERT OR REPLACE INTO object_revisions 在 src/aios_core 中无结果

## Git
- 起始 3678ab8cebe1769e0b8170e34780ef51d4bcc23c
- 经过 38058fa M0-004 archive final pass
- 本轮生产逻辑 NO CHANGE (base.py, models.py, time.py, sqlite_store.py 已符合M0-005冻结算法)
- 新增测试 tests/unit/test_world_object_revision.py 14 tests

---

## R1 PATCH 2026-09-14 object_type continuity

### 背景
- 总工程师直接GitHub审查，当前真实基线 9c25b4a6b13b169e5a77789cc9b171d7b8b53e67
- W01-W14已验证存在，Python3.12 CI 160 PASS
- 旧记录 PYTHON_312_CI_RESULT_UNAVAILABLE 对于当前HEAD已失效，正式状态应改为 PYTHON_312_CI_PASS
- 发现唯一生产代码缺口：同一object_id跨revision时 object_type未验证，理论上可出现 ent_xxx rev1 ENTITY rev2 CLAIM

### 正式冻结 object_type identity
- 同一object_id第一次成功持久化的object_type成为永久类型身份
- 合法: ent_xxx rev1 ENTITY rev2 ENTITY rev3 ENTITY
- 非法: ent_xxx rev1 ENTITY rev2 CLAIM, clm_xxx rev1 CLAIM rev2 EVENT
- 原因: object_id长期身份，object_type核心协议，M0-003已冻结按ObjectType生成前缀的稳定不透明ID，稳定对象不能变另一类
- subject_id本轮明确不冻结：未来可能主体误归属认知修正，M0-005不提前限制

### Store最小修改
- 文件: src/aios_core/storage/sqlite_store.py
- 新增 helper _latest_object_type(conn, object_id) -> str | None: SELECT object_type FROM object_revisions WHERE object_id=? ORDER BY revision DESC LIMIT 1
- 在 Validate revision monotonicity before any write 阶段，revision检查通过后，若 latest is not None，获取历史object_type，若 existing != obj.object_type.value => raise StoreError VERSION_CONFLICT "object type cannot change across revisions" context object_id, expected_object_type, actual_object_type
- 使用 VERSION_CONFLICT，不新增ErrorCode，属于同一object_id revision lineage版本身份冲突
- 验证必须在任何write之前 (INSERT world_commits, INSERT object_revisions, world_meta, operation, idempotency) 之前，失败整个事务不产生新世界状态

### 新增测试
- DummyClaim class: object_type CLAIM content test
- W15: 空store, obj_id ENTITY, rev1 ENTITY成功, rev2 CLAIM same obj_id => VERSION_CONFLICT expected ENTITY actual CLAIM
- W16: world rev1 ENTITY rev1, 准备commit同时包含非法CLAIM rev2 + 全新合法ENTITY rev1 => 整个commit失败, current_world_revision==1, 原对象latest仍rev1 ENTITY, 非法CLAIM不存在, 新ENTITY也不存在, world_commits无新增, 证明整个世界事务原子失败
- W17: W16失败后提交同一原object_id rev2 ENTITY => 成功 world 1->2 latest rev2 ENTITY, 证明失败未消耗revision未污染identity
- W17后直接检查DB: SELECT revision, object_type WHERE object_id=? ORDER BY revision => rev1 ENTITY rev2 ENTITY 无CLAIM
- 不做ID前缀硬校验，禁止新增 object_id.startswith(prefix)等，M0-003冻结生成器输出，M0-005冻结已存在object_id lineage连续性

### 不修改
- base.py, models.py, time.py, ids.py 原则上不得修改，本轮仅修改 sqlite_store.py
- SQLite schema, world revision算法, knowledge cutoff, time canonicalization, Wake DST, reference validation, idempotency, ErrorCode集合 禁止修改

### 对抗验证 R1
- A 删除object_type continuity check => W15失败 (ENTITY->CLAIM被允许)
- B 错误码改成 INVALID_ARGUMENT => W15失败 (code不匹配)
- C 类型冲突后仍增加world revision => W16失败 (world应1得2)
- D 类型冲突时允许同commit另一合法对象写入 => W16失败 (新ENTITY应不存在但存在)
- E 类型冲突失败后让合法ENTITY rev2无法提交 => W17失败
- 全部恢复后正式测试

### 正式测试 R1
- 本地 Python 3.11.2, 163 passed (160 + W15-W17)
- Reference 15 passed
- GitHub Actions Python 3.12.14 预期 163 passed (总工直接GitHub核验新HEAD CI，不能拿旧HEAD替代)

### CI状态
- 当前HEAD 9c25b4a CI: Python 3.12.14 160 PASS (总工直接确认)
- R1新HEAD CI: 需push后总工直接GitHub核验，本地记录 CI_PENDING_CHIEF_VERIFICATION 或实际看到的PASS

### SHA
- time.py: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 保持不变
- sqlite_store.py: 新增 _latest_object_type + object_type check，最小修改
