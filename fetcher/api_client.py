import os
import time
import logging
import urllib3

import requests
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
logger = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4"


class OddsAPIClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY", "")
        self.session = requests.Session()
        self.credits_remaining: int | None = None
        self.credits_used: int | None = None

    def _get(self, path: str, params: dict) -> dict | list:
        params["apiKey"] = self.api_key
        for attempt in range(3):
            try:
                resp = self.session.get(f"{BASE}{path}", params=params, timeout=15,
                                        verify=False)
                self.credits_remaining = int(resp.headers.get("x-requests-remaining", -1))
                self.credits_used = int(resp.headers.get("x-requests-used", -1))
                logger.info("API %s → %d | credits used=%s remaining=%s",
                            path, resp.status_code,
                            self.credits_used, self.credits_remaining)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Rate limited, retrying in %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == 2:
                    raise
                logger.warning("Request error (%s), retry %d", exc, attempt + 1)
                time.sleep(1)
        raise RuntimeError("API request failed after retries")

    def get_sports(self, all: bool = False) -> list[dict]:
        return self._get("/sports", {"all": str(all).lower()})

    def get_odds(self, sport_key: str, markets: list[str],
                 regions: str = "eu", bookmakers: list[str] | None = None,
                 event_ids: list[str] | None = None,
                 odds_format: str = "decimal") -> list[dict]:
        params: dict = {
            "regions":    regions,
            "markets":    ",".join(markets),
            "oddsFormat": odds_format,
            "dateFormat": "iso",
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)
        if event_ids:
            params["eventIds"] = ",".join(event_ids)
        return self._get(f"/sports/{sport_key}/odds", params)

    def get_scores(self, sport_key: str, days_from: int = 1) -> list[dict]:
        return self._get(
            f"/sports/{sport_key}/scores",
            {"daysFrom": days_from, "dateFormat": "iso"},
        )
