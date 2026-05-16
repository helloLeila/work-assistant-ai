## Why

### 问题 1:`web_search_node` 是 stub,时效性问题全部失败

当前 `backend/app/nodes/web_search_node.py` 整段实现就是返回一句固定文本:

```python
async def web_search_node(state: dict) -> dict:
    query = state["query"]
    supplemental_text = f"当前知识库中没有足够材料直接回答“{query}”,建议补充相关制度或流程文档。"
    return {"structured_data": {"web_fallback": supplemental_text}, ...}
```

实际表现(已复现):
- 用户问 **"今天天气怎么样"** → 模型基于训练截止前的数据胡编一个温度,或回 "我无法获取实时信息"
- 用户问 **"今天是几号"** → 模型回训练时的日期(可能是去年的)
- 用户问 **"帮我生成 200 字 2026 AI agent 趋势总结"** → 模型只能凭 2024-2025 训练语料推测,把已经过时的项目当 "最新趋势"

`web_search_node` 在路由表里**确实存在**,但只在"知识库检索打分不及格"时才被触发,且返回内容毫无价值。**这条路径对于"问时效"的请求根本不会被走到**——意图分类先把这类请求扔进 `chitchat` 桶,直接进 `generate_node` 让主模型瞎答。

### 问题 2:`chitchat` 桶里混了三种本质不同的请求

现在 `intent_chain.KEYWORD_RULES` 的 `chitchat` 一行(`@/Users/leila/Documents/coding/tongtong/backend/app/chains/intent_chain.py:40-52`):

```python
("chitchat", [
    "生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写",
    "你是谁", "你叫什么", "你好", ..., "谢谢", ...,
], ["knowledge"]),
```

把以下三类截然不同的请求归为同一桶:

| 请求示例 | 真实需求 | 当前行为 | 期望行为 |
|---|---|---|---|
| "你是谁" / "谢谢" | 问候/身份(0ms 应答) | ✅ fast-path | 保持不变 |
| "帮我写一段感谢信" | 不联网写作(纯模型生成) | ⚠️ 直接进 generate,够用但混在 chitchat 概念上不准 | 独立为 `direct_write` |
| "帮我生成 200 字 2026 AI agent 趋势总结" | **必须联网搜素材**才能写准 | ❌ 进 generate 让模型瞎写 | 独立为 `web_research_write`,先搜 Bocha 再写 |

模型在同一个 `chitchat` 桶里看不到这三种请求的差异,就**没有任何机制**能选择正确的执行路径。

### 问题 3:已具备落地条件,继续拖只是浪费配额

我们已经注册 Bocha AI(`api.bocha.cn`),具体可用性:
- **国内直连**,免 VPN(Tavily/Serper 等海外方案不可行)
- **协议简单**:REST POST,Bearer token,JSON body/response
- **价格友好**:免费 1000 次/月,超出 ¥0.03/次
- **配额已生效**:开发期不接,只是月底白白浪费 1000 次免费额度

## What Changes

按"自下而上"的依赖顺序分层。每条 before/after 都明确,实施者可单独 review 每层。

### A. 配置层(无依赖,先落)

| 项目 | Before | After |
|---|---|---|
| `Settings` 字段 | 无 Bocha 相关字段 | 新增 5 个:`bocha_api_key/base_url/max_results/timeout_seconds/freshness` |
| `Settings.bocha_enabled` | 不存在 | 新增 property,判断 `bocha_api_key.strip() != ""` |
| `.env.example` | 无 Bocha 段 | 新增 `[Bocha Web Search]` 段,5 个变量带注释 |

### B. Service 层(依赖 A)

| 项目 | Before | After |
|---|---|---|
| `app/services/web_search_service.py` | 文件不存在 | 新增 `WebSearchService` 类,签名 `async def search(query, *, max_results=None) -> WebSearchResult` |
| Pydantic 模型 | 无 | 新增 `WebSearchHit`(title/url/snippet/source/published_at) 和 `WebSearchResult`(query/results/elapsed_ms) |
| 错误协议 | — | 超时抛 `TimeoutError`,网络错误抛 `httpx.HTTPError`,字段不符抛 `ValidationError`,**Service 不做降级,降级是 node 的职责** |
| 单例 | — | 模块级 `get_web_search_service()` lazy 创建,测试可 monkeypatch |

### C. Node 层(依赖 B)

| 项目 | Before | After |
|---|---|---|
| `web_search_node` | 14 行 stub,返回固定文案 | 真调 Service;捕获所有异常 → 标 `web_search_failed=True` 继续走 generate;成功时把结果写入 `state["structured_data"]["web_results"]` |
| SSE 事件 | 无 | push `progress`("正在联网搜索:{query[:30]}" / "已找到 N 条线索"),每条结果 push 一条 `trace`(step="source", label=title, detail=url) |
| key 未配置 | — | 节点入口检查 `settings.bocha_enabled`,关闭时不发 HTTP 请求,直接 push progress + 返回降级 state |

### D. 意图层(独立于 B/C,可并行)

| 项目 | Before | After |
|---|---|---|
| `IntentClassification.intent` 允许值 | knowledge/salary/personal/travel/chitchat/clarify | 新增 `web_research_write` / `direct_write`,共 8 个 |
| `KEYWORD_RULES` chitchat 行 | 写作词 + 问候词混在一起,fallback `["knowledge"]` | **拆成 3 条**:`chitchat` 只留问候/身份/感谢;新增 `direct_write` 包含生成/写/撰写等;新增 `web_research_write` 包含今天/最新/2026/趋势/天气/新闻 |
| 短查询兜底 | 默认 chitchat(0.85) | 不变 |
| `FEW_SHOTS` | 4 条业务示例 | 增加 2 条:`web_research_write`(2026 趋势)和 `direct_write`(感谢信) |
| 意图 system prompt 枚举 | 5 个 intent | 8 个 intent + 各自一句话说明 |

### E. 路由层(依赖 C/D)

| 项目 | Before | After |
|---|---|---|
| `route_by_intent` mapping | chitchat/clarify → generate_node(经 planner) | 新增 `web_research_write → web_search_node`、`direct_write → planner_node` |
| `web_search_node` 后继边 | `web_search_node → generate_node` 已存在,但只从 grader 失败时进入 | 保留;额外让 web_research_write 主动进入,出口仍接 generate_node |
| `_status_label_for_state` | 5 个 intent 标签 | 新增 `web_research_write → "撰写联网总结"`、`direct_write → "撰写正文"` |
| `web_search_node` 状态包装 | step="web_search" label="联网补充检索" | 改为 label="联网搜索"(主动联网而非"补充") |

### F. Generate 层(依赖 C)

| 项目 | Before | After |
|---|---|---|
| `_build_context_text` / context_parts | 拼 draft / structured_data / sources | 新增分支:`structured_data["web_results"]` 时,格式化为 markdown 引用块塞进 prompt |
| system prompt 降级提示 | 无 | 检测 `web_search_failed=True` 时,在 system 注入"无外部搜索结果,请基于已有知识作答并明确告知用户内容可能不是最新" |
| chitchat 快速模板 | `_fixed_chitchat_answer` 仅在 intent=="chitchat" 时触发 | 不变(direct_write 不走快速模板,因为它不是问候) |

### G. 前端层(依赖 C 的 SSE 协议)

| 项目 | Before | After |
|---|---|---|
| `useChatStream.ts` | 已有 `onTrace`,`step="source"` 已可识别(走知识库路径) | 不变;web_search_node push 的 trace 复用同一通道 |
| `ChatMessageBubble.vue` source chip | 仅显示文件名 + 页码 | trace `step="source"` 且 detail 是 URL 时,渲染为可点击 chip(title + 域名)|
| ChatStep 图标 | 节点级 emoji 已有映射 | `step="web_search"` 用🌐,与 `retrieve` 区分 |

## 兼容性 / BREAKING 分析

**无 BREAKING**:
- 老 `chitchat` 触发路径**100% 保留**:问候、身份、感谢这些词全部留在 chitchat 桶,fast-path 行为字节级一致
- 写作类(生成/写/总结...)从 chitchat 移到 `direct_write`,但 **`direct_write` 的下游链路与原 chitchat 完全一致**(都是 planner_node → generate_node),用户感知不到变化
- `web_research_write` 是全新意图,只有用户输入命中"今天/最新/2026/天气..."等新词时才触发;不命中就走原路径
- `BOCHA_API_KEY` 留空 = `web_research_write` 自动降级回 `direct_write`,**老部署不需要任何配置变更也能启动**

**测试影响**:
- 现有 11 条 `test_intent_chain.py` 用例:`generation_request_uses_local_chitchat_fast_path` 这条会改成 `direct_write`,其它 10 条不变
- 新增 ≥ 10 条单测覆盖 service / node / 新意图

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
