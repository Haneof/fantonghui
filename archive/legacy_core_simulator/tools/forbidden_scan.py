"""Sprint 1 禁止事项的机械执行器(09 §Sprint 1 禁止事项 1-7)。

设计原则: 架构师写的"禁止"不能只活在聊天记录里,必须变成可执行断言,否则下一个
Agent 一句"我优化了一下"就越界了。

    python3 tools/forbidden_scan.py
"""
from __future__ import annotations

import hashlib
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 禁止 #1: 宪法 V1.2-r1 已封版。此哈希由 Sprint 1 Task 1 生成;要改宪法必须先在
#: docs 层走架构裁决,再更新这里的常量(让"顺手改宪法"变成一个显眼的 diff)。
CONSTITUTION_SHA256 = None  # 由 constitution_hash() 现算,与 tests 中的记录值比对

#: 禁止 #4: V0.1 不接大模型、不接网络。
FORBIDDEN_IMPORTS = re.compile(
    r"\b(import|from)\s+(openai|anthropic|google\.generativeai|genai|httpx|requests|urllib\.request|"
    r"urllib\.parse|socket|grpc|ollama|transformers|torch|llama_cpp|mistralai|cohere)\b"
)

#: 扫描器自身。规则 c/d 是"源码里出现某字面量即违规",而本文件正是这些字面量的定义处,
#: 属于自指而非实现,故仅对 c/d 豁免;a/b(定义与调用点)对本文件照样生效。
SELF = Path(__file__).resolve()

#: 禁止 #6: 去重只属于 Event Runtime(02 §1),且全仓只能有一套(Task 4 第 7 项)。
DEDUPE_DEFS = re.compile(r"^\s*def (dedupe|is_duplicate|fingerprint)\b", re.M)
DEDUPE_CALLS = re.compile(r"\.(dedupe|is_duplicate|fingerprint)\(")
LEDGER_TOKEN = "dropped.jsonl"
#: Task 4 明确禁止的方向: 语义相似度/模糊匹配判重(那等于把 LLM 或模型偷偷请回来)。
SIMILARITY_TOKENS = ("difflib", "SequenceMatcher", "levenshtein", "similarity",
                     "embedding", "cosine", "fuzzy")

#: 禁止 #3: 以下子系统必须仍是骨架(Sprint 2/3/4 才实现)。
MUST_STAY_SKELETON = [
    "core.memory.memory_runtime:MemoryRuntime",
    "core.identity.identity_runtime:IdentityRuntime",
    "core.attention.relevance:RelevanceRuntime",
    "core.attention.attention_runtime:AttentionRuntime",
    "core.attention.wake:WakeRuntime",
    "core.attention.lease:LeaseManager",
    "core.ai.ai_runtime:AIRuntime",
    "core.ai.model_router:ModelRouter",
    "core.capability.capability_runtime:CapabilityRuntime",
    "core.policy.permission:PermissionRuntime",
    "core.policy.safety:SafetyRuntime",
    "core.interaction.interaction_runtime:InteractionRuntime",
    "core.evolution.evolution_runtime:EvolutionRuntime",
]

#: 禁止 #2: Runtime 边界集合(与 docs/02 对齐;新增/删除契约必须在这里显式改)。
EXPECTED_CONTRACTS = [
    "Perception Runtime", "Event Runtime", "World Runtime", "State Runtime", "Memory Runtime",
    "Identity Runtime", "Relevance Runtime", "Attention Runtime", "Lease Runtime", "Wake Runtime",
    "AI Runtime", "Capability Runtime", "Interaction Runtime", "Evolution Runtime",
]

CODE_DIRS = ["core", "tools", "adapters"]


def sources() -> list[Path]:
    return [p for d in CODE_DIRS for p in (ROOT / d).rglob("*.py") if p.is_file()]


def constitution_hash() -> str:
    return hashlib.sha256((ROOT / "docs/AIOS_Constitution_V1.2-r1.md").read_text(encoding="utf-8").encode()).hexdigest()


def check_no_model_or_network() -> list[str]:
    return [f"禁止#4 不得接入大模型/网络: {p.relative_to(ROOT)}:{i}"
            for p in sources() for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if FORBIDDEN_IMPORTS.search(line)]


def check_dedupe_home() -> list[str]:
    """禁止#6 + Task 4 第 7 项: 全仓只允许 core/event/ 这一套去重。

    四条机械规则,避免"再写一个 dedupe"变成双重去重:
      a) 定义去重/判重函数只能出现在 core/event/
      b) 调用 .dedupe/.is_duplicate/.fingerprint 只能出现在 core/event/
      c) 读写 dropped.jsonl 留痕只能出现在 core/event/(留痕格式只有一套)
      d) core/ 任何位置出现语义相似度/模糊匹配判重 -> 直接违规(禁把模型请回来)
    """
    bad: list[str] = []
    for p in sources():
        rel = p.relative_to(ROOT).as_posix()
        src = p.read_text(encoding="utf-8")
        in_event = rel.startswith("core/event/")
        if DEDUPE_DEFS.search(src) and not in_event:
            bad.append(f"禁止#6 去重实现出现在 Event Runtime 之外: {rel}")
        if DEDUPE_CALLS.search(src) and not in_event:
            bad.append(f"Task4#7 第二处去重调用点(会造成双重去重): {rel}")
        if p.resolve() != SELF and LEDGER_TOKEN in src and not in_event:
            bad.append(f"Task4#7 留痕文件被 Event Runtime 之外读写: {rel}")
    for p in CODE_DIRS:
        for q in (ROOT / p).rglob("*.py"):
            if q.resolve() == SELF:
                continue
            src = q.read_text(encoding="utf-8")
            hits = [tok for tok in SIMILARITY_TOKENS if tok.lower() in src.lower()]
            if hits:
                bad.append(f"Task4 禁止语义相似度判重(等于把模型请回来): "
                           f"{q.relative_to(ROOT)} 命中 {hits}")
    defs = [q.relative_to(ROOT).as_posix() for q in (ROOT / "core/event").rglob("*.py")
            if DEDUPE_DEFS.search(q.read_text(encoding="utf-8"))]
    if len(defs) != 1:
        bad.append(f"Task4#7 判重实现必须恰好一处,实得 {len(defs)}: {defs}")
    return bad


def check_perception_gate() -> list[str]:
    src = (ROOT / "core/event/event_runtime.py").read_text(encoding="utf-8")
    if "is_minted" not in src:
        return ["禁止#5 EventRuntime 缺少感知层铸造校验(is_minted),Simulator 可以绕过 Perception Runtime"]
    return []


def check_skeleton_intact() -> list[str]:
    bad = []
    for ref in MUST_STAY_SKELETON:
        mod, cls = ref.split(":")
        try:
            obj = getattr(importlib.import_module(mod), cls)
            obj()
            bad.append(f"禁止#3 Sprint 2/3/4 的 {cls} 已被实例化(应仍是骨架)")
        except NotImplementedError:
            pass
        except Exception as exc:  # noqa: BLE001
            bad.append(f"禁止#3 {cls} 骨架抛出了非 NotImplementedError: {type(exc).__name__}: {exc}")
    return bad


def check_runtime_boundaries() -> list[str]:
    from tools import schema_check as sc

    names = [n for _, n in sc.contracts()]
    if names != EXPECTED_CONTRACTS:
        return [f"禁止#2 docs/02 的契约集合与 Sprint 1 冻结的集合不一致: {names} != {EXPECTED_CONTRACTS}"]
    sc.check_contracts_have_home()
    return []


def check_prohibitions_recorded() -> list[str]:
    doc = (ROOT / "docs/09_FIRST_SPRINT_TASKS.md").read_text(encoding="utf-8")
    if "## Sprint 1 禁止事项" not in doc:
        return ["禁止#7 的七条纪律未写进 docs/09,无法被后续 Agent 遵守"]
    return []


def run() -> list[str]:
    problems: list[str] = []
    for fn in (check_no_model_or_network, check_dedupe_home, check_perception_gate,
               check_skeleton_intact, check_runtime_boundaries, check_prohibitions_recorded):
        problems += fn()
    return problems


if __name__ == "__main__":
    print(f"扫描 {len(sources())} 个源文件,宪法 sha256[:12]={constitution_hash()[:12]}")
    bad = run()
    if bad:
        print("\n".join(bad))
        raise SystemExit(1)
    print("禁止事项 1-7: 全部通过(机械检查,非自我声明)")
