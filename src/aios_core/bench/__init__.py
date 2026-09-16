"""Bench - G-M1P 规模冒烟 Gate 套件（设计书 R4 §3.4-T2-H：三点位 p95 一致）。

治理：正式 50 万修订压测在 M1 Gate 开启后跑目标硬件；CI 以 `--revisions`
降规模保持脚本常热（tests/integration/test_g_m1p_smoke.py）。本包只读消费
store/index 公开面，不触任何运行路径。
"""
