"""Unit tests for push notification utilities (pywebpush mocked)."""

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ── App bootstrap ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flask_app(tmp_path_factory):
    import os
    from dotenv import load_dotenv
    load_dotenv()
    os.environ.setdefault("SECRET_KEY", "unit-test-secret")
    os.environ.setdefault("SMTP_HOST", "localhost")
    os.environ.setdefault("SMTP_PORT", "1025")
    os.environ.setdefault("SMTP_USERNAME", "test")
    os.environ.setdefault("SMTP_PASSWORD", "test")
    os.environ.setdefault("EMAIL_SENDER", "test@example.com")
    os.environ.setdefault("VAPID_PRIVATE_KEY", "test-private-key")
    os.environ.setdefault("VAPID_PUBLIC_KEY", "test-public-key")
    os.environ.setdefault("VAPID_CLAIMS_EMAIL", "test@example.com")

    import app.config as cfg_module
    cfg_module._config = None

    db_path = str(tmp_path_factory.mktemp("unit_db") / "unit.db")
    from app import create_app
    return create_app({"DATABASE": db_path, "TESTING": True})


@pytest.fixture(autouse=True)
def clean_db(flask_app):
    with flask_app.app_context():
        from app import db
        db.execute("DELETE FROM push_subscriptions")
        db.execute("DELETE FROM scores")
        db.execute("DELETE FROM tournament_members")
        db.execute("DELETE FROM tournaments")
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM users")
    yield


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_user(flask_app, email="user@test.com", is_admin=False):
    with flask_app.app_context():
        from app import db
        auth_key = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (email, name, timezone, is_admin, auth_key) VALUES (?, ?, ?, ?, ?)",
            (email, "Test", "UTC", int(is_admin), auth_key),
        )
        return dict(db.query_one("SELECT * FROM users WHERE email = ?", (email,)))


def _make_subscription(flask_app, user_id, endpoint="https://fcm.example.com/push/fake"):
    with flask_app.app_context():
        from app import db
        db.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
            (user_id, endpoint, "p256dh-key", "auth-key"),
        )


def _make_session(flask_app, user_id):
    with flask_app.app_context():
        from app import db
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at.isoformat()),
        )
        return token


# ── send_push ─────────────────────────────────────────────────────────────────

class TestSendPush:
    SUBSCRIPTION = {
        "endpoint": "https://fcm.example.com/push/abc",
        "keys": {"p256dh": "key", "auth": "auth"},
    }
    PAYLOAD = {"title": "Test", "body": "Hello", "url": "/"}

    def test_returns_true_on_success(self, flask_app):
        with flask_app.app_context():
            from app.pwa.push_utils import send_push
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush") as mock_wp:
                result = send_push(self.SUBSCRIPTION, self.PAYLOAD, cfg)
            assert result is True
            mock_wp.assert_called_once()

    def test_payload_serialized_as_json(self, flask_app):
        with flask_app.app_context():
            from app.pwa.push_utils import send_push
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush") as mock_wp:
                send_push(self.SUBSCRIPTION, self.PAYLOAD, cfg)
            _, kwargs = mock_wp.call_args
            sent_data = json.loads(kwargs.get("data") or mock_wp.call_args[1].get("data", "{}"))
            assert sent_data["title"] == "Test"

    def test_returns_false_on_generic_webpush_exception(self, flask_app):
        with flask_app.app_context():
            from app.pwa.push_utils import send_push
            from app.config import get_config
            from pywebpush import WebPushException
            cfg = get_config()
            mock_exc = WebPushException("bad")
            mock_exc.response = MagicMock(status_code=500)
            with patch("app.pwa.push_utils.webpush", side_effect=mock_exc):
                result = send_push(self.SUBSCRIPTION, self.PAYLOAD, cfg)
            assert result is False

    def test_410_gone_removes_subscription(self, flask_app):
        """A 410 from the push server means the subscription is stale; it should be deleted."""
        user = _make_user(flask_app)
        endpoint = "https://fcm.example.com/push/gone"
        _make_subscription(flask_app, user["id"], endpoint=endpoint)

        with flask_app.app_context():
            from app.pwa.push_utils import send_push
            from app.config import get_config
            from app import db
            from pywebpush import WebPushException

            cfg = get_config()
            sub = {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}
            mock_exc = WebPushException("Gone")
            mock_exc.response = MagicMock(status_code=410)
            with patch("app.pwa.push_utils.webpush", side_effect=mock_exc):
                result = send_push(sub, self.PAYLOAD, cfg)

            assert result is False
            row = db.query_one("SELECT 1 FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
            assert row is None, "Stale subscription should have been deleted"

    def test_returns_false_on_unexpected_exception(self, flask_app):
        with flask_app.app_context():
            from app.pwa.push_utils import send_push
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush", side_effect=RuntimeError("network down")):
                result = send_push(self.SUBSCRIPTION, self.PAYLOAD, cfg)
            assert result is False


# ── send_push_to_user ─────────────────────────────────────────────────────────

class TestSendPushToUser:
    PAYLOAD = {"title": "Hi", "body": "There", "url": "/"}

    def test_sends_to_all_user_subscriptions(self, flask_app):
        user = _make_user(flask_app)
        _make_subscription(flask_app, user["id"], endpoint="https://fcm.example.com/1")
        _make_subscription(flask_app, user["id"], endpoint="https://fcm.example.com/2")

        with flask_app.app_context():
            from app.pwa.push_utils import send_push_to_user
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush") as mock_wp:
                count = send_push_to_user(user["id"], self.PAYLOAD, cfg)
            assert count == 2
            assert mock_wp.call_count == 2

    def test_returns_zero_when_no_subscriptions(self, flask_app):
        user = _make_user(flask_app)
        with flask_app.app_context():
            from app.pwa.push_utils import send_push_to_user
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush"):
                count = send_push_to_user(user["id"], self.PAYLOAD, cfg)
            assert count == 0

    def test_partial_failure_counted_correctly(self, flask_app):
        user = _make_user(flask_app)
        _make_subscription(flask_app, user["id"], endpoint="https://fcm.example.com/ok")
        _make_subscription(flask_app, user["id"], endpoint="https://fcm.example.com/fail")

        from pywebpush import WebPushException
        fail_exc = WebPushException("bad")
        fail_exc.response = MagicMock(status_code=500)

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise fail_exc

        with flask_app.app_context():
            from app.pwa.push_utils import send_push_to_user
            from app.config import get_config
            cfg = get_config()
            with patch("app.pwa.push_utils.webpush", side_effect=side_effect):
                count = send_push_to_user(user["id"], self.PAYLOAD, cfg)
        assert count == 1


# ── all_scores_submitted ──────────────────────────────────────────────────────

class TestAllScoresSubmitted:
    def _setup_tournament(self, flask_app, puzzle_number=1000):
        from app import db
        admin = _make_user(flask_app, "admin@t.com", is_admin=True)
        user1 = _make_user(flask_app, "p1@t.com")
        user2 = _make_user(flask_app, "p2@t.com")
        cur = db.execute(
            "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
            ("Test Tournament", puzzle_number, 7, admin["id"]),
        )
        t_id = cur.lastrowid
        db.execute(
            "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
            (t_id, user1["id"]),
        )
        db.execute(
            "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
            (t_id, user2["id"]),
        )
        return t_id, user1, user2, puzzle_number

    def test_false_when_no_scores(self, flask_app):
        with flask_app.app_context():
            t_id, _, _, pn = self._setup_tournament(flask_app)
            from app.pwa.push_utils import all_scores_submitted
            assert all_scores_submitted(t_id, pn) is False

    def test_false_when_only_partial_scores(self, flask_app):
        with flask_app.app_context():
            from app import db
            t_id, user1, user2, pn = self._setup_tournament(flask_app)
            db.execute(
                "INSERT INTO scores (user_id, puzzle_number, guesses, share_text) VALUES (?, ?, ?, ?)",
                (user1["id"], pn, 3, ""),
            )
            from app.pwa.push_utils import all_scores_submitted
            assert all_scores_submitted(t_id, pn) is False

    def test_true_when_all_scores_in(self, flask_app):
        with flask_app.app_context():
            from app import db
            t_id, user1, user2, pn = self._setup_tournament(flask_app)
            for u in (user1, user2):
                db.execute(
                    "INSERT INTO scores (user_id, puzzle_number, guesses, share_text) VALUES (?, ?, ?, ?)",
                    (u["id"], pn, 3, ""),
                )
            from app.pwa.push_utils import all_scores_submitted
            assert all_scores_submitted(t_id, pn) is True


# ── notify_tournament_members ─────────────────────────────────────────────────

class TestNotifyTournamentMembers:
    def test_notifies_all_members_except_excluded(self, flask_app):
        with flask_app.app_context():
            from app import db
            submitter = _make_user(flask_app, "submitter@t.com")
            other = _make_user(flask_app, "other@t.com")
            cur = db.execute(
                "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
                ("Notify Test", 1000, 7, submitter["id"]),
            )
            t_id = cur.lastrowid
            for u in (submitter, other):
                db.execute(
                    "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
                    (t_id, u["id"]),
                )
            _make_subscription(flask_app, other["id"])

        called = []
        with patch("app.pwa.push_utils.webpush", side_effect=lambda **kw: called.append(kw)):
            from app.pwa.push_utils import notify_tournament_members
            from app.config import get_config
            cfg = get_config()
            notify_tournament_members(
                t_id, submitter["id"], {"title": "New score!", "body": "", "url": "/"}, cfg, flask_app
            )
            # thread is daemon — give it time
            time.sleep(0.3)

        assert len(called) == 1, f"Expected 1 push (to 'other'), got {len(called)}"


# ── /pwa/push/test endpoint ───────────────────────────────────────────────────

class TestPushTestEndpoint:
    def test_admin_can_trigger_test_push(self, flask_app):
        admin = _make_user(flask_app, "admin2@t.com", is_admin=True)
        _make_subscription(flask_app, admin["id"])
        token = _make_session(flask_app, admin["id"])

        client = flask_app.test_client()
        client.set_cookie("wt_session", token)
        with patch("app.pwa.push_utils.webpush") as mock_wp:
            resp = client.post("/pwa/push/test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sent"] == 1
        mock_wp.assert_called_once()

    def test_non_admin_gets_403(self, flask_app):
        user = _make_user(flask_app, "nobody@t.com", is_admin=False)
        token = _make_session(flask_app, user["id"])
        client = flask_app.test_client()
        client.set_cookie("wt_session", token)
        resp = client.post("/pwa/push/test")
        assert resp.status_code == 403

    def test_unauthenticated_gets_redirect(self, flask_app):
        client = flask_app.test_client()
        resp = client.post("/pwa/push/test")
        assert resp.status_code in (302, 401)
