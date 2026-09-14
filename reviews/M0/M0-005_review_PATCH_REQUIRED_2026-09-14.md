# M0-005 总工程师代码审查

日期：2026-09-14

状态：

PATCH REQUIRED

审查HEAD：

9c25b4a6b13b169e5a77789cc9b171d7b8b53e67

## 已通过部分

总工程师直接GitHub审查确认：

- WorldObject 11个公共字段
- W01-W14实际存在
- revision >=1
- 首次持久化必须rev1
- revision严格+1
- rev1/rev2历史保留
- rev4跳写失败
- failed transaction不增加World Revision
- failed rev4以后合法rev3可以提交
- object_revisions append-only
- multi-object commit只产生一个World Revision
- Object Revision与World Revision分离
- M0-004时间冻结未被破坏

GitHub Actions也已直接确认：

Python：

3.12.14

正式测试：

160 passed

## 阻塞问题：object_type continuity缺口

当前 SQLiteWorldStore revision验证只检查：

latest revision -> expected_revision = latest + 1

但没有验证：

同一个 object_id 的 object_type 是否保持一致。

因此当前理论上可以出现：

ent_xxx rev1 = ENTITY
ent_xxx rev2 = CLAIM

只要revision连续，这是禁止的。

## 裁决

M0-005：

PATCH REQUIRED

执行：

M0-005-R1

要求：

- 同一object_id第一次成功持久化的object_type成为永久类型身份
- 非法跨类型revision必须 VERSION_CONFLICT
- context: object_id, expected_object_type, actual_object_type
- 验证必须在任何write之前，整个事务原子失败
- 新增 W15/W16/W17
- subject_id本轮明确不冻结
- 不做ID前缀硬校验
- 不修改 base.py/models.py/time.py/ids.py/schema/world revision算法/knowledge cutoff等

M0-006：

HOLD
