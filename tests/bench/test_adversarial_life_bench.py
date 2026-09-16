"""对抗生命数据发生器（Massive Synthetic Life Bench）的独立真值自检。

发生器本身就是被测对象的一部分：如果它吐不出百万级、吐不出对抗性、
或者"证据/噪声"边界含混，后面八阶段的断言就全无意义。因此这里单独钉住
发生器的五条硬性质（规模 / 五条人生线 / 真值边界 / 确定性可复现 / 独立于被测代码）。
"""

from __future__ import annotations

from datetime import timezone

from aios_core.bench.adversarial_life_bench import (
    FULL_PROFILE,
    GATE_PROFILE,
    KIND_AUDIO,
    KIND_CHAT,
    KIND_GPS,
    KIND_HR,
    KIND_IMAGE,
    KIND_IMU,
    KIND_SMS,
    ROLE_EVIDENCE,
    ROLE_NOISE,
    MassiveSyntheticLifeBench,
)

UTC = timezone.utc


def _collect(profile) -> dict:
    bench = MassiveSyntheticLifeBench(profile, seed=20260916)
    raw = 0
    kinds: set[str] = set()
    stories: set[str] = set()
    noise_texts: set[str] = set()
    evidence_texts: set[str] = set()
    for sample in bench.iter_samples():
        raw += 1
        if sample.kind == "imu_burst":
            raw += len(sample.payload.get("samples", ())) - 1
        kinds.add(sample.kind)
        if sample.story:
            stories.add(sample.story)
        text = sample.payload.get("text") or sample.payload.get("transcript")
        if isinstance(text, str) and text:
            if sample.role == ROLE_NOISE:
                noise_texts.add(text)
            elif sample.role == ROLE_EVIDENCE:
                evidence_texts.add(text)
    return {
        "raw": raw,
        "kinds": kinds,
        "stories": stories,
        "noise_texts": noise_texts,
        "evidence_texts": evidence_texts,
        "beats": tuple(bench.beats),
        "evidence_keys": tuple(bench.evidence_keys()),
    }


def test_gate_profile_is_million_scale_and_multimodal() -> None:
    data = _collect(GATE_PROFILE)
    assert data["raw"] > 1_000_000, f"GATE 档位必须过百万，实际 {data['raw']}"
    expected_kinds = {KIND_IMU, KIND_HR, KIND_AUDIO, KIND_IMAGE, KIND_CHAT, KIND_GPS, KIND_SMS}
    assert expected_kinds <= data["kinds"], (
        f"必须覆盖波形/心率/音频/图像/对话/轨迹/短信多种模态，实际 {sorted(data['kinds'])}"
    )
    assert len(data["kinds"]) >= 7, f"模态必须齐备，实际 {sorted(data['kinds'])}"
    assert data["stories"] == {"WANG", "OVERTIME", "FAMILY", "MOVE", "CHRONIC"}, (
        f"五条复杂人生切片必须齐全，实际 {sorted(data['stories'])}"
    )


def test_full_profile_is_three_million_scale() -> None:
    assert FULL_PROFILE.nominal_sample_total > 3_000_000, (
        f"离线全量档位必须超过三百万，实际 {FULL_PROFILE.nominal_sample_total}"
    )
    assert FULL_PROFILE.nominal_sample_total > GATE_PROFILE.nominal_sample_total, (
        "全量档位必须严格大于门禁档位"
    )


def test_ground_truth_boundary_between_evidence_and_noise() -> None:
    data = _collect(GATE_PROFILE)
    assert data["noise_texts"], "必须存在真实噪声真值"
    assert data["evidence_texts"], "必须存在真实证据真值"
    overlap = data["noise_texts"] & data["evidence_texts"]
    assert overlap == set(), f"证据与噪声真值不得交叉污染（交集 {len(overlap)} 条）"
    assert len(data["beats"]) >= 20, f"证据节拍至少 20 条，实际 {len(data['beats'])}"
    assert len(data["evidence_keys"]) == len(data["beats"]), "每条节拍必须有唯一 key"


def test_evidence_beats_are_long_horizon_life_facts() -> None:
    data = _collect(GATE_PROFILE)
    days = sorted(beat.day for beat in data["beats"])
    assert days[0] < 60 and days[-1] > 900, (
        f"节拍必须横跨三年长周期生活（{days[0]}..{days[-1]}）"
    )
    assert len(days) == len(set(days)) or len(set(days)) > 10, (
        f"节拍应分散在多个日期，实际落在 {len(set(days))} 天"
    )
    channels = {beat.channel for beat in data["beats"]}
    assert {"audio_utterance", "chat_message", "sms"} <= channels, (
        f"证据必须覆盖语音/对话/短信多通道，实际 {sorted(channels)}"
    )
    speakers = {beat.speaker_token for beat in data["beats"] if beat.speaker_token}
    assert speakers, "语音类证据必须绑定声纹说话人标识"
    texts = [beat.text for beat in data["beats"]]
    assert len(set(texts)) == len(texts), "证据节拍文本必须唯一，避免真值含混"


def test_generator_is_deterministic_for_a_fixed_seed() -> None:
    first = MassiveSyntheticLifeBench(GATE_PROFILE, seed=7)
    second = MassiveSyntheticLifeBench(GATE_PROFILE, seed=7)
    first_beats = tuple((beat.key, beat.text, beat.day) for beat in first.beats)
    second_beats = tuple((beat.key, beat.text, beat.day) for beat in second.beats)
    assert first_beats == second_beats, "同一 seed 的证据节拍必须逐字可复现"
    first_sample = next(first.iter_samples())
    second_sample = next(second.iter_samples())
    assert first_sample.payload == second_sample.payload, "同一 seed 的样本必须逐字可复现"


def test_generator_does_not_import_the_system_under_test() -> None:
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    source = (root / "src" / "aios_core" / "bench" / "adversarial_life_bench.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "from aios_core.bench.blind_bench_harness",
        "from aios_core.bench.blind_bench_cognition",
        "from aios_core.bench.blind_bench_dialogue",
        "from aios_core.ingest",
        "from aios_core.storage",
        "from aios_core.tools",
        "from aios_core.query",
        "from aios_core.world",
    )
    hits = [token for token in forbidden if token in source]
    assert hits == [], f"真值发生器不得依赖被测实现（命中 {hits}）"
