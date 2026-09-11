# AIOS Syscall Table V0（系统调用表 v0）—— App 与下三层之间唯一合法入口

- 签发：2026-09-11，最高项目决策者裁决 D2 ｜ 上位依据：宪法 V1.4-r0 §9.1（App 不得自建认知）、`docs/01_CORE_ARCHITECTURE.md` V0.2 §2/§7
- 为什么现在必须冻结：实测主线有 **19 条 `sys.*` 主题散落在 15 个服务里**（各自 `subscribe=["sys.xxx"]`），
  无编号、无版本、无鉴权、无统一错误码，且 SDK 只有 `publish()` 没有 `call()` —— App 今天只能"往里塞事件"，
  **什么都问不到**。一个 OS 的"上为应用服务"若没有这张表，就是空话。
- 冻结效力：表内条目即承诺（改语义须升表版本）；表外的 `sys.*` 视为**内部件**，不得给 App 用，扫到即打回。

## 一、传输与调用约定（不改总线帧协议）

```
请求  {"t":"call", "req_id":"<uuid>", "call":"curve.read", "ver":0, "auth":"<app_token>", "args":{...}}
应答  {"t":"reply","req_id":"<uuid>", "ok":true, "data":{...}}           / {"ok":false,"err":"E_*","detail":"..."}
超时  客户端默认 2.0s（读 `aios_config.json.call_timeout_s`）；超时 = E_TIMEOUT，调用方不得当成功处理
广播  沿用现有 pub/sub（evt.#、world.#）；Call 是请求-应答，Pub 是上报，两者不得混用
```

- 帧仍走现有总线 JSON-lines，`msg` 载荷装 call/reply —— **不新建第二套 IPC**（One AIOS）。
- `err` 闭集：`E_AUTH`（未授权/降级）· `E_SCHEMA`（参数不合表）· `E_NO_SUCH_CALL` · `E_UNAVAILABLE`（服务 down）· `E_TIMEOUT` · `E_QUOTA`（超配额）· `E_VERSION`（表版本不符）。
- `auth` 由 privacyd 的授权状态机校验；未授权 → `E_AUTH`，并在审计留痕（不得静默拒绝）。

## 二、调用表 v0（22 条；`来源`列：现有=已在主线实现，归并=把散落主题收编，新增=待实装）

| # | Call | 归属服务 | 参数（要点） | 返回 | 鉴权 | 来源 |
|---|---|---|---|---|---|---|
| 1 | `obs.attach` | hublinkd | source, modality, payload_ref, observed_at | obs_id, accepted | ✅ 上报授权 | 新增（L1 入口） |
| 2 | `timeline.query` | hublinkd→stated | t_from, t_to, subject_ns, kinds[] | 同轴对象序列（带 timeline_seq） | ✅ 读授权 | 归并 `sys.query.life` |
| 3 | `timeline.subscribe` | hublinkd | kinds[], window | 增量推送句柄 | ✅ | 归并 `evt.#` 订阅 |
| 4 | `dim.register` | 待建 dimensiond | dimension_id, source_event_types[], scoring, baseline_policy | registered / E_QUOTA | ✅ 注册审批 | 新增（宪法 §3.2） |
| 5 | `dim.list` | dimensiond | subject_ns | 维度清单 + 热值 + 状态 | 公开 | 新增 |
| 6 | `curve.read` | dimensiond | dimension_id, window, resolution, zoom | 点列 + delta/direction/slope/volatility | ✅ | 新增（替代 `sys.cmd.rebuild_pyramid` 的读侧） |
| 7 | `evidence.pack` | attentiond | trigger_id 或 t_window | 证据切片引用（obs_id / chg_id，不复制正文） | ✅ | 新增（§4.3 Trigger Window） |
| 8 | `trigger.audit` | attentiond | t_from, t_to, dimension_id | 每次触发为什么响 + 判对没 | ✅ | 新增（§4.3 Trigger Audit） |
| 9 | `world.state.read` | stated | slots[] | 九槽位快照 + state_sha | ✅ | 现有（读快照文件） |
| 10 | `world.change.query` | stated | t_from, t_to, change_type | before/after/evidence_events | ✅ | 现有 |
| 11 | `memory.link` | memoryd | anchor_kw[], subject, context_filter | 候选锚点集（**先召回后筛选**，§8.2.1） | ✅ | 新增 |
| 12 | `memory.summary.read` | memoryd | summary_node_id 或 previous+1 | 节点内容 + sequence | ✅ | 归并 `sys.query.summary` |
| 13 | `cognition.assert` | cognitiond | statement, epistemic, evidence[] | id / 拒绝（INFERRED 冒充 KNOWN） | ✅ 写权限 | 现有 `sys.cognition.assert` |
| 14 | `self.read` | cognitiond | — | AI 自我状态树末态（人格/对用户态度） | 本 AI 会话 | 新增（§5.9 第 1 步） |
| 15 | `model.call` | modelrouterd | task_kind, context_ref, budget | 结构化结果 + 实际所用模型 | ✅ 最小上下文 | 现有 `sys.model.request` |
| 16 | `capability.ask` | abilityd + safetyd + privacyd | capability, args, purpose | grant/deny + audit_id | ✅ | 新增（§10；abilityd 现为空壳） |
| 17 | `action.report` | abilityd→evolutiond | action_id, outcome, metric | accepted | ✅ | 新增（旧验收 J 缺口） |
| 18 | `interact.request` | interactd | level, content, urgency | 送达级别 + 是否被沉默 | ✅ | 现有 `sys.interact.request` |
| 19 | `interact.feedback` | interactd→evolutiond | intervention_id, 接受/忽略/否定 | accepted | ✅ | 现有 `sys.interact.feedback` |
| 20 | `schedule.set` | 待建 scheduled | when, kind, template, ttl | task_id | ✅ | 新增（§5.8 定时自治） |
| 21 | `settings.get` / `settings.set` | 待建 settingsd | key, value, scope（用户/AI/每 App） | 当前值 + 版本 | ✅ 写须确认 | **新增（现在整仓"设置"命中 0）** |
| 22 | `audit.query` / `consent.export` / `consent.revoke` | settingsd + privacyd | subject, t_from, t_to / 全量 | 可读记录 / 导出包 / 撤销回执 | ✅ 用户本人 | 新增（§10 数据主权四项，命中 ≈0） |

**App 侧只允许调这 22 条**；`safety.*` 例外——安全信号走总线 `safety.emergency` 单向旁路，不许被任何鉴权或配额延迟（§4.2-6）。

## 三、设置面（Settings = 用户主权面，OS 必备件，我们此前完全空白）

设置不是"一个页面"，它是**用户对整个 AIOS 的唯一控制权**。契约要点（实现仍冻结，见 §12.5）：

```
维度控制      哪些维度在采集 / 暂停 / 删除（dim.list + dim.register 的反向）
触发控制      各维度阈值敏感度、安静窗口、陪伴窗口（含"AI 自行调节"的许可开关与回滚按钮）
安全例外      安全底线阈值：只显示、不可调低（UI 必须灰掉，且服务端 E_AUTH 兜底）
记忆控制      三树可见 / 可解释（这条推断的依据是什么）/ 可删 / 可导出
AI 人格控制   AI 自我状态可读、态度可纠正、自我更新可否决
隐私与上云    每源授权、最小上下文预览、云端调用审计
配额与保留期  原始观测保留天数、各 App 写入配额（超限 E_QUOTA 并提示，而非静默丢弃）
App 挂载      每个 App 注册了哪些维度、读了哪些证据、贡献了什么
```

每条设置项必须是 `(key, value, version, changed_by, changed_at, rollback_key)` —— 与 `evolutiond` 的 `strategy_versions` 同构，因此可审计、可回滚，不设第二套配置存储。

## 四、实施顺序（不新增缺口，只排先后）

1. SDK 补 `call()/超时/错误码`（**先修管道，不碰任何已验收逻辑**）→ 让 `test_s1_t5` 那类验收从"读文件"升级为"走调用表"
2. 把现有 8 条"归并/现有"项正式登记进表并加鉴权中间层（行为不变，口径先立）
3. 新实装项（1/4/5/6/7/8/11/14/16/20/21/22）随各自迁移任务落地，逐项进 `STATUS.md` 看板
4. 本表升版须同批改 `docs/02` 对应 Runtime 契约，禁止两边各说各话
