import sqlite3
import threading
from pathlib import Path

_local = threading.local()
_app = None


def init_app(app):
    global _app
    _app = app
    app.teardown_appcontext(_teardown)


def _get_db_path() -> str:
    if _app is not None:
        return _app.config["DATABASE"]
    raise RuntimeError("No app configured")


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        path = _get_db_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def _teardown(exc):
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def init_db():
    schema = Path(__file__).parent / "db" / "schema.sql"
    conn = get_db()
    conn.executescript(schema.read_text())
    conn.commit()


def query_one(sql: str, params=()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def query_all(sql: str, params=()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def execute(sql: str, params=()) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur
