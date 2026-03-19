# 面试学习 GraphRAG 系统原型

本节对应 `code/C10`，实现了一个面向求职学生的 Interview Prep GraphRAG 原型系统。

## 能力映射

- 数据接入层：支持 Markdown / 文本，并为 PDF 与 OCR 预留接入点。
- 知识图谱：围绕 `Question / Answer / Concept / Source / Company` 建模。
- 检索系统：融合关键词检索、轻量 TF-IDF 相似度、图谱扩展。
- 问答系统：基于检索结果组装结构化回答。
- 学习系统：支持熟练度打分与复习调度。
- 面试模拟：根据命中题目自动生成追问。

## 运行

```bash
cd code/C10
python main.py
```

## 建议的下一步工程化增强

1. 把 PDF 解析与 OCR 占位逻辑替换成真实解析器。
2. 用 Milvus 替换轻量向量检索实现。
3. 用 Neo4j 替换内存图谱，实现增量更新。
4. 把答案生成接入 LLM，支持多轮模拟面试。
