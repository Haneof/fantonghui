# Lease（注意力租约）Schema · V0.1

> Deep Blue Attention Lease 的 OS 落地。发放者：attentiond。

## 租约对象

```protobuf
message Lease {
  string lease_id    = 1;  // 唯一标识
  string event_id    = 2;  // 触发本次租约的事件
  string holder      = 3;  // 持有服务（cognitiond/decisiond/modelrouterd）
  int32  budget_ms   = 4;  // 算力预算（默认 30000ms）
  int64  issued_at   = 5;
  int64  deadline    = 6;  // issued_at + budget_ms
  bool   cloud_extend = 7; // 是否申请了云端扩展
  enum State { ACTIVE = 0; RELEASED = 1; EXPIRED = 2; }
  State  state       = 8;
}
```

## 规则

1. 一次事件一个租约链；链式申请总额封顶（防雪崩）
2. 超时强制回收；事件标记 UNRESOLVED 进未解决队列
3. 用户一级触发（USER_TRIGGER）免审核直接发租
4. SAFETY 事件免审核 + 预算上浮
5. 统计指标（健康看板）：每日发放数 / 平均时长 / 超时率 / 云端扩展率
6. 省电模式 = 提高非关键事件的发放门槛，绝不冻结 safetyd 与感知

## 充电时段任务（不走租约）

摘要压缩 / 主题树重建 / 成长树对账 / 模型更新 —— 排入充电+空闲窗口的批处理队列。
