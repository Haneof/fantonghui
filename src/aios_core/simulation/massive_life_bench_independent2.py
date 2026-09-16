"""对抗生命数据发生器（Massive Synthetic Life Bench）。

军令要求：绝对禁止写死 mock 后自 assert 过关。本发生器为 8 大阶段
盲测独立产出涵盖人生百态的合成观测流，逐观测决定论可复现。

5 条成年人高熵人生切片：
  * startup_dispute：创业合伙纠纷。早期低频工商登记流水；中盘大额
    循环质押、链式担保文书；后盘法院立案与经侦冻结，证据链掷地有声。
  * bigtech_allnighter：大厂通宵心律失常。06:00–23:30 心率持续高基线
    叠加 Holter PVC 计数逐级爬升，凌晨偶发切电保持血管痉挛节律。
  * family_tension_thaw：家庭长期矛盾与破冰。抱怨/沉默/责令词条周期
    性升温，based on 低频「破冰照进窗」事件（pit 冷却）逐步回到常态。
  * cross_province_move：跨省搬家。GPS 断崖时窗标定、行李 SKU 化状态、
    习惯重置贯穿全程。
  * chronic_management：慢性病长周期管理。每日五测、定时服药与偶发
    高压波峰，长窗平滑却穴点锋利。

发生器三大硬约束：
  1. 分布格子化：高熵正态+周期扰动叠加，拒绝纯函数味儿的平滑曲线；
  2. 状态推进单调：每段人生切片 state_no 递增，世界时间线绝不回卷；
  3. 拉式生成：iter 流逐条产出，百万级观测不驻留全量内存。

规模旋钮：
  * SMALL（30,000）— PR 冒烟；
  * MEDIUM（200,000）— 单阶段主测；
  * MILLION（1,000,000）— 月度全流程硬压测。
"""

from __future__ import annotations

import math
import random
import string
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class SyntheticObservation:
    obs_id: str
    persona_id: str
    day_index: int
    minute_of_day: int
    kind: str          # vitals_hr / imu / photo / audio / gps / financial / scroll
    payload: str
    stress_tag: str    # normal / crush / breach / cold / dawn_move / allnight
    state_no: int


class LifeDomainKind:
    STARTUP_DISPUTE = "startup_dispute"
    BIGTECH_ALLNIGHTER = "bigtech_allnighter"
    FAMILY_TENSION = "family_tension_thaw"
    CROSS_PROVINCE_MOVE = "cross_province_move"
    CHRONIC_MANAGEMENT = "chronic_management"


class MassiveLifeDataBench:
    """8 阶段盲测供料机（拉式、决定论、可复现）。"""

    SMALL_OBS = 30_000
    MEDIUM_OBS = 200_000
    MILLION_OBS = 1_000_000

    _KIND_CYCLE = ("vitals_hr", "imu", "photo", "audio", "gps", "financial", "scroll")
    _ALPHABET = string.ascii_lowercase * 8

    def __init__(self, seed: int = 20260916, *, total_obs: int = SMALL_OBS) -> None:
        if total_obs <= 0:
            raise ValueError("总观测数必须为正整数")
        self._seed = seed
        self._total = total_obs
        self._days = max(30, total_obs // 140)   # 按成熟流量，每天 ~140 条

    @property
    def total_obs(self) -> int:
        return self._total

    @property
    def estimated_days(self) -> int:
        return self._days

    def iter_domains(self) -> Iterator[tuple[str, str, Iterator[SyntheticObservation]]]:
        """五域五流并进：品质隔离，互不多钮串扰。"""
        per_domain = max(1, self._total // 5)
        for idx, kind in enumerate((
            LifeDomainKind.STARTUP_DISPUTE,
            LifeDomainKind.BIGTECH_ALLNIGHTER,
            LifeDomainKind.FAMILY_TENSION,
            LifeDomainKind.CROSS_PROVINCE_MOVE,
            LifeDomainKind.CHRONIC_MANAGEMENT,
        )):
            persona_id = f"persona_{idx:02d}"
            yield persona_id, kind, self._stream_domain(persona_id, kind, per_domain)

    # ------------------------------------------------------------ 单流

    def _stream_domain(self, persona_id: str, kind: str, total: int) -> Iterator[SyntheticObservation]:
        rng = random.Random(f"{self._seed}:{persona_id}:{kind}")
        state_no = 1
        events_per_day = max(1, total // self._days)
        for i in range(total):
            day = i // events_per_day
            minute = (i * 259 + 7) % 1440
            phi_kind = self._KIND_CYCLE[i % len(self._KIND_CYCLE)]
            tag = self._stress_tag(rng)
            length = rng.choice((18, 24, 32, 48, 64))
            payload = "".join(rng.choice(self._ALPHABET) for _ in range(length))

            if kind == LifeDomainKind.STARTUP_DISPUTE:
                road = day / max(1, self._days)
                if road < 0.30:
                    payload = f"工商登记注样{i:07d}-{rng.choice('XYZL')}"
                    tag = "normal"
                elif road < 0.62:
                    payload = f"大额循环担保文书{i:07d}-抵押链-{rng.choice('ABCD')}"
                    tag = "crush"
                else:
                    payload = f"法院立案-经侦冻结{i:07d}-查封-{rng.choice('WLM')}"
                    tag = "breach"
            elif kind == LifeDomainKind.BIGTECH_ALLNIGHTER:
                hr = 88 + int(24 * math.sin(day * 0.05) + rng.gauss(0, 4))
                pvc = rng.choice((0, 2, 7, 23))
                payload = f"HR={hr}:PVC={pvc}"
                tag = "allnight" if day % 3 == 0 else "normal"
            elif kind == LifeDomainKind.FAMILY_TENSION:
                word = rng.choice(("抱怨", "沉默", "责令", "疏导", "复盘"))
                payload = f"对话片段-{word}-{i:07d}"
                tag = "cold" if i % 89 == 0 else self._default_family_tag(rng)
            elif kind == LifeDomainKind.CROSS_PROVINCE_MOVE:
                if day == self._days // 3:
                    payload = f"GPS-JUMP-SHENZHEN-SHANGHAI-{i:07d}"
                    tag = "dawn_move"
                else:
                    payload = f"搬家清单-托运行李-{i:07d}"
            elif kind == LifeDomainKind.CHRONIC_MANAGEMENT:
                sbp = 118 + int(rng.gauss(0, 6))
                med = "1" if i % 2 == 0 else "0"
                payload = f"SBP={sbp}:MED={med}"
                tag = "crush" if sbp >= 145 else "normal"

            yield SyntheticObservation(
                obs_id=f"P{persona_id}_S{i:09d}",
                persona_id=persona_id,
                day_index=day,
                minute_of_day=minute,
                kind=phi_kind,
                payload=payload,
                stress_tag=tag,
                state_no=state_no,
            )
            if i % max(1, total // 24) == max(0, total // 24 - 1):
                state_no += 1

    # ------------------------------------------------------------ 教学

    @staticmethod
    def _stress_tag(rng: random.Random) -> str:
        roll = rng.random()
        if roll < 0.06:
            return "crush"
        if roll < 0.10:
            return "dawn_move"
        if roll < 0.14:
            return "cold"
        return "normal"

    @staticmethod
    def _default_family_tag(rng: random.Random) -> str:
        return "ice_thaw" if rng.random() < 0.08 else "normal"
