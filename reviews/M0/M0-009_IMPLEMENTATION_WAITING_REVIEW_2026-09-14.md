# M0-009 实现记录

状态：WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：EvidenceSet（一等证据集合）契约冻结

起始commit：65f1dd2868dfa638b9090e6dea997edd63dc3e66 (M0-008 FINAL PASS 211 passed)

## 生产修改

src/aios_core/contracts/models.py 仅修改EvidenceSet validator：

- 保持已有 empty check
- 新增：member_refs/support_refs/counter_refs/context_refs any revision None => ValueError "<field> requires pinned ObjectRef revisions"
- 新增：selector.dimension_refs any revision None => ValueError "selector.dimension_refs requires pinned ObjectRef revisions"
- 新增：knowledge_window.knowledge_cutoff <= learned_at per as_utc else ValueError
- 原因：历史证据不能随target latest变化，EvidenceSet不是导航对象，必须pinned；selector维度定义必须稳定；系统不能声称快照允许知道未来资料
- 其他src预期NO CHANGE，实际仅models.py变更，符合允许范围

## 测试文件 tests/unit/test_evidence_set.py 19 tests E01-E19

- E01 schema exact types：EvidenceSet WorldObject subclass, purpose str, knowledge_window KnowledgeWindow, member/support/counter/context list[ObjectRef], selector EvidenceSelector|None, selection_method str, aggregation_method str|None, aggregation_version str|None, coverage EvidenceCoverage, stale bool, EvidenceSelector time_range TemporalExtent dimension_refs list[ObjectRef] filters dict algorithm_version str, EvidenceCoverage expected int|None observed int|None ratio float|None missing list[str]
- E02 empty reject：member [] selector None => ValidationError
- E03 explicit members：A@1 B@1 commit round-trip
- E04 member floating reject：revision None => ValidationError
- E05 support/counter/context floating reject
- E06 selector dimension floating reject：dimension_refs revision None => ValidationError, revision 1合法
- E07 selector-only合法：selector存在 member []合法
- E08 materialization：rev1 selector [] + rev2 same selector + members A@1 B@1, rev1仍[] rev2有成员，证明可材料化
- E09 fixed interval one week later：time_range 2026-09-01->09-14 cutoff 09-14 23:59 保存，写入09-21新Observation，旧revision仍原区间，新Observation不自动出现
- E10 dynamic time替代拒绝：time_range "now-14d" ValidationError, extra forbid
- E11 separation：S/C/X support/counter/context严格分离
- E12 coverage/missingness：expected 10 observed 7 ratio 0.7 missing [...] round-trip
- E13 cutoff不能未来：learned 10:00 cutoff 11:00 => ValidationError, 10:00合法 09:00合法 as_utc
- E14 world_revision round-trip：cutoff T world_revision 7保存仍7
- E15 pinned history不漂移：target rev1 old, EvidenceSet member @1, target rev2 new, member仍rev1读取old
- E16 stale/rebuild capability：rev1 [A] stale False, rev2 [A] stale True, rev3 [A,B] stale False, revision能力
- E17 coverage bounds：ratio 0.0/0.5/1.0合法 -0.01/1.01非法，expected/observed负数拒绝，不增加observed<=expected
- E18 object_type固定：EVENT => ValidationError
- E19 ref pin exact annotation：member/support/counter/context list[ObjectRef]

## 保护

- M0-008 Claim冻结
- M0-006 ObjectRef通用语义保留，仅EvidenceSet更严格
- M0-005 append-only等
- 不提前做M1-006 evidence service, M3-002 stale自动, 不新增模型调用

## 对抗

A empty validator删除 E02 FAIL, B member floating允许 E04/E15 FAIL, C support/counter/context floating E05 FAIL, D cutoff未来 E13 FAIL, E old interval重算 E09 FAIL, F 合并列表 E11 FAIL, G rev2覆盖rev1 E08/E16 FAIL，恢复有效

## 测试

230 passed (211+19), 0 failed, Reference 15 passed, Production diff仅models.py符合允许

## 证据

- src/aios_core/contracts/models.py 修改validator
- tests/unit/test_evidence_set.py 19 tests
- reviews/M0/M0-008_final_PASS_2026-09-14.md
- reviews/M0/evidence/M0_009_REVIEW_PACKET.md
- reviews/M0/evidence/M0_009_TEST_OUTPUT.txt 230+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-009 CODE REVIEW，禁止M0-010
