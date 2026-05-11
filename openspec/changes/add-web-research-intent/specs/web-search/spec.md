## ADDED Requirements

### Requirement: WebSearchService 封装 Bocha API 调用

系统 SHALL 提供一个 `WebSearchService` 类,屏蔽 Bocha 协议细节。Service 接受 `query: str` 与可选 `max_results: int`,返回一个 Pydantic `WebSearchResult` 对象,字段包括 `results: list[WebSearchHit]`、`query: str`、`elapsed_ms: int`。`WebSearchHit` 字段:`title: str`、`url: HttpUrl`、`snippet: str`、`source: str`、`published_at: str | None`。

#### Scenario: 正常调用返回结构化结果
- **WHEN** Service 收到查询 "2026 AI agent 趋势" 且 Bocha 返回 5 条结果
- **THEN** Service 返回 `WebSearchResult.results` 长度等于 5,每条 `title` 与 `url` 非空,`elapsed_ms` 大于 0

#### Scenario: 返回数量受 BOCHA_MAX_RESULTS 限制
- **WHEN** 配置 `BOCHA_MAX_RESULTS=3` 且 Bocha 实际返回 10 条
- **THEN** Service 返回的 `results` 至多 3 条

### Requirement: WebSearchService 超时强制 1.5 秒并抛 TimeoutError

Service SHALL 使用 `asyncio.wait_for` 或 `httpx.Timeout` 将单次调用包在 `BOCHA_TIMEOUT_SECONDS`(默认 1.5)内。超时后 MUST 抛 `TimeoutError`,由调用方决定降级策略。

#### Scenario: 慢响应被打断
- **WHEN** Bocha 服务端 3 秒后才回包,而 `BOCHA_TIMEOUT_SECONDS=1.5`
- **THEN** Service 在 1.5 秒内抛 `TimeoutError`,不阻塞主链路

### Requirement: web_search_node 失败时降级到 generate_node 不抛错

`web_search_node` SHALL 捕获 Service 的所有异常(`TimeoutError`、`httpx.HTTPError`、`ValidationError`),将 `structured_data` 标记 `web_search_failed=True` 并附带 `reason`,然后正常返回让 `generate_node` 继续执行。MUST 不向上层抛异常,MUST 不让前端看到 error 事件。

#### Scenario: Bocha 超时
- **WHEN** Service 抛 `TimeoutError`
- **THEN** `web_search_node` push 一条 `progress` 事件("联网搜索超时,改用本地知识"),返回 `{"structured_data": {"web_search_failed": True, "reason": "timeout"}}`

#### Scenario: Bocha 返回 HTTP 500
- **WHEN** Service 抛 `httpx.HTTPStatusError(status_code=500)`
- **THEN** `web_search_node` 表现同上,前端收到的是 progress 而非 error

#### Scenario: BOCHA_API_KEY 为空时不调用
- **WHEN** `BOCHA_API_KEY=""` 且节点被触发
- **THEN** 节点直接 push progress("未配置联网搜索,改用本地知识"),不发起 HTTP 请求,返回 `web_search_failed=True`

### Requirement: web_search_node 推送细粒度 SSE 进度

`web_search_node` SHALL 在执行过程中向前端 push 至少以下 SSE 事件:
- `status` step=`web_search` state=`running`(进入节点时,已由 `_with_status` 包装层自动)
- `progress` step=`web_search` detail=`正在联网搜索:{query前 30 字}`(开始请求时)
- `progress` step=`web_search` detail=`已找到 N 条线索`(请求成功后)
- `trace` step=`source` label=`{title}` detail=`{url}` state=`done`(每条结果一条,最多 5 条)
- `status` step=`web_search` state=`done`(离开节点时,由 `_with_status` 自动)

#### Scenario: 成功调用 push 完整事件序列
- **WHEN** Bocha 返回 3 条结果
- **THEN** 前端收到 1 条 status running、2 条 progress、3 条 trace source、1 条 status done,顺序符合上述规范

### Requirement: generate_node 感知 web_search_failed 并调整提示

`generate_node` SHALL 检查 `state["structured_data"].get("web_search_failed")`,若为真则在 system prompt 注入"无法访问外部搜索,请基于已有知识作答并明确告知用户内容可能不是最新的"指令。

#### Scenario: 降级后生成带提示的答案
- **WHEN** `web_search_failed=True` 且用户问"2026 AI 趋势"
- **THEN** 模型回答中包含类似"以下基于训练数据,可能不是最新信息"的免责说明
