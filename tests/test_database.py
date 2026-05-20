"""Tests for db/database.py and db/queries.py using in-memory SQLite."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("TURSO_URL", None)
os.environ.pop("TURSO_TOKEN", None)

import sqlite3
from db.database import Connection, Row, _Cursor, _TursoHTTPCursor, _TursoHTTPConnection


# ── Row ────────────────────────────────────────────────────────────────────────

def test_row_key_access():
    r = Row({"a": 1, "b": 2})
    assert r["a"] == 1
    assert r["b"] == 2


def test_row_index_access():
    r = Row({"a": 1, "b": 2})
    assert r[0] == 1
    assert r[1] == 2


def test_row_is_dict():
    r = Row({"x": 42})
    assert isinstance(r, dict)
    assert dict(r) == {"x": 42}


# ── Connection (sqlite3) ───────────────────────────────────────────────────────

@pytest.fixture
def conn():
    raw = sqlite3.connect(":memory:")
    c = Connection(raw)
    yield c
    c.close()


def test_execute_returns_row(conn):
    cur = conn.execute("SELECT 1 AS n")
    row = cur.fetchone()
    assert row["n"] == 1


def test_fetchall_returns_rows(conn):
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    conn.execute_batch([
        ("INSERT INTO t VALUES (1, 'a')", ()),
        ("INSERT INTO t VALUES (2, 'b')", ()),
    ])
    rows = conn.execute("SELECT * FROM t ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] == 1
    assert rows[1]["val"] == "b"


def test_fetchone_none_on_empty(conn):
    conn.execute("CREATE TABLE t (id INTEGER)")
    assert conn.execute("SELECT * FROM t").fetchone() is None


def test_context_manager_commits(conn):
    conn.execute("CREATE TABLE t (v INTEGER)")
    with conn:
        conn.execute("INSERT INTO t VALUES (99)")
    row = conn.execute("SELECT v FROM t").fetchone()
    assert row["v"] == 99


def test_context_manager_rollback_on_exception(conn):
    conn.execute("CREATE TABLE t (v INTEGER NOT NULL)")
    conn.commit()
    try:
        with conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise ValueError("intentional")
    except ValueError:
        pass
    assert conn.execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"] == 0


def test_executescript_creates_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS a (id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS b (id INTEGER PRIMARY KEY)
    """)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {"a", "b"}.issubset(tables)


def test_select_changes(conn):
    conn.execute("CREATE TABLE t (v INTEGER)")
    with conn:
        conn.execute("INSERT INTO t VALUES (1)")
    n = conn.execute("SELECT changes()").fetchone()[0]
    assert n == 1


def test_execute_batch_returns_affected(conn):
    conn.execute("CREATE TABLE t (v INTEGER)")
    n = conn.execute_batch([
        ("INSERT INTO t VALUES (1)", ()),
        ("INSERT INTO t VALUES (2)", ()),
    ])
    assert n == 2


def test_execute_batch_ignores_duplicates(conn):
    conn.execute("CREATE TABLE t (v INTEGER UNIQUE)")
    n = conn.execute_batch([
        ("INSERT OR IGNORE INTO t VALUES (1)", ()),
        ("INSERT OR IGNORE INTO t VALUES (1)", ()),  # duplicate → ignored
    ])
    assert n == 1
    assert conn.execute("SELECT COUNT(*) AS c FROM t").fetchone()["c"] == 1


# ── _df helper ─────────────────────────────────────────────────────────────────

import pandas as pd
from db.queries import _df


def test_df_returns_dataframe(conn):
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.execute_batch([("INSERT INTO t VALUES (1, 'hello')", ())])
    df = _df(conn, "SELECT * FROM t")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b"]
    assert df.iloc[0]["a"] == 1


def test_df_empty_returns_empty_dataframe(conn):
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    df = _df(conn, "SELECT * FROM t")
    assert df.empty
    assert list(df.columns) == ["a", "b"]


def test_df_with_params(conn):
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    conn.execute_batch([
        ("INSERT INTO t VALUES (1, 'x')", ()),
        ("INSERT INTO t VALUES (2, 'y')", ()),
    ])
    df = _df(conn, "SELECT * FROM t WHERE id=?", (2,))
    assert len(df) == 1
    assert df.iloc[0]["val"] == "y"


# ── init_db smoke test ─────────────────────────────────────────────────────────

def test_init_db_creates_all_tables(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    import importlib
    import db.database as dbmod
    importlib.reload(dbmod)
    import db.models as models
    importlib.reload(models)

    models.init_db()

    raw = sqlite3.connect(str(tmp_path / "test.db"))
    tables = {r[0] for r in raw.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    raw.close()

    expected = {
        "user_config", "fetch_presets", "matches", "match_results",
        "odds_snapshots", "line_changes", "steam_moves", "clv_records",
    }
    assert expected.issubset(tables)


# ── detect_line_changes (SQL rewrite) ─────────────────────────────────────────

from db.models import init_db as _init_db
from analytics.movements import detect_line_changes


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import config, db.database, db.models, db.queries, analytics.movements
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    import importlib
    for mod in (db.database, db.models, db.queries, analytics.movements):
        importlib.reload(mod)
    db.models.init_db()
    return tmp_path / "t.db"


def _insert_snapshot(db_path, snapshot_time, match_id, bookmaker, market, selection, odds, line=None):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT OR IGNORE INTO odds_snapshots
           (snapshot_time,match_id,home_team,away_team,commence_time,
            bookmaker,market,selection,line,odds)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (snapshot_time, match_id, "H", "A", "2099-01-01T20:00:00Z",
         bookmaker, market, selection, line, odds),
    )
    conn.commit()
    conn.close()


def test_detect_line_changes_detects_move(fresh_db):
    _insert_snapshot(fresh_db, "2024-01-01T10:00:00", "m1", "pinnacle", "h2h", "Home", 2.00)
    _insert_snapshot(fresh_db, "2024-01-01T11:00:00", "m1", "pinnacle", "h2h", "Home", 1.90)

    from analytics.movements import detect_line_changes as dlc
    n = dlc("2024-01-01T11:00:00")
    assert n == 1

    conn = sqlite3.connect(str(fresh_db))
    row = conn.execute("SELECT * FROM line_changes").fetchone()
    conn.close()
    assert row is not None
    assert abs(row[10] - (-0.1)) < 0.001  # odds_delta column


def test_detect_line_changes_no_move_on_first_snapshot(fresh_db):
    _insert_snapshot(fresh_db, "2024-01-01T10:00:00", "m1", "pinnacle", "h2h", "Home", 2.00)
    from analytics.movements import detect_line_changes as dlc
    assert dlc("2024-01-01T10:00:00") == 0


def test_detect_line_changes_ignores_tiny_move(fresh_db):
    _insert_snapshot(fresh_db, "2024-01-01T10:00:00", "m1", "pinnacle", "h2h", "Home", 2.000)
    _insert_snapshot(fresh_db, "2024-01-01T11:00:00", "m1", "pinnacle", "h2h", "Home", 2.005)
    from analytics.movements import detect_line_changes as dlc
    assert dlc("2024-01-01T11:00:00") == 0


# ── _TursoHTTPCursor ───────────────────────────────────────────────────────────

def test_turso_cursor_fetchone():
    cur = _TursoHTTPCursor(["a", "b"], [Row({"a": 1, "b": 2})], 1)
    row = cur.fetchone()
    assert row["a"] == 1
    assert cur.fetchone() is None


def test_turso_cursor_fetchall():
    rows = [Row({"v": i}) for i in range(3)]
    cur = _TursoHTTPCursor(["v"], rows, 3)
    result = cur.fetchall()
    assert len(result) == 3
    assert result[2]["v"] == 2


def test_turso_cursor_description():
    cur = _TursoHTTPCursor(["x", "y"], [], 0)
    assert cur.description[0][0] == "x"
    assert cur.description[1][0] == "y"


def test_turso_cursor_no_description_when_no_cols():
    cur = _TursoHTTPCursor(None, [], 0)
    assert cur.description is None


# ── _TursoHTTPConnection (mocked HTTP) ────────────────────────────────────────

import unittest.mock as mock


def _turso_response(cols, rows_raw, affected=0):
    """Build a fake Turso pipeline HTTP response."""
    return {
        "results": [
            {
                "type": "ok",
                "response": {
                    "type": "execute",
                    "result": {
                        "cols": [{"name": c} for c in cols],
                        "rows": rows_raw,
                        "affected_row_count": affected,
                    },
                },
            },
            {"type": "ok", "response": {"type": "close"}},
        ]
    }


def _make_turso(mock_post, response_json):
    mock_resp = mock.Mock()
    mock_resp.raise_for_status = mock.Mock()
    mock_resp.json.return_value = response_json
    mock_post.return_value = mock_resp
    return _TursoHTTPConnection("libsql://test.turso.io", "token")


@mock.patch("requests.post")
def test_turso_execute_select(mock_post):
    response = _turso_response(
        ["id", "name"],
        [[{"type": "integer", "value": "1"}, {"type": "text", "value": "Alice"}]],
    )
    turso = _make_turso(mock_post, response)
    row = turso.execute("SELECT * FROM users").fetchone()
    assert row["id"] == 1
    assert row["name"] == "Alice"


@mock.patch("requests.post")
def test_turso_execute_returns_affected(mock_post):
    response = _turso_response([], [], affected=3)
    turso = _make_turso(mock_post, response)
    cur = turso.execute("INSERT INTO t VALUES (1)")
    assert cur.rowcount == 3


@mock.patch("requests.post")
def test_turso_changes_intercept(mock_post):
    response = _turso_response([], [], affected=1)
    turso = _make_turso(mock_post, response)
    turso.execute("INSERT INTO t VALUES (1)")
    n = turso.execute("SELECT changes()").fetchone()[0]
    assert n == 1
    assert mock_post.call_count == 1  # changes() must NOT trigger extra HTTP call


@mock.patch("requests.post")
def test_turso_execute_batch_one_request(mock_post):
    """execute_batch must send all statements in a single HTTP call."""
    response = {
        "results": [
            {"type": "ok", "response": {"type": "execute",
                                         "result": {"cols": [], "rows": [], "affected_row_count": 1}}},
            {"type": "ok", "response": {"type": "execute",
                                         "result": {"cols": [], "rows": [], "affected_row_count": 1}}},
            {"type": "ok", "response": {"type": "close"}},
        ]
    }
    mock_resp = mock.Mock()
    mock_resp.raise_for_status = mock.Mock()
    mock_resp.json.return_value = response
    mock_post.return_value = mock_resp

    turso = _TursoHTTPConnection("libsql://test.turso.io", "token")
    total = turso.execute_batch([
        ("INSERT INTO t VALUES (1)", ()),
        ("INSERT INTO t VALUES (2)", ()),
    ])
    assert total == 2
    assert mock_post.call_count == 1  # single HTTP call


@mock.patch("requests.post")
def test_turso_decode_null(mock_post):
    response = _turso_response(["v"], [[{"type": "null"}]])
    turso = _make_turso(mock_post, response)
    row = turso.execute("SELECT v FROM t").fetchone()
    assert row["v"] is None


@mock.patch("requests.post")
def test_turso_encode_params(mock_post):
    response = _turso_response([], [], affected=1)
    turso = _make_turso(mock_post, response)
    turso.execute("INSERT INTO t VALUES (?, ?, ?)", (42, 3.14, "hello"))
    sent = mock_post.call_args[1]["json"]
    args = sent["requests"][0]["stmt"]["args"]
    assert args[0] == {"type": "integer", "value": "42"}
    assert args[1] == {"type": "float", "value": 3.14}
    assert args[2] == {"type": "text", "value": "hello"}
