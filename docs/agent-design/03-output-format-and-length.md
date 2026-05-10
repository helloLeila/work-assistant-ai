# 03 · 输出格式策略 · 长度预算 · 流式渲染权衡

> 用户写"1000 字面经",模型实际只产 500-700。这不是 bug,是默认值在卡你。

## 症状一:用户要 1000 字,模型只给 500-700

发"生成 1000 字面试 LangGraph 的面经",输出明显不到 1000 字就收尾。

## 根因(按影响大小排序)

### 主因:`max_tokens`默认上限 1024

`@backend/app/core/llm.py`原本只在`enable_thinking=True`时才设置`max_tokens=8192`。chitchat / 写作类走`enable_thinking=False`分支,**完全没设**`max_tokens`,落到`langchain-anthropic`默认 1024。

中文 token 比 ≈ 1.5 字/token,理论上限 ~700 字。**模型物理上写不到 1000 字。**

### 次因:LLM 天生低估字数

GPT-4 / Claude / MiniMax 都有这个毛病——RLHF 训练数据里"100 字"实际平均 60-80 字,"1000 字"实际 500-700 字。即使解开`max_tokens`,模型仍倾向于提前收尾。

## 方案:四阶段长度治理

### Phase 1:解开`max_tokens`死结(必做)

无论 thinking 开关都设合理基线。新增配置:

```bash
ANTHROPIC_OUTPUT_TOKENS=4096      # 关 thinking 时纯答案预算
ANTHROPIC_MAX_TOKENS=8192         # 开 thinking 时总预算(thinking + 答案)
ANTHROPIC_THINKING_BUDGET=4000    # thinking 占多少
```

`get_chat_model()`总是设`max_tokens`,只是不同模式用不同值:

```python
if enable_thinking and budget > 0:
    max_tokens = max(settings.anthropic_max_tokens, budget + 2048)
else:
    max_tokens = settings.anthropic_output_tokens
```

光这一步,1000 字面经就能正常输出到 1500-2000 字范围。

### Phase 2:Prompt 工程强化(必做)

`stream_final_answer`里识别"长度敏感请求":

```python
def _detect_length_request(query: str) -> int | None:
    m = re.search(r"(\d{2,5})\s*字", query)
    return int(m.group(1)) if m else None

target = _detect_length_request(query)
length_clause = (
    f"\n\n字数要求:用户明确要求 ~{target} 字,"
    f"请按此规模充分展开,不要少于 {int(target * 0.9)} 字。"
    f"建议先列 3-5 段大纲再每段展开。"
) if target else ""
```

把`length_clause`拼到 system prompt **末尾**(LLM 对 recent context 注意力高于 instruction 开头)。

### Phase 3:自检 + Continuation(可选)

如果模型仍未达标,Claude Code 风格的"未达标续写":

```python
output = ""
async for chunk in chain.astream(...):
    output += chunk
    push_token(chunk)

iteration = 0
while len(output) < target * 0.85 and iteration < 2:
    cont_prompt = f"上面的回答只有 {len(output)} 字,距离 {target} 字还差 {target-len(output)}。请在前文基础上继续展开..."
    async for chunk in continuation_chain.astream(...):
        output += chunk
        push_token(chunk)
    iteration += 1
```

UI 上表现为"先吐一段,稍停,再继续吐"——和 Claude Code 写长文档一样的节奏。

### Phase 4:Plan-then-Write(架构升级)

终极方案:`generate_node`拆成两步:

```
generate_node
├─ if WRITING_INTENT and 估计需要长输出:
│    planner_chain: 大纲规划(轻量模型, ~500ms)
│    writer_chain:  按大纲逐段流式输出(主模型)
└─ else:
     直接流式(原逻辑)
```

接近 Claude Code 工作流,前端步骤面板自然显示"📝 规划大纲 → ✍️ 撰写第 1 段 → ..."。

---

## 症状二:模型输出 markdown,但用户只想要散文

发"生成 200 字面经",模型用`## 标题`+ 列表 + `**加粗**`,不像自然散文。

## 根因

`@backend/app/chains/response_chain.py`的 system prompt 写着:

> 答案应像真人客服一样总结要点,**必要时使用 markdown 列表**

模型当真了。对 chitchat/写作类来讲这是错配——这类应该输出自然散文。

## 方案:按 intent 选输出风格

复用`THINKING_INTENTS`分组思路:

```python
def _format_rules(intent: str) -> str:
    if intent in {"knowledge", "salary", "personal", "travel"}:
        return "格式偏好:可以使用 markdown 列表/加粗突出字段;回答业务数据时优先列点。"
    return (
        "格式偏好:用自然流畅的中文段落,**不要使用** markdown 标题(##)、"
        "无序列表(- )、加粗(**)等任何 markdown 语法,直接写散文。"
    )
```

---

## 症状三:流式期间显示`##`/`**`原文,流结束突然刷新成 HTML

`@frontend/src/components/ChatMessageBubble.vue`的优化:流式期间用`bubble__plain`渲染纯文本,`isStreaming=false`后才走 markdown 解析。

## 根因

每收到一个 token 都重新跑`marked.parse()`,长文本下 CPU 拉满 + 滚动卡顿。改成"流式 plain → 完成后 HTML"是性能上的正确选择。

## 权衡分析

| 方案 | 性能 | 视觉一致性 | 推荐度 |
|---|---|---|---|
| 每 token 重新 marked.parse | 差(O(n²)) | 实时排版 | ❌ |
| 流式 plain text → 完成后 HTML(当前) | 好 | 末尾跳变,看到`##`原文 | ⭐⭐ |
| 流式期间剥掉 markdown 符号 | 好 | 视觉平滑 | ⭐⭐⭐ |
| 段级 streaming(完整段落渲染,未完段落 plain) | 好 | 平滑 | ⭐⭐⭐⭐ |
| 让模型干脆不出 markdown(配合 intent 选风格) | 好 | 完全平滑(但只针对写作类) | ⭐⭐⭐⭐⭐ |

**当前项目最优组合**:
- 写作类(chitchat):prompt 让模型不出 markdown → 视觉天然一致
- 业务类(knowledge/...):保留 markdown,容忍少量末尾跳变
- 未来可加段级 streaming 进一步优化业务类

## 关键代码引用

- 长度配置:`@backend/app/core/config.py` `anthropic_output_tokens`
- 模型工厂:`@backend/app/core/llm.py` 默认 max_tokens 基线
- 长度解析 + 风格切换:`@backend/app/chains/response_chain.py`
- 前端流式渲染:`@frontend/src/components/ChatMessageBubble.vue` `bubble__plain` / `htmlContent`

## 未做项

- Phase 3 continuation:目前没做,期望靠 Phase 1+2 解决 95% 场景
- Phase 4 plan-then-write:架构性升级,见独立 PR
- 段级 streaming markdown:留作后续优化
- 字数检测目前只匹配中文"X 字",未识别"X 个字"/"around X words"等变体
