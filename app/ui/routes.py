from zoneinfo import available_timezones

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app import db
from app.auth import require_login
from app.config import get_config, current_puzzle_number
from app.tournaments.scoring import tournament_state

bp = Blueprint("ui", __name__)


@bp.route("/")
@require_login
def dashboard():
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg, tz=g.user["timezone"])
    uid = g.user["id"]

    # All tournaments
    all_tournaments = db.query_all("SELECT * FROM tournaments ORDER BY name")

    my_ids = {
        row["tournament_id"]
        for row in db.query_all(
            "SELECT tournament_id FROM tournament_members WHERE user_id = ?", (uid,)
        )
    }

    my_active = []
    open_tournaments = []
    ended_tournaments = []

    for t in all_tournaments:
        t = dict(t)
        state = tournament_state(t, today_puzzle)
        t["state"] = state
        if t["id"] in my_ids:
            if state in ("ACTIVE", "UPCOMING"):
                my_active.append(t)
            else:
                ended_tournaments.append(t)
        else:
            if state in ("ACTIVE", "UPCOMING"):
                open_tournaments.append(t)

    return render_template(
        "ui/dashboard.html",
        my_active=my_active,
        open_tournaments=open_tournaments,
        ended_tournaments=ended_tournaments,
        today_puzzle=today_puzzle,
    )


@bp.route("/submit")
@require_login
def submit_redirect():
    if g.submitted_today:
        return redirect(url_for("ui.dashboard"))
    cfg = get_config()
    today_puzzle = current_puzzle_number(cfg, tz=g.user["timezone"])
    uid = g.user["id"]
    my_ids = {
        row["tournament_id"]
        for row in db.query_all(
            "SELECT tournament_id FROM tournament_members WHERE user_id = ?", (uid,)
        )
    }
    for t in db.query_all("SELECT * FROM tournaments ORDER BY name"):
        t = dict(t)
        if t["id"] in my_ids and tournament_state(t, today_puzzle) == "ACTIVE":
            return redirect(url_for("tournaments.submit", tournament_id=t["id"]))
    return redirect(url_for("ui.dashboard"))


@bp.route("/profile", methods=["GET", "POST"])
@require_login
def profile():
    timezones = sorted(available_timezones())

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        tz = request.form.get("timezone", "UTC").strip()
        colorblind = 1 if request.form.get("colorblind") else 0

        errors = []
        if not name:
            errors.append("Name is required.")
        if tz not in available_timezones():
            tz = "UTC"

        if errors:
            return render_template("ui/profile.html", errors=errors, timezones=timezones)

        db.execute(
            "UPDATE users SET name = ?, timezone = ?, colorblind = ? WHERE id = ?",
            (name, tz, colorblind, g.user["id"]),
        )
        # Refresh g.user
        updated = db.query_one("SELECT * FROM users WHERE id = ?", (g.user["id"],))
        g.user = dict(updated)
        flash("Profile saved.", "success")
        return redirect(url_for("ui.profile"))

    return render_template("ui/profile.html", timezones=timezones)
