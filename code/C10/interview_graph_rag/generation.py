"""Answer composition for the interview GraphRAG demo."""

from __future__ import annotations

from typing import List

from .retrieval import RetrievalHit
from .study_tracker import StudyRecord


class AnswerGenerator:
    """Compose grounded answers from retrieval results without requiring an external LLM."""

    def build_answer(self, query: str, hits: List[RetrievalHit], review_records: List[StudyRecord]) -> str:
        if not hits:
            return "没有找到相关题目。建议先导入八股文或面经资料，再尝试提问。"

        lines = [f"问题：{query}", "", "推荐回答结构："]
        for index, hit in enumerate(hits, start=1):
            lines.append(f"{index}. 主题：{hit.chunk.title}")
            lines.append(f"   - 标准问题：{hit.chunk.question}")
            lines.append(f"   - 回答要点：{self._summarize(hit.chunk.answer)}")
            lines.append(f"   - 检索依据：{', '.join(hit.reasons)}")
            if hit.graph_context:
                lines.append(f"   - 图谱关联：{'; '.join(hit.graph_context)}")
        if review_records:
            lines.append("")
            lines.append("待复习知识点：")
            for record in review_records[:5]:
                lines.append(f"- {record.chunk_id}: 熟练度 {record.familiarity}/5，下次复习 {record.next_review_at}")
        return "\n".join(lines)

    def _summarize(self, text: str, limit: int = 120) -> str:
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 3] + "..."
