import asyncio
import os

import httpx

ASSETS_API = "https://assets.deadlock-api.com"
ANALYTICS_API = "https://analytics.deadlock-api.com"
DATA_API = "https://data.deadlock-api.com"
MIN_MATCH_ID = 31611558
MIN_BADGE_LEVEL = 90
MAX_DISTANCE = 1
MIN_USED_ITEMS = 15
MAX_CONCURRENT = 40
API_KEY = os.getenv("DEADLOCK_API_KEY")


class DeadlockAPI:
    def __init__(self):
        self.client = httpx.AsyncClient(http2=True)
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def get_all_heroes(self) -> list[(int, str)]:
        """Fetch all active heroes."""
        response = await self.client.get(f"{ASSETS_API}/v2/heroes", params={"only_active": "true"})
        response.raise_for_status()
        return [(hero["id"], hero["name"]) for hero in response.json()]

    async def get_hero_builds(self, hero_id: int) -> list[dict]:
        """Fetch all builds for a given hero."""
        response = await self.client.get(
            f"{DATA_API}/v1/builds/by-hero-id/{hero_id}",
            params={"only_latest": "true", "limit": "-1"},
            timeout=None,
        )
        response.raise_for_status()
        return response.json()

    async def fetch_winrate(self, hero_id: int, item_ids: str) -> dict | None:
        """Fetch win rate analysis for given hero and items."""
        try:
            async with self.semaphore:
                for _ in range(3):
                    response = await self.client.get(
                        f"{ANALYTICS_API}/v1/dev/item-win-rate-analysis/by-similarity",
                        params={
                            "min_match_id": MIN_MATCH_ID,
                            "item_ids": item_ids,
                            "hero_id": hero_id,
                            "min_badge_level": MIN_BADGE_LEVEL,
                            "max_distance": MAX_DISTANCE,
                            "min_used_items": MIN_USED_ITEMS,
                            "distance_function": "non_matching_items",
                            "k_most_similar_builds": 100_000,
                            **({"api_key": API_KEY} if API_KEY else {}),
                        },
                    )
                    if response.status_code == 429:
                        print("Rate limited, waiting 1s")
                        await asyncio.sleep(1)
                        continue
                    if not response.is_success:
                        return None
                    response.raise_for_status()
                    return response.json()
        except httpx.RequestError as e:
            print(f"Error fetching winrate: {e.request.headers}")
            return None
