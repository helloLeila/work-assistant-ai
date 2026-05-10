# Agent 设计踩坑与决策记录

> 给未来的自己/接手者看,把"为什么这么写"留下来,别只留"怎么写"。

本文档汇总了`tongtong`办公助手 Agent 在迭代过程中踩过的坑、做过的设计权衡、以及对应的代码改动。每一条都尽量做到:
1. **症状**:用户/开发者实际看到的现象
2. **根因**:经过排查后定位到的真实原因
3. **方案**:采取的设计/实现
4. **未做项**:还没修但已知的问题或后续优化空间

---

## 目录

1. [Extended Thinking 与节点级状态推送](./agent-design/01-thinking-and-status.md)
2. [推理模型 vs 工具模型的分工](./agent-design/02-routing-and-model-tiers.md)
3. [输出格式、长度预算与流式渲染](./agent-design/03-output-format-and-length.md)
4. [Planner-then-Writer:长输出的两段式生成](./agent-design/04-planner-then-writer.md)

---

## 总览:Agent 流水线现状

```
用户提问
    │
    ▼
┌─────────────────────┐
│ intent_router_node  │  关键词 fast-path → LLM fallback
└─────────────────────┘  status: 理解你的问题
    │
    ├─ knowledge ─▶ knowledge_rag_node ─▶ grader_node ─▶ generate_node
    ├─ salary    ─▶ auth_check_node    ─▶ salary_query_node ─▶ generate_node
    ├─ personal  ─▶ auth_check_node    ─▶ personal_info_node ─▶ generate_node
    ├─ travel    ─▶ travel_booking_node ─▶ generate_node
    └─ chitchat  ─▶ planner_node ─▶ generate_node
                     (长字数请求规划大纲,其余 pass-through)
                                              │
                                              ▼
                                    ┌─────────────────────┐
                                    │ stream_final_answer │
                                    │  - 按 intent 切风格 │
                                    │  - extended thinking│
                                    │  - 长度自检 续写    │
                                    └─────────────────────┘
                                              │
                                              ▼
                                    hallucination_check_node ─▶ 完成
```

每个节点入口/出口都通过`SSEStreamer.push_status()`把"现在在干什么"实时推给前端,前端在思考块里渲染成步骤列表(参考[01](./agent-design/01-thinking-and-status.md))。

## 维护建议

- 新加节点时,务必走`_with_status`包装,前端 UX 才不会冷场
- 新加意图时,记得同步更新`THINKING_INTENTS`(决定是否启用思考)和输出风格策略
- prompt 里的"格式偏好""长度要求"放 system prompt **末尾**比开头更有效(LLM 对 recent context 注意力更高)
