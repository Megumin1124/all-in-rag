# C10 Interview Prep GraphRAG System

这个示例项目基于 `task.md` 的需求，并参考了 `code/C9` 的模块化组织方式，提供一个**面向求职学生的 Interview Prep GraphRAG 原型**。

## 已覆盖能力

- 多来源数据接入：Markdown / 文本 / PDF占位 / 图片OCR占位。
- 八股文知识标准化：统一抽取为 `KnowledgeChunk`。
- 图谱建模：`Question / Answer / Concept / Source / Company` 节点与关系。
- Hybrid + GraphRAG 检索：关键词、轻量 TF-IDF、图谱扩展融合。
- 学习系统：熟练度记录（0-5）与基于遗忘曲线的复习调度。
- 面试模拟：自动生成追问问题。
- 数据质量：基于问答签名与置信度去重。

## 目录结构

```text
code/C10/
├── config.py
├── main.py
├── README.md
└── interview_graph_rag/
    ├── __init__.py
    ├── data_ingestion.py
    ├── generation.py
    ├── interview_simulator.py
    ├── knowledge_graph.py
    ├── retrieval.py
    └── study_tracker.py
```

## 运行方式

```bash
cd code/C10
python main.py
```

## 后续可扩展点

- 将 `data_ingestion.py` 的 PDF / OCR 占位逻辑接入真实解析器。
- 将 `KnowledgeGraphBuilder` 替换为 Neo4j 写入与增量更新逻辑。
- 将 `HybridGraphRetriever` 接入 Embedding 模型与 Milvus。
- 将 `AnswerGenerator` 接入 LLM，支持多轮面试模拟。
