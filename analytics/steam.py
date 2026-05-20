from datetime import datetime, timezone, timedelta

from db.database import get_connection
from config import STEAM_MIN_BOOKS, STEAM_MIN_ODDS_DELTA, STEAM_WINDOW_MINUTES


def detect_steam_moves(snapshot_time: str) -> int:
    window_start = (
        datetime.fromisoformat(snapshot_time.replace("Z", "+00:00"))
        - timedelta(minutes=STEAM_WINDOW_MINUTES)
    ).isoformat()

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO steam_moves
            (detected_at, match_id, market, selection,
             bookmaker_count, avg_odds_delta, direction, minutes_to_kickoff)
        SELECT
            ?,
            match_id,
            market,
            selection,
            COUNT(*)                                              AS bookmaker_count,
            ROUND(AVG(odds_delta), 4)                            AS avg_odds_delta,
            CASE WHEN AVG(odds_delta) > 0 THEN 'up' ELSE 'down' END AS direction,
            MIN(minutes_to_kickoff)                              AS minutes_to_kickoff
        FROM line_changes
        WHERE detected_at >= ? AND detected_at <= ?
        GROUP BY match_id, market, selection
        HAVING COUNT(*) >= ?
           AND ABS(AVG(odds_delta)) >= ?
           AND COUNT(CASE WHEN odds_delta > 0 THEN 1 END) IN (0, COUNT(*))
        """,
        (snapshot_time, window_start, snapshot_time,
         STEAM_MIN_BOOKS, STEAM_MIN_ODDS_DELTA),
    )
    inserted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    return inserted
