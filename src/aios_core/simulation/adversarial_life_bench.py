"""对抗生命数据发生器（Massive Synthetic Life Bench，MT-ADV-001）。

定位
----
本模块是**独立的对抗数据发生器**：它只负责制造"人生百态"级别的原始样本流，
**不知道也不需要知道任何测试断言**。测试侧只能消费它产出的原始流、走真实提纯
与认知管线，绝不允许把期望值反过来写进发生器（禁止自编自答）。

五条人生切片（覆盖宪法要求的复杂现实，而非单一老套案例）
--------------------------------------------------------
1. ``STARTUP_PARTNER_DISPUTE``     创业合伙纠纷：出资、对赌、撕逼、银行流水、诉讼；
2. ``TECH_OVERTIME_ARRHYTHMIA``    大厂通宵与心律失常：深夜版本上线 + 咖啡因 + 早搏；
3. ``FAMILY_CONFLICT_THAW``        家庭长期矛盾与破冰：多年积怨、沉默、冬至破冰；
4. ``INTERPROVINCIAL_RELOCATION``  跨省搬家与生活相变：迁徙、租房、社保、社交重构；
5. ``CHRONIC_ILLNESS_LONGITUDE``   慢性病长周期管理：血糖/血压、复诊、用药、并发症。

时间轴与配额
------------
* 时间轴严格落在 2024-01-01 → 2026-09-15（永不产生"未来数据"）；
* IMU 抽样率 50Hz（宪法明令禁止直写库的那一类原始数据）；
* 心率 1Hz 级长序列（含平稳平台 + 突变波形）；
* 视觉抓拍 / 音频切片 / 文本环境流按真实密度混入，含**明确的环境噪声**
  （叫卖、垃圾短信、群聊刷屏）与**核心证据原话**（合同、承诺、争吵、医嘱）。

全部数据由种子确定，可复现但不含任何断言。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterator

from aios_core.perception.edge_stream_purifier import (
    RawAudioSlice,
    RawEnvironmentText,
    RawHeartSample,
    RawImuSample,
    RawVisionFrame,
)

UTC = timezone.utc

__all__ = [
    "LifeArchetype",
    "LifeArchetypeSpec",
    "MassiveSyntheticLifeBench",
    "RawSampleCounts",
    "SAGA_SEEDS",
    "TIMELINE_START",
    "TIMELINE_END",
]

TIMELINE_START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
TIMELINE_END = datetime(2026, 9, 15, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _us(ts: datetime) -> int:
    return int(ts.timestamp() * 1_000_000)


class LifeArchetype(StrEnum):
    """五条人生切片。"""

    STARTUP_PARTNER_DISPUTE = "startup_partner_dispute"
    TECH_OVERTIME_ARRHYTHMIA = "tech_overtime_arrhythmia"
    FAMILY_CONFLICT_THAW = "family_conflict_thaw"
    INTERPROVINCIAL_RELOCATION = "interprovincial_relocation"
    CHRONIC_ILLNESS_LONGITUDE = "chronic_illness_longitude"


@dataclass(frozen=True, slots=True)
class LifeArchetypeSpec:
    """一条人生切片的生成配额与关键实体。"""

    archetype: LifeArchetype
    subject_label: str
    imu_samples: int
    heart_samples: int
    vision_frames: int
    audio_slices: int
    text_events: int
    start_day_offset: int
    #: 关键人物（实体编号 → 真实身份），供声纹绑定使用。
    cast: tuple[tuple[str, str], ...]
    #: 环境噪声文本（必须被判为噪声的那一类原始数据）。
    noise_texts: tuple[str, ...]
    #: 核心证据原话（必须永存的那一类原始数据）。
    core_texts: tuple[str, ...]


SAGA_SEEDS: tuple[LifeArchetypeSpec, ...] = (
    LifeArchetypeSpec(
        archetype=LifeArchetype.STARTUP_PARTNER_DISPUTE,
        subject_label="创业合伙纠纷",
        imu_samples=210_000,
        heart_samples=14_400,
        vision_frames=120,
        audio_slices=360,
        text_events=520,
        start_day_offset=30,
        cast=(("P001", "王建国"), ("P002", "陈律师"), ("P003", "财务小刘")),
        noise_texts=(
            "商场广播：三楼男装全场促销清仓打折，欢迎扫码关注公众号",
            "外卖骑手群聊刷屏：今天单量爆炸了兄弟们冲啊哈哈哈哈",
            "营销短信：恭喜您中奖了，免费领取千元优惠券，退订回T",
            "街边叫卖：新鲜出炉的烤红薯，五块钱一个好吃不贵",
            "地铁车厢广播：下一站国贸，请乘客注意脚下安全",
        ),
        core_texts=(
            "我和王建国当面签了对赌协议：出资五十万占股 30%，约定年化 8%，半年内归还本金。",
            "银行流水截图：2024-05-10 向王建国个人账户转账 500000 元，摘要写的是合伙出资款。",
            "合伙人会议上王建国拍桌子翻脸：钱早就投进项目了，你们要查账先把我告了再说！",
            "法院裁定：王建国涉嫌合同诈骗，冻结名下账户，案件移送经侦进一步侦查。",
            "陈律师的原话：借据、转账凭证、聊天记录三样齐全，证据链闭合，胜算在七成以上。",
        ),
    ),
    LifeArchetypeSpec(
        archetype=LifeArchetype.TECH_OVERTIME_ARRHYTHMIA,
        subject_label="大厂通宵与心律失常",
        imu_samples=210_000,
        heart_samples=21_600,
        vision_frames=90,
        audio_slices=260,
        text_events=430,
        start_day_offset=120,
        cast=(("P001", "产品经理老赵"), ("P002", "同组程序员小林")),
        noise_texts=(
            "茶水间自动贩卖机嗡嗡作响，几个陌生人在讨论晚上吃啥",
            "园区门口外卖小哥叫卖：代取快递两块一个",
            "公司群广告：内部推荐购房享受九折优惠，扫码进群",
            "健身房广播：私教课程限时秒杀，办卡送两节体验课",
        ),
        core_texts=(
            "凌晨 02:40 还在办公室改版本，这是本周第三次通宵，胸口有点发闷。",
            "手环报警：静息心率 128，频发室性早搏，HRV 掉到 18ms。",
            "体检报告原始结论：窦性心律不齐伴频发室性早搏，建议心内科复诊并减少熬夜。",
            "主管原话：这个版本押上了明年的预算，谁掉链子谁负责。",
            "我答应过自己：这周之后一定把作息调回来，再通宵就去做心脏彩超。",
        ),
    ),
    LifeArchetypeSpec(
        archetype=LifeArchetype.FAMILY_CONFLICT_THAW,
        subject_label="家庭长期矛盾与破冰",
        imu_samples=210_000,
        heart_samples=14_400,
        vision_frames=110,
        audio_slices=420,
        text_events=560,
        start_day_offset=200,
        cast=(("P001", "母亲李秀兰"), ("P002", "父亲周国强"), ("P003", "妹妹周小雨")),
        noise_texts=(
            "菜市场叫卖：新鲜蒜薹便宜卖，走过路过不要错过",
            "老家邻居群刷屏：转发这条链接就能领红包",
            "电视里循环播放的药品广告：专治腰腿疼，买三送一",
            "公交报站广播：终点站到了，请乘客从后门下车",
        ),
        core_texts=(
            "妈妈在电话里第一次道歉：那年你辞职回家，是我说话太重了，别往心里去。",
            "我说出口的原话：妈，我不想吵了，这么多年我也有错，冬至我回家一起包饺子。",
            "父亲酒后翻旧账：当年要不是你非要留在大城市，家里也不会吵成这样。",
            "妹妹发来的信息：哥，爸妈嘴上不说，其实一直在等你回家，我给你留了房间。",
            "全家的约定：以后每个月视频一次，过年必须回家，不再拿旧事互相扎心。",
        ),
    ),
    LifeArchetypeSpec(
        archetype=LifeArchetype.INTERPROVINCIAL_RELOCATION,
        subject_label="跨省搬家与生活相变",
        imu_samples=210_000,
        heart_samples=12_000,
        vision_frames=100,
        audio_slices=240,
        text_events=430,
        start_day_offset=320,
        cast=(("P001", "中介老徐"), ("P002", "新同事阿哲"), ("P003", "房东王阿姨")),
        noise_texts=(
            "搬家货车里的收音机在放不知名的广告",
            "小区门口房产中介叫卖：学区房特价，买房送车位",
            "装修电钻声持续不断，邻居在楼道里抱怨",
            "家具城促销广播：满一万减两千，扫码下单立减",
        ),
        core_texts=(
            "辞掉干了六年的工作，从成都搬到杭州，落户口材料已经交上去了。",
            "签租约时房东原话：押一付三，一年内退租押金不退，这是合同约定。",
            "社保迁移回执：养老与医疗保险关系已从成都转入杭州，缴费年限连续计算。",
            "第一晚在新家失眠到凌晨三点，窗外是陌生的城市高架噪声。",
            "和阿哲吃饭时说的话：以前的朋友都在成都，这里我算从头再来一遍。",
        ),
    ),
    LifeArchetypeSpec(
        archetype=LifeArchetype.CHRONIC_ILLNESS_LONGITUDE,
        subject_label="慢性病长周期管理",
        imu_samples=210_000,
        heart_samples=14_400,
        vision_frames=120,
        audio_slices=300,
        text_events=470,
        start_day_offset=430,
        cast=(("P001", "内分泌科张医生"), ("P002", "社区护士小李"), ("P003", "病友老张")),
        noise_texts=(
            "医院大厅广播：请 3021 号到三号窗口取药",
            "候诊区有人在推销保健品，说吃三个月能根治糖尿病",
            "药店促销短信：血糖仪半价，试纸买十送三，退订回T",
            "食堂循环播放的背景音乐和嘈杂人声混在一起",
        ),
        core_texts=(
            "张医生的医嘱原话：二甲双胍早晚各一片，餐后两小时血糖务必每周测三次。",
            "糖化血红蛋白化验单：7.9%，比三个月前的 7.1% 明显升高，需要调整用药。",
            "社区随访记录：连续两周餐后血糖超过 11 mmol/L，已上报家庭医生。",
            "我跟医生说了实话：最近项目忙，晚饭经常超过十点才吃，药也漏服过两次。",
            "和老张的约定：每天走够八千步，互相打卡，谁断了就请对方吃一顿饭。",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class RawSampleCounts:
    """原始流配额与实际产出数。"""

    imu: int
    heart: int
    vision: int
    audio: int
    text: int

    @property
    def total(self) -> int:
        return self.imu + self.heart + self.vision + self.audio + self.text


class MassiveSyntheticLifeBench:
    """对抗生命数据发生器（种子确定、配额可调、零断言）。"""

    def __init__(self, *, seed: int = 20260916, scale: float = 1.0) -> None:
        if scale <= 0.0:
            raise ValueError("scale must be positive")
        self.seed = seed
        self.scale = scale

    # ------------------------------------------------------------------
    # 单条切片
    # ------------------------------------------------------------------

    def _quota(self, spec: LifeArchetypeSpec) -> RawSampleCounts:
        factor = self.scale
        return RawSampleCounts(
            imu=max(1, int(spec.imu_samples * factor)),
            heart=max(1, int(spec.heart_samples * factor)),
            vision=max(1, int(spec.vision_frames * factor)),
            audio=max(1, int(spec.audio_slices * factor)),
            text=max(1, int(spec.text_events * factor)),
        )

    def counts(self) -> RawSampleCounts:
        totals = [self._quota(spec) for spec in SAGA_SEEDS]
        return RawSampleCounts(
            imu=sum(item.imu for item in totals),
            heart=sum(item.heart for item in totals),
            vision=sum(item.vision for item in totals),
            audio=sum(item.audio for item in totals),
            text=sum(item.text for item in totals),
        )

    def generate_stream(self) -> Iterator[object]:
        """产出全部五条人生切片的原始样本流（百万级，惰性）。"""

        for index, spec in enumerate(SAGA_SEEDS):
            rng = random.Random(self.seed + index * 7919)
            yield from self._generate_archetype(spec, rng)

    def _generate_archetype(
        self, spec: LifeArchetypeSpec, rng: random.Random
    ) -> Iterator[object]:
        quota = self._quota(spec)
        origin = TIMELINE_START + timedelta(days=spec.start_day_offset)
        span_days = max(1.0, (TIMELINE_END - origin) / DAY)
        span_us = int((TIMELINE_END - origin).total_seconds() * 1_000_000)

        # ---- 1) 50Hz IMU：静止/走动/跑动/突发撞击四种宏观状态 -----------------
        motion_profile = rng.choice(
            (
                (0.98, 0.015, 0.004),   # 久坐为主
                (0.86, 0.11, 0.03),     # 走动较多
                (0.72, 0.22, 0.06, 0.0),  # 高强度
            )
        )
        still_p, walk_p, run_p = motion_profile[0], motion_profile[1], motion_profile[2]
        impact_plan = {
            int(quota.imu * fraction)
            for fraction in (0.17, 0.41, 0.66, 0.88)
            if fraction < 1.0
        }
        for seq in range(quota.imu):
            t_us = _us(origin) + int(seq * 20_000)
            roll = rng.random()
            if seq in impact_plan:
                # 突发撞击：合成加速度远超 4.5g（跌倒疑似）
                yield RawImuSample(
                    t_us=t_us,
                    ax=round(rng.uniform(1.5, 3.0), 4),
                    ay=round(rng.uniform(1.0, 2.5), 4),
                    az=round(rng.uniform(5.0, 9.0), 4),
                    gyro_mag=round(rng.uniform(2.0, 6.0), 4),
                )
                continue
            if roll < still_p:
                yield RawImuSample(
                    t_us,
                    round(rng.gauss(0.04, 0.04), 5),
                    round(rng.gauss(0.02, 0.04), 5),
                    round(1.0 + rng.gauss(0.0, 0.02), 5),
                    round(abs(rng.gauss(0.0, 0.01)), 5),
                )
            elif roll < still_p + walk_p:
                yield RawImuSample(
                    t_us,
                    round(rng.gauss(0.28, 0.14), 4),
                    round(rng.gauss(0.18, 0.12), 4),
                    round(1.28 + rng.gauss(0.0, 0.10), 4),
                    round(abs(rng.gauss(0.6, 0.25)), 4),
                )
            else:
                # 剧烈跑动：合成加速度均值 ~2.1g，峰值 5σ 仍严格低于 4.0g 冲击门限，
                # 因此真实跌倒（5~9g）不会被日常运动污染，反之亦然。
                yield RawImuSample(
                    t_us,
                    round(rng.gauss(0.62, 0.22), 4),
                    round(rng.gauss(0.48, 0.20), 4),
                    round(1.85 + rng.gauss(0.0, 0.25), 4),
                    round(abs(rng.gauss(2.4, 0.7)), 4),
                )

        # ---- 2) 心率：1Hz 连续采样时段（epoch 突发式佩戴），含长平稳平台与突变 ---
        #
        # 手环不是全年 24h 满负荷采样：真实形态是"某个时段连续 1Hz 采一段"。
        # 每条人生切片切出若干 epoch，其中一部分刻意落在深夜（通宵/早搏场景），
        # 另一部分落在白天（日常平稳），从而同时覆盖"平稳压缩"与"突变独立成 Observation"
        # 两种宪法形态。
        epochs = 12
        per_epoch = max(60, quota.heart // epochs)
        epoch_span_us = span_us / epochs
        for epoch in range(epochs):
            start_us = _us(origin) + int(epoch * epoch_span_us)
            acute = epoch % 4 == 1
            nighttime = acute or epoch % 3 == 2
            base_hour = 3 if nighttime else 10
            base_start = start_us + (base_hour - 8) * 3_600_000_000
            if base_start < _us(origin):
                base_start = start_us
            baseline = 62.0 if nighttime else 76.0
            spike_at = per_epoch // 2 if acute else -1
            for seq in range(per_epoch):
                t_us = base_start + seq * 1_000_000
                if seq == spike_at:
                    yield RawHeartSample(
                        t_us,
                        round(baseline + rng.uniform(42.0, 62.0), 2),
                        round(rng.uniform(13.0, 24.0), 2),
                        rng.randint(2, 6),
                    )
                    continue
                yield RawHeartSample(
                    t_us,
                    round(baseline + rng.gauss(0.0, 1.1), 2),
                    round(rng.uniform(36.0, 58.0), 2),
                    0,
                )

        # ---- 3) 视觉抓拍：含低画质垃圾帧与高价值证据帧 ----------------------
        for seq in range(quota.vision):
            t_us = _us(origin) + int(seq * span_us / max(1, quota.vision))
            is_garbage = seq % 5 == 3
            if is_garbage:
                yield RawVisionFrame(
                    frame_id=f"{spec.archetype.value}_img_{seq:05d}",
                    t_us=t_us,
                    caption="昏暗模糊，画面严重抖动无法解析",
                    tags=("blur",),
                    raw_bytes=bytes(256),
                    mean_luma=11.0,
                    high_freq_energy=0.12,
                    motion_magnitude=0.95,
                )
                continue
            core = spec.core_texts[seq % len(spec.core_texts)]
            yield RawVisionFrame(
                frame_id=f"{spec.archetype.value}_img_{seq:05d}",
                t_us=t_us,
                caption=f"现场抓拍：{core[:38]}",
                tags=("evidence", spec.archetype.value),
                raw_bytes=bytes(1024),
                mean_luma=138.0,
                high_freq_energy=0.72,
                motion_magnitude=0.08,
            )

        # ---- 4) 音频切片：核心原话 + 环境噪声混流 --------------------------
        for seq in range(quota.audio):
            t_us = _us(origin) + int(seq * span_us / max(1, quota.audio))
            slot, identity = spec.cast[seq % len(spec.cast)]
            is_noise = seq % 3 == 1
            if is_noise:
                yield RawAudioSlice(
                    slice_id=f"{spec.archetype.value}_aud_{seq:05d}",
                    t_us=t_us,
                    transcript=spec.noise_texts[seq % len(spec.noise_texts)],
                    speaker_slot="P900",
                    voiceprint_feature=self._voiceprint(rng, 0.95),
                    ambient_db=round(rng.uniform(62.0, 88.0), 1),
                    duration_ms=2400,
                    bound_entity_id=None,
                )
                continue
            utterance = spec.core_texts[seq % len(spec.core_texts)]
            yield RawAudioSlice(
                slice_id=f"{spec.archetype.value}_aud_{seq:05d}",
                t_us=t_us,
                transcript=utterance,
                speaker_slot=slot,
                voiceprint_feature=self._voiceprint(rng, 0.05),
                ambient_db=round(rng.uniform(40.0, 58.0), 1),
                duration_ms=3600,
                bound_entity_id=f"{spec.archetype.value}:{slot}:{identity}",
            )

        # ---- 5) 文本环境流：聊天/合同/短信/群聊 ---------------------------
        for seq in range(quota.text):
            t_us = _us(origin) + int(seq * span_us / max(1, quota.text))
            bucket = seq % 4
            if bucket == 1:
                yield RawEnvironmentText(
                    event_id=f"{spec.archetype.value}_txt_{seq:05d}",
                    t_us=t_us,
                    channel="sms",
                    text=spec.noise_texts[seq % len(spec.noise_texts)],
                )
            else:
                yield RawEnvironmentText(
                    event_id=f"{spec.archetype.value}_txt_{seq:05d}",
                    t_us=t_us,
                    channel="chat",
                    text=spec.core_texts[(seq // 2) % len(spec.core_texts)],
                )

    @staticmethod
    def _voiceprint(rng: random.Random, offset: float) -> tuple[float, ...]:
        base = [0.02] * 128
        for index in range(0, 12):
            base[index] = round(0.8 + rng.uniform(-0.05, 0.05), 4)
        for index in range(64, 76):
            base[index] = round(offset + rng.uniform(0.0, 0.05), 4)
        return tuple(base)

    # ------------------------------------------------------------------
    # 便捷入口
    # ------------------------------------------------------------------

    def archetype_of(self, raw: object) -> str | None:
        """从原始样本反查它属于哪条人生切片（便于统计，不参与生成语义）。"""

        if isinstance(raw, RawVisionFrame):
            return raw.frame_id.rsplit("_img_", 1)[0]
        if isinstance(raw, RawAudioSlice):
            return raw.slice_id.rsplit("_aud_", 1)[0]
        if isinstance(raw, RawEnvironmentText):
            return raw.event_id.rsplit("_txt_", 1)[0]
        return None
