"""AIOS Core Simulator —— Sprint 1 Task 9: 按时间线播放用户的一天.

主链(01 §5 / 00): Raw Signal -> Perception -> Semantic Event -> Event Runtime
-> World Update -> World Change -> (Sprint 3 才接 Relevance/Attention/Wake)

用法:
    python3 tools/simulator/player.py --scenario adapters/simulator/negotiation_timeline.txt
    python3 tools/simulator/player.py --noise 3        # 注入 3 条重复噪音,验证去重
    python3 tools/simulator/player.py --fresh          # 清空 var/ 重跑

统计口径来自 04 §11 与 08 B: expensive_model_call_count / semantic_event_count <= 1%。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.simulator.mock_adapter import MockSimulatorAdapter  # noqa: E402
from core.event.event_runtime import EventRuntime  # noqa: E402
from core.perception.perception_runtime import PerceptionRuntime, reset_id_space  # noqa: E402
from core.world.entity_runtime import EntityRuntime  # noqa: E402
from core.world.world_runtime import WorldRuntime  # noqa: E402


def run(scenario: Path, var_dir: Path, date: str, noise: int = 0, fresh: bool = False) -> dict:
    if fresh and var_dir.exists():
        shutil.rmtree(var_dir)
    var_dir.mkdir(parents=True, exist_ok=True)
    reset_id_space()

    adapter = MockSimulatorAdapter(scenario)
    raw = adapter.read() + adapter.repeat_last(noise)

    perception = PerceptionRuntime(date=date)
    perception.register_adapter(adapter)
    events = [perception.ingest_signal(sig) for sig in raw]

    store = EventRuntime(var_dir / "events")
    accepted = [e for e in (store.ingest(ev, origin="perception") for ev in events) if e is not None]

    entities = EntityRuntime(var_dir / "world")
    world = WorldRuntime(var_dir / "world", entities)
    #: 计数是跨运行的累计值(resume 从台账恢复),因此"本轮"必须用增量,否则第二次运行
    #: 会把上次的账报成本次的成果。
    before_run = (world.updated, world.no_change, world.stale_skipped, world.replay_skipped,
                  world.rejected, world.attempted)
    changes = [c for c in (world.apply_update(ev) for ev in accepted) if c is not None]
    after_run = (world.updated, world.no_change, world.stale_skipped, world.replay_skipped,
                 world.rejected, world.attempted)
    run_delta = dict(zip(("applied", "no_slot_change", "stale", "replay_skipped", "rejected",
                          "attempted"), (b - a for a, b in zip(before_run, after_run))))

    ledger = world.update_ledger()
    conservation = world.conservation()
    trace_problems = world.verify_traceability({e["id"] for e in store.all_events()})
    conservation_problems = world.verify_conservation() + world.verify_ledger()

    replay = world.replay(store.all_events(), var_dir / "replay")
    replay_changes = replay.all_changes()
    replay_ok = (
        replay.current_state() == world.current_state()
        and [c["change_type"] for c in replay_changes] == [c["change_type"] for c in changes]
        and [(c["before"], c["after"]) for c in replay_changes] == [(c["before"], c["after"]) for c in changes]
    )

    return {
        "raw_signals": len(raw),
        "semantic_event_count": store.stats()["semantic_event_count"],
        "duplicate_dropped": store.stats()["duplicate_dropped"],
        "unknown_kept": perception.unknown,
        "raw_still_held": perception.raw_still_held(),
        "run_delta": run_delta,
        "world_updates": world.updated,
        "world_no_change": world.no_change,
        "world_attempted": world.attempted,
        "world_stale": world.stale_skipped,
        "world_replay_skipped": world.replay_skipped,
        "world_rejected": world.rejected,
        "ledger": ledger,
        "conservation": conservation,
        "trace_problems": trace_problems,
        "conservation_problems": conservation_problems,
        "changes": changes,
        "state": world.current_state(),
        "entities": entities.all_entities(),
        "events": accepted,
        "world": world,
        "store": store,
        "replay_ok": replay_ok,
        # 04 §11 要求的 5 个计数器;Sprint 1 不接模型、不实现 Wake,因此恒为 0
        "expensive_model_call_count": 0,
        "ai_wake_session_count": 0,
        "micro_wake_count": 0,
        "emergency_wake_count": 0,
    }


def report(r: dict, scenario: Path, var_dir: Path) -> None:
    ratio = (r["expensive_model_call_count"] / r["semantic_event_count"] * 100) if r["semantic_event_count"] else 0.0
    print(f"AIOS Core Simulator —— Sprint 1 / Phase 1 (Event + World)")
    print(f"scenario : {scenario.relative_to(ROOT)}")
    print(f"var      : {var_dir.relative_to(ROOT)}")
    print()
    print(f"[1] raw signal                     : {r['raw_signals']}")
    print(f"[2] Semantic Event (perception mint): {r['semantic_event_count']}  (其中未知场景保留 {r['unknown_kept']} 条,未丢弃)")
    print(f"[3] Event Runtime 去重后落库        : {r['semantic_event_count']}  (窗口内重复丢弃 {r['duplicate_dropped']} 条)")
    d = r["run_delta"]
    print(f"[4] Event -> World Update          : 本轮 applied={d['applied']}  "
          f"no_slot_change={d['no_slot_change']}  stale={d['stale']}  "
          f"replay_skipped={d['replay_skipped']}  rejected={d['rejected']}  (attempted={d['attempted']})")
    print(f"      跨运行累计(从 updates.jsonl 恢复)  : applied={r['world_updates']}  "
          f"no_change={r['world_no_change']}  attempted={r['conservation']['attempted']}")
    print(f"[5] World Change Delta              : {len(r['changes'])} 条")
    print(f"[6] World Update 台账             : {r['world_attempted']} 次尝试全部有下落\n"
          f"      applied={r['conservation']['applied']}  no_rule={r['conservation']['no_rule']}  "
          f"no_slot_change={r['conservation']['no_slot_change']}  stale={r['world_stale']}  "
          f"replay_skipped={r['world_replay_skipped']}  rejected={r['world_rejected']}")
    print()
    print("世界变化序列:")
    for c in r["changes"]:
        print(f"  {c['window']['start'][11:16]}  {c['id']}  {c['change_type']:<24} "
              f"slots={sorted(c['after'])} evidence={','.join(c['evidence_events'])}")
    print()
    print("Event -> World Update 台账(每一条尝试的下落):")
    for ln in r["ledger"]:
        slots = ",".join(sorted((ln.get("update") or {}).get("slots", {}))) or "-"
        print(f"  {ln['id']}  {str(ln['event_id']):<9} {str(ln['rule'] or '-'):<22} "
              f"{ln['disposition']:<16} change={ln['change_id'] or '-':<9} slots={slots}")
        if ln.get("note"):
            print(f"        note: {ln['note']}")
    print()
    print(f"可追溯性核对(World Change -> Event): {'全部通过' if not r['trace_problems'] else r['trace_problems']}")
    print(f"守恒/台账自检                        : {'全部通过' if not r['conservation_problems'] else r['conservation_problems']}")
    print()
    print("当前 World State:")
    print("  " + json.dumps(r["state"], ensure_ascii=False, sort_keys=True))
    print()
    print("Entity Store:")
    for e in r["entities"]:
        print(f"  {e['id']:<13} type={e['type']:<7} relationship_ids={e['relationship_ids']}")
    print()
    print("telemetry(04 §11 / 08 B 口径):")
    for k in ("semantic_event_count", "expensive_model_call_count", "ai_wake_session_count",
              "micro_wake_count", "emergency_wake_count", "duplicate_dropped"):
        print(f"  {k:<28}= {r[k]}")
    print(f"  {'ratio(expensive/semantic)':<28}= {ratio:.2f}%  (验收上限 1%)")
    print(f"  {'raw_still_held(隐私)':<28}= {r['raw_still_held']}  (必须为 0)")
    print()
    print(f"回放一致性(08 A): {'一致' if r['replay_ok'] else '不一致 ✗'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AIOS Core Simulator 时间线播放器")
    ap.add_argument("--scenario", default=str(ROOT / "adapters/simulator/negotiation_timeline.txt"))
    ap.add_argument("--var", default=str(ROOT / "var/run"))
    ap.add_argument("--date", default="2026-09-09")
    ap.add_argument("--noise", type=int, default=0, help="追加 N 条与最后一条相同的噪音,验证去重")
    ap.add_argument("--fresh", action="store_true", help="运行前清空 var 目录")
    a = ap.parse_args(argv)
    scenario, var_dir = Path(a.scenario), Path(a.var)
    report(run(scenario, var_dir, a.date, noise=a.noise, fresh=a.fresh), scenario, var_dir)
    return 0 if var_dir.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
