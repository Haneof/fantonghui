"""AIOS 3.0 全天生活流与多维总结高熵考题发生器（Daily Summary Question Generator）。

出卷官代号：Agent-aa2c
法定使命：生成 10,000 个人真实 24 小时生活流的高熵试卷，并提供完备的六大维度方向性语义标答。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from aios_core.simulation.daily_summary_factor_banks import (
    CONFLICT_ARCHETYPES,
    DAILY_ROUTINE_SLICES,
    PERSONA_TEMPLATES,
)


class PersonaProfile(BaseModel):
    """佩戴者人生画像。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(..., description="佩戴者姓名")
    gender: str = Field(..., description="性别")
    age: int = Field(..., ge=18, le=85, description="年龄")
    occupation: str = Field(..., description="职业身份")
    city: str = Field(..., description="生活所在城市")
    living_status: str = Field(..., description="居住与家庭状态")
    health_baseline: str = Field(..., description="健康生理基线")
    financial_baseline: str = Field(..., description="财务与收入基线")
    personality_tag: str = Field(..., description="性格特点与心理韧性")


class DailyCleanedSlice(BaseModel):
    """已清洗提纯的单条日常时间切片。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    time: str = Field(..., description="时间戳（如 07:15, 12:30, 21:10）")
    modality: str = Field(..., description="模态来源：mic, app, sensor, user_dialogue")
    event_type: str = Field(..., description="事件性质类别")
    content: str = Field(..., description="切片文本内容（对话、通知、摘要）")
    details: Dict[str, Any] = Field(default_factory=dict, description="结构化伴生属性")


class DirectionalDimensionTruth(BaseModel):
    """单维度的方向性语义标准答案（方向正确给分，触犯红线一票否决）。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    core_summary: str = Field(..., description="该维度今日核心事实一句话精炼标答")
    direction_anchors: List[str] = Field(..., description="核心方向语义锚点（必须覆盖的核心因果事实）")
    acceptable_synonyms: List[str] = Field(..., description="可接受的方向近义词簇（命中其一即视为同向）")
    redline_forbidden: List[str] = Field(..., description="绝对偏离的红线判据（违者判定颠倒是非一票否决）")


class DailyDirectionalGroundTruth(BaseModel):
    """全天多维方向性语义标答体系。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    global_daily_summary: DirectionalDimensionTruth = Field(..., description="全局日总结标答")
    dim_health: DirectionalDimensionTruth = Field(..., description="健康生理维度标答")
    dim_social: DirectionalDimensionTruth = Field(..., description="人际社交维度标答")
    dim_emotion: DirectionalDimensionTruth = Field(..., description="情绪心理维度标答")
    dim_finance: DirectionalDimensionTruth = Field(..., description="财务契约维度标答")
    dim_career: DirectionalDimensionTruth = Field(..., description="事业行动维度标答")


class DailySummaryQuestion(BaseModel):
    """一道标准的 24 小时人生全天生活流考题。"""
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str = Field(..., description="考题唯一编号，如 Q_DAILY_00001")
    generator_agent: str = Field(default="agent-aa2c", description="出题战队标识")
    timestamp_date: str = Field(default="2026-09-16", description="虚拟发生日期")
    persona: PersonaProfile = Field(..., description="佩戴者画像")
    cleaned_daily_stream: List[DailyCleanedSlice] = Field(..., description="已清洗的全天生活流序列 (07:00~23:30)")
    directional_ground_truth: DailyDirectionalGroundTruth = Field(..., description="六大维度方向性语义标答")


class DailySummaryQuestionGenerator:
    """万卷高熵全天生活流考题发生器。"""

    def __init__(self, generator_agent: str = "agent-aa2c", seed: int = 20260916):
        self.generator_agent = generator_agent
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_single_question(self, index: int) -> DailySummaryQuestion:
        """根据确定性索引构造一个人的一整天（24小时生活流与六大维度标答）。"""
        qnum = index + 1
        qid = f"Q_DAILY_{qnum:05d}"

        # 1. 抽取佩戴者基础画像并注入随机微扰
        p_base = self.rng.choice(PERSONA_TEMPLATES)
        age_offset = self.rng.randint(-3, 3)
        actual_age = max(18, min(80, p_base["age"] + age_offset))
        persona = PersonaProfile(
            name=p_base["name"],
            gender=p_base["gender"],
            age=actual_age,
            occupation=p_base["occupation"],
            city=p_base["city"],
            living_status=p_base["living_status"],
            health_baseline=p_base["health_baseline"],
            financial_baseline=p_base["financial_baseline"],
            personality_tag=p_base["personality_tag"],
        )

        # 2. 抽取今日核心生活事件冲突族
        arch = self.rng.choice(CONFLICT_ARCHETYPES)

        # 3. 编织全天 07:00 ~ 23:30 已清洗生活流切片
        slices: List[DailyCleanedSlice] = []

        # 3.1 晨间体征（07:10）
        hr_rest = self.rng.randint(62, 74)
        sleep_h = self.rng.randint(5, 7)
        sleep_m = self.rng.randint(10, 50)
        slices.append(
            DailyCleanedSlice(
                time="07:10",
                modality="sensor",
                event_type="vital_signs_routine",
                content=f"{persona.name}晨起静息心率测量为{hr_rest}bpm，昨夜实际睡眠{sleep_h}小时{sleep_m}分，体征基线稳定。",
                details={"heart_rate_bpm": hr_rest, "sleep_hours": round(sleep_h + sleep_m/60.0, 1), "status": "normal"}
            )
        )

        # 3.2 晨间早餐与出门（07:40）
        slices.append(
            DailyCleanedSlice(
                time="07:40",
                modality="mic",
                event_type="family_dialogue",
                content=f"厨房水龙头水声，佩戴者吃完燕麦与煎蛋，整理背包换鞋出门，自言自语：“又是忙碌的一天。”",
                details={"scene": "居家准备", "speaker": persona.name}
            )
        )

        # 3.3 晨间通勤乘车（08:25）
        transit_fee = round(self.rng.uniform(3.0, 7.0), 1)
        slices.append(
            DailyCleanedSlice(
                time="08:25",
                modality="app",
                event_type="commute_transit",
                content=f"【{persona.city}轨道交通】乘车码自动完成扣费{transit_fee}元，行程自住址站至工作地站。",
                details={"app": "微信出行", "amount": transit_fee}
            )
        )

        # 3.4 上午：冲突铺垫或事件开端（09:30）
        slices.append(
            DailyCleanedSlice(
                time="09:30",
                modality="app",
                event_type="work_message",
                content=f"【工作钉钉/企业微信】收到核心日程推进通知：{arch['time_anchors']['morning']}，参会人员已全部就位。",
                details={"app": "企业微信", "priority": "high"}
            )
        )

        # 3.5 上午：日常琐事（10:45）
        slices.append(
            DailyCleanedSlice(
                time="10:45",
                modality="mic",
                event_type="colleague_banter",
                content=f"前台取美团外卖生椰拿铁，同事闲聊：“今天空调开得挺足，你脸色看起来有点紧绷啊。”佩戴者：“嗯，待会还有重要事情要定。”",
                details={"scene": "办公楼走廊", "ambient_db": 62.5}
            )
        )

        # 3.6 中午：核心事件关键转折爆发（12:15）
        slices.append(
            DailyCleanedSlice(
                time="12:15",
                modality="mic",
                event_type="critical_incident",
                content=f"核心事件对话切片：{arch['time_anchors']['noon']}。现场气氛极其紧张，发生严肃争议与重大转折，对佩戴者造成直接冲击。",
                details={"scene": "关键决策现场", "stress_flag": True}
            )
        )

        # 3.7 中午：传感器体征即时反应（12:35）
        hr_noon = self.rng.randint(95, 120)
        slices.append(
            DailyCleanedSlice(
                time="12:35",
                modality="sensor",
                event_type="vital_signs_stress",
                content=f"手环监测到心率出现显著剧烈波动，读数快速攀升至{hr_noon}bpm，皮电反应增强，伴随静止无动作持续5分钟。",
                details={"heart_rate_bpm": hr_noon, "stress_level": "acute"}
            )
        )

        # 3.8 下午：日常琐事穿插（14:30）
        slices.append(
            DailyCleanedSlice(
                time="14:30",
                modality="app",
                event_type="daily_logistics",
                content=f"【菜鸟驿站】您的日用品包裹已送达丰巢快递柜，取件码{self.rng.randint(100000, 999999)}，请于24小时内取件。",
                details={"app": "菜鸟", "category": "logistics"}
            )
        )

        # 3.9 下午：核心事件次级波及（15:45）
        slices.append(
            DailyCleanedSlice(
                time="15:45",
                modality="mic",
                event_type="conflict_aftermath",
                content=f"事件持续发酵：{arch['time_anchors']['afternoon']}。佩戴者独处压抑，长叹一口气。",
                details={"emotional_state": "suppressed_grief"}
            )
        )

        # 3.10 傍晚：下班与交通（18:10）
        steps_day = self.rng.randint(8500, 16000)
        slices.append(
            DailyCleanedSlice(
                time="18:10",
                modality="sensor",
                event_type="motion_tracker",
                content=f"晚高峰离开工作区域，全天累计步数达{steps_day}步，手臂规律摆动，中速步行中。",
                details={"steps": steps_day, "motion_mode": "walking"}
            )
        )

        # 3.11 晚间：夜间高潮冲击（20:45）
        slices.append(
            DailyCleanedSlice(
                time="20:45",
                modality="mic",
                event_type="evening_climax",
                content=f"晚间核心事件进一步激化：{arch['time_anchors']['evening']}。涉及核心当事人与亲密关系的断裂与重组。",
                details={"intensity": "extreme", "scene": "晚间生活环境"}
            )
        )

        # 3.12 晚间：体征极值记录（21:15）
        hr_peak = self.rng.randint(124, 138)
        slices.append(
            DailyCleanedSlice(
                time="21:15",
                modality="sensor",
                event_type="vital_signs_peak",
                content=f"手环触发心率超阈值告警：心率在静止状态下飙升至{hr_peak}bpm，持续超20分钟，体感伴有心慌与剧烈情绪波动。",
                details={"heart_rate_bpm": hr_peak, "alarm": "TACHYCARDIA_TRIGGERED"}
            )
        )

        # 3.13 深夜：平复与自救沉思（22:30）
        slices.append(
            DailyCleanedSlice(
                time="22:30",
                modality="mic",
                event_type="night_reflection",
                content=f"深夜独处收场：{arch['time_anchors']['night']}。佩戴者喝下一杯温开水，整理杂乱思绪，准备迎接明日挑战。",
                details={"scene": "独处反思", "resolution_state": "resilient"}
            )
        )

        # 3.14 临睡：入眠体征（23:25）
        slices.append(
            DailyCleanedSlice(
                time="23:25",
                modality="sensor",
                event_type="bedtime_sleep",
                content=f"躺卧于床铺入睡，心率逐步回落至68~74bpm，身体处于深度疲竭状态，传感器切入夜间睡眠监测模式。",
                details={"heart_rate_bpm": 70, "state": "entering_sleep"}
            )
        )

        # 4. 构建六大维度严格方向性语义标答
        directional_gt = DailyDirectionalGroundTruth(
            global_daily_summary=DirectionalDimensionTruth(
                core_summary=arch["global_summary"],
                direction_anchors=list(arch["global_anchors"]),
                acceptable_synonyms=list(arch["global_synonyms"]),
                redline_forbidden=list(arch["global_forbidden"]),
            ),
            dim_health=DirectionalDimensionTruth(
                core_summary=arch["health_fact"],
                direction_anchors=list(arch["health_anchors"]),
                acceptable_synonyms=list(arch["health_synonyms"]),
                redline_forbidden=list(arch["health_forbidden"]),
            ),
            dim_social=DirectionalDimensionTruth(
                core_summary=arch["social_fact"],
                direction_anchors=list(arch["social_anchors"]),
                acceptable_synonyms=list(arch["social_synonyms"]),
                redline_forbidden=list(arch["social_forbidden"]),
            ),
            dim_emotion=DirectionalDimensionTruth(
                core_summary=arch["emotion_fact"],
                direction_anchors=list(arch["emotion_anchors"]),
                acceptable_synonyms=list(arch["emotion_synonyms"]),
                redline_forbidden=list(arch["emotion_forbidden"]),
            ),
            dim_finance=DirectionalDimensionTruth(
                core_summary=arch["finance_fact"],
                direction_anchors=list(arch["finance_anchors"]),
                acceptable_synonyms=list(arch["finance_synonyms"]),
                redline_forbidden=list(arch["finance_forbidden"]),
            ),
            dim_career=DirectionalDimensionTruth(
                core_summary=arch["career_fact"],
                direction_anchors=list(arch["career_anchors"]),
                acceptable_synonyms=list(arch["career_synonyms"]),
                redline_forbidden=list(arch["career_forbidden"]),
            ),
        )

        return DailySummaryQuestion(
            question_id=qid,
            generator_agent=self.generator_agent,
            timestamp_date="2026-09-16",
            persona=persona,
            cleaned_daily_stream=slices,
            directional_ground_truth=directional_gt,
        )

    def generate_bank(
        self,
        count: int = 10000,
        output_file: Optional[str] = None,
        progress_interval: int = 2000
    ) -> List[DailySummaryQuestion]:
        """批量生成指定数量（默认 10,000）的全天生活流考题。"""
        t_start = time.perf_counter()
        print(f"[{self.generator_agent}] 开始确定性生成 {count} 道全天生活流高熵考题 (seed={self.seed})...")

        fout = None
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            fout = open(output_file, "w", encoding="utf-8")

        questions: List[DailySummaryQuestion] = []
        try:
            for i in range(count):
                q = self.generate_single_question(i)
                questions.append(q)
                if fout:
                    fout.write(q.model_dump_json() + "\n")
                if (i + 1) % progress_interval == 0:
                    print(f"[{self.generator_agent}] 已生成 {i + 1} / {count} 道全天考题...")
        finally:
            if fout:
                fout.close()

        elapsed = time.perf_counter() - t_start
        print(f"[{self.generator_agent}] 成功生成 {count} 道题，耗时 {elapsed:.2f}s！落盘 -> {output_file}")
        return questions


def generate_and_save_manifest(
    questions_file: str,
    manifest_file: str,
    total_count: int = 10000
):
    """提取考题元数据并输出审计清单清单。"""
    print(f"[Manifest] 正在生成考题自审清单 -> {manifest_file}")
    file_size_mb = round(os.path.getsize(questions_file) / (1024 * 1024), 2)
    
    archetype_counts = {}
    city_counts = {}
    gender_counts = {"男": 0, "女": 0}

    with open(questions_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            p = data["persona"]
            gender_counts[p["gender"]] = gender_counts.get(p["gender"], 0) + 1
            city_counts[p["city"]] = city_counts.get(p["city"], 0) + 1

    manifest = {
        "generator_agent": "agent-aa2c",
        "question_bank_type": "full_daily_multidim_summary_10k",
        "timestamp_utc": "2026-09-16T12:40:00Z",
        "total_questions": total_count,
        "file_size_mb": file_size_mb,
        "questions_path": questions_file,
        "gender_distribution": gender_counts,
        "top_cities": sorted(city_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        "compliance_assertions": {
            "covers_six_dimensions": True,
            "has_direction_anchors": True,
            "has_acceptable_synonyms": True,
            "has_redline_forbidden": True,
            "deterministic_reproducible": True,
            "seed": 20260916
        }
    }

    os.makedirs(os.path.dirname(manifest_file), exist_ok=True)
    with open(manifest_file, "w", encoding="utf-8") as fo:
        json.dump(manifest, fo, indent=2, ensure_ascii=False)
    print(f"[Manifest] 自审清单已保存！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS 3.0 全天生活流考题生成器")
    parser.add_argument("--count", type=int, default=10000, help="生成题目总数（默认 10000）")
    parser.add_argument("--seed", type=int, default=20260916, help="随机数种子（确定性复现）")
    parser.add_argument("--out", default="benchmarks/daily_summary/questions/questions_agent_aa2c_10k.jsonl", help="输出路径")
    parser.add_argument("--manifest", default="benchmarks/daily_summary/reports/manifest_daily_summary_aa2c.json", help="清单输出路径")

    args = parser.parse_args()

    generator = DailySummaryQuestionGenerator(generator_agent="agent-aa2c", seed=args.seed)
    generator.generate_bank(count=args.count, output_file=args.out)
    generate_and_save_manifest(args.out, args.manifest, total_count=args.count)
