"""
Source HackerNews.

Utilise l'API officielle Firebase (gratuite, pas de clé) :
https://github.com/HackerNews/API

Stratégie :
1. Récupère les IDs des top stories du jour (1 appel)
2. Pour chacun, récupère le détail (titre, URL, score, etc.) en parallèle
3. Filtre les "Ask HN" / "Show HN" sans URL externe (optionnel)
"""

import asyncio
from datetime import datetime, timezone

import httpx

from src.models import BriefingItem
from src.sources.base import Source

API_BASE = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(Source):
    name = "hackernews"

    async def fetch(self, client: httpx.AsyncClient) -> list[BriefingItem]:
        # 1. Récupère la liste des top stories
        resp = await client.get(f"{API_BASE}/topstories.json", timeout=10)
        resp.raise_for_status()
        all_ids: list[int] = resp.json()

        # On garde les N premiers selon la config
        n = self.config.top_stories
        story_ids = all_ids[:n]

        # 2. Récupère le détail de chaque story EN PARALLÈLE (asyncio.gather)
        # Ça transforme N requêtes séquentielles (lentes) en N requêtes simultanées
        tasks = [self._fetch_item(client, sid) for sid in story_ids]
        raw_items = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Normalise au format BriefingItem
        items: list[BriefingItem] = []
        for raw in raw_items:
            if isinstance(raw, Exception) or raw is None:
                continue  # on skippe les erreurs silencieusement

            # On garde seulement les "story" avec une URL externe
            if raw.get("type") != "story" or not raw.get("url"):
                continue

            items.append(
                BriefingItem(
                    source=self.name,
                    title=raw.get("title", "(sans titre)"),
                    url=raw["url"],
                    summary="",  # HN ne donne pas de résumé natif
                    score=float(raw.get("score", 0)),
                    published_at=datetime.fromtimestamp(
                        raw["time"], tz=timezone.utc
                    ) if "time" in raw else None,
                    metadata={
                        "hn_id": raw.get("id"),
                        "comments_count": raw.get("descendants", 0),
                        "author": raw.get("by"),
                        "hn_url": f"https://news.ycombinator.com/item?id={raw.get('id')}",
                    },
                )
            )

        return items

    async def _fetch_item(self, client: httpx.AsyncClient, item_id: int) -> dict | None:
        """Récupère le détail d'une story HN."""
        try:
            resp = await client.get(f"{API_BASE}/item/{item_id}.json", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return None