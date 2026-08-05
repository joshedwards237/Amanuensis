"""§5.7's arithmetic, and the two controls that make it mean anything.

The guard is a floor on words per second of retained speech. Almost every test
here is one of two controls, deliberately:

**It must fire on the failures that exist.** The 30.5-second dictation that
returned two words, and the corpus collapse before it. A guard that has never
fired is a guard that has never been tested, and this project has two gates
that could have passed by measuring nothing.

**It must not fire on genuine speech.** The Phase 1 corpus ran 2.18–3.33 words
per second across six samples. A floor that flags a slow speaker is worse than
no floor, because it refuses to inject words the user actually said — so the
negative control is not a formality here, it is the thing most likely to be
wrong.

What is *not* tested here is orchestration. Whether a fired verdict triggers a
retry, and what happens when the retry also fires, belongs to the controller
and is tested there. This module answers one question about one transcript.
"""

from __future__ import annotations

import pytest

from amanuensis.config import GuardConfig
from amanuensis.guard import evaluate
from amanuensis.models.results import GuardOutcome


def _verdict(
    text: str,
    retained_seconds: float,
    *,
    fell_back: bool = False,
    config: GuardConfig | None = None,
):
    return evaluate(
        text,
        retained_seconds=retained_seconds,
        fell_back=fell_back,
        config=config or GuardConfig(),
    )


# ---------------------------------------------------------------------------
# The positive control — the failures this was built for
# ---------------------------------------------------------------------------


def test_the_live_failure_fires() -> None:
    """30.5 s of held hotkey, two words. 0.066 w/s. 2026-08-05, §5.7."""
    verdict = _verdict(" For Tenants.", 30.5)
    assert verdict.outcome is GuardOutcome.FAILED
    assert verdict.words_per_second == pytest.approx(0.066, abs=0.005)


def test_the_measured_corpus_collapse_fires() -> None:
    """A prose prompt reduced a 25 s clip to five words. 0.20 w/s."""
    verdict = _verdict("And how much is this?", 25.0)
    assert verdict.outcome is GuardOutcome.FAILED


def test_a_transcript_of_nothing_fires() -> None:
    """The limit case of the same failure, and the one a rate cannot express."""
    verdict = _verdict("   ", 30.0)
    assert verdict.outcome is GuardOutcome.FAILED
    assert verdict.words_per_second == 0.0


# ---------------------------------------------------------------------------
# The negative control — genuine speech must survive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rate", "what"),
    [
        (2.18, "slowest genuine Phase 1 corpus sample"),
        (3.33, "fastest genuine Phase 1 corpus sample"),
        (1.5, "slower than anything measured, still ordinary speech"),
        (0.51, "one hundredth above the floor"),
    ],
)
def test_genuine_speech_is_not_flagged(rate: float, what: str) -> None:
    seconds = 60.0
    words = " ".join(["word"] * round(rate * seconds))
    verdict = _verdict(words, seconds)
    assert verdict.outcome is GuardOutcome.PASSED, what


def test_the_floor_itself_passes() -> None:
    """A rate exactly at the floor is not below it.

    Stated as a test because "below the floor" and "at or below the floor"
    differ by exactly the users the floor is most likely to be wrong about.
    """
    verdict = _verdict(" ".join(["word"] * 5), 10.0)
    assert verdict.words_per_second == pytest.approx(0.5)
    assert verdict.outcome is GuardOutcome.PASSED


# ---------------------------------------------------------------------------
# The three cases where it does not run — each recorded, none inferred
# ---------------------------------------------------------------------------


def test_short_utterances_are_not_checked() -> None:
    """A genuine two-second "OK, do that" is 1.5 w/s — but "Yes." is 0.5."""
    verdict = _verdict("Yes.", 2.0)
    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "min_audio_seconds" in verdict.reason


def test_the_boundary_second_is_checked() -> None:
    """`min_audio_seconds` is the shortest clip the guard *does* judge."""
    verdict = _verdict("one two three four five six seven", 5.0)
    assert verdict.outcome is GuardOutcome.PASSED


def test_a_vad_fallback_suppresses_the_guard() -> None:
    """No speech was detected, so the denominator is not speech (O10)."""
    verdict = _verdict("hm", 30.0, fell_back=True)
    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "fell back" in verdict.reason


def test_a_zero_floor_disables_it() -> None:
    verdict = _verdict("", 60.0, config=GuardConfig(min_words_per_second=0.0))
    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "disabled" in verdict.reason


# ---------------------------------------------------------------------------
# O10 — a guard that never fires must be diagnosable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        {"text": "a b c d e f", "retained_seconds": 30.0},
        {"text": "one", "retained_seconds": 2.0},
        {"text": "one", "retained_seconds": 30.0, "fell_back": True},
    ],
    ids=["ran", "skipped-short", "skipped-fallback"],
)
def test_retained_seconds_is_always_reported(case: dict) -> None:
    """Objection O10: an over-trimming VAD inflates the rate silently.

    The verdict alone cannot show that. The denominator has to travel with it,
    including — especially — on the paths where no rate was computed at all.
    """
    verdict = _verdict(**case)
    assert verdict.retained_seconds == case["retained_seconds"]


def test_no_rate_is_reported_when_none_was_computed() -> None:
    """`None` and `0.0` mean opposite things and must not be confused."""
    verdict = _verdict("one", 2.0)
    assert verdict.words_per_second is None


# ---------------------------------------------------------------------------
# Counting words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "words"),
    [
        (" leading and trailing ", 3),
        ("double  spaced   words", 3),
        ("line\nbreaks\tand\ttabs", 4),
        ("", 0),
        ("hyphenated-words count once", 3),
    ],
)
def test_word_counting(text: str, words: int) -> None:
    verdict = _verdict(text, 60.0)
    assert verdict.words_per_second == pytest.approx(words / 60.0)
