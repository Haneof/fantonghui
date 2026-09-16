# AIOS Core — as-built 审查与验收报告：M1-001R 端侧多模态轻量摄入与声纹 180 天淘汰

- **审查人角色**：1号开发 Agent（领单）＋ 独立首席架构师（验收口径）
- **日期**：2026-09-16　**分支**：`arena/01a0a631-fantonghui`（本会话固定分支，见 §8 说明）
- **工单**：`governance/dispatches/TASK_DISPATCH_AGENT_1_M1_001R.md`
- **被测对象**：`src/aios_core/ingest/multimodal_edge.py`
  - 审查前 `subject_sha256 = c8871fc3bea19d36…`（555 行，由前一轮 1号战队落地）
  - 本轮修复后 `subject_sha256 = dbc841465da0d8e1…`
- **证据工件**（全部入 `SHA256SUMS`）：
  - 探针 `reviews/architecture/evidence/verify_landed_m1_001r_edge.py`（v1.2.0，`script_sha256=5ad1d460…`）
  - 修复后 `verify_landed_m1_001r_edge_result.json` / `.log`（**10/10 门通过**）
  - 修复前 `verify_landed_m1_001r_edge_PREFIX_historical_result.json` / `.log`（已标 `HISTORICAL`，缺陷证据）
  - 单测 `tests/unit/test_m1_001r_edge_cleaner.py`（22 → **41 个用例**）；全仓 `650 → 669 passed`
- **新增 gap 号**：`V3G-009`（已修）、`V3G-010`（已修）、`V3G-011`（待治理裁决）

---

## 0. 裁定

**交付成立**。三条最高违宪红线**全部可执行地满足**，且实现质量显著高于工单骨架。
但审查发现 **2 个真实缺陷（均已在本提交修复并补测）** 与 **1 个必须由治理方裁决的口径分歧**：

| # | 结论 | 严重度 | 状态 |
|---|---|---|---|
| 红线 1 | 画质 < 0.4 丢弃、**0.4 本身保留**（与工单字面口径一致）；非法画质值 fail-closed 抛错而非静默当低质 | — | ✅ 达标 |
| 红线 2 | 输出模型**不可能**持有字节（`Literal[False]` + 校验器 + `extra="forbid"` + `frozen`）；可变帧在**成功/丢弃/非法**三条路径上都被真擦除 | — | ✅ 达标 |
| 红线 3 | 未绑定实体的陌生声纹 > 180 天 **100% 打墓碑**（10,000/10,000）；已绑定实体 **0 误伤**（0/2,000）；输入不被就地改写 | — | ✅ 达标 |
| **V3G-009** | `RawByteSink` 把"仅释放引用"计入"已销毁字节" ⇒ **隐私计量撒谎** | P1 | ✅ **已修 + 已补测** |
| **V3G-010** | `bind_nearest_entities` 在每次比较里重复解析十六进制 ⇒ 100 万次比较 748.6 ms | P2 | ✅ **已修（3.66×）+ 已补测** |
| **V3G-011** | "180 天"存在**两套口径**（Manager 严格 `>`，StateMachine 包含 `>=`），边界日给出相反答案 | P1 | ⚠️ **待治理裁决**（不擅自统一） |

---

## 1. 实测总表（10 道门，全部绑定 profile）

探针 profile：`frame_clean_p95_ms=50.0`（工单 §1.2"端侧 50ms 初筛"）、帧缓冲 2 MB、`lsh_feature_hash_p95_ms=20.0`、
`bind 2,000 profiles × 500 enrollments ≤ 500 ms`、`sweep/advance 100k profiles ≤ 5/10 s`、`tombstone_recall=1.0`、`bound_false_positive=0`。

| 门 | 断言 | 实测 | 判定 |
|---|---|---|---|
| **E1** | 画质门边界：0.3999 丢 / **0.4 收** / 0.0 丢 | 三条全对，阈值 `QUALITY_THRESHOLD=0.4` | ✅ |
| **E2** | 输出无字节载荷：**按注解类型**判定（不看字段名） | 6 个字段无一为 bytes/bytearray/memoryview；`raw_image_bytes_retained=True` **构造即抛错**；JSON 序列化仅 242 字节 | ✅ |
| **E3** | 可变缓冲在**成功/丢弃/非法**三条路径都被擦零；可写 memoryview 同样擦到底层存储 | 4/4 全零 | ✅ |
| **E4** | sink 计量必须区分「已擦除」与「仅释放引用」 | 修复前 `zeroed_*`/`released_*` **不存在**；修复后 1,000,000 zeroed + 1,000,000 released = 2,000,000 purged | ✅（修复后） |
| **E5** | 单帧清洗（含 2 MB 擦除）p95 ≤ 50 ms | **0.173 ms**（p50 0.099；丢弃路径 0.134）⇒ **289× 余量** | ✅ |
| **E6** | 红线 3：陌生声纹召回 100%、已绑定误伤 0、新鲜未绑定误伤 0、输入不被改写 | 10,000/10,000；0/2,000；0/1,000；既有墓碑 500/500 保持 | ✅ |
| **E7** | 180 天**边界日**的口径分歧必须被显式测出并记录 | Manager：180 天 `False`、181 天 `True`；StateMachine：180 天 **已归档**、181 天已归档 ⇒ 边界日相反 | ✅（分歧已记录，裁决待治理方） |
| **E8** | LSH：128 位确定性、维度/非有限值 fail-closed、24 说话人 → 24 个互异哈希、单次哈希 ≤ 20 ms | 哈希 32 hex 字符、重复调用一致、127 维与 NaN 均抛错、24/24 互异、**0.797 ms** | ✅ |
| **E9** | 声纹绑定 2,000×500 = 100 万次比较 ≤ 500 ms | 修复前 **748.6 ms**（0.749 µs/次）；修复后 **204.3 ms**（0.204 µs/次）= **3.66×**；`bound_count` 前后同为 **969** ⇒ 语义 parity | ✅（修复后） |
| **E10** | 生命周期规模成本：100k 档案 sweep ≤ 5 s、advance ≤ 10 s | sweep **437.408 ms**、advance **550.465 ms** | ✅ |
| **E11** | 流式摄入 4,000 帧 × 512 KB 的峰值 RSS（可擦除 vs 不可擦除） | 两条路径**同为 268.6 MB** | ℹ️ 见 §6 |

**工单那条"50ms 初筛"因此第一次成为可判定命题**：在本 profile 下实测 0.173 ms，余量 289×。
但要说清楚它**测的是什么**：清洗与擦除环节，不含上游轻量模型的画质评估与 caption 生成（那不在本模块内，见 §6）。

---

## 2. V3G-009（P1，已修）：隐私计量把"没销毁"记成"已销毁"

**修复前**（`RawByteSink.purge`）：

```python
byte_count = raw_bytes.nbytes if isinstance(raw_bytes, memoryview) else len(raw_bytes)
EdgeMultimodalCleaner._zero_mutable_buffer(raw_bytes)   # 对不可变 bytes 是 no-op
with self._lock:
    self._purged_frames += 1
    self._purged_bytes += byte_count                    # ← 照记不误
```

Python 的 `bytes` 不可变，进程内**无法擦除**其存储；`_zero_mutable_buffer` 对它直接 return。
但计数器照样累加 ⇒ 一个以"物理删除原始大图字节"为**最高违宪红线**的模块，
其对外计量会声称"已销毁 2,000,000 字节"，而其中 1,000,000 字节只是被丢了引用，
内容原封不动留在调用方持有的内存里（直到 GC，若进了 swap/core dump 则更久）。

**这不是"实现没做到红线"，而是"实现无法自证做到了红线"**——差别很重要：
不可变 bytes 的物理擦除在 Python 里本就做不到（实现方在 docstring 里**诚实写明了**这一点，这是加分项），
但把两者混进同一个计数器，就让这个客观限制**在指标层面消失**了。

**修复**（向后兼容）：保留 `purged_*` 为总量，新增 `zeroed_*`（真擦除）与 `released_*`（仅释放引用）：

```python
erasable = self._is_erasure_capable(raw_bytes)   # bytearray 或可写 memoryview
EdgeMultimodalCleaner._zero_mutable_buffer(raw_bytes)
with self._lock:
    self._purged_frames += 1;  self._purged_bytes += byte_count
    if erasable: self._zeroed_frames += 1;   self._zeroed_bytes += byte_count
    else:        self._released_frames += 1; self._released_bytes += byte_count
```

`released_frame_count > 0` 现在是一个**可观测的告警信号**：它意味着设备适配层交进来的是 `bytes`，
端侧采集路径应当改交 `bytearray`/`memoryview`，红线 2 的"物理删除"才真的可达。
`retained_byte_count` 继续恒为 0（本组件任何路径都不持有引用）。

**补测**：`test_raw_byte_sink_separates_zeroed_from_released_accounting`、
`test_raw_byte_sink_memoryview_accounting_follows_writability`（只读 memoryview 归 released、可写归 zeroed 且擦到底层）、
`test_cleaner_sink_accounting_tracks_frame_mutability`（走完整清洗路径的计量）。

---

## 3. V3G-010（P2，已修）：`bind_nearest_entities` 的 O(P×E) 重复解析

修复前每次比较都调用 `hamming_distance(profile.feature_hash, feature_hash)`，
而它内部对**两个 32 字符十六进制串各做一次 `int(value, 16)`**。这两个值在整个循环里是不变量。

| | 比较次数 | 耗时 | 每次比较 | `bound_count` |
|---|---|---|---|---|
| 修复前 | 1,000,000 | **748.6 ms** | 0.749 µs | 969 |
| 修复后 | 1,000,000 | **204.3 ms** | 0.204 µs | **969**（parity） |

**预算理由**（工单未给，故由本审查设定并写明依据）：绑定发生在端侧冷启动/新登记匹配路径；
500 个已登记实体已远超个人设备现实规模；本容器 748.6 ms 已超预算，而穿戴级 ARM 通常再慢 3~10 倍
⇒ 会变成用户可感知的启动卡顿。故门限取 **500 ms（开发靶机口径）**。

**修复**：新增 `_parse_hash()`（校验 + 转 int，错误信息与原 `hamming_distance` **逐字相同**），
登记侧解析一次、profile 侧解析一次，循环内只做 `^` 与 `.bit_count()`；
`hamming_distance` 公开 API 语义与报错文案不变。

### 3.1 我在修复过程中犯的错，以及它暴露的测试覆盖缺口（必须记录）

第一版"优化"我漏写了 `.bit_count()`：

```python
(profile_bits ^ enrollment_bits, entity_id)          # ← 按 XOR 数值大小排序，与海明距离无关
((profile_bits ^ enrollment_bits).bit_count(), entity_id)   # ← 正确
```

后果：排序依据从"海明距离"变成"XOR 整数大小"，`nearest_distance <= 16` 几乎恒假 ⇒
300 个 profile 里 **178 个绑定结果改变**（大多从"绑定"变成"不绑定"），而 **650 个既有测试全绿放行**。

**这暴露的是一个真实的覆盖缺口，不是我的个人失误**：既有测试钉住了 `bind_nearest_entities` 的
**fail-closed 分支**（`test_ambiguous_lsh_enrollment_fails_closed_as_unbound`：并列 ⇒ 不绑）与
格式校验分支，但**没有任何测试钉住"成功绑定"这条正路**。于是一个把正路彻底改坏的变更可以静默通过。

补测因此以**行为基准对照**为核心，而不是只测快慢：
`_naive_bind_reference()` 保留优化前的形状（每次比较调用公开 `hamming_distance`），
新测试断言优化后的输出与之**逐一相同**，并覆盖五个判定分支
（唯一最近 ⇒ 绑；并列 ⇒ 不绑；最近但太远 ⇒ 不绑；已绑定 ⇒ 不动；已墓碑 ⇒ 不动）。

> **一般化教训**（值得进设计书）：对"只改性能不改语义"的重构，验收断言必须是
> **与旧实现的行为差分**，而不是新实现的自证测试。自证测试只会重复你此刻的理解，
> 而此刻的理解正是最可能出错的地方。

---

## 4. V3G-011（P1，**不擅自修**）："180 天"有两套口径

| 路径 | 判定 | 180 天整 | 181 天 |
|---|---|---|---|
| `VoiceprintLifecycleManager.sweep_stale_voiceprints` | 严格 `> 180d` | **不打墓碑** | 打墓碑 |
| `VoiceprintTTLStateMachine.advance` | 包含 `>= 180d` | **打墓碑（移出热表）** | 打墓碑 |

两者都有测试钉住自己的口径，模块 docstring 也**主动声明**了这个差异（"without changing the legacy
manager's strict `> 180 days` contract"）⇒ 这是**有意共存**，不是疏忽。

但共存意味着：**同一份声纹档案，走不同路径，在边界日会得到相反的隐私结论。**
工单与宪法红线 3 的字面是"超过 180 天"（= 严格 `>`），而"更早删除"在隐私上更保守、在法律上更安全。

我**不擅自统一**，因为两个方向都有真实代价：改成 `>=` 会让 Manager 在边界日多删（改变既有验收断言），
改成 `>` 会让 StateMachine 少删（削弱隐私保守性）。登记为治理裁决项，并给出建议：
**对外验收与法条口径用 `> 180d`；端侧自动清理用 `>= 180d` 偏保守——但两者必须写进同一份契约文档，
并注明哪一条是权威口径**，否则下一次重构会有人"顺手统一"，而没人知道统一到了错的一边。

探针 E7 的作用是**让分歧无法被遗忘**：它不断言谁对，只断言"分歧被显式测出并记录在案"。

---

## 5. 公允记录：已落地实现比工单骨架强的地方

工单给的骨架是"最小可跑版"。实际落地版本在多处**优于骨架**，这些不该被缺陷清单掩盖：

1. **`raw_image_bytes_retained: Literal[False]` + before-validator**：不是"默认 False"，而是**类型上不可能为 True**；
   骨架的 `bool = Field(default=False)` 允许调用方传 True。
2. **擦除放在 `finally`**：合格帧、丢弃帧、**校验失败帧**三条路径都擦；骨架只在成功路径丢引用，
   非法输入抛异常时帧缓冲原样留着。
3. **非法画质值 fail-closed**：`quality_score="abc"`/NaN/越界 ⇒ 抛 `ValueError`；
   骨架用 `.get("quality_score", 0.5)` 静默兜底成"合格"，那会让坏数据混进主库。
4. **`extra="forbid"` + `frozen=True`**：输出模型不可变、不可夹带私货；骨架两者皆无。
5. **128 维 LSH 真的实现了**（工单 §1.4 要求）：确定性随机超平面（`shake_256` 种子化）、
   维度与非有限值 fail-closed、`bind_nearest_entities` 对**并列最近者一律不绑**（宁可漏绑不错绑）。
6. **生命周期状态机拒绝时间倒流**（`advance` 对 `now < _last_advanced_at` 抛错）、
   墓碑**不自动复活**、`sweep` 不改写输入（返回投影）。
7. **`_zero_mutable_buffer` 分块擦除且诚实标注局限**（不可变 bytes 无法擦除，所有权在设备适配层）。

---

## 6. 未裁定事项（诚实边界）

1. **E5 的 50 ms 只覆盖"清洗 + 擦除"**，不含上游轻量模型的画质评估与 caption 生成——
   工单 §1.2 的"端侧 50ms 初筛"若指**含模型的端到端初筛**，则本模块无法裁定，需要模型侧另立 profile 与工件。
   本审查按"本模块可控范围"设定口径，并在此显式声明。
2. **E11 峰值 RSS 无差异（268.6 MB vs 268.6 MB）**：4,000 帧 × 512 KB 流式喂入，
   可擦除与不可擦除两条路径的峰值内存**相同**。原因是 CPython 分配器对两种情况都会复用已释放块，
   而每帧都是新分配、用完即弃。⇒ **擦除的价值不在 RSS，而在取证面**（冷内存、swap、core dump、
   进程崩溃后的残留）。这一条如实记录，不用它去支撑"擦除能省内存"的说法。
3. **哈希校验的宽松处已钉住但未收紧**：`int(value, 16)` 接受 `0x` 前缀与下划线分隔符，
   因此 32 字符里含前缀/下划线的串会被当作合法 128 位哈希（有效位实际更少）。
   新测试 `test_hash_validation_leniency_is_pinned_as_known_behaviour` **钉住现状**，
   使任何收紧都成为一次显式决定——收紧会让已入库的此类哈希失效，属契约变更，需治理方裁决。
4. **本轮未审**：`multimodal_edge.py` 与 `storage/sqlite_store.py` 的落库路径是否真的没有 BLOB 列
   （E2 只证明了**本模块的输出模型**不含字节载荷，没有证明存储层不会从别处接收图片字节）。
   这条留给下一轮的存储层审查，**不在本报告下任何结论**。

---

## 7. 验收断言清单（工单要求 3 条 + 本审查追加）

工单 §4 要求的三条，逐条对应到**可执行断言**：

| 工单要求 | 落地断言 | 位置 |
|---|---|---|
| 画质 < 0.4 时返回 None | `test_edge_cleaner_discards_quality_below_point_four` + 探针 E1（含 0.4 边界**保留**） | 既有测试 / 探针 |
| Observation 的 `raw_image_bytes_retained` 严格为 False | `test_edge_cleaner_accepts_exact_threshold_and_never_retains_raw_bytes` + 探针 E2（按注解类型判定 + 构造 True 必抛错） | 既有测试 / 探针 |
| 超 180 天未活跃的无主声纹 100% 打墓碑 | `test_voiceprint_sweep_tombstones_every_stale_unbound_profile`（100 条）+ 探针 E6（**10,000 条，召回 1.0，已绑定误伤 0**） | 既有测试 / 探针 |

本审查追加的 19 条（`tests/unit/test_m1_001r_edge_cleaner.py`，22 → 41）：
sink 计量区分度 ×3、绑定行为差分 ×2（含 300×200 规模档 + 250 ms 宽松上界防抖动）、
畸形哈希分层 fail-closed ×3（登记侧 5 参数 + profile 侧 4 参数 + 空串归模型层）、
`hamming_distance` 契约不变 ×1、2 MB 帧 50 ms 预算 ×1、哈希宽松处钉住 ×2 等。

**全仓：`650 → 669 passed`（0 failed）。**

---

## 8. 复现、分支与推送状态

```bash
pip install --break-system-packages pydantic pytest          # 沙箱每次重启后需重装
PYTHONPATH=src python3 -m pytest                             # 669 passed
PYTHONPATH=src python3 reviews/architecture/evidence/verify_landed_m1_001r_edge.py \
        --repeat 60 --json reviews/architecture/evidence/verify_landed_m1_001r_edge_result.json
```

- **分支**：工单要求 `arena/agent-01-m1-001r`，但**本会话被平台固定绑定到 `arena/01a0a631-fantonghui`**，
  不能创建或推送到其他分支（Arena 以该分支追踪本会话）。改动全部落在会话分支上，
  合并到 `arena/agent-01-m1-001r` 或 `aios-2.0` 由治理方在 PR 阶段处置。
- **推送状态**：`gh auth status` 报 `GH_TOKEN is no longer valid` ⇒ **本轮无法推送**。
  提交已在本地分支上；需要用户在 Arena 重连 GitHub 后由下一次操作推送。
- **号位提示（不属本工单，但必须说）**：`M1-001R` 是**未注册号**（`R` 后缀不在 R4_prefix 命名空间内）。
  registry 中本模块语义的正主是 `M1-017` `simulated-edge-reduction-pipeline`，声纹生命周期另有 `RC-016`。
  见上一轮报告的 `V3G-004`（号位错位）与 `V3G-005`（派工单不带 slug）。本报告按工单原文使用 `M1-001R` 称呼，
  `traces_to` 则指向 registry 的真实号位。

**免责声明**：合成帧与合成声纹、容器文件系统、`Python 3.11.2 / pydantic 2.13.5 / SQLite 3.40.1`。
数字用于**门限可达性与修复前后比较**，不是产品 SLO 承诺；运行间存在 ±20% 抖动，
故所有引用值均绑定工件哈希（`script_sha256=5ad1d460…`，`subject_sha256=dbc84146…`）。
