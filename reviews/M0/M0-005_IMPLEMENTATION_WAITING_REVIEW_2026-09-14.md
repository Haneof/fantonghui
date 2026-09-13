# M0-005 实现记录

状态：

WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

WorldObject 公共字段与 Append-Only Revision 规则正式冻结

起始commit：

3678ab8cebe1769e0b8170e34780ef51d4bcc23c (M0-004 FINAL PASS)
38058fa (M0-004 archive final pass and authorize M0-005)

## 实现了什么

1. 归档 M0-004 FINAL PASS: reviews/M0/M0-004_final_PASS_2026-09-14.md, 更新 TASK_PROGRESS_R2.md M0-004 FINAL PASS M0-005 IN PROGRESS

2. 检查 WorldObject正式公共字段: src/aios_core/contracts/base.py 已包含 object_id, object_type, subject_id, revision, occurred, learned_at, recorded_at, source_refs, created_by, status, metadata 11项，完全符合，无需重写

3. 检查 Revision正式含义: revision是同一个长期object_id的版本号，1->2->3严格+1，禁止跳版本、禁止覆盖、禁止UPDATE旧payload，修改对象正确行为是写入新revision

4. 检查 object_id与revision职责: object_id对象身份，revision该身份版本，例如 Entity rev1 未知人物A rev2 妈妈 object_id相同 revision 1->2 旧rev1继续存在，禁止为改名重新生成object_id，M0-003稳定ID继续有效

5. 检查 World Revision与Object Revision分离: Object Revision单个对象版本，World Revision一次成功世界事务全局版本，一个commit写两个对象只产生一个World Revision，Object A rev5不意味着World Revision=5

6. 检查当前存储Revision算法: src/aios_core/storage/sqlite_store.py 已有 _latest_revision MAX(revision), expected_revision = 1 if latest None else latest+1, 若 obj.revision != expected_revision => VERSION_CONFLICT with object_id, expected_revision, actual_revision，符合M0-005冻结算法，无需重写

7. 检查首次持久化必须revision=1: Pydantic只负责 revision>=1, 真正首次必须是1由SQLiteWorldStore负责，新object_id直接提交rev2模型可构造但store拒绝 VERSION_CONFLICT，分层设计，不把DB历史塞进Pydantic

8. 检查 Append-only正式规则: object_revisions真相表 INSERT新revision，禁止UPDATE/DELETE/INSERT OR REPLACE，允许未来索引表缓存表更新自身，但真相版本必须追加

9. 不新增未授权身份规则: 同一object_id跨revision时 object_type/subject_id是否必须相同，任务书未明确，本轮禁止擅自新增，认为当前合理，无ARCHITECTURE_PROPOSAL

10. 新建正式测试文件 tests/unit/test_world_object_revision.py 14 tests:
   - W01 公共字段集合 11项
   - W02 所有持久模型继承WorldObject 19个
   - W03 revision下限 0/-1拒绝 1合法
   - W04 新对象不能从rev2开始 VERSION_CONFLICT expected 1 actual 2 world_revision仍0
   - W05 写入rev1 未知人物A world_revision 1
   - W06 写入rev2 妈妈 world_revision 2 latest 妈妈
   - W07 rev1仍可精确读取 未知人物A / rev2 妈妈 / latest 妈妈
   - W08 直接跳rev4必须失败 VERSION_CONFLICT expected 3 actual 4
   - W09 失败事务原子回滚 world_revision仍2 数据库仍[1,2]
   - W10 失败后rev3仍可正常写入 world_revision 3
   - W11 直接验证append-only数据库行 2行 rev1旧payload仍存在
   - W12 World Revision vs Object Revision分离 multi-object commit world_revision=1 两对象world_revision都=1
   - W13 下一次修改单个对象 world 1->2 A rev2 B仍rev1 证明分离
   - W14 Append-only源码证据 grep UPDATE/REPLACE无结果

11. M0-004冻结保护: time.py SHA256 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 保持不变，SQLite时间canonical逻辑未变，Wake DST修复未变

12. 对抗验证 A-E 有效，恢复正式代码

13. 正式测试 160 passed (146+14), reference 15 passed

14. 更新 TASK_PROGRESS_R2.md M0-005 CODE COMPLETE WAITING CHIEF REVIEW

## 哪些没有实现

- 未新增 object_type/subject_id immutable约束，等待总工裁决
- 未实现 ObjectRef/SourceRef新验证规则、引用knowledge cutoff、同事务互相引用新规则、历史ref导航 (属于M0-006)
- 未修改各业务对象契约 Observation/Entity业务字段/Relation/Dimension/Claim/EvidenceSet/EventAnchor/Summary/Goal/Dependency/Task/Wake/Session/Action/Outcome/OperationExperience/ToolProposal，除非发现根本未继承WorldObject (未发现)
- 未提前做M0-006

## 为什么没有越界

- 只做M0-005公共字段+Revision+Append-only+World vs Object Revision分离冻结
- 生产逻辑已符合，无需重写，仅新增测试
- 遵守总工亲自代码要求

## 测试

- 正式 160 passed
- Reference 15 passed
- 对抗 A-E 有效

## 审查证据

- reviews/M0/M0-004_final_PASS_2026-09-14.md
- reviews/M0/evidence/M0_005_REVIEW_PACKET.md
- reviews/M0/evidence/M0_005_TEST_OUTPUT.txt
- tests/unit/test_world_object_revision.py

## 下一步

等待总工程师 M0-005 CODE REVIEW，签发 FINAL PASS 后才允许进入 M0-006。
