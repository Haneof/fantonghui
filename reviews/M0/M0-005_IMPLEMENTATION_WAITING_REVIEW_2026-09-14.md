# M0-005 实现记录

状态：

R1 PATCH COMPLETE / WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

WorldObject 公共字段与 Append-Only Revision 规则正式冻结 + R1 object_type identity

起始commit：

9c25b4a6b13b169e5a77789cc9b171d7b8b53e67 (M0-005基线 160 passed, Python 3.12.14 CI PASS)

## 已通过部分 (总工直接GitHub审查)

- WorldObject 11公共字段
- W01-W14存在
- revision >=1, 首次必须rev1, 严格+1, rev1/rev2历史保留, rev4跳写失败, failed transaction不增加World Revision, failed后rev3可提交, append-only, multi-object单World Revision, Object vs World分离, M0-004时间冻结未破坏
- GitHub Actions Python 3.12.14 160 passed, 旧PYTHON_312_CI_RESULT_UNAVAILABLE已失效，应改为PYTHON_312_CI_PASS

## R1 唯一生产代码缺口

- 同一object_id的object_type是否保持一致未验证，理论上可出现 ent_xxx rev1 ENTITY rev2 CLAIM

## R1 正式冻结 object_type identity

- 同一object_id第一次成功持久化的object_type成为永久类型身份
- 合法: ENTITY->ENTITY, 非法: ENTITY->CLAIM, CLAIM->EVENT
- subject_id本轮明确不冻结
- 不做ID前缀硬校验

## 实现

- 文件: src/aios_core/storage/sqlite_store.py 最小修改
- 新增 _latest_object_type helper: SELECT object_type WHERE object_id ORDER BY revision DESC LIMIT 1
- 在 pre-write validation阶段 revision检查通过后，若 latest is not None，比较 existing_object_type vs obj.object_type.value，不一致 => VERSION_CONFLICT context object_id, expected_object_type, actual_object_type
- 使用VERSION_CONFLICT，不新增ErrorCode
- 验证在任何write之前，失败整个事务原子

## 新增测试

- DummyClaim class
- W15: ENTITY rev1 -> CLAIM rev2 same id => VERSION_CONFLICT expected ENTITY actual CLAIM
- W16: world rev1, commit包含非法CLAIM rev2 + 全新ENTITY rev1 => 整个commit失败, world仍1, 原latest仍rev1 ENTITY, 非法rev2不存在, 新ENTITY不存在, world_commits无新增
- W17: W16失败后合法ENTITY rev2 => 成功 world 1->2 latest rev2 ENTITY, 检查DB rev1 ENTITY rev2 ENTITY无CLAIM

## 测试

- 本地 163 passed (160+3), reference 15 passed
- GitHub Actions R1新HEAD需总工直接核验，本地记录 CI_PENDING_CHIEF_VERIFICATION

## 未修改

- base.py, models.py, time.py, ids.py 未修改 (除store)
- SQLite schema, world revision算法, knowledge cutoff, Wake DST, reference, idempotency, ErrorCode 未修改

## 证据

- reviews/M0/M0-005_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_005_REVIEW_PACKET.md (含R1)
- reviews/M0/evidence/M0_005_R1_TEST_OUTPUT.txt 163+15
- tests/unit/test_world_object_revision.py (W15-W17)

## 下一步

等待总工程师 M0-005 FINAL REVIEW，签发 FINAL PASS 后才允许进入 M0-006。
