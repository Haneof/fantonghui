# AIOS 接口契约 v0.1（M0 冻结版）

> 本契约是 M0 并行开发的唯一依据。任何代理**不得单方面修改**；修改须经最高指挥官批准并通知所有依赖方。
> 实现语言（M0）：Python 3.13，仅标准库。协议本身语言中立，Rust 移植（任务 07）按同一契约对齐。

## 1. 代码目录与文件所有权

```
code/
├── bus/aios_busd.py            [总线代理 T01]
├── bus/README.md               [总线代理 T01]
├── aios_sdk/aios_sdk.py        [SDK代理 T02]
├── aios_sdk/README.md          [SDK代理 T02]
├── aiosd/aiosd.py              [管家代理 T03]
├── aiosd/selftest/**           [管家代理 T03]
├── aios_config.json            [管家代理 T03]
├── services.json               [管家代理 T03]
├── services/<name>.py ×15      [空壳代理 T04]
├── simulator/simd.py           [模拟测试代理 T05]
├── simulator/scripts/*.json    [模拟测试代理 T05]
├── tests/test_m0.py            [模拟测试代理 T06]
└── run/                        [运行期产物：aiosd 与总线写入；日志在 run/logs/]
```

## 2. 总线传输协议（JSON Lines over TCP）

- 地址：`127.0.0.1:7800`（读 aios_config.json 的 bus_host / bus_port，缺省即此值）
- 帧：单行 JSON + `\n`，UTF-8，单帧 ≤ 256KB
- **服务 → 总线**：
  - `{"t":"hello","service":"<name>"}`　连接后首帧，必须
  - `{"t":"sub","topics":["evt.#", ...]}`　订阅；`#` 为通配后缀（`evt.#` 匹配一切 `evt.` 开头主题），其余精确匹配
  - `{"t":"pub","topic":"<topic>","msg":{...}}`　发布；msg 至少含 `id / ts / source / type / content`
  - `{"t":"hb","pid":<pid>,"ts":<unix秒>}`　心跳，每 1.0s 一帧（SDK 自动发）
  - `{"t":"bye"}`　优雅退出
- **总线 → 服务**：
  - `{"t":"evt","topic":"...","from":"<service>","msg":{...}}`
  - `{"t":"err","code":"...","text":"..."}`　坏帧/未知帧时返回；总线自身不崩溃
- 主题命名：`evt.<source>.<type>` 为事件；`sys.*` 为系统管理保留（仅显式订阅者可收）
- 转发规则：发布者**不回环**收到自己的消息

## 3. 总线统计文件

每 1.0s 写 `run/bus_stats.json`：
`{"ts":<unix>, "services":{"<name>":{"connected":true,"last_hb":<unix>,"frames_in":<n>}}}`

## 4. SDK（模块 aios_sdk/aios_sdk.py）

```python
class AIOSService:
    def __init__(self, name: str, subscribe: list[str] | None = None,
                 on_event: Callable[[str, str, dict], None] | None = None): ...
    def run(self) -> None: ...        # 阻塞主循环；连接失败重试 3 次(间隔0.3s)后 exit(1)
    def publish(self, topic: str, msg: dict) -> None: ...   # 线程安全；未连接时丢弃并记日志
    def log(self, text: str) -> None: ...   # 追加 run/logs/<name>.log（带时间戳）
# on_event(topic, from_service, msg) 回调；心跳由 SDK 内置线程自动发送，业务代码不操心
```

## 5. aios_config.json

```json
{"bus_host":"127.0.0.1","bus_port":7800,"hb_interval_s":1.0,"hb_timeout_s":3.0,
 "scan_interval_s":0.2,"restart_min_interval_s":0.5,"max_restarts_per_min":10}
```

## 6. services.json（aiosd 的输入）

```json
{"bus":{"script":"bus/aios_busd.py"},
 "services":[{"name":"hublinkd","script":"services/hublinkd.py","always_on":true,"order":1},
             {"name":"stated","script":"services/stated.py","always_on":false,"order":2}]}
```
**启动顺序（冻结）**：bus → hublinkd(1) → stated(2) → safetyd(3) → privacyd(4) → modemgrd(5) → attentiond(6) → perceptiond(7) → entityd(8) → memoryd(9) → cognitiond(10) → decisiond(11) → abilityd(12) → interactd(13) → evolutiond(14) → modelrouterd(15)
always_on=true：hublinkd、safetyd、privacyd（其余 false）

## 7. aiosd 行为规范

- 启动：先拉起 bus 子进程，0.5s 后按 order 依次拉起服务（python = `sys.executable`，cwd = code 根目录）
- 监控：每 `scan_interval_s` 对每个子进程 `poll()`；发现退出 → 记日志 → 距上次拉起 ≥ `restart_min_interval_s` 则立即重启；每分钟重启次数 > `max_restarts_per_min` → 该服务 state=UNSTABLE（继续重启但打标）
- 每 0.5s 写 `run/health.json`：
  `{"ts":..,"bus":{"pid":..,"state":"up"},"services":{"<name>":{"pid":..,"state":"up|down|unstable","restarts":N,"last_hb":<unix|null>}}}`
  （last_hb 从 run/bus_stats.json 合并，取不到则 null）
- Ctrl+C / terminate：按启动逆序停止全部子进程

## 8. M0 验收标准（冻结，对应 ROADMAP M0 门禁）

- **A1 事件互通**：test_m0.py 以服务名 `testdriver` 发布 `sys.test.ping` 后 5s 内收到 `evt.hub.echo`（hublinkd→perceptiond 回声链路）
- **A2 击杀复活**：`taskkill /F` 任意服务 pid 后 ≤1.5s，health.json 显示该服务重启（pid 变化、state=up）
- **A3 心跳全绿**：health.json 中 bus + 15 服务全部 state=up，且 last_hb 距今 < 3s
- **A4 契约一致**：服务间无直连，全部通信经总线（代码审查项）
- **A5 日志齐全**：run/logs/ 下 ≥16 个非空日志文件

## 9. 里程碑门禁

M0 = 任务 01-08 全部验收通过。M1 及以后在此门禁通过后解锁派单。
