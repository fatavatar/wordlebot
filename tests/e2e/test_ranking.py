"""Phase 5: Ranking edge case tests."""

import pytest

from app.tournaments.scoring import compute_standings, can_see_score
from tests.e2e.conftest import create_user


def _make_tournament(flask_app, admin_user, start_offset=0, num_days=7):
    from app import db
    from app.config import get_config, current_puzzle_number
    cfg = get_config()
    today = current_puzzle_number(cfg)
    with flask_app.app_context():
        cur = db.execute(
            "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
            ("Rank Test", today + start_offset, num_days, admin_user["id"]),
        )
        t = db.query_one("SELECT * FROM tournaments WHERE id = ?", (cur.lastrowid,))
        return dict(t)


def _standings(flask_app, t, user_ids):
    from app import db
    from app.config import get_config, current_puzzle_number
    cfg = get_config()
    today = current_puzzle_number(cfg)
    with flask_app.app_context():
        members = db.query_all(
            "SELECT u.*, tm.joined_at FROM tournament_members tm JOIN users u ON u.id = tm.user_id WHERE tm.tournament_id = ?",
            (t["id"],),
        )
        placeholders = ",".join("?" * len(user_ids))
        scores = db.query_all(
            f"SELECT * FROM scores WHERE user_id IN ({placeholders})",
            tuple(user_ids),
        )
        return compute_standings(
            [dict(m) for m in members],
            [dict(s) for s in scores],
            t,
            today,
            cfg,
        )


class TestRankingEdgeCases:
    def test_all_miss_ranked_by_guesses_sum(self, flask_app, admin_user: dict):
        from app import db
        t = _make_tournament(flask_app, admin_user, start_offset=-1, num_days=7)
        u1 = create_user(flask_app, "rank1@test.com", "R1")
        u2 = create_user(flask_app, "rank2@test.com", "R2")

        with flask_app.app_context():
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))
            pnum = t["start_puzzle"]
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 0, 1)", (u1["id"], pnum))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 0, 1)", (u2["id"], pnum))

        result = _standings(flask_app, t, [u1["id"], u2["id"]])
        # Same misses, same guesses → same rank (first by name sort doesn't matter here, just both rank 1)
        assert result[0]["total_misses"] == 1
        assert result[1]["total_misses"] == 1

    def test_rank_1_fewer_misses(self, flask_app, admin_user: dict):
        from app import db
        t = _make_tournament(flask_app, admin_user, start_offset=-2, num_days=7)
        u1 = create_user(flask_app, "ra1@test.com", "RA1")
        u2 = create_user(flask_app, "ra2@test.com", "RA2")

        with flask_app.app_context():
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))
            pnum = t["start_puzzle"]
            # u1: solve in 2
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 2, 1)", (u1["id"], pnum))
            # u2: miss
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 0, 1)", (u2["id"], pnum))

        result = _standings(flask_app, t, [u1["id"], u2["id"]])
        assert result[0]["user_id"] == u1["id"]
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2

    def test_rank_tiebreak_total_guesses(self, flask_app, admin_user: dict):
        from app import db
        t = _make_tournament(flask_app, admin_user, start_offset=-2, num_days=7)
        u1 = create_user(flask_app, "tb1@test.com", "TB1")
        u2 = create_user(flask_app, "tb2@test.com", "TB2")

        with flask_app.app_context():
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))
            pnum = t["start_puzzle"]
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 2, 1)", (u1["id"], pnum))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 6, 1)", (u2["id"], pnum))

        result = _standings(flask_app, t, [u1["id"], u2["id"]])
        assert result[0]["user_id"] == u1["id"]
        assert result[0]["total_guesses"] == 2
        assert result[1]["total_guesses"] == 6

    def test_rank_updates_after_new_submission(self, flask_app, admin_user: dict):
        from app import db
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user, start_offset=-1, num_days=7)
        u1 = create_user(flask_app, "upd1@test.com", "UPD1")
        u2 = create_user(flask_app, "upd2@test.com", "UPD2")

        with flask_app.app_context():
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u1["id"]))
            db.execute("INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)", (t["id"], u2["id"]))
            pnum = t["start_puzzle"]
            # Initially u1 misses, u2 gets 3
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 0, 1)", (u1["id"], pnum))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 3, 1)", (u2["id"], pnum))

        result = _standings(flask_app, t, [u1["id"], u2["id"]])
        # u2 should be ranked first (no miss)
        assert result[0]["user_id"] == u2["id"]

    def test_score_hidden_before_viewer_submits(self, flask_app, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user, start_offset=0, num_days=7)
        u1 = create_user(flask_app, "vh1@test.com", "VH1")
        u2 = create_user(flask_app, "vh2@test.com", "VH2")

        scores = []  # no submissions yet

        with flask_app.app_context():
            # u1 has NOT submitted; day is still open
            visible = can_see_score(
                viewer_id=u1["id"],
                target_user_id=u2["id"],
                puzzle_number=today,
                scores=scores,
                target_user=u2,
                cfg=cfg,
            )
            assert visible is False

    def test_score_visible_after_viewer_submits(self, flask_app, admin_user: dict):
        from app import db
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        t = _make_tournament(flask_app, admin_user, start_offset=0, num_days=7)
        u1 = create_user(flask_app, "vv1@test.com", "VV1")
        u2 = create_user(flask_app, "vv2@test.com", "VV2")

        with flask_app.app_context():
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 3, 1)", (u1["id"], today))
            db.execute("INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 4, 1)", (u2["id"], today))
            scores = db.query_all("SELECT * FROM scores WHERE puzzle_number = ?", (today,))
            scores = [dict(s) for s in scores]
            visible = can_see_score(
                viewer_id=u1["id"],
                target_user_id=u2["id"],
                puzzle_number=today,
                scores=scores,
                target_user=dict(u2),
                cfg=cfg,
            )
            assert visible is True

    def test_rank_includes_late_joiner_misses(self, flask_app, admin_user: dict):
        from app import db
        from app.config import get_config, current_puzzle_number
        from flask import g
        cfg = get_config()
        today = current_puzzle_number(cfg)
        # Tournament started 5 days ago
        t = _make_tournament(flask_app, admin_user, start_offset=-5, num_days=10)
        u1 = create_user(flask_app, "lj1@test.com", "LJ1")
        u2 = create_user(flask_app, "lj2@test.com", "LJ2")

        with flask_app.app_context():
            # u1 joined at start (no misses penalty)
            db.execute(
                "INSERT INTO tournament_members (tournament_id, user_id, joined_at) VALUES (?, ?, datetime('now', '-5 days'))",
                (t["id"], u1["id"]),
            )
            # u2 joined today (late, should have auto-misses for past 5 days)
            db.execute(
                "INSERT INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
                (t["id"], u2["id"]),
            )
            # Insert u1's score for recent days (1 guess each)
            pnum = t["start_puzzle"]
            for i in range(5):
                db.execute(
                    "INSERT OR IGNORE INTO scores (user_id, puzzle_number, guesses, hard_mode) VALUES (?, ?, 1, 1)",
                    (u1["id"], pnum + i),
                )

        result = _standings(flask_app, t, [u1["id"], u2["id"]])
        # u2 is late joiner → more misses → ranked last
        u1_rank = next(r for r in result if r["user_id"] == u1["id"])
        u2_rank = next(r for r in result if r["user_id"] == u2["id"])
        assert u1_rank["rank"] < u2_rank["rank"]
        assert u2_rank["total_misses"] >= 5

    def test_viewer_always_sees_own_score(self, flask_app, admin_user: dict):
        from app.config import get_config, current_puzzle_number
        cfg = get_config()
        today = current_puzzle_number(cfg)
        u1 = create_user(flask_app, "own1@test.com", "OWN1")

        visible = can_see_score(
            viewer_id=u1["id"],
            target_user_id=u1["id"],
            puzzle_number=today,
            scores=[],
            target_user=u1,
            cfg=cfg,
        )
        assert visible is True
