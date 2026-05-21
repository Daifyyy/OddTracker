#!/usr/bin/env python3
"""
Smart auto-fetch script for GitHub Actions.

Fetches only presets where:
  - auto_fetch = 1
  - credits_remaining > credit_floor
  - has upcoming matches within 48 hours
  - dynamic interval (based on closest match) has elapsed since last fetch

Dynamic intervals:
  > 48h to kickoff  → skip
  24–48h            → 8h interval
  12–24h            → 4h interval
  6–12h             → 2h interval
  2–6h              → 1h interval
  0–2h              → 30 min interval
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from db.models import init_db, migrate_db
from db.queries import get_presets, get_matches_df, get_config, set_config, touch_preset
from fetcher.runner import run_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_CREDIT_FLOOR = 30


def dynamic_interval_hours(hours_to_kickoff: float) -> float:
    if hours_to_kickoff > 48:  return float("inf")
    if hours_to_kickoff > 24:  return 8.0
    if hours_to_kickoff > 12:  return 4.0
    if hours_to_kickoff >  6:  return 2.0
    if hours_to_kickoff >  2:  return 1.0
    return 0.5


def hours_to_closest_match(sport_key: str) -> float | None:
    """Returns hours to closest upcoming/live match, or None if none within 48h."""
    df = get_matches_df(sport_key, only_active=True)
    if df.empty:
        return None
    now = datetime.now(timezone.utc)
    closest = None
    for _, row in df.iterrows():
        try:
            ct = datetime.fromisoformat(row["commence_time"].replace("Z", "+00:00"))
            h = (ct - now).total_seconds() / 3600
            if h > -2:  # include matches up to 2h after kickoff (in-play)
                if closest is None or h < closest:
                    closest = h
        except Exception:
            pass
    return closest


def main() -> int:
    init_db()
    migrate_db()

    credit_floor = int(get_config("auto_fetch_credit_floor", DEFAULT_CREDIT_FLOOR))
    credits = get_config("credits_remaining")

    if credits is not None and credits < credit_floor:
        log.warning("Credits %d below floor %d — skipping all auto-fetches", credits, credit_floor)
        return 0

    presets = get_presets()
    auto_presets = [p for p in presets if p.get("auto_fetch")]

    if not auto_presets:
        log.info("No presets with auto_fetch enabled — nothing to do")
        return 0

    log.info("Auto-fetch candidates: %s", [p["name"] for p in auto_presets])

    now = datetime.now(timezone.utc)
    fetched = 0

    for p in auto_presets:
        h_closest = hours_to_closest_match(p["sport_key"])

        if h_closest is None:
            log.info("[%s] No upcoming matches — skip", p["name"])
            continue

        interval_h = dynamic_interval_hours(h_closest)

        if interval_h == float("inf"):
            log.info("[%s] Closest match in %.1fh (>48h) — skip", p["name"], h_closest)
            continue

        last_used = p.get("last_used_at")
        if last_used:
            last_dt = datetime.fromisoformat(last_used)
            hours_since = (now - last_dt).total_seconds() / 3600
            if hours_since < interval_h:
                log.info(
                    "[%s] %.1fh since last fetch (interval %.1fh) — skip",
                    p["name"], hours_since, interval_h,
                )
                continue

        log.info(
            "[%s] Fetching — closest match in %.1fh, interval %.1fh",
            p["name"], h_closest, interval_h,
        )
        try:
            result = run_once(
                p["sport_key"],
                json.loads(p["markets"]),
                p["regions"],
                json.loads(p["bookmakers"]),
            )
            touch_preset(p["name"])
            set_config("last_fetch_at", now.isoformat())
            fetched += 1
            log.info(
                "[%s] OK — %d snapshots, %d events, credits remaining: %s",
                p["name"], result["snapshots_stored"], result["events_fetched"],
                result["credits_remaining"],
            )
            credits = result.get("credits_remaining")
            if credits is not None and credits < credit_floor:
                log.warning("Credits dropped to %d (floor %d) — stopping", credits, credit_floor)
                break
        except Exception as exc:
            log.error("[%s] Fetch failed: %s", p["name"], exc)

    log.info("Done. Fetched %d preset(s).", fetched)
    return fetched


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
