#!/usr/bin/env python3
"""Management CLI for Wordle Tournament."""

import argparse
import sys


def cmd_init_db(args):
    from app import create_app
    from app import db as db_module

    app = create_app()
    with app.app_context():
        db_module.init_db()
    print("Database initialized.")


def cmd_make_admin(args):
    email = args.email.strip().lower()
    from app import create_app
    from app import db as db_module

    app = create_app()
    with app.app_context():
        user = db_module.query_one("SELECT id, name FROM users WHERE email = ?", (email,))
        if not user:
            print(f"No user found with email: {email}")
            sys.exit(1)
        db_module.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
        print(f"Made admin: {user['name'] or email} ({email})")


def cmd_send_test_email(args):
    from app import create_app
    from app.auth.email_utils import send_auth_code
    from app.config import get_config

    app = create_app()
    with app.app_context():
        cfg = get_config()
        send_auth_code(args.email, "123456", cfg)
    print(f"Test email sent to {args.email}")


def cmd_list_users(args):
    from app import create_app
    from app import db as db_module

    app = create_app()
    with app.app_context():
        users = db_module.query_all("SELECT id, email, name, is_admin, timezone, created_at FROM users ORDER BY id")
        if not users:
            print("No users.")
            return
        print(f"{'ID':<5} {'EMAIL':<35} {'NAME':<20} {'ADMIN':<6} {'TZ':<25} CREATED")
        print("-" * 100)
        for u in users:
            print(f"{u['id']:<5} {u['email']:<35} {(u['name'] or '-'):<20} {('yes' if u['is_admin'] else 'no'):<6} {u['timezone']:<25} {u['created_at']}")


def main():
    parser = argparse.ArgumentParser(description="Wordle Tournament management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Initialize the database schema")

    p_admin = sub.add_parser("make-admin", help="Grant admin to a user")
    p_admin.add_argument("email", help="User email address")

    p_email = sub.add_parser("send-test-email", help="Send a test login email")
    p_email.add_argument("email", help="Recipient email address")

    sub.add_parser("list-users", help="List all registered users")

    args = parser.parse_args()

    commands = {
        "init-db": cmd_init_db,
        "make-admin": cmd_make_admin,
        "send-test-email": cmd_send_test_email,
        "list-users": cmd_list_users,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
