"""
REST API endpoint for iOS Shortcut submissions.
Auth via auth_key (long-lived UUID, no session cookie required).
"""

from flask import Blueprint, g, jsonify, request

from app import db
from app.config import get_config, current_puzzle_number
from app.tournaments.scoring import ParseError, is_past_deadline, parse_wordle_share, tournament_state

bp = Blueprint("api", __name__, url_prefix="/api")


def _auth_by_key(auth_key: str) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE auth_key = ?", (auth_key,))
    return dict(row) if row else None


@bp.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or request.form

    auth_key = data.get("auth_key") or data.get("key")
    if not auth_key:
        return jsonify({"error": "auth_key is required"}), 401

    user = _auth_by_key(auth_key)
    if not user:
        return jsonify({"error": "Invalid auth_key"}), 401

    share_text = (data.get("score") or data.get("share_text") or "").strip()
    comment = (data.get("comment") or "").strip() or None

    if not share_text:
        return jsonify({"error": "score is required"}), 400

    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg, tz=user.get("timezone", "UTC"))

    try:
        parsed = parse_wordle_share(share_text, today_puzzle)
    except ParseError as e:
        return jsonify({"error": str(e)}), 422

    if is_past_deadline(parsed.puzzle_number, user["timezone"], cfg):
        return jsonify({"error": "The deadline for this puzzle has passed."}), 422

    # Insert score
    try:
        db.execute(
            """
            INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode, share_text, comment)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user["id"], parsed.puzzle_number, parsed.guesses, 1, share_text, comment),
        )
    except Exception:
        return jsonify({"error": "Score already submitted for this puzzle."}), 409

    return jsonify({
        "status": "ok",
        "puzzle": parsed.puzzle_number,
        "guesses": parsed.guesses,
        "hardMode": parsed.hard_mode,
    })
