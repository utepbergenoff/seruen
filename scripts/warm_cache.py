import argparse
import asyncio

import httpx


async def warm(base_url):
    async with httpx.AsyncClient(base_url=base_url, timeout=90) as client:
        response = await client.get("/scenarios")
        response.raise_for_status()
        for row in response.json():
            for _ in range(2):
                result = await client.post("/recommend", json=row["request"])
                result.raise_for_status()
            data = result.json()
            print(row["id"], data["mode"], len(data["recommendations"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    asyncio.run(warm(parser.parse_args().base_url))
