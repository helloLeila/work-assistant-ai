# 01 · Extended Thinking 与节点级状态推送

> 让用户在 16 秒等待里看到"它在干什么",而不是看死秒表。

## 症状

用户发"差旅报销最多能报多少",前端思考块显示`思考中 16.3s`,中途完全没有任何字符出现,直到 16 秒后正式答案才开始流式输出。用户体验:**疑似卡住、想关掉重试**。

## 根因(定位过程)

第一反应:模型推理慢——开 extended thinking 让 reasoning token 流出来填补空场。
第二排查:加完 thinking 还是冷场。
真凶:**LangGraph 流水线在`generate_node`之前要串行跑 3 个非流式 LLM 调用**。

```
START → intent_router_node     (LLM, ~2-4s, 非流式)
      → knowledge_rag_node     (LLM, ~3-5s, 还会生成一个被丢弃的 draft)
      → grader_node            (LLM, ~1-3s, 非流式)
      → generate_node          (终于开始 push_token)
```

累计 8-15s 的"前期"完全没向前端发任何事件,前端只能看死秒表。

## 方案

### A. SSE 协议层:新增`status`事件

`@app/core/streaming.py` 增加:

```python
async def push_status(self, *, step: str, label: str, state: str) -> None:
    await self._queue.put(StreamEvent(
        type="status",
        payload={"step": step, "label": label, "state": state},
    ))
```

负载三件套:
- `step`:稳定机器 id(`intent`/`retrieve`/`grade`/`generate`/...),前端按此 upsert
- `label`:中文描述,可改文案不破坏协议
- `state`:`running` / `done`

### B. LangGraph 装饰器:每个节点入口/出口推送

`@app/agents/office_assistant_graph.py` 引入`_with_status()`:

```python
def _with_status(node_fn, *, step, label, takes_runtime=False):
    async def wrapped(state, runtime):
        streamer = getattr(runtime.context, "streamer", None)
        if streamer:
            await streamer.push_status(step=step, label=label, state="running")
        try:
            return await (node_fn(state, runtime) if takes_runtime else node_fn(state))
        finally:
            if streamer:
                await streamer.push_status(step=step, label=label, state="done")
    return wrapped
```

`try/finally`保证异常路径也会发`done`,前端 spinner 不会卡死。

### C. Extended Thinking 按 intent 启用

业务推理(`knowledge`/`salary`/`personal`/`travel`)需要 reasoning,开启 thinking 让 token 边推理边吐:

`@app/chains/response_chain.py`:
```python
THINKING_INTENTS = {"knowledge", "salary", "personal", "travel"}

def should_enable_extended_thinking(intent: str) -> bool:
    return intent in THINKING_INTENTS
```

`chitchat`/写作类不开 thinking——它们是创作任务,模型"思考"反而会拖慢首 token,损害体验。

### D. 前端步骤列表渲染

`@frontend/src/components/ChatMessageBubble.vue` 在思考块里加`thinking__steps`:

- `running`步骤:紫色加粗 + 转圈 spinner + 实时秒表
- `done`步骤:灰色 + 绿色对勾 + 凝固耗时
- 流结束后步骤列表保留(像 Claude Code/Cursor 一样可回顾)

## 关键代码引用

- 后端协议:`@backend/app/core/streaming.py`
- 节点装饰:`@backend/app/agents/office_assistant_graph.py:60-90`
- thinking 开关:`@backend/app/chains/response_chain.py:12-17`
- 前端渲染:`@frontend/src/components/ChatMessageBubble.vue` `.thinking__steps`

## 未做项

- `hallucination_check_node`目前没发 status。它通常毫秒级,但如果未来加重了,该补上
- 状态事件没有错误态(`state="error"`)。当前异常路径只发`done`,前端无法区分"成功完成"与"失败兜底"。如有需要可扩展
- thinking 内容流式期间纯文本展示,流结束后才走 markdown 渲染——避免每 token 重新 marked.parse 的性能爆炸。代价是用户看到一段时间的`**`/`##`原文,之后跳变成排版后的 HTML
