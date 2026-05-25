"""Sample Wordle share texts for testing."""

VALID_4_GUESSES = """\
Wordle 1234 4/6*
⬛🟨⬛⬛🟩
🟨⬛⬛🟩🟩
⬛🟩⬛🟩🟩
🟩🟩🟩🟩🟩
"""

VALID_1_GUESS = """\
Wordle 1234 1/6*
🟩🟩🟩🟩🟩
"""

VALID_MISS = """\
Wordle 1234 X/6*
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
"""

VALID_TODAY = """\
Wordle #TODAY 3/6*
⬛🟨⬛⬛🟩
🟩🟩⬛🟩🟩
🟩🟩🟩🟩🟩
"""

VALID_HASH_PREFIX = """\
Wordle #1234 4/6*
⬛🟨⬛⬛🟩
🟨⬛⬛🟩🟩
⬛🟩⬛🟩🟩
🟩🟩🟩🟩🟩
"""

NO_ASTERISK = """\
Wordle 1234 4/6
⬛🟨⬛⬛🟩
🟩🟩🟩🟩🟩
"""

MALFORMED_HEADER = """\
I played Wordle today and got it in 4!
"""

VALID_6_GUESSES = """\
Wordle 1234 6/6*
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛
⬛🟨⬛⬛⬛
🟨🟩⬛🟩⬛
🟩🟩🟩🟩🟩
"""
