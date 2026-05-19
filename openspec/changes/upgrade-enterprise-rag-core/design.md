# 企业知识库 RAG 核心升级（Milvus 保留版）— 设计文档

## Context

当前项目已经有一条基础知识库链路：

- 上传文档：`backend/app/api/routes/knowledge.py`
- 文档管理与切分：`backend/app/services/knowledge_service.py`
- 向量库与本地回退：`backend/app/vectorstore/milvus_client.py`
- RAG 调用：`backend/app/chains/rag_chain.py`
- LangGraph 节点：`knowledge_rag_node.py`、`grader_node.py`

现状更像“知识库 demo”：

- `KnowledgeService` 用 `UnstructuredFileLoader` + `RecursiveCharacterTextSplitter`
- chunk 固定 `800/150`
- metadata 只有 `doc_id/source_file/page_num/department/upload_time/doc_type`
- Milvus 路径是 `max_marginal_relevance_search`
- 失败时回退到本地词法重叠搜索
- 没有 query rewrite、hybrid retrieval、rerank、状态版本过滤、访问审计

这意味着：系统能回答一部分问题，但不能稳定支持企业真实使用场景。

## Goals

- 在不更换 `Milvus` 的前提下，把知识库升级成 2026 通用 RAG 架构
- 一期必须覆盖：ingestion、metadata、ACL、query rewrite、hybrid retrieval、rerank、citations、audit、debug
- 文档状态和版本进入检索主链路，而不是回答后再补救
- 让初学者只看文档也能知道“每一层该做什么、怎么测、哪里容易错”

## Non-Goals

- 本次不更换向量库，不改成 `pgvector` / `Qdrant`
- 本次不做完整多租户 IAM 系统
- 本次不做复杂审批流
- 本次不做 UI 级企业知识后台
- 本次不做自动化离线评测平台，但会预留数据结构

## 官方依据

以下设计不是拍脑袋，是对齐当前主流官方资料后的收敛方案：

- Milvus 官方文档已把 `Hybrid Search`、`Filtered Search`、`Reranking`、`BM25/full-text search` 作为标准能力：
  - https://milvus.io/docs/hybrid_search_with_milvus.md
  - https://milvus.io/docs/overview.md
  - https://milvus.io/docs/id/v2.5.x/filtered-search.md
- Azure AI Search 官方文档明确说明 hybrid query 用 `RRF` 融合，并强调 `1 / (rank + k)` 中的 `k` 是算法常数，常见值接近 `60`，不是候选数：
  - https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
- Query rewrite 在近两年 RAG 研究里已是常见前置增强手段：
  - https://arxiv.org/abs/2305.14283
  - https://arxiv.org/abs/2411.13154

## Target Architecture

```text
用户 query
   |
   v
Query Rewrite
   |
   v
Access Policy Resolver ------------------------------+
   |                                                  |
   v                                                  |
Hybrid Retrieval                                      |
  |- Dense search (Milvus dense vector)              |
  |- Sparse search (Milvus BM25 / sparse field)      |
  |- Scalar filter (ACL + status + version)          |
   |                                                  |
   +--> Low-recall fallback / retry ------------------+
   |
   v
RRF Merge
   |
   v
Rerank
   |
   v
Citation Pack Builder
   |
   v
Grounded Answer Generation
   |
   +--> Debug Trace
   +--> Audit Log
```

## Layer Responsibilities

### 1. Ingestion Layer

职责：

- 接收上传的原始文档
- 解析文本
- 生成文档元数据
- 切分 chunk
- 为 dense / sparse 检索准备索引输入

建议拆成独立服务：

- `KnowledgeIngestionService`
- `DocumentParser`
- `ChunkingStrategyResolver`

不要再把“上传、元数据写入、切分、重建索引”都塞在一个服务里。现有 `KnowledgeService` 职责过重，后面只会越来越难调。

首版 chunking 默认值直接定死，避免实现时每个人各自理解：

- 默认：`512 tokens + 128 overlap`
- 这不是“行业唯一标准”，而是本项目首版的工程默认值
- 选择它的原因是：比当前 `800/150` 更利于制度类文档的精细引用、ACL/version 过滤和 rerank
- 只有在文档类型明确需要更大上下文时，才允许通过 `ChunkingStrategyResolver` 覆盖

允许覆盖默认切分的首版文档类型范围也直接定死：

- 合同 / 协议类长条款文档
- 表格型制度附件
- 流程表单 / 审批模板
- 超短通知 / 公告

除以上类型外，默认不允许随意改动切分标准。

token 统计口径必须统一，否则同样的“512 tokens”会被切成不同大小：

- 首版统一使用 `tiktoken` 作为 token 计数器
- ingestion、重建索引、测试样例都必须复用这同一套计数口径

`section_path` 不是凭空生成的，它依赖解析器拿到标题层级。因此 ingestion 必须明确一条要求：

- 解析器能提取标题层级时，必须写入 `section_path`
- 提取不到标题时，`section_path` 可以为空，但必须回退到 `source_file + chunk_index/page_num` 的引用方式

### 2. Metadata Policy Layer

职责：

- 管理文档状态
- 管理版本
- 管理可见范围
- 管理责任人、更新时间、有效期

文档级字段建议至少包含：

| 字段 | 说明 |
|---|---|
| `doc_id` | 文档唯一 ID |
| `title` | 文档标题 |
| `source_file` | 原始文件名 |
| `department` | 归属部门 |
| `visibility_scope` | `public / department / private / project` |
| `owner_user_id` | 私有文档所有者 |
| `project_ids` | 可访问项目组 |
| `status` | `draft / active / deprecated / archived` |
| `version` | 版本号 |
| `is_latest` | 是否最新生效版本 |
| `effective_at` | 生效时间 |
| `expires_at` | 失效时间 |
| `maintainer` | 维护责任人 |
| `upload_time` | 上传时间 |
| `checksum` | 去重与变更检测 |

chunk 级字段建议补齐：

| 字段 | 说明 |
|---|---|
| `chunk_id` | chunk 唯一 ID |
| `doc_id` | 所属文档 |
| `chunk_index` | 顺序号 |
| `section_path` | 标题路径 |
| `token_count` | chunk token 数 |
| `status` | 文档状态镜像，便于过滤 |
| `version` | 文档版本镜像 |
| `is_latest` | 文档是否最新镜像 |
| `visibility_scope` | 权限镜像 |
| `department` | 权限镜像 |

`checksum` 的用途要写死：

- 检测重复上传，而不是只按文件名判断
- 检测文档内容是否真的变更
- 作为是否需要重建索引和失效旧 chunk 的依据之一

文档元数据默认赋值规则也要直接写死：

- 新文档默认 `version=v1.0`
- 未显式传 `effective_at` 时，默认“上传即生效”
- 若未设置 `expires_at`，表示长期有效
- 旧数据迁移时，若已有 `department`，默认 `visibility_scope=department`
- 仅在历史数据连 `department` 都缺失时，才允许降级成 `public`

### 3. Access Control Layer

职责：

- 把“当前用户能看什么”转成检索过滤条件
- 保证不该看的 chunk 根本不进入候选集

一期可见范围规则：

- `public`：所有登录用户可见
- `department`：仅用户所在部门可见
- `private`：仅 `owner_user_id` 可见
- `project`：仅属于指定 `project_ids` 的用户可见
- `admin_all_access`：`hr_admin` / `knowledge_admin` 可见全部

管理员对私有文档的规则也要定死：

- 一期默认允许 `knowledge_admin` / `hr_admin` 查看全部 `private` 文档
- 如后续需要更严格管控，再增加开关或审批流
- 首版不做“管理员默认也受私有文档限制”的复杂分支

一期明确不做完整实现，但要写进 TODO 的项目：

- 权限继承
- 临时授权
- 审批流触发权限变更

ACL 输出形式建议统一成：

```python
AccessPolicy(
    allowed_departments=["hr", "finance"],
    allowed_project_ids=["p-001", "p-007"],
    can_read_private_doc_ids=["doc-123"],
    milvus_filter='status == "active" and is_latest == true and (...)',
)
```

这样 dense、sparse、本地回退都能吃同一份权限决策。

这不是“建议”，而是强约束：

- dense 检索
- sparse / BM25 检索
- 本地词法兜底检索

三套链路必须复用同一个 `AccessPolicyResolver` 输出，不允许各写一套过滤逻辑。否则最容易出现“Milvus 主路径没问题，本地兜底却泄露权限”的隐蔽 bug。

ACL 依赖的最小用户上下文字段：

- `user_id`
- `department`
- `roles`
- `project_ids`

如果当前认证模型里还没有 `project_ids`，则本次变更需要同步补齐用户上下文结构；否则 `project` 范围无法真正落地。

这条依赖关系也要写成硬规则：

- `project_ids` 未就绪时，`project` 权限不得假装生效
- 可以保留字段和数据模型，但检索侧必须明确降级为“不启用 project scope”

文档级权限字段变更后的同步规则也要明确：

- 修改 `visibility_scope`
- 修改 `department`
- 修改 `owner_user_id`
- 修改 `status`
- 修改 `version`
- 修改 `is_latest`

以上任一字段变化时，所有关联 chunk 的镜像字段必须自动同步。

首版建议机制：

- 小批量更新：同步内联更新
- 大批量更新：异步批处理任务
- 同步未完成前，把文档标记为 `sync_pending`
- `sync_pending` 文档默认不参与检索，避免出现“文档已不可见，chunk 还可搜到”的窗口漏洞

### 4. Query Rewrite Layer

职责：

- 把用户原始提问改成更适合检索的 query
- 解决口语、省略、简称、上下文承接问题

默认规则：

- 轻量 rewrite 默认全开
- 保留原 query
- rewrite 失败时直接回退原 query
- rewrite retry 最多只允许 1 次

推荐输出：

```python
QueryRewriteResult(
    original_query="出差打车能报吗",
    rewritten_query="差旅报销制度中市内交通费是否可以报销",
    keywords=["差旅", "报销", "市内交通费"],
    strategy="light_rewrite",
)
```

`keywords` 不是装饰字段，它的用途是：

- 为 sparse/BM25 检索提供更干净的关键词输入
- 帮助保留制度名、编号、版本号、岗位级别等精确术语
- 不允许把所有 rewrite 产物无脑拼回查询，必须做去停用词和去噪

关键词提取规范也要直接定死，避免每个开发者各做一套：

- 每次最多提取 `5` 个关键词
- 至少保留 `1` 个有效关键词；提不出来时直接不产出关键词数组
- 必须剔除礼貌词、虚词和空泛动作词，例如：
  - `请`
  - `帮我`
  - `一下`
  - `这个`
  - `那个`
  - `的`
  - `了`
  - `吗`
  - `呢`
  - `啊`
  - `关于`
  - `查`
  - `看`
- 但不能误删制度名、版本号、岗位级别、实体名和编码

关键词使用方式也要统一：

- `dense retrieval` 继续使用原 query / rewritten query 做语义召回
- `keywords` 只作为 sparse/BM25 的补充输入
- `keywords` 不替换原 query，只做叠加增强

改写黑名单同样必须写死，以下内容默认禁止改写：

- 工号
- 项目编码
- 合同编号
- 制度编号
- 版本号
- 其他满足固定编码模式的字符串

如果 query 主要由这类固定编码组成，rewrite 只允许做轻量清洗，不允许语义改写。

增强规则：

- 仅在以下情况触发二次改写或 HyDE：
  - 初次召回为空
  - 召回分数过低
  - 明显是高价值问题（人事、财务、合规、制度、合同）

显式限制：

- 不让所有 query 默认走 HyDE
- 不对带精确编号的 query 乱改，比如 `V2.1`、`P3`、`OKR-2026`
- 不对工号、项目编码、合同编号这类固定编码做语义改写

### 5. Hybrid Retrieval Layer

职责：

- 同时执行 dense 和 sparse 两路召回
- 使用统一过滤条件
- 输出可比较的候选集

Milvus 层建议：

- dense：现有 embedding 向量字段
- sparse：BM25 或 sparse embedding 字段
- filter：把 ACL + status + version 一起下推

这层不要再混进生成逻辑，只负责“找候选”。

无论是否走 Milvus，**本地回退搜索都必须执行同一套过滤**：

- ACL 过滤
- `status=active`
- `is_latest=true`
- `effective_at / expires_at` 有效期判断

否则 Milvus 挂掉时，本地回退会直接变成越权泄露通道。

### 6. Merge + Rerank Layer

职责：

- 先融合 dense / sparse 候选
- 再把最能回答问题的 chunk 排到前面

融合建议：

- 默认 `RRF`
- `rank_constant` 默认 `60`
- 候选数量与 RRF 常数分开配置

Rerank 建议：

- 输入不是无限放大
- 默认只对融合后的前 `30~50` 条做 rerank
- 输出 Top `3~5` 给生成

检索 profile 建议如下：

| Profile | Dense | Sparse | Merge 后保留 | Rerank 输出 | 适用场景 |
|---|---:|---:|---:|---:|---|
| `faq_low_cost` | 20 | 20 | 30 | 3 | 简短 FAQ |
| `standard` | 30~50 | 30~50 | 30~50 | 3~5 | 默认企业问答 |
| `high_recall` | 50~80 | 50~80 | 50~80 | 5 | 复杂制度、长文档 |

权重策略：

- 制度、编号、模板类问题：提高 sparse 重要性
- 经验、流程解释、口语提问：提高 dense 重要性

除场景自动判断外，后台还要保留一个简易总开关，方便运营和排障时快速调偏向：

- `balanced`
- `semantic_bias`
- `keyword_bias`

这不是替代自动策略，而是一个全局偏向系数，用于在不改代码的情况下快速微调 dense / sparse 整体权重。

高召回模式再补一条硬限制：

- rerank 默认只读取前 50 条融合候选
- 只有显式打开高召回扩展时，rerank 输入才允许放大到 80
- 首版不允许 rerank 直接吃 100 条候选

### 6.1 Performance Budget

这里写的是**首版基准目标**，不是“任何环境都必须满足”的绝对承诺。必须在固定数据量、固定硬件、固定模型条件下测 `p50/p95`，而不是直接把某个毫秒数字当真理。

本节性能预算默认基于以下 benchmark 前提：

- 语料规模：`<= 100,000 chunks`
- rerank 运行在 GPU 部署或等价加速环境
- dense embedding、sparse 检索、rerank 模型版本固定
- 单次请求不跨区域调用外部高延迟服务

首版建议跟踪：

- query rewrite：`p95 <= 120ms`
- dense+sparse retrieval：`p95 <= 150ms`
- RRF merge：`p95 <= 20ms`
- rerank（输入 30~50 候选）：`p95 <= 200ms`
- 检索侧总耗时（不含最终大模型生成）：`p95 <= 450ms`

如果后续 benchmark 明显不符，应先调整 profile、候选数量和 rerank 输入规模，而不是直接提高所有超时阈值。

### 7. Grounded Answer Layer

职责：

- 只基于通过 ACL 和 rerank 后的内容回答
- 回答时附引用
- 引用必须可追溯到 chunk/document

输出结构建议：

```python
KnowledgeAnswerPayload(
    answer="...",
    citations=[
        {
            "doc_id": "doc-123",
            "chunk_id": "chunk-9",
            "source_file": "差旅报销制度-v2.1.pdf",
            "section_path": "第三章 / 市内交通",
            "version": "v2.1",
        }
    ],
    retrieval_debug={...},
)
```

### 8. Observability Layer

职责：

- 给开发者定位问题
- 给企业做访问审计
- 给后续评测预留原始数据

日志不能混成一锅，首版直接拆成三类：

1. `retrieval_debug_trace`
   - 面向开发排障
   - 记录检索链路细节
   - 默认只在 `dev / staging` 全量开启
   - `prod` 默认走精简版或采样版

2. `access_audit_log`
   - 面向合规、权限审计、越权追踪
   - 生产环境必须保留
   - 不依赖开发调试开关

3. `user_behavior_log`
   - 面向产品分析
   - 只记录必要行为事件
   - 不混入检索内部细节

其中至少记录这些字段：

1. `retrieval_debug_trace`
   - 原 query
   - rewrite query
   - ACL 过滤表达式
   - dense 候选 ID / dense score
   - sparse 候选 ID / sparse score
   - RRF 结果 / rrf score
   - rerank 结果 / rerank score
   - 最终引用
   - low-confidence 判定结果
   - rewrite retry 次数

2. `access_audit_log`
   - 用户 ID
   - 用户角色
   - client IP
   - query
   - 命中的文档 ID
   - 被拦截的文档 ID 列表
   - deny reason
   - request start/end time
   - timestamp

3. `user_behavior_log`
   - query 类型
   - 是否命中知识库
   - 是否触发 rewrite / history lookup
   - 会话维度事件

4. `user-facing trace`
   - “已改写查询”
   - “已检索到 32 条候选”
   - “已筛选 4 条高相关片段”

环境开关和保存策略也要定死，避免线上把数据库打爆：

| 日志类型 | dev/staging | prod 默认 | 默认保留时长 | 说明 |
|---|---|---|---|---|
| `retrieval_debug_trace` | 全量详细 | 精简或采样 | 7 天 | 用于排障，不做长期全量存储 |
| `access_audit_log` | 开启 | 全量开启 | 180 天 | 用于审计、风控、越权追踪 |
| `user_behavior_log` | 开启 | 开启 | 30 天 | 用于产品分析 |

这里的保留时长是**项目默认值**，不是法律真值；后续如果企业合规要求不同，应改成配置项覆盖。

日志访问权限也必须分层：

- 普通员工：不可查看 `retrieval_debug_trace`
- 普通员工：不可直接查看 `access_audit_log`
- `knowledge_admin` / 平台运维 / 开发维护人员：按后台权限查看对应日志
- 前端用户侧只允许看到 `user-facing trace` 级别的信息，不能看到内部检索分数和过滤表达式

敏感内容脱敏规则：

- 命中薪资、个人隐私、涉密制度等敏感场景时
- `access_audit_log` 保留必要审计信息，但 query 和 snippet 必须脱敏或摘要化
- `retrieval_debug_trace` 在生产环境不得落完整敏感正文，优先记录文档 ID、chunk ID、分数和脱敏摘要

低置信度与重试的首版规则也要写死，避免实现时没人知道怎么判：

- `rewrite_retry_max = 1`
- merge 后候选 `< 5`，判定为低召回
- 最终 rerank 可用候选 `< 3`，判定为低置信度
- rerank score 阈值使用“模型配置项 + benchmark 校准值”，不在设计文档里拍脑袋写成跨模型通用绝对值

也就是说：

- 条数阈值首版写死
- 分数阈值首版必须校准后配置，不允许开发各自随手写

## Failure and Fallback Rules

### 候选为空

处理顺序：

1. 检查 ACL 后是否已空
2. 如果是权限过滤后为空，直接回“暂无可见资料或没有权限”
3. 如果是检索本身为空，做一次轻量 rewrite retry
4. 还为空，再按 `faq_low_cost -> standard -> high_recall` 的顺序只升级一档
5. 仍为空，走保守回答，不硬编制度

### 历史版本 / 作废文档主动查询

默认规则仍然是：

- `deprecated`
- 已过期
- 非 `is_latest`

默认不进入候选集。

但要补一个显式入口：

- 当用户明确表达“旧版本 / 历史版本 / 作废制度 / 2024 年旧规则 / v1.0”这类查询意图时
- 系统允许进入 `history_lookup` 模式
- 在该模式下可以放宽 `is_latest=true`、`deprecated`、已过期等默认过滤
- 但必须在回答中明确标注“历史版本 / 非现行制度”

多重兜底动作的先后顺序也要写死，避免实现时每个人理解不同：

1. 首次执行：`light_rewrite + 当前默认 profile`
2. 若低召回：对 rewrite 重试 1 次
3. 若仍低召回：只升级 1 档 retrieval profile
4. 若仍低召回且命中 HyDE 白名单：执行 1 次 HyDE
5. 若 query 明确是历史查询：以上步骤在 `history_lookup` 模式下执行
6. 仍失败：返回保守回答，不硬答

自动升档后也必须自动降回默认，避免系统长期挂在高成本模式：

- profile 升级只在“当前这一次请求”内生效
- 请求结束后，下一个请求重新从默认 profile 开始
- 不允许因为上一条请求进了 `high_recall`，后续整段会话都一直停在高成本模式

### 候选太少

规则：

- 如果 dense 和 sparse 合并后小于阈值，触发二次 rewrite
- 如果问题包含精确编号，不允许盲目扩词，只能轻度放宽

### 文档版本冲突

规则：

- 同一 `doc_id family` 只优先保留 `is_latest=true`
- 如果用户明确问旧版本，允许回查指定版本
- 默认不把过期制度和现行制度同时送给生成

### 权限冲突

规则：

- 权限过滤永远在检索前
- 任何 chunk 只要 ACL 不满足，不能进入 merge / rerank

## Debug Playbook

这部分是给后续开发直接照着排查的。

### 1. 用户说“明明文档里有，为什么没答出来”

按顺序看：

1. 看 `rewrite_result`
   - 有没有把 query 改坏
2. 看 `access_policy`
   - 文档是不是被部门或项目权限挡掉了
3. 看 `status/version filter`
   - 文档是不是 `deprecated` 或不是最新版本
4. 看 `dense_candidates`
   - 语义召回有没有命中
5. 看 `sparse_candidates`
   - 关键词召回有没有命中
6. 看 `rrf_merged`
   - 是不是融合时被挤掉
7. 看 `reranked_top`
   - 是不是 rerank 排名太低被截断

### 2. 用户说“答的是旧制度”

先查：

- `status`
- `version`
- `is_latest`
- `effective_at`
- `expires_at`

如果旧制度能进候选集，说明 metadata 过滤做错了，不是模型问题。

### 3. 用户说“没权限的文档被看到了”

先查：

- 当前用户角色
- `AccessPolicyResolver` 输出
- Milvus filter 表达式
- 本地回退路径有没有也执行同样过滤

只要有一条检索路径绕过 ACL，就是后端 bug。

### 4. 用户说“为什么延迟这么高”

先拆时延：

- rewrite 用时
- dense 检索用时
- sparse 检索用时
- merge 用时
- rerank 用时
- generate 用时

最常见的问题不是 Milvus，而是：

- rewrite 过重
- rerank 候选过多
- 所有 query 都走高召回 profile

### 5. 上传流程卡在中间怎么办

上传拆成多步后，必须有失败回滚与单步重试策略：

- 原始文件保存成功，但解析失败：
  - 保留原始文件
  - 标记 ingestion 状态为 `parse_failed`
  - 允许管理员不重新上传文件，直接重试解析
- chunk 生成成功，但索引写入失败：
  - 不发布半成品 chunk 到正式检索集合
  - 标记为 `index_failed`
  - 允许从索引步骤继续重试
- 任一步骤失败，都不能留下“用户可检索，但数据不完整”的中间态

### 6. section_path 为空时前端显示什么

如果解析不到标题层级，前端不能显示空白引用。

首版统一回退显示：

- `source_file · 第 {chunk_index} 片段`

如果只有页码，则显示：

- `source_file · 第 {page_num} 页片段`

### 7. 旧数据迁移怎么做

一期不采用“用户查到哪条就临时补哪条”的惰性迁移，因为这会导致线上行为不一致、难排障。

首版统一采用：

- 后台一次性迁移脚本
- 启动前或发版时执行
- 迁移完成后再切换到新检索链路

如果存在未迁移文档：

- 标记为 `migration_pending`
- 默认不进入新检索链路

## Phase 1 Scope

这轮必须完成：

- 文档 metadata 升级
- query rewrite 轻量版
- dense + sparse hybrid retrieval
- RRF merge
- rerank
- 前置 ACL
- 状态 / 版本过滤
- 引用回答
- audit log
- debug trace

## Deferred TODOs

这些必须写进文档，但不放进一期实现承诺：

- ACL 权限继承
- 临时授权
- 审批流驱动 ACL
- 自动文档失效提醒
- 索引异步重建调度
- 检索离线评测面板
- 反馈学习型 query rewrite
- semantic cache
- 按 heading / 表格 / 附件类型的高级 chunking

## Acceptance Criteria

- 普通员工检索不到无权限文档
- 默认不会引用 `deprecated` 或过期版本
- 口语化制度问题召回质量明显优于当前单路方案
- 回答必须带可追溯引用
- 调试时能还原“query 是怎么被改写、怎么被过滤、怎么被召回、怎么被重排”的完整过程
