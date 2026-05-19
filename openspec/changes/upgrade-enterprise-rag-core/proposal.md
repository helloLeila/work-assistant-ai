## Why

### 问题 1：现有知识库链路还是“能跑的 demo”，不是企业级 RAG 核心

当前实现集中在以下几个文件：

- `backend/app/services/knowledge_service.py`
- `backend/app/vectorstore/milvus_client.py`
- `backend/app/chains/rag_chain.py`
- `backend/app/nodes/knowledge_rag_node.py`
- `backend/app/nodes/grader_node.py`

它已经具备“上传文档 -> 切分 -> Milvus 检索 -> 生成回答”的基本能力，但核心检索仍然偏简化：

- 文档切分固定为 `chunk_size=800`、`chunk_overlap=150`，没有按文档类型区分策略
- 检索主路径是 Milvus `max_marginal_relevance_search`，回退是本地词法重叠
- 没有正式的 `dense + sparse` 混合召回
- 没有专门的 rerank 层
- 没有 query rewrite
- 没有文档状态 / 版本过滤
- 没有正式的访问审计日志
- 调试时看不到“每一步到底发生了什么”

这套实现适合做原型，但不适合真实企业知识库。员工一旦开始问制度、流程、版本差异、部门权限问题，系统会很快暴露边界。

### 问题 2：权限、版本、状态都没有前置到检索阶段

现在 `KnowledgeService.search()` 只支持两个过滤维度：

- `department`
- `doc_type`

这不够企业使用。真实场景至少会遇到：

- 文档已作废，但还能被搜到
- 新旧版本并存，模型引用了旧版本
- HR 文档和财务文档不能混查
- 个人私有文档、项目组文档、公共文档可见范围不同

更关键的是：**权限必须发生在检索前，不是模型回答时“尽量别说”**。不该看的 chunk 根本不能进入候选集。

### 问题 3：检索质量缺少 2026 的通用标准做法

企业知识库里有两类问题：

- 语义表达问题：用户说“出差打车能不能报”，文档写的是“市内交通费报销标准”
- 精确关键词问题：用户问“P3 年假”“制度 V2.1”“劳动合同模板”

只做 dense 容易漏掉术语，只做 sparse 容易听不懂口语表达。2026 更通用的路线已经很稳定：

- query rewrite
- dense retrieval
- sparse retrieval / BM25
- hybrid merge
- rerank
- grounded answer with citations

Milvus 官方文档已经把 `Hybrid Search`、`Filtered Search`、`Reranking` 当成标准能力；Azure AI Search 官方文档也明确说明 hybrid search 通过 RRF 融合，并强调 RRF 常数 `k` 和 top-k 候选数不是一回事。

### 问题 4：没有把“后面还要补什么”写进正式文档，后续开发容易失控

之前很多需求是在聊天里确认的，比如：

- Query 改写默认全开，HyDE 只作为高价值场景可选项
- 需要文档状态和版本过滤
- 需要补齐企业权限细粒度
- 需要审计日志
- 需要低召回兜底

如果这些只留在聊天记录里，后面开发时最容易出现两种问题：

- 该做的核心漏掉
- 不该这轮做的东西被提前塞进一期，导致 scope 失控

所以这次 OpenSpec 除了写一期方案，也要把**后续 TODO 和延期项明确记下来**。

## What Changes

### A. 把现有 knowledge 能力升级成标准企业 RAG 核心分层

本次把知识库链路拆成 8 层清晰边界：

1. `Ingestion`：解析文档、切分 chunk、写入结构化元数据
2. `Metadata Policy`：维护状态、版本、可见范围、责任人等字段
3. `Access Control`：根据当前用户生成检索过滤条件
4. `Query Rewrite`：把口语化或上下文省略问题改写成更利于检索的查询
5. `Hybrid Retrieval`：并行执行 dense + sparse 检索
6. `Hybrid Merge + Rerank`：先融合候选，再用 reranker 重排
7. `Grounded Answering`：只基于通过权限和排序后的 chunk 回答，并附引用
8. `Observability`：输出可调试的检索轨迹和访问审计

### B. 一期新增文档状态、版本和权限过滤

文档与 chunk 元数据将补齐以下核心字段：

- `status`：`active` / `draft` / `deprecated` / `archived`
- `version`：如 `v1.0`、`v2.1`
- `is_latest`
- `effective_at`
- `expires_at`
- `visibility_scope`
- `department`
- `owner_user_id`
- `project_ids`
- `owner_name` / `maintainer`

其中：

- 检索默认只查 `active`
- 默认优先 `is_latest=true`
- 过期文档和停用文档不能进入候选集
- ACL 在检索前构造过滤表达式并注入 Milvus / 本地回退路径

### C. 一期引入 query rewrite，但严格控制成本

Query rewrite 设计分两档：

- 默认档：轻量 rewrite，全量开启
- 增强档：HyDE / 多路改写，只在高价值或低召回场景触发

也就是：

- 不让每个 query 都走昂贵扩写
- 但必须解决口语、省略、同义表达带来的检索损失

### D. 用可配置 profile 替代写死的检索链路

本次不把检索链路写死成某一组固定数字，而是定义三档 profile：

- `faq_low_cost`
- `standard`
- `high_recall`

默认推荐：

- FAQ：dense 20 + sparse 20 -> RRF 合并后取 30 -> rerank Top 3
- 标准：dense 30~50 + sparse 30~50 -> RRF 合并后取 30~50 -> rerank Top 3~5
- 高召回：merge 后上限 80，rerank 默认读 50、最大不超过 80，不作为默认值

RRF 常数默认沿用通用实现值（如 `60`），明确与候选集数量分离，不再混写成“RRF k=10”。

### E. 新增可审计、可调试、可降级的检索闭环

系统新增两类记录：

- `audit log`：谁查了什么、看到了哪些文档、是否命中过权限拒绝
- `debug trace`：rewrite 后 query、dense 候选、sparse 候选、融合结果、rerank 结果、最终引用

同时增加兜底：

- 候选太少时，自动放宽 profile 或重写 query 重试一次
- 权限过滤后为空时，明确告诉用户“没有权限或暂无可见资料”
- 检索分数低时，不硬答，走 clarify 或保守回答

### F. 把“后面还要补”的 TODO 正式写进文档

本次 change 会把以下内容明确写成**延期 TODO**，避免它们在一期里被误实现，也避免后续忘掉：

- ACL 权限继承
- 临时授权
- 审批流驱动的权限生效
- 文档生命周期自动化
- 检索效果评测平台
- 主动离线重建索引调度
- chunk 图谱 / heading-aware retrieval
- FAQ cache / semantic cache

## Capabilities

### New Capabilities

- `knowledge-ingestion`：企业知识库文档接入、切分、元数据建模、版本与状态管理
- `knowledge-retrieval`：query rewrite、dense+sparse 混合检索、RRF 融合、rerank 与引用回答
- `knowledge-access-control`：基于用户身份的检索前 ACL 过滤
- `knowledge-observability`：检索调试轨迹、访问审计、低召回兜底与失败诊断

### Modified Capabilities

<!-- 当前仓库还没有单独沉淀知识库 spec，本次以新增能力文档为主。 -->

## Impact

**代码**

- `backend/app/services/knowledge_service.py`
- `backend/app/vectorstore/milvus_client.py`
- `backend/app/chains/rag_chain.py`
- `backend/app/nodes/knowledge_rag_node.py`
- `backend/app/nodes/grader_node.py`
- `backend/app/models/domain.py`
- `backend/app/core/config.py`
- `backend/app/core/streaming.py`
- `backend/app/services/history_service.py`
- `backend/app/api/routes/knowledge.py`

**新增模块**

- `backend/app/services/query_rewrite_service.py`
- `backend/app/services/access_policy_service.py`
- `backend/app/services/retrieval_audit_service.py`
- `backend/app/services/rerank_service.py`
- `backend/app/services/knowledge_ingestion_service.py`

**数据与存储**

- 文档元数据结构需要升级
- chunk 元数据结构需要升级
- 审计日志需要单独存储介质或本地 JSONL 兜底
- Milvus collection schema 需要扩展 dense / sparse / scalar metadata

**测试**

- 新增 ingestion、ACL、hybrid retrieval、rerank、audit、debug trace 测试
- 需要补齐回归测试，确保旧的上传/检索接口不被破坏

**风险**

- 需要一次性梳理清楚“这轮必须做”与“后续 TODO”
- 需要迁移现有知识库元数据，否则新旧文档字段会不兼容
- 需要明确 rerank 与 query rewrite 的成本上限，否则延迟会飙升
