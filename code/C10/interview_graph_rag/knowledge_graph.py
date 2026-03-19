"""Knowledge-graph construction utilities for interview preparation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .data_ingestion import KnowledgeChunk


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    name: str
    properties: Dict[str, object] = field(default_factory=dict)


class KnowledgeGraphBuilder:
    """Build a lightweight in-memory graph from normalized interview chunks."""

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[Tuple[str, str, str]] = []
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.chunk_lookup: Dict[str, KnowledgeChunk] = {}

    def build(self, chunks: List[KnowledgeChunk]) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.adjacency.clear()
        self.chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}

        for chunk in chunks:
            self._add_node(chunk.chunk_id, "Question", chunk.question, {"company": chunk.company})
            answer_id = f"ans:{chunk.chunk_id}"
            self._add_node(answer_id, "Answer", chunk.title, {"confidence": chunk.confidence})
            self._add_edge(answer_id, chunk.chunk_id, "ANSWERS")

            source_id = f"src:{chunk.source_path}"
            self._add_node(source_id, "Source", chunk.source_path, {"source_type": chunk.source_type})
            self._add_edge(chunk.chunk_id, source_id, "FROM_SOURCE")

            if chunk.company:
                company_id = f"company:{chunk.company}"
                self._add_node(company_id, "Company", chunk.company)
                self._add_edge(chunk.chunk_id, company_id, "ASKED_BY")

            for tag in chunk.tags or self._infer_tags(chunk):
                concept_id = f"concept:{tag}"
                self._add_node(concept_id, "Concept", tag)
                self._add_edge(chunk.chunk_id, concept_id, "ABOUT")
                self._add_edge(answer_id, concept_id, "EXPLAINS")

        self._link_related_concepts(chunks)

    def _infer_tags(self, chunk: KnowledgeChunk) -> List[str]:
        candidates = [token for token in chunk.tokens if len(token) > 1]
        return list(dict.fromkeys(candidates[:5]))

    def _link_related_concepts(self, chunks: List[KnowledgeChunk]) -> None:
        by_company: Dict[str, List[KnowledgeChunk]] = defaultdict(list)
        for chunk in chunks:
            by_company[chunk.company].append(chunk)

        for company, items in by_company.items():
            for i, current in enumerate(items):
                for other in items[i + 1 :]:
                    overlap = set(current.tags).intersection(other.tags)
                    if overlap:
                        self._add_edge(current.chunk_id, other.chunk_id, "RELATED_QUESTION")
                        self._add_edge(other.chunk_id, current.chunk_id, "RELATED_QUESTION")
                    elif company != "通用":
                        self._add_edge(current.chunk_id, other.chunk_id, "SAME_COMPANY")
                        self._add_edge(other.chunk_id, current.chunk_id, "SAME_COMPANY")

    def _add_node(self, node_id: str, node_type: str, name: str, properties: Dict[str, object] | None = None) -> None:
        self.nodes.setdefault(node_id, GraphNode(node_id=node_id, node_type=node_type, name=name, properties=properties or {}))

    def _add_edge(self, source: str, target: str, relation: str) -> None:
        self.edges.append((source, relation, target))
        self.adjacency[source].add(target)
        self.adjacency[target].add(source)

    def expand_from_chunk(self, chunk_id: str, hops: int = 2) -> List[GraphNode]:
        visited = {chunk_id}
        frontier = {chunk_id}
        for _ in range(hops):
            next_frontier = set()
            for node_id in frontier:
                for neighbor in self.adjacency.get(node_id, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return [self.nodes[node_id] for node_id in visited if node_id in self.nodes and node_id != chunk_id]
