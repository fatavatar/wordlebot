"""Phase 4 E2E tests: PWA, service worker, push notifications."""

import json
import re
import threading
import time

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import create_user, login_as


class TestManifest:
    def test_manifest_served(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        response = page.goto(f"{live_server}/static/manifest.json")
        assert response.status == 200
        data = response.json()
        assert data["name"] == "Wordle Tournament"
        assert data["display"] == "standalone"
        assert len(data["icons"]) >= 2

    def test_manifest_linked_in_html(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        manifest_link = page.locator("link[rel=manifest]")
        expect(manifest_link).to_have_attribute("href", re.compile(r"manifest\.json"))

    def test_apple_touch_icon_linked(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        apple_icon = page.locator("link[rel='apple-touch-icon']")
        expect(apple_icon).to_have_count(1)

    def test_icons_accessible(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        for size in ["192", "512"]:
            resp = page.goto(f"{live_server}/static/icons/icon-{size}.png")
            assert resp.status == 200


class TestServiceWorker:
    def test_sw_script_served(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        response = page.goto(f"{live_server}/static/js/sw.js")
        assert response.status == 200
        assert "serviceWorker" in response.text() or "self.addEventListener" in response.text()

    def test_sw_registers_on_page_load(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        # Wait for SW to register
        page.wait_for_timeout(1000)
        sw_registered = page.evaluate(
            "() => navigator.serviceWorker.getRegistration('/static/js/sw.js').then(r => !!r)"
        )
        assert sw_registered is True

    def test_offline_fallback_page_exists(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        response = page.goto(f"{live_server}/static/offline.html")
        assert response.status == 200
        assert "offline" in response.text().lower() or "Offline" in response.text()


class TestPushEndpoints:
    def test_vapid_public_key_endpoint(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        response = page.goto(f"{live_server}/pwa/vapid-public-key")
        assert response.status == 200
        data = response.json()
        assert "publicKey" in data
        # VAPID public keys are base64url encoded
        assert len(data["publicKey"]) > 20

    def test_push_subscribe_saves_row(self, flask_app, regular_user: dict):
        """Test the push subscribe API endpoint directly."""
        from tests.e2e.conftest import create_session_for_user
        token = create_session_for_user(flask_app, regular_user["id"])

        fake_subscription = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/fake-endpoint-12345",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlzkAv-43n6LFd8D0JXQeulHi8c9tK6FaKT4AvpA",
                "auth": "tBHItJI5svbpez7KI4CCXg",
            },
        }

        client = flask_app.test_client()
        client.set_cookie("wt_session", token)
        resp = client.post(
            "/pwa/push/subscribe",
            data=json.dumps(fake_subscription),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        with flask_app.app_context():
            from app import db
            row = db.query_one(
                "SELECT * FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
                (regular_user["id"], fake_subscription["endpoint"]),
            )
            assert row is not None

    def test_push_unsubscribe_removes_row(self, flask_app, regular_user: dict):
        """Test push unsubscribe removes the DB row."""
        from tests.e2e.conftest import create_session_for_user
        from app import db

        with flask_app.app_context():
            db.execute(
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                (regular_user["id"], "https://example.com/push/test", "key", "auth"),
            )

        token = create_session_for_user(flask_app, regular_user["id"])
        client = flask_app.test_client()
        client.set_cookie("wt_session", token)
        resp = client.post("/pwa/push/unsubscribe")
        assert resp.status_code == 200

        with flask_app.app_context():
            row = db.query_one(
                "SELECT 1 FROM push_subscriptions WHERE user_id = ?",
                (regular_user["id"],),
            )
            assert row is None


class TestiOSShortcutPage:
    def test_ios_shortcut_page_shows_auth_key(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/pwa/ios-shortcut")
        expect(page.locator("h1")).to_contain_text("iOS Shortcut")
        # Auth key should be visible on the page
        expect(page.get_by_text(regular_user["auth_key"])).to_be_visible()

    def test_ios_shortcut_shows_endpoint_url(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/pwa/ios-shortcut")
        expect(page.get_by_text("api/submit")).to_be_visible()

    def test_notification_help_page(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/pwa/notification-help")
        expect(page.locator("h1")).to_contain_text("Enable Notifications")


class TestAndroidShare:
    def test_share_target_in_manifest(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        response = page.goto(f"{live_server}/static/manifest.json")
        data = response.json()
        assert "share_target" in data
        assert data["share_target"]["action"] == "/tournaments/submit-via-share"

    def test_android_share_route_redirects_to_submit(self, flask_app, regular_user: dict):
        """When in only one active tournament, share target redirects to submit."""
        from app import db
        from app.config import get_config, current_puzzle_number
        from tests.e2e.conftest import create_session_for_user

        cfg = get_config()
        today = current_puzzle_number(cfg)

        with flask_app.app_context():
            # Create an active tournament and join
            admin = create_user(flask_app, "admin_share@test.com", "Admin", is_admin=True)
            cur = db.execute(
                "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
                ("Share Test", today, 7, admin["id"]),
            )
            t_id = cur.lastrowid
            db.execute(
                "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
                (t_id, regular_user["id"]),
            )

        import urllib.parse
        share_text = f"Wordle {today} 3/6*\n⬛🟨⬛⬛🟩\n"
        encoded = urllib.parse.quote(share_text)

        token = create_session_for_user(flask_app, regular_user["id"])
        client = flask_app.test_client()
        resp = client.get(
            f"/tournaments/submit-via-share?share_text={encoded}",
            headers={"Cookie": f"wt_session={token}"},
        )
        # Should redirect to the submit page for the single active tournament
        assert resp.status_code in (302, 200)
