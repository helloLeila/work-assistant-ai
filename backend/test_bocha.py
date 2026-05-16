"""调试 Bocha API 返回格式。"""

import asyncio
import json
import httpx


async def test_bocha():
    api_key = "sk-api-key-2026051123323670402"
    url = "https://api.bocha.cn/v1/web-search"

    payload = {
        "query": "今天天气",
        "count": 3,
        "freshness": "oneMonth",
        "summary": True,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"请求 URL: {url}")
    print(f"请求头: {headers}")
    print(f"请求体: {json.dumps(payload, ensure_ascii=False)}")
    print()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10)
            print(f"状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            print()
            data = response.json()
            print("响应 JSON:")
            print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_bocha())
