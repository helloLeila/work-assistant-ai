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

### 4. 调试历史回放

重点验证两件事：

1. 新发一条天气消息后，页面内实时卡片能否显示
2. 刷新页面后，同一条历史消息的卡片能否恢复

如果“实时有，刷新没了”，优先查：

- `HistoryService.append_turn`
- `/chat/history` 返回模型
- 前端 `selectSession()` 的消息映射

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
