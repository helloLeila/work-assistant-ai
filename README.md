# 企业智能办公助手

企业智能办公助手是一个面向企业内部场景的 AI 办公平台，提供统一的对话入口，覆盖知识检索、薪酬查询、个人信息查询和商旅代办四类核心业务。

## 核心能力

- 企业知识库检索：支持文档上传、切分、索引构建、检索问答和引用溯源
- 薪酬查询：按员工、经理、HR 管理员角色控制访问范围
- 个人信息查询：对手机号、身份证等敏感字段自动脱敏
- 商旅代办：从自然语言中抽取出行信息，并可转发到第三方商旅接口
- 流程可扩展：基于 LangGraph 编排节点，新业务可按节点方式接入

## 技术架构

- 前端：Vue 3 + Vite + Tailwind CSS
- 后端：FastAPI + SSE 流式输出
- 模型层：Minimax 2.7/ OpenAI 兼容模型
- AI 编排：
  - LangChain 负责检索、提示词、输出解析、工具调用
  - LangGraph 负责状态、路由、条件边、重试、Checkpoint
- 数据层：
  - Milvus：知识库向量检索，支持 HNSW 索引与部门维度隔离
  - PostgreSQL：结构化业务数据主后端
  - SQLite：本地开发样例回退
  - Redis：缓存与会话扩展预留
- 可观测性：LangSmith

## 架构分层

```text
Vue 前端
  ├─ 登录页
  ├─ 智能工作台
  └─ 知识库管理页
        │
        ▼
FastAPI 接口层
  ├─ 认证
  ├─ 聊天流式接口
  ├─ 知识库接口
  └─ 系统概览接口
        │
        ▼
LangGraph 编排层
  ├─ 意图识别
  ├─ 权限判断
  ├─ 知识检索
  ├─ 商旅代办
  ├─ 可信度检查
  └─ 回答生成
        │
        ▼
LangChain 能力层
  ├─ Retriever
  ├─ Prompt
  ├─ OutputParser
  ├─ Tool
  └─ Embeddings
        │
        ▼
Milvus / PostgreSQL / Redis / 外部商旅系统
```

## 项目目录

```text
tongtong/
├── backend/
│   ├── app/
│   │   ├── agents/          # LangGraph 主图
│   │   ├── api/             # FastAPI 路由
│   │   ├── chains/          # LangChain 链能力
│   │   ├── core/            # 配置、安全、日志、生命周期
│   │   ├── models/          # Pydantic 模型
│   │   ├── nodes/           # LangGraph 节点
│   │   ├── services/        # 业务服务
│   │   ├── tools/           # 工具封装
│   │   └── vectorstore/     # Milvus 与本地回退检索
│   ├── data/                # 样例数据、上传文件、索引和历史记录
│   └── tests/               # 后端测试
├── frontend/
│   └── src/
│       ├── components/      # 复用组件
│       ├── composables/     # 可复用前端逻辑
│       ├── lib/             # API 封装
│       ├── pages/           # 页面
│       ├── router/          # 路由守卫
│       ├── stores/          # 登录状态
│       └── types/           # 前端类型定义
├── docs/
│   └── 开发手册.md
├── docker-compose.yml
├── requirements.txt
├── Makefile
├── backend/.env.example
└── frontend/.env.example
```

## 快速启动

### 1. 准备环境变量

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

这里开始就按严格前后端分离来：

- `backend/.env` 只给后端用
- `frontend/.env` 只给前端用

`OPENAI_API_KEY` 可以暂时留空。留空时系统会自动使用本地回退逻辑，方便先把整套流程跑起来。

如果你现在只有 MiniMax，没有 OpenAI 官方 Key，也可以直接使用 OpenAI 兼容接法：

```env
OPENAI_API_KEY=你的 MiniMax Key
OPENAI_BASE_URL=https://api.minimaxi.com/v1
OPENAI_MODEL=MiniMax-M2.7
OPENAI_EMBEDDING_MODEL=
```

这里把 `OPENAI_EMBEDDING_MODEL` 留空，是为了避免在没有可用 Embedding 接口时强行初始化向量模型。这样知识库会自动退回到本地词法检索，聊天链路仍然可以跑通。

### 2. 启动基础设施

```bash
docker compose up -d
```

会启动这些服务：

- PostgreSQL
- Redis
- Milvus
- etcd
- minio
- backend

如果你只想本地调试前后端，也可以只启动数据库相关服务：

```bash
docker compose up -d postgres redis etcd minio milvus
```

### 3. 本地启动后端

首次准备虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

之后**日常启动只需要一条命令**（不需要再 `source` 激活，Makefile 直接调用 `.venv/bin/uvicorn`）：

```bash
make dev-backend
```

看到下面这行才算成功：

```text
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

后端地址：

- 健康检查：`http://localhost:8000/api/health`
- 系统概览：`http://localhost:8000/api/overview`

#### 常见启动问题

**1. `ERROR: [Errno 48] Address already in use`**

8000 端口被旧的 uvicorn 进程占着了（多发于 `--reload` worker 没被父进程一起带走时）。一把梭：

```bash
make kill-backend && make dev-backend
```

`make kill-backend` 会同时清掉端口占用进程和遗留的 uvicorn 子进程。

**2. 启动卡在 `Waiting for application startup.` 不动**

通常是 lifespan 阶段调用 Embedding 接口超时。如果你用的模型供应商（例如 MiniMax 国内版）**没有提供 OpenAI 兼容的 Embedding 模型**，请把 `backend/.env` 里的 `OPENAI_EMBEDDING_MODEL` 留空，知识库会自动回退到本地词法检索。改完 `backend/.env` 必须重启后端才会生效（`get_settings()` 有缓存）。

**3. 模型名 404 / 一直报错**

OpenAI 兼容接口的 `OPENAI_MODEL` **大小写敏感**。MiniMax 的正确写法是 `MiniMax-M2.7`，写成 `minimax-m2.7` 会 404。

**4. 改了 `backend/.env` 但行为没变**

后端没有重启。`Ctrl+C` 停掉旧进程后重新 `make dev-backend`。

### 4. 本地启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：

- `http://localhost:5173`

## 体验账号

所有样例账号默认密码相同：`RuiRui123!`

| 角色 | 用户名 | 姓名 | 说明 |
| --- | --- | --- | --- |
| 员工 | `li.wei` | 李伟 | 可查本人薪酬与个人信息 |
| 员工 | `zhao.qin` | 赵琴 | 可查本人薪酬与个人信息 |
| 经理 | `zhang.min` | 张敏 | 可查看本人及直属下属信息 |
| HR 管理员 | `wang.hr` | 王静 | 可查看全量薪酬与人事信息 |
| 知识库管理员 | `chen.kb` | 陈楠 | 可管理知识库文档 |

## 推荐体验路径

登录后可以直接尝试下面几类问题：

- 知识库：`帮我总结公司的差旅报销标准，并列出关键限制条件。`
- 薪酬：`请查询我本月的薪酬总包。`
- 个人信息：`帮我查看我的合同到期日、剩余年假和部门信息。`
- 商旅代办：`下周二帮我预订上海到深圳的商务舱，2位乘客。`

## 商旅接口接入

如果你已经有第三方商旅系统，可以在 `backend/.env` 中配置：

```env
TRAVEL_API_BASE_URL=https://travel.example.com
TRAVEL_API_PATH=/orders
TRAVEL_API_AUTH_TOKEN=your-token
TRAVEL_API_TIMEOUT_SECONDS=10
TRAVEL_API_FALLBACK_ENABLED=true
```

配置后，商旅模块会优先把结构化结果转发给外部接口；如果接口不可用，并且 `TRAVEL_API_FALLBACK_ENABLED=true`，系统会自动回退到本地订单确认逻辑。

如果你现在还没有真实商旅接口地址，`TRAVEL_API_BASE_URL` 直接留空即可，项目会默认走本地下单回退，不影响演示和开发。

## 开发命令

```bash
make backend-install     # 安装后端依赖
make dev-backend         # 启动后端（venv 内 uvicorn，无需手动激活）
make kill-backend        # 强杀占用 8000 端口的后端进程
make frontend-install    # 安装前端依赖
make dev-frontend        # 启动前端
make test                # 运行后端测试
make build-frontend      # 校验前端构建
make compose-up          # 启动基础设施（PostgreSQL / Milvus / etcd / minio / Redis）
```

## 当前实现说明

- LangGraph 已接通意图识别、权限校验、知识检索、商旅代办、回答生成和可信度检查链路
- LangChain 已用于 Prompt、Retriever、OutputParser、Tool、Embeddings 等节点内部能力
- Milvus 不可用时，会自动退回到本地词法检索，保证开发环境可运行
- PostgreSQL 不可用时，会自动退回到本地 SQLite 样例库，保证业务链路不断

### 企业知识库 RAG 核心升级（50 Commit）

知识检索链路已完成企业级 RAG 架构升级，检索流程统一为：
**Query Rewrite → ACL → Hybrid Retrieval（dense + sparse）→ RRF 融合 → Rerank 精排 → Citation 打包 → Grounded Answer**

核心能力与实现状态：

| 阶段 | 实现文件 | 说明 |
|------|----------|------|
| Query Rewrite | `app/services/query_rewrite_service.py` | 轻量规则改写、关键词提取（上限 5 个，停用词过滤）、改写黑名单（工号/合同号/项目编码）、改写重试（最多 1 次）、HyDE 白名单 |
| ACL | `app/services/access_policy_service.py` | 统一访问策略解析，支持 public / department / private / project 权限范围，管理员可查看 private 文档 |
| Hybrid Retrieval | `app/vectorstore/milvus_client.py` | dense（Milvus 向量检索）+ sparse（本地 BM25），统一 ACL 过滤，支持三档 profile（faq_low_cost / standard / high_recall）与全局 bias 模式（balanced / semantic_bias / keyword_bias） |
| RRF 融合 | `app/vectorstore/milvus_client.py` | rank_constant=60，候选按 chunk_id 去重 |
| Rerank | `app/services/rerank_service.py` | 基于分数的近似重排，standard 档默认 30~50 输入，high_recall 档最大 80 |
| Fallback | `app/chains/rag_chain.py` | 低召回（< 5）时依次触发：rewrite retry → 临时升档（high_recall，单请求自动降回）→ HyDE 白名单检测 → 保守回答；低置信度（< 3）时返回保守回答 |
| History Lookup | `app/chains/rag_chain.py` | 查询含"旧版本/历史版本/作废制度"等关键词时自动开启，允许命中 deprecated 文档 |
| Citation | `app/chains/rag_chain.py` | 检索结果打包为 CitationItem（doc_id / chunk_id / source_file / section_path / snippet），section_path 缺失时回退为"source_file · 第 N 片段" |
| Debug Trace | `app/services/retrieval_debug_service.py` | 记录各阶段中间结果（dense / sparse / RRF / rerank 候选、改写重试次数、fallback 动作、history_lookup 状态） |
| Audit Log | `app/services/retrieval_audit_service.py` | 记录用户身份、请求上下文、匹配/阻挡文档、拒绝原因；查询含身份证号/手机号/工号时自动脱敏 |
| 节点整合 | `app/nodes/knowledge_rag_node.py` | 已接入新链路，返回 KnowledgeAnswerPayload；同时保留 draft_answer / sources / retrieved_docs 供旧节点兼容 |
| 接口 | `app/api/routes/knowledge.py` | 新增 `POST /api/knowledge/search`，直接返回结构化 KnowledgeAnswerPayload（含 answer、citations、retrieval_debug） |

**兼容性说明**：`run_rag_chain` 保留旧接口签名作为兼容层，`knowledge_rag_node` 与 `grader_node` 同时支持新旧 payload，过渡期内现有 LangGraph 工作流无需改动。

## 文档

- 面向初学者的说明见 [docs/开发手册.md](/Users/leila/Documents/coding/tongtong/docs/开发手册.md)
- 后端单独启动说明见 [docs/后端启动手册.md](/Users/leila/Documents/coding/tongtong/docs/后端启动手册.md)
