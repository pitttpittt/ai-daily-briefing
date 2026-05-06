# 📰 AI Daily Briefing

> Un agent autonome qui récupère les actualités tech/IA du jour depuis HackerNews, ArXiv et GitHub Trending, sélectionne les plus pertinentes avec Claude (Anthropic), et envoie un briefing résumé en français par email.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude-orange.svg)](https://www.anthropic.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 Ce que ça fait

Tous les matins (ou à la demande) :

1. **Scrape** ~80 articles tech/IA depuis 3 sources en parallèle
2. **Sélectionne** les 5 plus pertinents avec Claude (Anthropic), en garantissant la diversité des sources
3. **Résume** chacun en 2 phrases, en français, avec une justification de la sélection
4. **Envoie** un email HTML responsive (et/ou affichage console)

Le tout en moins de 10 secondes, pour environ $0.005 par briefing.

## 🏗️ Architecture

```
ai-daily-briefing/
├── config.yaml              # Configuration (sources, prompts, destinataires)
├── src/
│   ├── models.py            # Modèles Pydantic (validation stricte)
│   ├── llm.py               # Wrapper Claude (ranking + résumé)
│   ├── delivery.py          # Canaux d'envoi (console, email, slack)
│   ├── main.py              # Orchestration asynchrone
│   ├── sources/             # Sources extensibles (Strategy Pattern)
│   │   ├── base.py
│   │   ├── hackernews.py    # API Firebase officielle
│   │   ├── arxiv.py         # API Atom officielle
│   │   └── github_trending.py  # Scraping HTML + selectolax
│   └── templates/
│       └── briefing.html    # Email template Jinja2
└── .github/workflows/
    └── daily.yml            # Cron quotidien (7h UTC)
```

**Stack** : Python 3.11+, async/await, httpx, Pydantic v2, Anthropic SDK, Jinja2, selectolax, feedparser.

## 🚀 Installation

```bash
git clone https://github.com/pitttpittt/ai-daily-briefing.git
cd ai-daily-briefing

# Installation des dépendances avec uv (https://github.com/astral-sh/uv)
uv sync

# Configuration des secrets
cp .env.example .env
# Édite .env avec ta clé Anthropic et tes paramètres SMTP
```

### Variables d'environnement

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Clé API Anthropic ([console.anthropic.com](https://console.anthropic.com/)) |
| `SMTP_HOST` | Serveur SMTP (ex: `smtp.gmail.com`) |
| `SMTP_PORT` | Port SMTP (587 pour TLS) |
| `SMTP_USER` | Adresse email expéditrice |
| `SMTP_PASSWORD` | App Password (pour Gmail : [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)) |
| `SMTP_FROM` | Adresse "From" (souvent = SMTP_USER) |
| `SMTP_TO` | Destinataire(s), virgule-séparés |

## 📖 Usage

### Lancement manuel

```bash
uv run python -m src.main
```

### Automatisation quotidienne via GitHub Actions

Le workflow `.github/workflows/daily.yml` lance le briefing tous les jours à 7h UTC. Il suffit d'ajouter les secrets dans `Settings → Secrets and variables → Actions` du repo.

### Personnalisation

Tout passe par `config.yaml` :

```yaml
briefing:
  language: "fr"
  top_n: 5

sources:
  - type: hackernews
    enabled: true
    top_stories: 30

  - type: arxiv
    enabled: true
    categories: ["cs.AI", "cs.LG", "cs.CL"]

  - type: github_trending
    enabled: true
    languages: ["python", "typescript", "rust"]
```

## 🧠 Choix techniques

- **Pydantic v2** pour valider la config et les réponses du LLM (zéro surprise en prod).
- **Strategy Pattern** sur les sources : ajouter une nouvelle source (Reddit, Lobsters, RSS custom...) = ~80 lignes, sans toucher au pipeline.
- **JSON structuré** pour le LLM, avec parsing tolérant aux fences markdown.
- **Diversité forcée** dans le top : sans cette règle, Claude ne sélectionne que des items HackerNews à fort score.
- **Async parallélisme** : les 3 sources sont scrapées simultanément, `asyncio.gather` collecte tout.
- **GitHub Actions** : exécution gratuite et illimitée pour les repos publics, pas besoin de serveur.

## 📄 License

MIT — fais-en ce que tu veux.
