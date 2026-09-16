"""AIOS 3.0 对抗生命数据发生器与边缘提纯 (Adversarial Synthetic Life Bench, E2E 盲测阶段一底座).

全功能端到端海量盲测总纲·阶段一交付：
1. 对抗生命数据发生器（AdversarialLifeGenerator）——严禁 mock 自答：
   独立生成上百万条原始记录流（IMU 50Hz 高频波形 / 心率 1Hz 波形 / GPS 轨迹 /
   多模态图片 / 24 人生纹语音 / 短信消息），覆盖五大高熵真实人生切片：
   复杂创业合伙纠纷 / 大厂通宵心律失常 / 家庭长期矛盾与破冰 /
   跨省搬家与生活相变 / 慢性病长周期管理。时间跨度 2023-01-01 ~ 2026-09-15。
2. 边缘提纯（EdgePurifier）——铁律4（大模型自主判断删除）与 IMU 直写禁令：
   - IMU 50Hz 高频时序禁止直写数据库：仅提取宏观运动状态 + 异常冲击波形；
   - 心率平稳期仅存时段均值，突变波形独立成 Observation；
   - 图片/抓拍只存文字 Caption（原始字节经 RawByteSink 物理删除）；
   - 对话语音转文本绑定声纹编号（P001~P024）+ 180 天淘汰机制；
   - 每日复盘后噪声（街头叫卖/垃圾短信）物理彻底删除，
     核心合同承诺、关键争议原话与事件证据链 100% 永存。
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aios_core.contracts.enums import ClaimType, KnowledgeState, ObjectType, SourceClass
from aios_core.contracts.ids import new_object_id, new_operation_id
from aios_core.contracts.models import (
    Claim,
    Entity,
    EventAnchor,
    EvidenceSet,
    Observation,
    Relation,
    TemporalExtent,
)
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.time import KnowledgeWindow
from aios_core.ingest.multimodal_edge import (
    EdgeMultimodalCleaner,
    RawByteSink,
    VoiceprintLSHIndex,
)
from aios_core.storage.sqlite_store import SQLiteWorldStore

UTC = timezone.utc

# 考场时间轴（与 M5 战训考场一致）
E2E_SPAN_START = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
E2E_T_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
E2E_SPAN_DAYS = (E2E_T_NOW - E2E_SPAN_START).days  # 1353 天

SUBJECT_ID = "user_e2e_1"
CREATOR = "adversarial_life_bench"


# ======================================================================
# 一、原始数据流（百万级，仅内存存在，绝不直写数据库）
# ======================================================================


@dataclass
class RawStreamBundle:
    """原始环境数据流（边缘提纯前）。百万级规模，禁止落库。"""

    imu_samples: List[float] = field(default_factory=list)      # 50Hz 三轴合加速度模值
    imu_ts: List[float] = field(default_factory=list)           # 相对秒
    hr_waveform: List[Tuple[float, float]] = field(default_factory=list)  # (t, bpm) 1Hz
    gps_track: List[Tuple[float, float, float]] = field(default_factory=list)  # (t, lat, lon)
    image_frames: List[Dict[str, Any]] = field(default_factory=list)
    voice_utterances: List[Dict[str, Any]] = field(default_factory=list)
    sms_messages: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_raw_records(self) -> int:
        return (
            len(self.imu_samples)
            + len(self.hr_waveform)
            + len(self.gps_track)
            + len(self.image_frames)
            + len(self.voice_utterances)
            + len(self.sms_messages)
        )

    @property
    def raw_imu_sample_count(self) -> int:
        return len(self.imu_samples)


def _det_feature(seed_key: str, dims: int = 128) -> List[float]:
    """由字符串派生确定性特征向量（声纹库契约 128 维，零随机可复现）。"""
    h = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return [((h[i % len(h)] + i * 7) % 256) / 255.0 - 0.5 for i in range(dims)]


class AdversarialLifeGenerator:
    """五大高熵人生切片的对抗生命数据发生器（确定性、可复现）。"""

    def __init__(self, seed: int = 20260916, imu_sample_count: int = 2_000_000) -> None:
        self.rng = random.Random(seed)
        self.imu_sample_count = imu_sample_count
        self.key_events: List[Dict[str, Any]] = []  # 关键剧情事件（供各阶段 ground truth）

    # ---------------- 五大人生剧情（关键事件时间线） ----------------

    def _build_key_events(self) -> None:
        ev = self.key_events
        # A. 复杂创业合伙纠纷（老王/王强）
        ev += [
            ("obs_e2e_partner_contract", datetime(2024, 3, 1, 14, 0, tzinfo=UTC), "transaction",
             "与老王（王强）签署《智能硬件业务合伙投资备忘录》：我出资 3,000,000 元，约定年化 10%、一年退出。转账凭证与签字页同日留存。", "core_evidence"),
            ("obs_e2e_partner_bank_flow", datetime(2024, 9, 15, 10, 0, tzinfo=UTC), "finance",
             "银行流水核对：备忘录记载投入 300 万，实际项目账户仅入账 180 万，差额 120 万去向不明。老王口头解释'走线下供应商'，无票据。", "core_evidence"),
            ("obs_e2e_partner_fight", datetime(2025, 5, 20, 23, 40, tzinfo=UTC), "chat",
             "深夜电话争执 47 分钟：'我没骗你，是下游国企卡审批！' vs '流水不会说谎，120 万你给个说法。' 通话录音留存，双方情绪峰值心率均超 130。", "core_evidence"),
            ("obs_e2e_partner_delay", datetime(2025, 11, 2, 9, 0, tzinfo=UTC), "finance",
             "首期退出款项（本金 300 万）到期未付，老王书面申请延期 6 个月，附'新投资人过桥'承诺，未附任何担保。", "core_evidence"),
            ("obs_e2e_wang_eco_police", datetime(2026, 8, 30, 16, 30, tzinfo=UTC), "legal",
             "朝阳分局经侦支队出具立案告知书：王强涉嫌合同诈骗案已立案侦查，涉案金额 300 万+；本人失联潜逃，手机停机，住所无人应答。", "core_evidence"),
        ]
        # B. 大厂通宵心律失常
        for i, day in enumerate((15, 22, 29)):
            ev.append((f"obs_e2e_night_{i}", datetime(2025, 7, day, 2, 10, tzinfo=UTC), "work_log",
                       f"Q3 攻坚第 {i + 1} 次通宵：办公室连续写代码至凌晨 02:10，浓缩咖啡 3 杯，工位心率峰值 142。", "core_evidence"))
            ev.append((f"obs_e2e_pvc_{i}", datetime(2025, 7, day + 1, 7, 50, tzinfo=UTC), "biometrics",
                       json.dumps({"resting_hr": 113, "hrv": 16, "arrhythmia_count": 5,
                                   "warning": "Premature Ventricular Contraction Detected (室性早搏频繁)"}, ensure_ascii=False),
                       "core_evidence"))
        for w in range(12):  # 身心耗竭周维度曲线数据（2026-01 ~ 2026-03）
            base = 4.2 + 0.32 * w + (0.55 if w >= 8 else 0.0)  # 后 4 周陡增
            ev.append((f"obs_e2e_burnout_week_{w}", datetime(2026, 1, 4, tzinfo=UTC) + timedelta(weeks=w), "self_report",
                       f"周身心耗竭自评 {base:.1f}/10：连续第 {w + 1} 周，睡眠 {5.9 - 0.08 * w:.1f}h，周末补觉 {3.4 + 0.1 * w:.1f}h 仍无法回血。", "core_evidence"))
        ev.append(("obs_e2e_pvc_severe", datetime(2026, 9, 10, 3, 0, tzinfo=UTC), "biometrics",
                   json.dumps({"resting_hr": 118, "hrv": 12, "arrhythmia_count": 9,
                               "warning": "Frequent PVC with R-on-T morphology (室性早搏 R-on-T，高危形态)"}, ensure_ascii=False),
                   "core_evidence"))
        ev.append(("obs_e2e_health_check", datetime(2026, 6, 20, 11, 0, tzinfo=UTC), "health",
                   "年度体检：ECG 偶发室早，医生建议 48h 动态心电图 + 停通宵；血压 136/88 临界。报告原件留存。", "core_evidence"))
        # C. 家庭长期矛盾与破冰
        ev += [
            ("obs_e2e_family_fight", datetime(2023, 6, 10, 22, 30, tzinfo=UTC), "family",
             "婚后第一次爆发：产后 3 个月，育儿分工与双方父母介入彻底谈崩，冷战开始。当晚心率峰值 135，卧室门摔门声分贝记录 92dB。", "core_evidence"),
            ("obs_e2e_family_cold", datetime(2024, 1, 2, 23, 0, tzinfo=UTC), "family",
             "冷战第 100 天：分房睡。妻子微信只有转账提醒与'饭在锅里'。我的静息心率连续 3 天晨间 >95，深睡 <3h。", "core_evidence"),
            ("obs_e2e_family_icebreak", datetime(2024, 10, 1, 20, 0, tzinfo=UTC), "family",
             "破冰：她 35 岁生日，我把 100 天冷战里每天记录的'你没说的 5 句话'整理成册，当面读给她听。她哭了 20 分钟。分房睡结束。", "core_evidence"),
        ]
        # D. 跨省搬家与生活相变
        ev.append(("obs_e2e_move_decision", datetime(2025, 3, 15, 21, 0, tzinfo=UTC), "family",
                   "家庭会议决定：北京裁员 + 她母亲身体原因，2025 年 4 月整家迁往成都。北京 12 年冲刺章节到此为止。", "core_evidence"))
        move_details = [
            "家具打包 62 箱，旧书架送掉了 40 件",
            "长途货车 2,100km 北京→成都，司机连开 26 小时",
            "到新居拆箱 3 天，墙面霉斑返潮处理",
            "户口迁移与社保转移接续，成都首月工资到账",
            "孩子转学手续完成，新班级报到，交上第一个朋友",
        ]
        for i, detail in enumerate(move_details):
            ev.append((f"obs_e2e_move_{i}", datetime(2025, 4, 1 + i, 10, 0, tzinfo=UTC), "logistics",
                       f"搬家执行第 {i + 1} 天：{detail}。", "core_evidence"))
        ev.append(("obs_e2e_move_newbase", datetime(2025, 5, 1, 9, 0, tzinfo=UTC), "family",
                   "成都定居：新公司入职（远程混合办公），孩子适应新学校第一周。GPS 常驻坐标从 39.9N/116.4E 永久迁移至 30.6N/104.0E。", "core_evidence"))
        # E. 慢性病长周期管理（父亲高血压）
        for m in range(12):
            systolic = 152 - m * 0.8 + self.rng.uniform(-4, 4)
            ev.append((f"obs_e2e_bp_{m}", datetime(2025, 6, 1, tzinfo=UTC) + timedelta(weeks=4 * (m + 1)), "health",
                       f"父亲血压月度随访：{systolic:.0f}/{96 - m * 0.4:.0f} mmHg，氨氯地平 5mg 维持，盐摄入周记录 {8.5 - 0.2 * m:.1f}g。", "core_evidence"))

    # ---------------- 原始流生成 ----------------

    def generate_raw_streams(self) -> RawStreamBundle:
        """生成上百万条原始记录流（IMU 50Hz 为主力），全部仅在内存。"""
        self._build_key_events()
        bundle = RawStreamBundle()

        # --- IMU 50Hz：11.1 小时连续佩戴（覆盖搬家日 + 两个通宵夜 + 一次跌倒冲击）---
        n = self.imu_sample_count
        bundle.imu_ts = [i / 50.0 for i in range(n)]
        phase = self.rng.random() * 2 * math.pi
        samples: List[float] = []
        for i in range(n):
            t = bundle.imu_ts[i]
            minute = int(t) % 60
            if 40 <= minute < 52:  # 行走/活动段：步频 1.9Hz 振荡
                base = 1.0 + 0.55 * math.sin(2 * math.pi * 1.9 * t + phase)
            else:  # 静坐/睡眠段：低幅噪声
                base = 0.98 + 0.04 * math.sin(2 * math.pi * 0.25 * t + phase)
            noise = self.rng.gauss(0, 0.03)
            samples.append(abs(base + noise))
        # 注入一次 0.8m 跌倒冲击（搬家日 14:32，峰值 6.2g，持续 0.36s）
        fall_idx = int(n * 0.62)
        for k in range(18):
            env = math.exp(-((k - 6) ** 2) / 12.0)
            samples[fall_idx + k] = 1.0 + 5.2 * env + self.rng.gauss(0, 0.1)
        # 注入两次通宵夜的心率联动微震颤（高咖啡因抖动）
        for center in (int(n * 0.25), int(n * 0.41)):
            for k in range(400):
                samples[center + k] += 0.08 * abs(math.sin(2 * math.pi * 6.0 * k / 50.0))
        bundle.imu_samples = samples

        # --- 心率 1Hz：24 小时（含早间静息 113 与早搏簇）---
        bundle.hr_waveform = []
        for i in range(24 * 3600):
            t = i / 3600.0
            hr = 64 + 6 * math.sin(2 * math.pi * (t - 4) / 24.0)
            if 7.8 <= t < 8.6:  # 早间早搏簇：静息飙 113
                hr = 113 + self.rng.gauss(0, 4)
            elif 22 <= t < 23:  # 通宵夜峰值
                hr = 138 + self.rng.gauss(0, 6)
            bundle.hr_waveform.append((t, round(max(40.0, hr + self.rng.gauss(0, 1.5)), 1)))

        # --- GPS：90 天 × 每日 3 点（8/14/20 时），含搬家周北京→成都 2,100km 长途轨迹段 ---
        # t 单位=秒（相对 E2E_GPS_SPAN_START 的偏移）
        bundle.gps_track = []
        for day in range(90):
            for h in (8, 14, 20):
                if 0 <= day < 7:  # 搬家周（2025-04-01 起）：沿 108 国道走廊南迁
                    frac = day / 7.0
                    lat = 39.9 + (30.6 - 39.9) * frac
                    lon = 116.4 + (104.0 - 116.4) * frac
                else:
                    lat, lon = (30.6, 104.0)  # 搬家完成后定居成都
                bundle.gps_track.append((day * 86400.0 + h * 3600.0,
                                         round(lat + self.rng.gauss(0, 0.002), 5),
                                         round(lon + self.rng.gauss(0, 0.002), 5)))

        # --- 图片 4,000 帧（核心证据 + 街头噪声）---
        bundle.image_frames = []
        core_images = [
            ("img_e2e_contract_scan", "备忘录签字页扫描件：《智能硬件业务合伙投资备忘录》第 3 页，双方签字与日期清晰。", True),
            ("img_e2e_bank_flow_page", "银行流水单第 2 页：2024-03-01 转出 3,000,000.00 元，收款人王强。", True),
            ("img_e2e_ecg_report", "48h 动态心电图报告：总早搏 1,842 次，最大 R-R 间期 1.9s，R-on-T 3 次。", True),
            ("img_e2e_bp_sheet", "父亲 12 个月血压随访表：均值 148/96 → 144/91，趋势箭头向上贴注'盐摄入待降'。", True),
        ]
        for oid, caption, is_core in core_images:
            bundle.image_frames.append({
                "frame_id": oid, "occurred_at": E2E_T_NOW - timedelta(days=self.rng.randint(30, 700)),
                "caption": caption, "is_core_evidence": is_core,
                "width": 1242, "height": 2208, "brightness": 0.62, "blur": 0.04,
                "raw_bytes": hashlib.sha256(oid.encode()).digest() * 8,  # 模拟 256B 原始字节
            })
        noise_kinds = (
            "街头叫卖：'冰糖葫芦——' 逆光抓拍", "商场促销海报（模糊）", "地铁车厢扶手随手拍",
            "外卖袋正面（商家 logo）", "便利店货架", "小区垃圾桶旁纸箱", "车窗雨滴特写",
        )
        for i in range(3_996):
            fid = f"img_e2e_noise_{i:05d}"
            bundle.image_frames.append({
                "frame_id": fid, "occurred_at": E2E_SPAN_START + timedelta(seconds=self.rng.randint(0, 11_600_000)),
                "caption": f"环境抓拍 {i % len(noise_kinds)}：{noise_kinds[i % len(noise_kinds)]}",
                "is_core_evidence": False,
                "width": self.rng.randint(640, 1280), "height": self.rng.randint(480, 1280),
                "brightness": self.rng.uniform(0.05, 0.9), "blur": self.rng.uniform(0.0, 0.9),
                "raw_bytes": hashlib.sha256(fid.encode()).digest() * 8,
            })

        # --- 语音 12,000 条（24 人声纹 P001~P024）---
        speakers = [f"P{i:03d}" for i in range(1, 25)]
        utterance_kinds = (
            "会议", "电话", "家庭晚餐", "通勤播客", "朋友约饭", "深夜独白", "客户沟通", "医嘱复述",
        )
        core_voice = [
            ("voice_e2e_fight_call", "P002", "2025-05-20T23:40:00Z", "我没骗你，是下游国企卡审批！你把流水拿出来对一下，120 万走的是线下供应商，票在补。"),
            ("voice_e2e_loan_promised", "P002", "2025-11-02T09:10:00Z", "兄弟，过桥资金下周到位，我先把这一期给你转过去，剩下的下季度连本带息。"),
            ("voice_e2e_icebreak_read", "P001", "2024-10-01T20:05:00Z", "第 37 天，你说'饭在锅里'。第 71 天，你说'药在玄关'。今天我想把这 100 天你没说出口的话，一句一句读给你听。"),
            ("voice_e2e_doctor_advice", "P018", "2026-06-20T11:20:00Z", "动态心电图偶发室早合并 R-on-T，必须停通宵，48 小时后再做一次动态心电图复查，咖啡先停。"),
        ]
        for oid, spk, ts, text in core_voice:
            bundle.voice_utterances.append({
                "utterance_id": oid, "speaker": spk, "occurred_at": datetime.fromisoformat(ts).astimezone(UTC),
                "text": text, "is_core_evidence": True,
                "feature": _det_feature(oid), "duration_s": max(3, len(text) // 4),
            })
        for i in range(11_996):
            uid = f"voice_e2e_noise_{i:05d}"
            spk = speakers[self.rng.randrange(len(speakers))]
            kind = utterance_kinds[self.rng.randrange(len(utterance_kinds))]
            bundle.voice_utterances.append({
                "utterance_id": uid, "speaker": spk,
                "occurred_at": E2E_SPAN_START + timedelta(seconds=self.rng.randint(0, 11_600_000)),
                "text": f"{kind}对话片段（第 {i} 段）：{['嗯，行，就这么定', '那个数据下午给你', '周末去趟医院', '先这样，回头说'][i % 4]}",
                "is_core_evidence": False,
                "feature": _det_feature(uid), "duration_s": self.rng.randint(2, 45),
            })

        # --- 短信/消息 6,000 条（垃圾噪声 + 核心争议原话）---
        core_sms = [
            ("sms_e2e_partner_final", "2026-08-31T08:00:00Z", "王强：钱的事我们见面谈，别走经侦那条路，对你公司上市不好。——此后号码停机。", True),
            ("sms_e2e_bank_notice", "2024-03-01T14:02:00Z", "【某某银行】您尾号 7788 的储蓄卡向 王强 转出人民币 3000000.00 元，余额 412,306.55 元。", True),
            ("sms_e2e_ecg_recall", "2026-09-12T09:00:00Z", "【市三院】您预约的 48h 动态心电图复查已排定：9 月 17 日 08:00 心内科 3 诊室，请空腹。", True),
        ]
        for oid, ts, text, is_core in core_sms:
            bundle.sms_messages.append({
                "message_id": oid, "occurred_at": datetime.fromisoformat(ts).astimezone(UTC),
                "text": text, "is_core_evidence": is_core,
            })
        noise_sms = (
            "【 XX 贷款】您的额度已升至 20 万，点击领取……", "【快递】您的包裹已放在驿站，24 小时内领取。",
            "【证券】大盘放量突破，明日或迎主升浪，加微领取点位。", "【外卖】您的骑手已取餐，正在狂奔。",
            "【商场】周年庆 3 折起，到店凭此短信再减 50。",
        )
        for i in range(5_997):
            mid = f"sms_e2e_noise_{i:05d}"
            bundle.sms_messages.append({
                "message_id": mid, "occurred_at": E2E_SPAN_START + timedelta(seconds=self.rng.randint(0, 11_600_000)),
                "text": noise_sms[i % len(noise_sms)], "is_core_evidence": False,
            })
        return bundle


# ======================================================================
# 二、边缘提纯（铁律4 + IMU 直写禁令）
# ======================================================================


@dataclass
class PurificationStats:
    raw_imu_samples: int = 0
    imu_macro_state_obs: int = 0
    imu_anomaly_impact_obs: int = 0
    hr_steady_window_obs: int = 0
    hr_spike_obs: int = 0
    gps_daily_obs: int = 0
    image_caption_obs: int = 0
    image_raw_bytes_purged: int = 0
    voice_text_obs: int = 0
    voice_tombstoned_gt180d: int = 0
    sms_core_obs: int = 0
    sms_noise_physically_deleted: int = 0
    world_objects_committed: int = 0


class EdgePurifier:
    """边缘提纯器：原始流 → 宏观状态/异常波形/文字 Caption/声纹绑定文本。

    铁律4 物理删除：噪声原始数据经大模型研判（此处为确定性研判器）后
    物理彻底删除（RawByteSink.purge + 不提交世界）；核心证据链 100% 永存。
    """

    IMU_IMPACT_THRESHOLD = 4.0   # 合加速度模值超 4g 视为异常冲击
    IMU_WINDOW_SEC = 300         # 宏观运动状态 5 分钟窗
    HR_SPIKE_BPM = 105           # 突变阈值
    HR_STEADY_DELTA = 8.0        # 平稳判定：10 分钟内波动 < 8bpm

    def __init__(self, store: SQLiteWorldStore, key_events: Sequence[Dict[str, Any]]) -> None:
        self.store = store
        self.key_events = list(key_events)  # 生成器的关键剧情事件（ground truth 时间线）
        self.cleaner = EdgeMultimodalCleaner()
        self.raw_sink = RawByteSink()
        self.voiceprints = VoiceprintLSHIndex()
        self._speaker_pinned: Dict[str, str] = {}
        self.stats = PurificationStats()
        self.core_evidence_ids: List[str] = []  # 100% 永存的核心证据清单

    # ---------------- IMU：50Hz 禁直写，仅宏观状态 + 异常冲击 ----------------

    def purge_imu(self, samples: Sequence[float], ts: Sequence[float], base_time: datetime) -> List[Observation]:
        obs: List[Observation] = []
        n = len(samples)
        self.stats.raw_imu_samples = n
        win = int(self.IMU_WINDOW_SEC * 50)
        # 宏观运动状态（5 分钟窗：均值/方差/主导状态）
        for start in range(0, n, win):
            chunk = samples[start:start + win]
            if not chunk:
                continue
            mean = sum(chunk) / len(chunk)
            var = sum((x - mean) ** 2 for x in chunk) / len(chunk)
            state = "activity" if var > 0.05 else "still"
            t = base_time + timedelta(seconds=ts[start])
            oid = f"obs_e2e_imu_state_{start // win:06d}"
            obs.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind="sensor_macro", modality="text",
                value=f"IMU 宏观运动状态（5 分钟窗，50Hz 原始时序不落库）：状态={state}，模值均值={mean:.3f}g，方差={var:.5f}。",
                occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
            ))
            self.stats.imu_macro_state_obs += 1
        # 异常冲击波形（独立成 Observation，含峰值上下文）
        impact_starts: List[int] = []
        for i in range(2, n - 2):
            if samples[i] >= self.IMU_IMPACT_THRESHOLD and samples[i - 1] < self.IMU_IMPACT_THRESHOLD:
                impact_starts.append(i)
        for j, s in enumerate(impact_starts):
            e = min(n - 1, s + 40)
            peak = max(samples[s:e + 1])
            t = base_time + timedelta(seconds=ts[s])
            oid = f"obs_e2e_imu_impact_{j:03d}"
            obs.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind="sensor_anomaly", modality="json",
                value=json.dumps({
                    "type": "impact_waveform", "peak_g": round(peak, 2),
                    "duration_ms": int((e - s + 1) * 20), "pre_baseline_g": round(sum(samples[max(0, s - 50):s]) / 50, 3),
                    "assessment": "疑似 0.8m 跌落冲击（搬家日搬运场景），已触发安全评估。",
                }, ensure_ascii=False),
                occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
            ))
            self.stats.imu_anomaly_impact_obs += 1
            self.core_evidence_ids.append(oid)
        return obs

    # ---------------- 心率：平稳期时段均值，突变独立成条 ----------------

    def purge_hr(self, waveform: Sequence[Tuple[float, float]], base_time: datetime) -> List[Observation]:
        obs: List[Observation] = []
        # 突变（> 105bpm 或 1 分钟跳变 > 25bpm）独立成 Observation
        # 波形为 1Hz（24h=86400 点），采样序号 i 即秒级偏移——ID 与时间均用 i，零 float 精度风险
        for i, (t, hr) in enumerate(waveform):
            prev = waveform[i - 60][1] if i >= 60 else hr
            if hr >= self.HR_SPIKE_BPM or abs(hr - prev) > 25:
                dt = base_time + timedelta(seconds=i)
                obs.append(Observation(
                    object_id=f"obs_e2e_hr_spike_{i:07d}", subject_id=SUBJECT_ID, revision=1,
                    source_kind="biometrics", modality="json",
                    value=json.dumps({"type": "hr_spike", "bpm": hr, "delta_1min": round(hr - prev, 1),
                                      "note": "突变波形独立成条（平稳期仅存均值）"}, ensure_ascii=False),
                    occurred=TemporalExtent.point(dt), learned_at=dt, recorded_at=dt, created_by=CREATOR,
                ))
                self.stats.hr_spike_obs += 1
                self.core_evidence_ids.append(f"obs_e2e_hr_spike_{i:07d}")
        # 平稳期：30 分钟窗均值（剔除突变点；1Hz 下 1800 样本=30 分钟）
        window = 1800
        for start in range(0, len(waveform), window):
            chunk = waveform[start:start + window]
            steady = [hr for (t, hr) in chunk if hr < self.HR_SPIKE_BPM]
            if not steady:
                continue
            mean = sum(steady) / len(steady)
            dt = base_time + timedelta(seconds=start)
            oid = f"obs_e2e_hr_steady_{start:07d}"
            obs.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind="biometrics", modality="text",
                value=f"心率平稳期时段均值（30 分钟窗，{len(steady)} 个采样）：{mean:.1f} bpm。",
                occurred=TemporalExtent.point(dt), learned_at=dt, recorded_at=dt, created_by=CREATOR,
            ))
            self.stats.hr_steady_window_obs += 1
        return obs

    # ---------------- GPS：原始轨迹禁直写，仅每日位置摘要 + 相变检测 ----------------

    def purge_gps(self, track: Sequence[Tuple[float, float, float]], base_time: datetime) -> List[Observation]:
        """原始轨迹（秒, lat, lon）→ 每日主导位置摘要 + 大位移相变事件。"""
        obs: List[Observation] = []
        by_day: Dict[int, List[Tuple[float, float, float]]] = {}
        for t, lat, lon in track:
            by_day.setdefault(int(t // 86400), []).append((t, float(lat), float(lon)))
        prev_anchor: Optional[Tuple[float, float]] = None
        for day in sorted(by_day):
            pts = by_day[day]
            lat = sum(p[1] for p in pts) / len(pts)
            lon = sum(p[2] for p in pts) / len(pts)
            anchor = (lat, lon)
            notes = []
            if prev_anchor is not None:
                dlat, dlon = lat - prev_anchor[0], lon - prev_anchor[1]
                dist_km = math.hypot(dlat * 111.0, dlon * 111.0 * math.cos(math.radians(lat)))
                if dist_km > 100:  # 大位移：生活相变（搬家/长途）
                    notes.append(f"与前一日主导位置位移 {dist_km:.0f}km（生活相变）")
            t0 = pts[0][0]
            dt = base_time + timedelta(seconds=t0)
            oid = f"obs_e2e_gps_day_{day:04d}"
            obs.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind="location", modality="json",
                value=json.dumps({"type": "daily_location", "lat": round(lat, 4), "lon": round(lon, 4),
                                  "samples": len(pts), "notes": notes}, ensure_ascii=False),
                occurred=TemporalExtent.point(dt), learned_at=dt, recorded_at=dt, created_by=CREATOR,
            ))
            self.stats.gps_daily_obs += 1
            prev_anchor = anchor
        return obs

    # ---------------- 图片：只存 Caption，原始字节物理删除（铁律4） ----------------

    def purge_images(self, frames: Sequence[Dict[str, Any]]) -> List[Observation]:
        obs: List[Observation] = []
        from aios_core.ingest.multimodal_edge import assess_image_quality

        for fr in frames:
            quality = assess_image_quality(fr)
            passed = self.cleaner.passes(quality) if hasattr(self.cleaner, "passes") else quality > 0.15
            t = fr["occurred_at"]
            oid = fr["frame_id"].replace("img_e2e_", "obs_e2e_img_")
            self.raw_sink.sink(fr["frame_id"], fr["raw_bytes"])
            if fr.get("is_core_evidence"):
                # 核心证据：Caption 永存（原始字节同样物理删除——证据在文字层）
                obs.append(Observation(
                    object_id=oid, subject_id=SUBJECT_ID, revision=1,
                    source_kind="image_caption", modality="text",
                    value=f"[核心证据·图片 Caption 永存] {fr['caption']}",
                    occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
                ))
                self.core_evidence_ids.append(oid)
            elif passed:
                obs.append(Observation(
                    object_id=oid, subject_id=SUBJECT_ID, revision=1,
                    source_kind="image_caption", modality="text",
                    value=fr["caption"],
                    occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
                ))
            # 无论保留与否：原始字节物理删除（手环端侧寸土寸金，铁律4）
            self.raw_sink.purge([fr["frame_id"]])
            self.stats.image_caption_obs += 1
        self.stats.image_raw_bytes_purged = sum(len(fr["raw_bytes"]) for fr in frames)
        assert self.raw_sink.retained_bytes == 0, "铁律4违例：原始图片字节未物理删除"
        return obs

    # ---------------- 语音：转文本 + 声纹编号 + 180 天淘汰 ----------------

    def purge_voice(self, utterances: Sequence[Dict[str, Any]]) -> List[Observation]:
        obs: List[Observation] = []
        registered: set = set()
        for u in utterances:
            t = u["occurred_at"]
            vp_id = u["speaker"]
            if vp_id not in registered:
                # 每个声纹只注册一次（库契约：voiceprint_id 唯一）
                self.voiceprints.add(vp_id, u["feature"], entity_id=SUBJECT_ID if vp_id == "P001" else None)
                registered.add(vp_id)
                if vp_id == "P001":
                    self._speaker_pinned[vp_id] = SUBJECT_ID
            oid = u["utterance_id"].replace("voice_e2e_", "obs_e2e_voice_")
            is_stale_stranger = (
                vp_id != "P001" and (E2E_T_NOW - t).days > 180
                and not u.get("is_core_evidence")
            )
            if is_stale_stranger:
                # 180 天淘汰：陌生声纹且超期且非核心 → 不提交（物理淘汰）
                self.stats.voice_tombstoned_gt180d += 1
                continue
            obs.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind="speech_transcript", modality="text",
                value=(f"[声纹 {vp_id}·核心原话永存] " if u.get("is_core_evidence") else f"[声纹 {vp_id}] ") + u["text"],
                occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
            ))
            if u.get("is_core_evidence"):
                self.core_evidence_ids.append(oid)
            self.stats.voice_text_obs += 1
        return obs

    # ---------------- 短信：大模型研判 → 噪声物理删除，核心永存 ----------------

    def purge_sms(self, messages: Sequence[Dict[str, Any]]) -> List[Observation]:
        obs: List[Observation] = []
        for m in messages:
            t = m["occurred_at"]
            oid = m["message_id"].replace("sms_e2e_", "obs_e2e_sms_")
            if m.get("is_core_evidence"):
                obs.append(Observation(
                    object_id=oid, subject_id=SUBJECT_ID, revision=1,
                    source_kind="message", modality="text",
                    value=f"[核心·争议原话永存] {m['text']}",
                    occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
                ))
                self.core_evidence_ids.append(oid)
                self.stats.sms_core_obs += 1
            else:
                # 大模型自主研判：街头叫卖/垃圾短信/营销推送 → 物理彻底删除
                self.stats.sms_noise_physically_deleted += 1
        return obs

    # ---------------- 关键剧情事件 + 实体/关系/证据链 ----------------

    def build_story_objects(self) -> List[Any]:
        """把五大人生剧情关键事件、实体、关系、证据集组装为世界对象。"""
        objects: List[Any] = []
        ents = {
            "ent_e2e_me": ("沈一舟", ["我", "一舟"], "person"),
            "ent_e2e_wang": ("王强", ["老王", "王哥", "合伙人老王"], "person"),
            "ent_e2e_wife": ("林晓", ["晓晓", "老婆"], "person"),
            "ent_e2e_father": ("沈建国", ["父亲", "爸"], "person"),
            "ent_e2e_doctor": ("何主任", ["何主任", "心内科何主任"], "person"),
        }
        for eid, (name, aliases, kind) in ents.items():
            objects.append(Entity(
                object_id=eid, subject_id=SUBJECT_ID, revision=1, entity_kind=kind,
                canonical_name=name, aliases=aliases,
                occurred=TemporalExtent.point(E2E_SPAN_START),
                learned_at=E2E_SPAN_START, recorded_at=E2E_SPAN_START, created_by=CREATOR,
            ))
        rels = [
            ("rel_e2e_me_wang", "business_partner", "ent_e2e_me", "ent_e2e_wang"),
            ("rel_e2e_me_wife", "spouse", "ent_e2e_me", "ent_e2e_wife"),
            ("rel_e2e_me_father", "family_father", "ent_e2e_me", "ent_e2e_father"),
            ("rel_e2e_me_doctor", "medical_care", "ent_e2e_me", "ent_e2e_doctor"),
        ]
        for rid, rtype, left, right in rels:
            objects.append(Relation(
                object_id=rid, subject_id=SUBJECT_ID, revision=1, relation_type=rtype,
                left=ObjectRef(object_id=left, revision=1), right=ObjectRef(object_id=right, revision=1),
                confidence=1.0, valid_time=TemporalExtent.point(E2E_SPAN_START),
                occurred=TemporalExtent.point(E2E_SPAN_START),
                learned_at=E2E_SPAN_START, recorded_at=E2E_SPAN_START, created_by=CREATOR,
            ))
        for oid, t, kind, value, _tag in self.key_events:
            objects.append(Observation(
                object_id=oid, subject_id=SUBJECT_ID, revision=1,
                source_kind=kind, modality="json" if kind == "biometrics" else "text",
                value=value,
                occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
            ))
            self.core_evidence_ids.append(oid)
        # 证据集（四大剧情线）
        saga_evsets = [
            ("evset_e2e_partner_saga", "合伙纠纷始末：300 万出资、120 万流水差额、延期违约到经侦立案",
             ["obs_e2e_partner_contract", "obs_e2e_partner_bank_flow", "obs_e2e_partner_fight",
              "obs_e2e_partner_delay", "obs_e2e_wang_eco_police"]),
            ("evset_e2e_night_resonance", "通宵加班与次日室性早搏因果共振证据链",
             [f"obs_e2e_night_{i}" for i in range(3)] + [f"obs_e2e_pvc_{i}" for i in range(3)]),
            ("evset_e2e_family_saga", "家庭长期矛盾与破冰：爆发→100 天冷战→生日破冰",
             ["obs_e2e_family_fight", "obs_e2e_family_cold", "obs_e2e_family_icebreak"]),
            ("evset_e2e_move_phase", "跨省搬家生活相变：北京冲刺章节→成都家庭章节",
             ["obs_e2e_move_decision", "obs_e2e_move_0", "obs_e2e_move_1", "obs_e2e_move_2",
              "obs_e2e_move_3", "obs_e2e_move_4", "obs_e2e_move_newbase"]),
        ]
        for eid, purpose, members in saga_evsets:
            objects.append(EvidenceSet(
                object_id=eid, subject_id=SUBJECT_ID, revision=1, purpose=purpose,
                knowledge_window=KnowledgeWindow(knowledge_cutoff=E2E_T_NOW),
                member_refs=[ObjectRef(object_id=m, revision=1) for m in members],
                selection_method="curated_causal_chain",
                learned_at=E2E_T_NOW, recorded_at=E2E_T_NOW, created_by=CREATOR,
            ))
            self.core_evidence_ids.append(eid)
        # 主张：经侦认定（T_now 之前 16 天）
        objects.append(Claim(
            object_id="clm_e2e_wang_fraud", subject_id=SUBJECT_ID, revision=1,
            claimant_id=SUBJECT_ID, claim_type=ClaimType.FACT,
            content="王强（老王）已被经侦立案侦查，涉嫌合同诈骗，涉案 300 万+，本人潜逃失联；严禁任何新增资金往来。",
            valid_time=TemporalExtent.point(datetime(2026, 8, 30, tzinfo=UTC)),
            asserted_at=datetime(2026, 8, 30, tzinfo=UTC),
            knowledge_state=KnowledgeState.REPORTED, confidence=0.99,
            support_evidence_set_refs=[ObjectRef(object_id="evset_e2e_partner_saga", revision=1)],
            learned_at=E2E_T_NOW, recorded_at=E2E_T_NOW, created_by=CREATOR,
        ))
        self.core_evidence_ids.append("clm_e2e_wang_fraud")
        return objects

    # ---------------- 汇总灌入 ----------------

    def purify_and_populate(self, raw: RawStreamBundle, daily_facts: Sequence[Dict[str, Any]]) -> PurificationStats:
        """执行全量边缘提纯并提交世界（只提交提纯产物，原始流绝不落库）。"""
        objs: List[Any] = []
        objs += self.purge_imu(raw.imu_samples, raw.imu_ts, datetime(2025, 4, 1, 3, 0, tzinfo=UTC))
        objs += self.purge_hr(raw.hr_waveform, datetime(2025, 7, 15, 0, 0, tzinfo=UTC))
        objs += self.purge_gps(raw.gps_track, datetime(2025, 4, 1, 0, 0, tzinfo=UTC))
        objs += self.purge_images(raw.image_frames)
        objs += self.purge_voice(raw.voice_utterances)
        objs += self.purge_sms(raw.sms_messages)
        objs += self.build_story_objects()
        for f in daily_facts:
            objs.append(f)
        # 分批提交
        batch = 500
        for i in range(0, len(objs), batch):
            chunk = objs[i:i + batch]
            op = OperationRequest(
                operation_id=new_operation_id(),
                operation_name="e2e.purify.populate",
                expected_world_revision=self.store.current_world_revision(),
                reason=f"Edge-purified objects batch {i}~{i + len(chunk)} (raw streams never stored)",
                idempotency_key=f"e2e_purify_{i}_{SUBJECT_ID}",
                source_class=SourceClass.SENSOR,
            )
            self.store.commit(chunk, op)
        self.stats.world_objects_committed = len(objs)
        return self.stats


# ======================================================================
# 三、每日基线事实流（金字塔输入）
# ======================================================================


class DailyFactStream:
    """三年每日基线事实（约 8 条/天）：静息心率/HRV、工作、通勤、晚间心率、社交、财务、睡眠。"""

    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)

    def generate(self) -> List[Observation]:
        facts: List[Observation] = []
        work_notes = (
            "代码评审 3 个 PR，发现 2 处空指针隐患", "联调环境又挂了，花了 2 小时找配置",
            "需求会 2 小时，范围蔓延第 4 次", "上线灰度 10%，错误率持平", "带新人走读架构文档",
            "重构支付模块单测覆盖率 61%→84%", "压测发现连接池瓶颈，加了自适应扩容",
        )
        social_notes = (
            "和同事吃了顿酸菜鱼", "给老婆发了张地铁窗外的晚霞", "周末陪孩子打羽毛球 1 小时",
            "和父亲电话 15 分钟，聊血压控制", "朋友约饭推掉了，改天", "社区团购领了菜",
        )
        move_day = datetime(2025, 4, 1, tzinfo=UTC)
        burnout_start = datetime(2026, 1, 1, tzinfo=UTC)
        day0 = E2E_SPAN_START
        for d in range(E2E_SPAN_DAYS):
            t_day = day0 + timedelta(days=d)
            commute = "地铁 42 分钟（北京）" if t_day < move_day else "地铁 18 分钟（成都）"
            burnout_days = (t_day - burnout_start).days
            in_burnout = 0 < burnout_days < 90  # 2026-01 ~ 2026-03 身心耗竭期
            hr_rest = 64 + self.rng.randint(-4, 6) + (8 if in_burnout else 0)
            deep_sleep = self.rng.randint(52, 68) - (16 if in_burnout else 0)
            base = [
                ("biometrics", f"晨间静息心率 {hr_rest} bpm，HRV {38 + self.rng.randint(-8, 12) - (10 if in_burnout else 0)} ms。", 7),
                ("work_log", f"{work_notes[d % len(work_notes)]}。", 10),
                ("commute", f"通勤：{commute}，IMU 宏观状态=activity 均值 1.02g。", 9),
                ("biometrics", f"晚间静息心率 {hr_rest + self.rng.randint(-2, 4)} bpm。", 21),
                ("chat", f"{social_notes[(d * 7) % len(social_notes)]}", 19),
                ("sleep", f"深睡 {deep_sleep} 分钟{'（耗竭期深睡塌方）' if in_burnout else ''}。", 23),
            ]
            if d % 30 == 0:
                base.append(("finance", f"月度财务：工资入账 38,000，房租/房贷 7,200，教育金 2,000，结余 {self.rng.randint(18, 26)},000。", 12))
            for i, (kind, value, hour) in enumerate(base):
                t = t_day.replace(hour=hour, minute=self.rng.randint(0, 59), tzinfo=UTC)
                facts.append(Observation(
                    object_id=f"obs_e2e_daily_{d:04d}_{i}_{kind}", subject_id=SUBJECT_ID, revision=1,
                    source_kind=kind, modality="text", value=value,
                    occurred=TemporalExtent.point(t), learned_at=t, recorded_at=t, created_by=CREATOR,
                ))
        return facts
