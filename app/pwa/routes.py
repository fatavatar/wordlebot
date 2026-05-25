"""PWA routes: manifest, service worker, push subscriptions, iOS Shortcut page."""

import json

from flask import Blueprint, g, jsonify, render_template, request

from app import db
from app.auth import require_login
from app.config import get_config

bp = Blueprint("pwa", __name__, url_prefix="/pwa")


@bp.route("/vapid-public-key")
def vapid_public_key():
    cfg = get_config()
    return jsonify({"publicKey": cfg.VAPID_PUBLIC_KEY})


@bp.route("/push/subscribe", methods=["POST"])
@require_login
def push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint", "")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid subscription"}), 400

    db.execute(
        "INSERT OR REPLACE INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
        (g.user["id"], endpoint, p256dh, auth),
    )
    return jsonify({"status": "ok"})


@bp.route("/push/unsubscribe", methods=["POST"])
@require_login
def push_unsubscribe():
    db.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (g.user["id"],))
    return jsonify({"status": "ok"})


@bp.route("/ios-shortcut")
@require_login
def ios_shortcut():
    return render_template("pwa/ios_shortcut.html")


@bp.route("/notification-help")
@require_login
def notification_help():
    return render_template("pwa/notification_help.html")


@bp.route("/push/test", methods=["POST"])
@require_login
def push_test():
    if not g.user.get("is_admin"):
        from flask import abort
        abort(403)
    from app.pwa.push_utils import send_push_to_user
    cfg = get_config()
    sent = send_push_to_user(
        g.user["id"],
        {"title": "Test Notification", "body": "Push is working!", "url": "/"},
        cfg,
    )
    return jsonify({"sent": sent})
