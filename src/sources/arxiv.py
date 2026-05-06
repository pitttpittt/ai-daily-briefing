"""Source ArXiv — API Atom officielle."""

from datetime import datetime, timezone

import feedparser
import httpx

from src.models import BriefingItem
from src.sources.base import Source

# HTTPS direct (l'URL HTTP renvoie un 301 vers HTTPS)
API_URL = "https://export.arxiv.org/api/query"


class ArxivSource(Source):
    name = "arxiv"

    async def fetch(self, client: httpx.AsyncClient) -> list[BriefingItem]:
        cats = self.config.categories or ["cs.AI"]
        search_query = " OR ".join(f"cat:{c}" for c in cats)

        params = {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(self.config.max_results),
        }

        resp = await client.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)

        items: list[BriefingItem] = []
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue

            published_at: datetime | None = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            authors = [a.get("name", "") for a in entry.get("authors", [])]
            summary = entry.get("summary", "").strip().replace("\n", " ")
            title = (
                entry.get("title", "(sans titre)")
                .strip()
                .replace("\n ", "")
                .replace("  ", " ")
            )

            items.append(
                BriefingItem(
                    source=self.name,
                    title=title,
                    url=url,
                    summary=summary[:500],
                    score=0.0,
                    published_at=published_at,
                    metadata={
                        "authors": authors[:5],
                        "categories": [t["term"] for t in entry.get("tags", [])],
                        "arxiv_id": entry.get("id", "").split("/")[-1],
                    },
                )
            )

        return items
