# IP 定位增强天气搜索 — 设计文档

## 背景

用户说"天气"两个字时，Bocha 通用搜索引擎返回的是全国各地的天气网页大杂烩（Pribinic、Sturlic、北京...），模型无法判断用户想问哪个城市。成熟产品（Siri/小爱/百度）的标准做法是用用户 IP 反查所在城市，自动补全地理位置。

## 目标

- 用户只说"天气"，系统自动定位到用户所在城市，搜索"北京 天气"
- 定位失败时不阻塞主链路，降级为原始 query
- 不引入付费依赖，不新增配置项

## 架构图

```
用户说"天气"
    │
    ▼
┌─────────────────────┐
│ FastAPI chat_stream │  X-Forwarded-For → X-Real-IP → request.client.host
│                     │  剔除内网代理段 → 提取真实公网 IP
└─────────────────────┘
    │
    ▼ client_ip
┌─────────────────────┐
│   ChatService       │  透传 client_ip → GraphState
└─────────────────────┘
    │
    ▼ state["client_ip"]
┌─────────────────────┐
│  web_search_node    │  检测 query 是否含天气关键词
│                     │  是 → 调用 ip_location_service 查城市（5min TTL 缓存）
│                     │  拼接搜索词: "深圳 天气"
│                     │  否 → 原始 query，不走定位
│                     │  限流超限时 → 直接跳过定位
└─────────────────────┘
    │
    ▼ "深圳 天气"
┌─────────────────────┐
│   Bocha API         │  返回深圳当地的天气网页
└─────────────────────┘
```

## 关键设计决策

### 1. IP 定位服务选型：ip-api.com

| 方案             | 优点                             | 缺点                        | 结论     |
| ---------------- | -------------------------------- | --------------------------- | -------- |
| ip-api.com       | 免费、无需 key、支持中文、响应快 | 有速率限制（150 req/min）   | **选中** |
| 淘宝 IP 库       | 国内速度快                       | 需要注册、API 不稳定        | 放弃     |
| 高德 IP 定位     | 准确度高                         | 需要 key、有配额限制        | 放弃     |
| MaxMind GeoLite2 | 离线、隐私好                     | 需要定期更新 DB、准确度一般 | 过重     |

ip-api.com 的接口：`http://ip-api.com/json/{ip}?lang=zh-CN`
响应示例：
```json
{
  "status": "success",
  "country": "中国",
  "regionName": "北京",
  "city": "北京",
  "query": "123.45.67.89"
}
```

### 2. 隐私处理

- 仅对"天气"类 query 触发 IP 定位，其他 query 不调用
- 调用 ip-api.com 时，IP 最后一段掩码：`192.168.1.0`（传前 3 段）
- 不存储 IP→城市映射到数据库或持久化日志
- 缓存使用内存 TTL 缓存（5 分钟），进程重启即清空

### 3. 触发条件

query 增强只在以下条件同时满足时触发：
1. `client_ip` 不为空（且不是内网/回环地址）
2. query 包含天气关键词（口语化覆盖）：
   - 核心词：`天气`、`气温`、`温度`、`forecast`
   - 口语化：`冷不冷`、`热不热`、`下雨`、`下雪`、`刮风`、`台风`、`雾霾`、`空气质量`、`穿衣指数`、`紫外线`
   - 时间修饰：`今天`、`明天`、`后天`、`下周`、`最近` + 天气相关词
3. query **不包含**已知城市名（避免重复拼接）

已知城市名列表用简化的常见城市名覆盖 90% 场景：北京、上海、广州、深圳、杭州、成都、武汉、西安、南京、重庆、天津、苏州、长沙、郑州、青岛、大连、厦门、昆明、哈尔滨、沈阳、济南、无锡、宁波、佛山、东莞、石家庄、太原、合肥、南昌、福州、南宁、贵阳、兰州、海口、乌鲁木齐、拉萨、银川、西宁、呼和浩特、长春。

### 4. 超时与降级

```
IP 定位调用 → 2s 超时
  ├── 成功 → 拼接 "{city} {query}" → 搜索
  └── 失败/超时 → 原始 query → push "未获取位置，搜索全国天气"
```

### 5. 用户感知

定位成功时：
```
已定位到深圳，正在搜索当地天气
正在调用 Bocha 搜索「深圳 天气」
已找到 5 条线索
```

定位失败时：
```
未获取到位置信息，搜索全国天气
正在调用 Bocha 搜索「天气」
已找到 5 条线索
```

## 接口变更

### chat.py

```python
from fastapi import Request

def _extract_client_ip(request: Request) -> str | None:
    """提取用户真实公网 IP，适配反向代理部署。"""
    # 优先取反向代理透传的真实 IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For 可能是逗号分隔的多级代理链，取第一个（最靠近用户）
        ip = forwarded.split(",")[0].strip()
        if not _is_private_ip(ip):
            return ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip and not _is_private_ip(real_ip.strip()):
        return real_ip.strip()

    # 直连场景
    if request.client and request.client.host:
        host = request.client.host
        if not _is_private_ip(host):
            return host

    return None


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,  # 新增：注入 HTTP 请求对象，用于提取客户端 IP
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    # 从请求头中提取客户端真实 IP（适配反向代理、云服务等场景）
    client_ip = _extract_client_ip(request)
    # 创建流式聊天生成器，传入客户端 IP 用于后续的地理位置和天气查询
    generator = get_chat_service().create_stream_generator(
        session_id=payload.session_id,
        query=payload.query,
        current_user=current_user,
        client_ip=client_ip,  # 新增：客户端 IP，用于获取用户位置信息
    )
    # 返回 SSE 流式响应
    return StreamingResponse(generator, media_type="text/event-stream")
```

GET 版同理。

### chat_service.py

```python
async def run_streaming_chat(
    self,
    *,
    session_id: str,  # 输入：会话 ID，用于标识当前聊天会话
    query: str,  # 输入：用户的查询内容或问题
    current_user: CurrentUser,  # 输入：当前用户对象，包含用户的身份信息
    streamer: SSEStreamer,  # 输入：SSE 流式响应生成器，用于发送实时消息
    client_ip: str | None = None,  # 输入：客户端 IP 地址，可选，用于定位用户地理位置
) -> None:
    ...
    state = await self._graph.ainvoke(
        {
            "session_id": session_id,  # 输入：会话 ID
            "query": query,  # 输入：用户查询
            "current_user": current_user,  # 输入：当前用户信息
            "client_ip": client_ip,  # 输入：客户端 IP 地址
            "retry_count": 0,  # 输入：重试次数，初始为 0
        },
        ...
    )  # 输出：聊天生成器的状态对象，包含会话的中间状态和结果
```

### GraphState

```python
class GraphState(TypedDict, total=False):
    session_id: str
    query: str
    current_user: CurrentUser
    client_ip: str | None  # 新增
    ...
```

## 新增模块

### ip_location_service.py

```python
import ipaddress
import time
from collections import deque

class IPLocationService:
    """IP 到城市的定位服务。

    - 仅传 IP 前 3 段（如 192.168.1.0）保护隐私
    - 5 分钟 TTL 内存缓存，IP 变动或切换网络后自动过期
    - 进程内分钟级计数器，ip-api 150 req/min 限流超限时直接跳过
    - 标准内网段（10/8, 172.16/12, 192.168/16, 127/8）直接返回 None
    - 2s 超时，失败不阻塞主链路
    """

    def __init__(self):
        self._cache: dict[str, tuple[str, float]] = {}  # ip -> (city, timestamp)
        self._ttl_seconds = 300  # 5 分钟
        self._rate_limit = 150   # ip-api 免费层限制
        self._window_seconds = 60
        self._call_times: deque[float] = deque()

    def _is_private_ip(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            return True

    def _mask_ip(self, ip: str) -> str:
        """掩码最后一段：192.168.1.89 -> 192.168.1.0"""
        parts = ip.split(".")
        if len(parts) == 4:
            parts[3] = "0"
            return ".".join(parts)
        return ip

    def _is_rate_limited(self) -> bool:
        now = time.time()
        # 清理过期窗口
        while self._call_times and self._call_times[0] < now - self._window_seconds:
            self._call_times.popleft()
        return len(self._call_times) >= self._rate_limit

    def _get_cached(self, masked_ip: str) -> str | None:
        if masked_ip in self._cache:
            city, ts = self._cache[masked_ip]
            if time.time() - ts < self._ttl_seconds:
                return city
            del self._cache[masked_ip]
        return None

    async def lookup(self, ip: str) -> str | None:
        if self._is_private_ip(ip):
            return None

        masked = self._mask_ip(ip)

        # 先读缓存
        cached = self._get_cached(masked)
        if cached is not None:
            return cached

        # 限流检查
        if self._is_rate_limited():
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://ip-api.com/json/{masked}?lang=zh-CN",
                    timeout=2.0,
                )
                self._call_times.append(time.time())
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    city = data.get("city")
                    if city:
                        self._cache[masked] = (city, time.time())
                        return city
        except (httpx.HTTPError, TimeoutError):
            pass
        return None
```

### web_search_node 增强

```python
async def web_search_node(state: dict, runtime) -> dict:
    query = state["query"] #用于访问必须存在的字段，确保程序逻辑的正确性。
    client_ip = state.get("client_ip") #属于可选字段，程序可以在没有它的情况下继续运行，因此用 state.get

    # 天气类 query 自动拼接城市
    augmented_query = await _augment_query(query, client_ip)
    if augmented_query != query:
        await streamer.push_progress(
            step="web_search",
            detail=f"已定位到城市，正在搜索「{augmented_query[:30]}」",
        )

    result = await service.search(augmented_query, ...)
    ...

async def _augment_query(query: str, client_ip: str | None) -> str:
    if not client_ip or not _is_weather_query(query):
        return query
    if _contains_city_name(query):
        return query  # 如果用户已指定城市，不重复拼接
    city = await get_ip_location_service().lookup(client_ip)
    if city:
        return f"{city} {query}" # 拼接城市+查询结果
    return query
```

## 测试策略

1. **IP 定位服务单测**：mock httpx，测试成功/失败/超时/私有 IP 四种场景
2. **query 增强单测**：测试含城市名/不含城市名/非天气 query 三种分支
3. **集成测试**：端到端验证"天气"→"北京 天气"的完整链路（mock IP 定位）

## 风险 

| 风险                               | 概率 | 影响                     | 缓解                                                          |
| ---------------------------------- | ---- | ------------------------ | ------------------------------------------------------------- |
| ip-api.com 服务不可用              | 低   | 定位失败降级为原始 query | 2s 超时 + 降级                                                |
| 用户在内网/回环地址                | 高   | 定位无意义               | 标准内网段（10/8, 172.16/12, 192.168/16, 127/8）直接返回 None |
| ip-api.com 速率限制（150 req/min） | 中   | 被封 IP 后所有定位失效   | 进程内分钟级计数器，超限直接跳过定位 + 5min TTL 缓存          |
| 反向代理拿不到真实 IP              | 中   | 定位到代理服务器所在地   | 优先 X-Forwarded-For → X-Real-IP，剔除内网段                  |
| IP 归属地变动                      | 低   | 缓存过期前定位到旧城市   | 5min TTL 缓存，用户切换 WiFi/4G 后最多错 5 分钟               |
| 隐私合规质疑                       | 低   | 用户不满                 | 仅传前 3 段 IP、不持久化、仅天气触发                          |
