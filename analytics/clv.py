from datetime import datetime, timezone

from db.database import get_connection
from db.queries import mark_completed


def mark_matches_completed() -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM matches WHERE is_completed=0 AND commence_time <= ?", (now,)
    ).fetchall()

    count = 0
    for row in rows:
        mark_completed(row["id"])
        calculate_clv_for_match(row["id"])
        count += 1

    conn.close()
    return count


def calculate_clv_for_match(match_id: str) -> int:
    conn = get_connection()

    # Get the match commence time
    match = conn.execute(
        "SELECT commence_time FROM matches WHERE id=?", (match_id,)
    ).fetchone()
    if not match:
        conn.close()
        return 0

    # For each (bookmaker, market, selection, line): find opening and closing odds
    combos = conn.execute(
        """SELECT DISTINCT bookmaker, market, selection, line
           FROM odds_snapshots WHERE match_id=?""",
        (match_id,),
    ).fetchall()

    inserted = 0
    with conn:
        for combo in combos:
            bm, mkt, sel, line = combo["bookmaker"], combo["market"], combo["selection"], combo["line"]

            opening = conn.execute(
                """SELECT odds, snapshot_time FROM odds_snapshots
                   WHERE match_id=? AND bookmaker=? AND market=? AND selection=?
                     AND (line=? OR (line IS NULL AND ? IS NULL))
                   ORDER BY snapshot_time ASC LIMIT 1""",
                (match_id, bm, mkt, sel, line, line),
            ).fetchone()

            closing = conn.execute(
                """SELECT odds, snapshot_time FROM odds_snapshots
                   WHERE match_id=? AND bookmaker=? AND market=? AND selection=?
                     AND (line=? OR (line IS NULL AND ? IS NULL))
                     AND snapshot_time <= ?
                   ORDER BY snapshot_time DESC LIMIT 1""",
                (match_id, bm, mkt, sel, line, line, match["commence_time"]),
            ).fetchone()

            if not opening or not closing:
                continue
            if opening["odds"] == closing["odds"]:
                continue

            clv_raw = round(opening["odds"] - closing["odds"], 4)
            clv_pct = round((opening["odds"] / closing["odds"] - 1) * 100, 2)

            conn.execute(
                """INSERT OR IGNORE INTO clv_records
                   (match_id, bookmaker, market, selection, line,
                    tracked_odds, tracked_at, closing_odds, clv_raw, clv_pct,
                    closing_snapshot_time)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (match_id, bm, mkt, sel, line,
                 opening["odds"], opening["snapshot_time"],
                 closing["odds"], clv_raw, clv_pct, closing["snapshot_time"]),
            )
            inserted += 1

    conn.close()
    return inserted
