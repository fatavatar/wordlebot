CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    email       TEXT UNIQUE NOT NULL,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    colorblind  INTEGER NOT NULL DEFAULT 0,
    dark_mode   INTEGER NOT NULL DEFAULT 0,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    auth_key    TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    code        TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT UNIQUE NOT NULL,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tournaments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    start_puzzle INTEGER NOT NULL,
    num_days     INTEGER NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tournament_members (
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    user_id       INTEGER NOT NULL REFERENCES users(id),
    joined_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tournament_id, user_id)
);

CREATE TABLE IF NOT EXISTS scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    puzzle_number INTEGER NOT NULL,
    guesses       INTEGER NOT NULL,
    hard_mode     INTEGER NOT NULL DEFAULT 1,
    share_text    TEXT,
    comment       TEXT,
    submitted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    is_auto_miss  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, puzzle_number)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    endpoint    TEXT NOT NULL,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_scores_puzzle    ON scores(puzzle_number);
CREATE INDEX IF NOT EXISTS idx_scores_user      ON scores(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token   ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_auth_codes_email ON auth_codes(email);
CREATE INDEX IF NOT EXISTS idx_tm_tournament    ON tournament_members(tournament_id);
