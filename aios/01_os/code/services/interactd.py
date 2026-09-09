# -*- coding: utf-8 -*-
"""interactd · 交互系统（M3 · T17 五级介入通道选择，最低打扰优先）
- 订阅：evt.normalized、sys.interact.request
- 通道等级（最低打扰优先，能低不高）：VISUAL(0) < HAPTIC(1) < BONE_CONDUCTION(2) < EXECUTE(3)
  另有 SILENT_WATCH 表示不介入（v0 不产生，保留语义）
- sys.interact.request {req_id, risk_class, priority} 按非对称规则选通道：
  - SAFETY   → HAPTIC（保命至少震动，可跨级）
  - SOCIAL   → priority=="high" ? BONE_CONDUCTION : VISUAL（社交默认静默，不打断谈话）
  - FINANCIAL→ HAPTIC（需用户注意，配合二次确认）
  - 其它     → VISUAL
- 结果：intervention_id=uuid4 → 发布 evt.intervention
  {intervention_id, risk_class, channel, priority, ts} + 回 evt.query.reply.<req_id>
  {intervention_id, channel}
- 对 evt.normalized：v0 仅接收，不处理
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aios_sdk.aios_sdk import AIOSService

# 通道等级（最低打扰优先，能低不高）——契约 tasks/contracts_m3.md §T17
CHANNEL_RANK = {"SILENT_WATCH": -1, "VISUAL": 0, "HAPTIC": 1,
                "BONE_CONDUCTION": 2, "EXECUTE": 3}

svc = AIOSService("interactd", subscribe=["evt.normalized", "sys.interact.request"])


def select_channel(risk_class, priority=""):
    """通道选择核心。返回通道名（字符串）。
    非对称规则（契约 §T17，最低打扰优先）：
      SAFETY   → HAPTIC
      SOCIAL   → priority=="high" ? BONE_CONDUCTION : VISUAL
      FINANCIAL→ HAPTIC
      其它     → VISUAL
    """
    rc = str(risk_class or "")
    if rc == "SAFETY":
        return "HAPTIC"
    if rc == "SOCIAL":
        return "BONE_CONDUCTION" if priority == "high" else "VISUAL"
    if rc == "FINANCIAL":
        return "HAPTIC"
    return "VISUAL"


def on_event(topic, from_svc, msg):
    if topic == "sys.interact.request":
        req_id = str(msg.get("req_id", uuid.uuid4()))
        risk_class = str(msg.get("risk_class", ""))
        priority = str(msg.get("priority", ""))
        channel = select_channel(risk_class, priority)
        intervention_id = str(uuid.uuid4())
        ts = time.time()
        svc.publish("evt.intervention", {
            "intervention_id": intervention_id,
            "risk_class": risk_class,
            "channel": channel,
            "priority": priority,
            "ts": ts,
        })
        svc.publish("evt.query.reply.%s" % req_id, {
            "intervention_id": intervention_id,
            "channel": channel,
        })
        svc.log(f"[介入] req={req_id} risk={risk_class or '(空)'} "
                f"priority={priority or '(空)'} → {channel} id={intervention_id}")
    elif topic == "evt.normalized":
        pass  # v0 仅接收，不处理


svc.on_event = on_event


# ---------------- 内联自测（python interactd.py --selftest） ----------------
def _selftest():
    """直接调用通道选择函数，验证四条分支（契约 tests/test_m3.py 门禁 1）：
      SOCIAL 默认 → VISUAL
      SOCIAL+high → BONE_CONDUCTION
      SAFETY      → HAPTIC
      FINANCIAL   → HAPTIC
    另补：未知/空 risk_class → VISUAL。
    """
    fails = []

    def check(name, got, want):
        ok = (got == want)
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            print("  got =%r" % (got,))
            print("  want=%r" % (want,))
            fails.append(name)

    check("SOCIAL 默认 → VISUAL",
          select_channel("SOCIAL", "low"), "VISUAL")
    check("SOCIAL+high → BONE_CONDUCTION",
          select_channel("SOCIAL", "high"), "BONE_CONDUCTION")
    check("SAFETY → HAPTIC",
          select_channel("SAFETY", "low"), "HAPTIC")
    check("FINANCIAL → HAPTIC",
          select_channel("FINANCIAL", "high"), "HAPTIC")
    check("其它(未知) → VISUAL",
          select_channel("WEATHER", "high"), "VISUAL")
    check("空 risk_class → VISUAL",
          select_channel("", ""), "VISUAL")

    if fails:
        print("SELFTEST FAILED: %s" % fails)
        sys.exit(1)
    print("SELFTEST PASSED (6/6)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        svc.log("服务启动（M3 · T17 交互系统：五级介入通道选择，最低打扰优先）")
        svc.run()
