import uuid
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.auth import require_login
from app.auth.email_utils import generate_code, send_auth_code
from app.config import get_config

bp = Blueprint("auth", __name__)


def _create_session(user_id: int) -> str:
    cfg = get_config()
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=cfg.SESSION_TTL_DAYS)
    db.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at.isoformat()),
    )
    return token


def _set_session_cookie(response, token: str):
    cfg = get_config()
    response.set_cookie(
        "wt_session",
        token,
        max_age=cfg.SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="Lax",
        secure=False,  # set True in production behind HTTPS
    )
    return response


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or "@" not in email:
            return render_template("auth/login.html", error="Please enter a valid email address.")

        cfg = get_config()
        code = generate_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=cfg.AUTH_CODE_TTL_MIN)

        # Invalidate any existing unused codes for this email
        db.execute("UPDATE auth_codes SET used = 1 WHERE email = ? AND used = 0", (email,))
        db.execute(
            "INSERT INTO auth_codes (email, code, expires_at) VALUES (?, ?, ?)",
            (email, code, expires_at.isoformat()),
        )

        try:
            send_auth_code(email, code, cfg)
        except Exception as exc:
            return render_template("auth/login.html", error=f"Failed to send email: {exc}")

        response = make_response(redirect(url_for("auth.verify")))
        response.set_cookie("wt_pending_email", email, httponly=True, samesite="Lax", max_age=900)
        return response

    return render_template("auth/login.html")


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    email = request.cookies.get("wt_pending_email", "")

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        email = request.form.get("email", email).strip().lower()

        if not code or not email:
            return render_template("auth/verify.html", email=email, error="Please enter your code.")

        row = db.query_one(
            "SELECT * FROM auth_codes WHERE email = ? AND code = ? AND used = 0 ORDER BY id DESC LIMIT 1",
            (email, code),
        )
        if not row:
            return render_template("auth/verify.html", email=email, error="Invalid code. Please try again.")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return render_template("auth/verify.html", email=email, error="Code has expired. Please request a new one.")

        # Mark code used
        db.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (row["id"],))

        # Upsert user
        user = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
        if not user:
            auth_key = str(uuid.uuid4())
            db.execute(
                "INSERT INTO users (email, auth_key) VALUES (?, ?)",
                (email, auth_key),
            )
            user = db.query_one("SELECT * FROM users WHERE email = ?", (email,))

        token = _create_session(user["id"])
        dest = url_for("auth.register") if user["name"] is None else (request.args.get("next") or url_for("ui.dashboard"))
        response = make_response(redirect(dest))
        _set_session_cookie(response, token)
        response.delete_cookie("wt_pending_email")
        return response

    return render_template("auth/verify.html", email=email)


@bp.route("/register", methods=["GET", "POST"])
@require_login
def register():
    from zoneinfo import available_timezones
    timezones = sorted(available_timezones())

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        tz = request.form.get("timezone", "UTC").strip()

        if not name:
            return render_template("auth/register.html", error="Name is required.", timezones=timezones)
        if tz not in available_timezones():
            tz = "UTC"

        db.execute("UPDATE users SET name = ?, timezone = ? WHERE id = ?", (name, tz, g.user["id"]))
        return redirect(url_for("ui.dashboard"))

    return render_template("auth/register.html", timezones=timezones)


@bp.route("/logout")
def logout():
    token = request.cookies.get("wt_session")
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie("wt_session")
    return response
