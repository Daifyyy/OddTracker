"""Tests for db/database.py and db/queries.py using in-memory SQLite."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force local SQLite path by ensuring TURSO_URL is not set
os.environ.pop("TURSO_URL", None)
os.environ.pop("TURSO_TOKEN", None)

import sqlite3
from db.database import Connection, Row, _Cursor


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


# ── Connection wrapper ─────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    raw = sqlite3.connect(":memory:")
    c = Connection(raw)
    yield c
    c.close()


def test_execute_returns_cursor(conn):
    cur = conn.execute("SELECT 1 AS n")
    row = cur.fetchone()
    assert row["n"] == 1


def test_fetchall_returns_rows(conn):
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    with conn:
        conn.execute("INSERT INTO t VALUES (1, 'a')")
        conn.execute("INSERT INTO t VALUES (2, 'b')")
    rows = conn.execute("SELECT * FROM t ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] == 1
    assert rows[1]["val"] == "b"


def test_fetchone_none_on_empty(conn):
    conn.execute("CREATE TABLE t (id INTEGER)")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert row is None


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
    row = conn.execute("SELECT COUNT(*) AS n FROM t").fetchone()
    assert row["n"] == 0


def test_executescript_creates_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS a (id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS b (id INTEGER PRIMARY KEY)
    """)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in tables]
    assert "a" in names
    assert "b" in names


def test_select_changes(conn):
    conn.execute("CREATE TABLE t (v INTEGER)")
    with conn:
        conn.execute("INSERT INTO t VALUES (1)")
    n = conn.execute("SELECT changes()").fetchone()[0]
    assert n == 1


# ── _df helper ────────────────────────────────────────────────────────────────

import pandas as pd
from db.queries import _df


def test_df_returns_dataframe(conn):
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    with conn:
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
    df = _df(conn, "SELECT * FROM t")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b"]
    assert df.iloc[0]["a"] == 1


def test_df_empty_returns_empty_dataframe(conn):
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    df = _df(conn, "SELECT * FROM t")
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == ["a", "b"]


def test_df_with_params(conn):
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    with conn:
        conn.execute("INSERT INTO t VALUES (1, 'x')")
        conn.execute("INSERT INTO t VALUES (2, 'y')")
    df = _df(conn, "SELECT * FROM t WHERE id=?", (2,))
    assert len(df) == 1
    assert df.iloc[0]["val"] == "y"


# ── init_db smoke test ─────────────────────────────────────────────────────────

def test_init_db_creates_all_tables(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    # Re-import to pick up patched DB_PATH
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
