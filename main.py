import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ohm_scraper.client import OhmClient
from ohm_scraper.config import PROJECT_ROOT, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ohm_scraper")

DATA_DIR = PROJECT_ROOT / "data"


def save_json(name: str, payload: dict[str, Any], timestamp: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{name}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    config = load_config()
    client = OhmClient(config)
    client.login()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    datasets = {
        "consumption_six_months": client.get_consumption_six_months(),
        "consumption_last_month": client.get_consumption_last_month(),
    }
    for name, payload in datasets.items():
        path = save_json(name, payload, timestamp)
        logger.info("Écrit : %s", path)


if __name__ == "__main__":
    main()
