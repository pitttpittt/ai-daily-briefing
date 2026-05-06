"""Source GitHub Trending — scraping HTML de github.com/trending."""

import httpx
from selectolax.parser import HTMLParser

from src.models import BriefingItem
from src.sources.base import Source

TRENDING_URL = "https://github.com/trending"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


class GitHubTrendingSource(Source):
    name = "github_trending"

    async def fetch(self, client: httpx.AsyncClient) -> list[BriefingItem]:
        languages = self.config.languages or [""]
        period = self.config.period or "daily"

        all_items: list[BriefingItem] = []
        seen_urls: set[str] = set()

        for language in languages:
            url = TRENDING_URL
            if language:
                url = f"{TRENDING_URL}/{language}"

            params = {"since": period}

            try:
                resp = await client.get(url, params=params, headers=HEADERS, timeout=15)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            items = self._parse_trending_page(resp.text, language=language)

            for item in items:
                url_str = str(item.url)
                if url_str in seen_urls:
                    continue
                seen_urls.add(url_str)
                all_items.append(item)

        return all_items

    def _parse_trending_page(self, html: str, language: str = "") -> list[BriefingItem]:
        tree = HTMLParser(html)
        items: list[BriefingItem] = []

        for article in tree.css("article.Box-row"):
            h2 = article.css_first("h2 a")
            if h2 is None:
                continue

            href = h2.attributes.get("href", "").strip()
            if not href:
                continue
            repo_url = f"https://github.com{href}"
            full_name = href.lstrip("/")

            desc_node = article.css_first("p")
            description = desc_node.text(strip=True) if desc_node else ""

            stars = self._parse_int(article, 'a[href$="/stargazers"]')

            today_node = article.css_first("span.d-inline-block.float-sm-right")
            stars_today = self._parse_int_from_text(
                today_node.text(strip=True) if today_node else ""
            )

            forks = self._parse_int(article, 'a[href$="/forks"]')

            lang_node = article.css_first('span[itemprop="programmingLanguage"]')
            detected_lang = (
                lang_node.text(strip=True) if lang_node else (language or "unknown")
            )

            items.append(
                BriefingItem(
                    source=self.name,
                    title=full_name,
                    url=repo_url,
                    summary=description,
                    score=float(stars),
                    published_at=None,
                    metadata={
                        "language": detected_lang,
                        "stars_today": stars_today,
                        "total_stars": stars,
                        "forks": forks,
                    },
                )
            )

        return items

    @staticmethod
    def _parse_int(article, selector: str) -> int:
        node = article.css_first(selector)
        if node is None:
            return 0
        return GitHubTrendingSource._parse_int_from_text(node.text(strip=True))

    @staticmethod
    def _parse_int_from_text(text: str) -> int:
        if not text:
            return 0
        cleaned = "".join(c for c in text if c.isdigit() or c in ",.kKmM")
        if not cleaned:
            return 0
        multiplier = 1
        if cleaned[-1] in "kK":
            multiplier = 1_000
            cleaned = cleaned[:-1]
        elif cleaned[-1] in "mM":
            multiplier = 1_000_000
            cleaned = cleaned[:-1]
        cleaned = cleaned.replace(",", "")
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return 0
