"""Point d'entrée du briefing quotidien.

Pipeline :
1. Charge la config + .env
2. Récupère les items de toutes les sources actives (en parallèle)
3. Demande à Claude de ranker + résumer (avec règle de diversité)
4. Envoie via tous les canaux activés (console + email + slack)
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

from src.delivery import DELIVERER_REGISTRY, Deliverer
from src.llm import LLMRanker
from src.models import BriefingItem, Config
from src.sources.arxiv import ArxivSource
from src.sources.base import Source
from src.sources.github_trending import GitHubTrendingSource
from src.sources.hackernews import HackerNewsSource

load_dotenv()


SOURCE_REGISTRY: dict[str, type[Source]] = {
    "hackernews": HackerNewsSource,
    "arxiv": ArxivSource,
    "github_trending": GitHubTrendingSource,
}


async def fetch_all_sources(config: Config) -> list[BriefingItem]:
    """Récupère les items de toutes les sources actives en parallèle."""
    sources: list[Source] = []
    for src_config in config.sources:
        if not src_config.enabled:
            continue
        source_class = SOURCE_REGISTRY.get(src_config.type)
        if source_class is None:
            print(f"⚠️  Source '{src_config.type}' pas encore implémentée, skip.")
            continue
        sources.append(source_class(src_config))

    if not sources:
        return []

    print(f"🔍 Récupération depuis {len(sources)} source(s)...")

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        tasks = [source.fetch(client) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[BriefingItem] = []
    for source, result in zip(sources, results, strict=False):
        if isinstance(result, Exception):
            print(f"❌ {source.name}: {result}")
            continue
        print(f"✅ {source.name}: {len(result)} items")
        all_items.extend(result)

    return all_items


def deliver_briefing(config: Config, ranked_items, generated_at: datetime) -> None:
    """Envoie le briefing via tous les canaux activés."""
    channels = {
        "console": config.delivery.console,
        "email": config.delivery.email,
        "resend": config.delivery.resend,
        "slack": config.delivery.slack,
    }

    for channel_name, channel_config in channels.items():
        if not channel_config.enabled:
            continue

        deliverer_class = DELIVERER_REGISTRY.get(channel_name)
        if deliverer_class is None:
            print(f"⚠️  Canal '{channel_name}' pas encore implémenté, skip.")
            continue

        deliverer: Deliverer = deliverer_class(channel_config)
        try:
            deliverer.send(ranked_items, config.briefing.name, generated_at)
        except Exception as e:
            print(f"❌ Erreur sur le canal '{channel_name}': {e}")


async def main() -> None:
    config = Config.load()
    generated_at = datetime.now(ZoneInfo(config.briefing.timezone))

    # 1. Récupération
    all_items = await fetch_all_sources(config)
    print(f"\n📦 Total: {len(all_items)} items collectés")

    if not all_items:
        print("⚠️  Aucun item récupéré. Vérifie la config et la connexion.")
        return

    # 2. Ranking par Claude
    print(f"\n🤖 Ranking par Claude ({config.llm.model})...")
    ranker = LLMRanker(config.llm)
    ranked = ranker.rank_and_summarize(all_items, top_n=config.briefing.top_n)
    print(f"✅ Top {len(ranked)} sélectionné")

    # 3. Livraison via tous les canaux activés
    deliver_briefing(config, ranked, generated_at)


if __name__ == "__main__":
    asyncio.run(main())
