from db.database import get_connection


def migrate_db() -> None:
    """Add columns introduced after initial schema — safe to call repeatedly."""
    conn = get_connection()
    with conn:
        for stmt in [
            "ALTER TABLE fetch_presets ADD COLUMN auto_fetch INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # column already exists
    conn.close()


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fetch_presets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL UNIQUE,
                sport_key    TEXT    NOT NULL,
                competition  TEXT    NOT NULL,
                markets      TEXT    NOT NULL,
                bookmakers   TEXT    NOT NULL,
                regions      TEXT    NOT NULL DEFAULT 'eu',
                created_at   TEXT    NOT NULL,
                last_used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS matches (
                id            TEXT PRIMARY KEY,
                sport_key     TEXT NOT NULL,
                sport_title   TEXT NOT NULL,
                home_team     TEXT NOT NULL,
                away_team     TEXT NOT NULL,
                commence_time TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at  TEXT NOT NULL,
                is_completed  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS match_results (
                match_id          TEXT PRIMARY KEY,
                home_score        INTEGER,
                away_score        INTEGER,
                corners_home      INTEGER,
                corners_away      INTEGER,
                corners_total     INTEGER,
                result_fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS odds_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                match_id      TEXT NOT NULL,
                home_team     TEXT NOT NULL,
                away_team     TEXT NOT NULL,
                commence_time TEXT NOT NULL,
                bookmaker     TEXT NOT NULL,
                market        TEXT NOT NULL,
                selection     TEXT NOT NULL,
                line          REAL,
                odds          REAL NOT NULL,
                UNIQUE(snapshot_time, match_id, bookmaker, market, selection, line)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_match_market
                ON odds_snapshots(match_id, market, bookmaker, snapshot_time);
            CREATE INDEX IF NOT EXISTS idx_snapshots_time
                ON odds_snapshots(snapshot_time);
            CREATE INDEX IF NOT EXISTS idx_snapshots_commence
                ON odds_snapshots(commence_time);

            CREATE TABLE IF NOT EXISTS line_changes (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at        TEXT NOT NULL,
                match_id           TEXT NOT NULL,
                bookmaker          TEXT NOT NULL,
                market             TEXT NOT NULL,
                selection          TEXT NOT NULL,
                old_line           REAL,
                new_line           REAL,
                old_odds           REAL NOT NULL,
                new_odds           REAL NOT NULL,
                odds_delta         REAL NOT NULL,
                minutes_to_kickoff REAL
            );

            CREATE TABLE IF NOT EXISTS steam_moves (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at        TEXT NOT NULL,
                match_id           TEXT NOT NULL,
                market             TEXT NOT NULL,
                selection          TEXT NOT NULL,
                bookmaker_count    INTEGER NOT NULL,
                avg_odds_delta     REAL NOT NULL,
                direction          TEXT NOT NULL,
                minutes_to_kickoff REAL,
                notes              TEXT
            );

            CREATE TABLE IF NOT EXISTS clv_records (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id              TEXT NOT NULL,
                bookmaker             TEXT NOT NULL,
                market                TEXT NOT NULL,
                selection             TEXT NOT NULL,
                line                  REAL,
                tracked_odds          REAL NOT NULL,
                tracked_at            TEXT NOT NULL,
                closing_odds          REAL NOT NULL,
                clv_raw               REAL NOT NULL,
                clv_pct               REAL NOT NULL,
                closing_snapshot_time TEXT NOT NULL
            );
        """)
    conn.close()
    migrate_db()
