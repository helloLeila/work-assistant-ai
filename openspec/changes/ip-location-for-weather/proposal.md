## Why

### 问题：用户说"天气"，返回的是全国各地的天气网页大杂烩

当前 `web_search_node` 直接把原始 query `"天气"` 传给 Bocha。Bocha 是通用搜索引擎，返回的是含"天气"关键词的网页，不区分城市：

| 返回结果 | 城市 | 天气信息 |
|---|---|---|
| 和风天气 - Pribinic | 白俄罗斯 | 17° 阵雨 |
| 和风天气 - Sturlic | 波黑 | 14° 阵雨 |
| 腾讯新闻 | 不显示 | 18-24°C 阴 |
| 新京报 | 北京 | 20-31°C 晴转多云 |
| 新京报 | 北京 | 多云有雷阵雨 |

模型面对 5 条不同城市的天气素材，无法判断用户想问哪里，只能含糊回答或罗列多个城市。

### 用户不会说"北京今天天气怎么样"

成熟产品（Siri/小爱/百度）的标准做法是：**用用户 IP 反查所在城市，自动补全地理位置**。用户只说"天气"两个字，系统也能给出当地天气。

### 当前架构缺少 IP→城市的链路

- `chat_stream` 接口不接收 `Request` 对象，拿不到 `client.host`
- `GraphState` 没有 `client_ip` 字段
- `web_search_node` 没有 IP 定位能力
- 搜索词永远是原始 query，没有任何增强

## What Changes

### A. Stream 入口层

| 项目 | Before | After |
|---|---|---|
| `chat_stream` / `chat_stream_get` 签名 | 只接收 `payload` / `Query` + `current_user` | 新增 `request: Request` 参数 |
| IP 提取 | 无 | 从 `request.client.host` 读取，优先取 `X-Forwarded-For`（适配反向代理） |
| IP 传递 | 无 | 传给 `create_stream_generator(client_ip=...)` |

### B. ChatService 层

| 项目 | Before | After |
|---|---|---|
| `run_streaming_chat` 签名 | `session_id, query, current_user, streamer` | 新增 `client_ip: str \| None = None` |
| `create_stream_generator` 签名 | `session_id, query, current_user` | 新增 `client_ip: str \| None = None` |
| GraphState 初始化 | 无 IP 字段 | 注入 `"client_ip": client_ip` |

### C. GraphState 层

| 项目 | Before | After |
|---|---|---|
| `GraphState` 字段 | 无 client_ip | 新增 `client_ip: str`（可选） |

### D. IP 定位服务层（新增）

| 项目 | Before | After |
|---|---|---|
| IP→城市服务 | 无 | 新增 `app/services/ip_location_service.py` |
| 定位提供商 | 无 | `ip-api.com`（免费，无需 key，中文支持） |
| 缓存 | 无 | `@lru_cache` 缓存同一 IP 的城市结果，减少重复调用 |
| 超时/降级 | 无 | 2s 超时，失败时返回 `None`（不阻塞主链路） |
| 隐私处理 | 无 | 仅传 IP 前 3 段（如 `192.168.1.x`）到外部服务，最后一段掩码保护 |

### E. WebSearch 增强层

| 项目 | Before | After |
|---|---|---|
| 搜索词 | 原始 query | 若 query 含"天气/气温/温度/forecast"且无城市名，自动拼接 `f"{city} {query}"` |
| 拼接时机 | 无 | `web_search_node` 调用 Bocha 前，先用 `_augment_query(query, client_ip)` 增强 |
| 用户感知 | 无 | push progress 显示 `"已定位到 {city}，正在搜索当地天气"` |
| 定位失败 | 无 | 降级为原始 query，push progress `"未获取到位置，搜索全国天气信息"` |

## 兼容性 / BREAKING 分析

**无 BREAKING**：
- `client_ip` 全链路都是可选参数，`None` 时行为与之前完全一致
- IP 定位失败（超时/服务不可用）时降级为原始 query，不影响任何现有路径
- `ip-api.com` 是免费服务，不引入付费依赖或配置项

**隐私合规**：
- 仅对"天气"类 query 做 IP 定位，其他 query 不走定位逻辑
- IP 最后一段掩码处理（`192.168.1.xxx`）
- 不存储 IP 城市映射到数据库或日志

## Capabilities

### New Capabilities
- `ip-location`：IP 到城市的定位能力，定义服务接口、缓存策略、超时降级、隐私处理
- `query-augmentation`：搜索词增强能力，定义触发条件（天气类 intent）、拼接规则、用户感知文案

### Modified Capabilities
- `web-search`：搜索词从原始 query 改为增强后的 query，增加定位成功/失败的 SSE progress 事件

## Impact

**代码**
- `backend/app/api/routes/chat.py`：新增 `Request` 参数，提取 client IP
- `backend/app/services/chat_service.py`：`run_streaming_chat` / `create_stream_generator` 新增 `client_ip` 参数
- `backend/app/agents/office_assistant_graph.py`：`GraphState` 新增 `client_ip` 字段
- `backend/app/services/ip_location_service.py`：**新增**
- `backend/app/nodes/web_search_node.py`：新增 query 增强逻辑，调用 IP 定位服务

**依赖**
- 新增 Python：`httpx`（已有，Bocha 已引入）
- 外部服务：`ip-api.com`（免费，无 key）

**配置**
- 无需新增 `.env` 配置项

**测试**
- 新增 `test_ip_location_service.py`（mock httpx）
- 新增 `test_web_search_node.py` 中 query 增强分支的用例
