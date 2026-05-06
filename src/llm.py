"""Wrapper Claude pour le ranking + résumé.

Stratégie :
- On groupe les items par source pour aider Claude à voir la diversité
- On lui demande explicitement de garantir au moins 1 item par source dans le top
- On exige une réponse JSON stricte, validée par Pydantic
"""

import json
from collections import defaultdict
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

from src.models import BriefingItem, LLMConfig, RankedItem


class _LLMRankedItem(BaseModel):
    index: int
    rank: int
    summary: str
    why_important: str


class _LLMResponse(BaseModel):
    items: list[_LLMRankedItem]


class LLMRanker:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = Anthropic()

    def rank_and_summarize(
        self,
        items: list[BriefingItem],
        top_n: int = 5,
    ) -> list[RankedItem]:
        if not items:
            return []

        # Liste des sources distinctes (pour la règle de diversité)
        sources_present = sorted({item.source for item in items})
        items_text = self._format_items_for_prompt(items)

        diversity_rule = ""
        if len(sources_present) > 1:
            diversity_rule = (
                f"\n\nRÈGLE DE DIVERSITÉ OBLIGATOIRE : ton top {top_n} doit "
                f"contenir AU MOINS UN article de CHACUNE des {len(sources_present)} "
                f"sources suivantes : {', '.join(sources_present)}. "
                "Si une source a un article moins populaire mais techniquement intéressant, "
                "préfère-le à un énième article de la source dominante."
            )

        user_prompt = f"""Voici {len(items)} articles tech/IA récupérés aujourd'hui, groupés par source :

{items_text}

Sélectionne les {top_n} articles les plus importants selon les critères donnés.{diversity_rule}

Réponds UNIQUEMENT avec un JSON valide au format suivant, sans texte avant ou après :

{{
  "items": [
    {{
      "index": <int, l'index global de l'article (le numéro entre crochets)>,
      "rank": <int, 1 pour le plus important, {top_n} pour le moins important>,
      "summary": "<résumé en 2 phrases max, en français, sans fautes d'orthographe>",
      "why_important": "<une phrase qui explique pourquoi c'est dans le top, en français>"
    }}
  ]
}}"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self.config.ranking_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()
        parsed = self._parse_llm_response(raw_text)

        ranked: list[RankedItem] = []
        for llm_item in parsed.items:
            if 0 <= llm_item.index < len(items):
                ranked.append(
                    RankedItem(
                        item=items[llm_item.index],
                        rank=llm_item.rank,
                        llm_summary=llm_item.summary,
                        why_important=llm_item.why_important,
                    )
                )

        ranked.sort(key=lambda r: r.rank)
        return ranked

    def _format_items_for_prompt(self, items: list[BriefingItem]) -> str:
        """Groupe les items par source pour aider Claude à percevoir la diversité.

        Format produit :
            === SOURCE: hackernews (29 items) ===
            [0] (score 1409) Titre
            [1] (score 543) Titre — résumé court
            ...

            === SOURCE: arxiv (20 items) ===
            [29] Titre — résumé court
            ...
        """
        # Groupe les items par source en gardant l'index global
        grouped: dict[str, list[tuple[int, BriefingItem]]] = defaultdict(list)
        for i, item in enumerate(items):
            grouped[item.source].append((i, item))

        blocks: list[str] = []
        for source_name in sorted(grouped):
            source_items = grouped[source_name]
            blocks.append(f"=== SOURCE: {source_name} ({len(source_items)} items) ===")
            for global_idx, item in source_items:
                score_str = f"score {int(item.score)}" if item.score > 0 else "no-score"
                extra = f" — {item.summary[:120]}" if item.summary else ""
                blocks.append(f"[{global_idx}] ({score_str}) {item.title}{extra}")
            blocks.append("")  # ligne vide entre les groupes

        return "\n".join(blocks)

    def _parse_llm_response(self, raw_text: str) -> _LLMResponse:
        text = raw_text
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data: dict[str, Any] = json.loads(text)
            return _LLMResponse(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(
                f"Réponse Claude invalide. Raw text:\n{raw_text}\n\nErreur: {e}"
            ) from e
