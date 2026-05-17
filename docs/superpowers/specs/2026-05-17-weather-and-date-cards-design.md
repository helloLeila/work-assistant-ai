# 天气卡片与日期卡片设计

## 目标

把“天气”和“今天几号 / 今天星期几”从纯文本回答升级成“文本 + 结构化卡片”的稳定能力，并且满足以下约束：

- 天气首版继续基于当前 `Bocha + WeatherExtractor` 链路，不在本轮接入专门天气 API
- 天气结果在聊天区显示为 `B3` 风格的全宽结果面板
- 日期问题继续保留简洁文本，同时追加一张小信息卡
- 前端不解析正文字符串，卡片数据由后端结构化下发
- SSE 实时渲染与历史记录回放都必须保留卡片，不允许刷新后丢失
- 文档中必须包含一份可执行的 `Debug Playbook`
- 实现阶段拆成 10 个逻辑 commit，便于 review / 回滚 / 后续替换天气数据源

## 非目标

- 本轮不接入 QWeather / WeatherAPI / OpenWeather 等专门天气供应商
- 本轮不重构整套消息系统为通用 block renderer
- 本轮不把所有结构化业务结果都统一成卡片，仅覆盖天气和日期
- 本轮不追求完美多天预报抽取准确率；无法可靠提取时优先降级展示

## 当前问题

现有实现已经解决了“天气误判旧日期”和“今天几号误走联网”的关键 bug，但还存在 4 个产品级缺口：

1. 前端只能消费 `content` 和 `sources`，看不到 `weather_report`
2. 聊天历史只存正文和来源，刷新后结构化天气信息丢失
3. 天气结果仍然主要以文本呈现，信息密度和可读性有限
4. 调试路径分散，难以快速判断是 SSE、后端抽取、历史持久化还是前端渲染出了问题

## 设计决策

### 1. 采用“文本 + artifact”双轨消息模型

助手消息继续保留 `content` 文本流，用户仍然能在卡片之上看到一句自然语言摘要。同时新增 `artifacts` 字段存放结构化展示块，避免前端依赖正文字符串做二次解析。

推荐消息形态：

- `content`：适合阅读和复制的自然语言回答
- `sources`：来源列表
- `artifacts`：前端可渲染的结构化块

首版只定义两类 artifact：

- `weather_card`
- `date_card`

这样做的收益：

- 后端文本文案改动不会破坏卡片
- 将来从 Bocha 切到专门天气 API 时，前端组件可复用
- 历史记录可完整回放，不会出现“只剩文字，卡片消失”

### 2. SSE 协议新增 `artifact` 事件

当前 SSE 只有 `token / thinking / status / progress / trace / source / done / error`。本轮新增：

- `artifact`

推荐载荷：

```json
{
  "type": "artifact",
  "artifact": {
    "kind": "weather_card",
    "version": 1,
    "data": {
      "...": "..."
    }
  }
}
```

设计原则：

- 文本 token 继续按现有方式流式输出
- 结构化卡片在后端有稳定数据后一次性下发
- 单条助手消息允许挂多个 artifact
- artifact 必须可持久化到历史记录并在刷新后恢复

### 3. 聊天历史新增 `artifacts`

当前 `HistoryTurn` 只有：

- `role`
- `content`
- `created_at`
- `sources`

本轮扩展为：

- `artifacts: list[MessageArtifact]`

历史接口和前端本地消息模型同步扩展，保证以下两个场景都可用：

1. SSE 首次实时渲染
2. 页面刷新后通过 `/chat/history` 重建消息列表

### 4. 天气卡片使用 B3 控制台信息板

聊天区保留当前对话流布局，但天气不再只是一段文本。助手消息展示顺序固定为：

1. 一句天气摘要文本
2. `B3` 全宽天气卡片
3. 来源折叠区

`B3` 的原因：

- 与当前 Workspace 页的办公后台气质一致
- 视觉上足够稳定，不会像单独天气 App 突然插入办公系统
- 后续增加更多字段或切供应商时扩展成本低

### 5. 日期问题使用“文本 + 小卡”

`今天几号 / 今天星期几 / 今天是几号` 继续先输出文本：

```text
今天是 2026年05月17日，星期日。
```

然后在同一条助手消息下追加一张小型信息卡，字段包括：

- 标题：今天
- 完整日期
- 星期
- 时区：`Asia/Shanghai`

这样既保留快速扫读的文本，又让日期能力在视觉上与天气卡片统一。

### 6. 本轮实现默认写详细注释

这轮改动跨越：

- SSE 协议
- 后端状态与持久化
- 前端消息模型
- 条件渲染与历史回放

这些位置后续最容易成为排障入口，因此本轮实现要求新代码和关键改动必须带详细注释，尤其要解释：

- 为什么要新增某个字段或事件
- 数据从哪个节点流到哪个节点
- 哪些分支是实时渲染使用，哪些分支是历史回放使用
- 为什么某些降级场景只显示文本不显示卡片
- 哪些地方是未来切专门天气 API 时的替换点

注释重点文件：

- `backend/app/core/streaming.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/history_service.py`
- `backend/app/nodes/web_search_node.py`
- `backend/app/nodes/generate_node.py`
- `frontend/src/composables/useChatStream.ts`
- `frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/ChatMessageBubble.vue`
- 新增的天气/日期卡片组件

## 结构化数据设计

### WeatherCard

```ts
type MessageArtifact =
  | { kind: "weather_card"; version: 1; data: WeatherCardData }
  | { kind: "date_card"; version: 1; data: DateCardData }

type WeatherCardData = {
  city: string
  relativeDayLabel: string
  forecastDate: string
  weekdayLabel: string
  summary: string
  currentTempC?: number | null
  tempLowC?: number | null
  tempHighC?: number | null
  feelsLikeC?: number | null
  windText?: string
  airQuality?: string
  humidity?: string
  precipitation?: string
  uvIndex?: string
  sourceName: string
  sourceUrl?: string
  forecastItems: Array<{
    date: string
    weekdayLabel: string
    relativeDayLabel: string
    condition: string
    tempLowC?: number | null
    tempHighC?: number | null
  }>
  completeness: {
    hasCurrent: boolean
    hasForecast: boolean
    missingFields: string[]
  }
}
```

字段规则：

- 当前气温优先显示；没有则退化成最高/最低温
- 湿度、降水、紫外线拿不到时显示 `暂无`
- `forecastItems` 最多 3 条
- 如果完全提取不到未来 3 天，卡片底部仍保留区域，但显示“暂未提取到后续 3 天天气”

### DateCard

```ts
type DateCardData = {
  title: string
  dateText: string
  weekdayLabel: string
  timezone: string
}
```

## 后端设计

### 1. `web_search_node` 继续负责天气查询入口

天气链路保持不变：

- query 判定为天气
- IP 定位增强城市
- Bocha 查询使用 `freshness="oneDay"`
- `WeatherExtractor` 做日期校验、字段归一化、来源择优

新增职责：

- 生成 `weather_card` artifact 数据
- 把 artifact 放入 `structured_data` 或单独状态字段，供流式和历史持久化使用

### 2. `WeatherExtractor` 扩展未来 3 天抽取

当前 extractor 已能稳定抽：

- 日期
- 天气
- 当前 / 高低温
- 风力
- 空气质量

本轮扩展目标：

- 尝试从同一命中的天气摘要里抽取最多 3 天后续预报
- 只接受日期连续且不早于目标日的数据
- 无法可靠抽取时，不返回伪造 forecast

抽取原则：

- `today` 命中必须精确等于目标日期
- 未来 3 天只能来自同一条可信天气结果或同一批连续天气结果
- 来源可信度规则延续当前实现

### 3. 日期卡由本地时间快路径直接生成

`generate_node` 当前已具备本地时间 fast-path。本轮扩展：

- 在返回日期文本的同时生成 `date_card`
- 日期卡不经过模型，不依赖网络，不依赖搜索结果

### 4. `SSEStreamer` 扩展 `push_artifact`

新增方法：

```python
async def push_artifact(self, artifact: dict[str, Any]) -> None:
    ...
```

ChatService 在图执行完成后，按消息顺序把 artifacts 推给前端。要求：

- 允许 0..N 个 artifacts
- 不影响已有 token/source 事件
- 出错时不因为卡片事件失败而中断整条文本回答

### 5. 历史记录持久化 `artifacts`

`HistoryService.append_turn()` 增加 `artifacts` 入参，`ChatTurn` / `HistoryTurn` 模型同步扩展。

持久化原则：

- 助手消息写入时正文、sources、artifacts 一起落盘
- 历史接口直接返回 artifact，不让前端重新推导

## 前端设计

### 1. 扩展消息模型

`ChatMessage` 与 `HistoryTurn` 新增：

- `artifacts?: MessageArtifact[]`

### 2. SSE 客户端处理 `artifact`

`openChatStream()` 新增：

- `onArtifact`

当前消息流中，前端把 artifact 追加到当前 assistant message。

### 3. ChatMessageBubble 保持主气泡不重构

不做通用 block renderer 大改造。本轮仅在 `ChatMessageBubble` 中增加一个 artifact 区：

- 正文下方
- 来源上方

渲染顺序：

1. 思考块
2. 正文
3. artifact 区
4. 来源

### 4. 新增两个展示组件

- `WeatherArtifactCard.vue`
- `DateArtifactCard.vue`

职责：

- `WeatherArtifactCard`：渲染 B3 风格的全宽天气面板
- `DateArtifactCard`：渲染简洁的小型日期卡

### 5. B3 天气卡片内容布局

固定结构：

- 顶部：城市、相对日期、完整日期、星期
- 右上：当前气温或主温度
- 中部：概况（天气、最高/最低温）
- 指标区：体感、风力、空气质量、湿度、降水、紫外线
- 底部：未来 3 天小卡片
- 尾部：来源

可用性规则：

- 缺字段显示 `暂无`
- 未来 3 天无可靠数据时，显示占位说明，不隐藏整张卡

## 失败降级

### 天气

- 有文本、无 artifact：至少展示文本，不显示空白卡片
- artifact 缺字段：单字段回退为 `暂无`
- 无法提取未来 3 天：显示“暂未提取到后续 3 天天气”
- 搜索失败或结果不可信：沿用当前不可用提示，不渲染天气卡片

### 日期

- 日期文本一定可用
- 若日期卡片构造失败，仍保留文本，不影响对话

### 历史

- 历史里没有 artifact 的旧消息按纯文本渲染
- 前端必须兼容“新旧历史格式并存”

## Debug Playbook

### 1. 先看原始 SSE，不先猜前端

浏览器打开：

- `DevTools -> Network -> /api/chat/stream -> Response`

按顺序检查：

1. 有没有 `token`
2. 有没有 `artifact`
3. 有没有 `source`
4. 有没有 `error`

判断规则：

- 有 `artifact`，页面没卡片：前端渲染问题
- 没 `artifact`，但有天气文本：后端结构化构造问题
- 没文本也没卡片：后端路由 / 图编排 / 流式链路问题
- 只有 `error`：直接回后端异常处理链路查

建议你在浏览器里至少盯住这些事件顺序：

```text
status(intent running)
status(intent done)
status(web_search running)
progress(web_search ...)
artifact(weather_card/date_card)
source(...)
done
```

如果你看到：

- `token` 有，但没有 `artifact`
  说明文本回答通了，但卡片数据没构造出来
- `artifact` 有，但页面没显示
  说明前端接收到了，但没挂到消息对象或没渲染
- `artifact` 和页面都正常，但刷新后消失
  说明历史持久化或历史回放映射有问题

### 1.1 怎么看 SSE Response 里到底发了什么

对你后面自己调试最重要的是这个顺序：

1. 打开浏览器开发者工具
2. 切到 `Network`
3. 发送 `深圳天气` 或 `今天几号`
4. 点开 `/api/chat/stream`
5. 看 `Response`

你会看到类似：

```text
data: {"type":"status","step":"intent","label":"理解需求","state":"running"}

data: {"type":"status","step":"intent","label":"理解需求","state":"done"}

data: {"type":"artifact","artifact":{"kind":"weather_card","version":1,"data":{"city":"深圳"}}}

data: {"type":"token","content":"深圳"}

data: {"type":"token","content":"今天"}

data: {"type":"done"}
```

这里不要先看页面长什么样，先确认：

- 有没有 `artifact`
- `artifact.kind` 是不是你期待的 `weather_card` / `date_card`
- `artifact.data` 字段是不是完整
- 有没有 `done`

### 1.2 怎么判断是“后端没发”还是“前端没接住”

看 3 个层次：

1. `Network Response`
   - 有 `artifact`：后端已经发出来了
   - 没 `artifact`：后端没发
2. 前端消息对象
   - 有 `artifact`，但 `assistantMessage.artifacts` 里没有：前端消费逻辑有问题
3. Vue 模板
   - `assistantMessage.artifacts` 有值，但 UI 没显示：组件渲染逻辑有问题

### 1.3 前端怎么直接看当前消息对象

本轮实现后，建议保留一段非常明确的开发期调试代码或注释，方便你以后临时打开。例如在 `WorkspacePage.vue` 的 SSE 接收位置附近可以临时加：

```ts
console.log("[artifact event]", payload)
console.log("[assistant message after artifact]", structuredClone(assistantMessage))
```

重点看：

- `assistantMessage.content`
- `assistantMessage.sources`
- `assistantMessage.artifacts`

如果 `artifacts` 数组里已经有：

```ts
{ kind: "weather_card", version: 1, data: { ... } }
```

但页面没卡片，那就不要再查后端，直接查：

- `ChatMessageBubble.vue`
- `WeatherArtifactCard.vue`
- `DateArtifactCard.vue`

### 1.4 前端怎么判断是实时渲染问题还是历史回放问题

这个很关键，必须分开测。

测试顺序：

1. 新发一条 `深圳天气`
2. 当场看卡片有没有显示
3. 刷新页面
4. 再看同一条历史消息有没有卡片

结果判断：

- 当场没有，刷新后也没有
  说明 SSE 或后端 artifact 构造有问题
- 当场有，刷新后没有
  说明历史持久化或 `selectSession()` 映射有问题
- 当场没有，刷新后反而有
  说明实时 SSE 接收逻辑有问题，历史接口是好的
- 两边都有
  说明整条链路通了

### 2. 调试天气链路

最小复现 query：

- `天气`
- `深圳天气`
- `明天深圳天气`

检查顺序：

1. `intent_chain` 是否走到天气路径
2. `web_search_node` 是否拿到 `freshness="oneDay"`
3. `WeatherExtractor` 是否产出 `weather_report`
4. artifact 构造是否成功
5. SSE 是否发出 `artifact`
6. 历史记录是否写入 `artifacts`

推荐你以后固定用这几个 query 回归：

- `天气`
- `深圳天气`
- `明天深圳天气`
- `天津天气`

每个 query 都按这张排查表查：

1. 输入后有没有马上出现 assistant message 空壳
2. SSE 里有没有 `web_search` 的 `status/progress`
3. `artifact(weather_card)` 有没有到
4. `weather_card.data.city` 对不对
5. `forecastDate` 对不对
6. `forecastItems` 有没有 3 条，或有没有明确缺失说明
7. 文本摘要和卡片字段是不是一致

### 2.1 天气问题定位表

#### 情况 A：有天气文本，没天气卡

优先排查：

- `web_search_node` 有没有把 `weather_card` 写进状态
- `ChatService` 有没有把 artifact push 到 SSE
- `HistoryService` 有没有接收 artifact

#### 情况 B：天气卡有了，但字段很少

优先排查：

- `WeatherExtractor` 是否没抽到字段
- 卡片数据构造层是否把空值直接丢了
- 前端组件是否把 `暂无` 字段过滤掉了

#### 情况 C：今天的天气显示成昨天

优先排查：

- `WeatherExtractor._pick_matching_date`
- `forecastDate`
- `relativeDayLabel`
- 卡片是不是拿错了历史数据

#### 情况 D：未来 3 天全空

优先排查：

- 搜索摘要里是否本来就没有未来 3 天
- extractor 是否只抽到了当天
- 卡片是否正确显示“暂未提取到后续 3 天天气”

### 3. 调试日期链路

最小复现 query：

- `今天几号`
- `今天星期几`
- `今天是几号`

检查顺序：

1. `intent_chain` 是否命中本地日期 fast-path
2. `generate_node` 是否直接生成文本
3. 是否同时生成 `date_card`
4. SSE 是否下发 `artifact`
5. 历史记录是否保留 `date_card`

推荐固定回归：

- `今天几号`
- `今天星期几`
- `今天是几号`
- `今天周几`

预期永远应该是：

- 不走联网天气搜索
- 不依赖主模型
- 有文本
- 有 `date_card`
- 刷新后仍存在

### 3.1 日期问题定位表

#### 情况 A：文本对，卡片没有

说明本地 fast-path 是通的，但 artifact 构造或传输有问题。

#### 情况 B：卡片有，文本不对

说明文本模板和卡片构造拿的时间源不一致，要查：

- `generate_node` 的本地时间函数
- `date_card` 构造函数

#### 情况 C：刷新后日期卡没了

直接查历史：

- `HistoryService.append_turn`
- `/chat/history`
- `selectSession()` 映射

### 4. 调试历史回放

重点验证两件事：

1. 新发一条天气消息后，页面内实时卡片能否显示
2. 刷新页面后，同一条历史消息的卡片能否恢复

如果“实时有，刷新没了”，优先查：

- `HistoryService.append_turn`
- `/chat/history` 返回模型
- 前端 `selectSession()` 的消息映射

建议你后面直接去 `backend/data/chat_history.json` 看落盘原文。你要确认某条 assistant turn 里除了：

- `content`
- `sources`

还应该有：

- `artifacts`

如果 JSON 里没有 `artifacts`，就不是前端问题。

### 4.1 你自己看历史 JSON 时要重点看什么

找到刚发完的那条 assistant 消息，检查：

```json
{
  "role": "assistant",
  "content": "深圳今天多云，20°C~26°C，南风3级。",
  "sources": [...],
  "artifacts": [
    {
      "kind": "weather_card",
      "version": 1,
      "data": {
        "city": "深圳",
        "forecastDate": "2026-05-17"
      }
    }
  ]
}
```

如果这里：

- `content` 有，`artifacts` 没有：后端持久化没写进去
- `artifacts` 有，但前端历史页没显示：前端历史映射或组件问题

### 5. 推荐测试清单

后端：

- `test_weather_extractor.py`
- `test_web_search_node.py`
- `test_generate_node.py`
- `test_chat_stream_api.py`
- 新增历史持久化测试

前端：

- artifact 事件处理测试
- `ChatMessageBubble` 条件渲染测试
- `WeatherArtifactCard` / `DateArtifactCard` 渲染测试
- 历史回放测试

### 5.1 建议你以后固定执行的命令

后端：

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_weather_extractor.py -q
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_web_search_node.py -q
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_generate_node.py -q
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_chat_stream_api.py -q
```

如果你改了历史记录：

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_chat_stream_api.py -q
```

前端如果后面补了组件测试，建议固定跑：

```bash
npm test
```

或者只跑天气/日期相关测试。

### 5.2 建议你加的临时调试日志位置

后端建议临时打点位置：

- `web_search_node`：构造 `weather_card` 前后
- `generate_node`：构造 `date_card` 前后
- `chat_service`：`push_artifact` 前
- `history_service`：assistant turn 落盘前

前端建议临时打点位置：

- `useChatStream.ts`：收到 `artifact` 时
- `WorkspacePage.vue`：把 artifact 挂到 `assistantMessage` 时
- `ChatMessageBubble.vue`：进入 artifact 渲染分支时

每次排障时，优先看“数据有没有到”，再看“页面为什么没画出来”。

## 风险与取舍

### 1. Bocha 不是专门天气源

风险：

- 湿度、降水、紫外线、未来 3 天不一定稳定可提取

取舍：

- 首版允许展示 `暂无`
- 结构化 schema 先定住，后面切专门天气 API 时前端不变

### 2. 历史模型升级

风险：

- 旧消息没有 artifact，新消息有 artifact

取舍：

- 采用向后兼容的可选字段
- 前端统一做空值兼容

### 3. 不做完整 block renderer

风险：

- `ChatMessageBubble` 里会多一层条件渲染

取舍：

- 这轮工作量可控
- 后续如果更多结构化卡片出现，再单独做 block 化重构

## 影响范围

后端：

- `backend/app/models/domain.py`
- `backend/app/models/chat.py`
- `backend/app/core/streaming.py`
- `backend/app/services/history_service.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/weather_extractor.py`
- `backend/app/nodes/web_search_node.py`
- `backend/app/nodes/generate_node.py`
- 相关测试

前端：

- `frontend/src/types/index.ts`
- `frontend/src/composables/useChatStream.ts`
- `frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/ChatMessageBubble.vue`
- 新增天气/日期卡片组件
- 相关测试

文档：

- 本设计文档
- 后续实现计划文档
- 调试说明

## 验证标准

1. `深圳天气` 返回摘要文本 + B3 天气卡片
2. 天气卡片在刷新页面后仍能从历史记录恢复
3. `今天几号` / `今天星期几` 返回文本 + 日期卡
4. 前端不依赖正文字符串解析卡片
5. SSE Response 中能看到 `artifact` 事件
6. 旧历史消息在无 artifact 情况下仍正常显示
7. `Debug Playbook` 可按步骤区分是 SSE、后端、历史还是前端问题

## 实现约束

实现阶段必须拆成 10 个逻辑 commit。推荐边界如下：

1. 模型与协议类型
2. SSE artifact 事件
3. 历史持久化 artifacts
4. 日期卡后端产出
5. 天气卡结构与后端产出
6. 天气 extractor 扩展未来 3 天
7. 前端类型与 SSE 消费
8. 日期卡组件与接线
9. 天气卡组件与接线
10. 文档、调试说明与回归测试收尾

这样可以保证每个 commit 都有清晰职责，并为后续切换专门天气 API 保留稳定的前端协议。

## 代码注释约束

本轮实现必须显式写出详细注释，尤其在以下地方：

- 新增的 SSE `artifact` 协议
- assistant message 上 `artifacts` 的实时接收和历史回放
- 天气卡片字段为什么允许 `暂无`
- 未来 3 天天气为什么有时只显示缺失说明
- 日期文本与日期卡为什么必须共享同一个本地时间源
- 调试日志建议保留在哪些位置，为什么这些位置最适合定位问题

要求达到的效果是：你过一段时间再回来看，不需要重新推断“这段代码为什么这样写”，直接靠注释和文档就能顺着数据流查问题。
