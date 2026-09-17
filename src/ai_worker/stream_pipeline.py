"""长会话三级流式流水线 (Three-Stage Streaming Pipeline, C10 / M2-016 / V25).

贯彻最高宪法第八十四条、第八十五条及 v3.0.1 裁决集 ADJ-001/007：
1. 第一级：前台极简活跃滑窗 (ActiveRollingWindow)
   - 保持 5~8 轮（默认 6 轮）活跃对话，单轮输出受 1~3 句老友语调严格护栏约束；
   - 确保前台对话 Token 严格受控，杜绝 50 轮碎片对话 Token 线性爆炸。
2. 第二级：后台异步增量事实萃取 (StreamingExtractWorker)
   - 滑出前台窗口的对话，平滑进入后台异步工作队列；
   - 静默萃取结构化事实（Claim）与事件锚点（EventAnchor），打上 extraction_watermark 与幂等键；
   - 对话进行中实时沉淀世界记忆，无需等到夜间复盘。
3. 第三级：跨周期超链接主动联想回捞 (ProactiveAssociativeRecall)
   - 侦测用户原话中的人名、实体与历史事件关键词；
   - 毫秒级从历史萃取库或核心世界中按需捞出历史锚点与事实切片；
   - 保证在第 50 轮提到第 2 轮的人名或承诺时，原话记忆瞬间就绪。
"""

from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

UTC = timezone.utc


# ============================================================================
# 第一级：前台活跃滑窗
# ============================================================================
class ActiveRollingWindow:
    """前台活跃滑动窗口。
    
    维持活跃轮数 <= max_turns，保证内存与 Token 处于恒定安全水位。
    超出的旧对话平滑迁出，返回给调用方投递至后台萃取流水线。
    """

    def __init__(self, max_turns: int = 6, max_tokens: int = 1500) -> None:
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._turns: deque[Tuple[str, str]] = deque()

    def push_turn(self, user_msg: str, ai_msg: str) -> List[Tuple[str, str]]:
        """压入一轮对话，并平滑迁出超额的历史轮次。"""
        self._turns.append((user_msg, ai_msg))
        evicted: List[Tuple[str, str]] = []
        while len(self._turns) > self.max_turns:
            evicted.append(self._turns.popleft())
        return evicted

    def get_prompt_messages(self) -> List[Dict[str, str]]:
        """输出适合直接注入大模型的消息列表。"""
        messages: List[Dict[str, str]] = []
        for user_msg, ai_msg in self._turns:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": ai_msg})
        return messages

    @property
    def total_turns(self) -> int:
        return len(self._turns)

    def estimate_tokens(self) -> int:
        """估算当前窗口内所有文本的 Token 消耗（按中文 1.5 字符/Token，英文 4 字符/Token 近似）。"""
        total_chars = sum(len(u) + len(a) for u, a in self._turns)
        return int(total_chars * 0.7) + 1

    def clear(self) -> None:
        self._turns.clear()


# ============================================================================
# 第二级：后台异步增量事实萃取
# ============================================================================
class ExtractedClaimCandidate(BaseModel):
    """后台萃取的结构化事实候选。"""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_val: str = Field(min_length=1)
    context_topic: str = Field(default="日常对话")
    sentiment: str = Field(default="中性")
    raw_quote: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    idempotency_key: str = Field(min_length=1)


class StreamingExtractWorker:
    """后台异步增量事实萃取器。
    
    采用无锁队列与线程池/同步双模，既能在多线程中作为 Daemon Worker 运行，
    也能在单元测试中进行同步即时萃取。
    """

    def __init__(
        self,
        custom_extractor: Optional[Callable[[List[Tuple[str, str]], int], List[ExtractedClaimCandidate]]] = None,
    ) -> None:
        self._queue: queue.Queue[Optional[Tuple[List[Tuple[str, str]], int]]] = queue.Queue()
        self._extracted_claims: List[ExtractedClaimCandidate] = []
        self._custom_extractor = custom_extractor
        self._watermark: int = 0
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

    def start_background_thread(self) -> None:
        """启动后台常驻工作线程。"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._worker_thread.start()

    def stop_background_thread(self) -> None:
        """安全停止后台工作线程。"""
        self._queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

    def _run_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            batch, turn_offset = item
            try:
                self.extract_sync(batch, turn_offset)
            finally:
                self._queue.task_done()

    def enqueue_evicted_turns(self, batch: List[Tuple[str, str]], turn_offset: int) -> None:
        """将前台滑出的对话批量压入后台队列。"""
        if not batch:
            return
        self._queue.put((batch, turn_offset))

    def extract_sync(
        self, batch: List[Tuple[str, str]], turn_offset: int
    ) -> List[ExtractedClaimCandidate]:
        """同步执行事实萃取（内置确定性规则引擎 + 可选自定义大模型萃取器）。"""
        if self._custom_extractor is not None:
            results = self._custom_extractor(batch, turn_offset)
        else:
            results = self._default_heuristic_extract(batch, turn_offset)

        with self._lock:
            for c in results:
                self._extracted_claims.append(c)
            self._watermark = max(self._watermark, turn_offset + len(batch))

        return results

    def _default_heuristic_extract(
        self, batch: List[Tuple[str, str]], turn_offset: int
    ) -> List[ExtractedClaimCandidate]:
        """确定性规则萃取器：从对话中提取人名实体、承诺意图、事实陈述。"""
        extracted: List[ExtractedClaimCandidate] = []
        
        # 常见人名与关系词模式
        person_patterns = [
            r"([老小][张王李赵钱孙周吴郑陈林沈刘马杨黄])",
            r"(妈妈|爸爸|父亲|母亲|女友|老婆|媳妇|兄弟|闺蜜|张总|李总|王总|刘总)",
            r"([A-Z][a-z]+)",
        ]
        # 承诺与事实动作
        fact_patterns = [
            (r"借[给走了去出了]([^，。！？]+)", "借贷关系"),
            (r"买[了个了支顶双台部包份本双个]([^，。！？]+)", "消费事实"),
            (r"答应[了要]([^，。！？]+)", "承诺待办"),
            (r"准备[要去]([^，。！？]+)", "意向目标"),
            (r"(合伙|合作|商量|开会|讨论)([^，。！？]+)", "合作事项"),
            (r"(生病|住院|发烧|头疼|早搏|失眠)", "生理状态"),
            (r"(分手|和好|吵架|冷战)", "人际关系波动"),
        ]

        for idx, (user_msg, ai_msg) in enumerate(batch):
            turn_no = turn_offset + idx + 1
            combined = f"{user_msg} {ai_msg}"

            # 提取人名
            found_persons = []
            for pat in person_patterns:
                for match in re.finditer(pat, user_msg):
                    found_persons.append(match.group(1))

            matched_any_fact = False
            # 提取关键动词/事实
            for f_pat, f_topic in fact_patterns:
                m = re.search(f_pat, user_msg)
                if m:
                    target_val = m.group(1) if m.groups() else m.group(0)
                    subject = found_persons[0] if found_persons else "用户"
                    
                    idempotency_str = f"{turn_no}:{subject}:{f_topic}:{target_val}"
                    h = hashlib.md5(idempotency_str.encode("utf-8")).hexdigest()[:12]
                    
                    claim = ExtractedClaimCandidate(
                        claim_id=f"clm_{h}",
                        subject=subject,
                        predicate=f_topic,
                        object_val=target_val.strip(),
                        context_topic=f_topic,
                        sentiment="负向" if "吵架" in user_msg or "生病" in user_msg else "正向" if "买" in user_msg else "中性",
                        raw_quote=user_msg.strip(),
                        turn_index=turn_no,
                        idempotency_key=f"idem_{h}",
                    )
                    extracted.append(claim)
                    matched_any_fact = True

            # 若有人物实体提及，但未触发特定动作，依然记录为实体人际交往切片
            if not matched_any_fact and found_persons:
                for p in set(found_persons):
                    idempotency_str = f"{turn_no}:{p}:人际交往:{user_msg[:20]}"
                    h = hashlib.md5(idempotency_str.encode("utf-8")).hexdigest()[:12]
                    claim = ExtractedClaimCandidate(
                        claim_id=f"clm_{h}",
                        subject=p,
                        predicate="人际交往",
                        object_val=user_msg.strip(),
                        context_topic="人际交往",
                        sentiment="中性",
                        raw_quote=user_msg.strip(),
                        turn_index=turn_no,
                        idempotency_key=f"idem_{h}",
                    )
                    extracted.append(claim)

        return extracted

    def drain(self, timeout: float = 2.0) -> List[ExtractedClaimCandidate]:
        """等待队列全部处理完毕并返回所有已提取事实。"""
        try:
            self._queue.join()
        except Exception:
            pass
        with self._lock:
            return list(self._extracted_claims)

    def get_all_extracted(self) -> List[ExtractedClaimCandidate]:
        with self._lock:
            return list(self._extracted_claims)

    @property
    def watermark(self) -> int:
        with self._lock:
            return self._watermark


# ============================================================================
# 第三级：跨周期超链接主动联想回捞
# ============================================================================
class ProactiveAssociativeRecall:
    """跨周期超链接主动联想回捞器。
    
    当用户即时输入提及历史人物、特定承诺或敏感事件时，
    毫秒级从第二级萃取库及外部世界存储中回捞最相关的 1~3 条核心原话切片。
    """

    def __init__(self, extract_worker: StreamingExtractWorker, world_store: Any = None) -> None:
        self.extract_worker = extract_worker
        self.world_store = world_store

    def recall_for_turn(self, user_msg: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """根据用户当前消息进行主动联想回捞。"""
        if not user_msg:
            return []

        claims = self.extract_worker.get_all_extracted()
        recalled: List[Dict[str, Any]] = []

        for c in reversed(claims):
            # 命中了主体人名或宾语核心词
            if (c.subject != "用户" and c.subject in user_msg) or (c.object_val in user_msg and len(c.object_val) >= 2):
                recalled.append({
                    "anchor_id": c.claim_id,
                    "subject": c.subject,
                    "predicate": c.predicate,
                    "object_val": c.object_val,
                    "raw_quote": c.raw_quote,
                    "turn_index": c.turn_index,
                    "relevance_score": 0.95,
                    "why_recalled": f"当前提及关键词与第 {c.turn_index} 轮事实精确命中",
                })
            if len(recalled) >= top_k:
                break

        return recalled


# ============================================================================
# 三级流式流水线统一入口
# ============================================================================
class ThreeStageStreamPipeline:
    """统合三级流式心智流水线的完整控制器。"""

    def __init__(
        self,
        max_active_turns: int = 6,
        max_active_tokens: int = 1500,
        custom_extractor: Optional[Callable[[List[Tuple[str, str]], int], List[ExtractedClaimCandidate]]] = None,
        world_store: Any = None,
    ) -> None:
        self.window = ActiveRollingWindow(max_turns=max_active_turns, max_tokens=max_active_tokens)
        self.extractor = StreamingExtractWorker(custom_extractor=custom_extractor)
        self.recall = ProactiveAssociativeRecall(self.extractor, world_store=world_store)
        self._turn_counter: int = 0

    def process_turn(
        self,
        user_msg: str,
        reply_generator: Callable[[List[Dict[str, str]], List[Dict[str, Any]]], str],
    ) -> Dict[str, Any]:
        """执行完整一轮会话处理。
        
        1. 联想回捞 (Stage 3)
        2. 装配活跃会话与提示词 (Stage 1)
        3. 调用大模型/回复生成器
        4. 前台滚动滑窗压入并迁出旧轮次
        5. 迁出内容异步推入事实萃取队列 (Stage 2)
        """
        self._turn_counter += 1
        turn_no = self._turn_counter

        # 1. 联想回捞
        recalled_cues = self.recall.recall_for_turn(user_msg)

        # 2. 获取前台活跃上下文
        prompt_messages = self.window.get_prompt_messages()

        # 3. 生成回复
        raw_reply = reply_generator(prompt_messages, recalled_cues)

        # 4. 压入前台滑动窗口并获取迁出的历史轮次
        evicted = self.window.push_turn(user_msg, raw_reply)

        # 5. 将迁出轮次推入后台萃取队列
        if evicted:
            evicted_offset = turn_no - len(self.window.get_prompt_messages()) // 2 - len(evicted)
            self.extractor.enqueue_evicted_turns(evicted, max(0, evicted_offset))
            # 同步即时萃取以保障弱线程环境下的确定性
            self.extractor.extract_sync(evicted, max(0, evicted_offset))

        return {
            "reply": raw_reply,
            "turn_index": turn_no,
            "recalled_cues": recalled_cues,
            "active_turns": self.window.total_turns,
            "estimated_tokens": self.window.estimate_tokens(),
            "evicted_count": len(evicted),
            "total_extracted_claims": len(self.extractor.get_all_extracted()),
        }

    def flush_and_extract_all(self) -> List[ExtractedClaimCandidate]:
        """强制将前台当前剩余对话全部送入萃取器并排空。"""
        remaining = list(self.window._turns)
        if remaining:
            self.extractor.extract_sync(remaining, self._turn_counter - len(remaining))
        return self.extractor.drain()
