# T03 aiosd 总管家（aiosd.py + 两份配置）

- 里程碑：M0 · 负责代理：管家代理 · 状态：🔵进行中 · 依赖：契约冻结

## 目标

AIOS 的"行政总管"：按冻结顺序拉起总线与 15 个服务、看门狗盯梢、被杀的服务 1 秒内复活、健康状态实时落盘。

## 实现方式（规划）

1. 读 `aios_config.json` + `services.json`（契约 §5 §6 §7）
2. 启动：先拉起 bus 子进程（`sys.executable` + 脚本相对路径，cwd=code 根），0.5s 后按 order 依次拉起 15 个服务
3. 监控循环（每 0.2s）：`proc.poll()` 发现退出 → `log` → 距上次拉起 ≥0.5s 立即重启；每分钟重启 >10 次 → state=UNSTABLE（继续重启但打标）
4. 每 0.5s 写 `run/health.json`（契约 §7 格式）；last_hb 从 `run/bus_stats.json` 合并（读不到为 null）
5. Ctrl+C：按启动逆序 terminate 全部子进程，等待退出
6. `services.json` 冻结 15 服务名单与顺序（契约 §6，always_on 标记照抄）
7. 自测（限 own 目录）：`aiosd/selftest/dummy_service.py`（用 SDK 连总线+心跳，3 秒后自杀退出）+ selftest 专用配置；跑 aiosd 观察 dummy 被反复重启、health.json 正确，然后清理全部子进程

## 文件所有权

只许写：`code/aiosd/aiosd.py`、`code/aiosd/selftest/**`、`code/aios_config.json`、`code/services.json`

## 验收标准

- [ ] 启动顺序符合契约 §6
- [ ] kill 服务后 ≤1.5s 复活（A2）
- [ ] health.json 格式与实时性符合契约 §7（A3）
- [ ] 逆序停止干净，无孤儿进程
- [ ] UNSTABLE 打标逻辑正确

## 进度

| 时间 | 事项 | 结果 |
|---|---|---|
| 2026-09-09 01:55 | 任务书下达，代理开工 | 🔵 |

## 验收记录（指挥官填写）

（待代理交付后填写）

## 验收记录（指挥官填写）

### 2026-09-09 02:26 | 最高指挥官
- 验收方式：实跑 M0 验收套件 test_m0.py（A1-A5）+ 任务专项实测
- 结果：**通过 ✅**
- 明细：A3 心跳全绿 2.4s（15/15）· A1 事件互通 0.2s · A2 击杀复活 0.7s（门禁 1.5s）· A4 无契约违规 · A5 日志 16 个
- 执行说明：代理配额故障，指挥官 fallback 亲建（见 TXX_log.md），验收标准未降低
