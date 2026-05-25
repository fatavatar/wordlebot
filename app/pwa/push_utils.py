"""VAPID push notification utilities."""

import json
import logging
import threading

from pywebpush import webpush, WebPushException

from app import db
from app.config import Config

logger = logging.getLogger(__name__)


def send_push(subscription_info: dict, payload: dict, cfg: Config) -> bool:
    """
    Send a push notification to a single subscription.
    Returns True on success, False on failure.
    Deletes the subscription row if the endpoint returns 410 Gone.
    """
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=cfg.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{cfg.VAPID_CLAIMS_EMAIL}"},
        )
        return True
    except WebPushException as e:
        if e.response is not None and e.response.status_code == 410:
            # Subscription is gone — remove it
            logger.info("Removing stale push subscription: %s", subscription_info.get("endpoint", ""))
            db.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ?",
                (subscription_info.get("endpoint", ""),),
            )
        else:
            logger.warning("Push failed: %s", e)
        return False
    except Exception as e:
        logger.warning("Push error: %s", e)
        return False


def _row_to_subscription(row) -> dict:
    return {
        "endpoint": row["endpoint"],
        "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
    }


def send_push_to_user(user_id: int, payload: dict, cfg: Config) -> int:
    """Send push to all subscriptions for a user. Returns count sent."""
    subs = db.query_all("SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,))
    sent = 0
    for sub in subs:
        if send_push(_row_to_subscription(sub), payload, cfg):
            sent += 1
    return sent


def notify_tournament_members(
    tournament_id: int,
    exclude_user_id: int,
    payload: dict,
    cfg: Config,
    app,
) -> None:
    """Notify all tournament members except the excluded user (fire-and-forget thread)."""
    def _send():
        with app.app_context():
            members = db.query_all(
                "SELECT user_id FROM tournament_members WHERE tournament_id = ? AND user_id != ?",
                (tournament_id, exclude_user_id),
            )
            for member in members:
                send_push_to_user(member["user_id"], payload, cfg)

    threading.Thread(target=_send, daemon=True).start()


def notify_all_scores_in(tournament_id: int, puzzle_number: int, cfg: Config, app) -> None:
    """Notify all tournament members that all scores are in."""
    def _send():
        with app.app_context():
            t = db.query_one("SELECT name FROM tournaments WHERE id = ?", (tournament_id,))
            if not t:
                return
            payload = {
                "title": "All scores in!",
                "body": f"All scores are in for {t['name']} — Wordle #{puzzle_number}",
                "url": f"/tournaments/{tournament_id}",
            }
            members = db.query_all(
                "SELECT user_id FROM tournament_members WHERE tournament_id = ?",
                (tournament_id,),
            )
            for member in members:
                send_push_to_user(member["user_id"], payload, cfg)

    threading.Thread(target=_send, daemon=True).start()


def all_scores_submitted(tournament_id: int, puzzle_number: int) -> bool:
    """True if every tournament member has submitted a score for this puzzle."""
    total = db.query_one(
        "SELECT COUNT(*) as c FROM tournament_members WHERE tournament_id = ?",
        (tournament_id,),
    )["c"]
    submitted = db.query_one(
        """
        SELECT COUNT(*) as c FROM scores s
        JOIN tournament_members tm ON tm.user_id = s.user_id AND tm.tournament_id = ?
        WHERE s.puzzle_number = ?
        """,
        (tournament_id, puzzle_number),
    )["c"]
    return total > 0 and submitted >= total
