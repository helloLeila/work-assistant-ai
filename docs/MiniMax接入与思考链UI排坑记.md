# MiniMax 接入与思考链 UI 排坑记

> 这一轮对话从"用户发`你好`后端 401"出发，最后落到一个能跑、有豆包风格思考链的可演示版本。
> 期间踩了**协议错配 / 流式 chunk 结构 / UI 状态机 / 首次推 GitHub 脱敏**四大类坑，全部记录如下。

---

## 一、问题地图

| # | 表象 | 根因 | 严重度 |
|---|---|---|---|
| 1 | 后端报 `invalid api key (2049)` | Token Plan 的 `sk-cp-` key 被塞到 OpenAI 协议接口去打 | 致命 |
| 2 | 切到 Anthropic 协议后空气泡转圈 | StrOutputParser 默认会把 `thinking` 块丢掉 | 高 |
| 3 | 思考链气泡里只有秒数没有思考文字 | 默认折叠，用户没点开 | 中 |
| 4 | 思考完到出完字之间无指示 | 我之前把全局"正在生成回复"删了，没补气泡内反馈 | 中 |
| 5 | 时间戳挤在气泡内，跟内容争视觉权重 | 老实现把时间贴在气泡内底部 | 低 |
| 6 | 首次推 GitHub 怕泄漏 key | `.env` 已忽略，但 `.env.bak.*`、`scripts/probe_key.py`、`.idea/`、`.codex/` 都还在工作区 | 高 |

---

## 二、问题 1：MiniMax `sk-cp-` key 401（最坑）

### 2.1 现象

`.env` 里写：
```
OPENAI_API_KEY=sk-cp-...QH4zMg
OPENAI_BASE_URL=https://api.minimaxi.com/v1
OPENAI_MODEL=abab6.5s-chat
```

后端报：
```json
{"type":"error","error":{"type":"authorized_error","message":"invalid api key (2049)","http_code":"401"}}
```

### 2.2 排查路径

写一个临时探针 `scripts/probe_key.py`，把同一个 key 同时打到 MiniMax 三个候选域名：

```python
candidates = [
    "https://api.minimaxi.com/v1",   # 国内 OpenAI 兼容
    "https://api.minimax.io/v1",     # 海外 OpenAI 兼容
    "https://api.minimax.chat/v1",   # 老海外域名
]
```

结果**全部** 401，且都返回 MiniMax 的 `request_id`——证明请求确实到了 MiniMax 集群、是它在主动拒绝。所以排除"网络打不通 / 域名不对"。

### 2.3 真正的原因

回头看 MiniMax 控制台截图，"接口密钥"页面顶部红字写得很清楚：

> 如果您想要按量计费，则使用此 API Key。如果您想通过 **Token Plan** 来使用，则需要专门使用 Token Plan 下的 API Key。

页面上有两把 key：

| 区段 | 前缀 | 用途 | 协议 |
|---|---|---|---|
| 体验中心 | `sk-api-...` | 按量计费 | **OpenAI 协议** → `api.minimaxi.com/v1` |
| Token Plan Key | `sk-cp-...` | 订阅套餐（Coding Plan） | **Anthropic 协议** → `api.minimaxi.com/anthropic` |

两类 key **互不通用**。文档原文：

> Token Plan API Key：专用于 Token Plan 套餐，文本模型按请求数量计费（5 小时滚动限额）。
> 其他开放平台的 API Key：用于按量付费访问所有 MiniMax 模型，按实际 token 消耗量计费。

更关键的是：**Token Plan 整套接口只发布了 Anthropic 协议**，官方所有调用示例都是 `anthropic.Anthropic()`，根本没有 OpenAI 协议入口。

### 2.4 解决方案

把后端从"只支持 OpenAI 协议"改成"按 provider 分派 OpenAI / Anthropic"。改动：

1. **依赖**：`requirements.txt` 加 `langchain-anthropic==1.2.0`（与 langchain 1.2.x 兼容）
2. **配置**：`backend/app/core/config.py` 加 4 个字段
   ```python
   llm_provider: str = ""           # openai / anthropic / 留空自动判断
   anthropic_api_key: str = ""
   anthropic_base_url: str = ""
   anthropic_model: str = "claude-3-5-sonnet-latest"
   ```
   并新增计算属性 `active_llm_provider`：显式指定优先，否则按 key 是否填写自动判断（Anthropic 优先）。
3. **工厂**：`backend/app/core/llm.py` 的 `get_chat_model()` 按 provider 分派 `ChatOpenAI` 或 `ChatAnthropic`。返回类型改成 `BaseChatModel | None`，调用侧因为只用 LangChain 通用接口（`prompt | llm` 管道、`astream` 等）完全无感。
4. **`.env` 迁移**：写了一次性脚本 `scripts/migrate_env_to_anthropic.py` 把 `OPENAI_API_KEY=sk-cp-...` 整体迁到 `ANTHROPIC_API_KEY` + 设 `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic` + 模型改 `MiniMax-M2.7`，原文件备份成 `.env.bak.<ts>`。

> ⚠️ Embedding 仍只走 OpenAI 协议——MiniMax Token Plan 不提供向量化接口。`.env` 把 `OPENAI_EMBEDDING_MODEL` 留空即可，知识库会自动退到本地词法检索。

---

## 三、问题 2：StrOutputParser 把 thinking 块吃掉

### 3.1 现象

切到 Anthropic 协议、key 通了之后，前端确实拿到了文本回答，但**思考块永远是空**：气泡只显示"已深度思考 3s"但没有任何思考文字，点击展开也是空。

### 3.2 排查

写个最小复现，看 ChatAnthropic 的流式 chunk 真实结构：

```python
async for chunk in (prompt | m).astream({"q": "你好"}):
    print(type(chunk.content), chunk.content)
```

输出：

```
NEW SHAPE: thinking -> {'thinking': '用户要求简短自我介绍，我应该简洁明了...', 'type': 'thinking', 'index': 0}
NEW SHAPE: thinking -> {'signature': '14d6beafe938...', 'type': 'thinking', 'index': 0}
STR chunk: '\n\n你好！我是 AI 助手...'
```

发现两件事：

1. ChatAnthropic 流式的 `chunk.content` **有时是 list of blocks（含 thinking）、有时直接是 str（文本 delta）**，混合出现。
2. `StrOutputParser` 在解析 list 形式 chunk 时**只保留 `type=='text'` 的块**，`type=='thinking'` 的块直接丢弃——这是 langchain-core 的设计：保护下游 chain 不被 reasoning 内容污染。

所以原代码 `chain = prompt | llm | StrOutputParser()` 拿到的永远是干净的文本流，思考链路上的 `push_thinking` 永远不会被调用。

### 3.3 解决方案

干掉 StrOutputParser，自己拆 chunk：

```python
# backend/app/chains/response_chain.py
async def _stream_chunk_to_streamer(chunk_content, streamer) -> str:
    visible = ""
    if isinstance(chunk_content, list):
        for block in chunk_content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "thinking":
                txt = block.get("thinking", "") or ""
                if txt:
                    await streamer.push_thinking(txt)
            elif t == "text":
                txt = block.get("text", "") or ""
                if txt:
                    visible += txt
                    await streamer.push_token(txt)
    elif isinstance(chunk_content, str):
        if chunk_content:
            visible = chunk_content
            await streamer.push_token(chunk_content)
    return visible

# 主调用：
chain = prompt | llm   # 不接 StrOutputParser
async for chunk in chain.astream(...):
    visible = await _stream_chunk_to_streamer(chunk.content, streamer)
    if visible:
        visible_chunks.append(visible)
```

这样 ChatOpenAI（chunk.content 是 str）和 ChatAnthropic（list of blocks）都能正确处理，且 thinking 走独立的 SSE 通道（`{type: "thinking", content: ...}`）。

> 🔍 **顺便发现的小坑**：thinking 块里有时只有 `signature` 没有 `thinking` 字段——那是 Anthropic 用来防伪的签名块，`block.get("thinking", "")` 会返回空，被我们的 if 判断自然过滤掉，不会污染 UI。

---

## 四、问题 3：思考块显示但点开是空 / 用户感知不到

### 4.1 现象

后端推送 thinking 事件没问题（终端日志里能看到），但用户在前端只能看到一行"已深度思考 3.0s"，点击没有展开 / 没看到内容。

### 4.2 根因

我最初设计前端组件时，`thinkingExpanded` 默认 `false`——用户不点击就看不到。但豆包是**思考期间默认展开实时滚动文字、思考完毕自动折叠**，让用户既能围观又不挡正式答案。

### 4.3 解决方案

`@/Users/leila/Documents/coding/tongtong/frontend/src/pages/WorkspacePage.vue` 里 `appendAssistantMessage()`：

```ts
thinkingExpanded: true,  // 思考期默认展开

// onToken 回调里：
if (assistantMessage.isThinking) {
  assistantMessage.isThinking = false;
  assistantMessage.thinkingEndAt = Date.now();
  assistantMessage.thinkingExpanded = false;  // 第一段正式 token 来了 → 自动收起
}
```

外加 `ChatMessageBubble.vue` 里的 250ms `setInterval` 心跳，让"思考中… 3.2s"的秒数能实时跳动。`watch(isThinking)` 控制启动/销毁定时器，避免空跑。

---

## 五、问题 4：思考完到出完字之间没有指示

### 5.1 现象

我把全局"正在生成回复"红色 `<a-tag>` 删除（觉得跟新的思考块功能重复）后，新的副作用出现了：**当思考块折叠、文字逐 token 出来时**，用户不知道是"还在出"还是"已经停了"——文字稳定 1 秒后没动，会以为已经结束。

### 5.2 解决方案

在助手气泡尾部加一个**闪烁打字光标**，仅在思考结束后到流彻底 done 之间显示。

```ts
// 类型加字段
isStreaming?: boolean;

// 创建消息时
isStreaming: true,

// onDone / onError 时
assistantMessage.isStreaming = false;
```

```vue
<span
  v-if="message.role === 'assistant' && message.isStreaming && !message.isThinking"
  class="typing-cursor"
/>
```

```css
.typing-cursor {
  display: inline-block;
  width: 8px; height: 16px;
  margin-left: 2px;
  background: currentColor;
  opacity: 0.65;
  animation: typing-blink 1s steps(2, start) infinite;
}
@keyframes typing-blink { to { visibility: hidden; } }
```

`steps(2, start)` 比 `linear` 更像真实终端光标的硬切换，不会给视觉一种"渐变呼吸灯"的廉价感。

---

## 六、问题 5：时间戳挪到气泡外

老布局把 `bubble__time` 放在 `<article class="bubble">` 内底部，灰字挤在红色气泡里很违和。改成现代 IM 风格：

```vue
<div class="bubble-row">
  <article class="bubble">...</article>
  <p class="bubble-row__time">{{ message.createdAt }}</p>
</div>
```

```css
.bubble-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bubble-row--user { align-items: flex-end; }
.bubble-row--assistant { align-items: flex-start; }
.bubble-row__time {
  font-size: 11px;
  color: rgba(15, 23, 42, 0.4);
  font-variant-numeric: tabular-nums;
}
```

`flex-direction: column` 让气泡和时间戳上下排，`align-items` 控制左右——用户消息右对齐、助手消息左对齐，时间戳跟着对齐边走。`tabular-nums` 让数字宽度一致，秒数跳动时不抖动。

---

## 七、问题 6：首次推 GitHub 的脱敏

### 7.1 风险点盘查

工作区里**潜在敏感**的位置：

| 文件/目录 | 含什么 | 处置 |
|---|---|---|
| `.env` | 真实 `sk-cp-` key | 已在 `.gitignore`，确认 staged 列表无 |
| `.env.bak.<ts>` | 迁移脚本生成的备份，含老 key | 加规则 `.env.bak.*` |
| `scripts/probe_key.py` | 调试用，会读 `.env` 真 key 直连 MiniMax | 单独 ignore |
| `scripts/migrate_env_to_anthropic.py` | 不读 key，只迁移字段 | 保留入库 |
| `backend/.idea/`、`.codex/` | IDE / AI 代理本地配置 | 全部 ignore |
| `backend/data/knowledge_index/` | Milvus 不可用时本地向量索引，启动会重建 | ignore |
| `backend/data/uploads/` | 终端用户上传文件 | ignore |
| `backend/data/chat_history.json` | 演示对话（已确认无手机号 / key） | **保留**入库 |
| `backend/data/seed_docs/` | 种子知识库文档 | **保留**入库 |
| 各 `*.py` `*.ts` `*.vue` `.md` | 源码 | grep 全文确认无 key 残留 |

旧测试文件 `backend/tests/test_llm.py` 历史版本里硬编码过真实 `sk-cp-` key（当时把它误当占位），重写时已替换为 `sk-cp-demo`、`sk-demo`。

### 7.2 验证手段

```bash
grep -rn "sk-cp-Nl\|sk-cp-2O\|QH4zMg\|SHwayo" \
  --include='*.py' --include='*.ts' --include='*.vue' --include='*.md' \
  --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ .
```

→ 0 命中。

```bash
git diff --cached -S "sk-cp-" -S "QH4zMg" --stat
```

→ 0 命中。安全。

### 7.3 最终 .gitignore（关键段）

```gitignore
# 本地环境变量与历史备份
.env
.env.bak
.env.bak.*
.env.local
.env.*.local

# 临时探针 / 一次性脚本（含真实接口探测）
scripts/probe_key.py

# IDE / 编辑器本地配置
.idea/
backend/.idea/
.vscode/
*.swp

# 本地 AI 代理工具配置
.codex/
.windsurf/

# 后端运行期产物
backend/data/knowledge_index/
backend/data/uploads/
```

---

## 八、回头看的工程教训

1. **第三方 API key 别直觉认协议**。同一个供应商可能同时提供 OpenAI / Anthropic / 自家原生三套接口，订阅类 key 经常**只支持其中一种**。文档要找"调用示例"那一节看 SDK 是哪个，别只看 base_url 域名。

2. **LangChain 的 OutputParser 是有副作用的**。`StrOutputParser` 看似只是"取个字符串"，其实会过滤 message content 里的非 text 块（thinking、tool_call、image 等）。如果你后续要拿到这些信息，直接拿 `BaseChatModel` 的原始 chunk，自己分流。

3. **后端协议切换尽量做成"可配置 + 调用侧零感知"**。本次改动 5 个 chain 文件全部不用动，因为它们调的是 `get_chat_model()` 返回的 `BaseChatModel` 抽象。这是 LangChain 价值最大的一点——把它用对。

4. **流式 UI 永远要有"还在跑"的视觉锚**。三个层级：
   - 思考阶段：秒表 + 旋转图标 + 实时文字
   - 出字阶段：闪烁打字光标
   - 全程：发送按钮 `loading=true` 禁掉重复点击

   缺一个用户都会怀疑系统挂了。

5. **首次推 GitHub 之前一律先 `git diff --cached -S` 扫敏感串**。`.gitignore` 写完容易漏掉历史备份、临时探针、IDE 配置。一次扫描省掉一辈子的尴尬。

---

## 九、关键文件索引

| 改动 | 路径 |
|---|---|
| 双协议工厂 | `backend/app/core/llm.py` |
| 配置字段 | `backend/app/core/config.py:43-60` `:128-155` |
| chunk 分流 | `backend/app/chains/response_chain.py:13-41` `:82-97` |
| SSE thinking 通道 | `backend/app/core/streaming.py:28-30` |
| 前端流式钩子 | `frontend/src/composables/useChatStream.ts:5-11` `:45-48` |
| 思考链 UI | `frontend/src/components/ChatMessageBubble.vue` |
| 消息状态机 | `frontend/src/pages/WorkspacePage.vue:159-180` `:202-239` |
| 类型 | `frontend/src/types/index.ts:17-35` |
| 一次性迁移 | `scripts/migrate_env_to_anthropic.py` |
| `.env` 模板 | `.env.example` |
| 忽略规则 | `.gitignore` |
