from datetime import datetime, timezone, timedelta

from db.database import get_connection
from config import STEAM_MIN_BOOKS, STEAM_MIN_ODDS_DELTA, STEAM_WINDOW_MINUTES


def detect_steam_moves(snapshot_time: str) -> int:
    conn = get_connection()
    window_start = (
        datetime.fromisoformat(snapshot_time.replace("Z", "+00:00"))
        - timedelta(minutes=STEAM_WINDOW_MINUTES)
    ).isoformat()

    changes = conn.execute(
        """SELECT match_id, market, selection, bookmaker, odds_delta, minutes_to_kickoff
           FROM line_changes
           WHERE detected_at >= ? AND detected_at <= ?""",
        (window_start, snapshot_time),
    ).fetchall()

    # Group by (match_id, market, selection)
    groups: dict[tuple, list] = {}
    for c in changes:
        key = (c["match_id"], c["market"], c["selection"])
        groups.setdefault(key, []).append(c)

    inserted = 0
    with conn:
        for (match_id, market, selection), items in groups.items():
            if len(items) < STEAM_MIN_BOOKS:
                continue

            avg_delta = sum(i["odds_delta"] for i in items) / len(items)
            if abs(avg_delta) < STEAM_MIN_ODDS_DELTA:
                continue

            # All must move in the same direction
            directions = set("up" if i["odds_delta"] > 0 else "down" for i in items)
            if len(directions) != 1:
                continue

            direction = directions.pop()
            minutes_to_kickoff = items[0]["minutes_to_kickoff"]

            conn.execute(
                """INSERT INTO steam_moves
                   (detected_at, match_id, market, selection,
                    bookmaker_count, avg_odds_delta, direction, minutes_to_kickoff)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (snapshot_time, match_id, market, selection,
                 len(items), round(avg_delta, 4), direction, minutes_to_kickoff),
            )
            inserted += 1

    conn.close()
    return inserted
