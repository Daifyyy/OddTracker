from datetime import datetime, timezone


def flatten_odds(events: list[dict], snapshot_time: str | None = None) -> list[dict]:
    if snapshot_time is None:
        snapshot_time = datetime.now(timezone.utc).isoformat()

    rows = []
    for event in events:
        match_id      = event["id"]
        home_team     = event["home_team"]
        away_team     = event["away_team"]
        commence_time = event["commence_time"]

        for bm in event.get("bookmakers", []):
            bookmaker = bm["key"]
            for mkt in bm.get("markets", []):
                market = mkt["key"]
                for outcome in mkt.get("outcomes", []):
                    rows.append({
                        "snapshot_time": snapshot_time,
                        "match_id":      match_id,
                        "home_team":     home_team,
                        "away_team":     away_team,
                        "commence_time": commence_time,
                        "bookmaker":     bookmaker,
                        "market":        market,
                        "selection":     outcome["name"],
                        "line":          outcome.get("point"),
                        "odds":          outcome["price"],
                    })
    return rows


def extract_events(events: list[dict]) -> list[dict]:
    return [
        {
            "id":           e["id"],
            "sport_key":    e["sport_key"],
            "sport_title":  e["sport_title"],
            "home_team":    e["home_team"],
            "away_team":    e["away_team"],
            "commence_time": e["commence_time"],
        }
        for e in events
    ]
