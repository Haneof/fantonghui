# -*- coding: utf-8 -*-
"""千题基准执行器
条件：{model: local_1.5B | gemini} × {noise: 0 | 5 | 15 | 30}
- 干净条件跑全部 1000 题；噪声条件只跑日志依赖题（T1/T2/T3/T5）
- 可断点续跑（results JSONL 按 qid+condition 去重）
- 判分：纯规则（无模型判卷）
"""
import json
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
LLAMA_PORT = os.environ.get("LLAMA_PORT", "8082")
BENCH = os.environ.get("BENCH", os.path.join(ROOT, "run", "bench1k"))
RESULTS = os.environ.get("BENCH_RESULTS", os.path.join(BENCH, "results.jsonl"))
COND_TAG = os.environ.get("COND_TAG", "local")
QUESTIONS = json.load(open(os.path.join(BENCH, "questions.json"), encoding="utf-8"))

# ---------- 条件表 ----------
CONDITIONS = [(COND_TAG, int(x)) for x in os.environ.get("BENCH_NOISE", "0").split(",")]
LOG_DEP = {"T1a", "T1b", "T2", "T3", "T5"}   # 噪声只作用于日志依赖题


def load_results():
    done = set()
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["qid"], r["condition"]))
                except Exception:
                    pass
    return done


_wlock = threading.Lock()


def append_result(r):
    with _wlock:
        with open(RESULTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()


# ---------- 噪声注入（模拟 0.5B 级摘要器的底层错误）----------
def perturb(lines, rate, seed):
    rnd = random.Random(seed)
    out = []
    for ln in lines:
        if rnd.random() < rate:
            kind = rnd.choice(["time", "swap", "num", "num"])
            if kind == "time" and re.search(r"\d{2}:\d{2}", ln):
                m = re.search(r"(\d{2}):(\d{2})", ln)
                hh, mm = int(m.group(1)), int(m.group(2))
                shift = rnd.choice([-15, -9, 9, 15])
                mm = (mm + shift) % 60
                if shift < 0:
                    hh = (hh - 1) % 24
                ln = re.sub(r"\d{2}:\d{2}", f"{hh:02d}:{mm:02d}", ln, count=1)
            elif kind == "swap":
                if "小王" in ln:
                    ln = ln.replace("小王", "小陈")
                elif "小陈" in ln:
                    ln = ln.replace("小陈", "小王")
                elif "¥" in ln:
                    ln = re.sub(r"¥(\d+)", lambda m: f"¥{max(2, int(m.group(1)) + rnd.choice([-9, 9, 13]))}", ln, count=1)
                else:
                    m = re.search(r"(\d{2,3})", ln)
                    if m:
                        v = max(40, int(m.group(1)) + rnd.choice([-10, 10]))
                        ln = ln.replace(m.group(1), str(v), 1)
            elif kind == "num":
                nums = re.findall(r"\d{2,3}", ln)
                if nums:
                    v = int(rnd.choice(nums))
                    ln = ln.replace(str(v), str(max(40, v + rnd.choice([-10, 10]))), 1)
        out.append(ln)
    if rate >= 0.15:
        pool = ["小陈发来消息：周末聚餐吧", "心率 111（静息异常）", "支付 咖啡 ¥88",
                "李经理发来消息：报告重写"]
        for _ in range(max(1, len(lines) // 40)):
            out.insert(rnd.randrange(len(out) + 1), "[幻觉] " + rnd.choice(pool))
    return out


# ---------- 模型调用 ----------
_gem_pool = None


def ask_gemini(system, user):
    global _gem_pool
    if _gem_pool is None:
        from api_pool.gemini_pool import GeminiPool
        _gem_pool = GeminiPool(model="gemini-flash-latest")
    t0 = time.time()
    text = _gem_pool.chat(system, user)
    return text, time.time() - t0


def ask_local(system, user):
    body = json.dumps({"model": "qwen", "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user}]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{LLAMA_PORT}/v1/chat/completions",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=int(os.environ.get("LLAMA_TIMEOUT", "120"))) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"], time.time() - t0


# ---------- 判分 ----------
def extract_nums(text):
    return [int(x) for x in re.findall(r"\d+", text)]


def extract_dates(text):
    return set(re.findall(r"\d{1,2}月\d{1,2}日", text))


def grade(q, answer):
    t = q["truth"]
    chk = q["check"]
    a = answer.strip()
    if chk == "dates":
        want = set(t["dates"])
        got = extract_dates(a)
        return 1.0 if want and want.issubset(got) else (0.5 if want & got else 0.0)
    if chk == "time":
        m = re.search(r"(\d{1,2}):(\d{2})", a)
        if not m:
            return 0.0
        got = int(m.group(1)) * 60 + int(m.group(2))
        hh, mm = t["time"].split(":")
        want = int(hh) * 60 + int(mm)
        return 1.0 if abs(got - want) <= 2 else 0.0
    if chk == "count":
        nums = extract_nums(a)
        return 1.0 if t["count"] in nums else 0.0
    if chk == "money":
        nums = extract_nums(a)
        return 1.0 if (t["total"] in nums and t["count"] in nums) else 0.0
    if chk == "contains":
        return 1.0 if t["promise"][:12] in answer else 0.0
    if chk == "maxnum":
        nums = extract_nums(a)
        return 1.0 if any(abs(x - t["max"]) <= 2 for x in nums) else 0.0
    if chk == "label":
        up = a.upper()
        for v in ("ESCALATE", "LOCAL", "IGNORE"):
            if v in up:
                return 1.0 if v == t["label"] else 0.0
        return 0.0
    return 0.0


SYSTEM = "你是 AIOS 腕上终端的认知引擎。只根据给定记录回答问题，答案要极简（数字/日期/原话），不要解释。"

# ---------- 主流程 ----------
done = load_results()
print(f"已有 {len(done)} 条结果，继续未完成的条件...", flush=True)
total_rows = 0
for model, noise in CONDITIONS:
    cond = f"{model}-n{noise}"
    todo = [q for q in QUESTIONS
            if (noise == 0 or q["type"] in LOG_DEP)
            and (q["qid"], cond) not in done]
    print(f"== 条件 {cond}: 待跑 {len(todo)} 题 ==", flush=True)
    if not todo:
        continue
    ask_fn = ask_local if model.startswith("local") else ask_gemini

    def work(q):
        lines = list(q["ctx"])
        if noise > 0 and lines:
            lines = perturb(lines, noise / 100.0, hash(q["qid"]) & 0xFFFF)
        ctx_text = "\n".join(lines) if lines else "（无附加记录）"
        user = f"记录：\n{ctx_text}\n\n问题：{q['q']}"
        try:
            if model.startswith("local"):
                ans, dt = ask_local(SYSTEM, user)
            else:
                ans, dt = ask_gemini(SYSTEM, user)
            score = grade(q, ans)
            append_result({"qid": q["qid"], "type": q["type"], "condition": cond,
                           "score": score, "latency": round(dt, 2), "answer": ans[:200]})
            return score
        except Exception as e:
            append_result({"qid": q["qid"], "type": q["type"], "condition": cond,
                           "score": 0, "latency": 0, "answer": f"ERROR {e}"})
            return 0

    with ThreadPoolExecutor(max_workers=4 if model.startswith("local") else 4) as ex:
        list(ex.map(work, todo))
    n_done = len(load_results())
    print(f"   条件 {cond} 完成，累计 {n_done} 条", flush=True)

print("全部条件执行完毕", flush=True)
