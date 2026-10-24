import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Non utilisé par l'espace client (les routes métier passent par espace-client.../api).
DEFAULT_API_BASE = "https://bo-api.ohm-energie.com"


@dataclass(frozen=True)
class Config:
    login: str
    password: str
    customer_number: str | None  # sinon déduit de la réponse de login
    api_base: str
    ct: str | None  # sinon body.user.currentContract de la réponse de login


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Renseignez-la dans {PROJECT_ROOT / '.env'} (voir .env.example)."
        )
    return value


def _optional(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def load_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    return Config(
        login=_require("OHM_LOGIN"),
        password=_require("OHM_PASSWORD"),
        customer_number=_optional("OHM_CUSTOMER_NUMBER"),
        api_base=os.getenv("OHM_API_BASE", DEFAULT_API_BASE).strip().rstrip("/"),
        ct=_optional("OHM_CT"),
    )
