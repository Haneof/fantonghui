# M0-003 实现记录

状态：

WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

稳定对象 ID 生成器正式冻结与验证

起始commit：

3430e13

## 实现了什么

- 确认 src/aios_core/contracts/ids.py 已与总工冻结代码语义一致 (SHA256 9972e1d4d7e272019da26d8fb466a9391dea868039e43b5fc9cdaf33073a8993)，未为制造diff重写
- 前缀表冻结19个：obs, ent, rel, dim, dmem, dder, clm, evs, evt, sum, gol, dep, tsk, wak, ses, act, out, exp, tlp
- 新增 tests/unit/test_ids.py 31 tests:
  - ObjectType完整性: set(_PREFIXES.keys()) == set(ObjectType)
  - prefix非空/唯一/冻结映射
  - 格式测试: <prefix>_[0-9a-f]{32} (parametrize 19 types)
  - Operation/Execution ID 格式 op_[0-9a-f]{32}, exec_[0-9a-f]{32} + 1000唯一性
  - 100k唯一性: 100,000个 ENTITY ID, len==len(set)==100k, 碰撞0, 耗时记录
  - Rename稳定性: 未知人物A -> 妈妈，同一 object_id, canonical_name变化
  - Revision稳定性: Event revision1/2 复用 object_id
  - 名称不进入ID: 签名只有 object_type, ID不含 "妈妈"
  - Truth leakage: secret_truth "mother_ground_truth_8848" not in ID, 签名无truth参数
  - UUID版本: parsed.version ==4, 冻结UUID4
- 更新 TASK_PROGRESS_R2.md, README.md, docs/DEV_LOG.md
- 保存测试输出和审查证据

## 哪些没有实现

- 未实现实体合并、Entity resolution、同人识别、relation graph、事件修正传播、UUID索引优化、ID微服务、分布式ID、设备ID、用户账号、安全token、加密ID、M0-004时间模型
- 未自行改成 ULID/UUID7/snowflake/hash(name)/autoincrement/semantic slug
- 未编码人名/日期/地点/成绩/测试真值/隐私语义到ID

## 为什么没有越界

- 本任务只冻结稳定、不透明、无名称依赖的ID生成规则
- 遵守总工亲自代码要求，未重新设计ID算法，继续使用 UUID4 + 短类型前缀 + "_" + 32位hex
- 对象首次创建生成，revision更新复用原 object_id

## 测试

- 正式 103 passed (72 + 31)
- Reference 15 passed
- 100k唯一性证据记录耗时
- 对抗测试 A-E 有效

## 审查证据

- reviews/M0/evidence/M0_003_REVIEW_PACKET.md
- reviews/M0/evidence/M0_003_TEST_OUTPUT.txt

## 下一步

等待总工程师 M0-003 CODE REVIEW，签发 FINAL PASS 后才允许进入 M0-004。
