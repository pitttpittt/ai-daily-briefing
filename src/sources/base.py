"""
Classe abstraite Source.

Toute source de données (HN, ArXiv, GitHub, RSS, etc.) hérite de cette classe.
Le pipeline principal ne dépend que de cette interface — il s'en fiche
de connaître les détails de chaque source.
"""

from abc import ABC, abstractmethod

import httpx

from src.models import BriefingItem, SourceConfig


class Source(ABC):
    """Interface commune à toutes les sources de données."""

    # Identifiant unique de la source. Override dans chaque sous-classe.
    name: str = "base"

    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[BriefingItem]:
        """
        Récupère les items de la source.

        Args:
            client: client HTTP partagé (réutilise les connexions = plus rapide)

        Returns:
            Liste d'items normalisés au format BriefingItem.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"