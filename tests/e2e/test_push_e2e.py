"""
Push notification delivery tests — no FCM, no real browser required.

Strategy: spin up a local HTTP server that acts as a fake push endpoint.
We give pywebpush a subscription whose endpoint points there, trigger a
push from the Flask server, and assert the encrypted push arrived with
correct VAPID Authorization and Content-Encoding headers.

This tests the complete server-side path end-to-end:
  payload → VAPID signing → encryption → HTTP delivery → receipt

The only thing NOT tested is FCM forwarding to the device, which is an
infra concern and not testable in a headless environment.
"""

import http.server
import json
import os
import threading
import time
from base64 import urlsafe_b64encode

import pytest
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tests.e2e.conftest import create_user, create_session_for_user


# ── Fake push endpoint ────────────────────────────────────────────────────────

class FakePushServer:
    """
    Minimal Web Push endpoint. Accepts POST, returns 201, records requests.
    Lets us verify pywebpush actually sent a push with VAPID headers.
    """

    def __init__(self):
        self.received: list[dict] = []
        self._server: http.server.HTTPServer | None = None
        self.port: int = 0

    def start(self):
        store = self.received

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                store.append({"headers": dict(self.headers), "body": body, "path": self.path})
                self.send_response(201)
                self.end_headers()

            def log_message(self, *_):
                pass

        self._server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._server.server_port
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        if self._server:
            self._server.shutdown()

    def wait_for_request(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.received:
                return True
            time.sleep(0.05)
        return False


def _fake_subscription(endpoint: str) -> dict:
    """Build a subscription dict with a real ECDH key pair pointing at endpoint."""
    private_key = generate_private_key(SECP256R1())
    public_key = private_key.public_key()
    p256dh = (
        urlsafe_b64encode(
            public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        )
        .rstrip(b"=")
        .decode()
    )
    auth = urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


# ── Module-level setup ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flask_app(tmp_path_factory):
    import app.config as cfg_module
    from dotenv import load_dotenv
    load_dotenv()
    os.environ.setdefault("SECRET_KEY", "push-e2e-secret")
    os.environ.setdefault("SMTP_HOST", "localhost")
    os.environ.setdefault("SMTP_PORT", "1025")
    os.environ.setdefault("SMTP_USERNAME", "test")
    os.environ.setdefault("SMTP_PASSWORD", "test")
    os.environ.setdefault("EMAIL_SENDER", "test@example.com")
    cfg_module._config = None

    db_path = str(tmp_path_factory.mktemp("push_e2e_db") / "push.db")
    from app import create_app
    return create_app({"DATABASE": db_path, "TESTING": True})


@pytest.fixture(autouse=True)
def clean_db(flask_app):
    with flask_app.app_context():
        from app import db
        for t in ("push_subscriptions", "scores", "tournament_members", "tournaments", "sessions", "users"):
            db.execute(f"DELETE FROM {t}")
    yield


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestVapidConfig:
    def test_vapid_keys_are_not_placeholders(self, flask_app):
        with flask_app.app_context():
            from app.config import get_config
            cfg = get_config()
            assert len(cfg.VAPID_PUBLIC_KEY) > 20, "VAPID_PUBLIC_KEY is a placeholder"
            assert len(cfg.VAPID_PRIVATE_KEY) > 20, "VAPID_PRIVATE_KEY is a placeholder"
            assert "@" in cfg.VAPID_CLAIMS_EMAIL, "VAPID_CLAIMS_EMAIL looks wrong"

    def test_vapid_public_key_is_base64url(self, flask_app):
        with flask_app.app_context():
            from app.config import get_config
            import base64
            cfg = get_config()
            key = cfg.VAPID_PUBLIC_KEY
            padded = key + "=" * ((4 - len(key) % 4) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            assert len(decoded) == 65, (
                f"VAPID public key decoded to {len(decoded)} bytes; expected 65 "
                "(uncompressed EC point: 0x04 + 32 bytes X + 32 bytes Y)"
            )


class TestPushSendingWithFakeEndpoint:
    """
    Tests that pywebpush actually sends a push with correct protocol headers.
    Does NOT use FCM or a real browser.
    """

    def test_push_arrives_at_endpoint(self, flask_app):
        """send_push delivers an encrypted Web Push POST to the subscription endpoint."""
        server = FakePushServer()
        server.start()
        try:
            sub = _fake_subscription(f"http://127.0.0.1:{server.port}/push")

            with flask_app.app_context():
                from app.pwa.push_utils import send_push
                from app.config import get_config
                cfg = get_config()
                result = send_push(sub, {"title": "Hello", "body": "World", "url": "/"}, cfg)

            assert result is True, "send_push returned False — check VAPID keys or pywebpush config"
            received = server.wait_for_request(timeout=5)
            assert received, "No POST reached the fake push endpoint within 5s"
        finally:
            server.stop()

    def test_push_has_vapid_authorization_header(self, flask_app):
        """The push request must carry a VAPID JWT in the Authorization header."""
        server = FakePushServer()
        server.start()
        try:
            sub = _fake_subscription(f"http://127.0.0.1:{server.port}/push")
            with flask_app.app_context():
                from app.pwa.push_utils import send_push
                from app.config import get_config
                send_push(sub, {"title": "Auth test", "body": "", "url": "/"}, get_config())

            server.wait_for_request(timeout=5)
            assert server.received, "No push received"
            auth = server.received[0]["headers"].get("Authorization") or server.received[0]["headers"].get("authorization", "")
            assert auth.startswith("vapid") or auth.startswith("WebPush"), (
                f"Expected VAPID Authorization header, got: {auth!r}"
            )
        finally:
            server.stop()

    def test_push_has_encrypted_content_encoding(self, flask_app):
        """Web Push payload must use aes128gcm (RFC 8291) content encoding."""
        server = FakePushServer()
        server.start()
        try:
            sub = _fake_subscription(f"http://127.0.0.1:{server.port}/push")
            with flask_app.app_context():
                from app.pwa.push_utils import send_push
                from app.config import get_config
                send_push(sub, {"title": "Encoding test", "body": "", "url": "/"}, get_config())

            server.wait_for_request(timeout=5)
            assert server.received, "No push received"
            encoding = (
                server.received[0]["headers"].get("Content-Encoding")
                or server.received[0]["headers"].get("content-encoding", "")
            )
            assert "aes128gcm" in encoding, (
                f"Expected aes128gcm content encoding, got: {encoding!r}"
            )
        finally:
            server.stop()

    def test_push_body_is_non_empty(self, flask_app):
        """The push request must have an encrypted body (empty body = no payload)."""
        server = FakePushServer()
        server.start()
        try:
            sub = _fake_subscription(f"http://127.0.0.1:{server.port}/push")
            with flask_app.app_context():
                from app.pwa.push_utils import send_push
                from app.config import get_config
                send_push(sub, {"title": "Body test", "body": "check me", "url": "/"}, get_config())

            server.wait_for_request(timeout=5)
            assert server.received, "No push received"
            assert len(server.received[0]["body"]) > 0, "Push body is empty — payload was not encrypted"
        finally:
            server.stop()

    def test_send_push_to_user_delivers_to_all_subscriptions(self, flask_app):
        """send_push_to_user delivers to every subscription a user has."""
        servers = [FakePushServer(), FakePushServer()]
        for s in servers:
            s.start()
        try:
            user = create_user(flask_app, "pushuser@test.com")
            with flask_app.app_context():
                from app import db
                for s in servers:
                    sub = _fake_subscription(f"http://127.0.0.1:{s.port}/push")
                    db.execute(
                        "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                        (user["id"], sub["endpoint"], sub["keys"]["p256dh"], sub["keys"]["auth"]),
                    )
                from app.pwa.push_utils import send_push_to_user
                from app.config import get_config
                count = send_push_to_user(user["id"], {"title": "Multi", "body": "", "url": "/"}, get_config())

            assert count == 2
            for s in servers:
                assert s.wait_for_request(timeout=5), f"Endpoint on port {s.port} received no push"
        finally:
            for s in servers:
                s.stop()

    def test_push_test_endpoint_delivers_push(self, flask_app):
        """The /pwa/push/test admin endpoint triggers a real push delivery."""
        server = FakePushServer()
        server.start()
        try:
            admin = create_user(flask_app, "admin_push@test.com", is_admin=True)
            sub = _fake_subscription(f"http://127.0.0.1:{server.port}/push")
            with flask_app.app_context():
                from app import db
                db.execute(
                    "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                    (admin["id"], sub["endpoint"], sub["keys"]["p256dh"], sub["keys"]["auth"]),
                )

            token = create_session_for_user(flask_app, admin["id"])
            client = flask_app.test_client()
            client.set_cookie("wt_session", token)
            resp = client.post("/pwa/push/test")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["sent"] == 1

            received = server.wait_for_request(timeout=5)
            assert received, (
                "The /pwa/push/test endpoint returned sent=1 but the push never arrived. "
                "This likely means pywebpush raised an exception that was silently caught."
            )
        finally:
            server.stop()
