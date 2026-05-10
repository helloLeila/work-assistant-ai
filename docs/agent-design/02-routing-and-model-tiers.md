# 02 · 推理模型 vs 工具模型分工

> 用挖掘机削苹果是浪费——意图分类、字段抽取、相关性打分这些"小活"不该用推理模型。

## 症状

用户发"生成 200 字面试 LangGraph 的面经",前端"理解你的问题"步骤跑了 11.5s。但发"差旅报销最多能报多少",同一步骤只用了 ~1s。同样是意图分类,延迟差 10 倍。

## 根因

`MiniMax-M2.7`是**推理模型**,会按"问题难度"动态分配思考时间:

| 输入 | 模型内心戏 | 耗时 |
|---|---|---|
| "差旅报销最多能报多少" | 关键词"报销""差旅"非常清晰 → `knowledge` ✓<br>**几乎不用思考**,直接出 JSON | ~1s |
| "生成200字面试LangGraph的面经" | 没业务关键词,反复纠结:<br>"这是查文档?闲聊?生成?LangGraph 是产品还是技术?面经算知识库?"<br>→ 内部跑一长串 reasoning | 10-15s |

这是 o1 / R1 / Claude Sonnet 4 thinking / DeepSeek R1 等所有推理模型的通病——**输入越模糊,思考时间越长**。GPT-4o 这种非推理模型对两类输入耗时相近(都几百 ms)。

**意图分类是 5 选 1 的小任务,本不需要"深思熟虑"。把它扔给推理模型 = 用挖掘机削苹果。**

## 方案

### A. 关键词 fast-path 提前(已存在,只是顺序错了)

`@backend/app/chains/intent_chain.py`原有逻辑:

```python
if llm is not None:
    # 跑 LLM 分类(慢)
else:
    # 关键词兜底(快)
```

这是反向的——好不容易写好的关键词路由,只在 LLM 不可用时才会触发。正确顺序:

```python
fast = _keyword_classify(query)
if fast.confidence >= 0.85:
    return fast        # 80%+ 查询毫秒级返回
return await _llm_classify(query)  # 真正模糊的才上 LLM
```

### B. 多档模型配置(主流方案)

ChatGPT / Cursor / Perplexity 都不用一个大模型干所有活。按任务难度分档:

| Chain | 任务性质 | 模型档位 |
|---|---|---|
| `classify_intent` | 5 选 1 分类 | utility(轻量、非推理) |
| `grade_documents` | 二分类(相关/不相关) | utility |
| `extract_travel_info` / `extract_personal_query` | 字段抽取 | utility |
| `run_rag_chain` 的 draft answer | 中间产物 | utility 或删除 |
| `stream_final_answer` | 用户能看到的最终答案 | **main**(M2.7 等推理模型) |

实际工程能让端到端延迟从 20s 降到 5-8s,而最终答案质量不变。

### C. Embedding 路由(进阶,需要 embedding 服务)

预计算每个 intent 的原型句子的 embedding,query 时算 cosine 相似度。比关键词鲁棒(对同义/口语化提问更友好),比 LLM 快(~50ms vs ~1s+)。

当前项目`OPENAI_EMBEDDING_MODEL`留空,走本地词法检索,**这条路暂不可用**——等接入向量化服务后再做。

## 关于 MiniMax 订阅的现实

如果用户用的是 MiniMax Coding Plan(`sk-cp-`key),通常包含:

- `MiniMax-M2.7` (推理,重)
- `MiniMax-Text-01` (非推理,轻)
- `MiniMax-Text-Pro` (非推理,中)

订阅都能用的话,utility 模型选`MiniMax-Text-01`或`Pro`即可。如果订阅只有一档,可以让 utility 走 OpenAI 协议指向 GPT-4o-mini / Qwen-Turbo / 阿里百炼小模型——架构上保持灵活。

## 关键代码引用(规划中,详见后续文档章节)

- 配置项:`@backend/app/core/config.py` 拟新增`anthropic_utility_model`
- 模型工厂:`@backend/app/core/llm.py` `get_chat_model(model_tier="main"|"utility")`
- 意图链:`@backend/app/chains/intent_chain.py` 重写为 fast-path 优先

## 未做项

- 多档模型配置(Phase 1 优化重点)
- 关键词 fast-path 提前(目前仍是 LLM 优先)
- Embedding 路由(等向量化服务接入)
- 路由层缓存:同一 query 短时间内重复时,直接用缓存意图,跳过分类
