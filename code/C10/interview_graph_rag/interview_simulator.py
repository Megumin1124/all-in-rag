"""Interview simulation and follow-up question helpers."""

from __future__ import annotations

from typing import List

from .retrieval import RetrievalHit


class InterviewSimulator:
    """Create interview prompts and follow-up questions from retrieved knowledge."""

    def generate_follow_ups(self, query: str, hits: List[RetrievalHit]) -> List[str]:
        follow_ups: List[str] = []
        for hit in hits[:3]:
            if hit.chunk.tags:
                follow_ups.append(f"如果把 {hit.chunk.tags[0]} 放到真实项目里，你会如何权衡方案？")
            follow_ups.append(f"请你不用背诵定义，结合 {hit.chunk.company} 面试语境解释：{hit.chunk.question}")
        if not follow_ups:
            follow_ups.append(f"请先给出你对问题“{query}”的第一版回答，再补充项目例子。")
        return list(dict.fromkeys(follow_ups))[:5]
