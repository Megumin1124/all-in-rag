"""Hybrid + graph retrieval for interview learning content."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

from .data_ingestion import KnowledgeChunk
from .knowledge_graph import KnowledgeGraphBuilder


@dataclass
class RetrievalHit:
    chunk: KnowledgeChunk
    score: float
    reasons: List[str]
    graph_context: List[str]


class HybridGraphRetriever:
    """Combine keyword overlap, dense-style token similarity, and graph expansion."""

    def __init__(self, top_k_dense: int = 5, top_k_keyword: int = 5, top_k_final: int = 6, graph_hops: int = 2):
        self.top_k_dense = top_k_dense
        self.top_k_keyword = top_k_keyword
        self.top_k_final = top_k_final
        self.graph_hops = graph_hops
        self.chunks: List[KnowledgeChunk] = []
        self.graph: KnowledgeGraphBuilder | None = None
        self.doc_freq: Dict[str, int] = {}

    def initialize(self, chunks: List[KnowledgeChunk], graph: KnowledgeGraphBuilder) -> None:
        self.chunks = chunks
        self.graph = graph
        self.doc_freq = Counter(token for chunk in chunks for token in set(chunk.tokens))

    def search(self, query: str) -> List[RetrievalHit]:
        query_tokens = [token for token in query.lower().split() if token] or list(query)
        keyword_scores = self._keyword_scores(query_tokens)
        dense_scores = self._dense_scores(query_tokens)

        combined: Dict[str, float] = Counter()
        reasons: Dict[str, List[str]] = {chunk.chunk_id: [] for chunk in self.chunks}
        for chunk_id, score in keyword_scores[: self.top_k_keyword]:
            combined[chunk_id] += score * 0.55
            reasons[chunk_id].append("关键词命中")
        for chunk_id, score in dense_scores[: self.top_k_dense]:
            combined[chunk_id] += score * 0.45
            reasons[chunk_id].append("语义相似")

        ranked = combined.most_common(self.top_k_final)
        hits: List[RetrievalHit] = []
        for chunk_id, score in ranked:
            chunk = next(item for item in self.chunks if item.chunk_id == chunk_id)
            graph_nodes = self.graph.expand_from_chunk(chunk_id, hops=self.graph_hops) if self.graph else []
            graph_context = [f"{node.node_type}:{node.name}" for node in graph_nodes[:6]]
            if graph_context:
                reasons[chunk_id].append("图谱扩展")
            hits.append(RetrievalHit(chunk=chunk, score=round(score, 4), reasons=reasons[chunk_id], graph_context=graph_context))
        return hits

    def _keyword_scores(self, query_tokens: List[str]) -> List[tuple[str, float]]:
        scores = []
        query_set = set(query_tokens)
        for chunk in self.chunks:
            overlap = query_set.intersection(chunk.tokens)
            score = len(overlap) / max(len(query_set), 1)
            if score:
                scores.append((chunk.chunk_id, score))
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def _dense_scores(self, query_tokens: List[str]) -> List[tuple[str, float]]:
        query_counter = Counter(query_tokens)
        scores = []
        for chunk in self.chunks:
            doc_counter = Counter(chunk.tokens)
            score = self._cosine_tfidf(query_counter, doc_counter)
            if score:
                scores.append((chunk.chunk_id, score))
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def _cosine_tfidf(self, q: Counter, d: Counter) -> float:
        terms = set(q) | set(d)
        numerator = 0.0
        q_norm = 0.0
        d_norm = 0.0
        total_docs = max(len(self.chunks), 1)
        for term in terms:
            idf = math.log((1 + total_docs) / (1 + self.doc_freq.get(term, 0))) + 1
            q_weight = q.get(term, 0) * idf
            d_weight = d.get(term, 0) * idf
            numerator += q_weight * d_weight
            q_norm += q_weight ** 2
            d_norm += d_weight ** 2
        denominator = math.sqrt(q_norm) * math.sqrt(d_norm)
        return numerator / denominator if denominator else 0.0
