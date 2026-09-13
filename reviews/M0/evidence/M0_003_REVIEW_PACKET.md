# M0-003 审查证据包

## 任务
稳定对象 ID 生成器正式冻结与验证

## 起始commit
3430e13 (M0-002 FINAL PASS)

## ids.py
是否与总工程师冻结代码逐字符/语义一致：是，语义一致，未为制造diff重写
SHA256: 9972e1d4d7e272019da26d8fb466a9391dea868039e43b5fc9cdaf33073a8993
路径: src/aios_core/contracts/ids.py

正式冻结代码：
```python
from __future__ import annotations
import uuid
from .enums import ObjectType

_PREFIXES: dict[ObjectType, str] = {
    ObjectType.OBSERVATION: "obs",
    ObjectType.ENTITY: "ent",
    ObjectType.RELATION: "rel",
    ObjectType.DIMENSION_DEFINITION: "dim",
    ObjectType.DIMENSION_MEMBERSHIP: "dmem",
    ObjectType.DIMENSION_DERIVATION: "dder",
    ObjectType.CLAIM: "clm",
    ObjectType.EVIDENCE_SET: "evs",
    ObjectType.EVENT: "evt",
    ObjectType.SUMMARY: "sum",
    ObjectType.GOAL: "gol",
    ObjectType.DEPENDENCY: "dep",
    ObjectType.TASK: "tsk",
    ObjectType.WAKE: "wak",
    ObjectType.SESSION: "ses",
    ObjectType.ACTION: "act",
    ObjectType.OUTCOME: "out",
    ObjectType.OPERATION_EXPERIENCE: "exp",
    ObjectType.TOOL_PROPOSAL: "tlp",
}

def new_object_id(object_type: ObjectType) -> str:
    return f"{_PREFIXES[object_type]}_{uuid.uuid4().hex}"

def new_operation_id() -> str:
    return f"op_{uuid.uuid4().hex}"

def new_execution_id() -> str:
    return f"exec_{uuid.uuid4().hex}"
```

## Prefix覆盖
ObjectType数量: 19
prefix数量: 19
唯一prefix数量: 19
set(_PREFIXES.keys()) == set(ObjectType) PASS
所有prefix非空 PASS
所有prefix唯一 PASS
正式映射冻结验证 PASS

## 格式
object: <prefix>_[0-9a-f]{32} 例如 ent_4fe4... 仅32位小写hex，无名字/日期/空格/斜杠 PASS (parametrize 19 types)
operation: op_[0-9a-f]{32} PASS
execution: exec_[0-9a-f]{32} PASS
连续生成1000次无重复 PASS

## 100k唯一性
生成数: 100,000
唯一数: 100,000
碰撞数: 0
耗时: 约0.3-0.5s (实际测试报告记录)
- 未降低为100/1000/10000
- 未引入缓存/批量服务器/线程池
- 仅随机碰撞回归测试

## Rename稳定性
未知人物A ID: ent_<hex> (revision 1)
妈妈 revision2 ID: 同一 object_id, canonical_name "妈妈"
是否一致: 是，object_id 相同，canonical_name 不同
目的: 身份解释变化，对象身份不变，验证通过

## Revision稳定性
说明: 使用 TestEvent (EVENT) 创建 revision1 和 revision2，复用同一 object_id，revision 1->2，object_id 不变
- revision不是identity 验证通过
- 未修改 Event/Claim字段定义，使用正式 WorldObject 测试子类

## 名称不进入ID
- new_object_id 签名只有 object_type，无 name/canonical_name/label/title/timestamp/subject truth PASS
- 两个不同名字 Entity ID 中不包含 "妈妈" / "未知人物A" PASS
- 防止 ent_mom_001 语义ID

## Truth leakage
secret_truth = "mother_ground_truth_8848"
生成100个Entity ID，确认 secret_truth not in object_id，且明显业务token不进入ID PASS
真正安全保证：ID函数根本不接收truth参数，签名只有 object_type

## UUID版本
version: 4
- 生成 ID 取 suffix, uuid.UUID(hex=suffix).version == 4 PASS
- operation 和 execution 同样验证 version 4 PASS
- 冻结当前是UUID4，未来换UUID7/ULID需正式架构变更

## 正式测试
Python: 3.11.2 (正式基线 >=3.12, PYTHON_312_RUNTIME_UNAVAILABLE)
passed: 103 (72原 + 31新增 test_ids.py)
failed: 0

## Reference测试
passed: 15
failed: 0
reference中 ids.py 作为历史地基参考，未修改

## 对抗测试
A: ENTITY prefix 改成 "mom" -> 前缀冻结测试失败，攻击有效
B: 两个 ObjectType 共用 "ent" -> 唯一性测试失败，攻击有效
C: new_object_id 改成 f"ent_{name}" 语义ID -> 格式/UUID4测试失败，攻击有效
D: UUID4 换成 UUID1 -> UUID version测试失败 (version 1 !=4)，攻击有效
E: revision2重新调用 new_object_id -> rename/revision稳定性测试失败 (id_v1 != id_v2)，攻击有效
攻击后恢复正式代码，未提交破坏

## 未实现事项
- 实体合并算法, Entity resolution, 同人识别, relation graph, 事件修正传播, UUID数据库索引优化, ID服务微服务, 分布式ID中心, 设备ID, 用户账号ID, 安全token, 加密ID, M0-004时间模型
- 本任务只冻结稳定、不透明、无名称依赖的ID生成规则

## Python版本
正式 >=3.12, 本地 3.11.2, PYTHON_312_CI_RESULT_UNAVAILABLE, CI_WORKFLOW_PRESENT

## git status
clean after commit
