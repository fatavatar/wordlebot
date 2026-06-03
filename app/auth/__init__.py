import functools
from datetime import datetime, timezone

from flask import g, redirect, request, url_for

from app import db


def _load_user_from_cookie():
    from flask import current_app
    token = request.cookies.get("wt_session")
    if not token:
        return None
    session_row = db.query_one(
        "SELECT s.user_id, s.expires_at FROM sessions s WHERE s.token = ?",
        (token,),
    )
    if not session_row:
        return None
    expires_at = datetime.fromisoformat(session_row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return None
    user = db.query_one("SELECT * FROM users WHERE id = ?", (session_row["user_id"],))
    return user


def require_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = _load_user_from_cookie()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        g.user = dict(user)
        # Check if the user has already submitted today's puzzle (used by nav)
        from app.config import get_config, current_puzzle_number
        _cfg = get_config()
        _today = current_puzzle_number(_cfg, tz=g.user.get("timezone", "UTC"))
        g.submitted_today = bool(db.query_one(
            "SELECT 1 FROM scores WHERE user_id = ? AND puzzle_number = ?",
            (g.user["id"], _today),
        ))
        # Redirect to registration if profile is incomplete
        if g.user["name"] is None and request.endpoint != "auth.register":
            return redirect(url_for("auth.register"))
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @functools.wraps(f)
    @require_login
    def decorated(*args, **kwargs):
        if not g.user.get("is_admin"):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated
