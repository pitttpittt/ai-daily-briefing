"""Module d'envoi du briefing.

Supporte plusieurs canaux configurables :
- console : print dans le terminal (toujours actif pour debug)
- email : envoi HTML via SMTP (Gmail, Outlook, etc.)
- slack : envoi via webhook (à venir)

Architecture : chaque canal est un Deliverer indépendant. On les exécute
en parallèle si plusieurs sont actifs.
"""

import os
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import DeliveryChannelConfig, RankedItem


# ----- Templating -----

# On charge les templates depuis src/templates/
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_html_briefing(
    ranked_items: list[RankedItem],
    briefing_name: str,
    generated_at: datetime,
) -> str:
    """Génère le HTML du briefing depuis le template Jinja2."""
    template = _jinja_env.get_template("briefing.html")
    return template.render(
        ranked_items=ranked_items,
        briefing_name=briefing_name,
        generated_at=generated_at,
    )


# ----- Deliverers -----

class Deliverer(ABC):
    """Interface commune à tous les canaux de livraison."""

    name: str = "base"

    def __init__(self, config: DeliveryChannelConfig):
        self.config = config

    @abstractmethod
    def send(
        self,
        ranked_items: list[RankedItem],
        briefing_name: str,
        generated_at: datetime,
    ) -> None:
        ...


class ConsoleDeliverer(Deliverer):
    """Affiche le briefing dans le terminal."""

    name = "console"

    def send(
        self,
        ranked_items: list[RankedItem],
        briefing_name: str,
        generated_at: datetime,
    ) -> None:
        print()
        print("=" * 70)
        print(f"  📰  {briefing_name}")
        print(f"  📅  {generated_at.strftime('%A %d %B %Y, %H:%M')}")
        print("=" * 70)
        print()

        if not ranked_items:
            print("Aucun item à afficher.")
            return

        for r in ranked_items:
            print(f"#{r.rank} — {r.item.title}")
            print(f"   📌 {r.why_important}")
            print(f"   {r.llm_summary}")
            print(f"   🔗 {r.item.url}")
            print(f"   (source: {r.item.source}, score: {int(r.item.score)})")
            print()


class EmailDeliverer(Deliverer):
    """Envoie le briefing par email HTML via SMTP.

    Lit les paramètres SMTP depuis les variables d'environnement :
    - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    - SMTP_FROM (optionnel, par défaut = SMTP_USER)
    - SMTP_TO (destinataire(s), virgule-séparés)
    """

    name = "email"

    def send(
        self,
        ranked_items: list[RankedItem],
        briefing_name: str,
        generated_at: datetime,
    ) -> None:
        host = os.environ.get("SMTP_HOST", "")
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "")
        # Les App Passwords Gmail s'affichent en 4 blocs de 4 caractères
        # séparés par des espaces. On les nettoie pour éviter les surprises.
        password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")
        sender = os.environ.get("SMTP_FROM", user)
        recipients_raw = os.environ.get("SMTP_TO", "")

        # Validation
        missing = [
            name for name, value in [
                ("SMTP_HOST", host),
                ("SMTP_USER", user),
                ("SMTP_PASSWORD", password),
                ("SMTP_TO", recipients_raw),
            ] if not value
        ]
        if missing:
            raise RuntimeError(
                f"EmailDeliverer : variables d'env manquantes : {', '.join(missing)}"
            )

        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

        # Sujet — on évite les emojis en tête (ça augmente le spam score)
        date_str = generated_at.strftime("%d/%m/%Y")
        subject_prefix = self.config.subject_prefix or briefing_name
        # Si le prefix commence par un emoji, on le déplace après pour passer les filtres
        subject = f"{subject_prefix} {date_str}"

        # Corps HTML
        html_body = render_html_briefing(ranked_items, briefing_name, generated_at)

        # Version texte de fallback (pour les clients mail qui n'affichent pas le HTML)
        text_body = self._render_text_fallback(ranked_items, briefing_name, generated_at)

        # Construction du message multipart (texte + HTML)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"AI Daily Briefing <{sender}>"
        msg["To"] = ", ".join(recipients)
        msg["Reply-To"] = sender
        # Headers anti-spam : montre que c'est un envoi légitime et non commercial
        msg["List-Unsubscribe"] = f"<mailto:{sender}?subject=unsubscribe>"
        msg["X-Mailer"] = "ai-daily-briefing/0.1"
        msg["X-Auto-Response-Suppress"] = "All"
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Envoi
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, recipients, msg.as_string())

        print(f"✉️  Email envoyé à {len(recipients)} destinataire(s)")

    @staticmethod
    def _render_text_fallback(
        ranked_items: list[RankedItem],
        briefing_name: str,
        generated_at: datetime,
    ) -> str:
        lines = [
            briefing_name,
            generated_at.strftime("%A %d %B %Y"),
            "=" * 50,
            "",
        ]
        for r in ranked_items:
            lines.append(f"#{r.rank} — {r.item.title}")
            lines.append(f"  > {r.why_important}")
            lines.append(f"  {r.llm_summary}")
            lines.append(f"  Lien : {r.item.url}")
            lines.append(f"  (source : {r.item.source})")
            lines.append("")
        return "\n".join(lines)


# ----- Registry -----

class ResendDeliverer(Deliverer):
    """Envoie le briefing via Resend (https://resend.com).

    Avantage vs SMTP Gmail : DKIM/SPF/DMARC pré-configurés côté Resend,
    déliverabilité ~99% (jamais en spam).

    Variables d'env :
    - RESEND_API_KEY : clé API Resend
    - RESEND_FROM : optionnel, sinon "onboarding@resend.dev" (sandbox)
    - RESEND_TO : destinataire(s), virgule-séparés.
                  En sandbox, doit être l'email du compte Resend.

    NB : sans domaine custom vérifié, Resend autorise uniquement
    l'envoi vers l'email du compte (sandbox de test).
    """

    name = "resend"

    def send(
        self,
        ranked_items: list[RankedItem],
        briefing_name: str,
        generated_at: datetime,
    ) -> None:
        # Import paresseux : la lib n'est requise que si ce canal est utilisé
        import resend

        api_key = os.environ.get("RESEND_API_KEY", "")
        sender = os.environ.get("RESEND_FROM", "onboarding@resend.dev")
        recipients_raw = os.environ.get("RESEND_TO", "")

        # Fallback : si RESEND_TO n'est pas défini, on utilise SMTP_TO
        if not recipients_raw:
            recipients_raw = os.environ.get("SMTP_TO", "")

        if not api_key:
            raise RuntimeError("ResendDeliverer : variable RESEND_API_KEY manquante")
        if not recipients_raw:
            raise RuntimeError(
                "ResendDeliverer : RESEND_TO (ou SMTP_TO en fallback) manquant"
            )

        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

        date_str = generated_at.strftime("%d/%m/%Y")
        subject_prefix = self.config.subject_prefix or briefing_name
        subject = f"{subject_prefix} {date_str}"

        html_body = render_html_briefing(ranked_items, briefing_name, generated_at)

        resend.api_key = api_key
        result = resend.Emails.send({
            "from": f"AI Daily Briefing <{sender}>",
            "to": recipients,
            "subject": subject,
            "html": html_body,
            "headers": {
                "X-Mailer": "ai-daily-briefing/0.1",
            },
        })

        email_id = result.get("id", "?") if isinstance(result, dict) else "?"
        print(f"✉️  Resend : email envoyé à {len(recipients)} destinataire(s) (id={email_id})")


DELIVERER_REGISTRY: dict[str, type[Deliverer]] = {
    "console": ConsoleDeliverer,
    "email": EmailDeliverer,
    "resend": ResendDeliverer,
    # "slack": SlackDeliverer,  # à venir
}
