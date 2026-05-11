## 1. 配置层

- [ ] 1.1 在 `backend/app/core/config.py` 新增四个 settings 字段:`bocha_api_key: str = ""`、`bocha_base_url: str = "https://api.bochaai.com/v1"`、`bocha_max_results: int = 5`、`bocha_timeout_seconds: float = 1.5`、`bocha_freshness: str = "oneMonth"`,均带 docstring 注释来源
- [ ] 1.2 在 `.env.example` 追加上述变量示例(`BOCHA_API_KEY=` 留空提示用户自行填写)
- [ ] 1.3 在 `Settings` 上新增 `bocha_enabled` property,判断 `bocha_api_key.strip() != ""`

## 2. Web Search Service

- [ ] 2.1 创建 `backend/app/services/web_search_service.py`,定义 Pydantic 模型 `WebSearchHit`(title/url/snippet/source/published_at) 与 `WebSearchResult`(results/query/elapsed_ms)
- [ ] 2.2 实现 `WebSearchService.search(query, max_results=None)`,使用 `httpx.AsyncClient` POST `{bocha_base_url}/web-search`,Header 带 `Authorization: Bearer {bocha_api_key}`,body 包含 `query`、`count`、`freshness`、`summary=true`
- [ ] 2.3 用 `asyncio.wait_for` 包到 `bocha_timeout_seconds`,超时抛 `TimeoutError`
- [ ] 2.4 Bocha 响应字段映射到 `WebSearchHit`(注意 Bocha 嵌套结构 `data.webPages.value[]`)
- [ ] 2.5 提供模块级单例 getter `get_web_search_service()`,内部 lazy 初始化

## 3. 改造 web_search_node

- [ ] 3.1 重写 `backend/app/nodes/web_search_node.py`,接受 `runtime` 拿到 streamer
- [ ] 3.2 入口先检查 `settings.bocha_enabled`,关闭时 push 一条 progress 并返回 `{"structured_data": {"web_search_failed": True, "reason": "bocha_api_key 未配置"}}`
- [ ] 3.3 调用 service 前 push `progress` "正在联网搜索:{query[:30]}"
- [ ] 3.4 调用 service,捕获 `TimeoutError` / `httpx.HTTPError` / `pydantic.ValidationError`,任一异常 push `progress` 失败说明并返回降级 state
- [ ] 3.5 成功后 push `progress` "已找到 N 条线索",对每条结果 push `trace`(step="source", label=title, detail=url)
- [ ] 3.6 把结构化结果存入 `state["structured_data"]["web_results"]`,把 url 列表追加到 `state["sources"]`

## 4. 意图层

- [ ] 4.1 在 `intent_chain.KEYWORD_RULES` 加入 `web_research_write` 条目(时效/新闻/显式联网词)
- [ ] 4.2 把现有 chitchat 行的写作类关键词("生成/写/撰写/面试/经验/介绍/总结/润色/改写")拆出到新的 `direct_write` 条目,chitchat 只保留问候/身份/感谢/帮助类词
- [ ] 4.3 在 `FEW_SHOTS` 增加 2 条示例:一条触发 web_research_write,一条触发 direct_write
- [ ] 4.4 更新 system prompt 里枚举,告诉模型新增的两个 intent 含义
- [ ] 4.5 调整 `IntentClassification` Pydantic 模型(或 `Literal`)允许新值

## 5. 路由层

- [ ] 5.1 在 `office_assistant_graph.py` 的 `route_by_intent` 增加分支:`web_research_write → web_search_node`、`direct_write → planner_node`
- [ ] 5.2 给 `web_search_node` 套 `_with_status` 包装,step="web_search",label="联网搜索"
- [ ] 5.3 `web_search_node` 之后边连到 `planner_node`(若 `web_search_failed=True` 也照样进 planner_node,由 generate 处理)
- [ ] 5.4 `_status_label_for_state` 新增 `web_research_write → 撰写联网总结`、`direct_write → 撰写正文`

## 6. generate_node 适配

- [ ] 6.1 在 `generate_node._build_context_text` 里增加 `web_results` 分支,把搜索结果格式化为 markdown 引用块塞进 prompt context
- [ ] 6.2 检查 `structured_data.get("web_search_failed")`,若为真则在 system prompt 加一段"无外部搜索结果,请基于现有知识作答并明确告知用户可能不是最新"
- [ ] 6.3 保持现有 chitchat 快速模板兼容,不影响 `direct_write` 路径

## 7. 测试

- [ ] 7.1 新增 `backend/tests/test_web_search_service.py`:mock httpx 验证正常返回、超时、HTTP 500、字段缺失 4 个场景
- [ ] 7.2 在 `backend/tests/test_intent_chain.py` 增加:`test_web_research_write_keyword_hits`、`test_direct_write_keyword_hits`、`test_writing_with_freshness_word_falls_to_llm`
- [ ] 7.3 新增 `backend/tests/test_web_search_node.py`:mock service 验证降级 / SSE 事件发出 / state 结构正确
- [ ] 7.4 确保现有 11 条意图测试不破坏(chitchat fast-path 行为不变)

## 8. 前端适配

- [ ] 8.1 `ChatMessageBubble.vue`:把 `source` 类型的 trace 事件渲染为可点击 chip(title + 域名)
- [ ] 8.2 `useChatStream.ts` 暴露 `onSourceCandidate`(沿用现有 onTrace,step="source" 时分发)
- [ ] 8.3 ChatStep 类型 `id="web_search"` 时图标用🌐 emoji 或地球 icon 区分

## 9. 文档与提交

- [ ] 9.1 更新 `README.md` 配置章节说明 Bocha 接入步骤
- [ ] 9.2 在 `docs/agent-design/02-routing-and-model-tiers.md` 追加章节说明 `web_research_write` / `direct_write` 拆分
- [ ] 9.3 跑 `openspec validate add-web-research-intent --strict` 确保 spec 与代码契合
- [ ] 9.4 跑全量后端测试,确认 >= 之前的 44 条全部通过 + 新增 ≥10 条
- [ ] 9.5 分 5-6 个聚焦 commit 提交(配置 / service / node / 意图 / 测试 / 文档)

## 10. 验收

- [ ] 10.1 手动:输入"今天天气如何"→ 看到搜索 step + source chip + 包含日期的答案
- [ ] 10.2 手动:输入"帮我生成 200 字 2026 AI agent 趋势总结"→ 触发 web_research_write,看到 source chip,回答引用了搜索内容
- [ ] 10.3 手动:输入"帮我写一段感谢信"→ 走 direct_write,没有 source 调用
- [ ] 10.4 手动:输入"你是谁"→ 仍然 fast-path 100ms 内回答
- [ ] 10.5 手动:把 `.env` 里 `BOCHA_API_KEY` 删掉,再问"今天天气"→ 看到降级提示,不报错
