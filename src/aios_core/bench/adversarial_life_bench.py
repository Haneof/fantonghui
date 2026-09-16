"""对抗生命数据发生器（Massive Synthetic Life Bench · 独立盲测数据源）。

定位
----
本模块是**被测系统之外**的独立样本发生器：它只依赖标准库，不 import 任何
``aios_core`` 被测实现，因此可以作为"盲测考官"给出**独立真值**
（哪些原话是必须永存的核心证据、哪些是必须物理删除的环境噪声）。

覆盖的人生百态（五条并行叙事主线 + 三层噪声）
--------------------------------------------
1. ``WANG``     创业合伙纠纷：合伙协议 → 借款转账 → 长期拖延 → 撕逼 → 法院裁定；
2. ``OVERTIME`` 大厂通宵心律失常：每两周凌晨通宵 + 咖啡因 → 次日心率骤升与早搏；
3. ``FAMILY``   家庭长期矛盾与破冰：争吵 → 冷战 → 母亲住院 → 道歉承诺；
4. ``MOVE``     跨省搬家与生活相变：深圳退租 → 成都落脚 → 作息基线永久位移；
5. ``CHRONIC``  慢性病长周期管理：季度血压/血糖记录 → 住院 → 指标回落。

噪声层：商圈叫卖、垃圾短信（验证码/营销）、群聊刷屏、路人闲聊、交通轰鸣。
这些噪声是**铁律 4** 的靶子：大模型每日复盘后必须物理删除。

数据量与流式约束
----------------
样本以**生成器（iterator）**逐个吐出，绝不整体驻留内存；``GATE_PROFILE`` 单次
遍历吐出的原始样本数已超过一百万条（IMU 50Hz 高频点按内层采样点计数）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Mapping

__all__ = [
    "BenchProfile",
    "EvidenceBeat",
    "FULL_PROFILE",
    "GATE_PROFILE",
    "KIND_AUDIO",
    "KIND_CHAT",
    "KIND_GPS",
    "KIND_HR",
    "KIND_IMAGE",
    "KIND_IMU",
    "KIND_SMS",
    "MassiveSyntheticLifeBench",
    "RawSample",
    "ROLE_EVIDENCE",
    "ROLE_NOISE",
    "ROLE_ROUTINE",
    "STORY_TITLES",
]

UTC = timezone.utc

KIND_IMU = "imu_burst"
KIND_HR = "heart_rate"
KIND_AUDIO = "audio_utterance"
KIND_IMAGE = "image_capture"
KIND_CHAT = "chat_message"
KIND_GPS = "gps_ping"
KIND_SMS = "sms"

ROLE_EVIDENCE = "evidence"
ROLE_NOISE = "noise"
ROLE_ROUTINE = "routine"

STORY_TITLES: Mapping[str, str] = {
    "WANG": "创业合伙纠纷（合伙→借贷→撕逼→银行流水→法院裁定）",
    "OVERTIME": "大厂通宵心律失常（熬夜→心率骤升→早搏→熔断）",
    "FAMILY": "家庭长期矛盾与破冰（争吵→冷战→住院→道歉承诺）",
    "MOVE": "跨省搬家与人生相变（深圳→成都→作息基线永久位移）",
    "CHRONIC": "慢性病长周期管理（季度指标→住院→好转）",
}


# ---------------------------------------------------------------------------
# 配置档位
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchProfile:
    """发生器档位（决定原始样本量级，不改任何业务语义）。"""

    name: str
    days: int
    imu_bursts_per_day: int
    imu_samples_per_burst: int
    hr_samples_per_day: int
    gps_per_day: int
    audio_per_day: int
    images_per_day: int
    chats_per_day: int
    sms_per_day: int

    @property
    def nominal_samples_per_day(self) -> int:
        return (
            self.imu_bursts_per_day * self.imu_samples_per_burst
            + self.hr_samples_per_day
            + self.gps_per_day
            + self.audio_per_day
            + self.images_per_day
            + self.chats_per_day
            + self.sms_per_day
        )

    @property
    def nominal_sample_total(self) -> int:
        return self.nominal_samples_per_day * self.days


#: pytest 门禁用档位：单次遍历 > 100 万条原始样本，运行时间约束在秒级。
GATE_PROFILE = BenchProfile(
    name="gate",
    days=1095,
    imu_bursts_per_day=1,
    imu_samples_per_burst=800,
    hr_samples_per_day=96,
    gps_per_day=48,
    audio_per_day=40,
    images_per_day=12,
    chats_per_day=30,
    sms_per_day=20,
)

#: 离线全量压测档位（CLI 使用）：单次遍历约 330 万条原始样本。
FULL_PROFILE = BenchProfile(
    name="full",
    days=1095,
    imu_bursts_per_day=3,
    imu_samples_per_burst=1200,
    hr_samples_per_day=288,
    gps_per_day=96,
    audio_per_day=64,
    images_per_day=24,
    chats_per_day=60,
    sms_per_day=48,
)


@dataclass(frozen=True, slots=True)
class EvidenceBeat:
    """叙事主线上的关键事实节拍（独立真值：这一句必须永存）。"""

    story: str
    label: str
    day: int
    channel: str
    text: str
    hour: int = 20
    minute: int = 30
    speaker_token: str | None = None
    learn_lag_days: int = 0

    @property
    def key(self) -> str:
        return f"{self.story}:{self.label}"


@dataclass(frozen=True, slots=True)
class RawSample:
    """一条原始样本（含考官真值；被测系统只能看到盲化视图）。"""

    sequence: int
    kind: str
    occurred_at: datetime
    learned_at: datetime
    payload: Mapping[str, Any]
    role: str
    story: str | None
    evidence_key: str | None

    @property
    def is_ground_truth_evidence(self) -> bool:
        return self.role == ROLE_EVIDENCE

    @property
    def is_ground_truth_noise(self) -> bool:
        return self.role == ROLE_NOISE

    def blinded(self) -> "BlindedSample":
        """剥离一切考官真值字段后的盲化视图（被测系统唯一可见形态）。"""

        return BlindedSample(
            sequence=self.sequence,
            kind=self.kind,
            occurred_at=self.occurred_at,
            learned_at=self.learned_at,
            payload=self.payload,
        )


@dataclass(frozen=True, slots=True)
class BlindedSample:
    """盲化样本：没有 role / story / evidence_key，杜绝系统"偷看答案"。"""

    sequence: int
    kind: str
    occurred_at: datetime
    learned_at: datetime
    payload: Mapping[str, Any]


# ---------------------------------------------------------------------------
# 叙事节拍表（独立真值）
# ---------------------------------------------------------------------------

_EVIDENCE_BEATS: tuple[EvidenceBeat, ...] = (
    # ---------------------------- 创业合伙纠纷 ----------------------------
    EvidenceBeat(
        story="WANG",
        label="pact_signing",
        day=10,
        channel=KIND_AUDIO,
        text="咱俩各出五十万，股份五五分，白纸黑字写下来，亏了一起扛。",
        hour=14,
        minute=10,
        speaker_token="P001",
    ),
    EvidenceBeat(
        story="WANG",
        label="loan_transfer",
        day=12,
        channel=KIND_SMS,
        text="招商银行：您尾号8899账户已向王强转出250000.00元，流水号20230112A。",
        hour=10,
        minute=5,
    ),
    EvidenceBeat(
        story="WANG",
        label="partnership_pact_copy",
        day=12,
        channel=KIND_CHAT,
        text="合伙协议原件我拍了照，借款五十万的借条也在，先存着。",
        hour=22,
        minute=15,
    ),
    EvidenceBeat(
        story="WANG",
        label="delay_excuse",
        day=400,
        channel=KIND_AUDIO,
        text="再宽限两个月，货款一到我立马把钱还你，咱兄弟还说这个？",
        hour=21,
        minute=40,
        speaker_token="P001",
    ),
    EvidenceBeat(
        story="WANG",
        label="dispute_quarrel",
        day=700,
        channel=KIND_AUDIO,
        text="你要是不认这笔账，咱就法庭上见，别怪我翻脸。",
        hour=23,
        minute=5,
        speaker_token="P001",
    ),
    EvidenceBeat(
        story="WANG",
        label="court_ruling",
        day=1000,
        channel=KIND_AUDIO,
        text="判决书下来了，认定合同诈骗，人已经跑了，钱得走追偿程序。",
        hour=15,
        minute=20,
        speaker_token="P002",
    ),
    # ---------------------------- 通宵心律失常 ----------------------------
    EvidenceBeat(
        story="OVERTIME",
        label="overnight_confession",
        day=510,
        channel=KIND_AUDIO,
        text="今晚又要通宵压测，这是我第三杯咖啡了，心口有点发紧。",
        hour=2,
        minute=30,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="OVERTIME",
        label="arrhythmia_diagnosis",
        day=514,
        channel=KIND_AUDIO,
        text="医生说是室性早搏，让我别再熬夜了，再熬就得出大事。",
        hour=11,
        minute=0,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="OVERTIME",
        label="health_promise",
        day=516,
        channel=KIND_CHAT,
        text="说好了这个月十一点前睡，谁再通宵谁请吃饭。",
        hour=23,
        minute=30,
    ),
    # ---------------------------- 家庭矛盾与破冰 ----------------------------
    EvidenceBeat(
        story="FAMILY",
        label="mother_quarrel",
        day=120,
        channel=KIND_AUDIO,
        text="你一年到头回几次家？电话也不接，是我这个妈做得不对吗？",
        hour=19,
        minute=50,
        speaker_token="P001",
    ),
    EvidenceBeat(
        story="FAMILY",
        label="cold_war_note",
        day=240,
        channel=KIND_CHAT,
        text="跟妈冷战三天了，电话一直没回，先冷一冷吧。",
        hour=22,
        minute=40,
    ),
    EvidenceBeat(
        story="FAMILY",
        label="mother_hospitalized",
        day=600,
        channel=KIND_AUDIO,
        text="妈住院了，血压高得压不住，你赶紧回来一趟。",
        hour=8,
        minute=20,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="FAMILY",
        label="apology",
        day=610,
        channel=KIND_AUDIO,
        text="妈，是我错了，以后每周我都回去，你别再生气了。",
        hour=18,
        minute=40,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="FAMILY",
        label="dumpling_promise",
        day=780,
        channel=KIND_CHAT,
        text="答应妈了，今年过年的饺子我来包，我学了两道你爱吃的馅。",
        hour=20,
        minute=10,
    ),
    # ---------------------------- 跨省搬家与相变 ----------------------------
    EvidenceBeat(
        story="MOVE",
        label="resign_decision",
        day=820,
        channel=KIND_AUDIO,
        text="深圳这边的工位今天就退了，下周搬去成都，重新开始。",
        hour=17,
        minute=30,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="MOVE",
        label="arrival_chengdu",
        day=828,
        channel=KIND_AUDIO,
        text="行李都到成都了，新租的房子朝南，窗外有棵很大的银杏。",
        hour=16,
        minute=0,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="MOVE",
        label="new_rhythm",
        day=900,
        channel=KIND_CHAT,
        text="搬到成都后节奏慢多了，晚上十点就困，早上六点自然醒。",
        hour=21,
        minute=0,
    ),
    # ---------------------------- 慢性病长周期 ----------------------------
    EvidenceBeat(
        story="CHRONIC",
        label="bp_reading_q1",
        day=330,
        channel=KIND_CHAT,
        text="今天血压142/92，药还是按时吃的，没敢停。",
        hour=9,
        minute=5,
    ),
    EvidenceBeat(
        story="CHRONIC",
        label="hospitalization",
        day=950,
        channel=KIND_AUDIO,
        text="住院部说血糖控制得还行，让继续打胰岛素，别自己减量。",
        hour=10,
        minute=40,
        speaker_token="P002",
    ),
    EvidenceBeat(
        story="CHRONIC",
        label="recovery_report",
        day=1050,
        channel=KIND_CHAT,
        text="复查结果不错，血糖和血脂的指标都下来了。",
        hour=15,
        minute=30,
    ),
    # ---------------- 迟到补录：三年前旧事今日才说清（三类时间解耦） ----------------
    EvidenceBeat(
        story="FAMILY",
        label="late_discovered_truth",
        day=600,
        channel=KIND_CHAT,
        text="其实妈那年住院前就查出高血压了，一直没敢告诉我。",
        hour=23,
        minute=10,
        learn_lag_days=470,
    ),
)

#: 通宵加班日（每 14 天一次，凌晨 02:00 段；用于心率/IMU 因果共振）
_OVERTIME_STRIDE_DAYS = 14
_OVERTIME_FIRST_DAY = 500
_OVERTIME_LAST_DAY = 640

#: 慢性病季度复查日
_CHRONIC_STRIDE_DAYS = 90
_CHRONIC_FIRST_DAY = 320
_CHRONIC_LAST_DAY = 1090

#: 疑似摔倒撞击日（IMU 冲击波形，触发 P0 硬旁路）
_FALL_DAYS: frozenset[int] = frozenset({260, 640, 880})

#: 搬家相变日：GPS 归属城市在此日切换
_RELOCATION_DAY = 828

_STREET_VENDOR_NOISE: tuple[str, ...] = (
    "（商圈叫卖）新鲜草莓便宜卖啦，十块钱两斤！",
    "（商圈叫卖）烤红薯热乎的，五块钱一个！",
    "（路边音响）全场清仓，买一送一，最后三天！",
    "（街头噪音）来来来，扫码送气球，小朋友过来看看！",
    "（商圈叫卖）现磨豆浆两块钱一杯，热的！",
)

_SMS_NOISE: tuple[str, ...] = (
    "【万客商城】限时秒杀，点击链接领取50元优惠券，退订回T。",
    "【验证码】884812，请勿泄露给任何人。",
    "【金融速贷】无抵押极速放款，额度最高20万，回复1咨询。",
    "【楼盘推广】临湖叠墅最后8套，本周末特价看房。",
    "【会员提醒】您的观影积分将于年底清零，请尽快使用。",
)

_GROUP_FLOOD: tuple[str, ...] = (
    "哈哈哈",
    "收到",
    "++1",
    "今天谁去打球？",
    "已阅",
    "打卡",
    "楼上说得对",
    "表情包",
)

_PASSERBY_CHATTER: tuple[str, ...] = (
    "（路人闲聊）这队排得也太长了吧。",
    "（路人闲聊）听说楼下那家面馆换老板了。",
    "（环境音）地铁进站，请乘客先下后上。",
    "（环境音）电梯超载，请后进乘客退出。",
    "（路人闲聊）今天天气比昨天舒服多了。",
)

_ROUTINE_CHATS: tuple[str, ...] = (
    "中午食堂的菜有点咸，下次换一家。",
    "把周报发群里了，记得看。",
    "下午三点开会，会议室改到5楼。",
    "快递到了，晚上回去取。",
    "楼下便利店买了两瓶水。",
)

_IMAGE_CAPTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("工位上的三杯空咖啡杯与亮着的双屏", ("office", "overtime")),
    ("厨房砧板上摊开的饺子皮和两碗馅", ("family", "kitchen")),
    ("新租房子朝南的窗台与窗外的银杏树", ("home", "chengdu")),
    ("医院走廊的候诊长椅与叫号屏", ("hospital", "waiting")),
    ("商圈人头攒动的步行街与霓虹招牌", ("street", "shopping")),
    ("共享单车上绑着的搬家纸箱", ("street", "moving")),
)

_VOICE_TOKENS: tuple[str, ...] = ("P001", "P002", "UNK_31", "UNK_42", "UNK_77", "UNK_88")

#: 只活跃于前半段时间轴的路人/服务员声纹（用于 180 天冷档案淘汰盲测）。
_TRANSIENT_TOKENS: tuple[str, ...] = ("UNK_77", "UNK_88")
_TRANSIENT_TOKEN_LAST_DAY: int = 220

#: 模拟原始二进制载荷（真实字节、流式即用即焚，绝不留主存储）。
_IMAGE_BYTES: bytes = b"\x89PNG\r\n\x1a\n" + b"f" * 2040
_AUDIO_BYTES: bytes = b"RIFF" + b"a" * 252


class MassiveSyntheticLifeBench:
    """对抗生命数据发生器：确定性、流式、带独立真值。"""

    def __init__(
        self,
        profile: BenchProfile = GATE_PROFILE,
        *,
        seed: int = 20260916,
        t_origin: datetime = datetime(2023, 1, 1, 0, 0, tzinfo=UTC),
    ) -> None:
        if profile.days < 1:
            raise ValueError("profile.days must be >= 1")
        self.profile = profile
        self.seed = int(seed)
        self.t_origin = t_origin.astimezone(UTC)

    # ------------------------------------------------------------------
    # 真值面
    # ------------------------------------------------------------------

    @property
    def beats(self) -> tuple[EvidenceBeat, ...]:
        return _EVIDENCE_BEATS

    def evidence_keys(self) -> frozenset[str]:
        return frozenset(beat.key for beat in _EVIDENCE_BEATS if beat.day < self.profile.days)

    def beats_on_day(self, day: int) -> tuple[EvidenceBeat, ...]:
        return tuple(beat for beat in _EVIDENCE_BEATS if beat.day == day)

    def overtime_days(self) -> tuple[int, ...]:
        return tuple(
            day
            for day in range(_OVERTIME_FIRST_DAY, min(_OVERTIME_LAST_DAY, self.profile.days), _OVERTIME_STRIDE_DAYS)
        )

    def chronic_review_days(self) -> tuple[int, ...]:
        return tuple(
            day
            for day in range(_CHRONIC_FIRST_DAY, min(_CHRONIC_LAST_DAY, self.profile.days), _CHRONIC_STRIDE_DAYS)
        )

    def fall_days(self) -> tuple[int, ...]:
        return tuple(sorted(day for day in _FALL_DAYS if day < self.profile.days))

    def expected_audio_noise_total(self) -> int:
        """每天固定 6 条街头噪声 + 4 条路人闲聊（其余为叙事/日常对话）。"""

        return (6 + 4) * self.profile.days

    def expected_sms_noise_total(self) -> int:
        """垃圾短信与验证码：每天 8 条。"""

        return 8 * self.profile.days

    # ------------------------------------------------------------------
    # 主入口：流式样本迭代
    # ------------------------------------------------------------------

    def iter_samples(self) -> Iterator[RawSample]:
        """按时间顺序流式吐出全部原始样本（内存驻留与天数无关）。"""

        sequence = 0
        profile = self.profile
        for day in range(profile.days):
            rng = random.Random(self.seed * 1_000_003 + day)
            day_start = self.t_origin + timedelta(days=day)
            beats_today = list(self.beats_on_day(day))
            overnight = day in self.overtime_days()
            fall_day = day in self.fall_days()
            chronic_review = day in self.chronic_review_days()

            # ---------------- IMU 高频运动流（绝不入库，仅出宏观状态） ----------------
            for burst_index in range(profile.imu_bursts_per_day):
                hour = 8 + burst_index * 4
                burst_start = day_start + timedelta(hours=hour)
                activity = ("walk", "run", "desk")[burst_index % 3]
                samples = self._imu_samples(
                    rng,
                    count=profile.imu_samples_per_burst,
                    activity=activity,
                    fall=fall_day and burst_index == 0,
                )
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_IMU,
                    occurred_at=burst_start,
                    learned_at=burst_start,
                    payload={
                        "frame_rate_hz": 50.0,
                        "activity": activity,
                        "samples": samples,
                        "t0_seconds": 0.0,
                    },
                    role=ROLE_ROUTINE,
                    story=None,
                    evidence_key=None,
                )
            if overnight:
                overnight_start = day_start + timedelta(hours=2)
                samples = self._imu_samples(rng, count=240, activity="desk", fall=False)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_IMU,
                    occurred_at=overnight_start,
                    learned_at=overnight_start,
                    payload={
                        "frame_rate_hz": 50.0,
                        "activity": "desk",
                        "samples": samples,
                        "t0_seconds": 0.0,
                    },
                    role=ROLE_ROUTINE,
                    story="OVERTIME",
                    evidence_key=None,
                )

            # ---------------- 心率流（平稳期只留均值，突变独立成波形） ----------------
            hr_step_minutes = max(1, 1440 // max(1, profile.hr_samples_per_day))
            for index in range(profile.hr_samples_per_day):
                minute = index * hr_step_minutes
                stamp = day_start + timedelta(minutes=minute)
                local_hour = stamp.hour
                base_bpm = 62.0 if local_hour < 6 else 72.0
                if overnight and 2 <= local_hour < 6:
                    base_bpm = 118.0 + rng.random() * 14.0
                elif local_hour >= 22 or local_hour < 1:
                    base_bpm = 66.0
                bpm = base_bpm + rng.gauss(0.0, 1.2)
                role = ROLE_ROUTINE
                story = None
                if overnight and 2 <= local_hour < 6:
                    role = ROLE_EVIDENCE
                    story = "OVERTIME"
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_HR,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={
                        "bpm": bpm,
                        "signal_quality": 0.9 - rng.random() * 0.1,
                        "context": "overnight_work" if (overnight and local_hour < 6) else "routine",
                    },
                    role=role,
                    story=story,
                    evidence_key=None,
                )

            # ---------------- GPS（搬家相变：城市归属永久切换） ----------------
            gps_step_minutes = max(1, 1440 // max(1, profile.gps_per_day))
            city = "CD" if day >= _RELOCATION_DAY else "SZ"
            for index in range(profile.gps_per_day):
                stamp = day_start + timedelta(minutes=index * gps_step_minutes)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_GPS,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={
                        "cluster": city,
                        "lat": (30.57 if city == "CD" else 22.54) + rng.gauss(0, 0.01),
                        "lon": (104.06 if city == "CD" else 114.06) + rng.gauss(0, 0.01),
                    },
                    role=ROLE_ROUTINE,
                    story="MOVE" if day in (_RELOCATION_DAY, _RELOCATION_DAY + 1) else None,
                    evidence_key=None,
                )

            # ---------------- 外界录音流（证据 vs 环境噪声） ----------------
            noise_quota = 6
            passerby_quota = 4
            beat_audio = [b for b in beats_today if b.channel == KIND_AUDIO]
            routine_quota = max(
                0, profile.audio_per_day - noise_quota - passerby_quota - len(beat_audio)
            )

            for beat in beat_audio:
                sequence += 1
                yield self._utterance(
                    sequence,
                    day_start,
                    beat,
                    rng,
                )
            for index in range(routine_quota):
                stamp = day_start + timedelta(hours=9 + index % 12, minutes=(index * 7) % 60)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_AUDIO,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload=self._audio_payload(
                        token=self._pick_token(index, day),
                        text=_ROUTINE_CHATS[index % len(_ROUTINE_CHATS)],
                        rng=rng,
                    ),
                    role=ROLE_ROUTINE,
                    story=None,
                    evidence_key=None,
                )
            for index in range(noise_quota):
                stamp = day_start + timedelta(hours=11 + index % 9, minutes=(index * 11) % 60)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_AUDIO,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload=self._audio_payload(
                        token=self._pick_token(index + 2, day),
                        text=_STREET_VENDOR_NOISE[index % len(_STREET_VENDOR_NOISE)],
                        rng=rng,
                    ),
                    role=ROLE_NOISE,
                    story=None,
                    evidence_key=None,
                )
            for index in range(passerby_quota):
                stamp = day_start + timedelta(hours=16 + index % 6, minutes=(index * 13) % 60)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_AUDIO,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload=self._audio_payload(
                        token=self._pick_token(index + 3, day),
                        text=_PASSERBY_CHATTER[index % len(_PASSERBY_CHATTER)],
                        rng=rng,
                    ),
                    role=ROLE_NOISE,
                    story=None,
                    evidence_key=None,
                )

            # ---------------- 图像抓拍（只留 Caption，永不存大图） ----------------
            beat_images = [b for b in beats_today if b.channel == KIND_IMAGE]
            image_slots = max(profile.images_per_day, len(beat_images))
            for index in range(image_slots):
                if index < len(beat_images):
                    beat = beat_images[index]
                    caption, tags = beat.text, (beat.story.lower(), "evidence")
                    quality = 0.72
                    stamp = day_start + timedelta(hours=beat.hour, minutes=beat.minute)
                else:
                    caption, tags = _IMAGE_CAPTIONS[index % len(_IMAGE_CAPTIONS)]
                    quality = 0.15 if index % 3 == 0 else 0.85
                    stamp = day_start + timedelta(hours=7 + index % 13)
                motion = 0.6 if quality < 0.4 else 0.12
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_IMAGE,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={
                        "metadata": {
                            "quality_score": quality,
                            "mean_luma": 33.0 if quality < 0.4 else 132.0,
                            "high_freq_energy": 0.2 if quality < 0.4 else 0.62,
                            "motion_magnitude": motion,
                            "caption": caption,
                            "tags": list(tags),
                            "source": f"{day}:{index}",
                        },
                        "raw_bytes": _IMAGE_BYTES,
                    },
                    role=ROLE_NOISE if quality < 0.4 else ROLE_ROUTINE,
                    story=None,
                    evidence_key=None,
                )

            # ---------------- 聊天/短信流（垃圾短信必须物理删除） ----------------
            beat_texts = [b for b in beats_today if b.channel in (KIND_CHAT, KIND_SMS)]
            for beat in beat_texts:
                sequence += 1
                yield self._text_message(sequence, day_start, beat)
            for index in range(profile.sms_per_day):
                stamp = day_start + timedelta(hours=8 + index % 14, minutes=(index * 9) % 60)
                if index < 8:
                    text = _SMS_NOISE[index % len(_SMS_NOISE)]
                    role = ROLE_NOISE
                else:
                    text = _GROUP_FLOOD[index % len(_GROUP_FLOOD)]
                    role = ROLE_NOISE
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_SMS,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={"sender": "10690412" if index < 8 else "GROUP_XT", "text": text},
                    role=role,
                    story=None,
                    evidence_key=None,
                )
            for index in range(profile.chats_per_day):
                stamp = day_start + timedelta(hours=7 + index % 16, minutes=(index * 17) % 60)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_CHAT,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={
                        "channel": "wechat",
                        "thread": "同事群" if index % 2 else "家人",
                        "from": "P002" if index % 2 else "P001",
                        "text": _ROUTINE_CHATS[index % len(_ROUTINE_CHATS)],
                    },
                    role=ROLE_ROUTINE,
                    story=None,
                    evidence_key=None,
                )

            # ---------------- 慢性病季度复查（长周期管理证据） ----------------
            if chronic_review:
                stamp = day_start + timedelta(hours=9, minutes=30)
                sequence += 1
                yield RawSample(
                    sequence=sequence,
                    kind=KIND_CHAT,
                    occurred_at=stamp,
                    learned_at=stamp,
                    payload={
                        "channel": "wechat",
                        "thread": "就诊记录",
                        "from": "P002",
                        "text": (
                            f"季度复查：血压{136 + day % 12}/{(86 + day % 8)}，"
                            f"血糖{6.4 + (day % 5) * 0.1:.1f}，药照常吃。"
                        ),
                    },
                    role=ROLE_EVIDENCE,
                    story="CHRONIC",
                    evidence_key=None,
                )

    # ------------------------------------------------------------------
    # 批量入口（供流水线按窗消费）
    # ------------------------------------------------------------------

    def iter_batches(self, batch_size: int = 1024) -> Iterator[tuple[RawSample, ...]]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        window: list[RawSample] = []
        for sample in self.iter_samples():
            window.append(sample)
            if len(window) >= batch_size:
                yield tuple(window)
                window.clear()
        if window:
            yield tuple(window)

    def expected_sample_total(self) -> int:
        """算术上界估算（真实吐出量由故事日补充流微调，测试用实际计数断言）。"""

        total = self.profile.nominal_sample_total
        total += len(self.overtime_days()) * 240
        total += len(self.chronic_review_days())
        return total

    # ------------------------------------------------------------------
    # 内部构造器
    # ------------------------------------------------------------------

    def _imu_samples(
        self,
        rng: random.Random,
        *,
        count: int,
        activity: str,
        fall: bool,
    ) -> tuple[tuple[float, float, float], ...]:
        if activity == "desk":
            base = 1.0
            noise = 0.02
        elif activity == "walk":
            base = 1.14
            noise = 0.06
        else:
            base = 1.9
            noise = 0.16
        samples: list[tuple[float, float, float]] = []
        for index in range(count):
            wobble = 0.05 * ((index % 50) / 50.0)
            samples.append(
                (
                    rng.gauss(0.0, noise),
                    rng.gauss(0.0, noise),
                    base + wobble + rng.gauss(0.0, noise),
                )
            )
        if fall:
            impact_start = min(count - 3, count // 2)
            samples[impact_start] = (0.35, 0.30, 3.42)
            samples[impact_start + 1] = (0.20, 0.15, 3.05)
            samples[impact_start + 2] = (0.05, 0.02, 1.06)
        return tuple(samples)

    def _pick_token(self, index: int, day: int) -> str:
        """声纹编号轮转：只在前半段出现过的路人声纹此后彻底冷掉（180 天淘汰靶子）。"""

        token = _VOICE_TOKENS[index % len(_VOICE_TOKENS)]
        if token in _TRANSIENT_TOKENS and day >= _TRANSIENT_TOKEN_LAST_DAY:
            return _VOICE_TOKENS[index % 2]
        return token

    def _audio_payload(self, *, token: str, text: str, rng: random.Random) -> dict[str, Any]:
        return {
            "speaker_token": token,
            "transcript": text,
            "duration_s": 1.5 + rng.random() * 3.0,
            "raw_bytes": _AUDIO_BYTES,
        }

    def _utterance(
        self,
        sequence: int,
        day_start: datetime,
        beat: EvidenceBeat,
        rng: random.Random,
    ) -> RawSample:
        stamp = day_start + timedelta(hours=beat.hour, minutes=beat.minute)
        learned = stamp + timedelta(days=beat.learn_lag_days)
        return RawSample(
            sequence=sequence,
            kind=KIND_AUDIO,
            occurred_at=stamp,
            learned_at=learned,
            payload=self._audio_payload(
                token=beat.speaker_token or "P002",
                text=beat.text,
                rng=rng,
            ),
            role=ROLE_EVIDENCE,
            story=beat.story,
            evidence_key=beat.key,
        )

    def _text_message(
        self,
        sequence: int,
        day_start: datetime,
        beat: EvidenceBeat,
    ) -> RawSample:
        stamp = day_start + timedelta(hours=beat.hour, minutes=beat.minute)
        learned = stamp + timedelta(days=beat.learn_lag_days)
        if beat.channel == KIND_SMS:
            payload: dict[str, Any] = {"sender": "95555", "text": beat.text}
        else:
            payload = {
                "channel": "wechat",
                "thread": "家庭群" if beat.story == "FAMILY" else "老王",
                "from": beat.speaker_token or "P002",
                "text": beat.text,
            }
        return RawSample(
            sequence=sequence,
            kind=beat.channel,
            occurred_at=stamp,
            learned_at=learned,
            payload=payload,
            role=ROLE_EVIDENCE,
            story=beat.story,
            evidence_key=beat.key,
        )
