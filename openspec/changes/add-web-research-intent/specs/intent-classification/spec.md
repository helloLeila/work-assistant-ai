## ADDED Requirements

### Requirement: 意图枚举包含 web_research_write 与 direct_write

意图分类输出的 `intent` 字段 SHALL 允许以下值之一:`knowledge`、`salary`、`personal`、`travel`、`web_research_write`、`direct_write`、`chitchat`、`clarify`。其中 `web_research_write` 表示需要先做联网搜索再写作的请求,`direct_write` 表示不需要联网素材的纯写作请求,`chitchat` 仅保留问候/身份/感谢等纯闲聊。

#### Scenario: 时效性写作触发 web_research_write
- **WHEN** 用户输入 "帮我生成 200 字 2026 AI agent 趋势总结"
- **THEN** 意图被分类为 `web_research_write`,且 `candidate_intents` 包含 `direct_write` 作为降级备选

#### Scenario: 纯写作不触发联网
- **WHEN** 用户输入 "帮我写一段感谢信"
- **THEN** 意图被分类为 `direct_write`,不触发任何外部搜索调用

#### Scenario: 问候归 chitchat 不归 direct_write
- **WHEN** 用户输入 "你是谁" 或 "你好"
- **THEN** 意图被分类为 `chitchat`,不调用任何 LLM 或外部 API,响应在 100ms 内开始

### Requirement: 关键词层支持 web_research_write 触发词

`KEYWORD_RULES` SHALL 包含 `web_research_write` 一条,触发词覆盖时效性、新闻类、显式联网请求三类。

#### Scenario: 时效性词命中
- **WHEN** 用户输入包含 "今天"、"最新"、"最近"、"2026"、"趋势" 中任一关键词
- **THEN** 关键词层命中 `web_research_write`,跳过 utility 模型分类

#### Scenario: 显式联网词命中
- **WHEN** 用户输入包含 "联网"、"实时"、"查一下"、"搜一下"、"新闻"、"天气" 中任一关键词
- **THEN** 关键词层命中 `web_research_write`

#### Scenario: 写作词与时效词平票交给模型
- **WHEN** 用户输入 "帮我生成 200 字 2026 AI agent 总结"(同时命中 `生成` 与 `2026`)
- **THEN** 关键词层放弃判断,流转到第 3 层 utility 模型,由模型根据 few-shot 决定

### Requirement: BOCHA_API_KEY 缺失时 web_research_write 自动降级

意图层 SHALL 不强制要求 Bocha 配置存在。当系统检测到 `BOCHA_API_KEY` 为空时,`web_research_write` 在节点执行阶段静默降级为 `direct_write`,意图分类本身不受影响。

#### Scenario: 未配置 BOCHA_API_KEY
- **WHEN** 用户输入 "今天天气如何" 且 `BOCHA_API_KEY` 为空
- **THEN** 意图仍为 `web_research_write`,但 `web_search_node` 跳过搜索直接 push 提示文本,并继续走 `generate_node` 给出"无法联网,请提供更多信息"的回答,不抛错
