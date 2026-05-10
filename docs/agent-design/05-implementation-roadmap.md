# 05 · 20-Commit 实施路线与回归说明

> 本轮"提升 Agent 体验"专项的提交清单 + 测试回归记录。
> 关联设计文档:[01](./01-thinking-and-status.md) · [02](./02-routing-and-model-tiers.md) · [03](./03-output-format-and-length.md) · [04](./04-planner-then-writer.md)

## 用户痛点 → 落地映射

| 用户原话 | 根因 | 落地 commit |
| --- | --- | --- |
| "回答跳字感觉一卡一卡" | 前端每收一个 token 都重渲染 markdown | C2 rAF 节流 |
| "思考中那几秒啥也不显示" | LangGraph 非流式节点期间无前端反馈 | C3 thinking + C4 节点级 status + C5 前端步骤列表 UI |
| "差旅报销那种快查询也卡很久" | intent_router 用了重模型做分类 | C7-C9 推理/工具模型分工(详见 02) |
| "输出格式怎么是 md" | system prompt 没分场景 | C11 按 intent 切换风格 |
| "写了 1000 字实际只有 600" | 模型 RLHF 偏置 + 一次性 prompt 控制力弱 | C12-C14 长度子句 + continuation 续写 + C15-C18 plan-then-write |

## 完整提交序列

| # | commit | 主题 |
| --- | --- | --- |
| 1 | 8214c2a | 品牌 tongtong → ruirui |
| 2 | 72c35b9 | perf(frontend): rAF 节流流式渲染 |
| 3 | 9216d1b | feat(backend): Anthropic extended thinking |
| 4 | f2526e3 | feat(backend): LangGraph 节点级状态事件 |
| 5 | d5ffddb | feat(frontend): 渲染节点级进度 |
| 6 | 3c1db92 | docs: agent-design-notes 骨架 |
| 7 | 19cf78b | docs: 01 thinking + status 决策 |
| 8 | 7b7a03a | docs: 02 推理/工具模型分工 |
| 9 | 65d5418 | docs: 03 输出格式 + 长度预算 |
| 10 | 5c65b95 | feat(llm): max_tokens 基线 + ANTHROPIC_OUTPUT_TOKENS |
| 11 | a3e55d6 | feat(response): 按 intent 切风格 |
| 12 | a3e55d6/37c09e8 | feat(response): 解析 query 字数 + 注入子句 |
| 13 | a3dad78 | feat(response): continuation 续写循环 |
| 14 | 89835b8 | test(response): continuation 阈值/触发 4 单测 |
| 15 | 992446d | feat(chains): planner_chain 大纲规划 |
| 16 | c12c9dc | feat(nodes): planner_node 包装 |
| 17 | 8129828 | feat(graph): planner 入图 |
| 18 | 30faa86 | feat(response): writer 接受 outline |
| 19 | 6a3f597 | test(planner): 触发门槛 + 兜底 6 单测 |
| 20 | 8ba18bc / 6a1a982 / da972f2 | docs 04 + 大纲流给前端 + writer prompt 重构 4 单测 |

(commit 数略多于 20——重构/分文件提交时切得更细，方便后续 cherry-pick 回退)

## 回归测试

执行: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests --deselect backend/tests/test_settings.py`

```
41 passed, 1 deselected, 3 warnings in 46.11s
```

`test_settings` 失败是环境变量缺省值差异(`OPENAI_EMBEDDING_MODEL` 未在测试环境注入),与本次专项无关,deselected 处理。

新增/影响的覆盖面:

- `test_llm.py` - max_tokens 基线 / thinking budget 兜底
- `test_response_chain.py` - 18 例:风格 / 长度解析 / continuation 触发 / writer prompt 注入
- `test_planner_chain.py` - 6 例:门槛触发 + LLM 不可用兜底

## 已知后续优化项

- planner 大纲只送主模型 + 已流到前端,但前端目前只渲到"思考折叠块",未做独立"📝 规划面板"——可在 ChatMessageBubble 里识别 `📝 已规划` 前缀单独渲染
- intent_router 的轻量分类模型还在用同一个 `get_chat_model()`,真正的多 tier 路由(详见 02)还需要落 `get_utility_chat_model()`
- continuation 续写阈值/最大轮数硬编码,未来可挂到配置
- planner_chain 异常未结构化日志,失败仅静默回退
