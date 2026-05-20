from db.database import get_connection


def detect_line_changes(snapshot_time: str) -> int:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO line_changes
            (detected_at, match_id, bookmaker, market, selection,
             old_line, new_line, old_odds, new_odds, odds_delta, minutes_to_kickoff)
        SELECT
            ?,
            n.match_id,
            n.bookmaker,
            n.market,
            n.selection,
            prev.line,
            n.line,
            prev.odds,
            n.odds,
            ROUND(n.odds - prev.odds, 4),
            ROUND((julianday(n.commence_time) - julianday('now')) * 1440, 1)
        FROM odds_snapshots n
        JOIN (
            SELECT match_id, bookmaker, market, selection, MAX(snapshot_time) AS max_time
            FROM odds_snapshots
            WHERE snapshot_time < ?
            GROUP BY match_id, bookmaker, market, selection
        ) latest
            ON  n.match_id  = latest.match_id
            AND n.bookmaker = latest.bookmaker
            AND n.market    = latest.market
            AND n.selection = latest.selection
        JOIN odds_snapshots prev
            ON  prev.match_id   = latest.match_id
            AND prev.bookmaker  = latest.bookmaker
            AND prev.market     = latest.market
            AND prev.selection  = latest.selection
            AND prev.snapshot_time = latest.max_time
        WHERE n.snapshot_time = ?
          AND (
              (prev.line IS NOT n.line)
              OR ABS(n.odds - prev.odds) >= 0.01
          )
        """,
        (snapshot_time, snapshot_time, snapshot_time),
    )
    inserted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    return inserted
