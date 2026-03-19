"""Interview Prep GraphRAG system entrypoint."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List

from config import DEFAULT_CONFIG, InterviewGraphRAGConfig
from interview_graph_rag import (
    AnswerGenerator,
    DataIngestionPipeline,
    HybridGraphRetriever,
    InterviewSimulator,
    KnowledgeGraphBuilder,
    StudyTracker,
)


class InterviewPrepGraphRAGSystem:
    """End-to-end demo system for interview preparation based on the task specification."""

    def __init__(self, config: InterviewGraphRAGConfig | None = None):
        self.config = config or DEFAULT_CONFIG
        self.pipeline = DataIngestionPipeline(self.config.data_dir, self.config.supported_extensions)
        self.graph_builder = KnowledgeGraphBuilder()
        self.retriever = HybridGraphRetriever(
            top_k_dense=self.config.top_k_dense,
            top_k_keyword=self.config.top_k_keyword,
            top_k_final=self.config.top_k_final,
            graph_hops=self.config.graph_hops,
        )
        self.study_tracker = StudyTracker(self.config.progress_store, self.config.review_interval_days)
        self.interview_simulator = InterviewSimulator()
        self.answer_generator = AnswerGenerator()
        self.chunks = []

    def initialize(self) -> None:
        self.chunks = self.pipeline.load()
        self.graph_builder.build(self.chunks)
        self.retriever.initialize(self.chunks, self.graph_builder)

    def stats(self) -> Dict[str, object]:
        concepts = len([node for node in self.graph_builder.nodes.values() if node.node_type == "Concept"])
        companies = sorted({chunk.company for chunk in self.chunks})
        source_types: Dict[str, int] = {}
        for chunk in self.chunks:
            source_types[chunk.source_type] = source_types.get(chunk.source_type, 0) + 1
        return {
            "chunks": len(self.chunks),
            "graph_nodes": len(self.graph_builder.nodes),
            "graph_edges": len(self.graph_builder.edges),
            "concepts": concepts,
            "companies": companies,
            "source_types": source_types,
            "config": asdict(self.config),
        }

    def ask(self, query: str) -> Dict[str, object]:
        hits = self.retriever.search(query)
        due = self.study_tracker.due_reviews()
        answer = self.answer_generator.build_answer(query, hits, due)
        follow_ups = self.interview_simulator.generate_follow_ups(query, hits)
        return {
            "answer": answer,
            "follow_ups": follow_ups,
            "hits": hits,
        }

    def update_progress(self, chunk_id: str, familiarity: int) -> Dict[str, object]:
        record = self.study_tracker.update_mastery(chunk_id, familiarity)
        return asdict(record)


if __name__ == "__main__":
    system = InterviewPrepGraphRAGSystem()
    system.initialize()
    print("=== Interview Prep GraphRAG System ===")
    print(system.stats())
    result = system.ask("如何回答 Redis 为什么快？")
    print(result["answer"])
    print("\n追问建议：")
    for item in result["follow_ups"]:
        print(f"- {item}")
