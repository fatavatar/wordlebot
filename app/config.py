import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    DATABASE: str = field(default_factory=lambda: os.environ.get("DATABASE", "wordle_tournament.db"))
    SECRET_KEY: str = field(default_factory=lambda: os.environ["SECRET_KEY"])

    SMTP_HOST: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", "smtp.gmail.com"))
    SMTP_PORT: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    SMTP_USERNAME: str = field(default_factory=lambda: os.environ.get("SMTP_USERNAME", ""))
    SMTP_PASSWORD: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    EMAIL_SENDER: str = field(default_factory=lambda: os.environ.get("EMAIL_SENDER", ""))
    SMTP_TLS: bool = field(default_factory=lambda: os.environ.get("SMTP_TLS", "true").lower() == "true")

    VAPID_PRIVATE_KEY: str = field(default_factory=lambda: os.environ.get("VAPID_PRIVATE_KEY", ""))
    VAPID_PUBLIC_KEY: str = field(default_factory=lambda: os.environ.get("VAPID_PUBLIC_KEY", ""))
    VAPID_CLAIMS_EMAIL: str = field(default_factory=lambda: os.environ.get("VAPID_CLAIMS_EMAIL", ""))

    IOS_SHORTCUT_ICLOUD_URL: str = field(default_factory=lambda: os.environ.get("IOS_SHORTCUT_ICLOUD_URL", ""))

    # Wordle puzzle #0 = June 19, 2021. Override with WORDLE_EPOCH_DATE=YYYY-MM-DD.
    WORDLE_EPOCH: date = field(default_factory=lambda: _parse_epoch())

    SESSION_TTL_DAYS: int = 30
    AUTH_CODE_TTL_MIN: int = 15

    TESTING: bool = False


def _parse_epoch() -> date:
    raw = os.environ.get("WORDLE_EPOCH_DATE", "2021-06-19")
    y, m, d = raw.split("-")
    return date(int(y), int(m), int(d))


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def current_puzzle_number(cfg: Config | None = None, reference: date | None = None, tz: str | None = None) -> int:
    if cfg is None:
        cfg = get_config()
    if reference:
        d = reference
    elif tz:
        from zoneinfo import ZoneInfo
        d = datetime.now(ZoneInfo(tz)).date()
    else:
        d = datetime.now(timezone.utc).date()
    return (d - cfg.WORDLE_EPOCH).days
