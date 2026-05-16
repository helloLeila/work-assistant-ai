"""测试 Bocha 不同认证方式。"""

import asyncio
import json
import httpx


API_KEY = "sk-api-key-2026051123323670402"
URL = "https://api.bocha.cn/v1/web-search"
PAYLOAD = {"query": "今天天气", "count": 2, "freshness": "oneMonth", "summary": True}


async def try_auth(name: str, headers: dict):
    print(f"\n{'='*50}")
    print(f"测试: {name}")
    print(f"Headers: {headers}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(URL, json=PAYLOAD, headers=headers, timeout=10)
            print(f"状态码: {resp.status_code}")
            data = resp.json()
            if resp.status_code == 200:
                print("✅ 成功!")
                print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
            else:
                print(f"❌ 失败: {data}")
    except Exception as e:
        print(f"💥 异常: {e}")


async def main():
    # 方式1: Bearer token (当前)
    await try_auth("Bearer Token", {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})

    # 方式2: 直接 Authorization (无 Bearer)
    await try_auth("直接 Authorization", {"Authorization": API_KEY, "Content-Type": "application/json"})

    # 方式3: X-API-Key header
    await try_auth("X-API-Key", {"X-API-Key": API_KEY, "Content-Type": "application/json"})

    # 方式4: api-key header
    await try_auth("api-key header", {"api-key": API_KEY, "Content-Type": "application/json"})

    # 方式5: x-api-key (小写)
    await try_auth("x-api-key (小写)", {"x-api-key": API_KEY, "Content-Type": "application/json"})

    # 方式6: token header
    await try_auth("token header", {"token": API_KEY, "Content-Type": "application/json"})


if __name__ == "__main__":
    asyncio.run(main())
