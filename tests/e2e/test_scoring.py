"""Phase 2 tests: Wordle parser and score submission."""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from app.tournaments.scoring import ParseError, parse_wordle_share, compute_standings
from tests.e2e.conftest import create_user, create_session_for_user, login_as
from tests.e2e.fixtures.wordle_shares import (
    VALID_4_GUESSES,
    VALID_1_GUESS,
    VALID_MISS,
    VALID_TODAY,
    VALID_HASH_PREFIX,
    NO_ASTERISK,
    MALFORMED_HEADER,
    VALID_6_GUESSES,
)


# ── Parser unit tests (no browser) ───────────────────────────────────────────

class TestWordleParser:
    def test_parse_standard_4_guesses(self):
        result = parse_wordle_share(VALID_4_GUESSES, today_puzzle=1234)
        assert result.puzzle_number == 1234
        assert result.guesses == 4
        assert result.hard_mode is True

    def test_parse_1_guess(self):
        result = parse_wordle_share(VALID_1_GUESS, today_puzzle=1234)
        assert result.guesses == 1

    def test_parse_miss(self):
        result = parse_wordle_share(VALID_MISS, today_puzzle=1234)
        assert result.puzzle_number == 1234
        assert result.guesses == 0
        assert result.hard_mode is True

    def test_parse_today_keyword(self):
        result = parse_wordle_share(VALID_TODAY, today_puzzle=999)
        assert result.puzzle_number == 999
        assert result.guesses == 3

    def test_parse_hash_prefix(self):
        result = parse_wordle_share(VALID_HASH_PREFIX, today_puzzle=1234)
        assert result.puzzle_number == 1234

    def test_parse_6_guesses(self):
        result = parse_wordle_share(VALID_6_GUESSES, today_puzzle=1234)
        assert result.guesses == 6

    def test_parse_no_asterisk_rejected(self):
        with pytest.raises(ParseError, match="Hard Mode"):
            parse_wordle_share(NO_ASTERISK, today_puzzle=1234)

    def test_parse_malformed_rejected(self):
        with pytest.raises(ParseError):
            parse_wordle_share(MALFORMED_HEADER, today_puzzle=1234)

    def test_parse_empty_rejected(self):
        with pytest.raises(ParseError):
            parse_wordle_share("", today_puzzle=1234)


# ── Tournament E2E tests ──────────────────────────────────────────────────────

def _create_tournament(flask_app, admin_user, start_offset=0, num_days=7, name="Test Tournament"):
    from app.config import get_config, current_puzzle_number
    from app import db
    cfg = get_config()
    today = current_puzzle_number(cfg)
    start = today + start_offset
    with flask_app.app_context():
        cur = db.execute(
            "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
            (name, start, num_days, admin_user["id"]),
        )
        t = db.query_one("SELECT * FROM tournaments WHERE id = ?", (cur.lastrowid,))
        return dict(t)


class TestTournamentCRUD:
    def test_create_tournament_requires_admin(self, page: Page, live_server: str, flask_app, regular_user: dict):
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/new")
        # Should get 403
        assert page.url.endswith("/tournaments/new") is False or "403" in page.content() or page.status == 403

    def test_create_tournament_as_admin(self, page: Page, live_server: str, flask_app, admin_user: dict):
        login_as(page, flask_app, live_server, admin_user)
        page.goto(f"{live_server}/tournaments/new")
        expect(page.locator("h1")).to_contain_text("Create Tournament")

        page.fill("input[name=name]", "My Test Tournament")
        page.fill("input[name=num_days]", "7")
        page.click("button[type=submit]")

        # Should redirect to tournament detail
        expect(page).to_have_url(re.compile(r"/tournaments/\d+"))
        expect(page.locator("h1")).to_contain_text("My Test Tournament")

    def test_create_tournament_validates_fields(self, page: Page, live_server: str, flask_app, admin_user: dict):
        login_as(page, flask_app, live_server, admin_user)
        page.goto(f"{live_server}/tournaments/new")
        # Clear name and submit
        page.fill("input[name=name]", "")
        page.fill("input[name=num_days]", "7")
        page.click("button[type=submit]")
        # Should show error or stay on page (HTML5 required attr)
        expect(page).to_have_url(re.compile(r"/tournaments/new"))

    def test_join_active_tournament(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _create_tournament(flask_app, admin_user, start_offset=0)  # active today
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")
        page.click("button:has-text('Join Tournament')")

        with flask_app.app_context():
            from app import db
            member = db.query_one(
                "SELECT 1 FROM tournament_members WHERE tournament_id = ? AND user_id = ?",
                (t["id"], regular_user["id"]),
            )
            assert member is not None

    def test_join_upcoming_tournament(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = _create_tournament(flask_app, admin_user, start_offset=1)  # starts tomorrow
        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}")
        expect(page.locator("button:has-text('Join Tournament')")).to_be_visible()

    def test_late_joiner_gets_prior_misses(self, flask_app, admin_user: dict, regular_user: dict):
        """A user joining mid-tournament should get MISS for past days."""
        from app import db
        from app.config import get_config, current_puzzle_number
        from app.tournaments.routes import _apply_late_join_misses

        cfg = get_config()
        today = current_puzzle_number(cfg)
        # Tournament started 3 days ago
        t = _create_tournament(flask_app, admin_user, start_offset=-3, num_days=7)

        with flask_app.app_context():
            # Simulate joining
            db.execute(
                "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
                (t["id"], regular_user["id"]),
            )

            # Manually set g.user for _apply_late_join_misses
            from flask import g
            with flask_app.test_request_context():
                g.user = regular_user
                _apply_late_join_misses(t["id"], regular_user["id"], t)

            # Should have misses for days before today
            misses = db.query_all(
                "SELECT * FROM scores WHERE user_id = ? AND guesses = 0",
                (regular_user["id"],),
            )
            assert len(misses) >= 1  # At least some auto-misses


class TestScoreSubmission:
    def _setup_active_tournament_with_member(self, flask_app, admin_user, regular_user):
        from app import db
        t = _create_tournament(flask_app, admin_user, start_offset=0, num_days=7)
        with flask_app.app_context():
            db.execute(
                "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
                (t["id"], regular_user["id"]),
            )
        return t

    def test_submit_score_web_form(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)

        t = self._setup_active_tournament_with_member(flask_app, admin_user, regular_user)
        login_as(page, flask_app, live_server, regular_user)

        # Build share text with today's puzzle number
        share_text = f"Wordle {today} 4/6*\n⬛🟨⬛⬛🟩\n🟨⬛⬛🟩🟩\n⬛🟩⬛🟩🟩\n🟩🟩🟩🟩🟩\n"
        page.goto(f"{live_server}/tournaments/{t['id']}/submit")
        page.fill("textarea[name=share_text]", share_text)
        page.click("button[type=submit]")

        # Should redirect to tournament detail
        expect(page).to_have_url(re.compile(r"/tournaments/\d+$"))

        with flask_app.app_context():
            from app import db
            score = db.query_one(
                "SELECT * FROM scores WHERE user_id = ? AND puzzle_number = ?",
                (regular_user["id"], today),
            )
            assert score is not None
            assert score["guesses"] == 4

    def test_submit_duplicate_rejected(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)

        t = self._setup_active_tournament_with_member(flask_app, admin_user, regular_user)
        share_text = f"Wordle {today} 3/6*\n⬛🟨⬛⬛🟩\n🟩🟩⬛🟩🟩\n🟩🟩🟩🟩🟩\n"

        # Insert first score directly
        with flask_app.app_context():
            from app import db
            db.execute(
                "INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode, share_text) VALUES (?, ?, 3, 1, ?)",
                (regular_user["id"], today, share_text),
            )

        login_as(page, flask_app, live_server, regular_user)
        page.goto(f"{live_server}/tournaments/{t['id']}/submit")
        page.fill("textarea[name=share_text]", share_text)
        page.click("button[type=submit]")

        expect(page.locator(".alert-error")).to_contain_text("already submitted")

    def test_submit_wrong_puzzle_range_rejected(self, page: Page, live_server: str, flask_app, regular_user: dict, admin_user: dict):
        t = self._setup_active_tournament_with_member(flask_app, admin_user, regular_user)
        login_as(page, flask_app, live_server, regular_user)

        # Use a puzzle number well outside the range
        out_of_range = t["start_puzzle"] + t["num_days"] + 999
        share_text = f"Wordle {out_of_range} 3/6*\n⬛🟨⬛⬛🟩\n🟩🟩⬛🟩🟩\n🟩🟩🟩🟩🟩\n"
        page.goto(f"{live_server}/tournaments/{t['id']}/submit")
        page.fill("textarea[name=share_text]", share_text)
        page.click("button[type=submit]")

        expect(page.locator(".alert-error")).to_contain_text("not part of this tournament")

    def test_api_submit_with_auth_key(self, flask_app, regular_user: dict, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)

        t = self._setup_active_tournament_with_member(flask_app, admin_user, regular_user)
        share_text = f"Wordle {today} 2/6*\n🟩🟩🟩🟩🟩\n🟩🟩🟩🟩🟩\n"

        client = flask_app.test_client()
        resp = client.post(
            "/api/submit",
            json={
                "auth_key": regular_user["auth_key"],
                "score": share_text,
                "comment": "Got it!",
            },
        )
        data = resp.get_json()
        assert resp.status_code == 200, data
        assert data["status"] == "ok"
        assert data["puzzle"] == today
        assert data["guesses"] == 2

    def test_api_invalid_auth_key_rejected(self, flask_app):
        client = flask_app.test_client()
        resp = client.post(
            "/api/submit",
            json={"auth_key": "invalid-key", "score": VALID_4_GUESSES},
        )
        assert resp.status_code == 401

    def test_api_no_asterisk_rejected(self, flask_app, regular_user: dict):
        client = flask_app.test_client()
        resp = client.post(
            "/api/submit",
            json={"auth_key": regular_user["auth_key"], "score": NO_ASTERISK},
        )
        assert resp.status_code == 422
        assert "Hard Mode" in resp.get_json()["error"]


class TestRanking:
    def test_fewer_misses_wins(self, flask_app, admin_user: dict):
        from app import db
        from app.config import get_config, current_puzzle_number
        from app.tournaments.scoring import compute_standings

        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _create_tournament(flask_app, admin_user, start_offset=-2, num_days=7)

        u1 = create_user(flask_app, "player1@test.com", "Player One")
        u2 = create_user(flask_app, "player2@test.com", "Player Two")

        with flask_app.app_context():
            # Both joined at start
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))

            # u1: 0 misses, 6 total guesses
            # u2: 1 miss, 2 guesses
            pnum = t["start_puzzle"]
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 3, 1)", (u1["id"], pnum))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 3, 1)", (u1["id"], pnum + 1))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 0, 1)", (u2["id"], pnum))  # miss
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 2, 1)", (u2["id"], pnum + 1))

            members = db.query_all(
                "SELECT u.*, tm.joined_at FROM tournament_members tm JOIN users u ON u.id = tm.user_id WHERE tm.tournament_id = ?",
                (t["id"],),
            )
            scores = db.query_all(
                "SELECT * FROM scores WHERE user_id IN (?, ?)", (u1["id"], u2["id"])
            )
            standings = compute_standings(
                [dict(m) for m in members], [dict(s) for s in scores], t, today, cfg
            )

        assert standings[0]["user_id"] == u1["id"], "Player with no misses should rank first"
        assert standings[1]["user_id"] == u2["id"]

    def test_tiebreak_fewer_guesses(self, flask_app, admin_user: dict):
        from app import db
        from app.config import get_config, current_puzzle_number
        from app.tournaments.scoring import compute_standings

        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _create_tournament(flask_app, admin_user, start_offset=-1, num_days=7)

        u1 = create_user(flask_app, "tie1@test.com", "Tie One")
        u2 = create_user(flask_app, "tie2@test.com", "Tie Two")

        with flask_app.app_context():
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))

            pnum = t["start_puzzle"]
            # Same misses (0), but u1 has fewer guesses
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 2, 1)", (u1["id"], pnum))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 5, 1)", (u2["id"], pnum))

            members = db.query_all(
                "SELECT u.*, tm.joined_at FROM tournament_members tm JOIN users u ON u.id = tm.user_id WHERE tm.tournament_id = ?",
                (t["id"],),
            )
            scores = db.query_all("SELECT * FROM scores WHERE user_id IN (?, ?)", (u1["id"], u2["id"]))
            standings = compute_standings(
                [dict(m) for m in members], [dict(s) for s in scores], t, today, cfg
            )

        assert standings[0]["user_id"] == u1["id"], "Fewer guesses should win on tiebreak"
