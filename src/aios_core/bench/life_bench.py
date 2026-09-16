"""Massive Synthetic Life Bench —— 对抗性生命数据发生器（盲测军令核心）。

工单红线：绝对禁止"自己出题自己答"。本发生器与被测管线完全解耦：

* 生成器持有**真值卷宗（BenchManifest）**——哪些音频是合同承诺原话、
  哪些是街头叫卖噪声、摔倒冲击落在哪个窗口、银行流水链有哪五环、
  搬家相变发生在第几天——全部由独立种子在生成期封存；
* 被测管线（摄入/清洗/金字塔/共振/……）对卷宗**不可见**，其输出
  一律对照卷宗裁决，满分路径是"管线真的找到了"，而非"测试写了 mock"；
* 五大人生切片：创业合伙纠纷、大厂通宵心律失常、家庭长期矛盾与破冰、
  跨省搬家与生活相变、慢性病长周期管理。全部高熵商业/工业实战语料，
  严禁低幼化样例。

原始样本量纲：full 档 3 年 × 5 切片 ≈ 110 万+ 原始采样点
（IMU 波形点 / 心率 5 分钟槽 / 语音转写碎片 / 图片帧 / 短信通知），
清洗后应收敛 1~2 个数量级——这正是阶段一的存在意义。
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "RawSample",
    "BenchManifest",
    "BenchWorld",
    "MassiveLifeBench",
    "SLICE_ALL",
]

SliceId = Literal["startup_dispute", "bigtech_overnight", "family_thaw", "province_move", "chronic_care"]

SLICE_ALL: tuple[str, ...] = (
    "startup_dispute",
    "bigtech_overnight",
    "family_thaw",
    "province_move",
    "chronic_care",
)

#: IMU 一个采集窗内的波形点数（50Hz × 1s 压缩窗）。
IMU_WINDOW_POINTS = 50
#: 冲击日（摔倒/撞击剧本）额外全速率采样的窗口数。
IMU_BURST_WINDOWS = 60

_T0_YEAR = 2023


def _iso_day(day_index: int) -> str:
    """day_index(0-based) → ISO 日期（基准 2023-01-01）。"""
    from datetime import date, timedelta

    return (date(_T0_YEAR, 1, 1) + timedelta(days=day_index)).isoformat()


@dataclass(frozen=True, slots=True)
class RawSample:
    """一条原始采样（未清洗层）。

    stream 取值：imu / heart_rate / audio / image / sms。
    payload 语义随 stream 变化（元组，免对象开销）。
    """

    seq: int
    slice_id: str
    day: int
    sec: float
    stream: str
    payload: tuple


@dataclass(slots=True)
class BenchManifest:
    """真值卷宗：生成期封存，管线输出据此裁决（对抗 Oracle）。"""

    total_raw_count: int = 0
    evidence_audio_ids: set[str] = field(default_factory=set)
    noise_audio_ids: set[str] = field(default_factory=set)
    evidence_sms_ids: set[str] = field(default_factory=set)
    noise_sms_ids: set[str] = field(default_factory=set)
    image_frame_ids: set[str] = field(default_factory=set)
    #: (slice_id, day, window_id, peak_g) —— 摔倒/冲击剧本
    impact_events: list[tuple[str, int, int, float]] = field(default_factory=list)
    #: (slice_id, day, slot_index, bpm) —— 心率突变剧本
    hr_spikes: list[tuple[str, int, int, int]] = field(default_factory=list)
    #: 合伙借贷流水链五环（claim id 依序）
    loan_chain_ids: list[str] = field(default_factory=list)
    fraud_verdict_day: int | None = None
    #: 跨省搬家相变日（province_move 切片内 day index）
    move_boundary_day: int | None = None
    #: 搬家后静息心率基线漂移（+bpm）
    move_baseline_shift_bpm: float = 0.0
    #: 慢性病切片收缩压长期斜率（mmHg/年）
    chronic_sbp_slope_per_year: float = 0.0
    #: 期望声纹簇：speaker_key -> 期望簇标签前缀（P001..）
    speaker_registry: dict[str, str] = field(default_factory=dict)
    #: 10 年合伙史（阶段五老王案）：观察记录与 500 个总结节点
    history_observations: list[tuple[int, str, str]] = field(default_factory=list)  # (year, obs_id, text)
    history_summary_nodes: list[tuple[str, int, str]] = field(default_factory=list)  # (node_id, year, text)

    def raw_count(self) -> int:
        return self.total_raw_count


@dataclass(slots=True)
class BenchWorld:
    """一次生成的完整盲测世界（原始流 + 卷宗）。"""

    days: int
    slices: tuple[str, ...]
    samples: list[RawSample]
    manifest: BenchManifest

    def raw_count(self) -> int:
        return self.manifest.total_raw_count


# ----------------------------------------------------------------------
# 高熵语料池（商业/工业实战口径，禁止低幼化）
# ----------------------------------------------------------------------

_EVIDENCE_AUDIO: dict[str, list[str]] = {
    "startup_dispute": [
        "（{spk}）合同补充协议我再说一遍：技术股百分之二十，{year}年三月起算，回购价按上一轮融资金额八折。",
        "（{spk}）这五百万是我个人打给公司的过桥款，流水你让财务直接调，{year}年十一月十二日到账。",
        "（{spk}）供应商对赌条款我签了，但个人连带担保那条必须删掉，我是来做产品的不是来坐牢的。",
        "（{spk}）董事会纪要写清楚：知识产权质押给银行这事，全体股东知情同意，{year}年六月五日。",
        "（{spk}）账期压到九十天是底线，再短资金链三月必断，这话我在这间办公室说过不止一次。",
    ],
    "bigtech_overnight": [
        "（{spk}）医生原话：连续两周凌晨三点后入睡，室性早搏负荷会继续抬升，先停两个迭代周期。",
        "（{spk}）上线预案我口述留档：灰度百分之五，回滚开关在运维台第二页，异常三十秒内切流。",
        "（{spk}）体检报告解读：动态心电图四千二百次室早，伴二联律趋势，建议心内科门诊复查。",
    ],
    "family_thaw": [
        "（{spk}）冷战第二十三天你第一次开口：孩子的幼儿园面试我不能缺席，这一条我们都没有异议。",
        "（{spk}）婚姻咨询师生原话记录：你们的问题不是感情没了，是十年里从没把账算开过。",
        "（{spk}）和解那天她说：下周开始每人每周留一晚给自己，谁也别查岗，试三个月。",
    ],
    "province_move": [
        "（{spk}）搬家公司合同写明：全程丢损按申报价值赔付，钢琴单独加保四千块。",
        "（{spk}）新城市第一通社区医院电话：慢性病建档需要原居地的用药记录原件。",
        "（{spk}）房东押金条我拍照存档：{year}年八月一日起租，押二付一，家电清单七项。",
    ],
    "chronic_care": [
        "（{spk}）心内科随访医嘱：苯磺酸氨氯地平每日五毫克，晨起服，三个月后复查动态血压。",
        "（{spk}）营养科处方原话：钠摄入压到每日五克以下，外卖一周不超过两次，先执行八周看曲线。",
        "（{spk}）复查结论：颈动脉斑块低回声，超医生说两年内没长大，继续药物控制不用介入。",
    ],
}

_NOISE_AUDIO: tuple[str, ...] = (
    "（环境）楼下地库门口喇叭循环：旧冰箱旧彩电上门回收，高价收现金。",
    "（环境）商场中庭促销广播：全场秋冬新品第二件半价，活动最后三天。",
    "（环境）电梯间广告屏外放：学三天，月入过万，名额有限速来。",
    "（环境）路边烧烤摊划拳喧哗与酒瓶碰撞，无法辨识语义。",
)

_NOISE_SMS: tuple[str, ...] = (
    "【xx金融】您的备用金额度已提升至80000元，点击链接即日提现，回T退订。",
    "【xx商城】双十一年终庆：抢2026元神券，爆款清仓一折起。",
    "【xx车管】您的车辆年检即将到期？代办理赔加微信速办。",
    "【xx彩票】内幕胆码免费领，昨日会员跟单盈利百分之三百。",
)

_EVIDENCE_SMS: dict[str, list[str]] = {
    "startup_dispute": [
        "【xx银行】您尾号8821账户{year}年11月12日转账支出500000.00元，对方：xx合伙企业，摘要：过桥款。",
        "【xx银行】您尾号8821账户{year}年02月03日收到转账200000.00元，对方：周某，摘要：还款第一期。",
        "【xx税务】您单位{year}年度企业所得税汇算已受理，应补税额137000.00元，请按期缴纳。",
    ],
    "bigtech_overnight": [
        "【xx健康】您的年度体检报告已出：心电图结论「窦性心律，室性早搏」，建议专科就诊。",
        "【xx办公】值班排班：您本周通宵值守周二、周四生产发布窗口，记得索取调休。",
    ],
    "province_move": [
        "【xx物流】您的搬家运单8327已签收，钢琴一件，签收人本人，如有异常48小时内申诉。",
        "【xx政务】您的新居住证审核通过，有效期至{year_plus3}年，请妥善保管电子凭证。",
    ],
    "chronic_care": [
        "【xx药房】您的处方药续方配送已发出：苯磺酸氨氯地平片 5mg×28片×3盒。",
        "【xx医院】您已预约{year}年季度心血管专科随访门诊，请携带动态血压报告。",
    ],
    "family_thaw": [
        "【xx教育】幼儿园面试确认：您的孩子面试时段为周六上午十点，请携带户口簿。",
    ],
}

_DISPUTE_CHAT: tuple[str, ...] = (
    "（{spk}）你现在跟我谈情谊？公司账上一千四百万流出你一笔一笔给我说清楚！",
    "（{spk}）撕破脸就不必装了，银行流水我全部拉出来了，{year}年那笔过桥款你到底转去了哪。",
    "（{spk}）行，那就法院见，欠条、流水、录音，我一样都不缺。",
)

_WORK_TOPICS: tuple[str, ...] = (
    "支付网关重构排期评审", "生产故障复盘会", "代码评审与发布窗口", "供应商对赌条款评审", "账期压力协调会",
)


class MassiveLifeBench:
    """确定性对抗发生器：同参数跨进程逐位一致（zlib.crc32 种子）。"""

    def __init__(
        self,
        *,
        days: int = 1096,
        slices: tuple[str, ...] = SLICE_ALL,
        seed: int = 20260916,
        density: Literal["full", "mid"] = "full",
    ) -> None:
        if days < 30:
            raise ValueError("days must be >= 30")
        unknown = [s for s in slices if s not in SLICE_ALL]
        if unknown:
            raise ValueError(f"unknown slices: {unknown}")
        self._days = days
        self._slices = slices
        self._seed = seed
        self._density = density

    # ---- 公共参数 -------------------------------------------------------

    @property
    def imu_windows_per_day(self) -> int:
        return 12 if self._density == "full" else 2

    @property
    def hr_slots_per_day(self) -> int:
        return 288 if self._density == "full" else 48

    # ---- 主入口 ---------------------------------------------------------

    def generate(self) -> BenchWorld:
        manifest = BenchManifest()
        samples: list[RawSample] = []
        seq = 0
        if "province_move" in self._slices:
            self._move_day = 700   # 相变日：跨省搬家（基线漂移锚点）
        base_vecs = self._speaker_base_vectors()
        manifest.speaker_registry.update(
            {k: f"P{i + 1:03d}" for i, k in enumerate(sorted(base_vecs))}
        )
        for day in range(self._days):
            for slice_id in self._slices:
                rng = random.Random(f"{self._seed}:{slice_id}:{day}")
                year = _T0_YEAR + day // 365
                spk = self._main_speaker(slice_id)
                bv = base_vecs[spk]
                # -- IMU 波形窗 ------------------------------------------------
                burst = self._impact_day(slice_id, day)
                windows = self.imu_windows_per_day + (IMU_BURST_WINDOWS if burst else 0)
                for w in range(windows):
                    vals, peak = self._imu_window(rng, burst and w >= self.imu_windows_per_day)
                    samples.append(RawSample(
                        seq=seq, slice_id=slice_id, day=day, sec=(w * 2400.0) % 86400.0,
                        stream="imu", payload=(w, vals),
                    ))
                    seq += 1
                    if burst and peak >= 2.6:
                        manifest.impact_events.append((slice_id, day, w, round(peak, 2)))
                # -- 心率 5 分钟槽 --------------------------------------------
                baseline = self._hr_baseline(slice_id, day)
                for slot in range(self.hr_slots_per_day):
                    jitter = rng.uniform(-4.0, 4.0)
                    spike = self._hr_spike_bpm(slice_id, day, slot)
                    bpm = baseline + jitter + spike
                    samples.append(RawSample(
                        seq=seq, slice_id=slice_id, day=day, sec=slot * 300.0,
                        stream="heart_rate", payload=(round(bpm, 1),),
                    ))
                    seq += 1
                    if spike > 0:
                        manifest.hr_spikes.append((slice_id, day, slot, int(bpm)))
                # -- 音频转写碎片（证据 + 噪声） --------------------------------
                audio_items = self._audio_plan(rng, slice_id, day, year, spk, base_vecs)
                for i, (text, vec, is_core, speaker_key, theme) in enumerate(audio_items):
                    fid = f"{slice_id}-audio-d{day:05d}-{i:02d}"
                    samples.append(RawSample(
                        seq=seq, slice_id=slice_id, day=day,
                        sec=(3600.0 + i * 1700.0) % 86400.0,
                        stream="audio", payload=(fid, text, vec, is_core, speaker_key, theme),
                    ))
                    seq += 1
                    if is_core:
                        manifest.evidence_audio_ids.add(fid)
                    else:
                        manifest.noise_audio_ids.add(fid)
                # -- 图片帧（只存 Caption） ------------------------------------
                for i in range(rng.randint(2, 8)):
                    fid = f"{slice_id}-img-d{day:05d}-{i:02d}"
                    quality = round(rng.uniform(0.2, 0.95), 3)
                    caption = f"{_iso_day(day)} 抓拍：{self._image_caption(rng, slice_id)}"
                    samples.append(RawSample(
                        seq=seq, slice_id=slice_id, day=day,
                        sec=(40000.0 + i * 900.0) % 86400.0,
                        stream="image",
                        payload=(fid, caption, rng.randint(2048, 6144), quality),
                    ))
                    seq += 1
                    manifest.image_frame_ids.add(fid)
                # -- 短信/通知 ---------------------------------------------------
                for i in range(rng.randint(12, 36)):
                    pool_ev = _EVIDENCE_SMS.get(slice_id, ())
                    if pool_ev and rng.random() < 0.28:
                        text = rng.choice(pool_ev).format(year=year, year_plus3=year + 3)
                        sid = f"{slice_id}-sms-d{day:05d}-{i:02d}"
                        samples.append(RawSample(
                            seq=seq, slice_id=slice_id, day=day, sec=(i * 2100.0) % 86400.0,
                            stream="sms", payload=(sid, text, True),
                        ))
                        seq += 1
                        manifest.evidence_sms_ids.add(sid)
                    else:
                        text = rng.choice(_NOISE_SMS)
                        sid = f"{slice_id}-sms-d{day:05d}-{i:02d}"
                        samples.append(RawSample(
                            seq=seq, slice_id=slice_id, day=day, sec=(i * 2100.0) % 86400.0,
                            stream="sms", payload=(sid, text, False),
                        ))
                        seq += 1
                        manifest.noise_sms_ids.add(sid)
        # -- 剧情卷宗封存 ------------------------------------------------------
        self._seal_plots(manifest)
        self._seal_partner_history(manifest)
        manifest.total_raw_count = self._count_raw_points(samples)
        return BenchWorld(
            days=self._days, slices=self._slices, samples=samples, manifest=manifest
        )

    # ---- 生成细节 ---------------------------------------------------------

    def _count_raw_points(self, samples: list[RawSample]) -> int:
        total = 0
        for s in samples:
            if s.stream == "imu":
                total += len(s.payload[1])
            else:
                total += 1
        return total

    def _speaker_base_vectors(self) -> dict[str, list[float]]:
        rng = random.Random(f"{self._seed}:voiceprint")
        return {
            key: [rng.gauss(0.0, 1.0) for _ in range(32)]
            for key in ("founder", "partner", "spouse", "doctor", "boss")
        }

    def _main_speaker(self, slice_id: str) -> str:
        return {
            "startup_dispute": "founder",
            "bigtech_overnight": "boss",
            "family_thaw": "spouse",
            "province_move": "founder",
            "chronic_care": "doctor",
        }[slice_id]

    def _impact_day(self, slice_id: str, day: int) -> bool:
        """摔倒/冲击剧本日：大厂切片低频真冲击；其它切片偶发轻微磕碰。"""
        if slice_id == "bigtech_overnight":
            return day in (214, 617, 933)
        if slice_id == "chronic_care":
            return day in (880,)
        return day in (777,) and slice_id == "province_move"

    def _imu_window(self, rng: random.Random, burst: bool) -> tuple[list[float], float]:
        """冲击日仅 ~5% 窗口含真实冲击尖峰（其余为活动增强窗），防真值注水。"""
        if burst and rng.random() < 0.05:
            base = [abs(rng.gauss(1.0, 0.35)) for _ in range(IMU_WINDOW_POINTS)]
            peak_idx = rng.randrange(10, IMU_WINDOW_POINTS - 10)
            peak = rng.uniform(2.6, 4.2)
            base[peak_idx] = peak
            base[peak_idx + 1] = peak * 0.6
        elif burst:
            base = [abs(rng.gauss(0.8, 0.3)) for _ in range(IMU_WINDOW_POINTS)]
            peak = max(base)
        else:
            base = [abs(rng.gauss(0.35, 0.12)) for _ in range(IMU_WINDOW_POINTS)]
            peak = max(base)
        return base, peak

    def _hr_baseline(self, slice_id: str, day: int) -> float:
        base = {
            "startup_dispute": 71.0, "bigtech_overnight": 68.0, "family_thaw": 70.0,
            "province_move": 69.0, "chronic_care": 74.0,
        }[slice_id]
        if slice_id == "province_move" and self._move_day is not None and day >= self._move_day:
            base += 6.0
        return base

    _move_day: int | None = None  # generate() 内部覆写，供基线漂移使用

    def _hr_spike_bpm(self, slice_id: str, day: int, slot: int) -> float:
        if slice_id == "bigtech_overnight" and day in (213, 214, 616, 617, 932, 933):
            if slot in (168, 169, 170):   # 凌晨 14:00 后第 168 槽 ≈ 通宵窗口
                return 52.0
        if slice_id == "startup_dispute" and day in (1042, 1043):
            if slot in (100, 101):
                return 44.0
        return 0.0

    def _audio_plan(
        self,
        rng: random.Random,
        slice_id: str,
        day: int,
        year: int,
        spk: str,
        base_vecs: dict[str, list[float]],
    ) -> list[tuple[str, list[float], bool, str, str]]:
        """一天内的音频碎片计划：证据 / 争议 / 噪声混合，声纹向量按说话人聚类。"""
        items: list[tuple[str, list[float], bool, str, str]] = []
        n = rng.randint(6, 24)
        # 证据概率：各切片在各自剧情日附近加密
        evidence_prob = 0.22
        if slice_id == "startup_dispute" and day in (430, 431, 1042, 1043):
            evidence_prob = 0.9
            chat = _DISPUTE_CHAT[(day + 0) % len(_DISPUTE_CHAT)]
            items.append((
                chat.format(spk="合伙人", year=year),
                self._voice_vec(rng, base_vecs["partner"]),
                True, "partner", "dispute_quote",
            ))
        if slice_id == "bigtech_overnight" and day in (215, 618):
            evidence_prob = 0.85
        if slice_id == "family_thaw" and day in (520, 521, 700):
            evidence_prob = 0.8
        for i in range(n - len(items)):
            roll = rng.random()
            if roll < evidence_prob:
                text = rng.choice(_EVIDENCE_AUDIO[slice_id]).format(spk=spk, year=year)
                items.append((text, self._voice_vec(rng, base_vecs[spk]), True, spk, "evidence"))
            elif roll < evidence_prob + 0.18:
                text = rng.choice(_NOISE_AUDIO)
                items.append((text, self._voice_vec(rng, None), False, "ambient", "noise"))
            else:
                text = f"（{spk}）日常闲聊碎片 {_iso_day(day)} 第{i}段，语义密度低。"
                items.append((text, self._voice_vec(rng, base_vecs[spk]), False, spk, "chatter"))
        return items

    def _voice_vec(self, rng: random.Random, base: list[float] | None) -> list[float]:
        if base is None:
            return [rng.gauss(0.0, 2.5) for _ in range(32)]
        return [b + rng.gauss(0.0, 0.06) for b in base]

    def _image_caption(self, rng: random.Random, slice_id: str) -> str:
        pools = {
            "startup_dispute": ("办公室白板融资排期", "快递纸箱堆叠的前台", "深夜工位双屏代码"),
            "bigtech_overnight": ("机房机柜指示灯", "工位桌面降压药盒", "白板发布检查单"),
            "family_thaw": ("餐桌上的两副碗筷", "幼儿园门口人流", "客厅加湿器与药盒"),
            "province_move": ("贴好封条的纸箱墙", "新居空客厅测量尺", "高速服务区路牌"),
            "chronic_care": ("血压计读数特写", "分装药盒与处方单", "小区步道晨练人群"),
        }
        return rng.choice(pools[slice_id])

    def _seal_plots(self, manifest: BenchManifest) -> None:
        """剧情真值封存：流水链 / 相变日 / 慢病斜率。"""
        if "startup_dispute" in self._slices:
            manifest.loan_chain_ids = [
                "startup_dispute-sms-d00077-03",
                "startup_dispute-sms-d00120-01",
                "startup_dispute-audio-d00430-00",
                "startup_dispute-sms-d00431-02",
                "startup_dispute-audio-d01042-00",
            ]
            manifest.fraud_verdict_day = min(self._days - 1, 1046)
        if "province_move" in self._slices:
            manifest.move_boundary_day = 700
            manifest.move_baseline_shift_bpm = 6.0
        if "chronic_care" in self._slices:
            manifest.chronic_sbp_slope_per_year = 4.5

    def _seal_partner_history(self, manifest: BenchManifest) -> None:
        """阶段五卷宗：10 年合伙史 + 500 个历史总结节点（老王案替身：周某案）。"""
        rng = random.Random(f"{self._seed}:partner_history")
        for year in range(2016, 2026):
            for k in range(50):   # 每年 50 个总结节点 → 共 500
                node_id = f"ph-sum-{year}-{k:02d}"
                text = (
                    f"{year}年第{k + 1}期合伙经营小结：与周某合作共管资金池，"
                    f"当期回款与流水核验一致，信任基线维持。"
                )
                manifest.history_summary_nodes.append((node_id, year, text))
            for k in range(20):   # 每年 20 条观察事实（SHA-256 目标物）
                obs_id = f"ph-obs-{year}-{k:02d}"
                text = (
                    f"{year}年观察{k:02d}：周某经手资金池调拨 {rng.randint(2, 90)} 万元，"
                    f"双方对账签认，原始凭证编号 V{year}{k:02d}。"
                )
                manifest.history_observations.append((year, obs_id, text))


def generate_partner_history_world(
    *, seed: int = 20260916
) -> tuple[list[tuple[int, str, str]], list[tuple[str, int, str]]]:
    """阶段五专用：返回（观察事实，总结节点）两个不可变序列。"""
    m = BenchManifest()
    MassiveLifeBench(days=30, density="mid", seed=seed)._seal_partner_history(m)
    return m.history_observations, m.history_summary_nodes
