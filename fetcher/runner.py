import logging
from datetime import datetime, timezone

from db.models import init_db
from db.queries import insert_snapshots, upsert_matches, set_config
from fetcher.api_client import OddsAPIClient
from fetcher.normalizer import flatten_odds, extract_events
from analytics.movements import detect_line_changes
from analytics.steam import detect_steam_moves
from analytics.clv import mark_matches_completed

logger = logging.getLogger(__name__)


def run_once(sport_key: str, markets: list[str],
             regions: str = "eu", bookmakers: list[str] | None = None) -> dict:
    client = OddsAPIClient()
    snapshot_time = datetime.now(timezone.utc).isoformat()

    logger.info("Fetching odds: sport=%s markets=%s regions=%s", sport_key, markets, regions)
    events = client.get_odds(sport_key, markets, regions, bookmakers)

    rows = flatten_odds(events, snapshot_time)
    event_metas = extract_events(events)

    upsert_matches(event_metas)
    stored = insert_snapshots(rows)

    detect_line_changes(snapshot_time)
    detect_steam_moves(snapshot_time)
    mark_matches_completed()

    credits_remaining = client.credits_remaining
    credits_used = client.credits_used
    if credits_remaining is not None:
        set_config("credits_remaining", credits_remaining)

    return {
        "snapshot_time":    snapshot_time,
        "events_fetched":   len(events),
        "snapshots_stored": stored,
        "credits_used":     credits_used,
        "credits_remaining": credits_remaining,
    }


def fetch_scores(sport_key: str, days_from: int = 1) -> dict:
    from db.queries import upsert_result, mark_completed
    from db.database import get_connection

    client = OddsAPIClient()
    scores = client.get_scores(sport_key, days_from)

    updated = 0
    conn = get_connection()
    match_ids = {
        row["id"] for row in conn.execute("SELECT id FROM matches WHERE sport_key=?",
                                           (sport_key,)).fetchall()
    }
    conn.close()

    for s in scores:
        if s["id"] not in match_ids:
            continue
        completed = s.get("completed", False)
        if not completed:
            continue

        scores_data = s.get("scores") or []
        home_score = away_score = None
        for sc in scores_data:
            if sc["name"] == s.get("home_team"):
                try:
                    home_score = int(sc["score"])
                except (ValueError, TypeError):
                    pass
            elif sc["name"] == s.get("away_team"):
                try:
                    away_score = int(sc["score"])
                except (ValueError, TypeError):
                    pass

        upsert_result(s["id"], home_score, away_score, None, None)
        mark_completed(s["id"])
        updated += 1

    credits_remaining = client.credits_remaining
    if credits_remaining is not None:
        set_config("credits_remaining", credits_remaining)

    return {
        "scores_fetched": len(scores),
        "matches_updated": updated,
        "credits_remaining": credits_remaining,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    init_db()

    sport = sys.argv[1] if len(sys.argv) > 1 else "soccer_germany_bundesliga"
    markets = sys.argv[2].split(",") if len(sys.argv) > 2 else ["h2h", "totals"]
    result = run_once(sport, markets)
    print(result)
