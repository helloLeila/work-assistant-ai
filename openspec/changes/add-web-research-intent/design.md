## Context

`backend/app/nodes/web_search_node.py` 目前是 stub:无论用户问什么,都返回"知识库没有相关材料"的固定文本。`intent_chain.KEYWORD_RULES` 里所有写作类(生成/写/总结/面试)都归到 `chitchat`,不区分是否需要外部素材,模型只能凭训练数据回答。

我们已经注册 Bocha Web Search(`api.bochaai.com`):

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

`KEYWORD_RULES` 新增两条:

```python
("web_research_write", [
    "今天", "明天", "昨天", "最新", "最近", "2026", "趋势",
    "天气", "新闻", "查一下", "搜一下", "联网", "实时",
], ["direct_write", "knowledge"]),
("direct_write", [
    "生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写",
], ["web_research_write", "knowledge"]),
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
| `BOCHA_BASE_URL` | `https://api.bochaai.com/v1` | 可被代理 |
| `BOCHA_MAX_RESULTS` | `5` | 单次搜索返回条数,1-10 |
| `BOCHA_TIMEOUT_SECONDS` | `1.5` | 单次调用超时,与 utility 分类的 1.5s 阈值对齐 |
| `BOCHA_FRESHNESS` | `oneMonth` | Bocha 时效过滤:`oneDay`/`oneWeek`/`oneMonth`/`oneYear`/`noLimit` |

**理由:** 任何配置缺失都不能让启动崩,只让对应能力 graceful degrade。

## Risks / Trade-offs

- **Bocha API 改 schema 或宕机** → 用 Pydantic 校验 + try/except 全包,失败立即降级 `direct_write`;启动时不预热,完全 lazy
- **每月 1000 次免费配额用完** → 不在代码层面做限流(YAGNI);用户自己关注 Bocha 后台;超量后第 1001 次调用会失败,自动走降级,不致命
- **关键词 "今天" 误命中** → 比如"今天我们公司差旅制度"会被错误归到 web_research_write,但有平票兜底(knowledge 关键词命中 1 次,web 命中 1 次 → 进 LLM 决断),实际误判很少
- **搜索结果质量不可控** → Bocha 是黑盒,可能给到低质量来源;v1 不做去重/打分,用户可点开 source chip 自行判断;有问题再加 grader
- **前端 source chip 渲染压力** → 5 条结果同时渲染问题不大,后续如果加到 10+ 再做虚拟列表
- **意图模型对新 intent 不熟** → few-shot 增加 2 条 web_research_write 示例,parser 仍按现有 PydanticOutputParser 严格校验

## Migration Plan

1. **PR 阶段**:全部改动在 `web_research_write` 路径生效,不动 `chitchat` 路径,已有用户行为不变
2. **灰度方式**:在 `.env` 不设 `BOCHA_API_KEY` 即可关掉新功能,代码自动 fallback
3. **回滚**:revert 单 PR,无数据迁移、无 schema 变更

## Open Questions

- Bocha 返回字段里是否带 `published_at`?如果有,可以在 chip 上显示日期。需要联调时确认
- 是否要把 web 搜索结果存入 chat_history.json 做溯源?v1 暂不做,只在当前回答内显示;后续做引用功能时再考虑
