"""Independent post-freeze grading for a pinned opponent daily bank.

Uses the opponent's reference judge byte-for-byte and labels its limitations;
no score corrections or substring games are applied. Provenance checks and
source-link diagnostics supplement, not replace, the reference score.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import zip_longest
import json
import lzma
from pathlib import Path
from statistics import mean

from aios_core.summaries.cross_team_daily_solver import BlindDailyQuestion, DIMS, SOLVER
from evaluator.daily_summary_aa2d_reference import (
    DailyLifeQuestion, DailySummaryDirectionalMatcher, DailySummarySubmission,
)


MAP = {"global_daily_summary": "global", "dim_health": "health", "dim_social": "social",
       "dim_emotion": "emotion", "dim_finance": "finance", "dim_career": "career"}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rows(path):
    opener = lzma.open if str(path).endswith(".xz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def split(qid):
    return "development" if int(hashlib.sha256(qid.encode()).hexdigest()[:8], 16) % 5 == 0 else "holdout"


def validate_submission(raw, question_id):
    if raw.get("question_id") != question_id or raw.get("solver_agent") != SOLVER:
        raise ValueError("answer identity mismatch")
    if any(not raw.get(f"generated_{dim}_summary", "").strip() for dim in DIMS):
        raise ValueError("empty summary exploits legacy substring scoring")
    return DailySummarySubmission.model_validate(raw)


def evaluate(questions, papers, source_manifest, run_dir, output):
    source = json.loads(Path(source_manifest).read_text(encoding="utf-8"))
    run_dir, output = Path(run_dir), Path(output)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if sha(questions) != manifest["blind_archive_sha256"] or sha(source_manifest) != manifest["source_manifest_sha256"]:
        raise ValueError("blind input or manifest hash mismatch")
    if sha(papers) != source["source_sha256"]:
        raise ValueError("original opponent paper checksum mismatch")
    if sha(Path(__file__).with_name("daily_summary_aa2d_reference.py")) != source["reference_judge_sha256"]:
        raise ValueError("reference judge changed")
    for name, digest in manifest["artifacts"].items():
        if Path(name).name != name or sha(run_dir / name) != digest:
            raise ValueError("frozen answer/audit checksum mismatch")
    output.mkdir(parents=True, exist_ok=False)
    seen = set()
    scores = defaultdict(list)
    dimension_scores = defaultdict(list)
    stats = defaultdict(Counter)
    examples = defaultdict(list)
    error_counts = defaultdict(Counter)
    by_dimension = Counter()
    with lzma.open(output / "per_question.jsonl.xz", "xt", encoding="utf-8") as details:
        for b, paper, answer, audit in zip_longest(rows(questions), rows(papers),
                rows(run_dir / "answers.jsonl.xz"), rows(run_dir / "audit.jsonl.xz")):
            if any(x is None for x in (b, paper, answer, audit)):
                raise ValueError("missing/extra row")
            blind = BlindDailyQuestion.model_validate(b)
            qid = blind.question_id
            if qid in seen or paper["question_id"] != qid or audit["question_id"] != qid:
                raise ValueError("duplicate or mismatched ID")
            seen.add(qid)
            if paper["generator_agent"] != source["generator_agent"]:
                raise ValueError("generator mismatch")
            if {k: paper[k] for k in b} != b:
                raise ValueError("projection does not match original evidence")
            question = DailyLifeQuestion.model_validate({**b, "directional_ground_truth": paper["directional_ground_truth"]})
            submission = validate_submission(answer, qid)
            report = DailySummaryDirectionalMatcher.evaluate_submission(question, submission).model_dump()
            diagnostics = []
            available = {f"{s.src}@{s.t}" for s in blind.cleaned_daily_stream}
            for ref_entries in audit["evidence"].values():
                for ref in ref_entries:
                    i = ref["slice_index"]
                    if not 0 <= i < len(blind.cleaned_daily_stream):
                        raise ValueError("bad source index")
                    s = blind.cleaned_daily_stream[i]
                    if ref["source_ref"] != f"{s.src}@{s.t}" or ref["source_sha256"] != hashlib.sha256(s.model_dump_json().encode()).hexdigest():
                        raise ValueError("source link hash mismatch")
            for key, result in report["dimension_results"].items():
                dim = MAP[key]
                truth = paper["directional_ground_truth"]["global_daily_summary" if dim == "global" else "dim:" + dim]
                expected = set(truth["key_evidence_refs"])
                cited = {x["source_ref"] for x in audit["evidence"][dim]}
                coverage = len(expected & cited) / max(len(expected), 1)
                diag = {"dimension": dim, "reference_score": result["score"],
                        "missed_anchors": result["missed_anchors"],
                        "uncited_reference_evidence": sorted(expected - cited),
                        "reference_evidence_missing_in_question": sorted(expected - available),
                        "reference_evidence_coverage": coverage,
                        "redline_strings": result["triggered_redline_violations"]}
                if result["score"] < 80:
                    diag.update({"reference_core_plot": truth["core_plot"],
                                 "submission": answer[f"generated_{dim}_summary"]})
                diagnostics.append(diag)
                by_dimension[dim] += 1
                for group in ("all", split(qid)):
                    dimension_scores[(group, dim)].append(result["score"])
                    stats[group]["dimension_count"] += 1
                    stats[group]["direction_literal_matches"] += result["direction_matched"]
                    stats[group]["evidence_coverage_sum"] += coverage
                    stats[group]["reference_missing_evidence"] += len(expected - available)
                    error_counts[group]["ANCHOR_LITERAL_MISS"] += len(result["missed_anchors"])
                    error_counts[group]["REFERENCE_REDLINE_MATCH"] += len(result["triggered_redline_violations"])
                    error_counts[group]["UNCITED_REFERENCE_EVIDENCE"] += len(expected - cited)
                    if not result["direction_matched"]:
                        error_counts[group]["DIRECTION_LITERAL_MISS"] += 1
                if split(qid) == "development" and result["score"] < 80 and len(examples[dim]) < 5:
                    examples[dim].append({"question_id": qid, **diag})
            for group in ("all", split(qid)):
                scores[group].append(report["overall_score"])
                stats[group]["passes"] += report["verdict"] == "PASS"
                stats[group]["fatal_redline_questions"] += report["fatal_redline_triggered"]
            details.write(json.dumps({**report, "split": split(qid), "diagnostics": diagnostics}, ensure_ascii=False, separators=(",", ":")) + "\n")
    if len(seen) != manifest["questions"] or len(seen) != source["questions"]:
        raise ValueError("unexpected question count")
    summary = {}
    for group, values in scores.items():
        count = len(values)
        summary[group] = {"questions": count, "reference_mean_score": mean(values),
                          "reference_passes": stats[group]["passes"],
                          "reference_pass_rate": stats[group]["passes"] / count,
                          "fatal_redline_questions": stats[group]["fatal_redline_questions"],
                          "mean_reference_evidence_coverage": stats[group]["evidence_coverage_sum"] / (6 * count),
                          "reference_missing_evidence": stats[group]["reference_missing_evidence"],
                          "dimension_mean_scores": {dim: mean(dimension_scores[(group, dim)]) for dim in DIMS},
                          "errors": dict(error_counts[group])}
    result = {"solver_version": manifest["solver_version"], "source_commit": source["source_commit"],
              "answer_sha256": manifest["artifacts"]["answers.jsonl.xz"], "reference_judge_sha256": source["reference_judge_sha256"],
              "summary": summary, "development_examples": examples,
              "limitations": ["Reference judge matches literal substrings, including redlines without negation scope; this is not semantic accuracy.",
                              "Empty answers and forged identities are rejected before the legacy judge to prevent its empty-substring perfect-score loophole.",
                              "Evidence coverage checks source citation, not full logical entailment or clinical causality.",
                              "Opponent labels can assert facts absent from or contradictory to the input. Scores are not altered to conceal this.",
                              "Only ID-disjoint development/holdout diagnostics; the same source templates may occur in both groups."]}
    (output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--papers", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evaluate(args.questions, args.papers, args.source_manifest, args.run_dir, args.output)
