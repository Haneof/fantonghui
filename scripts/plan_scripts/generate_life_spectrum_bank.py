#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性生成《AIOS 3.0 全人生谱系高熵数据清洗题库》（出题侧交付脚本）。

用法
----
    # 1) 标准交付：每个战队 10,000 道明文题库（Master Dispatch #11 口径）
    python scripts/plan_scripts/generate_life_spectrum_bank.py \
        --agent-id agent-01a0a9fd --count 10000 --seed 20260916 \
        --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl \
        --ground-truth-out benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd.jsonl

    # 2) 全量 30,000 道（体积防护：直接落 gzip，gunzip 后可还原标准 JSONL）
    python scripts/plan_scripts/generate_life_spectrum_bank.py \
        --agent-id agent-01a0a9fd --count 30000 --seed 20260916 \
        --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd_30k.jsonl.gz \
        --ground-truth-out benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd_30k.jsonl.gz

    # 3) 审计既有题库（不重新生成）
    python scripts/plan_scripts/generate_life_spectrum_bank.py --verify-only \
        --questions-out benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl

设计纪律
--------
* 全流程确定性：同 (agent_id, seed, count, start_index) 必得同一套题库与同一份 SHA256；
* 生成即校验：每一行都过 `validate_question()`（CleaningQuestion 契约）+ 全量自洽审计；
* 不写死答案：标答只给"方向性同义词簇 + 实体锚点 + 一句话核心事实"，裁判端做方向容差判分。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, TextIO

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aios_core.simulation.life_spectrum_question_generator import (  # noqa: E402
    GeneratorConfig,
    FullLifeSpectrumQuestionGenerator,
    audit_questions,
    factor_inventory,
    validate_question,
)

UTC = timezone.utc
TRUTH_KEYS = ("question_id", "ground_truth_facts", "ground_truth_junk_ids")


def _open_writer(path: Path) -> TextIO:
    """按扩展名选择写入器：.gz -> 确定性 gzip（mtime=0），其余按 UTF-8 明文。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        raw = path.open("wb")
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0)
        return io.TextIOWrapper(gz, encoding="utf-8", newline="\n")
    return path.open("w", encoding="utf-8", newline="\n")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line(record: Dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"


def _ground_truth_record(question: Dict[str, Any]) -> Dict[str, Any]:
    """标答底稿（裁判/答题双方共用；只含方向性标答，不带原始噪音流）。"""

    record = {key: question[key] for key in TRUTH_KEYS}
    record["generator_agent"] = question["generator_agent"]
    record["domain"] = question["factor_ids"]["domain"]
    record["focus_stream"] = question["factor_ids"]["focus_stream"]
    return record


def _field_schema() -> Dict[str, Any]:
    """交付给各战队的字段字典（题目流的紧凑键名映射 + 语义说明）。"""

    return {
        "question_id": "题目唯一编号 Q_<generator_agent>_<00001..>",
        "generator_agent": "出题战队编号（答题端严禁 solver_agent == generator_agent）",
        "timestamp_utc": "虚拟事件发生时间（ISO 8601，UTC）",
        "difficulty": "EASY / MEDIUM / HARD / ADVERSARIAL",
        "persona_tag": "维度一佩戴者身份标签（编号_身份_年龄_主诉）",
        "factor_ids": {
            "demographic": "维度一 D01..D50 佩戴者身份",
            "core_event": "维度二主事件族（H/F/S/C/L + 两位编号）",
            "core_event_secondary": "维度二次事件族（跨域叠加，可为空串）",
            "sensor": "维度三传感器波形 S00..S06",
            "acoustic": "维度四声学拓扑 A01..A12",
            "linguistic": "维度五方言包（可叠加修辞陷阱，如 shaanxi+argot_hidden）",
            "speaker_topology": "维度六声纹拓扑规模（3~24）",
            "trap": "维度七对抗陷阱 T01..T08（恒有，T00 保留位）",
            "focus_stream": "本题主打数据流：sensor / mic / voiceprint / app / dialogue",
            "domain": "主事件所属认知域 dim:health / dim:finance / dim:social / dim:career / dim:life",
            "slots": "本题随机槽位指纹（金额|日期|城市），用于唯一性审计",
        },
        "sensor_stream": {
            "sample_id": "传感器样本 ID（也是事实溯源可用 ID）",
            "profile": "波形模板编号",
            "raw_imu_g_force": "IMU 合加速度多点采样（G）",
            "heart_rate_bpm": "心率",
            "hr_rest_bpm/hr_max_bpm": "阵发性心动过速的静息值与峰值（S03）",
            "pvc_burst_count": "室性早搏阵发次数",
            "sinus_pause_s": "窦性停搏秒数（S04）",
            "baro_hpa/baro_drop_hpa": "气压计读数与骤降幅度（S05）",
            "impact_peak_g/post_impact_still_s": "冲击峰值与坠落后静止时长（S01）",
            "false_impact_note": "伪冲击判据说明（S02）",
            "cadence_spm/motion_state": "步频与运动状态（S06）",
            "spO2_pct/ambient_temp_c/gps_loc": "血氧 / 环境温度 / 定位",
            "counter_evidence": "陷阱反证（如假摔无冲击波峰），系统侧证据",
        },
        "mic_stream[]": {
            "sid": "片段 ID（垃圾剪枝以该 ID 为准）",
            "spk": "声纹标识 spk_*（背景陌生人片段即铁律四垃圾）",
            "db": "环境声压级 dB",
            "text": "转写文本（方言已转写为首通话）",
            "junk": "出题方标注的垃圾标记（ground_truth_junk_ids 为权威判定）",
            "overlap": "重叠说话人标识（抢话场景）",
            "dialect": "方言来源说明",
        },
        "voiceprint_cluster": {
            "user": "佩戴者声纹 ID",
            "detected": "全部检出说话人（3~24）",
            "key": "关键交互人声纹（佩戴者与事件相关方）",
            "overlap": "发生重叠抢话的片段 ID",
            "detected_only": "仅检出无有效语音片段的说话人（不得作为证据引用）",
        },
        "app_message_stream[]": {
            "mid": "消息 ID（垃圾剪枝以该 ID 为准）",
            "app": "应用名（WeChat / Alipay / Email / HospitalApp / 法院/银行/平台等）",
            "sender": "发送者（人或系统通知）",
            "text": "消息正文",
            "junk": "出题方标注的垃圾标记",
            "role": "counter 表示该消息是陷阱反证",
        },
        "user_dialogue_stream[]": {
            "uid": "原话 ID（垃圾剪枝以该 ID 为准）",
            "text": "佩戴者原话 / 自言自语",
            "scene": "场景描述",
            "junk": "出题方标注的垃圾标记",
            "rhet": "修辞类型（口嗨吹牛 / 反讽 / 自杀隐喻 / ...）",
        },
        "ground_truth_facts[]": {
            "fact_id": "事实编号",
            "dimension_id": "认知维度归属",
            "semantic_intent": "语义意图方向（UPPER_SNAKE）",
            "anchor_entities": "实体锚点（人名/金额/机构）",
            "directional_keywords": "方向性同义词簇（≥6 个，命中任一即方向相符）",
            "core_content": "基准事实描述（方向正确即可得分，严禁字面抠字）",
            "source_ref_id": "不可篡改的原始证据片段 ID",
            "confidence": "出题方置信度（恒为 1.0）",
        },
        "ground_truth_junk_ids": "必须被物理剪枝的垃圾片段 ID 列表（铁律四）",
    }


def _iter_questions(generator: FullLifeSpectrumQuestionGenerator, questions_out: Path, ground_truth_out: Path,
                    strict: bool, stats: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """边写边校验：每一行都过 CleaningQuestion 契约，结构非法立即抛错（零容忍）。"""

    with _open_writer(questions_out) as q_writer, _open_writer(ground_truth_out) as gt_writer:
        for question in generator.generate_all():
            if strict:
                validate_question(question)
            q_writer.write(_line(question))
            gt_writer.write(_line(_ground_truth_record(question)))
            stats["written"] += 1
            yield question


def generate_bank(args: argparse.Namespace) -> Dict[str, Any]:
    config = GeneratorConfig(
        agent_id=args.agent_id,
        seed=args.seed,
        count=args.count,
        start_index=args.start_index,
    )
    generator = FullLifeSpectrumQuestionGenerator(config)
    questions_out = Path(args.questions_out)
    ground_truth_out = Path(args.ground_truth_out)

    started = time.time()
    stats: Dict[str, Any] = {"written": 0}
    audit_iter = _iter_questions(generator, questions_out, ground_truth_out, not args.no_validate, stats)
    if args.audit_sample > 0:
        audit_iter = _limited(audit_iter, args.audit_sample)
    audit = audit_questions(audit_iter)
    elapsed = round(time.time() - started, 2)

    manifest = {
        "agent_id": args.agent_id,
        "seed": args.seed,
        "count": args.count,
        "rows_written": stats["written"],
        "start_index": args.start_index,
        "question_id_range": [f"Q_{args.agent_id}_{args.start_index:05d}",
                              f"Q_{args.agent_id}_{args.start_index + args.count - 1:05d}"],
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_seconds": elapsed,
        "factor_inventory": factor_inventory(),
        "audit_sample_size": audit["total"],
        "audit": audit,
        "files": {
            "questions": {
                "path": str(questions_out),
                "bytes": questions_out.stat().st_size,
                "compressed": questions_out.suffix == ".gz",
                "sha256": _sha256_of(questions_out),
            },
            "ground_truth": {
                "path": str(ground_truth_out),
                "bytes": ground_truth_out.stat().st_size,
                "compressed": ground_truth_out.suffix == ".gz",
                "sha256": _sha256_of(ground_truth_out),
            },
        },
        "dataset_discipline": {
            "domain_floor": "任一大认知域 ≥ 15%（本库按 5 域各 20% 均匀配比）",
            "focus_stream_ratio": "sensor 30% / mic 30% / voiceprint 20% / app 15% / dialogue 5%",
            "difficulty_ratio": "EASY 15% / MEDIUM 40% / HARD 30% / ADVERSARIAL 15%",
            "answer_policy": "标答只给方向性同义词簇与实体锚点，裁判端按方向容差判分（严禁抠字眼）",
            "junk_policy": "铁律四：环境叫卖/营销短信/刷屏验证码/口头禅发泄必须物理剪枝",
            "schema_policy": "五大数据流为自由结构（Dict[str, Any]），键名映射见字段字典，语义等价即可提交",
        },
    }
    return manifest


def _limited(iterable: Iterator[Dict[str, Any]], limit: int) -> Iterator[Dict[str, Any]]:
    """只审计前 limit 题，但整卷仍完整生成与落盘。"""

    emitted = 0
    for item in iterable:
        if emitted >= limit:
            break
        emitted += 1
        yield item
    for _ in iterable:  # 继续驱动生成器把剩余题目写完
        pass


def write_report(manifest: Dict[str, Any], report_path: Path) -> None:
    audit = manifest["audit"]
    inventory = manifest["factor_inventory"]
    lines = [
        f"# 出题交付报告 · 战队 {manifest['agent_id']}",
        "",
        f"> 生成时间（UTC）：{manifest['generated_at_utc']} ｜ 随机种子：`{manifest['seed']}` ｜ 题量：{manifest['count']}",
        f"> 编号区间：`{manifest['question_id_range'][0]}` → `{manifest['question_id_range'][1]}` ｜ 生成耗时：{manifest['elapsed_seconds']}s",
        "",
        "## 一、七维因子库规模",
        "",
        "| 维度 | 规模 |",
        "| --- | --- |",
        f"| 维度一 佩戴者身份（16~90 岁全职业光谱） | {inventory['personas']} 位 |",
        f"| 维度二 事件族（5 大认知域 × 极限事件谱系） | {inventory['event_families']} 族 |",
        f"| 维度三 传感器波形 | {inventory['sensor_profiles']} 类（S00~S06） |",
        f"| 维度四 声学环境拓扑 | {inventory['acoustic_topologies']} 类（A01~A12） |",
        f"| 维度五 方言包 / 修辞陷阱 | {inventory['dialect_packs']} 套 / {inventory['rhetoric_specs']} 类 |",
        f"| 维度六 声纹说话人角色 | {inventory['speaker_roles']} 类（3~24 人拓扑） |",
        f"| 维度七 真假对抗陷阱 | {inventory['traps']} 类（T01~T08） |",
        "",
        f"## 二、审计结论（抽样 {audit['total']} 题 / 全量 {manifest['rows_written']} 题均已过 CleaningQuestion 契约校验）",
        "",
        f"- 因子签名唯一率：**{audit['unique_factor_signatures']}/{audit['total']}**",
        f"- 核心事实文本唯一率：**{audit['unique_core_contents']}/{audit['total']}**",
        f"- 平均每题标答事实数：**{audit['facts_per_question']}**；垃圾片段占比：**{audit['junk_ratio']}**",
        f"- 声纹规模区间：**{audit['speaker_count_min']} ~ {audit['speaker_count_max']}** 人",
        f"- 结构自洽性问题：**{audit['duct_issue_count']}**（垃圾 ID 越界 / 事实溯源缺失 / 方向词簇不足 6 个 / 非法声纹标识）",
        "",
        "### 认知域配比",
        "",
        "| 认知域 | 题数 | 占比（红线 ≥15%）|",
        "| --- | --- | --- |",
    ]
    for domain, count in audit["domains"].items():
        lines.append(f"| {domain} | {count} | {audit['domain_ratio'][domain]:.1%} |")
    lines += ["", "### 数据流聚焦配比（Master Dispatch #11）", "", "| 数据流 | 题数 | 占比 |", "| --- | --- | --- |"]
    for stream, count in sorted(audit["focus_streams"].items()):
        lines.append(f"| {stream} | {count} | {audit['focus_ratio'][stream]:.1%} |")
    lines += ["", "### 难度配比", "", "| 难度 | 题数 |", "| --- | --- |"]
    for level, count in audit["difficulty"].items():
        lines.append(f"| {level} | {count} |")
    lines += ["", "### 对抗陷阱命中分布", "", "| 陷阱 | 命中题数 |", "| --- | --- |"]
    for trap, count in sorted(audit["traps"].items()):
        lines.append(f"| {trap} | {count} |")
    lines += ["", "### 方言覆盖", "", "| 方言包 | 题数 |", "| --- | --- |"]
    for dialect, count in sorted(audit["dialects"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {dialect} | {count} |")
    lines += [
        "",
        "## 三、交付文件与校验",
        "",
        f"- 考题集合：`{manifest['files']['questions']['path']}`（{manifest['files']['questions']['bytes']} 字节"
        f"{'，gzip 压缩' if manifest['files']['questions']['compressed'] else '，明文 JSONL'}）",
        f"  - SHA256 `{manifest['files']['questions']['sha256']}`",
        f"- 标答底稿：`{manifest['files']['ground_truth']['path']}`（{manifest['files']['ground_truth']['bytes']} 字节"
        f"{'，gzip 压缩' if manifest['files']['ground_truth']['compressed'] else '，明文 JSONL'}）",
        f"  - SHA256 `{manifest['files']['ground_truth']['sha256']}`",
        "",
        "> 压缩件还原方式：`gunzip -c questions_xxx.jsonl.gz > questions_xxx.jsonl`（逐行独立 JSON，可直接流式处理）。",
        "> 标答与题目同源同种子：同一 `question_id` 在两个文件中一一对应，标答文件只保留方向性事实簇与垃圾 ID。",
        "",
        "## 四、质量红线对照",
        "",
        "1. **零模板化**：每题由 7 维因子笛卡尔积 + 槽位随机（人名/金额/日期/地点/物品/症状/方言原话）生成，唯一率见上表；",
        "2. **逻辑自洽**：波形与事件族硬绑定（坠落必为高 G + 静止段，跑步基线绝不做心梗解释，碰瓷必无撞击波峰），身份年龄与事件族双向适配；",
        "3. **方向性标答**：每个事实自带 ≥6 个方向同义词，裁判端按方向容差判分，不做字面抠字；",
        "4. **真假对抗**：假转账截图、先承认后反悔、承诺撤回、假摔碰瓷、语音克隆、伪造病历、阴阳合同、伪造传感器理赔八类陷阱按难度注入；",
        "5. **铁律四垃圾**：叫卖噪音、营销短信、砍一刀、验证码、口头禅发泄全部列入 `ground_truth_junk_ids`，必须被物理剪枝；",
        "6. **证据可溯**：每条标答事实的 `source_ref_id` 均指向真实存在的片段 ID，传感器证据仅在波形异常时引用。",
        "",
        "## 五、复现方式",
        "",
        "```bash",
        "python scripts/plan_scripts/generate_life_spectrum_bank.py \\",
        f"    --agent-id {manifest['agent_id']} --count {manifest['count']} --seed {manifest['seed']} \\",
        f"    --questions-out {manifest['files']['questions']['path']} \\",
        f"    --ground-truth-out {manifest['files']['ground_truth']['path']}",
        "```",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _read_rows(path: Path) -> Iterator[Dict[str, Any]]:
    opener = gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open("r", encoding="utf-8")
    with opener as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:  # 行级损坏必须显式暴露
                raise ValueError(f"{path}:{line_number} JSON 解析失败: {exc}") from exc


def verify_bank(questions_path: Path, limit: int) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    invalid: List[str] = []
    for row in _read_rows(questions_path):
        if limit and len(rows) >= limit:
            break
        try:
            validate_question(row)
        except Exception as exc:  # 结构非法行必须在报告中呈现
            invalid.append(f"{row.get('question_id', '?')}: {exc}")
        rows.append(row)
    audit = audit_questions(rows)
    audit["schema_invalid_count"] = len(invalid)
    audit["schema_invalid_samples"] = invalid[:5]
    return audit


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description="AIOS 3.0 全人生谱系高熵题库生成器")
    parser.add_argument("--agent-id", default="agent-01a0a9fd", help="出题战队编号（写入 question_id）")
    parser.add_argument("--count", type=int, default=10000, help="题目数量")
    parser.add_argument("--seed", type=int, default=20260916, help="随机种子（决定整卷内容）")
    parser.add_argument("--start-index", type=int, default=1, help="起始编号")
    parser.add_argument("--questions-out", default="benchmarks/data_cleaning/questions/questions_agent-01a0a9fd.jsonl")
    parser.add_argument("--ground-truth-out", default="benchmarks/data_cleaning/ground_truth/gt_agent-01a0a9fd.jsonl")
    parser.add_argument("--manifest-out", default="benchmarks/data_cleaning/reports/manifest_agent-01a0a9fd.json")
    parser.add_argument("--report-out", default="benchmarks/data_cleaning/reports/generation_report_agent-01a0a9fd.md")
    parser.add_argument("--schema-out", default="benchmarks/data_cleaning/reports/question_schema_agent-01a0a9fd.json")
    parser.add_argument("--audit-sample", type=int, default=5000, help="审计抽样题数（0 表示全量审计）")
    parser.add_argument("--no-validate", action="store_true", help="跳过逐行 CleaningQuestion 契约校验（不建议）")
    parser.add_argument("--verify-only", action="store_true", help="只审计既有题库，不重新生成")
    parser.add_argument("--verify-limit", type=int, default=0, help="verify 模式读取上限（0 表示全量）")
    args = parser.parse_args(list(argv))

    if args.verify_only:
        audit = verify_bank(Path(args.questions_out), args.verify_limit)
        print(json.dumps(audit, ensure_ascii=False, indent=1))
        return 0 if audit["duct_issue_count"] == 0 and audit["schema_invalid_count"] == 0 else 1

    manifest = generate_bank(args)
    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(manifest, Path(args.report_out))
    schema_path = Path(args.schema_out)
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(_field_schema(), ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {
        "questions": manifest["files"]["questions"]["path"],
        "ground_truth": manifest["files"]["ground_truth"]["path"],
        "questions_sha256": manifest["files"]["questions"]["sha256"],
        "count": manifest["count"],
        "start_index": manifest["start_index"],
        "elapsed_seconds": manifest["elapsed_seconds"],
        "audit": {key: manifest["audit"][key] for key in
                  ("total", "unique_factor_signatures", "unique_core_contents", "junk_ratio",
                   "facts_per_question", "speaker_count_min", "speaker_count_max",
                   "duct_issue_count")},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if manifest["audit"]["duct_issue_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
