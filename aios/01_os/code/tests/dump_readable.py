# -*- coding: utf-8 -*-
"""把考卷导出为可读文本（每批 50 题一个文件，供大模型本人作答）"""
import json
import os
import sys

SRC = r"C:\Users\Administrator\.openclaw-autoclaw\workspace\aios\01_os\code\run\bench1k"
batch = sys.argv[1] if len(sys.argv) > 1 else "b1"
start = {"b1": 0, "b2": 250, "b3": 500, "b4": 750}[batch]
end = start + 250
Q = json.load(open(os.path.join(SRC, f"blind_{batch}.json"), encoding="utf-8"))
out = os.path.join(SRC, f"blind_{batch}_readable.txt")
with open(out, "w", encoding="utf-8") as f:
    for q in Q[:250]:
        f.write(f"### {q['qid']} [{q['type']}]\n")
        f.write(f"问题: {q['q']}\n")
        for ln in q["ctx"][:40]:
            f.write(f"  {ln}\n")
        if len(q["ctx"]) > 40:
            f.write(f"  ...(ctx 共 {len(q['ctx'])} 行，后 {len(q['ctx'])-40} 行略)\n")
        f.write("\n")
print(f"导出完成: {out}")
