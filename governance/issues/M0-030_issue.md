# M0-030 · runtime_profile 双配置契约（virtual / band_v0）+ R4-09.1 Claim 信任字段

**里程碑**：M0′（R4 追加）｜**依赖**：R4-05.2 冻结清单、R4-09.1/3｜**上位**：设计书 §2.4、T6｜**CAM**：R4-09（已挂真实测试）

## 背景（为什么 lethal）
33.4/19.1 让 IM 与旁听语音"平等互证"却无信任模型——同事玩笑可一路合宪长成
提醒任务；穿戴端约束（电池/带宽/算力）在宪法里是许诺，无 profile 则 M1–M7 按
虚拟假设过度优化，M8 消融系统性偏乐观。

## 已交付（候选契约冻结，2026-09-16）
1. `enums.py`：`ProfileName = {virtual, band_v0}`（入快照枚举冻结）。
2. `models.py`（入快照模型哈希冻结——**配置进冻结面，才不是许愿**）：
   - `IngestPolicy`：hr 压缩窗 / imu 仅宏观事件 / 图像仅语义文本 / 每摄入算力
     预算(us) / 图像队列深度 / 丢帧必须记录；
   - `LatencyPolicy`：首字 1000ms / 同步召回 50ms（与 G-M1P 同数）/ TTS 分段；
   - `StoragePolicy`：raw_tier_days=30（M1-019 施工图引用处闭环）/ 环缓冲 /
     存储速率上限；
   - `RuntimeProfile`：`extra=forbid`（夹带新旋钮 = 改代码路径，拒）；validator
     写死宪法硬线两 profile 同判（tombstone 不可关 / 禁 raw IMU / 禁大图 /
     丢帧必录——"只改数字不改路径"的结构化表达）；band_v0 逐数字 ≤ virtual
     默认 + 四个必填旋钮 + 队列深度 ≤3；
   - `DEFAULT_VIRTUAL / DEFAULT_BAND_V0` 冻结常量 + `resolve_runtime_profile`。
3. R4-09.1 Claim 字段表追加（第 38 条）：`source_trust`（0–1）+
   `corroboration_required`；validator：印证前禁升 FACT（V31 契约执法点）；
   `may_drive_external_action` 谓词。`tests/unit/test_claim.py` 按批准漂移
   流程登记两字段。
4. 快照再生成：40 模型（+RuntimeProfile 家族 4）；gate 串仍
   `M0-R2+R4-delta-candidate`（签核包批准动作第 1 步统一翻转）。

## 遗留工作（不入本契约任务）
- C01/C13/C02 运行面消费 profile（M1 摄入、M2-018 预算闸门）；
- band_v0 一日回放冒烟 harness（T6，M2 起每里程碑出口强制）——可挂
  `aios_core.bench.g_m1p` 的 report 骨架扩展 profile 段；
- source_trust 随反馈演化的更新机制（Reinterpretation 同族，M3+）。

## 已知限制
- 依赖 R4-09 批准（签核包 §1 复审块 B）；驳回时随 M0-023~028 delta 一并 revert；
- profile 数值（800us/100k、h·rev 等）为工程默认候选，签核人可改数字而模型
  形状不变——数字不进模型哈希的部分（validator 阈值）如需改须重跑本文件测试。

## 验收
- [x] tests/unit/test_r4_09_runtime_profile_and_trust.py（9 用例）
- [x] 快照含 profile 家族哈希；CAM R4-09 条目挂真实测试，7/7
- [ ] R4 签核转正（与 M0-023~028 同一动作，见签核包 §2）
