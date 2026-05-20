import os
import sqlite3

from config import DB_PATH

TURSO_URL = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")


class Row(dict):
    """Dict subclass supporting both key and integer index access."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, raw):
        self._raw = raw

    @property
    def description(self):
        return self._raw.description

    @property
    def rowcount(self):
        return getattr(self._raw, "rowcount", -1)

    def _wrap(self, raw_row):
        if raw_row is None:
            return None
        if self._raw.description:
            cols = [d[0] for d in self._raw.description]
            if isinstance(raw_row, dict):
                return Row(raw_row)
            return Row(zip(cols, raw_row))
        return raw_row

    def fetchone(self):
        return self._wrap(self._raw.fetchone())

    def fetchall(self):
        rows = self._raw.fetchall()
        if not rows or not self._raw.description:
            return rows
        cols = [d[0] for d in self._raw.description]
        return [Row(r) if isinstance(r, dict) else Row(zip(cols, r)) for r in rows]

    def fetchmany(self, size=None):
        rows = self._raw.fetchmany(size) if size is not None else self._raw.fetchmany()
        if not rows or not self._raw.description:
            return rows
        cols = [d[0] for d in self._raw.description]
        return [Row(r) if isinstance(r, dict) else Row(zip(cols, r)) for r in rows]

    def close(self):
        if hasattr(self._raw, "close"):
            self._raw.close()


class Connection:
    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return _Cursor(self._raw.cursor())

    def execute(self, sql: str, params: tuple = ()) -> _Cursor:
        return _Cursor(self._raw.execute(sql, params))

    def executescript(self, script: str) -> None:
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._raw.execute(stmt)
        self._raw.commit()

    def commit(self):
        self._raw.commit()

    def rollback(self):
        if hasattr(self._raw, "rollback"):
            self._raw.rollback()

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.rollback()
        else:
            self.commit()


def get_connection() -> Connection:
    if TURSO_URL and TURSO_TOKEN:
        import libsql_experimental as libsql
        raw = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    else:
        raw = sqlite3.connect(DB_PATH)
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
    return Connection(raw)
