"""
Shared test infrastructure for Wordle Tournament E2E tests.
Uses an in-memory SQLite DB, mocked SMTP, and a live Flask test server.
"""

import smtplib
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# ── App setup ────────────────────────────────────────────────────────────────

SMTP_OUTBOX: list[dict] = []
_outbox_lock = threading.Lock()


class _MockSMTP:
    """Captures emails instead of sending them."""

    sent: list[dict] = SMTP_OUTBOX

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        with _outbox_lock:
            SMTP_OUTBOX.append({"from": from_addr, "to": to_addrs, "msg": msg})

    def quit(self):
        pass


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch (stdlib smtplib cannot be re-patched per test easily)."""
    import smtplib as _smtplib
    original = _smtplib.SMTP
    _smtplib.SMTP = _MockSMTP
    yield
    _smtplib.SMTP = original


@pytest.fixture(scope="session")
def flask_app(monkeypatch_session, tmp_path_factory):
    """Create a test Flask app with an isolated temp database."""
    db_path = str(tmp_path_factory.mktemp("db") / "test.db")

    import os
    from dotenv import load_dotenv
    # Load .env first so real credentials are available, then fall back to test values
    load_dotenv()
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
    os.environ.setdefault("SMTP_HOST", "localhost")
    os.environ.setdefault("SMTP_PORT", "1025")
    os.environ.setdefault("SMTP_USERNAME", "test")
    os.environ.setdefault("SMTP_PASSWORD", "test")
    os.environ.setdefault("EMAIL_SENDER", "test@example.com")
    os.environ.setdefault("VAPID_PRIVATE_KEY", "test")
    os.environ.setdefault("VAPID_PUBLIC_KEY", "test")
    os.environ.setdefault("VAPID_CLAIMS_EMAIL", "test@example.com")

    # Reset cached config so env vars take effect
    import app.config as cfg_module
    cfg_module._config = None

    from app import create_app
    flask_app = create_app({"DATABASE": db_path, "TESTING": True})
    yield flask_app


@pytest.fixture(scope="session")
def live_server(flask_app) -> Generator[str, None, None]:
    """Start Flask development server on a free port for Playwright tests."""
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, flask_app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    b = playwright_instance.chromium.launch(headless=True)
    yield b
    b.close()


@pytest.fixture
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    ctx = browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Generator[Page, None, None]:
    p = context.new_page()
    yield p
    p.close()


# ── DB helpers ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_db(flask_app):
    """Truncate all tables between tests for isolation."""
    with flask_app.app_context():
        from app import db
        db.execute("DELETE FROM push_subscriptions")
        db.execute("DELETE FROM scores")
        db.execute("DELETE FROM tournament_members")
        db.execute("DELETE FROM tournaments")
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM auth_codes")
        db.execute("DELETE FROM users")
    yield


@pytest.fixture(autouse=True)
def clear_smtp_outbox():
    """Clear SMTP outbox between tests."""
    with _outbox_lock:
        SMTP_OUTBOX.clear()
    yield


@pytest.fixture
def smtp_outbox() -> list[dict]:
    return SMTP_OUTBOX


def create_user(flask_app, email: str, name: str = "Test User",
                timezone: str = "America/New_York",
                is_admin: bool = False) -> dict:
    """Insert a user directly into the DB and return it as a dict."""
    with flask_app.app_context():
        from app import db
        auth_key = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (email, name, timezone, is_admin, auth_key) VALUES (?, ?, ?, ?, ?)",
            (email, name, timezone, int(is_admin), auth_key),
        )
        row = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
        return dict(row)


def create_session_for_user(flask_app, user_id: int) -> str:
    """Insert a session row and return the token."""
    with flask_app.app_context():
        from app import db
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at.isoformat()),
        )
        return token


def login_as(page: Page, flask_app, base_url: str, user: dict) -> str:
    """Set session cookie for a user so the page is authenticated."""
    token = create_session_for_user(flask_app, user["id"])
    page.context.add_cookies([{
        "name": "wt_session",
        "value": token,
        "url": base_url,
        "httpOnly": True,
        "sameSite": "Lax",
    }])
    return token


# ── User fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def regular_user(flask_app) -> dict:
    return create_user(flask_app, "player@example.com", "Test Player")


@pytest.fixture
def admin_user(flask_app) -> dict:
    return create_user(flask_app, "admin@example.com", "Admin User", is_admin=True)


@pytest.fixture
def user_page(page: Page, flask_app, live_server: str, regular_user: dict) -> Page:
    """Page pre-authenticated as a regular user."""
    login_as(page, flask_app, live_server, regular_user)
    return page


@pytest.fixture
def admin_page(page: Page, flask_app, live_server: str, admin_user: dict) -> Page:
    """Page pre-authenticated as admin."""
    login_as(page, flask_app, live_server, admin_user)
    return page
