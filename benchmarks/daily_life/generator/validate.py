"""Structural/temporal/accounting audit, deliberately not an answer-solving model."""
from __future__ import annotations

import hashlib
import json
import lzma
from collections import Counter
from datetime import datetime
from pathlib import Path

DIMENSIONS = ("global_daily_summary", "dim:health", "dim:social", "dim:emotion", "dim:finance", "dim:career")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_question(q):
    require(set(q) == {"question_id", "persona", "cleaned_daily_stream", "directional_ground_truth"}, "Question root fields differ from contract")
    p, stream, gt = q["persona"], q["cleaned_daily_stream"], q["directional_ground_truth"]
    require(p["fictional"] is True, "Synthetic provenance missing")
    require(18 <= p["age"] <= 90, "Implausible persona age")
    require(len(stream) >= 220, "Not enough daily slices")
    require(set(gt) == set(DIMENSIONS), "All six answer dimensions required")
    start = datetime.fromisoformat(p["day_window"]["start"])
    end = datetime.fromisoformat(p["day_window"]["end"])
    require(start.tzinfo is not None and end.tzinfo is not None, "Timezone required")
    require((end - start).total_seconds() == 86400, "Window is not 24 hours")
    require(start.hour == start.minute == 0, "Day does not start at midnight")
    require(start.date().isoformat() == p["day"], "Persona date mismatch")
    actors = {p["person_id"], *(c["entity_id"] for c in p["contacts"])}
    require(len(actors) == len(p["contacts"]) + 1, "Duplicate actor identity")
    ids, observations, channels, starts, mic_actors = set(), {}, Counter(), set(), set()
    prev, previous_steps = start, -1
    sleep = audit = None
    deltas, loan_principal = [], 0
    for s in stream:
        sid = s["slice_id"]
        require(sid not in ids, "Duplicate slice ID")
        ids.add(sid)
        observations[sid] = s
        a, b = datetime.fromisoformat(s["timestamp"]), datetime.fromisoformat(s["end_timestamp"])
        require(a.tzinfo is not None and b.tzinfo is not None, "Slice timezone missing")
        require(a == prev and a < b <= end, "Gap, overlap, unordered or out-of-window interval")
        prev = b
        starts.add(a.strftime("%H:%M"))
        require(s["modality"] in {"MIC", "APP", "SENSOR"}, "Unknown modality")
        channels[s["modality"]] += 1
        require(isinstance(s["text"], str) and s["text"].strip(), "Empty cleaned observation")
        require(s["participants"] and set(s["participants"]) <= actors, "Unbound participant")
        if s["modality"] == "MIC":
            mic_actors.update(s["participants"])
        # Blind data has provenance, not importance classes or answer labels.
        require(not ({"ground_truth", "semantic_intent", "answer", "is_core", "is_junk", "expected_dimension"} & s.keys()), "Answer annotation leaked into observations")
        m = s.get("measurements", {})
        if "cumulative_steps" in m:
            require(isinstance(m["cumulative_steps"], int) and m["cumulative_steps"] >= previous_steps, "Cumulative steps went backwards")
            previous_steps = m["cumulative_steps"]
        if "heart_rate_bpm" in m:
            require(35 <= m["heart_rate_bpm"] <= 190, "Implausible heart-rate reading")
            require(m["on_wrist"] == (m["measurement_quality"] == "valid"), "Measurement quality/contact contradiction")
        if "sleep_minutes" in m:
            sleep = m
            span = (datetime.fromisoformat(m["sleep_episode_end"]) - datetime.fromisoformat(m["sleep_episode_start"])).total_seconds() / 60
            require(m["sleep_minutes"] + m["awake_minutes"] == span, "Sleep arithmetic inconsistent")
            require(180 <= m["sleep_minutes"] <= 600, "Sleep duration implausible")
        if "account_summary" in s:
            require(audit is None, "Multiple final financial snapshots")
            audit = s["account_summary"]
        if "transaction" in s:
            tx = s["transaction"]
            require(tx["owner_id"] == p["person_id"], "Transaction ownership mismatch")
            require(type(tx["delta_cents"]) is int, "Money must use integer cents")
            deltas.append(tx["delta_cents"])
            loan_principal += tx.get("new_disbursed_principal_cents", 0)
    require(prev == end and {"07:00", "23:30"} <= starts, "Incomplete night/day coverage")
    require(min(channels.values()) >= 20 and len(channels) == 3, "Insufficient modality mix")
    require(all(f"{p['person_id']}:{relation}" in mic_actors for relation in ["peer", "friend", "family", "stranger"]), "Missing family/peer/friend/stranger MIC coverage")
    require(sleep is not None and audit is not None, "Sleep or final financial summary missing")
    require(audit["owner_id"] == p["person_id"], "Account ownership mismatch")
    require(audit["opening_balance_cents"] + sum(deltas) == audit["closing_balance_cents"], "Cash reconciliation failed")
    require(sum(d for d in deltas if d > 0) == audit["posted_credits_cents"], "Posted credit total mismatch")
    require(-sum(d for d in deltas if d < 0) == audit["posted_debits_cents"], "Posted debit total mismatch")
    require(loan_principal == audit["new_disbursed_principal_cents"], "New debt amount mismatch")
    if audit["pending_status"] == "SIGNED_AWAITING_DISBURSEMENT":
        require(loan_principal == 0 and audit["posted_credits_cents"] == 0, "Signed loan incorrectly treated as disbursed")
    referenced = set()
    anchors = 0
    for dimension, block in gt.items():
        require(block["core_summary"].strip(), "Missing core summary")
        require(len(block["acceptable_directional_paraphrases"]) >= 3, "Too few directional paraphrases")
        require(block["red_line_criteria"], "Missing red lines")
        require("不得要求逐字" in block["scoring_policy"], "Literal-match grading must be prohibited")
        local_ids = set()
        for anchor in block["semantic_core_anchors"]:
            require(anchor["anchor_id"] not in local_ids, "Duplicate anchor in dimension")
            local_ids.add(anchor["anchor_id"])
            refs = anchor["evidence_refs"]
            require(refs and len(refs) == len(set(refs)) and set(refs) <= ids, "Missing, duplicated or dangling evidence reference")
            require(anchor["proposition"].strip() and anchor["acceptable_direction_synonyms"], "Anchor lacks proposition or synonyms")
            require(set(anchor["entity_ids"]) <= actors, "Ground truth refers to an unobservable actor")
            require(set(anchor["entity_ids"]) <= {a for ref in refs for a in observations[ref]["participants"]}, "Anchor entity has no linked observation")
            numeric = anchor.get("numeric_anchors", {})
            if "sleep_minutes" in numeric:
                require(numeric == {"sleep_minutes": sleep["sleep_minutes"], "resting_hr_bpm": sleep["resting_hr_bpm"], "final_steps": previous_steps}, "Sleep/steps answer numbers lack support")
            if "displayed_onset_hr_bpm" in numeric:
                onset_m = observations[refs[0]]["measurements"]
                end_m = observations[refs[1]]["measurements"]
                require(numeric == {"displayed_onset_hr_bpm": onset_m["heart_rate_bpm"], "onset_measurement_valid": onset_m["measurement_quality"] == "valid", "recheck_hr_bpm": end_m["heart_rate_bpm"]}, "Health answer numbers or quality lack support")
            if "major_item_cents" in numeric:
                for key in ["opening_balance_cents", "closing_balance_cents", "posted_debits_cents", "posted_credits_cents", "new_disbursed_principal_cents"]:
                    require(numeric[key] == audit[key], "Financial answer number lacks support")
                major = numeric["major_item_cents"]
                amount_text = f"{major // 100}.{major % 100:02d}元"
                require(amount_text in " ".join(observations[r]["text"] for r in refs), "Major amount is absent from linked evidence")
                small_refs = [observations[r]["transaction"] for r in refs if "transaction" in observations[r]][:3]
                require(numeric["daily_small_expenses_cents"] == -sum(t["delta_cents"] for t in small_refs), "Daily expense answer lacks support")
            referenced.update(refs)
            anchors += 1
        for red in block["red_line_criteria"]:
            require(red["severity"] == "ONE_VOTE_VETO" and red["rejected_assertion"], "Red line incomplete")
            require("否定" in red["applies_only_when"], "Veto must not punish quoted or negated propositions")
    require(len(gt["global_daily_summary"]["semantic_core_anchors"]) >= 4, "Global answer lacks a multidimensional storyline")
    require(len(stream) - len(referenced) >= 180, "Not enough mundane daily context")
    # Ensure the global answer is not spoon-fed verbatim inside a 'reflection' slice.
    require(all(gt["global_daily_summary"]["core_summary"] not in s["text"] for s in stream), "Global answer copied into blind input")
    signature = tuple(gt[d]["core_summary"] for d in ["dim:career", "dim:social", "dim:health", "dim:finance"])
    return {"slices": len(stream), "anchors": anchors, "ordinary_slices": len(stream) - len(referenced),
            "channels": channels, "signature": signature, "occupation": p["occupation"], "city": p["city"],
            "finance_status": audit["pending_status"], "urgent": "已赴急诊" in gt["dim:health"]["core_summary"]}


def iter_complete(path):
    """Stream the published standard JSON array (one compact object per line)."""
    with lzma.open(path, "rt", encoding="utf-8") as f:
        require(f.readline().strip() == "[", "Complete bank must be a JSON array")
        ended = False
        saw_last = False
        for line in f:
            stripped = line.strip()
            if stripped == "]":
                require(saw_last, "Empty bank or trailing comma")
                ended = True
                break
            require(not saw_last, "Missing comma between JSON objects")
            saw_last = not stripped.endswith(",")
            yield json.loads(stripped[:-1] if not saw_last else stripped)
        require(ended and not f.read().strip(), "Missing array end or trailing data")


def validate_bank(directory, expected_count=10000):
    directory = Path(directory)
    totals, occupations, cities, channels, finance_statuses = Counter(), Counter(), Counter(), Counter(), Counter()
    people, names, questions, signatures, slice_counts = set(), set(), set(), set(), []
    with lzma.open(directory / "blind_questions.jsonl.xz", "rt", encoding="utf-8") as bf, \
         lzma.open(directory / "directional_ground_truth.jsonl.xz", "rt", encoding="utf-8") as gf:
        for q in iter_complete(directory / "daily_life_10000.json.xz"):
            blind_line, gt_line = bf.readline(), gf.readline()
            require(blind_line and gt_line, "Split artifacts truncated")
            blind, gt = json.loads(blind_line), json.loads(gt_line)
            expected_blind = {k: v for k, v in q.items() if k != "directional_ground_truth"}
            require(blind == expected_blind, "Blind artifact differs from complete input")
            require(gt == {"question_id": q["question_id"], "directional_ground_truth": q["directional_ground_truth"]}, "GT split mismatch")
            p = q["persona"]
            require(q["question_id"] not in questions, "Duplicate question")
            require(p["person_id"] not in people and p["name"] not in names, "Not 10000 distinct people")
            questions.add(q["question_id"])
            people.add(p["person_id"])
            names.add(p["name"])
            stat = validate_question(q)
            signatures.add(stat["signature"])
            slice_counts.append(stat["slices"])
            for key in ["slices", "anchors", "ordinary_slices", "urgent"]:
                totals[key] += stat[key]
            totals["questions"] += 1
            channels.update(stat["channels"])
            occupations[stat["occupation"]] += 1
            cities[stat["city"]] += 1
            finance_statuses[stat["finance_status"]] += 1
        require(not bf.read().strip() and not gf.read().strip(), "Extra rows in split artifacts")
    require(totals["questions"] == expected_count, "Not exactly 10000 questions")
    require(len(occupations) == 12 and len(cities) == 12, "Missing role/city coverage")
    require(len(signatures) >= expected_count * .90, "Excessive identical semantic story combinations")
    return {"verdict": "PASS", "unique_people": len(people), "unique_names": len(names), "totals": dict(totals),
            "unique_semantic_story_combinations": len(signatures),
            "slices_per_day": {"min": min(slice_counts), "max": max(slice_counts), "mean": sum(slice_counts) / len(slice_counts)},
            "occupations": dict(occupations), "cities": dict(cities), "modalities": dict(channels),
            "finance_statuses": dict(finance_statuses), "full_day_seconds_each": 86400,
            "limitations": "Structural, temporal, attribution and accounting audit, not independent LLM semantic grading or proof of real-world generalization."}
