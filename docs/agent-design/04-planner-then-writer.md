# 04 · Planner-then-Writer:长输出的两段式生成

> 关联代码:`backend/app/chains/planner_chain.py` · `backend/app/nodes/planner_node.py` · `backend/app/chains/response_chain.py:stream_final_answer`

## 症状

用户写"生成 1000 字面试经验,agent 方向",首轮回答经常只有 600~700 字就草草收尾;追问"再写多点"才补足。

## 根因

1. **RLHF 偏置**:开源/对齐过的模型在长输出时倾向"前重后轻",开头详细、结尾敷衍;最终字数普遍**低估目标 20%~40%**。
2. **一次性 prompt 控制力弱**:在 system prompt 里写"请写 1000 字"只能让模型尽量写,无强约束;模型常常写到 700 字觉得"差不多了"就 stop。
3. **没有结构骨架**:模型自由发挥时容易合并段落、跳过细节,字数自然下来了。

## 方案:Plan-then-Write

灵感来自 Claude Code 的 plan-then-execute 工作流——把"长输出生成"拆成两步:

```
用户长请求 (>=500 字)
    │
    ▼
┌────────────────────────┐
│ planner_node           │  跑一个轻量 LLM 调用,产出 3-5 段大纲
│ (chitchat + 长字数)    │  每段标注"~XXX 字"预算
└────────────────────────┘
    │  state.outline
    ▼
┌────────────────────────┐
│ generate_node          │  把大纲注入 system prompt 末尾
│ stream_final_answer    │  让主模型严格按段展开
└────────────────────────┘
    │
    ▼  仍未达 85% 时
┌────────────────────────┐
│ continuation 续写循环  │  最多 2 轮,在前文基础上接着写
└────────────────────────┘
```

### 触发条件

只在**写作类长请求**上启用 planner,见 `should_run_planner`:

| 条件 | 原因 |
| --- | --- |
| `intent == "chitchat"` | 业务类(knowledge/salary/personal/travel)上下文都来自结构化数据/检索片段,不需要规划 |
| `target_chars >= 500` | 低于 500 字一气呵成更快;大纲反而是开销 |
| 用户明确写"X 字" | 没字数要求时无法判断长短,默认走原直通路径 |

不满足条件的请求让 `planner_node` **pass-through**(返回 `{}` 不污染 state),所以图编排可以无脑把所有 chitchat 路径都串过它。

### 大纲格式选型

planner 输出**纯文本**而不是 JSON:

- 大纲只是给主模型读的提示,不需要结构化解析,少跑一次 parser
- 字数预算明确写出(`第 1 段(~300 字): ...`),让主模型按段配额生成
- 要求大纲本身 ≤200 字,避免规划本身吃掉太多 token

### Prompt 注入位置

大纲拼到 `stream_final_answer` 的 system prompt **末尾**(和"格式子句""长度子句"并列):

```python
f"{style_clause}{length_clause}{outline_clause}"
```

理由同 03 篇——LLM 对 recent context 的注意力比 instruction 开头更高,放末尾命中率最高。

### 与 continuation 的关系

planner 不是续写的替代,而是**前置优化**:

| 机制 | 作用 | 触发时机 |
| --- | --- | --- |
| planner | 提高首轮生成的均衡度和字数达标率 | generate_node 之前 |
| continuation | 首轮仍不达标时兜底补写 | stream_final_answer 内,首轮结束后 |

经验上加了 planner 之后 continuation 触发率显著下降(1000 字目标首轮普遍能写到 850+),但兜底逻辑保留——LLM 输出方差大,留一层保险。

## 故障安全

任意一步失败都不应该阻塞主流程:

1. **`get_chat_model()` 返回 None**(LLM 不可用):`plan_writing_outline` 返回空串
2. **planner 调用抛异常**:`planner_node` 捕获后返回 `{}`(TODO:目前异常会冒泡,见下文)
3. **outline 为空字符串**:`stream_final_answer` 走无大纲分支,行为等价于改造前

## UX 副产物

`planner_node` 经过 `_with_status` 包装后,前端会显示一条"规划写作大纲 ⏳"的步骤,让用户在长请求开头的几秒里看到进度,而不是死秒表。

## 未做项

- planner 大纲目前只送给主模型,**没流给前端**;后续可在 `planner_node` 里加 `streamer.push_thinking(outline)`,让用户看到"已规划 3 段大纲..."
- planner 失败时没有显式日志,仅静默回退
- 字数门槛 500 是经验值,不同语种/风格下可能要重新调参
- 没有缓存:同样 query 重复请求会重复跑 planner;长输出场景重复率本身不高,先不做
