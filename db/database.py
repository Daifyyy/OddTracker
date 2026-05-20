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


# ── sqlite3 wrapper ────────────────────────────────────────────────────────────

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
            return Row(r) if isinstance(raw_row, dict) else Row(zip(cols, raw_row))
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


class Connection:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql: str, params: tuple = ()) -> _Cursor:
        return _Cursor(self._raw.execute(sql, params))

    def execute_batch(self, stmts: list[tuple[str, tuple]]) -> int:
        """Execute many (sql, params) pairs; return total affected rows."""
        total = 0
        for sql, params in stmts:
            self._raw.execute(sql, params)
            total += self._raw.execute("SELECT changes()").fetchone()[0]
        self._raw.commit()
        return total

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


# ── Turso HTTP wrapper (no native dependencies) ────────────────────────────────

class _TursoHTTPCursor:
    def __init__(self, cols, rows, affected):
        self._cols = cols
        self._rows = rows
        self._pos = 0
        self.rowcount = affected

    @property
    def description(self):
        if not self._cols:
            return None
        return [(c, None, None, None, None, None, None) for c in self._cols]

    def fetchone(self):
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchall(self):
        rows = self._rows[self._pos:]
        self._pos = len(self._rows)
        return rows

    def fetchmany(self, size=None):
        size = size or 100
        rows = self._rows[self._pos:self._pos + size]
        self._pos += len(rows)
        return rows


class _TursoHTTPConnection:
    def __init__(self, url: str, token: str):
        self._url = url.replace("libsql://", "https://") + "/v2/pipeline"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._last_changes = 0

    @staticmethod
    def _encode(val):
        if val is None:
            return {"type": "null"}
        if isinstance(val, bool):
            return {"type": "integer", "value": str(int(val))}
        if isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        if isinstance(val, float):
            return {"type": "real", "value": str(val)}
        return {"type": "text", "value": str(val)}

    @staticmethod
    def _decode(cell):
        t = cell.get("type")
        if t == "null":
            return None
        if t == "integer":
            return int(cell["value"])
        if t == "real":
            return float(cell["value"])
        return cell.get("value")

    def _pipeline(self, stmts: list[tuple[str, tuple]], ignore_errors=False):
        import requests
        reqs = []
        for sql, params in stmts:
            stmt: dict = {"sql": sql}
            if params:
                stmt["args"] = [self._encode(p) for p in params]
            reqs.append({"type": "execute", "stmt": stmt})
        reqs.append({"type": "close"})

        resp = requests.post(self._url, json={"requests": reqs},
                             headers=self._headers, timeout=30, verify=False)
        resp.raise_for_status()

        cursors = []
        for res in resp.json()["results"][:-1]:
            if res["type"] == "error":
                if not ignore_errors:
                    raise Exception(res.get("error", {}).get("message", "Turso error"))
                cursors.append(_TursoHTTPCursor(None, [], 0))
                continue
            r = res["response"]["result"]
            cols = [c["name"] for c in r.get("cols", [])]
            rows = [Row(zip(cols, [self._decode(cell) for cell in raw]))
                    for raw in r.get("rows", [])]
            cursors.append(_TursoHTTPCursor(cols or None, rows,
                                            r.get("affected_row_count", 0)))
        return cursors

    def execute(self, sql: str, params: tuple = ()) -> _TursoHTTPCursor:
        # Intercept changes() — return cached value from previous write
        if sql.strip().upper().startswith("SELECT CHANGES()"):
            return _TursoHTTPCursor(["changes()"],
                                    [Row({"changes()": self._last_changes})], 0)
        cur = self._pipeline([(sql, params)])[0]
        self._last_changes = cur.rowcount
        return cur

    def execute_batch(self, stmts: list[tuple[str, tuple]]) -> int:
        """Send all statements in one HTTP roundtrip; return total affected rows."""
        if not stmts:
            return 0
        cursors = self._pipeline(stmts, ignore_errors=True)
        total = sum(c.rowcount for c in cursors)
        self._last_changes = total
        return total

    def executescript(self, script: str) -> None:
        stmts = [(s.strip(), ()) for s in script.split(";") if s.strip()]
        if stmts:
            self._pipeline(stmts)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


# ── factory ────────────────────────────────────────────────────────────────────

def get_connection():
    if TURSO_URL and TURSO_TOKEN:
        return _TursoHTTPConnection(TURSO_URL, TURSO_TOKEN)
    raw = sqlite3.connect(DB_PATH)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    return Connection(raw)
