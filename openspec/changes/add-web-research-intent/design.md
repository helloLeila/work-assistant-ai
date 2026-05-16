## Context

`backend/app/nodes/web_search_node.py` 目前是 stub:无论用户问什么,都返回"知识库没有相关材料"的固定文本。`intent_chain.KEYWORD_RULES` 里所有写作类(生成/写/总结/面试)都归到 `chitchat`,不区分是否需要外部素材,模型只能凭训练数据回答。

我们已经注册 Bocha Web Search(`api.bocha.cn`):

- 协议:简单 REST POST,返回 JSON
- 价格:免费 1000 次/月,超出 ¥0.03/次(参考价)
- 国内直连,无 VPN
- 字段:`query` / `freshness` / `summary` / `count`

LangGraph 与 SSE 基础设施已就绪:`push_progress`、`push_trace`、`push_sources` 都已在 `core/streaming.py` 里,前端 `useChatStream.ts` 已支持 `progress` / `trace` 事件类型。

约束:
- 用户在国内,**不能依赖 Tavily/Serper**(被墙、需 VPN)
- 必须做超时降级:Bocha 慢 / 失败时不能让用户卡 30s
- 不能新增重 SDK,直接走 `httpx` 即可

## Goals / Non-Goals

**Goals:**
- 新增 `web_research_write` 意图,正确路由"今天天气""2026 AI 趋势""帮我生成 200 字 agent 总结"这类需要联网素材的请求
- 把 Bocha API 封装成一个独立 service,可单测、可 mock、可降级
- 整条链路有可观测性:用户能看到"⟳ 搜索资料 / ✓ 找到 5 条线索 / ⟳ 提炼要点 / ⟳ 生成正文"
- 失败优雅降级:Bocha 超时/出错时,自动回退到 `direct_write` 路径继续生成,不报错

**Non-Goals:**
- 不接 Tavily / Serper / Brave(国内访问问题,留作未来海外版)
- 不做搜索结果缓存(单次会话内多次问相同问题不会去重,YAGNI)
- 不做来源去重/可信度评分(v1 直接信 Bocha 排序)
- 不做"模型自己决定要不要搜"(那是 tool calling 范式,与现有三层路由架构冲突,留作后续)
- 不在 chitchat fast-path 里加任何 Bocha 调用(快速路径必须 0 ms)

## Intent Architecture: 从 5 意图到 7 意图

现有意图把"写作类"和"闲聊类"混在一个 `chitchat` 桶里，导致：
- "帮我写一段面试经验"和"你是谁"走同一条路径
- 需要联网素材的写作请求（如"2026 AI 趋势总结"）被归为纯写作，模型只能靠训练数据编造

### 拆分后的 7 意图定义

| 意图 | 覆盖场景 | 走什么节点链 | 检索源 |
|---|---|---|---|
| `knowledge` | 查企业内部制度、手册、FAQ、报销流程 | RAG → grader → generate | **企业 RAG** (Milvus/本地) |
| `salary` | 查薪酬、工资、奖金、个税 | auth → 查 DB → 结构化直出 | 业务数据库 |
| `personal` | 查年假、合同、部门、手机号 | auth → 查 DB → 结构化直出 | 业务数据库 |
| `travel` | 订机票、酒店、出差申请 | 解析参数 → 下单 → 结构化直出 | 商旅 API |
| `web_research_write` | **需要外部素材的写作/查询**：天气、新闻、趋势、实时信息 | Bocha 搜索 → planner → generate | **Bocha 联网搜索** |
| `direct_write` | **纯写作，无需外部素材**：感谢信、面试经验、润色改写 | planner → generate | 无（模型自生成） |
| `chitchat` | **纯闲聊问候**：你是谁、你好、谢谢、再见 | 固定模板直出 | 无 |
| `clarify` | 意图不明确，需要用户确认 | generate（反问句） | 无 |

### chitchat 拆分前后对比

**拆分前（现状）：**
```python
"chitchat": [
    # 写作类 + 问候类混在一起
    "生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写",
    "你是谁", "你叫什么", "你好", "您好", "嗨",
    "你能做什么", "你会什么", "怎么用", "帮助",
    "谢谢", "辛苦了", "再见", "拜拜",
    "hi", "hello",
]
```

**拆分后：**
```python
"web_research_write": ["今天", "明天", "昨天", "最新", "最近", "2026", "趋势",
                        "天气", "新闻", "查一下", "搜一下", "联网", "实时"]
"direct_write": ["生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写"]
"chitchat": ["你是谁", "你叫什么", "你好", "您好", "嗨",
              "你能做什么", "你会什么", "怎么用", "帮助",
              "谢谢", "辛苦了", "再见", "拜拜",
              "hi", "hello"]
```

## Scene Decision Flow: 什么 query 会走到哪条路

```
用户输入 query
    │
    ▼
┌─────────────────┐
│  第一层：关键词快速路径   │  ← ~0ms，覆盖80%高频场景
│  KEYWORD_RULES  │
└─────────────────┘
    │
    ├─ 命中 "薪酬/工资/奖金" ──► intent=salary ──► 权限校验 ──► 查薪酬表 ──► 结构化直出
    │
    ├─ 命中 "年假/合同/身份证" ──► intent=personal ──► 权限校验 ──► 查人事表 ──► 结构化直出
    │
    ├─ 命中 "机票/酒店/出差" ──► intent=travel ──► 解析参数 ──► 创建商旅订单 ──► 结构化直出
    │
    ├─ 命中 "制度/报销/手册/FAQ" ──► intent=knowledge ──► 企业RAG检索 ──► grader评估
    │                                                              │
    │                                            ┌─ 相关度高 ──► 用检索结果生成回答
    │                                            │
    │                                            └─ 相关度低 ──► web_search_node(Bocha补充)
    │                                                              │
    │                                            （RAG未命中时的降级补充，不是主路径）
    │
    ├─ 命中 "今天/明天/最新/2026/天气/新闻/搜一下" ──► intent=web_research_write ──► Bocha联网搜索 ──► 生成
    │  │
    │  └─ 同时命中 "生成/写/总结" ──► 平票 ──► LLM决断 ──► web_research_write 或 direct_write
    │
    ├─ 命中 "生成/写/撰写/面试/经验/总结/润色" ──► intent=direct_write ──► planner规划 ──► 生成
    │  │
    │  └─ 同时命中 "今天/最新/2026" ──► 平票 ──► LLM决断 ──► 可能升级为 web_research_write
    │
    ├─ 命中 "你是谁/你好/谢谢/再见" ──► intent=chitchat ──► 固定模板直出（零延迟）
    │
    └─ 未命中任何关键词 ──► 进入第二层

                      │
                      ▼
            ┌─────────────────┐
            │  第二层：短查询兜底   │
            │  ≤15字默认chitchat  │
            └─────────────────┘
                      │
                      ├─ "在吗"/"ok" ──► chitchat
                      │
                      └─ >15字 ──► 进入第三层

                                        │
                                        ▼
                              ┌─────────────────┐
                              │  第三层：LLM分类    │
                              │  utility小模型(1.5s) │
                              └─────────────────┘
                                        │
                                        ▼
                              模型判断 intent + confidence
                                        │
                    ├─ confidence < 0.7 且非chitchat ──► clarify（让用户确认）
                    │
                    └─ confidence ≥ 0.7 ──► 按意图走对应路径
```

### 场景对照表

| 用户Query | 关键词命中 | 意图 | 走的节点链 | 检索源 |
|---|---|---|---|---|
| "帮我查一下差旅报销制度" | 制度 | `knowledge` | RAG → grader → generate | **企业RAG** |
| "公司的年假有多少天" | 年假 | `personal` | auth → 查DB → 结构化直出 | 业务数据库 |
| "下周二深圳飞上海机票" | 机票 | `travel` | 解析 → 下单 → 结构化直出 | 商旅API |
| **"今天深圳天气怎么样"** | 今天+天气 | **`web_research_write`** | Bocha搜索 → planner → generate | **Bocha联网** |
| **"2026年AI Agent趋势"** | 2026+趋势 | **`web_research_write`** | Bocha搜索 → planner → generate | **Bocha联网** |
| **"帮我搜一下最新的React文档"** | 搜一下+最新 | **`web_research_write`** | Bocha搜索 → planner → generate | **Bocha联网** |
| "帮我生成200字面试经验" | 生成+面试+经验 | `direct_write` | planner → generate | 无 |
| **"帮我生成200字2026 AI总结"** | 生成+2026 | **平票** → LLM决断 | 取决于模型 | 可能Bocha或纯模型 |
| "你是谁" | 你是谁 | `chitchat` | 固定模板直出 | 无 |
| "帮我写一份离职申请" | 写 | `direct_write` | planner → generate | 无 |

## 企业 RAG vs Bocha 联网搜索的边界

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        内部知识 vs 外部信息 边界                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   企业 RAG (knowledge 意图)          Bocha 联网搜索 (web_research_write 意图) │
│   ─────────────────────────          ─────────────────────────────────────   │
│                                                                             │
│   查"内部"信息                        查"外部"信息                           │
│   ├── 公司制度/手册/FAQ                ├── 今天天气/新闻热点                   │
│   ├── 报销流程/标准                    ├── 2026行业趋势                       │
│   ├── 部门组织架构                     ├── 最新技术文档                       │
│   └── 内部项目文档                     └── 实时股价/汇率                       │
│                                                                             │
│   数据源：Milvus向量库 + 本地文件         数据源：Bocha搜索引擎                  │
│   检索方式：语义相似度匹配                检索方式：关键词全文搜索               │
│   回答风格：引用制度条文                  回答风格：综合多来源+提示时效性         │
│                                                                             │
│                              重叠场景                                        │
│                              ───────                                        │
│   "查一下公司最新的AI政策"                                                  │
│        │                                                                    │
│        ├── 命中 knowledge（公司）+ web_research_write（查一下/最新）         │
│        ├── 平票 → LLM决断                                                   │
│        └── 通常模型会选 knowledge（"公司"权重更高）                          │
│                                                                             │
│   "最新的劳动法对年假有什么新规定"                                            │
│        │                                                                    │
│        ├── 命中 knowledge（年假/规定）+ web_research_write（最新）           │
│        ├── 平票 → LLM决断                                                   │
│        └── 通常模型会选 web_research_write（外部法规更新）                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### RAG 降级到 Bocha 的策略

`knowledge` 路径的 `grader_node → web_search_node` 降级链**保留**：
- 当企业RAG检索不到相关内容时，fallback 到 Bocha 补充搜索
- **但**：如果 query 明确包含"公司/我司/内部"等词，RAG 未命中时**不走** Bocha 降级，直接说"未找到相关制度"
- v1 暂不做这个过滤（YAGNI），保留现有降级行为

## Graph 路由映射

```
intent_router_node
    │
    ├─► route_by_intent("knowledge") ──► knowledge_rag_node ──► grader_node
    │                                                               │
    │                                    ┌─ relevant ──► generate_node
    │                                    │
    │                                    └─ not relevant ──► web_search_node ──► generate_node
    │
    ├─► route_by_intent("salary") ──► auth_check_node ──► [salary_query_node | generate_node(denied)]
    │
    ├─► route_by_intent("personal") ──► auth_check_node ──► [personal_info_node | generate_node(denied)]
    │
    ├─► route_by_intent("travel") ──► travel_booking_node ──► generate_node
    │
    ├─► route_by_intent("web_research_write") ──► web_search_node ──► planner_node ──► generate_node
    │
    ├─► route_by_intent("direct_write") ──► planner_node ──► generate_node
    │
    ├─► route_by_intent("chitchat") ──► planner_node ──► generate_node
    │
    └─► route_by_intent("clarify") ──► generate_node

所有路径最终都汇聚到 generate_node ──► hallucination_check_node ──► [END | retry generate_node]
```

### 关键连接变更

新增/修改的边：
- `intent_router_node` → `web_search_node`（新增：`web_research_write` 直接路由）
- `web_search_node` → `planner_node`（新增：搜完素材后规划/生成）
- `intent_router_node` → `planner_node`（修改：`direct_write` 替代原来的 `chitchat` 写作类）

`grader_node → web_search_node`（保留：knowledge 的 RAG 未命中降级）

## Decisions

### 1. Bocha 接入位置:独立 service,不在 node 里直接调 httpx

新增 `app/services/web_search_service.py`,包装 Bocha 调用:

```python
class WebSearchService:
    async def search(self, query: str, *, max_results: int = 5) -> WebSearchResult: ...
```

`WebSearchResult` 是 Pydantic 模型,字段:`results: list[WebSearchHit]`、`query: str`、`elapsed_ms: int`。

`web_search_node` 只负责:调 service → push SSE → 把结果塞进 state。

**理由:** 与 `payroll_service` / `travel_service` 一致的分层惯例。让 node 保持薄,service 可独立测试。

**Alternative considered:** 直接在 node 里 httpx,理由"就一个 API 干嘛多写一层"。否决:违反现有架构,且后续如果换 Serper/Brave 时,只能动 node,影响范围大。

### 2. 失败降级策略:超时/异常 → 标记 `web_search_failed`,继续走 generate_node

`web_search_node` 内部捕获所有 Bocha 异常:

```python
try:
    result = await asyncio.wait_for(service.search(...), timeout=BOCHA_TIMEOUT_SECONDS)
except (TimeoutError, httpx.HTTPError) as exc:
    await streamer.push_progress(step="web_search", detail=f"联网搜索失败({exc.__class__.__name__}),改用本地知识")
    return {"structured_data": {"web_search_failed": True, "reason": str(exc)}}
```

`generate_node` 看到 `web_search_failed` 时,在 system prompt 里说明"无外部搜索结果,请基于已有知识回答并提示用户可能不是最新信息"。

**理由:** 用户体验优先于功能完备。Bocha 1500ms 超时即降级,绝不让用户等 10s 看到 timeout 错误。

**Alternative considered:** 重试 3 次再降级。否决:重试本质是把 1500ms 变成 4500ms,体感更差;Bocha API 已有自己的重试,客户端层重试只增加复杂度。

### 3. 意图判别规则:关键词触发 + LLM 兜底

`KEYWORD_RULES` 新增两条,拆分 chitchat:

```python
("web_research_write", [
    "今天", "明天", "昨天", "最新", "最近", "2026", "趋势",
    "天气", "新闻", "查一下", "搜一下", "联网", "实时",
], ["direct_write", "knowledge"]),
("direct_write", [
    "生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写",
], ["web_research_write", "knowledge"]),
("chitchat", [
    "你是谁", "你叫什么", "你好", "您好", "嗨",
    "你能做什么", "你会什么", "怎么用", "帮助",
    "谢谢", "辛苦了", "再见", "拜拜",
    "hi", "hello",
], ["knowledge"]),
```

注意触发优先级:"帮我生成 200 字 2026 AI agent 总结"会同时命中 web_research_write(2026) 和 direct_write(生成),根据现有平票逻辑会**让 utility 模型决断**。这正符合预期。

**理由:** 关键词覆盖 80% 高频情况,模糊场景交给 LLM,保持现有三层路由不变形。

### 4. SSE 事件序列(参照上一轮 UX 设计稿)

```
status: web_search running "联网搜索"
progress: web_search "正在调用 Bocha 搜索 {query}"
progress: web_search "已收到 N 条结果"
trace: source "OpenAI Agents SDK" detail=url state=done
trace: source "Anthropic MCP" detail=url state=done
status: web_search done
status: generate running "生成正文"
... tokens ...
status: generate done
```

`source_candidate` 事件用现有 `push_trace(step="source", ...)` 复用,不引入新事件类型(与上一轮 UX 设计共识)。

### 5. 配置与降级

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `BOCHA_API_KEY` | `""` | 留空 = `web_research_write` 路径直接 fallback 到 `direct_write` |
| `BOCHA_BASE_URL` | `https://api.bocha.cn/v1` | 可被代理 |
| `BOCHA_MAX_RESULTS` | `5` | 单次搜索返回条数,1-10 |
| `BOCHA_TIMEOUT_SECONDS` | `1.5` | 单次调用超时,与 utility 分类的 1.5s 阈值对齐 |
| `BOCHA_FRESHNESS` | `oneMonth` | Bocha 时效过滤:`oneDay`/`oneWeek`/`oneMonth`/`oneYear`/`noLimit` |

**理由:** 任何配置缺失都不能让启动崩,只让对应能力 graceful degrade。

### 6. Planner 节点适配新意图

`planner_node` 当前仅对 `intent == "chitchat"` 启用规划。拆分后需要覆盖 `direct_write` 和 `web_research_write`:

```python
def should_run_planner(*, intent: str, target_chars: int | None) -> bool:
    if intent not in {"chitchat", "direct_write", "web_research_write"}:
        return False
    ...
```

**理由:** `direct_write` 和 `web_research_write` 都是写作类，长输出（≥500字）同样需要大纲规划来避免"前重后轻"。

### 7. 为什么不用 Function Calling 做意图分类

当前项目使用 **prompt + PydanticOutputParser** 强制输出 JSON，而不是原生 function calling/tool_use。

| | 当前方案 (Prompt+JSON) | 原生 Function Calling |
|---|---|---|
| 模型输出 | 文本 `"{"intent":"knowledge"}"` | 结构化 `tool_calls=[...]` |
| 是否需要模型支持 | 不需要，任何文本模型都行 | 需要 API 支持 |
| 适用场景 | 硬路由分类（代码决定走哪条路） | 动态工具选择（模型决定调用什么） |

我们的架构是**代码硬路由**（`route_by_intent` 里写死映射），不是**模型动态选工具**。Function calling 在这种固定图编排里增加复杂度、没有收益。

此外，用户的 MiniMax 模型虽然支持 function calling，但推理模型（M2.7）+ function calling 会让意图分类这种简单任务拖到 10s+，反而更慢。

**结论：保持 prompt + JSON parser 方案。**

## Risks / Trade-offs

- **Bocha API 改 schema 或宕机** → 用 Pydantic 校验 + try/except 全包,失败立即降级 `direct_write`;启动时不预热,完全 lazy
- **每月 1000 次免费配额用完** → 不在代码层面做限流(YAGNI);用户自己关注 Bocha 后台;超量后第 1001 次调用会失败,自动走降级,不致命
- **关键词 "今天" 误命中** → 比如"今天我们公司差旅制度"会被错误归到 web_research_write,但有平票兜底(knowledge 关键词命中 1 次,web 命中 1 次 → 进 LLM 决断),实际误判很少
- **搜索结果质量不可控** → Bocha 是黑盒,可能给到低质量来源;v1 不做去重/打分,用户可点开 source chip 自行判断;有问题再加 grader
- **前端 source chip 渲染压力** → 5 条结果同时渲染问题不大,后续如果加到 10+ 再做虚拟列表
- **意图模型对新 intent 不熟** → few-shot 增加 2 条 web_research_write 示例,parser 仍按现有 PydanticOutputParser 严格校验
- **chitchat 拆分后老用户习惯** → "帮我写一段总结"以前走 chitchat（固定模板不存在，走生成），现在走 direct_write（一样走生成），用户无感知差异

## Migration Plan

1. **PR 阶段**:全部改动在 `web_research_write` / `direct_write` 路径生效,不动 `chitchat` 纯问候路径,已有用户行为不变
2. **灰度方式**:在 `.env` 不设 `BOCHA_API_KEY` 即可关掉新功能,代码自动 fallback
3. **回滚**:revert 单 PR,无数据迁移、无 schema 变更

## Open Questions

- Bocha 返回字段里是否带 `published_at`?如果有,可以在 chip 上显示日期。需要联调时确认
- 是否要把 web 搜索结果存入 chat_history.json 做溯源?v1 暂不做,只在当前回答内显示;后续做引用功能时再考虑
- `grader_node` 在 knowledge 路径的降级是否应过滤"公司/内部"等词?当前保留原行为，后续根据用户反馈决定
