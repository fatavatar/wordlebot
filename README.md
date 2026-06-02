# Wordlebeta

A private Wordle tournament app. Compete daily with friends — submit your Hard Mode score, track standings on a live leaderboard, and get push notifications when teammates submit.

## Features

- **Tournaments** — admin creates multi-day competitions; players join and submit daily
- **Leaderboard** — ranked by fewest misses then fewest total guesses; today's scores only count once all members have submitted (prevents inferring scores from rank changes)
- **Passwordless auth** — login via 6-digit email code, no passwords
- **iOS Shortcut** — share directly from the Wordle app via the iOS share sheet
- **Android share target** — install the PWA and Wordlebeta appears in Android's share sheet
- **Push notifications** — notified when a teammate submits; full reveal notification once everyone's in
- **Auto-miss** — background thread inserts MISS rows for members who don't submit before midnight in their timezone
- **Late-joiner penalty** — joining mid-tournament retroactively inserts MISS rows for elapsed days
- **Colorblind mode** — swaps green/yellow for orange/blue throughout, persisted per user

## Running with Docker (recommended)

```bash
cp .env.example .env   # fill in your values
docker compose up -d
```

The SQLite database is mounted from `./wordle_tournament.db` — data persists across rebuilds.

First run — initialise the schema and create an admin:

```bash
docker compose exec web python manage.py init-db
# log in via the web UI first, then:
docker compose exec web python manage.py make-admin you@example.com
```

Rebuild after code changes:

```bash
docker compose up -d --build
```

Useful commands:

```bash
docker compose logs -f          # tail logs
docker compose restart          # restart container
docker compose down             # stop and remove container
```

## Running locally (dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask run --debug
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | yes | — | Flask secret key (long random string) |
| `DATABASE` | no | `wordle_tournament.db` | Path to SQLite file |
| `SMTP_HOST` | yes | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | no | `587` | SMTP port |
| `SMTP_USERNAME` | yes | — | SMTP login |
| `SMTP_PASSWORD` | yes | — | SMTP password / app password |
| `EMAIL_SENDER` | yes | — | From address for login emails |
| `SMTP_TLS` | no | `true` | Use STARTTLS |
| `VAPID_PRIVATE_KEY` | no | — | VAPID private key for push notifications |
| `VAPID_PUBLIC_KEY` | no | — | VAPID public key (served to browsers) |
| `VAPID_CLAIMS_EMAIL` | no | — | Contact email for VAPID |
| `IOS_SHORTCUT_ICLOUD_URL` | no | — | iCloud link shown on the iOS shortcut setup page |
| `WORDLE_EPOCH_DATE` | no | `2021-06-19` | Override puzzle #0 date |

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833).

Generate VAPID keys (one-time):

```bash
python3 -c "
from py_vapid import Vapid
v = Vapid(); v.generate_keys()
print('VAPID_PRIVATE_KEY=' + v.private_pem().decode().strip())
print('VAPID_PUBLIC_KEY=' + v.public_key.public_bytes(
    __import__('cryptography.hazmat.primitives.serialization',fromlist=['Encoding']).Encoding.X962,
    __import__('cryptography.hazmat.primitives.serialization',fromlist=['PublicFormat']).PublicFormat.UncompressedPoint
).hex())
"
```

Or use [web-push-codelab](https://web-push-codelab.glitch.me/).

## Management CLI

```bash
python manage.py init-db                    # initialise schema (safe to re-run)
python manage.py make-admin <email>         # grant admin to a user
python manage.py list-users                 # list all users
python manage.py send-test-email <email>    # test SMTP config
```

## iOS Shortcut setup

1. Log in and go to **Profile → Setup instructions**
2. Copy your personal API key
3. Tap **Add Shortcut**, then tap **⋯** to edit
4. Paste your API key into the first Text step, tap **Done → Add Shortcut**
5. In Wordle: tap **Share → Submit Wordle**

## Score submission

Scores must be **Hard Mode** (share text header ends with `*`). Submit via:

- **Web form** — paste share text on the tournament submit page
- **iOS Shortcut** — share from Wordle → Submit Wordle
- **Android share target** — install the PWA, then share directly from Wordle
- **API** — `POST /api/submit` with `auth_key`, `score` (share text), and optional `comment`

The API returns JSON: `{"status": "ok", "puzzle": 1234, "guesses": 3, "hardMode": true}`

## Database

SQLite with WAL mode and foreign keys. Schema is in `app/db/schema.sql`.

```bash
# Backup while app is running
sqlite3 wordle_tournament.db ".backup backup.db"
```

## Project structure

```
app/
├── __init__.py           # create_app(), blueprints, auto-miss scheduler
├── config.py             # Config dataclass from .env
├── db.py                 # Thread-local SQLite helpers
├── db/schema.sql
├── auth/                 # Login, verify, logout
├── tournaments/          # Tournament routes, scoring logic, scheduler
├── ui/                   # Dashboard, profile
├── api/                  # POST /api/submit
├── pwa/                  # Manifest, service worker, push, iOS shortcut
├── templates/
└── static/
    ├── css/nyt-theme.css
    ├── js/sw.js
    ├── manifest.json     # PWA manifest with share_target
    └── icons/
Dockerfile
docker-compose.yml
manage.py
wsgi.py
```
