"""SIM-MASSIVE-001 海量虚拟人生多维时空仿真推演机 (Massive Synthetic Life Benchmark).

纯 Python、零 UI、无头跑批的高熵多维人生数据发生器。
覆盖 2024-01-01 至 2026-09-15 跨越近千天（730+天真实时间轴）：
1. 生理流：心率、静息心率、深睡浅睡周期时序；
2. 社交流：与老王、妈妈、前任小林、同事等真实对话原话与即时语音微切片；
3. 财务与合同流：借款合同、投资协议、历年送礼账单与日常开销；
4. 四大宪法级标杆因果剧情线：
   - 老王诈骗案 (Old Wang Fraud Saga)：2024合伙借款50万 -> 2025借口拖延 -> 2026诈骗定罪，今天打标签；
   - 妈妈生日礼物推演案 (Mom's Birthday Saga)：2023丝巾、2024足浴盆闲置、2025按摩椅极佳 -> 2026膝盖受寒与预算推导；
   - 三年感情隐性因果案 (Romance Timeline Saga)：初识热恋 -> 深夜争吵心率异常 -> 冷战与隐式分手；
   - 熬夜早搏因果共振案 (Work-Health Resonance Saga)：周四深夜02:00加班 -> 次日晨间心率飙升与早搏。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aios_core.contracts.enums import (
    ClaimType,
    KnowledgeState,
    SourceClass,
)
from aios_core.contracts.ids import new_operation_id
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
from aios_core.storage.sqlite_store import SQLiteWorldStore

START_TIME = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


@dataclass
class MassiveBenchStats:
    total_observations: int = 0
    total_entities: int = 0
    total_relations: int = 0
    total_event_anchors: int = 0
    total_claims: int = 0
    total_evidence_sets: int = 0
    generation_time_ms: float = 0.0


class MassiveLifeBenchGenerator:
    """海量高熵多维人生数据发生器。"""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def generate_world_dataset(
        self,
        target_count: int = 10000,
    ) -> tuple[list[Any], dict[str, str]]:
        """生成高熵多维实体、关系、事件锚点、主张与海量观测。"""
        objects: list[Any] = []
        entity_ids: dict[str, str] = {}

        # 1. 核心实体定义
        user_ent = Entity(
            object_id="ent_user_me",
            subject_id="user_1",
            revision=1,
            entity_kind="person",
            canonical_name="用户自己",
            aliases=["我", "自己"],
            occurred=TemporalExtent.point(START_TIME),
            learned_at=START_TIME,
            recorded_at=START_TIME,
            created_by="sim_generator",
        )
        entity_ids["user"] = user_ent.object_id
        objects.append(user_ent)

        wang_ent = Entity(
            object_id="ent_old_wang",
            subject_id="user_1",
            revision=1,
            entity_kind="person",
            canonical_name="老王",
            aliases=["王强", "王哥", "合伙人老王"],
            occurred=TemporalExtent.point(START_TIME),
            learned_at=START_TIME,
            recorded_at=START_TIME,
            created_by="sim_generator",
        )
        entity_ids["old_wang"] = wang_ent.object_id
        objects.append(wang_ent)

        mom_ent = Entity(
            object_id="ent_mom",
            subject_id="user_1",
            revision=1,
            entity_kind="person",
            canonical_name="妈妈",
            aliases=["母亲", "老妈", "李秀英"],
            occurred=TemporalExtent.point(START_TIME),
            learned_at=START_TIME,
            recorded_at=START_TIME,
            created_by="sim_generator",
        )
        entity_ids["mom"] = mom_ent.object_id
        objects.append(mom_ent)

        lin_ent = Entity(
            object_id="ent_xiao_lin",
            subject_id="user_1",
            revision=1,
            entity_kind="person",
            canonical_name="小林",
            aliases=["林悦", "女朋友小林", "前女友"],
            occurred=TemporalExtent.point(START_TIME),
            learned_at=START_TIME,
            recorded_at=START_TIME,
            created_by="sim_generator",
        )
        entity_ids["xiao_lin"] = lin_ent.object_id
        objects.append(lin_ent)

        # 2. 关系网络
        rel_mom = Relation(
            object_id="rel_user_mom",
            subject_id="user_1",
            revision=1,
            relation_type="family_mother",
            left=ObjectRef(object_id=user_ent.object_id, revision=1),
            right=ObjectRef(object_id=mom_ent.object_id, revision=1),
            confidence=1.0,
            valid_time=TemporalExtent.point(START_TIME),
            occurred=TemporalExtent.point(START_TIME),
            learned_at=START_TIME,
            recorded_at=START_TIME,
            created_by="sim_generator",
        )
        objects.append(rel_mom)

        rel_wang = Relation(
            object_id="rel_user_wang",
            subject_id="user_1",
            revision=1,
            relation_type="business_partner",
            left=ObjectRef(object_id=user_ent.object_id, revision=1),
            right=ObjectRef(object_id=wang_ent.object_id, revision=1),
            confidence=1.0,
            valid_time=TemporalExtent.point(datetime(2024, 3, 1, tzinfo=UTC)),
            occurred=TemporalExtent.point(datetime(2024, 3, 1, tzinfo=UTC)),
            learned_at=datetime(2024, 3, 1, tzinfo=UTC),
            recorded_at=datetime(2024, 3, 1, tzinfo=UTC),
            created_by="sim_generator",
        )
        objects.append(rel_wang)

        # 3. 剧情线 1：老王诈骗案 (Old Wang Fraud Saga)
        t_wang_loan = datetime(2024, 5, 10, 14, 0, tzinfo=UTC)
        obs_wang_contract = Observation(
            object_id="obs_wang_loan_contract",
            subject_id="user_1",
            revision=1,
            source_kind="transaction",
            modality="text",
            value="老王与我签署《云计算业务合伙投资备忘录》，转账借款500,000元，约定年化收益8%，半年内归还本金。",
            occurred=TemporalExtent.point(t_wang_loan),
            learned_at=t_wang_loan,
            recorded_at=t_wang_loan,
            created_by="sim_generator",
        )
        objects.append(obs_wang_contract)

        t_wang_delay = datetime(2024, 11, 15, 19, 30, tzinfo=UTC)
        obs_wang_delay = Observation(
            object_id="obs_wang_delay_msg",
            subject_id="user_1",
            revision=1,
            source_kind="chat",
            modality="text",
            value="老王发微信：'兄弟，下游回款被卡在国企审批流程了，再通融两个月，下季度连本带息给你打过去！'",
            occurred=TemporalExtent.point(t_wang_delay),
            learned_at=t_wang_delay,
            recorded_at=t_wang_delay,
            created_by="sim_generator",
        )
        objects.append(obs_wang_delay)

        t_wang_fight = datetime(2025, 8, 20, 21, 15, tzinfo=UTC)
        obs_wang_fight = Observation(
            object_id="obs_wang_fight_call",
            subject_id="user_1",
            revision=1,
            source_kind="audio",
            modality="text",
            value="电话录音：我质问老王为什么偷偷变更公司法人并将资产转移给亲戚，老王恼羞成怒挂断电话。",
            occurred=TemporalExtent.point(t_wang_fight),
            learned_at=t_wang_fight,
            recorded_at=t_wang_fight,
            created_by="sim_generator",
        )
        objects.append(obs_wang_fight)

        t_wang_court = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
        obs_wang_court = Observation(
            object_id="obs_wang_court_verdict",
            subject_id="user_1",
            revision=1,
            source_kind="transaction",
            modality="text",
            value="北京市朝阳区人民法院刑事判决书：被告人王强（老王）犯合同诈骗罪，判处有期徒刑三年六个月，责令退赔全部款项，并列入失信被执行人黑名单。",
            occurred=TemporalExtent.point(t_wang_court),
            learned_at=t_wang_court,
            recorded_at=t_wang_court,
            created_by="sim_generator",
        )
        objects.append(obs_wang_court)

        ev_wang = EvidenceSet(
            object_id="evset_wang_case",
            subject_id="user_1",
            revision=1,
            purpose="老王合同诈骗全案诉讼证据链",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=t_wang_court),
            member_refs=[
                ObjectRef(object_id=obs_wang_contract.object_id, revision=1),
                ObjectRef(object_id=obs_wang_delay.object_id, revision=1),
                ObjectRef(object_id=obs_wang_fight.object_id, revision=1),
                ObjectRef(object_id=obs_wang_court.object_id, revision=1),
            ],
            selection_method="curated",
            occurred=TemporalExtent(start=t_wang_loan, end=t_wang_court),
            learned_at=t_wang_court,
            recorded_at=t_wang_court,
            created_by="sim_generator",
        )
        objects.append(ev_wang)

        anchor_wang = EventAnchor(
            object_id="anchor_wang_fraud_timeline",
            subject_id="user_1",
            revision=1,
            title="老王借款与合同诈骗始末",
            interpretation="老王从合伙借款50万、推延拖欠到法院正式以合同诈骗罪定罪的全过程",
            confidence=1.0,
            participant_refs=[
                ObjectRef(object_id=wang_ent.object_id, revision=1),
                ObjectRef(object_id=user_ent.object_id, revision=1),
            ],
            evidence_set_refs=[ObjectRef(object_id=ev_wang.object_id, revision=1)],
            event_time=TemporalExtent(start=t_wang_loan, end=t_wang_court),
            occurred=TemporalExtent(start=t_wang_loan, end=t_wang_court),
            learned_at=t_wang_court,
            recorded_at=t_wang_court,
            created_by="sim_generator",
        )
        objects.append(anchor_wang)

        claim_wang = Claim(
            object_id="claim_wang_is_fraudster",
            subject_id=wang_ent.object_id,
            revision=1,
            claimant_id="court_judgment",
            claim_type=ClaimType.FACT,
            content="老王（王强）已被法院以合同诈骗罪定罪，属于法定失信被执行人与金融诈骗犯，严禁任何业务信任与财务往来。",
            confidence=1.0,
            valid_time=TemporalExtent.point(t_wang_court),
            asserted_at=t_wang_court,
            knowledge_state=KnowledgeState.INFERRED,
            support_evidence_set_refs=[
                ObjectRef(object_id=ev_wang.object_id, revision=1)
            ],
            occurred=TemporalExtent.point(t_wang_court),
            learned_at=t_wang_court,
            recorded_at=t_wang_court,
            created_by="sim_generator",
        )
        objects.append(claim_wang)

        # 4. 剧情线 2：妈妈生日礼物推演案 (Mom's Birthday Saga)
        t_mom_2023 = datetime(2023, 5, 8, 18, 0, tzinfo=UTC)
        obs_gift_2023 = Observation(
            object_id="obs_mom_gift_2023",
            subject_id="user_1",
            revision=1,
            source_kind="transaction",
            modality="text",
            value="送妈妈母亲节生日礼物：一条真丝丝巾（420元）。妈妈反馈：颜色很洋气，但平时在老家干农活做家务根本没机会戴，放在衣柜落灰。",
            occurred=TemporalExtent.point(t_mom_2023),
            learned_at=t_mom_2023,
            recorded_at=t_mom_2023,
            created_by="sim_generator",
        )
        objects.append(obs_gift_2023)

        t_mom_2024 = datetime(2024, 5, 8, 19, 0, tzinfo=UTC)
        obs_gift_2024 = Observation(
            object_id="obs_mom_gift_2024",
            subject_id="user_1",
            revision=1,
            source_kind="transaction",
            modality="text",
            value="送妈妈智能加热电动足浴盆（680元）。妈妈微信反馈：机器盛水后太重了，腰吃不消搬不动，且倒水麻烦，用过两次就闲置在卫生间了。",
            occurred=TemporalExtent.point(t_mom_2024),
            learned_at=t_mom_2024,
            recorded_at=t_mom_2024,
            created_by="sim_generator",
        )
        objects.append(obs_gift_2024)

        t_mom_2025 = datetime(2025, 5, 8, 12, 0, tzinfo=UTC)
        obs_gift_2025 = Observation(
            object_id="obs_mom_gift_2025",
            subject_id="user_1",
            revision=1,
            source_kind="transaction",
            modality="text",
            value="送妈妈全身气囊智能揉捏按摩椅（4200元）。妈妈极度高兴，电话里连续夸赞：每天跳完广场舞回来都要躺半小时，腰酸背痛大为缓解，邻居们都来体验羡慕。",
            occurred=TemporalExtent.point(t_mom_2025),
            learned_at=t_mom_2025,
            recorded_at=t_mom_2025,
            created_by="sim_generator",
        )
        objects.append(obs_gift_2025)

        t_mom_2026 = datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
        obs_mom_health_2026 = Observation(
            object_id="obs_mom_health_knee_2026",
            subject_id="user_1",
            revision=1,
            source_kind="chat",
            modality="text",
            value="老妈电话聊家常：'最近一到梅雨天阴天，左腿膝盖老寒腿就酸胀发凉，走路使不上劲，贴膏药也没太大用。' 我记录当前预算为3000元左右准备挑选合适健康礼品。",
            occurred=TemporalExtent.point(t_mom_2026),
            learned_at=t_mom_2026,
            recorded_at=t_mom_2026,
            created_by="sim_generator",
        )
        objects.append(obs_mom_health_2026)

        ev_mom = EvidenceSet(
            object_id="evset_mom_gifts",
            subject_id="user_1",
            revision=1,
            purpose="历年母亲送礼反馈与身体健康档案",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=t_mom_2026),
            member_refs=[
                ObjectRef(object_id=obs_gift_2023.object_id, revision=1),
                ObjectRef(object_id=obs_gift_2024.object_id, revision=1),
                ObjectRef(object_id=obs_gift_2025.object_id, revision=1),
                ObjectRef(object_id=obs_mom_health_2026.object_id, revision=1),
            ],
            selection_method="curated",
            occurred=TemporalExtent(start=t_mom_2023, end=t_mom_2026),
            learned_at=t_mom_2026,
            recorded_at=t_mom_2026,
            created_by="sim_generator",
        )
        objects.append(ev_mom)

        anchor_mom = EventAnchor(
            object_id="anchor_mom_birthday_gifts",
            subject_id="user_1",
            revision=1,
            title="历年妈妈生日与健康需求演变",
            interpretation="梳理2023-2026年给母亲送礼的喜好反馈（拒绝笨重倒水、偏好舒适轻便理疗）与当前老寒腿膝盖理疗需求",
            confidence=1.0,
            participant_refs=[
                ObjectRef(object_id=mom_ent.object_id, revision=1),
                ObjectRef(object_id=user_ent.object_id, revision=1),
            ],
            evidence_set_refs=[ObjectRef(object_id=ev_mom.object_id, revision=1)],
            event_time=TemporalExtent(start=t_mom_2023, end=t_mom_2026),
            occurred=TemporalExtent(start=t_mom_2023, end=t_mom_2026),
            learned_at=t_mom_2026,
            recorded_at=t_mom_2026,
            created_by="sim_generator",
        )
        objects.append(anchor_mom)

        claim_mom = Claim(
            object_id="claim_mom_gift_preference",
            subject_id=mom_ent.object_id,
            revision=1,
            claimant_id="user_me",
            claim_type=ClaimType.PREFERENCE,
            content="妈妈偏好轻便舒适型健康理疗礼品（如老寒腿膝盖局部按摩保暖），严禁赠送笨重需提水倒水的大型家电及无实用价值装饰品。",
            confidence=0.98,
            valid_time=TemporalExtent.point(t_mom_2026),
            asserted_at=t_mom_2026,
            knowledge_state=KnowledgeState.INFERRED,
            support_evidence_set_refs=[
                ObjectRef(object_id=ev_mom.object_id, revision=1)
            ],
            occurred=TemporalExtent.point(t_mom_2026),
            learned_at=t_mom_2026,
            recorded_at=t_mom_2026,
            created_by="sim_generator",
        )
        objects.append(claim_mom)

        # 5. 剧情线 3：三年感情隐性因果案 (Romance Timeline Saga)
        t_romance_start = datetime(2024, 2, 14, tzinfo=UTC)
        obs_rom_start = Observation(
            object_id="obs_romance_start",
            subject_id="user_1",
            revision=1,
            source_kind="chat",
            modality="text",
            value="情人节和小林在江边餐厅共进晚餐，确定情侣恋爱关系，两人非常甜蜜默契。",
            occurred=TemporalExtent.point(t_romance_start),
            learned_at=t_romance_start,
            recorded_at=t_romance_start,
            created_by="sim_generator",
        )
        objects.append(obs_rom_start)

        t_romance_fight = datetime(2025, 4, 10, 23, 45, tzinfo=UTC)
        obs_rom_fight = Observation(
            object_id="obs_romance_fight",
            subject_id="user_1",
            revision=1,
            source_kind="chat",
            modality="text",
            value="深夜微信激烈争吵：小林抱怨我整天加班毫无陪伴，未来规划南辕北辙，双方陷入长达三周的冰冷冷战。",
            occurred=TemporalExtent.point(t_romance_fight),
            learned_at=t_romance_fight,
            recorded_at=t_romance_fight,
            created_by="sim_generator",
        )
        objects.append(obs_rom_fight)

        t_romance_end = datetime(2025, 10, 1, 16, 0, tzinfo=UTC)
        obs_rom_end = Observation(
            object_id="obs_romance_breakup",
            subject_id="user_1",
            revision=1,
            source_kind="chat",
            modality="text",
            value="国庆假期在咖啡馆，小林和平提出分手：'我们都累了，放彼此自由吧。' 互相退还了彼此家门的钥匙，正式结束一年半的感情。",
            occurred=TemporalExtent.point(t_romance_end),
            learned_at=t_romance_end,
            recorded_at=t_romance_end,
            created_by="sim_generator",
        )
        objects.append(obs_rom_end)

        ev_rom = EvidenceSet(
            object_id="evset_romance_timeline",
            subject_id="user_1",
            revision=1,
            purpose="与小林的情感演进证据集",
            knowledge_window=KnowledgeWindow(knowledge_cutoff=t_romance_end),
            member_refs=[
                ObjectRef(object_id=obs_rom_start.object_id, revision=1),
                ObjectRef(object_id=obs_rom_fight.object_id, revision=1),
                ObjectRef(object_id=obs_rom_end.object_id, revision=1),
            ],
            selection_method="curated",
            occurred=TemporalExtent(start=t_romance_start, end=t_romance_end),
            learned_at=t_romance_end,
            recorded_at=t_romance_end,
            created_by="sim_generator",
        )
        objects.append(ev_rom)

        anchor_rom = EventAnchor(
            object_id="anchor_romance_xiao_lin",
            subject_id="user_1",
            revision=1,
            title="与小林的感情历程与平静分手",
            interpretation="记录2024情人节确立关系、2025春季争吵冷战、到2025国庆和平分手的完整历程",
            confidence=1.0,
            participant_refs=[
                ObjectRef(object_id=lin_ent.object_id, revision=1),
                ObjectRef(object_id=user_ent.object_id, revision=1),
            ],
            evidence_set_refs=[ObjectRef(object_id=ev_rom.object_id, revision=1)],
            event_time=TemporalExtent(start=t_romance_start, end=t_romance_end),
            occurred=TemporalExtent(start=t_romance_start, end=t_romance_end),
            learned_at=t_romance_end,
            recorded_at=t_romance_end,
            created_by="sim_generator",
        )
        objects.append(anchor_rom)

        claim_rom = Claim(
            object_id="claim_romance_status",
            subject_id=lin_ent.object_id,
            revision=1,
            claimant_id="user_me",
            claim_type=ClaimType.FACT,
            content="与小林的情感关系已于2025年国庆节和平解除，钥匙已退还，目前处于完全平静无纠葛的前任状态。",
            confidence=1.0,
            valid_time=TemporalExtent.point(t_romance_end),
            asserted_at=t_romance_end,
            knowledge_state=KnowledgeState.INFERRED,
            support_evidence_set_refs=[
                ObjectRef(object_id=ev_rom.object_id, revision=1)
            ],
            occurred=TemporalExtent.point(t_romance_end),
            learned_at=t_romance_end,
            recorded_at=t_romance_end,
            created_by="sim_generator",
        )
        objects.append(claim_rom)

        # 6. 剧情线 4：熬夜早搏因果共振案 (Work-Health Resonance Saga)
        work_obs_list: list[Observation] = []
        bio_obs_list: list[Observation] = []
        for i, dt_day in enumerate([15, 22, 29]):
            t_work = datetime(2025, 7, dt_day, 2, 0, tzinfo=UTC)
            obs_work_night = Observation(
                object_id=f"obs_work_late_night_{i}",
                subject_id="user_1",
                revision=1,
                source_kind="work_log",
                modality="text",
                value="赶Q3重大版本上线，在办公室连续加班编写代码至凌晨02:30，喝了3杯浓缩咖啡，极度疲惫困乏。",
                occurred=TemporalExtent.point(t_work),
                learned_at=t_work,
                recorded_at=t_work,
                created_by="sim_generator",
            )
            objects.append(obs_work_night)
            work_obs_list.append(obs_work_night)

            t_bio = datetime(2025, 7, dt_day, 8, 30, tzinfo=UTC)
            obs_bio_spike = Observation(
                object_id=f"obs_bio_arrhythmia_{i}",
                subject_id="user_1",
                revision=1,
                source_kind="biometrics",
                modality="json",
                value=json.dumps(
                    {
                        "resting_hr": 112,
                        "hrv": 18,
                        "arrhythmia_count": 4,
                        "warning": "Premature Ventricular Contraction Detected (室性早搏频繁)",
                    }
                ),
                occurred=TemporalExtent.point(t_bio),
                learned_at=t_bio,
                recorded_at=t_bio,
                created_by="sim_generator",
            )
            objects.append(obs_bio_spike)
            bio_obs_list.append(obs_bio_spike)

        ev_health_work = EvidenceSet(
            object_id="evset_health_overtime_resonance",
            subject_id="user_1",
            revision=1,
            purpose="深夜熬夜与次日早搏因果共振证据链",
            knowledge_window=KnowledgeWindow(
                knowledge_cutoff=datetime(2025, 7, 30, 10, 0, tzinfo=UTC)
            ),
            member_refs=[
                ObjectRef(object_id=o.object_id, revision=1)
                for o in work_obs_list + bio_obs_list
            ],
            selection_method="curated",
            occurred=TemporalExtent(
                start=datetime(2025, 7, 15, 2, 0, tzinfo=UTC),
                end=datetime(2025, 7, 29, 9, 0, tzinfo=UTC),
            ),
            learned_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            recorded_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            created_by="sim_generator",
        )
        objects.append(ev_health_work)

        anchor_health_work = EventAnchor(
            object_id="anchor_overtime_arrhythmia_resonance",
            subject_id="user_1",
            revision=1,
            title="Q3攻坚期连续深夜加班诱发室性早搏共振",
            interpretation="2025年7月中下旬每周四连续通宵加班喝咖啡后，次日晨间静息心率飙升至110+且频繁早搏",
            confidence=0.96,
            participant_refs=[ObjectRef(object_id=user_ent.object_id, revision=1)],
            evidence_set_refs=[
                ObjectRef(object_id=ev_health_work.object_id, revision=1)
            ],
            event_time=TemporalExtent(
                start=datetime(2025, 7, 15, 2, 0, tzinfo=UTC),
                end=datetime(2025, 7, 29, 9, 0, tzinfo=UTC),
            ),
            occurred=TemporalExtent(
                start=datetime(2025, 7, 15, 2, 0, tzinfo=UTC),
                end=datetime(2025, 7, 29, 9, 0, tzinfo=UTC),
            ),
            learned_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            recorded_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            created_by="sim_generator",
        )
        objects.append(anchor_health_work)

        claim_health_work = Claim(
            object_id="claim_overtime_arrhythmia_causality",
            subject_id=user_ent.object_id,
            revision=1,
            claimant_id="ai_cognition_brain",
            claim_type=ClaimType.INFERENCE,
            content="凌晨2点后通宵加班与大剂量咖啡因摄入是导致次日室性早搏与心率骤升的决定性生理诱因，应建立前置疲劳熔断保护。",
            confidence=0.96,
            valid_time=TemporalExtent.point(datetime(2025, 7, 30, 10, 0, tzinfo=UTC)),
            asserted_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            knowledge_state=KnowledgeState.INFERRED,
            support_evidence_set_refs=[
                ObjectRef(object_id=ev_health_work.object_id, revision=1)
            ],
            occurred=TemporalExtent.point(datetime(2025, 7, 30, 10, 0, tzinfo=UTC)),
            learned_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            recorded_at=datetime(2025, 7, 30, 10, 0, tzinfo=UTC),
            created_by="sim_generator",
        )
        objects.append(claim_health_work)

        # 7. 生成海量高熵日常观测
        remaining_count = max(0, target_count - len(objects))
        cur_time = START_TIME
        time_step = timedelta(minutes=15)

        for idx in range(remaining_count):
            cur_time += time_step
            kind_rand = self.rng.random()
            if kind_rand < 0.65:
                hr = self.rng.randint(60, 95)
                obs = Observation(
                    object_id=f"obs_bio_stream_{idx}",
                    subject_id="user_1",
                    revision=1,
                    source_kind="biometrics",
                    modality="json",
                    value=json.dumps(
                        {"heart_rate": hr, "steps": self.rng.randint(0, 150)}
                    ),
                    occurred=TemporalExtent.point(cur_time),
                    learned_at=cur_time,
                    recorded_at=cur_time,
                    created_by="sim_generator",
                )
            elif kind_rand < 0.85:
                chats = [
                    "今天天气真好，出去散步了半小时",
                    "中午食堂的红烧肉做咸了",
                    "把下周的技术方案初稿发给同事评审了",
                    "买了杯美式咖啡提神",
                    "听了一期人工智能与心智哲学的播客",
                ]
                obs = Observation(
                    object_id=f"obs_chat_stream_{idx}",
                    subject_id="user_1",
                    revision=1,
                    source_kind="chat",
                    modality="text",
                    value=self.rng.choice(chats),
                    occurred=TemporalExtent.point(cur_time),
                    learned_at=cur_time,
                    recorded_at=cur_time,
                    created_by="sim_generator",
                )
            else:
                cost = self.rng.randint(15, 200)
                obs = Observation(
                    object_id=f"obs_finance_stream_{idx}",
                    subject_id="user_1",
                    revision=1,
                    source_kind="transaction",
                    modality="text",
                    value=f"微信支付消费 {cost} 元，用于日常餐饮便利店。",
                    occurred=TemporalExtent.point(cur_time),
                    learned_at=cur_time,
                    recorded_at=cur_time,
                    created_by="sim_generator",
                )
            objects.append(obs)

        return objects, entity_ids


def populate_massive_world(
    store: SQLiteWorldStore,
    target_count: int = 5000,
    batch_size: int = 500,
    seed: int = 42,
) -> MassiveBenchStats:
    """高效批量灌入海量真实数据流进入多维世界。"""
    gen = MassiveLifeBenchGenerator(seed=seed)
    t0 = time.perf_counter()
    objects, _ent_ids = gen.generate_world_dataset(target_count=target_count)

    obs_cnt = 0
    ent_cnt = 0
    rel_cnt = 0
    anchor_cnt = 0
    claim_cnt = 0
    ev_cnt = 0

    for o in objects:
        if isinstance(o, Observation):
            obs_cnt += 1
        elif isinstance(o, Entity):
            ent_cnt += 1
        elif isinstance(o, Relation):
            rel_cnt += 1
        elif isinstance(o, EventAnchor):
            anchor_cnt += 1
        elif isinstance(o, Claim):
            claim_cnt += 1
        elif isinstance(o, EvidenceSet):
            ev_cnt += 1

    for i in range(0, len(objects), batch_size):
        chunk = objects[i : i + batch_size]
        op = OperationRequest(
            operation_id=new_operation_id(),
            operation_name="sim.massive.populate",
            expected_world_revision=store.current_world_revision(),
            reason=f"Populate synthetic chunk {i}~{i + len(chunk)}",
            idempotency_key=f"chunk_{i}_{seed}",
            source_class=SourceClass.AI_COGNITION,
        )
        store.commit(chunk, op)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return MassiveBenchStats(
        total_observations=obs_cnt,
        total_entities=ent_cnt,
        total_relations=rel_cnt,
        total_event_anchors=anchor_cnt,
        total_claims=claim_cnt,
        total_evidence_sets=ev_cnt,
        generation_time_ms=elapsed_ms,
    )
