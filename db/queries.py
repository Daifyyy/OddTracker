import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from db.database import get_connection, Connection


def _df(conn: Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    if not rows:
        cols = [d[0] for d in cur.description] if cur.description else []
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)


# ── user_config ────────────────────────────────────────────────────────────────

def get_config(key: str, default: Any = None) -> Any:
    conn = get_connection()
    row = conn.execute("SELECT value FROM user_config WHERE key=?", (key,)).fetchone()
    conn.close()
    return json.loads(row["value"]) if row else default


def set_config(key: str, value: Any) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO user_config(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
    conn.close()


# ── fetch_presets ──────────────────────────────────────────────────────────────

def get_presets() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM fetch_presets ORDER BY last_used_at DESC NULLS LAST, name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_preset(name: str, sport_key: str, competition: str,
                markets: list, bookmakers: list, regions: str = "eu") -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO fetch_presets(name,sport_key,competition,markets,bookmakers,regions,created_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 sport_key=excluded.sport_key, competition=excluded.competition,
                 markets=excluded.markets, bookmakers=excluded.bookmakers,
                 regions=excluded.regions""",
            (name, sport_key, competition,
             json.dumps(markets), json.dumps(bookmakers), regions, now),
        )
    conn.close()


def delete_preset(name: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM fetch_presets WHERE name=?", (name,))
    conn.close()


def touch_preset(name: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE fetch_presets SET last_used_at=? WHERE name=?",
            (datetime.now(timezone.utc).isoformat(), name),
        )
    conn.close()


# ── matches ────────────────────────────────────────────────────────────────────

def upsert_matches(events: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    stmts = [
        (
            """INSERT INTO matches(id,sport_key,sport_title,home_team,away_team,
                                  commence_time,first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
            (e["id"], e["sport_key"], e["sport_title"],
             e["home_team"], e["away_team"], e["commence_time"], now, now),
        )
        for e in events
    ]
    conn.execute_batch(stmts)
    conn.close()


def get_matches_df(sport_key: str | None = None, only_active: bool = False) -> pd.DataFrame:
    conn = get_connection()
    where = []
    params: list = []
    if sport_key:
        where.append("sport_key=?")
        params.append(sport_key)
    if only_active:
        where.append("is_completed=0")
    sql = "SELECT * FROM matches"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY commence_time"
    df = _df(conn, sql, tuple(params))
    conn.close()
    return df


def mark_completed(match_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute("UPDATE matches SET is_completed=1 WHERE id=?", (match_id,))
    conn.close()


# ── odds_snapshots ─────────────────────────────────────────────────────────────

def insert_snapshots(rows: list[dict]) -> int:
    if not rows:
        return 0
    conn = get_connection()
    stmts = [
        (
            """INSERT OR IGNORE INTO odds_snapshots
               (snapshot_time,match_id,home_team,away_team,commence_time,
                bookmaker,market,selection,line,odds)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (r["snapshot_time"], r["match_id"], r["home_team"], r["away_team"],
             r["commence_time"], r["bookmaker"], r["market"],
             r["selection"], r.get("line"), r["odds"]),
        )
        for r in rows
    ]
    inserted = conn.execute_batch(stmts)
    conn.close()
    return inserted


def get_snapshots_df(match_id: str, market: str | None = None,
                     bookmaker: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    where = ["match_id=?"]
    params: list = [match_id]
    if market:
        where.append("market=?")
        params.append(market)
    if bookmaker:
        where.append("bookmaker=?")
        params.append(bookmaker)
    sql = ("SELECT * FROM odds_snapshots WHERE " + " AND ".join(where)
           + " ORDER BY snapshot_time")
    df = _df(conn, sql, tuple(params))
    conn.close()
    return df


def get_opening_odds(match_id: str, market: str) -> pd.DataFrame:
    conn = get_connection()
    df = _df(
        conn,
        """SELECT bookmaker, market, selection, line, odds, snapshot_time
           FROM odds_snapshots
           WHERE match_id=? AND market=?
             AND snapshot_time=(
               SELECT MIN(snapshot_time) FROM odds_snapshots
               WHERE match_id=? AND market=?)""",
        (match_id, market, match_id, market),
    )
    conn.close()
    return df


def get_closing_odds(match_id: str, market: str) -> pd.DataFrame:
    conn = get_connection()
    df = _df(
        conn,
        """SELECT bookmaker, market, selection, line, odds, snapshot_time
           FROM odds_snapshots o
           JOIN matches m ON o.match_id=m.id
           WHERE o.match_id=? AND o.market=?
             AND o.snapshot_time <= m.commence_time
             AND o.snapshot_time=(
               SELECT MAX(o2.snapshot_time)
               FROM odds_snapshots o2
               JOIN matches m2 ON o2.match_id=m2.id
               WHERE o2.match_id=? AND o2.market=?
                 AND o2.snapshot_time <= m2.commence_time)""",
        (match_id, market, match_id, market),
    )
    conn.close()
    return df


def get_latest_odds_per_book(match_id: str, market: str) -> pd.DataFrame:
    conn = get_connection()
    df = _df(
        conn,
        """SELECT bookmaker, selection, line, odds, snapshot_time
           FROM odds_snapshots
           WHERE match_id=? AND market=?
             AND snapshot_time=(
               SELECT MAX(snapshot_time) FROM odds_snapshots
               WHERE match_id=? AND market=?)
           ORDER BY bookmaker, selection""",
        (match_id, market, match_id, market),
    )
    conn.close()
    return df


# ── line_changes ───────────────────────────────────────────────────────────────

def get_line_changes_df(match_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if match_id:
        df = _df(
            conn,
            "SELECT * FROM line_changes WHERE match_id=? ORDER BY detected_at DESC",
            (match_id,),
        )
    else:
        df = _df(conn, "SELECT * FROM line_changes ORDER BY detected_at DESC LIMIT 500")
    conn.close()
    return df


# ── steam_moves ────────────────────────────────────────────────────────────────

def get_steam_moves_df(hours: int = 48) -> pd.DataFrame:
    conn = get_connection()
    df = _df(
        conn,
        """SELECT s.*, m.home_team, m.away_team, m.sport_key
           FROM steam_moves s JOIN matches m ON s.match_id=m.id
           WHERE s.detected_at >= datetime('now', ?)
           ORDER BY s.detected_at DESC""",
        (f"-{hours} hours",),
    )
    conn.close()
    return df


# ── clv_records ────────────────────────────────────────────────────────────────

def get_clv_df(sport_key: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if sport_key:
        df = _df(
            conn,
            """SELECT c.*, m.home_team, m.away_team, m.sport_key, m.commence_time
               FROM clv_records c JOIN matches m ON c.match_id=m.id
               WHERE m.sport_key=? ORDER BY c.tracked_at DESC""",
            (sport_key,),
        )
    else:
        df = _df(
            conn,
            """SELECT c.*, m.home_team, m.away_team, m.sport_key, m.commence_time
               FROM clv_records c JOIN matches m ON c.match_id=m.id
               ORDER BY c.tracked_at DESC""",
        )
    conn.close()
    return df


# ── match_results ──────────────────────────────────────────────────────────────

def get_results_df() -> pd.DataFrame:
    conn = get_connection()
    df = _df(
        conn,
        """SELECT r.*, m.home_team, m.away_team, m.sport_key, m.commence_time
           FROM match_results r JOIN matches m ON r.match_id=m.id
           ORDER BY m.commence_time DESC""",
    )
    conn.close()
    return df


def upsert_result(match_id: str, home_score: int | None, away_score: int | None,
                  corners_home: int | None, corners_away: int | None) -> None:
    total = None
    if corners_home is not None and corners_away is not None:
        total = corners_home + corners_away
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO match_results(match_id,home_score,away_score,
               corners_home,corners_away,corners_total,result_fetched_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(match_id) DO UPDATE SET
                 home_score=excluded.home_score, away_score=excluded.away_score,
                 corners_home=excluded.corners_home, corners_away=excluded.corners_away,
                 corners_total=excluded.corners_total,
                 result_fetched_at=excluded.result_fetched_at""",
            (match_id, home_score, away_score, corners_home, corners_away, total, now),
        )
    conn.close()
