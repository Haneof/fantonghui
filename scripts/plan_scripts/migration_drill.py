"""B1 生产库迁移彩排（POST_GATE_48H §1）——只读生产、必在副本上跑。

用法: python scripts/plan_scripts/migration_drill.py --db copy_of_world.db [--expect-backfill N]
"""
import argparse, json, shutil, sqlite3, tempfile
from pathlib import Path
from aios_core.storage import SQLiteWorldStore

ap = argparse.ArgumentParser()
ap.add_argument("--db", type=Path, required=True)
ap.add_argument("--expect-backfill", type=int)
a = ap.parse_args()
work = Path(tempfile.mkdtemp()) / "drill.db"
shutil.copy2(a.db, work)  # 生产库只读；彩排的一切写动作发生在副本
before = sqlite3.connect(work).execute("PRAGMA table_info(world_commits)").fetchall()
has_col = any(r[1] == "source_class" for r in before)
store = SQLiteWorldStore(work)  # 打开即触发 _ensure_source_class_schema
audit = None
if not has_col:
    row = sqlite3.connect(work).execute(
        "SELECT value FROM world_meta WHERE key='schema_migration_m0_023'").fetchone()
    audit = json.loads(row[0]) if row else None
    if audit and a.expect_backfill is not None:
        assert audit["backfilled_rows"] == a.expect_backfill, \
            f"审计行数 {audit['backfilled_rows']} ≠ 预期 {a.expect_backfill}：生产库与彩排假设不符"
    assert audit is not None or before, "旧库应有迁移审计；无审计=迁移未发生，异常"
revs = store.current_world_revision()
assert store.current_world_revision() == revs, "彩排本身改写了修订号=严重异常"
trig = store.triggerable_commits_after(0, limit=max(revs, 1))
print(json.dumps({"pre_migrated": has_col, "audit": audit, "revisions": revs,
                  "triggerable_visible": len(trig),
                  "maintenance_invisible": all(r["source_class"] != "maintenance" for r in trig)},
                 ensure_ascii=False))
