"""PWA routes: manifest, service worker, push subscriptions, iOS Shortcut page."""

import json
import plistlib
import uuid

from flask import Blueprint, Response, g, jsonify, render_template, request

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
    cfg = get_config()
    return render_template(
        "pwa/ios_shortcut.html",
        icloud_url=cfg.IOS_SHORTCUT_ICLOUD_URL,
        auth_key=g.user["auth_key"],
    )


@bp.route("/ios-shortcut/download")
@require_login
def ios_shortcut_download():
    base_url = request.host_url.rstrip("/")
    api_url = f"{base_url}/api/submit"
    auth_key_uuid = str(uuid.uuid4()).upper()
    comment_uuid = str(uuid.uuid4()).upper()

    shortcut = {
        "WFWorkflowName": "Submit Wordle",
        "WFWorkflowClientVersion": "1140.1",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowInputContentItemClasses": ["WFTextContentItem"],
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,
            "WFWorkflowIconStartColor": 431817727,
        },
        "WFWorkflowNoInputBehavior": {
            "Name": "WFWorkflowNoInputBehaviorAskForInput",
            "Parameters": {"ItemClass": "WFTextContentItem"},
        },
        "WFWorkflowTypes": [],
        "WFWorkflowActions": [
            # Text action holding the auth key — user edits this once after importing
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
                "WFWorkflowActionParameters": {
                    "WFTextActionText": {
                        "Value": {"string": "YOUR_AUTH_KEY"},
                        "WFSerializationType": "WFTextTokenString",
                    },
                    "UUID": auth_key_uuid,
                    "CustomOutputName": "Auth Key",
                },
            },
            # Ask for optional comment
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
                "WFWorkflowActionParameters": {
                    "WFAskActionPrompt": "Add a comment (optional)",
                    "WFAskActionDefaultAnswer": "",
                    "WFAskActionInputType": "Text",
                    "UUID": comment_uuid,
                    "CustomOutputName": "Comment",
                },
            },
            # POST score + comment to API
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
                "WFWorkflowActionParameters": {
                    "WFHTTPMethod": "POST",
                    "WFURL": api_url,
                    "WFHTTPBodyType": "JSON",
                    "WFJSONValues": {
                        "Value": {
                            "WFDictionaryFieldValueItems": [
                                {
                                    "WFItemType": 0,
                                    "WFKey": {"Value": {"string": "auth_key"}, "WFSerializationType": "WFTextTokenString"},
                                    "WFValue": {
                                        "Value": {
                                            "attachmentsByRange": {
                                                "{0, 1}": {
                                                    "OutputName": "Auth Key",
                                                    "OutputUUID": auth_key_uuid,
                                                    "Type": "ActionOutput",
                                                }
                                            },
                                            "string": "￼",
                                        },
                                        "WFSerializationType": "WFTextTokenString",
                                    },
                                },
                                {
                                    "WFItemType": 0,
                                    "WFKey": {"Value": {"string": "score"}, "WFSerializationType": "WFTextTokenString"},
                                    "WFValue": {
                                        "Value": {
                                            "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}},
                                            "string": "￼",
                                        },
                                        "WFSerializationType": "WFTextTokenString",
                                    },
                                },
                                {
                                    "WFItemType": 0,
                                    "WFKey": {"Value": {"string": "comment"}, "WFSerializationType": "WFTextTokenString"},
                                    "WFValue": {
                                        "Value": {
                                            "attachmentsByRange": {
                                                "{0, 1}": {
                                                    "OutputName": "Comment",
                                                    "OutputUUID": comment_uuid,
                                                    "Type": "ActionOutput",
                                                }
                                            },
                                            "string": "￼",
                                        },
                                        "WFSerializationType": "WFTextTokenString",
                                    },
                                },
                            ]
                        },
                        "WFSerializationType": "WFDictionaryFieldValue",
                    },
                },
            },
            # Open the app
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
                "WFWorkflowActionParameters": {"WFURL": base_url},
            },
        ],
    }

    data = plistlib.dumps(shortcut, fmt=plistlib.FMT_BINARY)
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="Submit Wordle.shortcut"'},
    )


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
