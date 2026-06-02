"""
Auto-miss daemon: inserts MISS rows for members who missed their midnight deadline.
Runs every 60 seconds in a background daemon thread.
"""

import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _run_auto_miss(app):
    # Backfill immediately on startup, then run every 60 seconds
    try:
        with app.app_context():
            _process_auto_misses(app)
    except Exception:
        logger.exception("Error in auto-miss scheduler (startup backfill)")
    while True:
        time.sleep(60)
        try:
            with app.app_context():
                _process_auto_misses(app)
        except Exception:
            logger.exception("Error in auto-miss scheduler")


def _process_auto_misses(app):
    from app import db
    from app.config import get_config, current_puzzle_number
    from app.tournaments.scoring import is_past_deadline, tournament_state

    cfg = get_config()
    today = current_puzzle_number(cfg)

    # Get all active/recently-ended tournaments (within last day to catch stragglers)
    tournaments = db.query_all("SELECT * FROM tournaments")
    for t in tournaments:
        state = tournament_state(t, today)
        if state not in ("ACTIVE", "ENDED"):
            continue

        start = t["start_puzzle"]
        end = start + t["num_days"] - 1

        # Check each puzzle day up to yesterday (today is still open)
        for pnum in range(start, min(today, end + 1)):
            # Get all members and their scores for this puzzle
            members = db.query_all(
                """
                SELECT u.id, u.timezone
                FROM tournament_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.tournament_id = ?
                """,
                (t["id"],),
            )

            for member in members:
                uid = member["id"]
                tz = member["timezone"]

                # Skip if already has a score
                existing = db.query_one(
                    "SELECT id FROM scores WHERE user_id = ? AND puzzle_number = ?",
                    (uid, pnum),
                )
                if existing:
                    continue

                # Insert MISS if their deadline has passed
                if is_past_deadline(pnum, tz, cfg):
                    try:
                        db.execute(
                            """
                            INSERT OR IGNORE INTO scores
                                (user_id, puzzle_number, guesses, hard_mode, is_auto_miss)
                            VALUES (?, ?, 0, 1, 1)
                            """,
                            (uid, pnum),
                        )
                        logger.info("Auto-miss inserted: user=%s puzzle=%s", uid, pnum)
                    except Exception:
                        logger.exception("Failed to insert auto-miss: user=%s puzzle=%s", uid, pnum)


def start_scheduler(app) -> threading.Thread:
    t = threading.Thread(target=_run_auto_miss, args=(app,), daemon=True, name="auto-miss-scheduler")
    t.start()
    logger.info("Auto-miss scheduler started")
    return t
