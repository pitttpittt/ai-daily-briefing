"""
Modèles de données du projet.

Tous les objets qui circulent dans le pipeline sont définis ici :
- BriefingItem : un item récupéré d'une source (HN story, ArXiv paper, GitHub repo)
- RankedItem : un item après scoring/résumé par le LLM
- Config : le contenu validé du config.yaml
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


# --- Items qui circulent dans le pipeline ---

class BriefingItem(BaseModel):
    """Un item brut récupéré d'une source, avant ranking/résumé."""

    source: str  # ex: "hackernews", "arxiv", "github_trending"
    title: str
    url: HttpUrl
    summary: str = ""  # description ou abstract si dispo
    score: float = 0.0  # score natif de la source (upvotes HN, étoiles GitHub...)
    published_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)  # données spécifiques à la source


class RankedItem(BaseModel):
    """Un item après que Claude l'a sélectionné et résumé."""

    item: BriefingItem
    rank: int  # 1 = plus important
    llm_summary: str  # résumé en 2 phrases par Claude
    why_important: str = ""  # une phrase qui explique pourquoi c'est dans le top


# --- Config (miroir du YAML) ---

class SourceConfig(BaseModel):
    """Config d'une source. Les champs varient selon le type."""

    type: Literal["hackernews", "github_trending", "arxiv"]
    enabled: bool = True
    # Champs optionnels selon le type, validés par chaque source elle-même
    top_stories: int = 30
    languages: list[str] = Field(default_factory=list)
    period: str = "daily"
    categories: list[str] = Field(default_factory=list)
    max_results: int = 20


class LLMConfig(BaseModel):
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024
    ranking_prompt: str


class DeliveryChannelConfig(BaseModel):
    enabled: bool = False
    subject_prefix: str = ""


class DeliveryConfig(BaseModel):
    email: DeliveryChannelConfig = Field(default_factory=DeliveryChannelConfig)
    slack: DeliveryChannelConfig = Field(default_factory=DeliveryChannelConfig)
    resend: DeliveryChannelConfig = Field(default_factory=DeliveryChannelConfig)
    console: DeliveryChannelConfig = Field(
        default_factory=lambda: DeliveryChannelConfig(enabled=True)
    )


class BriefingMeta(BaseModel):
    name: str = "AI Daily Briefing"
    language: Literal["fr", "en"] = "fr"
    top_n: int = 5
    timezone: str = "Europe/Paris"


class Config(BaseModel):
    """Config complète du projet, chargée depuis config.yaml."""

    briefing: BriefingMeta
    sources: list[SourceConfig]
    llm: LLMConfig
    delivery: DeliveryConfig

    @classmethod
    def load(cls, path: str = "config.yaml") -> "Config":
        """Charge et valide la config depuis un fichier YAML."""
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)