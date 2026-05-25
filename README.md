# Wordle Tournament

A Flask + SQLite web app for running multi-player Wordle tournaments. Players paste their daily Wordle share text to submit scores. The app tracks leaderboards, handles late joiners, and delivers push notifications. Installable as a PWA on iOS and Android.

---

## Features

- **Email-code auth** — passwordless login via 6-digit code (15 min TTL)
- **Tournaments** — admin creates tournaments with a start puzzle and duration; players join and submit daily
- **Leaderboard** — ranked by fewest misses, then fewest total guesses; scores are hidden until you've submitted for the day
- **Auto-miss** — background thread inserts MISS rows for members who don't submit before midnight in their timezone
- **Late-joiner penalty** — joining mid-tournament retroactively inserts MISS rows for days already elapsed
- **iOS Shortcut** — share directly from the Wordle app via the native iOS Share Sheet (POST /api/submit with your personal auth key)
- **Android Share** — manifest `share_target` pre-populates the submit form from the Android share sheet
- **PWA** — installable to home screen, offline fallback, service worker caching
- **Push notifications** — VAPID push when a teammate submits, and when all scores are in for the day
- **Colorblind mode** — orange/blue tile palette, persisted per user

---

## Requirements

- Python 3.10+
- A Gmail account (or any SMTP server) for sending login codes
- VAPID keys for push notifications (generate once, store in `.env`)

---

## Setup

### 1. Clone and create a virtualenv

```bash
git clone <repo-url>
cd wbai-claude
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```dotenv
SECRET_KEY=your-random-secret-key-here

# SMTP (Gmail example — use an App Password, not your account password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_SENDER=you@gmail.com

# VAPID (push notifications) — generate once with the command below
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_CLAIMS_EMAIL=you@example.com
```

**Generating VAPID keys** (one-time):

```bash
python3 - <<'EOF'
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print("VAPID_PRIVATE_KEY=" + v.private_key.private_bytes(
    encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.PEM,
    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PrivateFormat']).PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=__import__('cryptography.hazmat.primitives.serialization', fromlist=['NoEncryption']).NoEncryption()
).decode().strip())
print("VAPID_PUBLIC_KEY=" + v.public_key.public_bytes(
    encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.X962,
    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.UncompressedPoint
).hex())
EOF
```

Or use the [web-push-codelab VAPID key generator](https://web-push-codelab.glitch.me/).

### 3. Initialize the database

```bash
python3 manage.py init-db
```

This creates `wordle_tournament.db` (or the path set in `DATABASE`) with all tables and indexes.

### 4. Create your first admin user

Log in via the web UI first (this creates your user record), then:

```bash
python3 manage.py make-admin you@example.com
```

Admins can create tournaments. Regular users can join and submit.

### 5. Run the development server

```bash
python3 wsgi.py
# or
flask --app wsgi run --debug
```

The app runs on `http://localhost:5000`.

---

## Production Deployment

### With Gunicorn + nginx

```bash
pip install gunicorn
gunicorn wsgi:app --workers 2 --bind 0.0.0.0:8000
```

The app is single-process friendly (SQLite + WAL mode). Two workers is enough for a small group. Do not use more workers than SQLite WAL can handle under your write load — for a few dozen users, 2 workers is fine.

Recommended nginx config fragment:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### HTTPS

Push notifications and PWA installation require HTTPS. Use Let's Encrypt (certbot) or a reverse proxy like Caddy that handles TLS automatically.

### Systemd service

```ini
[Unit]
Description=Wordle Tournament
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/wbai-claude
EnvironmentFile=/opt/wbai-claude/.env
ExecStart=/opt/wbai-claude/.venv/bin/gunicorn wsgi:app --workers 2 --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable wordle-tournament
systemctl start wordle-tournament
```

---

## Management CLI

```bash
# Initialize or re-initialize the database schema (safe to re-run)
python3 manage.py init-db

# Grant admin privileges to a user (they must have logged in first)
python3 manage.py make-admin user@example.com

# Send a test login email to verify SMTP is working
python3 manage.py send-test-email user@example.com

# List all registered users
python3 manage.py list-users
```

---

## iOS Shortcut Setup

This lets you submit your Wordle score directly from the iOS share sheet without opening the browser.

1. Log in and go to **Profile → iOS Shortcut** (`/pwa/ios-shortcut`)
2. Follow the on-screen instructions — the page shows your personal auth key and the endpoint URL
3. In the Shortcuts app, create a shortcut that POSTs to `https://your-domain.com/api/submit` with:
   - `auth_key` — your personal key (shown on the iOS Shortcut page)
   - `score` — the shared Wordle text (from the Share Sheet input)
   - `comment` — optional comment (can be empty)

The API returns JSON: `{"status": "ok", "puzzle": 1234, "guesses": 3, "hardMode": true}`

---

## Android Share

The PWA manifest includes a `share_target` so Android's native share sheet can send Wordle results directly to the app. Install the PWA first (Add to Home Screen), then share from the Wordle app and select "Wordle Tournament" from the share sheet.

---

## Running Tests

```bash
# Install Playwright browsers (first time only)
playwright install chromium

# Run all tests
pytest tests/

# Skip slow Playwright tests (unit/integration only, ~5s)
pytest tests/ -m "not slow"

# Run a specific test file
pytest tests/e2e/test_ranking.py -v

# With coverage
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```

The test suite uses an in-memory SQLite database, a mock SMTP server, and a live Werkzeug server on a random port. No external services are required.

**Test files:**

| File | What it covers |
|---|---|
| `test_auth.py` | Login flow, email codes, session management, registration |
| `test_scoring.py` | Wordle share text parser, deadline logic, `can_see_score` |
| `test_tournaments.py` | Create/join/submit/leave, API endpoint, duplicate rejection |
| `test_dashboard.py` | Dashboard sections, live score preview, profile/colorblind |
| `test_pwa.py` | Manifest, service worker, push subscribe/unsubscribe, iOS Shortcut page |
| `test_ranking.py` | Ranking edge cases: tiebreaks, misses, late joiners, visibility |
| `test_full_flow.py` | End-to-end lifecycle, push notifications, colorblind persistence |

---

## Project Structure

```
wbai-claude/
├── app/
│   ├── __init__.py           # create_app(), blueprint registration, auto-miss scheduler
│   ├── config.py             # Config dataclass, loaded from .env
│   ├── db.py                 # Thread-local SQLite connections, query helpers
│   ├── db/schema.sql         # Full database schema
│   ├── auth/
│   │   ├── __init__.py       # require_login, require_admin decorators
│   │   ├── routes.py         # /login, /verify, /logout, /register
│   │   └── email_utils.py    # send_auth_code() via SMTP
│   ├── tournaments/
│   │   ├── routes.py         # /tournaments/*, /tournaments/<id>/submit
│   │   ├── scoring.py        # Wordle parser, standings, deadline logic
│   │   └── scheduler.py      # Auto-miss daemon thread
│   ├── ui/
│   │   └── routes.py         # /, /profile
│   ├── api/
│   │   └── routes.py         # POST /api/submit (iOS Shortcut)
│   ├── pwa/
│   │   ├── routes.py         # /pwa/*, push subscribe/unsubscribe endpoints
│   │   └── push_utils.py     # VAPID push, notify helpers
│   ├── templates/            # Jinja2 templates (NYT-themed)
│   └── static/
│       ├── css/nyt-theme.css # Full NYT color palette + colorblind mode
│       ├── js/app.js         # Score preview parser, SW registration
│       ├── js/sw.js          # Service worker (cache-first static, offline fallback)
│       ├── js/push.js        # Push subscription client
│       ├── manifest.json     # PWA manifest with share_target
│       ├── offline.html      # Offline fallback page
│       └── icons/            # 192×192 and 512×512 PNG icons
├── tests/e2e/                # Playwright + pytest test suite (81 tests)
├── manage.py                 # Management CLI
├── wsgi.py                   # WSGI entry point
├── requirements.txt
└── pyproject.toml            # pytest configuration
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Flask secret key for signing |
| `DATABASE` | No | `wordle_tournament.db` | Path to SQLite database file |
| `SMTP_HOST` | Yes | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP port (STARTTLS) |
| `SMTP_USERNAME` | Yes | — | SMTP login username |
| `SMTP_PASSWORD` | Yes | — | SMTP login password / app password |
| `EMAIL_SENDER` | Yes | — | From address for login emails |
| `SMTP_TLS` | No | `true` | Whether to use STARTTLS |
| `VAPID_PRIVATE_KEY` | Yes | — | VAPID private key for push notifications |
| `VAPID_PUBLIC_KEY` | Yes | — | VAPID public key (served to browsers) |
| `VAPID_CLAIMS_EMAIL` | Yes | — | Contact email in VAPID claims |
| `WORDLE_EPOCH_DATE` | No | `2021-06-19` | Override puzzle #0 date (`YYYY-MM-DD`) |

---

## Database

SQLite with WAL mode and foreign keys enabled. The schema lives in `app/db/schema.sql` and is idempotent (`CREATE TABLE IF NOT EXISTS`) — safe to re-run `manage.py init-db` without data loss.

**Backing up:**

```bash
# Simple file copy (safe with WAL mode when app is idle)
cp wordle_tournament.db wordle_tournament.db.bak

# Online backup (safe while app is running)
sqlite3 wordle_tournament.db ".backup wordle_tournament_backup.db"
```

**Inspecting:**

```bash
sqlite3 wordle_tournament.db
.tables
SELECT * FROM users;
SELECT t.name, COUNT(tm.user_id) as members
  FROM tournaments t
  LEFT JOIN tournament_members tm ON tm.tournament_id = t.id
  GROUP BY t.id;
```

---

## Scores and Puzzle Numbers

Wordle puzzle numbers are calculated as `(today - 2021-06-19).days`. Puzzle #0 was June 19, 2021. Today's puzzle number is shown on the submit page and in the leaderboard headers.

Scores use `guesses = 0` for a MISS (failed to solve or did not submit). `guesses = 1–6` is the number of attempts. `hard_mode = 1` means the share text had a `*` suffix (Hard Mode required to submit).

---

## Troubleshooting

**Login emails not arriving:**
- Run `python3 manage.py send-test-email you@example.com` to test SMTP
- For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) — not your account password
- Check spam folder

**Push notifications not working:**
- HTTPS is required (push will silently fail on HTTP)
- Verify VAPID keys are set correctly in `.env`
- Check browser console for service worker errors

**"Hard Mode required" error on submit:**
- The app only accepts Hard Mode shares — the share text must end with `*` on the header line (e.g. `Wordle 1234 3/6*`)
- Share from the Wordle app with Hard Mode enabled, or enable Hard Mode in Wordle settings

**Scores showing as `—` (hidden):**
- Expected behavior — scores are hidden until you submit for that day, or until midnight passes in the other player's timezone
- Once you submit, all other players' scores for that puzzle become visible
