#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算出某条命令在 arena-pc-bridge v1.6.0 里的关联 ID (SHA-256 前 4 字节)。
用法: python cmd_id.py "命令原文"   或   cat cmd.txt | python cmd_id.py
"""
import hashlib, sys

text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
print(hashlib.sha256(text.encode("utf-8")).digest()[:4].hex())
