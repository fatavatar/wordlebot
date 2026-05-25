import threading
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.auth import require_admin, require_login
from app.config import get_config, current_puzzle_number
from app.tournaments.scoring import (
    ParseError,
    can_see_score,
    cell_class,
    compute_standings,
    is_past_deadline,
    parse_wordle_share,
    puzzle_date,
    tournament_state,
)

bp = Blueprint("tournaments", __name__, url_prefix="/tournaments")


def _get_tournament_or_404(tournament_id: int) -> dict:
    t = db.query_one("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
    if not t:
        abort(404)
    return dict(t)


def _is_member(tournament_id: int, user_id: int) -> bool:
    return bool(db.query_one(
        "SELECT 1 FROM tournament_members WHERE tournament_id = ? AND user_id = ?",
        (tournament_id, user_id),
    ))


def _apply_late_join_misses(tournament_id: int, user_id: int, tournament: dict):
    """Insert MISS rows for all days before the user joined."""
    cfg = get_config()
    today = current_puzzle_number(cfg)
    start = tournament["start_puzzle"]
    # Days from start up to (but not including) today that are past deadline
    for pnum in range(start, today):
        if is_past_deadline(pnum, g.user["timezone"], cfg):
            db.execute(
                "INSERT OR IGNORE INTO scores (user_id, puzzle_number, guesses, hard_mode, is_auto_miss) VALUES (?, ?, 0, 1, 1)",
                (user_id, pnum),
            )


# ── Admin: create tournament ──────────────────────────────────────────────────

@bp.route("/new", methods=["GET", "POST"])
@require_admin
def new():
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        start_puzzle_raw = request.form.get("start_puzzle", "").strip()
        num_days_raw = request.form.get("num_days", "").strip()

        errors = []
        if not name:
            errors.append("Tournament name is required.")
        try:
            start_puzzle = int(start_puzzle_raw)
            if start_puzzle <= 0:
                raise ValueError
        except ValueError:
            errors.append("Start puzzle must be a positive integer.")
            start_puzzle = today_puzzle

        try:
            num_days = int(num_days_raw)
            if num_days < 1:
                raise ValueError
        except ValueError:
            errors.append("Number of days must be at least 1.")
            num_days = 7

        if errors:
            return render_template("tournaments/create.html", errors=errors,
                                   today_puzzle=today_puzzle, form=request.form)

        cur = db.execute(
            "INSERT INTO tournaments (name, start_puzzle, num_days, created_by) VALUES (?, ?, ?, ?)",
            (name, start_puzzle, num_days, g.user["id"]),
        )
        return redirect(url_for("tournaments.detail", tournament_id=cur.lastrowid))

    return render_template("tournaments/create.html", today_puzzle=today_puzzle, form={})


# ── Tournament detail ─────────────────────────────────────────────────────────

@bp.route("/<int:tournament_id>")
@require_login
def detail(tournament_id: int):
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg)
    t = _get_tournament_or_404(tournament_id)
    state = tournament_state(t, today_puzzle)
    is_member = _is_member(tournament_id, g.user["id"])

    # Fetch all members (with join time)
    members = db.query_all(
        """
        SELECT u.*, tm.joined_at
        FROM tournament_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.tournament_id = ?
        ORDER BY u.name
        """,
        (tournament_id,),
    )
    members = [dict(m) for m in members]

    # Fetch all scores for puzzles in this tournament
    start = t["start_puzzle"]
    end = start + t["num_days"] - 1
    scores = db.query_all(
        "SELECT * FROM scores WHERE puzzle_number BETWEEN ? AND ? AND user_id IN "
        "(SELECT user_id FROM tournament_members WHERE tournament_id = ?)",
        (start, end, tournament_id),
    )
    scores = [dict(s) for s in scores]

    standings = compute_standings(members, scores, t, today_puzzle, cfg)

    # Build visibility map: {(user_id, puzzle_number): bool}
    viewer_id = g.user["id"]
    member_map = {m["id"]: m for m in members}
    puzzle_range = list(range(start, min(today_puzzle, end) + 1))

    def visible(uid, pnum):
        target = member_map.get(uid, {})
        return can_see_score(viewer_id, uid, pnum, scores, target, cfg)

    return render_template(
        "tournaments/detail.html",
        tournament=t,
        state=state,
        is_member=is_member,
        standings=standings,
        puzzle_range=puzzle_range,
        visible=visible,
        cell_class=cell_class,
        today_puzzle=today_puzzle,
        puzzle_date=lambda pnum: puzzle_date(pnum, cfg),
    )


# ── Join / Leave ──────────────────────────────────────────────────────────────

@bp.route("/<int:tournament_id>/join", methods=["POST"])
@require_login
def join(tournament_id: int):
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg)
    t = _get_tournament_or_404(tournament_id)
    state = tournament_state(t, today_puzzle)

    if state == "ENDED":
        flash("This tournament has ended.", "error")
        return redirect(url_for("tournaments.detail", tournament_id=tournament_id))

    if _is_member(tournament_id, g.user["id"]):
        flash("You're already in this tournament.", "info")
        return redirect(url_for("tournaments.detail", tournament_id=tournament_id))

    db.execute(
        "INSERT OR IGNORE INTO tournament_members (tournament_id, user_id) VALUES (?, ?)",
        (tournament_id, g.user["id"]),
    )

    # Apply late-join misses
    if state == "ACTIVE":
        _apply_late_join_misses(tournament_id, g.user["id"], t)

    flash("You've joined the tournament!", "success")
    return redirect(url_for("tournaments.detail", tournament_id=tournament_id))


@bp.route("/<int:tournament_id>/leave", methods=["POST"])
@require_login
def leave(tournament_id: int):
    db.execute(
        "DELETE FROM tournament_members WHERE tournament_id = ? AND user_id = ?",
        (tournament_id, g.user["id"]),
    )
    flash("You've left the tournament.", "info")
    return redirect(url_for("ui.dashboard"))


# ── Score submission ──────────────────────────────────────────────────────────

@bp.route("/<int:tournament_id>/submit", methods=["GET", "POST"])
@require_login
def submit(tournament_id: int):
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg)
    t = _get_tournament_or_404(tournament_id)
    state = tournament_state(t, today_puzzle)

    if state == "ENDED":
        flash("This tournament has ended.", "error")
        return redirect(url_for("tournaments.detail", tournament_id=tournament_id))

    if not _is_member(tournament_id, g.user["id"]):
        flash("Join the tournament first.", "error")
        return redirect(url_for("tournaments.detail", tournament_id=tournament_id))

    if request.method == "POST":
        share_text = request.form.get("share_text", "").strip()
        comment = request.form.get("comment", "").strip() or None

        try:
            parsed = parse_wordle_share(share_text, today_puzzle)
        except ParseError as e:
            return render_template("tournaments/submit.html", tournament=t,
                                   state=state, error=str(e), share_text=share_text)

        # Check puzzle is within tournament range
        start = t["start_puzzle"]
        end = start + t["num_days"] - 1
        if not (start <= parsed.puzzle_number <= end):
            return render_template(
                "tournaments/submit.html", tournament=t, state=state,
                error=f"Puzzle #{parsed.puzzle_number} is not part of this tournament (#{start}–#{end}).",
                share_text=share_text,
            )

        # Check deadline
        if is_past_deadline(parsed.puzzle_number, g.user["timezone"], cfg):
            return render_template(
                "tournaments/submit.html", tournament=t, state=state,
                error="The deadline for this puzzle has passed (midnight in your timezone).",
                share_text=share_text,
            )

        # Insert score (UNIQUE constraint handles duplicates)
        try:
            db.execute(
                """
                INSERT INTO scores (user_id, puzzle_number, guesses, hard_mode, share_text, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (g.user["id"], parsed.puzzle_number, parsed.guesses, 1, share_text, comment),
            )
        except Exception:
            return render_template(
                "tournaments/submit.html", tournament=t, state=state,
                error="You've already submitted a score for this puzzle.",
                share_text=share_text,
            )

        # Push notifications (stub — implemented in Phase 4)
        _trigger_push_on_submit(tournament_id, parsed.puzzle_number, today_puzzle)

        flash("Score submitted!", "success")
        return redirect(url_for("tournaments.detail", tournament_id=tournament_id))

    # Pre-populate from Android share sheet
    share_text = request.args.get("share_text", "")
    return render_template("tournaments/submit.html", tournament=t, state=state,
                           share_text=share_text)


def _trigger_push_on_submit(tournament_id: int, puzzle_number: int, today_puzzle: int):
    """Fire-and-forget push notifications to tournament members."""
    from flask import current_app
    from app.pwa.push_utils import (
        notify_tournament_members,
        notify_all_scores_in,
        all_scores_submitted,
    )
    cfg = get_config()
    app = current_app._get_current_object()

    payload = {
        "title": "New score submitted",
        "body": f"{g.user['name']} submitted their Wordle #{puzzle_number} score!",
        "url": f"/tournaments/{tournament_id}",
    }
    notify_tournament_members(tournament_id, g.user["id"], payload, cfg, app)

    if all_scores_submitted(tournament_id, puzzle_number):
        notify_all_scores_in(tournament_id, puzzle_number, cfg, app)


# ── Submit via Android share sheet ────────────────────────────────────────────

@bp.route("/submit-via-share")
@require_login
def submit_via_share():
    """Pre-populate submit form from Android share target."""
    share_text = request.args.get("share_text", "").strip()
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg)

    # Find active tournaments the user is in
    tournaments = db.query_all(
        """
        SELECT t.* FROM tournaments t
        JOIN tournament_members tm ON tm.tournament_id = t.id
        WHERE tm.user_id = ?
        ORDER BY t.name
        """,
        (g.user["id"],),
    )
    active = [t for t in tournaments if tournament_state(dict(t), today_puzzle) == "ACTIVE"]

    if len(active) == 1:
        return redirect(url_for("tournaments.submit", tournament_id=active[0]["id"],
                                share_text=share_text))

    return render_template("tournaments/pick_tournament.html",
                           tournaments=active, share_text=share_text)
