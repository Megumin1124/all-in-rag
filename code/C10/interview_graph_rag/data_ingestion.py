"""Data ingestion pipeline for interview-prep content."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass
class KnowledgeChunk:
    """Normalized chunk used across retrieval, graph construction, and learning flows."""

    chunk_id: str
    source_path: str
    source_type: str
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    company: str = "通用"
    question: str = ""
    answer: str = ""
    confidence: float = 1.0
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def tokens(self) -> List[str]:
        text = " ".join([self.title, self.content, self.question, self.answer, " ".join(self.tags)])
        return [tok for tok in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if tok]


class DataIngestionPipeline:
    """Load multi-source interview data and normalize it into structured chunks."""

    def __init__(self, data_dir: Path, supported_extensions: Dict[str, str]):
        self.data_dir = Path(data_dir)
        self.supported_extensions = supported_extensions

    def load(self) -> List[KnowledgeChunk]:
        chunks: List[KnowledgeChunk] = []
        for path in sorted(self.data_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.supported_extensions:
                continue
            chunks.extend(self._load_file(path))
        return self._deduplicate(chunks)

    def _load_file(self, path: Path) -> List[KnowledgeChunk]:
        file_type = self.supported_extensions[path.suffix.lower()]
        if file_type in {"markdown", "text"}:
            raw_text = path.read_text(encoding="utf-8")
        elif file_type == "pdf":
            raw_text = f"[PDF占位内容] {path.stem}。可在此接入真实 PDF 解析器。"
        else:
            raw_text = f"[OCR占位内容] {path.stem}。可在此接入 OCR 服务。"

        if path.suffix.lower() == ".json":
            return self._from_json(path, raw_text, file_type)
        return self._from_markdown_like(path, raw_text, file_type)

    def _from_json(self, path: Path, raw_text: str, file_type: str) -> List[KnowledgeChunk]:
        data = json.loads(raw_text)
        chunks: List[KnowledgeChunk] = []
        for item in data:
            chunks.append(self._build_chunk(path, file_type, item))
        return chunks

    def _from_markdown_like(self, path: Path, raw_text: str, file_type: str) -> List[KnowledgeChunk]:
        sections = [section.strip() for section in re.split(r"\n(?=# )", raw_text) if section.strip()]
        chunks: List[KnowledgeChunk] = []
        for index, section in enumerate(sections, start=1):
            title_match = re.search(r"^#\s+(.+)$", section, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else f"{path.stem}-{index}"
            question_match = re.search(r"\*\*问题\*\*[:：]\s*(.+)", section)
            answer_match = re.search(r"\*\*回答\*\*[:：]\s*([\s\S]+?)(?:\n\*\*|$)", section)
            tags_match = re.search(r"\*\*标签\*\*[:：]\s*(.+)", section)
            company_match = re.search(r"\*\*公司\*\*[:：]\s*(.+)", section)
            chunk = self._build_chunk(
                path,
                file_type,
                {
                    "title": title,
                    "content": section,
                    "question": question_match.group(1).strip() if question_match else title,
                    "answer": answer_match.group(1).strip() if answer_match else section,
                    "tags": [tag.strip() for tag in (tags_match.group(1).split(",") if tags_match else []) if tag.strip()],
                    "company": company_match.group(1).strip() if company_match else "通用",
                    "confidence": 0.92 if file_type == "markdown" else 0.75,
                },
            )
            chunks.append(chunk)
        return chunks

    def _build_chunk(self, path: Path, file_type: str, payload: Dict[str, object]) -> KnowledgeChunk:
        content = str(payload.get("content") or payload.get("answer") or "")
        chunk_id = hashlib.md5(f"{path}:{payload.get('title')}:{content}".encode("utf-8")).hexdigest()[:12]
        return KnowledgeChunk(
            chunk_id=chunk_id,
            source_path=str(path.relative_to(self.data_dir.parent.parent)) if path.is_absolute() else str(path),
            source_type=file_type,
            title=str(payload.get("title") or path.stem),
            content=content,
            tags=list(payload.get("tags") or []),
            company=str(payload.get("company") or "通用"),
            question=str(payload.get("question") or payload.get("title") or path.stem),
            answer=str(payload.get("answer") or content),
            confidence=float(payload.get("confidence") or 1.0),
            metadata={
                "source_name": path.name,
                "source_type": file_type,
            },
        )

    def _deduplicate(self, chunks: Sequence[KnowledgeChunk]) -> List[KnowledgeChunk]:
        seen: Dict[str, KnowledgeChunk] = {}
        for chunk in chunks:
            signature = hashlib.md5((chunk.question + chunk.answer).encode("utf-8")).hexdigest()
            existing = seen.get(signature)
            if existing is None or chunk.confidence > existing.confidence:
                seen[signature] = chunk
        return list(seen.values())
