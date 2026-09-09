# -*- coding: utf-8 -*-
"""触发门控基准：本地 1.5B 能不能正确判断 忽略/本地处理/升级大模型
（用户裁定的问题：本地模型必须知道什么事应该叫大模型、什么事需要忽略）
"""
import json
import time
import urllib.request

PORT = 8082   # 1.5B 实例

CASES = [
    # (情境, 期望判定, 说明)
    ("心率 72，用户在工位坐着", "IGNORE", "正常体征，纯噪音"),
    ("静息状态下心率 110 持续 5 分钟", "ESCALATE", "健康异常，必须叫大模型+安全层"),
    ("小王发来消息：明天能见面吗？", "LOCAL", "社交轻提醒，本地能处理"),
    ("张总发来消息：交付时间表发我，今天要", "ESCALATE", "重要客户+时限压力，关系与工作风险"),
    ("用户在地铁上，心率 88", "IGNORE", "通勤正常状态"),
    ("用户深夜 23:40 支付 夜宵外卖 ¥45（连续第 4 天）", "ESCALATE", "行为模式异常（宪法情绪性进食场景），值得云端分析"),
    ("用户连续第 3 天对家人说'我在忙'（实际在刷手机）", "ESCALATE", "自我矛盾行为+家庭关系信号，大模型值得介入"),
    ("电梯里听到同事谈论天气", "IGNORE", "无关噪音"),
    ("用户对张总说：这个版本明天给你方案（今天已是周四）", "ESCALATE", "承诺产生+时间紧，云端应追踪"),
    ("运动中瞬时心率 142", "IGNORE", "运动心率正常范围"),
    ("银行短信：账户支出 ¥15,000", "ESCALATE", "大额消费，金融类必须二次确认+大模型分析"),
    ("用户说：今天真没意思", "LOCAL", "情绪轻信号，本地关怀+留档，尚不需大模型"),
]

SYSTEM = """你是 AIOS 腕上终端的注意力门控引擎（常驻本地小模型）。
你的唯一职责：对每条事件做出三选一的判定——
- IGNORE：噪音或完全正常的状态，只留档，绝不打扰上层
- LOCAL：本地能处理的小事（轻提醒/留档/简单响应），不值得动用云端
- ESCALATE：值得唤醒云端大模型深入分析的事件（健康异常/重要关系变化/承诺/情绪信号/大额消费）
判定要考虑：与用户的相关度、异常程度、错过它的代价、以及"云端大模型时间宝贵"。
只输出 JSON：{"verdict": "IGNORE|LOCAL|ESCALATE", "reason": "≤15字"}"""

def ask(user):
    body = json.dumps({"model": "qwen", "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user}]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"], time.time() - t0

def main():
    print("===== 门控基准 · 本地 1.5B（12 情境）=====", flush=True)
    right = 0
    rows = []
    for text, expect, why in CASES:
        try:
            raw, dt = ask(text)
            verdict = "?"
            for v in ("IGNORE", "LOCAL", "ESCALATE"):
                if v in raw.upper():
                    verdict = v
                    break
            ok = verdict == expect
            right += ok
            rows.append((text[:22], expect, verdict, round(dt, 1), ok, raw[:80]))
            print(f"[{'对' if ok else '错'}] {text[:24]}… → {verdict}（期望 {expect}）{dt:.1f}s", flush=True)
        except Exception as e:
            rows.append((text[:22], expect, "ERROR", 0, False, str(e)[:80]))
            print(f"[错] {text[:24]}… → 异常 {e}", flush=True)
    print("=" * 50)
    print(f"门控准确率: {right}/{len(CASES)}")
    json.dump([{"situation": r[0], "expect": r[1], "got": r[2], "latency": r[3],
                "ok": r[4], "raw": r[5]} for r in rows],
              open("run/gate_benchmark_1.5B.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("已存 run/gate_benchmark_1.5B.json")


if __name__ == "__main__":
    main()
