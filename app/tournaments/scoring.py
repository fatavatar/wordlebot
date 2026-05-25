"""
Wordle share text parser, scoring logic, and deadline utilities.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Config, current_puzzle_number


class ParseError(Exception):
    pass


@dataclass
class ParsedScore:
    puzzle_number: int
    guesses: int       # 0 = MISS
    hard_mode: bool
    raw_header: str


# Matches: "Wordle 1234 4/6*"  or  "Wordle #1234 4/6*"  or  "Wordle #TODAY 4/6*"
_HEADER_RE = re.compile(
    r"^Wordle\s+(?:#TODAY|#?(?P<num>\d+))\s+(?P<g>X|\d)/6(?P<hard>\*)?",
    re.MULTILINE | re.IGNORECASE,
)


def parse_wordle_share(text: str, today_puzzle: int) -> ParsedScore:
    m = _HEADER_RE.search(text)
    if not m:
        raise ParseError("Could not find a Wordle score header. Make sure you're pasting the full share text.")

    if not m.group("hard"):
        raise ParseError("Only Hard Mode submissions are accepted (score must end with *).")

    raw = text[m.start():m.end()]

    if m.group("num"):
        puzzle_number = int(m.group("num"))
    else:
        # #TODAY
        puzzle_number = today_puzzle

    if puzzle_number <= 0:
        raise ParseError("Puzzle number must be a positive integer.")

    g = m.group("g")
    guesses = 0 if g == "X" else int(g)
    if guesses < 0 or guesses > 6:
        raise ParseError(f"Invalid guess count: {g}")

    return ParsedScore(
        puzzle_number=puzzle_number,
        guesses=guesses,
        hard_mode=True,
        raw_header=raw,
    )


def puzzle_date(puzzle_number: int, cfg: Config) -> date:
    """Return the calendar date for a given puzzle number."""
    return cfg.WORDLE_EPOCH + timedelta(days=puzzle_number)


def is_past_deadline(puzzle_number: int, user_timezone: str, cfg: Config) -> bool:
    """True if it's past midnight at the end of the puzzle day in the user's timezone."""
    p_date = puzzle_date(puzzle_number, cfg)
    tz = ZoneInfo(user_timezone)
    # Deadline: end of puzzle day at 23:59:59 local time
    deadline = datetime(p_date.year, p_date.month, p_date.day, 23, 59, 59, tzinfo=tz)
    return datetime.now(tz) > deadline


def tournament_state(t: dict, today_puzzle: int) -> str:
    """Compute UPCOMING / ACTIVE / ENDED dynamically from today's puzzle number."""
    start = t["start_puzzle"]
    end = start + t["num_days"] - 1
    if today_puzzle < start:
        return "UPCOMING"
    elif today_puzzle <= end:
        return "ACTIVE"
    else:
        return "ENDED"


def can_see_score(
    viewer_id: int,
    target_user_id: int,
    puzzle_number: int,
    scores: list[dict],
    target_user: dict,
    cfg: Config,
) -> bool:
    """
    Visibility rule:
    - Always visible if viewer == target
    - Visible if viewer has already submitted for this puzzle
    - Visible if the day has ended (past midnight) for the target user
    """
    if viewer_id == target_user_id:
        return True

    # Has the viewer submitted for this puzzle?
    viewer_submitted = any(
        s["user_id"] == viewer_id and s["puzzle_number"] == puzzle_number
        for s in scores
    )
    if viewer_submitted:
        return True

    # Has the target's day ended?
    return is_past_deadline(puzzle_number, target_user["timezone"], cfg)


def compute_standings(
    members: list[dict],
    scores: list[dict],
    tournament: dict,
    today_puzzle: int,
    cfg: Config,
) -> list[dict]:
    """
    Compute per-member standings for a tournament.

    Returns a list sorted by: total_misses ASC, total_guesses ASC.
    Each entry includes daily_scores keyed by puzzle_number.
    Late joiners: all days before join date count as MISS.
    """
    start = tournament["start_puzzle"]
    num_days = tournament["num_days"]
    end = start + num_days - 1

    # Build a score lookup: (user_id, puzzle_number) -> score row
    score_map: dict[tuple, dict] = {}
    for s in scores:
        score_map[(s["user_id"], s["puzzle_number"])] = s

    results = []
    for member in members:
        uid = member["id"]
        join_dt = datetime.fromisoformat(member["joined_at"])
        join_puzzle = max(
            start,
            (join_dt.date() - cfg.WORDLE_EPOCH).days,
        )

        total_misses = 0
        total_guesses = 0
        days_submitted = 0
        daily_scores: dict[int, dict] = {}

        for pnum in range(start, min(today_puzzle, end) + 1):
            row = score_map.get((uid, pnum))

            if row:
                guesses = row["guesses"]
                daily_scores[pnum] = {
                    "guesses": guesses,
                    "is_auto_miss": bool(row["is_auto_miss"]),
                    "submitted_at": row["submitted_at"],
                    "comment": row.get("comment"),
                    "share_text": row.get("share_text"),
                }
                if guesses == 0:
                    total_misses += 1
                else:
                    total_guesses += guesses
                    days_submitted += 1
            elif pnum < join_puzzle:
                # Late joiner penalty — days before they joined
                total_misses += 1
                daily_scores[pnum] = {"guesses": 0, "is_auto_miss": True, "late_join": True}
            else:
                # Not yet submitted (today or future puzzles don't count yet)
                daily_scores[pnum] = {"guesses": None}

        results.append({
            "user_id": uid,
            "name": member["name"],
            "email": member["email"],
            "total_misses": total_misses,
            "total_guesses": total_guesses,
            "days_submitted": days_submitted,
            "daily_scores": daily_scores,
        })

    # Sort: fewest misses first, then fewest total guesses
    results.sort(key=lambda r: (r["total_misses"], r["total_guesses"]))

    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def cell_class(guesses: int | None) -> str:
    if guesses is None:
        return "future"
    if guesses == 0:
        return "miss"
    if guesses <= 2:
        return "guess-great"
    if guesses <= 4:
        return "guess-ok"
    return "guess-bad"
