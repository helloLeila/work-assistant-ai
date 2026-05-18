# 企业知识库 RAG 核心升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 Milvus 的前提下，把现有知识库 demo 升级成企业可用的 RAG 核心：支持 metadata 治理、ACL、query rewrite、hybrid retrieval、rerank、history lookup、debug trace、audit log，并按 50 个中文 commit 渐进落地。

**Architecture:** 以现有 `knowledge_service -> milvus_client -> rag_chain -> knowledge_rag_node` 为骨架，拆出 ingestion、access policy、query rewrite、rerank、audit 等明确模块。检索链路统一改成 `rewrite -> ACL -> dense+sparse -> RRF -> rerank -> grounded answer`，所有 fallback 和日志策略都统一配置化。

**Tech Stack:** FastAPI, LangGraph, LangChain, Milvus, Python, pytest, JSON/JSONL, tiktoken

---

## 0. 执行规则

- 每个 commit 都是可测试、可回滚、可审查的最小切片。
- 所有 commit message 使用中文。
- 默认 TDD：先补测试，再写实现，再跑测试，再提交。
- 每一波结束都至少跑对应局部测试；关键里程碑跑 `make test-backend`。
- 不动用户现有运行数据文件：`backend/data/business_demo.db`、`backend/data/chat_history.json`。

## 1. 文件分工草图

### 现有核心文件

- `backend/app/services/knowledge_service.py`
  - 现有上传、metadata、重建索引入口
- `backend/app/vectorstore/milvus_client.py`
  - 现有 Milvus + 本地回退检索
- `backend/app/chains/rag_chain.py`
  - 现有 RAG 检索与生成
- `backend/app/nodes/knowledge_rag_node.py`
  - 现有知识库节点
- `backend/app/nodes/grader_node.py`
  - 现有检索评估与 web fallback 路由

### 计划新增文件

- `backend/app/services/knowledge_ingestion_service.py`
  - 上传分步流程、失败重试、chunk 产出
- `backend/app/services/access_policy_service.py`
  - ACL 统一计算
- `backend/app/services/query_rewrite_service.py`
  - light rewrite、keywords、HyDE、rewrite retry
- `backend/app/services/retrieval_audit_service.py`
  - 审计日志
- `backend/app/services/retrieval_debug_service.py`
  - debug trace 输出
- `backend/app/services/rerank_service.py`
  - rerank 统一调用
- `backend/app/services/metadata_migration_service.py`
  - 旧 metadata 迁移脚本/逻辑
- `backend/app/models/knowledge_retrieval.py`
  - retrieval payload / trace / audit typed models

### 重点测试文件

- `backend/tests/test_knowledge_ingestion_service.py`
- `backend/tests/test_access_policy_service.py`
- `backend/tests/test_query_rewrite_service.py`
- `backend/tests/test_milvus_client.py`
- `backend/tests/test_rag_chain.py`
- `backend/tests/test_knowledge_rag_node.py`
- `backend/tests/test_retrieval_audit_service.py`
- `backend/tests/test_metadata_migration_service.py`

## 2. 50 个中文 Commit 拆分

### Wave 1: Metadata 与迁移基线

#### Commit 1
- [ ] 范围：为文档 metadata typed model 建立新结构
- [ ] 文件：`backend/app/models/knowledge.py`、`backend/tests/test_knowledge_models.py`
- [ ] 测试：新增 metadata 默认值测试
- [ ] 提交：`提交 01：新增知识库元数据模型`

#### Commit 2
- [ ] 范围：为 retrieval payload/debug/audit 建立 typed model
- [ ] 文件：`backend/app/models/knowledge_retrieval.py`、`backend/tests/test_knowledge_retrieval_models.py`
- [ ] 测试：新增 payload 序列化测试
- [ ] 提交：`提交 02：新增检索载荷与日志模型`

#### Commit 3
- [ ] 范围：补 config 字段，加入 log retention、profile、bias mode、rewrite retry 配置
- [ ] 文件：`backend/app/core/config.py`、`.env.example`、`backend/tests/test_config.py`
- [ ] 测试：新增配置默认值测试
- [ ] 提交：`提交 03：补充企业检索配置项`

#### Commit 4
- [ ] 范围：为旧 metadata 设计迁移默认规则
- [ ] 文件：`backend/app/services/metadata_migration_service.py`、`backend/tests/test_metadata_migration_service.py`
- [ ] 测试：旧数据补齐 `version/effective_at/visibility_scope`
- [ ] 提交：`提交 04：实现知识库元数据迁移规则`

#### Commit 5
- [ ] 范围：把迁移服务接到 `KnowledgeService` 初始化流程
- [ ] 文件：`backend/app/services/knowledge_service.py`、`backend/tests/test_knowledge_service.py`
- [ ] 测试：启动时自动迁移旧 metadata
- [ ] 提交：`提交 05：接入元数据迁移入口`

### Wave 2: Ingestion 分步与 chunk 规则

#### Commit 6
- [ ] 范围：拆出 `KnowledgeIngestionService` 基础骨架
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：创建空骨架与状态流转测试
- [ ] 提交：`提交 06：拆出知识接入服务骨架`

#### Commit 7
- [ ] 范围：统一 token 计数器为 `tiktoken`
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：相同文档切分边界稳定
- [ ] 提交：`提交 07：统一切分 token 计数口径`

#### Commit 8
- [ ] 范围：将默认 chunking 改成 `512/128`
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：普通制度文档默认切分
- [ ] 提交：`提交 08：调整默认切片规则`

#### Commit 9
- [ ] 范围：加入 `ChunkingStrategyResolver`
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：合同/表格/流程表单允许特化策略
- [ ] 提交：`提交 09：增加切片策略解析器`

#### Commit 10
- [ ] 范围：为 `section_path` 加标题提取与安全回退
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：无法提取标题时回退到文件名与片段号
- [ ] 提交：`提交 10：补充分段路径回退规则`

### Wave 3: Ingestion 失败回滚与重试

#### Commit 11
- [ ] 范围：定义 ingestion 状态：`parse_failed/index_failed/sync_pending/migration_pending`
- [ ] 文件：`backend/app/models/knowledge.py`、`backend/tests/test_knowledge_models.py`
- [ ] 测试：状态枚举与默认值测试
- [ ] 提交：`提交 11：补充知识接入状态枚举`

#### Commit 12
- [ ] 范围：实现解析失败回滚
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：解析失败后保留原文件、不发布 chunk
- [ ] 提交：`提交 12：实现解析失败回滚`

#### Commit 13
- [ ] 范围：实现索引失败回滚
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：索引失败后不暴露半成品数据
- [ ] 提交：`提交 13：实现索引失败回滚`

#### Commit 14
- [ ] 范围：实现解析步骤单独重试
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：无需重传文件即可重试解析
- [ ] 提交：`提交 14：支持解析步骤重试`

#### Commit 15
- [ ] 范围：实现索引步骤单独重试
- [ ] 文件：`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_knowledge_ingestion_service.py`
- [ ] 测试：从 `index_failed` 恢复
- [ ] 提交：`提交 15：支持索引步骤重试`

### Wave 4: ACL 基线

#### Commit 16
- [ ] 范围：抽出 `AccessPolicyResolver` typed input/output
- [ ] 文件：`backend/app/services/access_policy_service.py`、`backend/tests/test_access_policy_service.py`
- [ ] 测试：public/department/private/project/admin 基础场景
- [ ] 提交：`提交 16：新增访问策略解析器`

#### Commit 17
- [ ] 范围：支持管理员查看 `private` 文档
- [ ] 文件：`backend/app/services/access_policy_service.py`、`backend/tests/test_access_policy_service.py`
- [ ] 测试：`knowledge_admin/hr_admin` 访问 private
- [ ] 提交：`提交 17：开放管理员私有文档权限`

#### Commit 18
- [ ] 范围：加 `project_ids` 依赖检查与显式禁用逻辑
- [ ] 文件：`backend/app/services/access_policy_service.py`、`backend/tests/test_access_policy_service.py`
- [ ] 测试：无 `project_ids` 时 project scope 禁用
- [ ] 提交：`提交 18：补足项目权限前置依赖`

#### Commit 19
- [ ] 范围：定义文档权限字段变更后的 chunk 同步接口
- [ ] 文件：`backend/app/services/access_policy_service.py`、`backend/app/services/knowledge_ingestion_service.py`、`backend/tests/test_access_policy_service.py`
- [ ] 测试：改文档权限后关联 chunk 镜像更新
- [ ] 提交：`提交 19：建立权限镜像同步接口`

#### Commit 20
- [ ] 范围：为大批量同步加入 `sync_pending`
- [ ] 文件：`backend/app/services/access_policy_service.py`、`backend/tests/test_access_policy_service.py`
- [ ] 测试：大批量权限更新期间默认不可检索
- [ ] 提交：`提交 20：加入权限同步中间态保护`

### Wave 5: Milvus 与本地回退统一过滤

#### Commit 21
- [ ] 范围：重构 `milvus_client.py`，接收统一 ACL 过滤对象
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：主路径接受 filter object
- [ ] 提交：`提交 21：统一向量检索过滤入口`

#### Commit 22
- [ ] 范围：Milvus dense 主路径执行 ACL + status + version + effective filter
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：无权限 chunk 不进候选集
- [ ] 提交：`提交 22：为稠密检索接入统一过滤`

#### Commit 23
- [ ] 范围：本地词法回退路径执行同一套过滤
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：Milvus 不可用时权限仍一致
- [ ] 提交：`提交 23：为本地兜底检索接入统一过滤`

#### Commit 24
- [ ] 范围：写死 visibility/status/version/effective 默认过滤策略
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：默认排除 deprecated/expired/non-latest
- [ ] 提交：`提交 24：固化默认检索过滤规则`

#### Commit 25
- [ ] 范围：增加 `history_lookup` filter 放宽逻辑
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：显式查询旧版/作废制度时可命中历史文档
- [ ] 提交：`提交 25：接入历史版本检索模式`

### Wave 6: Query Rewrite 与关键词

#### Commit 26
- [ ] 范围：新增 `QueryRewriteService` 基础骨架
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：rewrite result typed output
- [ ] 提交：`提交 26：新增查询改写服务骨架`

#### Commit 27
- [ ] 范围：实现 light rewrite + 原 query fallback
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：rewrite 报错时直接回退原 query
- [ ] 提交：`提交 27：实现轻量改写与失败兜底`

#### Commit 28
- [ ] 范围：实现关键词提取上限与停用词规则
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：最多 5 个关键词、过滤礼貌词和虚词
- [ ] 提交：`提交 28：统一关键词提取规范`

#### Commit 29
- [ ] 范围：实现禁止改写名单
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：工号/项目编码/合同编号不被改写
- [ ] 提交：`提交 29：加入固定编码改写黑名单`

#### Commit 30
- [ ] 范围：接入 rewrite retry，最大 1 次
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：低召回时只允许重试 1 次
- [ ] 提交：`提交 30：限制改写重试次数`

### Wave 7: Sparse、Hybrid 与权重偏向

#### Commit 31
- [ ] 范围：在 `milvus_client.py` 增加 sparse/BM25 检索数据结构
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：sparse 候选可独立返回
- [ ] 提交：`提交 31：新增稀疏检索数据通道`

#### Commit 32
- [ ] 范围：让 `keywords` 作为 sparse 补充输入
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：keywords 增强 sparse 命中，不替换原 query
- [ ] 提交：`提交 32：接入关键词增强稀疏检索`

#### Commit 33
- [ ] 范围：实现 hybrid candidate payload
- [ ] 文件：`backend/app/models/knowledge_retrieval.py`、`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：dense/sparse 候选统一格式
- [ ] 提交：`提交 33：统一混合检索候选结构`

#### Commit 34
- [ ] 范围：增加 global bias mode：`balanced/semantic_bias/keyword_bias`
- [ ] 文件：`backend/app/core/config.py`、`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：切换 bias mode 后权重生效
- [ ] 提交：`提交 34：加入检索偏向总开关`

#### Commit 35
- [ ] 范围：固化 `faq_low_cost/standard/high_recall` 三档 profile
- [ ] 文件：`backend/app/core/config.py`、`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：每档 profile 的候选规模符合预期
- [ ] 提交：`提交 35：固化检索档位配置`

### Wave 8: RRF 与 Rerank

#### Commit 36
- [ ] 范围：实现 RRF merge
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：`rank_constant=60` 与候选数分离
- [ ] 提交：`提交 36：实现混合候选 RRF 融合`

#### Commit 37
- [ ] 范围：新增 `RerankService` 基础骨架
- [ ] 文件：`backend/app/services/rerank_service.py`、`backend/tests/test_rerank_service.py`
- [ ] 测试：rerank service typed interface
- [ ] 提交：`提交 37：新增重排服务骨架`

#### Commit 38
- [ ] 范围：接入 rerank，默认输入 30~50
- [ ] 文件：`backend/app/services/rerank_service.py`、`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_rerank_service.py`
- [ ] 测试：默认只读前 30~50 条
- [ ] 提交：`提交 38：接入默认重排流程`

#### Commit 39
- [ ] 范围：限制 `high_recall` rerank 默认 50、最大 80
- [ ] 文件：`backend/app/core/config.py`、`backend/app/services/rerank_service.py`、`backend/tests/test_rerank_service.py`
- [ ] 测试：高召回输入上限生效
- [ ] 提交：`提交 39：限制高召回重排上限`

#### Commit 40
- [ ] 范围：实现自动升档后自动降回默认 profile
- [ ] 文件：`backend/app/vectorstore/milvus_client.py`、`backend/tests/test_milvus_client.py`
- [ ] 测试：高召回不粘住整个会话
- [ ] 提交：`提交 40：实现单请求临时升档机制`

### Wave 9: RAG Chain 与 History Lookup

#### Commit 41
- [ ] 范围：重构 `rag_chain.py` 输入输出，接入 rewrite + ACL + hybrid
- [ ] 文件：`backend/app/chains/rag_chain.py`、`backend/tests/test_rag_chain.py`
- [ ] 测试：返回 retrieval payload 而非旧 `documents/sources`
- [ ] 提交：`提交 41：重构知识检索主链路`

#### Commit 42
- [ ] 范围：把 `history_lookup` 接到 rag chain
- [ ] 文件：`backend/app/chains/rag_chain.py`、`backend/tests/test_rag_chain.py`
- [ ] 测试：显式查询旧版/作废制度可命中历史数据
- [ ] 提交：`提交 42：接入历史版本查询模式`

#### Commit 43
- [ ] 范围：固化兜底顺序：rewrite retry -> 升档 -> HyDE -> 保守回答
- [ ] 文件：`backend/app/chains/rag_chain.py`、`backend/tests/test_rag_chain.py`
- [ ] 测试：fallback 顺序严格一致
- [ ] 提交：`提交 43：固化检索兜底顺序`

#### Commit 44
- [ ] 范围：接入 HyDE 白名单
- [ ] 文件：`backend/app/services/query_rewrite_service.py`、`backend/app/chains/rag_chain.py`、`backend/tests/test_query_rewrite_service.py`
- [ ] 测试：仅人事/财务/合规/制度/合同类触发 HyDE
- [ ] 提交：`提交 44：接入受控假设文档扩写`

#### Commit 45
- [ ] 范围：统一低召回/低置信度判定
- [ ] 文件：`backend/app/chains/rag_chain.py`、`backend/tests/test_rag_chain.py`
- [ ] 测试：merge `<5`、rerank `<3` 触发兜底
- [ ] 提交：`提交 45：固化低召回与低置信度判定`

### Wave 10: 引用、日志、节点、接口、文档

#### Commit 46
- [ ] 范围：生成 citation payload 与 `section_path` 前端回退文案
- [ ] 文件：`backend/app/chains/rag_chain.py`、`backend/tests/test_rag_chain.py`
- [ ] 测试：无 `section_path` 时回退为 `source_file · 第N片段`
- [ ] 提交：`提交 46：完善引用载荷与回退文案`

#### Commit 47
- [ ] 范围：新增 `RetrievalDebugService`
- [ ] 文件：`backend/app/services/retrieval_debug_service.py`、`backend/tests/test_retrieval_debug_service.py`
- [ ] 测试：记录 dense/sparse/RRF/rerank 分数与 retry 次数
- [ ] 提交：`提交 47：新增检索调试日志服务`

#### Commit 48
- [ ] 范围：新增 `RetrievalAuditService`
- [ ] 文件：`backend/app/services/retrieval_audit_service.py`、`backend/tests/test_retrieval_audit_service.py`
- [ ] 测试：记录 user_roles/client_ip/blocked_doc_ids，敏感查询脱敏
- [ ] 提交：`提交 48：新增检索审计日志服务`

#### Commit 49
- [ ] 范围：改造 `knowledge_rag_node.py`、`grader_node.py` 与知识接口
- [ ] 文件：`backend/app/nodes/knowledge_rag_node.py`、`backend/app/nodes/grader_node.py`、`backend/app/api/routes/knowledge.py`、`backend/tests/test_knowledge_rag_node.py`
- [ ] 测试：节点与路由适配新 payload
- [ ] 提交：`提交 49：接入新知识检索节点链路`

#### Commit 50
- [ ] 范围：补 README / OpenSpec 对应实现说明，跑回归测试，收尾
- [ ] 文件：`README.md`、`backend/tests/...`
- [ ] 测试：局部测试 + `make test-backend`
- [ ] 提交：`提交 50：完善企业知识库升级文档与回归测试`

## 3. 局部测试建议

- metadata / migration：
  - `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_knowledge_models.py backend/tests/test_metadata_migration_service.py -q`
- ingestion：
  - `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_knowledge_ingestion_service.py -q`
- ACL：
  - `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_access_policy_service.py -q`
- rewrite：
  - `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_query_rewrite_service.py -q`
- vectorstore / hybrid / rerank：
  - `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_milvus_client.py backend/tests/test_rag_chain.py backend/tests/test_rerank_service.py -q`
- 全量后端：
  - `make test-backend`

## 4. 风险提醒

- 这是大范围后端重构，不能一口气大改 `knowledge_service.py`
- ACL、history lookup、fallback 顺序必须始终由测试锁住
- 所有低置信度与采样/日志策略都要通过 config 控制，不要写死到业务代码里
- 任何时候都不能让本地回退绕过 ACL

## 5. 首波执行顺序

如果直接开始实现，按下面顺序最稳：

1. Commit 1-5：metadata + migration
2. Commit 6-15：ingestion
3. Commit 16-25：ACL + unified filter
4. Commit 26-35：rewrite + sparse/hybrid
5. Commit 36-45：RRF + rerank + history lookup
6. Commit 46-50：citation + logs + node integration + docs
