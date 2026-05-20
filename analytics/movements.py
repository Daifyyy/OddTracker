from datetime import datetime, timezone

from db.database import get_connection


def detect_line_changes(snapshot_time: str) -> int:
    conn = get_connection()
    # Find all (match, bookmaker, market, selection) combos in the latest snapshot
    new_rows = conn.execute(
        """SELECT match_id, bookmaker, market, selection, line, odds, commence_time
           FROM odds_snapshots WHERE snapshot_time=?""",
        (snapshot_time,),
    ).fetchall()

    inserted = 0
    with conn:
        for row in new_rows:
            # Get the most recent previous snapshot for this combo
            prev = conn.execute(
                """SELECT line, odds FROM odds_snapshots
                   WHERE match_id=? AND bookmaker=? AND market=? AND selection=?
                     AND snapshot_time < ?
                   ORDER BY snapshot_time DESC LIMIT 1""",
                (row["match_id"], row["bookmaker"], row["market"],
                 row["selection"], snapshot_time),
            ).fetchone()

            if prev is None:
                continue

            odds_delta = round(row["odds"] - prev["odds"], 4)
            line_changed = (prev["line"] != row["line"])
            odds_changed = abs(odds_delta) >= 0.01

            if not (line_changed or odds_changed):
                continue

            try:
                ko = datetime.fromisoformat(row["commence_time"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                minutes_to_kickoff = (ko - now).total_seconds() / 60
            except Exception:
                minutes_to_kickoff = None

            conn.execute(
                """INSERT INTO line_changes
                   (detected_at, match_id, bookmaker, market, selection,
                    old_line, new_line, old_odds, new_odds, odds_delta, minutes_to_kickoff)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_time, row["match_id"], row["bookmaker"], row["market"],
                 row["selection"], prev["line"], row["line"],
                 prev["odds"], row["odds"], odds_delta, minutes_to_kickoff),
            )
            inserted += 1

    conn.close()
    return inserted
