# Wordle Tournament

A PWA for running multi-player Wordle tournaments with daily score tracking, leaderboards, and mobile integration.

**Stack:** Flask + SQLite (Python 3 stdlib DB, zero external infra). Deployed as a single-process app.

---

## Players & Authentication

Users sign up with:
- **Name** (display name, required)
- **Email** (unique, required)
- **Timezone** (IANA timezone string, e.g. `America/New_York`; required)
- **Color-Blind** flag to denote if the user is colorblind.

**Auth flow:**
1. User enters email on the login page.
2. Server generates a 6-digit confirmation code, emails it to the user.
3. User enters the code on the site to log in.
4. A session cookie is set (HTTP-only, secure). Codes expire after 15 minutes.
5. Returning users can request a new code at any time; the previous code is invalidated.

No passwords are stored. No persistent tokens beyond the session cookie.

**Admins:** Designated via a CLI command (`python manage.py make-admin <email>`). Admins can create tournaments, view all scores, and manage tournament state.

---

## Wordle Score Format

**Parser extracts from the header line:**
- **Puzzle number:** `1234` (or `#TODAY` for the current puzzle)
- **Guess count:** `4` (number of guesses to solve)
- **Hard mode:** `*` suffix on the guess count (e.g., `4/6*`)
- **Miss indicator:** `X` suffix (e.g., `X/6X` means they didn't solve it)

**Validation rules:**
- Hard mode is **required** — submissions without `*` are rejected with an error.
- Guess count must be 1–6 for solved puzzles.
- Puzzle number must be a positive integer or `#TODAY`.

---

## Tournament Model

**An admin creates a tournament with:**
- **Name** (required)
- **Start Wordle #** (the puzzle number the tournament begins with)
- **Number of days** (e.g., 7 for a week-long tournament)

**Tournament states:**
- `UPCOMING` - start wordle number is tomorrow or later.  Can join, but there are no scores yet.
- `ACTIVE` — users can join and submit scores.
- `ENDED` — tournament is read-only; displays final standings.

Multiple tournaments may run concurrently. A user may join any number of active tournaments.

**Joining:**
- Users can join any active/upcoming tournament from the dashboard.
- If a user joins after the start date, all prior days count as **MISS**.

**Scoring:**
- One daily submission applies to **all active tournaments** a user is in.
- Score = number of guesses (lower is better).
- **MISS** = 0 guesses (worst outcome) — assigned when a user doesn't submit by their deadline or explicitly marks a miss.
- **Ranking:** Fewest misses first. Tiebreaker: fewest total guesses.

**Deadline:**
- Scores are due by **midnight (00:00:00) in the user's configured timezone**.
- After midnight, the user's entry for that day auto-records as MISS.
- Users may update their timezone at any time (affects future deadlines only).

**Auto-end:**
- After the final day passes for all participants, the tournament transitions to `ENDED` automatically (or an admin can end it early).

---

## Score Visibility Rules

**The core privacy rule:** A user only sees another user's score for a given day when **either**:
1. The user has submitted their own score already **OR**
2. The day has ended (past midnight) for that user and they have recorded a miss.

Until then, other users' scores are hidden. Comments are always visible once posted.

**Per-day detail view:** Clicking a day shows all full Wordle submissions (the grid) and comments for visible scores.

---

## Interface

**Dashboard (home page):** Three sections:
1. **My Active Tournaments** — tournaments the user is participating in.
2. **Open Tournaments** — active/upcoming tournaments the user hasn't joined yet (with a "Join" button).
3. **Ended Tournaments** — completed tournaments (read-only leaderboard view).

**Tournament detail page:**
- Leaderboard table: rank, name, misses, total guesses.
- Day-by-day grid: each cell shows a user's guess count (or `MISS`), with a comment indicator (💬) if present.
- Hidden scores show `—` with a tooltip explaining why.
- Click a day to expand all submissions and comments for that day.

**Score submission page:**
- Paste area for the Wordle share text.
- Comment field (optional).
- Parse preview: shows extracted puzzle #, guess count, and hard mode status before submit.
- Submit button.

**NYT Theme**
- Use color scheme from NYT wordle game (Including the right colors for color-blind users)
- Use fonts from NYT Wordle game (no copywrite issues, this will be a privately hosted game for a few users)
- Use design styling from NYT Wordle game.

---

## iOS Share Shortcut Integration

An iOS Shortcut allows users to share their Wordle score directly from the Wordle app.  Provide detailed instructions to users for setting this up.

**Flow:**
1. User downloads the Shortcut (provided on the site). The Shortcut embeds the user's unique `auth_key` (a UUID set during onboarding).
2. From the Wordle app, user taps Share → selects the Shortcut.
3. The Shortcut captures the share text (Wordle score), prompts the user for an optional comment.
4. The Shortcut POSTs to `POST /api/submit` with the score text, comment, and `auth_key`.
5. On success, the Shortcut opens the PWA deep-link to the current tournament day: `wordletourn.com/tournament/<id>/day/<puzzle#>`.

**API endpoint (`POST /api/submit`):**
- Auth: `auth_key` parameter (long-lived per-user UUID, revocable from settings).
- Body: `{ "score": "<wordle share text>", "comment": "<optional>" }`
- Response: `{ "status": "ok", "puzzle": 1234, "guesses": 4, "hardMode": true }` or error.

**Android:** Uses the native share sheet — the OS routes the shared text to the PWA, which parses it in the submission form (still allow a comment).

---

## Notifications

**PWA push notifications** via the Web Push API (no Firebase dependency — use native VAPID).

**Notification triggers:**
1. **Score submitted:** When a user submits, all other participants in the same active tournament get a notification: `"{Name} submitted their score for Wordle #{N}"` + their comment if present.
2. **All scores in:** When all participants have submitted (or the day ends): `"All scores in for {Tournament Name} — Wordle #{N}"`.

**Permission:** On first visit, prompt the user to enable notifications. Persist the subscription server-side.  Enable users to turn this on/off from their profile page.  Give a help button with directions to enable notifications for the PWA if they are having issues.

---

## Testing

A core feature for **EVERY** phase.  End to end unit and integration testing with playwright.

---

## Non-Functional Requirements

- **PWA:** Installable on iOS and Android. Offline-capable for viewing cached tournament data.
- **Mobile-first responsive design.**
- **SQLite database** — single file, simple backups. No migrations needed for v1 (schema is stable).
- **Deploy:** Single Flask process behind a reverse proxy (nginx or Caddy). HTTPS required for PWA + push.
