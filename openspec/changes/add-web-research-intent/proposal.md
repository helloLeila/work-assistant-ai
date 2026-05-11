## Why

当前 `web_search_node` 只是 stub,问"今天天气""今天是几号""2026 AI agent 趋势"这类时效性问题时,系统只能基于训练截止前的数据回答,容易胡说或返回过期内容。同时意图分类把"生成 200 字 agent 总结"这类需要联网素材的写作和"帮我写一段感谢信"这类不需要联网的写作混在同一个 chitchat 桶里,模型无法选择正确的执行路径。

我们已经注册了 Bocha AI(`api.bochaai.com`)的 Web Search API(国内可直连,免 VPN),具备落地条件。

## What Changes

- 新增意图 `web_research_write`:需要联网搜素材后再写作的请求
- 现有 `chitchat` 拆分:`chitchat`(纯问候/身份/感谢) 保留快回答,新增 `direct_write`(不联网写作)与 `web_research_write` 并列
- `intent_chain.KEYWORD_RULES` 调整:加入"今天/最新/2026/趋势/天气/新闻/查一下"等触发词指向 `web_research_write`
- `web_search_node` 从 stub 改为**真接 Bocha Web Search API**,返回标题/URL/正文摘要的结构化结果
- LangGraph 路由表加入 `web_research_write → web_search_node → generate_node` 链路,流式过程发 `progress` / `trace` / `source_candidate` 事件
- 新增配置 `BOCHA_API_KEY` / `BOCHA_BASE_URL` / `BOCHA_MAX_RESULTS` / `BOCHA_TIMEOUT_SECONDS`
- 新增 `app/services/web_search_service.py`,封装 Bocha 客户端 + 错误降级(失败时回退到 chitchat 写作,不阻塞用户)
- 前端 SSE 增加来源 chip 渲染(已有 source 通道,扩展显示 web 来源标题 + 域名)

无 BREAKING:旧的 chitchat 关键词全部保留,只是把新词加进 web_research_write,默认行为对老用户无变化。

## Capabilities

### New Capabilities
- `intent-classification`:意图识别能力,定义所有支持的 intent 枚举、关键词路由规则、置信度策略、`web_research_write` / `direct_write` 的判别条件
- `web-search`:Web Search 能力,定义 Bocha API 调用契约、结果结构、超时/降级策略、SSE 事件流

### Modified Capabilities
<!-- 项目暂无已沉淀的 spec,本次为首批新增,因此 Modified 留空。 -->

## Impact

**代码**
- `backend/app/chains/intent_chain.py`:KEYWORD_RULES 扩列、新增 intent 枚举
- `backend/app/nodes/web_search_node.py`:从 stub 改为真实 Bocha 调用
- `backend/app/agents/office_assistant_graph.py`:新增 `web_research_write` 路由分支
- `backend/app/services/web_search_service.py`:**新增**
- `backend/app/core/config.py`:新增 4 个 BOCHA_* 配置项
- `backend/app/core/streaming.py`:已具备 `push_progress` / `push_trace`,可直接复用;`push_sources` 扩展 web 来源
- `backend/app/models/domain.py`:`IntentClassification` intent 字段允许值扩展
- `frontend/src/components/ChatMessageBubble.vue`:source chip 增加 web 来源样式(标题 + 域名)

**依赖**
- 新增 Python:`httpx`(很可能已有,因为 LangChain 依赖了)。不引入新的 SDK,Bocha 直接走 REST 即可。

**外部依赖 / 成本**
- Bocha API:1 次请求消耗 1 个 quota,免费层每月 1000 次,超出按量计费
- 网络延迟:新增 1 次外部 HTTP 调用(~500-1500ms),仅在 `web_research_write` 路径上,其他路径完全不受影响

**配置**
- 必须在 `.env` 加 `BOCHA_API_KEY=<your-key>`,否则 `web_research_write` 路径直接降级为 `direct_write`,启动不报错

**测试**
- 新增 `test_web_search_service.py`(单测,mock httpx)
- 新增 `test_intent_chain.py::test_web_research_write_keywords` 等用例
- 现有 `test_intent_chain.py` 11 条不应破坏
