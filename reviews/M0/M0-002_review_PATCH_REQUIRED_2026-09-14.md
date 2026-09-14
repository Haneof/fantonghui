# M0-002 总工程师代码审查

日期：2026-09-14

状态：

PATCH REQUIRED

审查对象：

结束commit：

b59cc719c0af8e0c40a7480179b8e94240198be9

## 已通过部分

总工程师确认：

- 10个 ErrorCode 保持冻结集合
- 未擅自增加新的协议错误码
- ErrorResponse 使用 code/message/context
- StoreError 已继承 AIOSProtocolError
- Store version/not-found/reference错误开始携带结构化context
- OUTCOME_UNKNOWN 与普通失败保持独立
- message 不再作为业务分支依据
- ErrorResponse 不自动序列化 traceback / __cause__
- reference目录未修改

## 阻塞问题1：AIOSProtocolError构造时没有验证context

当前：

self._context = context

类型标注：

dict[str, JsonValue]

不会提供Python运行时保证。

因此：

AIOSProtocolError(
    ErrorCode.INVALID_ARGUMENT,
    "bad request",
    context={"bad": object()},
)

当前可以先成功创建，
直到 to_response() 时才出现 ValidationError。

协议错误必须在构造成功时就已经满足协议约束。

## 阻塞问题2：context内部状态可被外部污染

当前异常直接保存调用者提供的dict，
并通过 .context 返回相同可变对象。

调用者可以：

- 修改原始context dict
- 修改 err.context

从而让一个已经创建成功的协议错误在未来变成不可序列化状态。

这违反稳定协议对象原则。

## 阻塞问题3：严格JSON数值

协议context必须使用标准JSON值。

NaN
Infinity
-Infinity

不是标准JSON数值。

ErrorResponse需要显式拒绝非有限浮点值，
不能依赖不同JSON序列化器的默认行为。

## 测试覆盖补强

需要增加：

- AIOSProtocolError构造即验证context
- 原context后续修改不能污染异常
- err.context修改不能污染异常内部状态
- NaN/Infinity拒绝
- empty commit context
- duplicate revision context
- self-current reference context

## 裁决

M0-002：

PATCH REQUIRED

执行：

M0-002-R1

M0-003：

HOLD
