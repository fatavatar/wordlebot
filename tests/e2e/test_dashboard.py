"""Phase 3 E2E tests: Dashboard, tournament detail, profile."""

import re
import uuid
from datetime import datetime, timezone

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import create_user, login_as


def _make_tournament(flask_app, admin_user, name="Test", start_offset=0, num_days=7):
    from app import db
    from app.config import get_config, current_puzzle_number
    cfg = get_config()
    today = current_puzzle_number(cfg)
    with flask_app.app_context():
        cur = db.execute(
            "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
            (name, today + start_offset, num_days, admin_user["id"]),
        )
        t = db.query_one("SELECT * FROM tournaments WHERE id = ?", (cur.lastrowid,))
        return dict(t)


def _join(flask_app, tournament_id, user_id):
    from app import db
    with flask_app.app_context():
        db.execute(
            "INSERT OR IGNORE INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
            (tournament_id, user_id),
        )


def _submit_score(flask_app, user_id, puzzle_number, guesses=3):
    from app import db
    with flask_app.app_context():
        db.execute(
            "INSERT OR IGNORE INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, ?, 1)",
            (user_id, puzzle_number, guesses),
        )


class TestDashboard:
    def test_dashboard_shows_my_active(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user, name="Active One")
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        expect(page.locator("text=Active One")).to_be_visible()

    def test_dashboard_shows_open_tournaments(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        _make_tournament(flask_app, admin_user, name="Open Tournament")
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        expect(page.locator("strong:has-text('Open Tournament')")).to_be_visible()
        expect(page.locator("button:has-text('Join')")).to_be_visible()

    def test_dashboard_shows_ended_tournament(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user, name="Old Tournament", start_offset=-10, num_days=3)
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        expect(page.locator("text=Old Tournament")).to_be_visible()

    def test_join_from_dashboard(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        _make_tournament(flask_app, admin_user, name="Join Me")
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        page.click("button:has-text('Join')")

        with flask_app.app_context():
            from app import db
            member = db.query_one(
                "SELECT 1 FROM tournament_members WHERE user_id = ?", (regular_user["id"],)
            )
            assert member is not None

    def test_admin_sees_new_tournament_button(self, page: Page, live_server: str, flask_app, admin_user: dict):
        login_as(page, flask_app, live_server, admin_user)
        page.goto(f"{live_server}/")
        expect(page.locator("text=New Tournament")).to_be_visible()

    def test_non_admin_no_new_tournament_button(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/")
        expect(page.locator("text=New Tournament")).not_to_be_visible()


class TestTournamentDetail:
    def test_detail_shows_leaderboard(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user, name="Leaderboard Test")
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")
        expect(page.locator(".leaderboard")).to_be_visible()
        # Check for the column header specifically (not the user name which also contains "Player")
        expect(page.locator(".leaderboard")).to_be_visible()
        expect(page.locator(".leaderboard th:has-text('Misses')")).to_be_visible()

    def test_detail_shows_join_button_for_non_member(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user)
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")
        expect(page.locator("button:has-text('Join Tournament')")).to_be_visible()

    def test_detail_shows_submit_button_for_member(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user)
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")
        expect(page.locator("a:has-text('Submit Score')")).to_be_visible()

    def test_score_hidden_before_own_submission(
        self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict
    ):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user, start_offset=0, num_days=7)

        other = create_user(flask_app, "other@test.com", "Other Player")
        _join(flask_app, t["id"], regular_user["id"])
        _join(flask_app, t["id"], other["id"])
        _submit_score(flask_app, other["id"], t["start_puzzle"])

        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")

        # Other's score should be hidden (viewer has not submitted)
        hidden_cells = page.locator(".day-grid-cell.hidden")
        assert hidden_cells.count() >= 1

    def test_score_visible_after_own_submission(
        self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict
    ):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user, start_offset=0, num_days=7)

        other = create_user(flask_app, "other2@test.com", "Other Player 2")
        _join(flask_app, t["id"], regular_user["id"])
        _join(flask_app, t["id"], other["id"])

        # Both submit
        _submit_score(flask_app, other["id"], t["start_puzzle"], guesses=3)
        _submit_score(flask_app, regular_user["id"], t["start_puzzle"], guesses=4)

        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")

        # No hidden cells — both submitted
        hidden_cells = page.locator(".day-grid-cell.hidden")
        assert hidden_cells.count() == 0


class TestSubmitForm:
    def _fill_and_trigger(self, page: Page, selector: str, value: str):
        """Fill a textarea and explicitly dispatch input event to trigger JS listeners."""
        page.fill(selector, value)
        page.eval_on_selector(selector, "el => el.dispatchEvent(new Event('input'))")

    def test_live_preview_shows_on_valid_input(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user)
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}/submit")

        share_text = f"Wordle {today} 3/6*\n⬛🟨⬛⬛🟩\n🟩🟩⬛🟩🟩\n🟩🟩🟩🟩🟩\n"
        self._fill_and_trigger(page, "textarea[name=share_text]", share_text)

        expect(page.locator("#preview")).to_be_visible()
        expect(page.locator("#preview-content")).to_contain_text("3 guess")

    def test_submit_disabled_without_asterisk(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _make_tournament(flask_app, admin_user)
        _join(flask_app, t["id"], regular_user["id"])
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}/submit")

        self._fill_and_trigger(page, "textarea[name=share_text]", "Wordle 1234 4/6\n⬛⬛⬛⬛⬛\n")
        expect(page.locator("#preview-error")).to_contain_text("Hard Mode")
        expect(page.locator("#submit-btn")).to_be_disabled()


class TestProfile:
    def test_profile_shows_user_info(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/profile")
        expect(page.locator("input[name=name]")).to_have_value(regular_user["name"])
        expect(page.locator("input[value='" + regular_user["email"] + "']")).to_be_visible()

    def test_profile_update_saves(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/profile")
        page.fill("input[name=name]", "Updated Name")
        page.select_option("select[name=timezone]", "Europe/London")
        page.click("button[type=submit]")

        with flask_app.app_context():
            from app import db
            user = db.query_one("SELECT * FROM users WHERE id = ?", (regular_user["id"],))
            assert user["name"] == "Updated Name"
            assert user["timezone"] == "Europe/London"

    def test_profile_shows_auth_key(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/profile")
        expect(page.locator("#auth-key")).to_have_value(regular_user["auth_key"])

    def test_colorblind_toggle_updates_db(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/profile")
        page.check("input[name=colorblind]")
        page.click("button[type=submit]")

        with flask_app.app_context():
            from app import db
            user = db.query_one("SELECT colorblind FROM users WHERE id = ?", (regular_user["id"],))
            assert user["colorblind"] == 1
