#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从文件/stdin 读取命令原文，输出关联 ID 与可直接粘贴的执行块。

务必用文件或 stdin 传入，不要用命令行参数 —— 参数会被 shell 二次解析，
引号丢失会导致算出的 ID 与浏览器端不一致（本项目已踩过一次）。

用法:
    python emit_cmd.py cmd.txt
    cat cmd.txt | python emit_cmd.py
"""
import hashlib
import io
import re
import sys

BEGIN = "###GPTPC" + "_BEGIN###"
END = "###GPTPC" + "_END###"

# 与油猴脚本 v1.6.1 的 validate() 保持一致
PLACEHOLDER_RE = re.compile(
    r"(这里写命令|你的命令|真实命令|待填写|请输入|占位符|TODO|你的电脑|<command>|\[command\]|\{command\})")
BROKEN_RE = re.compile(r"^(cmd|dir|test|测试|\.\.\.|<|>)$", re.I)
# v1.4.2 的老规则，用来提示向后兼容性
LEGACY_BROKEN_RE = re.compile(r"\\n|\\r|\\t|\.\.\.", re.I)


def main():
    if len(sys.argv) > 1:
        raw = io.open(sys.argv[1], encoding="utf-8").read()
    else:
        raw = sys.stdin.read()
    cmd = raw.rstrip("\r\n")

    problems = []
    if len(cmd) < 3:
        problems.append("命令过短")
    if BROKEN_RE.match(cmd):
        problems.append("疑似占位命令")
    m = PLACEHOLDER_RE.search(cmd)
    if m:
        problems.append("命中占位符关键词: %s" % m.group(0))
    if "\n" in cmd:
        problems.append("含真实换行，桥可能只执行首行")

    legacy = LEGACY_BROKEN_RE.search(cmd)

    cid = hashlib.sha256(cmd.encode("utf-8")).digest()[:4].hex()

    print("id          = %s" % cid)
    print("length      = %d" % len(cmd))
    print("v1.6.1 校验 = %s" % ("通过" if not problems else " / ".join(problems)))
    if legacy:
        print("v1.4.2 兼容 = 会被老版拒绝 (命中 %r)" % legacy.group(0))
    else:
        print("v1.4.2 兼容 = 通过")
    print()
    print(BEGIN)
    print(cmd)
    print(END)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
