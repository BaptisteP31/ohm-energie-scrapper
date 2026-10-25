import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Non utilisé par l'espace client (les routes métier passent par espace-client.../api).
DEFAULT_API_BASE = "https://bo-api.ohm-energie.com"

DEFAULT_SERVICE_HOST = "127.0.0.1"
DEFAULT_SERVICE_PORT = 8080
DEFAULT_CACHE_TTL = 900
DEFAULT_PUBLISH_ADDRESS = "127.0.0.1"


@dataclass(frozen=True)
class Config:
    login: str
    password: str
    customer_number: str | None  # sinon déduit de la réponse de login
    api_base: str
    ct: str | None  # sinon body.user.currentContract de la réponse de login
    service_host: str = DEFAULT_SERVICE_HOST
    service_port: int = DEFAULT_SERVICE_PORT
    api_token: str | None = None
    cache_ttl: int = DEFAULT_CACHE_TTL
    publish_address: str = DEFAULT_PUBLISH_ADDRESS


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Renseignez-la dans {PROJECT_ROOT / ".env"} (voir .env.example)."
        )
    return value


def _optional(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        if val < 0:
            raise ValueError(f"Variable {name} doit être positive (reçu: {val})")
        return val
    except ValueError as exc:
        raise ValueError(f"Variable {name} doit être un entier valide (reçu: {raw!r})") from exc


def load_config(env_file: Path | None = None) -> Config:
    load_dotenv(env_file or (PROJECT_ROOT / ".env"))
    return Config(
        login=_require("OHM_LOGIN"),
        password=_require("OHM_PASSWORD"),
        customer_number=_optional("OHM_CUSTOMER_NUMBER"),
        api_base=os.getenv("OHM_API_BASE", DEFAULT_API_BASE).strip().rstrip("/"),
        ct=_optional("OHM_CT"),
        service_host=os.getenv("SERVICE_HOST", DEFAULT_SERVICE_HOST).strip() or DEFAULT_SERVICE_HOST,
        service_port=_int_env("SERVICE_PORT", DEFAULT_SERVICE_PORT),
        api_token=_optional("OHM_API_TOKEN"),
        cache_ttl=_int_env("OHM_CACHE_TTL", DEFAULT_CACHE_TTL),
        publish_address=os.getenv("OHM_PUBLISH_ADDRESS", DEFAULT_PUBLISH_ADDRESS).strip() or DEFAULT_PUBLISH_ADDRESS,
    )
