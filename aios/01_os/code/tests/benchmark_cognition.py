# -*- coding: utf-8 -*-
"""认知能力基准测试：用人生树真实数据考小模型
任务：J1 小时摘要 / J2 日报 / J3 人物理解 / J4 承诺检测 / J5 主动关怀决策
用法：python tests/benchmark_cognition.py --port 8081 --tag 0.5B [--gemini]
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
DB = os.path.join(ROOT, "run", "life_tree.db")


def q(sql, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def chat(port, model, system, user, timeout=120):
    body = json.dumps({"model": model, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user}]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = time.time() - t0
    text = data["choices"][0]["message"]["content"]
    return text, dt


def gemini_chat(system, user):
    from api_pool.gemini_pool import GeminiPool
    pool = GeminiPool(model="gemini-flash-latest")
    t0 = time.time()
    text = pool.chat(system, user)
    return text, time.time() - t0


def load_tasks():
    tasks = {}
    # J1 小时摘要：取事件最多的小时的原始事件
    (bucket, cnt) = q("SELECT (CAST(timestamp_s AS INT)/3600)*3600 AS h, COUNT(*) c "
                      "FROM raw_log GROUP BY h ORDER BY c DESC LIMIT 1")[0]
    rows = q("SELECT timestamp_s, type, content FROM raw_log "
             "WHERE timestamp_s >= ? AND timestamp_s < ? ORDER BY timestamp_s", (bucket, bucket + 3600))
    rows = rows[:40]                                   # 超出部分截断，避免超出小模型上下文
    lines = [f"{time.strftime('%H:%M:%S', time.localtime(r[0]))} [{r[1]}] {r[2]}" for r in rows]
    tasks["J1 小时摘要"] = (
        "你是腕上 AI 的时间轴摘要引擎。把这一小时的事件流压缩成 3 句以内的中文摘要，"
        "保留关键人物和异常点。\n事件流：\n" + "\n".join(lines),
        f"输入 {len(rows)} 条事件")
    # J3 人物理解：张总相关（最近 30 条）
    rows = q("SELECT timestamp_s, type, content FROM raw_log "
             "WHERE content LIKE '%张总%' ORDER BY timestamp_s DESC LIMIT 30")
    lines = [f"{time.strftime('%m-%d %H:%M', time.localtime(r[0]))} [{r[1]}] {r[2]}" for r in rows]
    tasks["J3 人物理解"] = (
        "你是腕上 AI 的关系认知引擎。根据这些事件回答：张总是谁？和用户是什么关系？"
        "最近的互动动态如何？有没有需要注意的风险？3-4 句话。\n事件：\n" + "\n".join(reversed(lines)),
        f"张总相关 {len(rows)} 条")
    # J4 承诺检测
    rows = q("SELECT timestamp_s, type, content FROM raw_log "
             "WHERE content LIKE '%答应%' OR content LIKE '%承诺%' OR content LIKE '%保证%' "
             "OR content LIKE '%明天给你%' OR content LIKE '%月底%' ORDER BY timestamp_s LIMIT 20")
    lines = [f"{time.strftime('%m-%d %H:%M', time.localtime(r[0]))} {r[2]}" for r in rows]
    tasks["J4 承诺检测"] = (
        "你是腕上 AI 的承诺追踪引擎。从下列事件中找出用户许下的承诺，标注哪条看起来还没完成。\n"
        "事件：\n" + "\n".join(lines),
        f"候选 {len(rows)} 条")
    # J5 主动关怀（宪法场景：犒劳大餐 + 异常心率的日子）
    rows = q("SELECT timestamp_s, type, content FROM raw_log "
             "WHERE type IN ('payment','vital','speech') AND (content LIKE '%火锅%' OR content LIKE '%216%' "
             "OR content LIKE '%110%' OR content LIKE '%西餐%') ORDER BY timestamp_s LIMIT 15")
    lines = [f"{time.strftime('%m-%d %H:%M', time.localtime(r[0]))} [{r[1]}] {r[2]}" for r in rows]
    tasks["J5 主动关怀决策"] = (
        "现在是晚上 21:30，用户在家。你是腕上 AI 的关怀引擎。根据最近这些信号，"
        "判断今晚该不该主动开口关心用户；如果该，给出具体要说的一句话（要自然、不说教、不提数据）。\n"
        "最近信号：\n" + "\n".join(lines),
        f"信号 {len(rows)} 条")
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--tag", default="0.5B")
    ap.add_argument("--gemini", action="store_true")
    args = ap.parse_args()

    tasks = load_tasks()
    out = {"tag": args.tag, "results": []}
    print(f"===== 认知基准 · {args.tag} (port {args.port}) =====", flush=True)
    for name, (prompt, note) in tasks.items():
        system = "你是 AIOS 腕上终端的认知引擎，中文回答，简洁准确。"
        try:
            if args.gemini:
                text, dt = gemini_chat(system, prompt)
            else:
                text, dt = chat(args.port, "qwen", system, prompt)
            print(f"--- {name}（{note} · {dt:.1f}s）---", flush=True)
            print(text[:600], flush=True)
            out["results"].append({"task": name, "latency_s": round(dt, 1), "answer": text})
        except Exception as e:
            print(f"--- {name} 失败: {e}", flush=True)
            out["results"].append({"task": name, "error": str(e)})
    out_path = os.path.join(ROOT, "run", f"benchmark_{args.tag}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"已保存: {out_path}", flush=True)


if __name__ == "__main__":
    main()
