# C9 图 RAG 烹饪助手实现说明

本文档基于 `code/C9` 目录中的实际代码整理，目标是把这一套系统的**完整工作机制、模块分工、函数位置、执行顺序、实现细节**讲清楚。你可以把它理解成这个项目的“架构说明 + 开发者导读 + 数据流说明”。

---

## 1. 整体目标

这个 C9 系统实现的是一套面向菜谱知识的 Graph RAG（Graph Retrieval-Augmented Generation）方案，核心目标有两层：

1. **离线阶段**：把 Markdown 菜谱解析成结构化数据，再转换成 Neo4j 可导入的图节点/关系 CSV。
2. **在线阶段**：从 Neo4j 读出图数据，构建结构化文档与 chunk，建立 Milvus 向量索引，再结合传统混合检索、图 RAG 检索、智能路由和 LLM 生成答案。

因此，这个目录里的代码实际上分成了两条链路：

- **离线建图链路**：`agent(代码系ai生成)/` 负责 Markdown → JSON → CSV/Neo4j 数据。
- **在线问答链路**：`main.py` + `rag_modules/` 负责 Neo4j/Milvus 检索和问答。

---

## 2. 目录结构与职责划分

### 2.1 在线 RAG 主体

- `main.py`
  - 系统入口，负责模块装配、知识库构建、交互式问答。
- `config.py`
  - 所有核心配置，例如 Neo4j、Milvus、Embedding、LLM、chunk 参数。
- `rag_modules/graph_data_preparation.py`
  - 图数据准备模块：从 Neo4j 读图数据，构造成结构化菜谱文档，再切 chunk。
- `rag_modules/milvus_index_construction.py`
  - Milvus 索引构建模块：文本向量化、建集合、建索引、相似度搜索。
- `rag_modules/hybrid_retrieval.py`
  - 混合检索模块：实体级 + 主题级双层检索，结合图索引、Neo4j、BM25、Milvus。
- `rag_modules/graph_indexing.py`
  - 图索引模块：将图实体和图关系组织成 KV 检索结构。
- `rag_modules/graph_rag_retrieval.py`
  - 图 RAG 检索模块：图查询理解、多跳遍历、子图提取、路径描述、图推理。
- `rag_modules/intelligent_query_router.py`
  - 智能查询路由器：分析查询复杂度并选择检索策略。
- `rag_modules/generation_integration.py`
  - 生成模块：把检索结果拼接成上下文，调用 Moonshot/Kimi 生成最终答案。

### 2.2 离线图数据生产链路

- `agent(代码系ai生成)/recipe_ai_agent.py`
  - 核心离线处理器。负责：
    - LLM 解析 Markdown 菜谱为 JSON。
    - 将 JSON 解析为 dataclass / 字典。
    - 构建节点、关系、属性、ID。
    - 批量处理、断点续传、分批保存。
    - 导出 Neo4j CSV。
- `agent(代码系ai生成)/amount_normalizer.py`
  - 用量标准器：把“适量 / 少许 / 一把 / 几滴”等表达统一化，并支持估算数值映射。
- `agent(代码系ai生成)/batch_manager.py`
  - 批处理辅助工具：查看进度、继续处理、合并批次、清理状态。
- `agent(代码系ai生成)/run_ai_agent.py`
  - 运行脚本封装。
- `agent(代码系ai生成)/AI_AGENT_README.md`
  - 这条离线链路原有说明。

---

## 3. 系统主流程：从启动到回答问题

## 3.1 入口类：`AdvancedGraphRAGSystem`

主入口在 `main.py` 中的 `AdvancedGraphRAGSystem` 类。

### 关键函数顺序

1. `initialize_system()`
2. `build_knowledge_base()`
3. `ask_question_with_routing()`
4. `generation_module.generate_adaptive_answer()` 或流式版本

### 实际执行流程

#### 第一步：初始化所有模块

`initialize_system()` 依次初始化：

1. `GraphDataPreparationModule`
2. `MilvusIndexConstructionModule`
3. `GenerationIntegrationModule`
4. `HybridRetrievalModule`
5. `GraphRAGRetrieval`
6. `IntelligentQueryRouter`

这一步相当于把：

- 图数据库连接
- 向量数据库连接
- LLM 客户端
- 混合检索器
- 图检索器
- 路由器

全部装配完成。

#### 第二步：构建或加载知识库

`build_knowledge_base()` 的逻辑是：

- 先检查 Milvus 集合是否已经存在。
- 如果存在，则直接 `load_collection()`。
- 即使 Milvus 已存在，也仍然会重新从 Neo4j 加载图数据，重新构造文档和 chunk，因为图检索和图索引依赖图结构内存态。
- 如果不存在，就执行完整的新建流程：
  1. `load_graph_data()`
  2. `build_recipe_documents()`
  3. `chunk_documents()`
  4. `build_vector_index()`
  5. 初始化检索器

#### 第三步：用户提问

`ask_question_with_routing()` 的执行顺序：

1. 路由器分析问题。
2. 自动选择：传统混合检索 / 图 RAG / 组合检索。
3. 返回相关文档 `relevant_docs`。
4. 生成模块读取这些文档，构造 prompt。
5. LLM 输出最终答案。

---

## 4. GraphDataPreparationModule：图数据准备模块

文件：`rag_modules/graph_data_preparation.py`

这个模块承担的是**在线阶段的数据装配**：

- 连接 Neo4j。
- 读取图中的 Recipe / Ingredient / CookingStep 节点。
- 把图结构重新组织成**结构化 Markdown 风格文档**。
- 把文档切成 chunk，供 BM25/Milvus 检索。

注意：它本身**不负责把 Markdown 原始菜谱直接写入 Neo4j**；那部分功能实际上在 `agent(代码系ai生成)` 目录中实现。也就是说，GraphDataPreparationModule 是“在线读图构文档”，离线建图由 AI Agent 链路负责。

### 4.1 数据结构

#### `GraphNode`

用于统一表示图节点：

- `node_id`
- `labels`
- `name`
- `properties`

#### `GraphRelation`

定义了关系结构：

- `start_node_id`
- `end_node_id`
- `relation_type`
- `properties`

当前在线流程里，真正大量使用的是 `GraphNode`，`GraphRelation` 更像预留结构。

### 4.2 核心函数

#### `__init__(uri, user, password, database)`

初始化连接参数，准备以下内存容器：

- `documents`
- `chunks`
- `recipes`
- `ingredients`
- `cooking_steps`

并立即调用 `_connect()`。

#### `_connect()`

负责建立 Neo4j Driver，并用 `RETURN 1` 做连通性测试。

#### `load_graph_data()`

这是在线图数据读取入口，做了三类节点加载：

1. **Recipe 节点**
   - 查询 `Recipe`。
   - 限定 `nodeId >= '200000000'`，说明系统把动态生成的业务节点放在这个 ID 区间。
   - 额外 `OPTIONAL MATCH (r)-[:BELONGS_TO_CATEGORY]->(c:Category)`，将分类关系回填到 `properties` 中。

2. **Ingredient 节点**
   - 直接加载所有 `Ingredient` 节点。

3. **CookingStep 节点**
   - 直接加载所有 `CookingStep` 节点。

#### 为什么这里很重要？

因为这一层把 Neo4j 中离散的图节点转成了 Python 内存对象，后续：

- 构文档要用它。
- 混合检索构图索引也要用它。
- 系统统计也要用它。

### 4.3 构建结构化菜谱文档：`build_recipe_documents()`

这是 GraphDataPreparationModule 的核心价值所在。

它并不是简单把某个节点的 description 读出来，而是**以 Recipe 为中心重新聚合图邻居信息**，形成“可供 LLM 阅读的结构化菜谱文档”。

#### 对每个 Recipe，会做什么？

1. 读取菜谱关联食材：
   - `MATCH (r:Recipe)-[req:REQUIRES]->(i:Ingredient)`
   - 取出 `amount`、`unit`、`description`

2. 读取菜谱关联步骤：
   - `MATCH (r:Recipe)-[c:CONTAINS_STEP]->(s:CookingStep)`
   - 取出 `description`、`stepNumber`、`methods`、`tools`、`timeEstimate`

3. 把这些数据拼成类似 Markdown 的结构：
   - `# 菜谱名`
   - `## 菜品描述`
   - 菜系、难度、时间信息、份量
   - `## 所需食材`
   - `## 制作步骤`
   - `## 标签`

4. 生成 `Document`
   - `page_content` 是完整内容。
   - `metadata` 里保存 `node_id / recipe_name / category / cuisine_type / difficulty / doc_type / ingredients_count / steps_count` 等信息。

#### 为什么要这样做？

因为图数据本身适合关系查询，但不适合直接送进向量模型。这个函数相当于完成了：

> 图结构 → 结构化语义文档

这样既保留了知识结构完整性，又让后续向量检索和生成模型更容易理解。

### 4.4 文档切块：`chunk_documents()`

构好菜谱文档后，还要切成 chunk，供：

- BM25 检索
- Milvus 向量检索
- 结果融合

#### 切块策略

1. **短文档**：不切，直接作为单块。
2. **有二级标题的文档**：优先按 `\n## ` 分段切块。
3. **没有明显章节结构的文档**：按长度做滑动窗口分块，使用 `chunk_size` 与 `chunk_overlap`。

#### chunk metadata 里补充的信息

- `chunk_id`
- `parent_id`
- `chunk_index`
- `total_chunks`
- `chunk_size`
- `section_title`
- `doc_type = chunk`

这一步很关键，因为后续无论是 BM25 还是 Milvus，检索到的实际上都是 chunk，不是完整 recipe 文档。

### 4.5 统计函数：`get_statistics()`

输出：

- 菜谱数
- 食材数
- 步骤数
- 文档数
- chunk 数
- 分类分布
- 菜系分布
- 难度分布
- 平均文档长度
- 平均 chunk 大小

这主要用于 `main.py` 中知识库概况展示。

---

## 5. 你要求的“GraphDataPreparationModule 离线补全”对应实现在哪里

你在需求里提到的这些能力：

- 通过 LLM 将结构化 Markdown 菜谱数据转换为 CSV 格式图数据
- 节点数据（菜谱、食材、步骤）
- 关系数据（菜谱-食材，菜谱-步骤）
- 用量标准器
- 数值映射
- LLM 提取 JSON，再解析成字典
- 利用字典数据构建节点信息、关系 id、属性等
- 将数据存入 Neo4j
- 批量处理和断点续传
- 保存 json 记录 totalfiles、processedfiles

这些能力并不在 `rag_modules/graph_data_preparation.py` 中，而是由 `agent(代码系ai生成)/recipe_ai_agent.py` + `amount_normalizer.py` 这套离线链路来承担。也就是说，**如果你要把 README 写完整，GraphDataPreparationModule 应该拆成“离线建图子阶段 + 在线读图子阶段”两个层面描述**。下面按实际代码解释。

### 5.1 Markdown → JSON：`KimiRecipeAgent.extract_recipe_info()`

文件：`agent(代码系ai生成)/recipe_ai_agent.py`

这是离线建图的第一步。

#### 输入

- `markdown_content`
- `file_path`

#### 做法

1. `infer_category_from_path(file_path)` 根据目录路径推断菜谱分类。
2. 构造一个非常详细的 prompt，要求大模型抽取：
   - 菜谱名称
   - 难度
   - 分类
   - 菜系
   - prep_time / cook_time / servings
   - ingredients
   - steps
   - tags
   - nutrition_info
3. `call_kimi_api()` 调 Moonshot/Kimi 模型。
4. 对返回的 JSON 文本做清洗。
5. `json.loads()` 解析。
6. 转换为 `RecipeInfo / IngredientInfo / CookingStep` 这些 dataclass。

#### 这正对应你的需求

- “利用 LLM 提取 json 格式的数据，然后解析为字典数据”
- “结构化 Markdown 菜谱 → 图数据的智能转换”

### 5.2 规则兜底：`_fallback_parse()`

如果 LLM JSON 解析失败，就用规则方法粗略提取：

- 标题行 → 菜名
- `★` 数量 → 难度
- 菜名关键词 → 粗略分类

这保证批量处理时不会因为个别样本彻底中断。

### 5.3 用量标准器：`AmountNormalizer`

文件：`agent(代码系ai生成)/amount_normalizer.py`

这是你需求里“用量标准器 + 数值映射”的直接实现。

#### `amount_mappings`

把相似概念统一，例如：

- `适当 / 酌量 / 随意` → `适量`
- `少量 / 一点点 / 微量 / 稍许` → `少许`
- `一把` → `1把`
- `一勺` → `1勺`
- `2-3滴` → `几滴`

#### `estimated_values`

把模糊概念映射成估计数值，例如：

- `少许` → `2`
- `中量` → `10`
- `大量` → `30`
- `1勺` → `5`
- `1汤匙` → `15`
- `1撮` → `1`

#### 核心函数

- `normalize_amount(amount, unit)`
  - 标准化表达 + 返回估计值。
- `parse_amount_with_unit(amount_str)`
  - 从“300毫升”“2个”“适量盐”这类字符串中拆出数量和单位。
- `get_comparable_value(amount, unit)`
  - 返回可比较的数值。
- `format_for_display(amount, unit)`
  - 生成展示用字符串。

#### 说明

目前这套标准化器已经实现，但在 `recipe_ai_agent.py` 的 `process_recipe()` 里还没有完全深度联动进去；也就是说，**框架上已经具备了“标准映射 + 数值估算”能力，但如果你后续要进一步补强，最自然的接入点就是在 `extract_recipe_info()` 输出 ingredients 后、`process_recipe()` 建节点前，对 amount/unit 做统一标准化。**

### 5.4 JSON / dataclass → 图节点与关系：`RecipeKnowledgeGraphBuilder.process_recipe()`

这一步就是你要求的：

- “利用字典数据，为每个节点构建信息、关系 id、属性等”
- “转换后的数据包括节点数据、关系数据”

#### 做法

1. 调用 `extract_recipe_info()` 得到 `RecipeInfo`。
2. 用 `generate_concept_id()` 生成菜谱节点 ID。
3. 构建菜谱节点字典 `recipe_concept`。
4. 遍历 `ingredients`：
   - 给每个食材生成节点 ID。
   - 构建 `Ingredient` 节点。
   - 创建 `Recipe -> Ingredient` 关系，关系上保存 `amount`、`unit`。
5. 遍历 `steps`：
   - 给每个步骤生成节点 ID。
   - 构建 `CookingStep` 节点。
   - 创建 `Recipe -> CookingStep` 关系，关系上保存 `step_order`。
6. 根据菜谱分类建立 `belongs_to_category` 关系。
7. 根据难度建立 `has_difficulty` 关系。

#### 节点类型

- `Recipe`
- `Ingredient`
- `CookingStep`
- 若干预定义概念：如分类、难度、根概念

#### 关系类型映射

在 `_init_relationship_mappings()` 中定义，包括：

- `has_ingredient`
- `requires_tool`
- `has_step`
- `belongs_to_category`
- `has_difficulty`
- `uses_method`
- `has_amount`
- `step_follows`
- `serves_people`
- `cooking_time`
- `prep_time`

不过当前 `process_recipe()` 实际重点用了：

- `has_ingredient`
- `has_step`
- `belongs_to_category`
- `has_difficulty`

### 5.5 导出 CSV：`export_to_neo4j_csv()`

这是 Markdown → Graph CSV 的最终落地步骤。

#### 导出的文件

- `nodes.csv`
- `relationships.csv`
- `neo4j_import.cypher`

#### 节点 CSV 内容

节点里会包含：

- `nodeId`
- `labels`
- `name`
- `preferredTerm`
- `category`
- `conceptType`
- `synonyms`

对于不同节点类型还会补充：

- `Recipe`：`difficulty / cuisineType / prepTime / cookTime / servings / tags / filePath`
- `Ingredient`：`amount / unit / isMain`
- `CookingStep`：`description / stepNumber / methods / tools / timeEstimate`

#### 关系 CSV 内容

关系里会包含：

- `startNodeId`
- `endNodeId`
- `relationshipType`
- `relationshipId`
- 以及额外属性，例如：`amount / unit / step_order`

### 5.6 写入 Neo4j

当前代码并没有直接用 Python Driver 批量写 Neo4j，而是采用：

1. 先导出 `nodes.csv`
2. 再导出 `relationships.csv`
3. 自动生成 `neo4j_import.cypher`
4. 由 Neo4j 执行 `LOAD CSV` + `apoc.create.relationship`

也就是说，这个项目的“将数据存入 neo4j”是通过**CSV + Cypher 导入脚本**完成的，而不是在线插入。

这在工程上是合理的，因为：

- 更适合大批量导入
- 便于断点续传和重跑
- 中间文件可审计、可修复

### 5.7 批量处理与断点续传

这部分由 `RecipeKnowledgeGraphBuilder` 实现。

#### `save_progress()`

会写出 `progress.json`，保存：

- `processed_files`
- `current_file`
- `total_files`
- `processed_count`
- `current_batch`
- `concept_id_counter`
- `timestamp`
- `concepts_count`
- `relationships_count`

这与你提到的：

- “保存一个 json 文件记录 totalfiles, processedfiles”

完全一致，而且实际实现比这更完整。

#### `load_progress()`

启动时读取 `progress.json`，恢复：

- 已处理文件集合
- 当前 batch 编号
- concept ID 计数器

#### `save_batch_data()`

每一批写到：

- `batch_xxx/concepts.csv`
- `batch_xxx/relationships.csv`

#### `merge_all_batches()`

最后把所有批次数据汇总成总 CSV。

#### `batch_process_recipes()`

核心批处理入口，流程是：

1. 加载进度（可 resume）。
2. 扫描菜谱目录，默认重点扫描 `dishes/`。
3. 过滤掉无关目录。
4. 跳过已处理文件。
5. 循环处理每个 Markdown。
6. 每 5 个文件保存一次进度。
7. 达到 `batch_size` 时保存批次并清空内存。
8. 中断时保存当前进度和当前批次。

这正是你的“批量处理和断点续传”要求。

---

## 6. MilvusIndexConstructionModule：向量索引模块

文件：`rag_modules/milvus_index_construction.py`

### 6.1 职责

这个模块负责：

- 连接 Milvus
- 加载 Embedding 模型
- 创建 collection schema
- 文本向量化
- 写入向量
- 建立 HNSW 索引
- 相似度检索

### 6.2 模型与向量维度

在 `config.py` 中默认配置：

- 模型：`BAAI/bge-small-zh-v1.5`
- 向量维度：`512`

这正对应你给出的需求：

- “使用 BGE-small-zh-v1.5 模型，512 维向量空间”

### 6.3 关键函数

#### `_setup_client()`

初始化 `MilvusClient`，连接 `http://host:port`。

#### `_setup_embeddings()`

初始化 `HuggingFaceEmbeddings`：

- `device='cpu'`
- `normalize_embeddings=True`

#### `_create_collection_schema()`

定义字段，包括：

- `id`
- `vector`
- `text`
- `node_id`
- `recipe_name`
- `node_type`
- `category`
- `cuisine_type`
- `difficulty`
- `doc_type`
- `chunk_id`
- `parent_id`

#### `build_vector_index(chunks)`

完整建索引主流程：

1. `create_collection(force_recreate=True)`
2. 用 embedding 模型对 chunk 文本做 `embed_documents()`
3. 整理实体字段
4. 分批插入 Milvus
5. `create_index()` 建 HNSW 索引
6. `load_collection()`
7. 等待索引构建结束

#### `similarity_search(query, k, filters)`

在线检索入口：

1. `embed_query(query)`
2. 可选生成 filter 表达式
3. 调 Milvus `search`
4. 把结果重新整理成统一结构：
   - `score`
   - `text`
   - `metadata`

### 6.4 为什么 metadata 很重要

因为检索到的不是裸文本，而是带图来源信息的 chunk。后续在：

- 路由器后处理
- 生成模块 prompt 构造
- 展示 recipe_name / node_type / score

这些环节都要依赖 metadata。

---

## 7. HybridRetrievalModule：混合检索模块

文件：`rag_modules/hybrid_retrieval.py`

### 7.1 模块定位

这是传统混合检索策略，不是“纯向量”，也不是“纯图查询”，而是多种检索手段的结合：

- 图索引键值对检索
- Neo4j 全文补充检索
- BM25
- Milvus 向量检索
- 最终用 Round-robin 方式融合

### 7.2 初始化

#### `initialize(chunks)`

做三件事：

1. 建 Neo4j driver。
2. 用 chunk 构建 `BM25Retriever`。
3. 调 `_build_graph_index()` 建图索引。

### 7.3 图索引构建：`_build_graph_index()`

底层使用 `GraphIndexingModule`：

1. 从 `data_module` 拿到 `recipes / ingredients / cooking_steps`
2. `create_entity_key_values()`
3. `_extract_relationships_from_graph()` 从 Neo4j 读取关系
4. `create_relation_key_values()`
5. `deduplicate_entities_and_relations()`

换句话说，这个模块在线上会把图数据额外加工成一套**适合检索的 KV 索引结构**。

### 7.4 查询关键词提取：`extract_query_keywords()`

这是双层检索的入口。

系统要求 LLM 把用户问题拆成两层：

1. **实体级关键词**：
   - 具体菜名、食材、工具等。
2. **主题级关键词**：
   - 抽象主题，如减肥、低脂、川菜、快手菜。

这样能把“查具体对象”和“查主题概念”区分开来。

### 7.5 实体级检索：`entity_level_retrieval()`

流程：

1. 用图索引按 key 精确找实体。
2. 对每个命中实体，补充一跳邻居 `_get_node_neighbors()`。
3. 如果图索引结果不足，再走 `_neo4j_entity_level_search()` 做 Neo4j 全文补充。
4. 按相关性排序。

这适合回答：

- 某个食材是什么
- 某道菜有哪些信息
- 某实体相关的一跳知识

### 7.6 主题级检索：`topic_level_retrieval()`

这部分更偏“概念级、主题级扩展”。

通常会利用：

- 图关系键值对
- 主题相关关系内容
- Neo4j 补充主题检索

它适合：

- 减脂餐推荐
- 川菜特色
- 家常菜主题归纳

### 7.7 双层检索：`dual_level_retrieval()`

这是你需求中“实体级 + 主题级双层检索”的核心落点。

流程：

1. `extract_query_keywords()`
2. `entity_level_retrieval()`
3. `topic_level_retrieval()`
4. Round-robin 合并成 `Document`

### 7.8 增强向量检索：`vector_search_enhanced()`

使用 Milvus 做语义相似度搜索，并把结果整理为 `Document`。

### 7.9 最终混合检索：`hybrid_search()`

这个函数是传统检索总入口，一般会融合：

- 双层检索结果
- 向量检索结果
- 可能还加 BM25 信号

最终产出统一的 `Document` 列表。

### 7.10 这里的 RRF / 轮询融合

从代码风格和注释看，这一层使用的是以 Round-robin 为主的融合思想，强调：

- 不让单一来源结果霸榜
- 实体级和主题级交替进入结果列表
- 与图 RAG 联合时也采用轮询合并

所以你在 README 里可以写成：

- “采用类 RRF / Round-robin 的多源融合策略”
- 如果严格从现有实现出发，更准确的表述是“**轮询融合（Round-robin）优先，非标准公式化 RRF**”。

---

## 8. GraphIndexingModule：图索引模块

文件：`rag_modules/graph_indexing.py`

这个模块是 HybridRetrievalModule 的底层支撑。

### 8.1 作用

把图数据重新组织成两种 KV：

1. **实体 KV**
2. **关系 KV**

便于做关键词级检索，而不是每次都直接访问整图。

### 8.2 实体 KV：`create_entity_key_values()`

为以下实体生成索引：

- Recipe
- Ingredient
- CookingStep

每个实体会生成：

- `entity_name`
- `index_keys`
- `value_content`
- `entity_type`
- `metadata`

其中默认把实体名称作为唯一主索引键。

### 8.3 关系 KV：`create_relation_key_values()`

把图中的关系也抽象成可检索对象。

这样主题级检索时就不仅能查节点，也能查关系语义。

### 8.4 去重优化：`deduplicate_entities_and_relations()`

避免重复索引项影响检索质量。

---

## 9. GraphRAGRetrieval：图 RAG 检索模块

文件：`rag_modules/graph_rag_retrieval.py`

这部分是整个系统最“图”的地方，目标不是只靠文本相似度，而是让查询直接作用于图结构。

### 9.1 核心能力

- 图查询理解
- 多跳遍历
- 子图提取
- 图结构推理
- 查询规划

### 9.2 初始化：`initialize()`

1. 建 Neo4j 连接。
2. 调 `_build_graph_index()` 预热。

### 9.3 查询理解：`understand_graph_query()`

这是从自然语言到图查询结构的关键一步。

#### LLM 需要输出的内容

- `query_type`
- `source_entities`
- `target_entities`
- `relation_types`
- `max_depth`
- `constraints`

#### 支持的查询类型

- `ENTITY_RELATION`
- `MULTI_HOP`
- `SUBGRAPH`
- `PATH_FINDING`
- `CLUSTERING`

#### 示例理解方式

- “鸡肉配什么蔬菜” → `multi_hop`
- “川菜有什么特色” → `subgraph`
- “和宫保鸡丁类似的菜有哪些” → `clustering`

### 9.4 多跳遍历：`multi_hop_traversal()`

这一步才真正体现图结构优势。

#### 实现方式

- 基于 `source_entities` 在 Neo4j 中定位起点。
- 构造 `MATCH path = (source)-[*1..max_depth]-(target)`。
- 可选按 `target_keywords` 过滤终点。
- 使用路径长度、节点度数、关系类型匹配做 relevance 评分。
- 返回 `GraphPath` 列表。

#### 意义

它不是只找“相似文本”，而是在找：

- 哪些路径把用户关心的实体连接起来
- 哪些中间节点提供了推理依据

### 9.5 子图提取：`extract_knowledge_subgraph()`

当问题更适合“围绕一个中心实体看整体知识网络”时，系统会提取子图。

产物是 `KnowledgeSubgraph`，包含：

- `central_nodes`
- `connected_nodes`
- `relationships`
- `graph_metrics`
- `reasoning_chains`

### 9.6 图结构推理：`graph_structure_reasoning()`

输入是子图和问题，输出是一组 reasoning chains / reasoning statements。

从接口设计看，这一层的作用是：

- 不是只返回节点
- 而是尝试把“节点 + 边 + 拓扑”转成可解释的推理链

### 9.7 自适应查询规划：`adaptive_query_planning()`

对于复杂问题，系统可以把一个问题拆成多个图查询计划。

这意味着它未来可以扩展为：

- 先查实体关系
- 再查类别扩展
- 最后做综合推理

### 9.8 最终入口：`graph_rag_search()`

整体流程可概括为：

1. `understand_graph_query(query)`
2. 根据类型走多跳遍历或子图提取
3. 路径 / 子图转为 `Document`
4. `_rank_by_graph_relevance()` 排序
5. 返回文档

### 9.9 图检索结果如何转回文本

系统通过：

- `_build_path_description()`
- `_build_subgraph_description()`
- `_paths_to_documents()`
- `_subgraph_to_documents()`

把图结构重新描述成自然语言文本块，再交给生成模块。

这一步是 Graph RAG 的关键闭环：

> 图查询结果 → 可供 LLM 消化的语义描述

---

## 10. IntelligentQueryRouter：智能查询路由

文件：`rag_modules/intelligent_query_router.py`

### 10.1 模块目的

不是所有问题都适合用图查询。

例如：

- “红烧肉怎么做”更适合传统检索。
- “鸡肉为什么适合搭配某些蔬菜”更适合图推理。

所以这里需要一个路由器自动决定走哪条检索链路。

### 10.2 查询分析：`analyze_query()`

系统让 LLM 输出以下指标：

- `query_complexity`
- `relationship_intensity`
- `reasoning_required`
- `entity_count`
- `recommended_strategy`
- `confidence`
- `reasoning`

### 10.3 路由策略

定义在 `SearchStrategy`：

- `HYBRID_TRADITIONAL`
- `GRAPH_RAG`
- `COMBINED`

### 10.4 路由执行：`route_query()`

执行顺序：

1. `analyze_query(query)`
2. 更新路由统计
3. 分发到：
   - `traditional_retrieval.hybrid_search()`
   - `graph_rag_retrieval.graph_rag_search()`
   - `_combined_search()`
4. `_post_process_results()` 给 metadata 打上路由标签

### 10.5 组合检索：`_combined_search()`

采用交替合并：

- 先取图 RAG 结果
- 再取传统检索结果
- 用内容 hash 做去重
- 最终截断为 top_k

这正是“动态策略选择 + 多源融合”的体现。

### 10.6 降级逻辑

如果 LLM 分析失败：

- 使用 `_rule_based_analysis()` 做规则兜底。

如果路由执行失败：

- 自动降级到传统混合检索。

这保证系统不会因为某个高级模块故障而完全不可用。

---

## 11. GenerationIntegrationModule：生成集成模块

文件：`rag_modules/generation_integration.py`

### 11.1 职责

负责把检索结果真正变成最终答案。

### 11.2 初始化

- 读取环境变量 `MOONSHOT_API_KEY`
- 用 `OpenAI(base_url="https://api.moonshot.cn/v1")` 初始化客户端

### 11.3 非流式生成：`generate_adaptive_answer()`

流程：

1. 遍历检索得到的 `Document`。
2. 从 `page_content` 取正文。
3. 如果 metadata 里有 `retrieval_level`，则加上层级标签。
4. 拼成统一 context。
5. 构造“专业烹饪助手”提示词。
6. 调用 LLM 生成最终回答。

### 11.4 流式生成：`generate_adaptive_answer_stream()`

在非流式逻辑基础上，增加：

- `stream=True`
- `timeout=60`
- 最多 `max_retries=3`
- 网络失败时指数回退重试
- 最终还能回退到非流式回答

### 11.5 为什么叫“自适应生成”

因为提示词不是按固定问答模板硬编码分类，而是让同一套模板根据上下文和问题类型自适应输出：

- 列表型答案
- 步骤型答案
- 综合型答案

---

## 12. 配置中心：`GraphRAGConfig`

文件：`config.py`

### 核心配置项

#### Neo4j

- `neo4j_uri`
- `neo4j_user`
- `neo4j_password`
- `neo4j_database`

#### Milvus

- `milvus_host`
- `milvus_port`
- `milvus_collection_name`
- `milvus_dimension = 512`

#### 模型

- `embedding_model = BAAI/bge-small-zh-v1.5`
- `llm_model = kimi-k2-0711-preview`

#### 检索 / 图配置

- `top_k = 5`
- `chunk_size = 500`
- `chunk_overlap = 50`
- `max_graph_depth = 2`

#### 生成配置

- `temperature = 0.1`
- `max_tokens = 2048`

这些参数共同决定：

- 文档块粒度
- 图遍历深度
- 检索返回条数
- 生成稳定性和长度

---

## 13. 一条完整数据流示例

下面用“适合减肥的鸡肉菜有哪些？”举例，说明整套系统怎么跑。

### 13.1 离线阶段

1. Markdown 菜谱输入。
2. `KimiRecipeAgent.extract_recipe_info()` 提取 JSON。
3. 解析成 `RecipeInfo`。
4. `RecipeKnowledgeGraphBuilder.process_recipe()`：
   - 建 Recipe 节点
   - 建 Ingredient 节点
   - 建 CookingStep 节点
   - 建 Recipe-Ingredient、Recipe-Step、Recipe-Category 等关系
5. `export_to_neo4j_csv()` 导出 `nodes.csv / relationships.csv / neo4j_import.cypher`
6. 导入 Neo4j。

### 13.2 在线建知识库阶段

1. `GraphDataPreparationModule.load_graph_data()` 从 Neo4j 读图。
2. `build_recipe_documents()` 以 Recipe 为中心聚合食材和步骤，生成结构化文档。
3. `chunk_documents()` 切成 chunk。
4. `MilvusIndexConstructionModule.build_vector_index()` 生成向量并写入 Milvus。
5. `HybridRetrievalModule.initialize()` 建 BM25 和图索引。
6. `GraphRAGRetrieval.initialize()` 预热图缓存。

### 13.3 在线问答阶段

1. 用户输入问题。
2. `IntelligentQueryRouter.analyze_query()` 判断复杂度。
3. 若问题偏推荐 + 主题抽象，可能走 `COMBINED`。
4. 传统链路从关键词、向量、BM25 找文本块。
5. 图链路从实体、路径、子图找结构化证据。
6. 路由器融合结果。
7. `GenerationIntegrationModule` 用这些结果生成最终答案。

---

## 14. 模块之间的依赖关系

可以把依赖关系理解成下面这样：

```text
Markdown菜谱
   ↓
KimiRecipeAgent / RecipeKnowledgeGraphBuilder
   ↓
Neo4j CSV + 导入脚本
   ↓
Neo4j 图数据库
   ↓
GraphDataPreparationModule
   ↓
结构化 Document / Chunk
   ├─→ MilvusIndexConstructionModule
   ├─→ HybridRetrievalModule(BM25 + 图索引)
   └─→ GraphRAGRetrieval(图查询)
                ↓
       IntelligentQueryRouter
                ↓
     GenerationIntegrationModule
                ↓
             最终回答
```

---

## 15. 如果按你的需求给 GraphDataPreparationModule 重新命名/理解，最合理的分层方式

为了与你给出的需求对齐，我建议在概念上把“图数据准备模块”拆成两个子模块理解：

### A. 离线图数据构建层

对应当前实际代码：

- `KimiRecipeAgent`
- `RecipeKnowledgeGraphBuilder`
- `AmountNormalizer`
- `batch_manager.py`

职责：

- Markdown → JSON
- JSON → 节点/关系字典
- 标准化用量
- 生成 Neo4j CSV
- 批量处理与断点续传

### B. 在线图数据装配层

对应当前实际代码：

- `GraphDataPreparationModule`

职责：

- Neo4j → Python GraphNode
- GraphNode → 结构化菜谱文档
- 文档 → chunk
- 为 Milvus / BM25 / Hybrid / GraphRAG 提供统一输入

这样你写 README 时，就不会把“离线建图”和“在线读图”混在一起。

---

## 16. 当前实现的优点

### 16.1 优点

1. **链路完整**
   - 已经覆盖离线建图、在线检索、生成问答。

2. **图与向量都用了**
   - 不只是简单向量 RAG，也不只是图数据库查询。

3. **结构化文档构建合理**
   - 以 Recipe 为中心聚合邻居，保留知识结构。

4. **批处理工程化程度不错**
   - 有进度记录、分批保存、恢复处理。

5. **路由设计清晰**
   - 简单问答和复杂关系推理分流明确。

### 16.2 当前仍可增强的点

1. **AmountNormalizer 还没完全接入主建图流程**
   - 可以在 `process_recipe()` 前后统一标准化 amount/unit。

2. **Neo4j 导入是离线脚本方式，不是 Python 直接写入**
   - 如果要更自动化，可以补 `write_to_neo4j()`。

3. **Hybrid 模块中的“RRF”更偏轮询融合，而不是标准 Reciprocal Rank Fusion 公式**
   - 如果后续论文化或产品化表述，需要说明清楚。

4. **GraphRAG 中部分高级推理函数仍偏框架化**
   - 接口设计完整，但可以继续增强 reasoning chains 的质量。

---

## 17. 建议你如何阅读代码

如果你想快速理解整个系统，推荐按下面顺序阅读：

### 第一遍：先看主流程

1. `main.py`
2. `config.py`

先搞清楚系统怎么启动，模块怎么串起来。

### 第二遍：看在线链路

1. `rag_modules/graph_data_preparation.py`
2. `rag_modules/milvus_index_construction.py`
3. `rag_modules/hybrid_retrieval.py`
4. `rag_modules/graph_rag_retrieval.py`
5. `rag_modules/intelligent_query_router.py`
6. `rag_modules/generation_integration.py`

### 第三遍：看离线建图链路

1. `agent(代码系ai生成)/recipe_ai_agent.py`
2. `agent(代码系ai生成)/amount_normalizer.py`
3. `agent(代码系ai生成)/batch_manager.py`

这样理解成本最低。

---

## 18. 总结

这套 `code/C9` 的真实工作机制可以概括成一句话：

> 先用 LLM 把 Markdown 菜谱转成结构化图数据并导入 Neo4j，再从图数据库中按 Recipe 聚合出结构化文档，建立 Milvus 向量索引，同时保留图检索链路，最后由智能路由器在传统混合检索与图 RAG 之间动态选择，并交给生成模块输出答案。

如果只看你最初列出的模块名称，那么当前代码已经基本具备：

- GraphDataPreparationModule（在线读图构文档）
- MilvusIndexConstructionModule
- HybridRetrievalModule
- GraphRAGRetrieval
- IntelligentQueryRouter
- GenerationIntegrationModule

而你要求补全的“Markdown → CSV 图数据 + 用量标准化 + 批处理断点续传”部分，当前实际落在：

- `KimiRecipeAgent`
- `RecipeKnowledgeGraphBuilder`
- `AmountNormalizer`
- `batch_manager.py`

因此，从 README 的角度，**最正确的写法不是把这些能力硬塞进单个文件，而是把 C9 解释为一条“离线建图 + 在线图 RAG”完整流水线。**
