"""验证 Bocha API 修复后的解析逻辑。"""

import asyncio
import json
import httpx


API_KEY = "你的新API_KEY"  # ← 去 https://open.bocha.cn 获取后替换
URL = "https://api.bocha.cn/v1/web-search"


async def main():
    payload = {
        "query": "今天天气",
        "count": 3,
        "freshness": "oneMonth",
        "summary": True,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(URL, json=payload, headers=headers, timeout=10)
        print(f"状态码: {resp.status_code}")
        data = resp.json()

        if resp.status_code != 200:
            print(f"错误: {data}")
            return

        print("✅ 请求成功!")
        print()

        # 按修复后的代码解析
        raw_results = data.get("webPages", {}).get("value", [])
        print(f"找到 {len(raw_results)} 条结果:")
        for item in raw_results:
            print(f"  - {item.get('name')}")
            print(f"    url: {item.get('url')}")
            print(f"    snippet: {item.get('snippet', '')[:60]}...")
            print(f"    summary: {item.get('summary', '')[:60]}...")
            print(f"    siteName: {item.get('siteName')}")
            print(f"    datePublished: {item.get('datePublished')}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
