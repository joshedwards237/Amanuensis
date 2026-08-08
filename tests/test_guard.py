"""§5.7's judgement about one decode, and the two controls that make it mean
anything.

The guard asks whether the decoder traversed the audio it was given. Almost
every test here is one of two controls, deliberately:

**It must fire on the failures that exist.** The 30.5-second dictation that
returned two words. A guard that has never fired is a guard that has never been
tested, and this project has two gates that could have passed by measuring
nothing.

**It must not fire on genuine speech, at any duration.** This is the half most
likely to be wrong and the half the earlier design got wrong. A words-per-second
floor cannot judge short audio at all — word count is an integer, so at two
seconds the rate quantises to 0.5 w/s per word and a genuine one-word "Yes." is
the same measurement as a transcript collapsed to one word. Coverage has no such
problem, and the tests below say so at 2 s, 30 s and 60 s rather than exempting
the short case the way the floor had to.

What is *not* tested here is orchestration — whether a retry happens, and what
the controller does with the answer. `resolve` is here because choosing between
two decodes is a judgement about transcripts rather than about scheduling; the
decision to *run* the second decode is the controller's and is tested there.
"""

from __future__ import annotations

import pytest

from amanuensis.config import GuardConfig
from amanuensis.guard import evaluate, resolve
from amanuensis.models.results import GuardOutcome, GuardVerdict


def _verdict(
    text: str = "some words here",
    *,
    decoded_seconds: float | None = None,
    retained_seconds: float = 30.0,
    fell_back: bool = False,
    config: GuardConfig | None = None,
) -> GuardVerdict:
    return evaluate(
        text,
        decoded_seconds=decoded_seconds,
        retained_seconds=retained_seconds,
        fell_back=fell_back,
        config=config or GuardConfig(),
    )


# ---------------------------------------------------------------------------
# The positive control — the failure this was built for
# ---------------------------------------------------------------------------


def test_the_live_failure_fires() -> None:
    """30.5 s held, two words, and a decoder that stopped at about 2 s.

    §5.7's motivating event. Coverage 6.5% against a 50% refusal gate.
    """
    verdict = _verdict(" For Tenants.", decoded_seconds=2.0, retained_seconds=30.5)

    assert verdict.outcome is GuardOutcome.FAILED
    assert verdict.coverage == pytest.approx(0.0656, abs=0.001)
    assert verdict.retry_advised is True


def test_a_decoder_that_emitted_nothing_fires() -> None:
    verdict = _verdict("", decoded_seconds=0.0, retained_seconds=30.0)
    assert verdict.outcome is GuardOutcome.FAILED
    assert verdict.coverage == 0.0


def test_a_partial_collapse_is_caught_that_the_old_floor_would_have_missed() -> None:
    """Objection O4. 40% of the audio never decoded — a substantial loss that
    still reads as ordinary speech, so a words-per-second floor set low enough
    to be safe for withholding text cannot see it."""
    verdict = _verdict(decoded_seconds=18.0, retained_seconds=30.0)

    assert verdict.outcome is GuardOutcome.PASSED
    assert verdict.retry_advised is True


# ---------------------------------------------------------------------------
# The negative control — genuine speech survives, at every duration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("retained", "decoded", "what"),
    [
        (2.0, 1.9, "a genuine two-second utterance — the operator's common case"),
        (1.2, 1.1, "shorter still"),
        (10.0, 9.6, "the duration G1 is specified at"),
        (30.0, 29.2, "the length of the dictation that failed"),
        (60.0, 58.8, "Phase 3's gate length"),
    ],
)
def test_genuine_speech_is_not_flagged_at_any_duration(
    retained: float, decoded: float, what: str
) -> None:
    """The property the rate floor could not have.

    A words-per-second instrument needed `min_audio_seconds` to exempt short
    audio, which left short dictation unguarded — and short dictation is the
    ordinary case here. Coverage reads the same at 1.2 s and at 60 s.
    """
    verdict = _verdict(decoded_seconds=decoded, retained_seconds=retained)

    assert verdict.outcome is GuardOutcome.PASSED, what
    assert verdict.retry_advised is False, what


def test_speaking_rate_does_not_enter_the_judgement() -> None:
    """The confound the first design carried. Two transcripts over identical
    audio, one four times as many words as the other, both fully decoded —
    the guard must not be able to tell them apart."""
    slow = _verdict("well", decoded_seconds=9.5, retained_seconds=10.0)
    fast = _verdict(" ".join(["word"] * 40), decoded_seconds=9.5, retained_seconds=10.0)

    assert slow.outcome is fast.outcome is GuardOutcome.PASSED
    assert slow.coverage == fast.coverage


def test_the_refusal_gate_itself_passes() -> None:
    """At the threshold is not below it — and the difference is exactly the
    users the threshold is most likely to be wrong about."""
    verdict = _verdict(decoded_seconds=15.0, retained_seconds=30.0)

    assert verdict.coverage == pytest.approx(0.5)
    assert verdict.outcome is GuardOutcome.PASSED


def test_a_decoder_that_overruns_is_not_flagged() -> None:
    """Whisper timestamps are approximate and can exceed the clip. Coverage
    above 1.0 is a rounding artefact, never a failure."""
    verdict = _verdict(decoded_seconds=30.4, retained_seconds=30.0)

    assert verdict.outcome is GuardOutcome.PASSED


# ---------------------------------------------------------------------------
# Where it does not run — recorded, never inferred from a missing value
# ---------------------------------------------------------------------------


def test_a_zero_gate_disables_it() -> None:
    verdict = _verdict(
        "", decoded_seconds=0.0, config=GuardConfig(min_decoded_coverage=0.0)
    )
    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "disabled" in verdict.reason


def test_a_vad_fallback_suppresses_the_guard() -> None:
    """No speech was detected, so retained seconds is the whole clip rather
    than speech, and the denominator means something else (O10)."""
    verdict = _verdict("hm", decoded_seconds=1.0, fell_back=True)

    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "fell back" in verdict.reason


def test_no_retained_speech_is_not_a_division() -> None:
    verdict = _verdict("", decoded_seconds=0.0, retained_seconds=0.0)
    assert verdict.outcome is GuardOutcome.SKIPPED


# ---------------------------------------------------------------------------
# The fallback floor — engines that cannot say where decoding stopped
# ---------------------------------------------------------------------------


def test_an_engine_with_no_span_falls_back_to_the_rate_floor() -> None:
    """§7.2's Moonshine and Parakeet are genuine alternatives and may not
    report segments. Treating a missing span as a pass would make the guard
    silently absent on a supported backend."""
    verdict = _verdict(" For Tenants.", decoded_seconds=None, retained_seconds=30.5)

    assert verdict.outcome is GuardOutcome.FAILED
    assert verdict.coverage is None
    assert verdict.words_per_second == pytest.approx(0.066, abs=0.005)


def test_the_fallback_exempts_short_audio_and_says_that_is_a_blind_spot() -> None:
    """The limitation the primary instrument does not have. Recorded on the
    verdict so a non-firing guard is diagnosable rather than assumed correct."""
    verdict = _verdict("Yes.", decoded_seconds=None, retained_seconds=2.0)

    assert verdict.outcome is GuardOutcome.SKIPPED
    assert verdict.reason is not None
    assert "min_audio_seconds" in verdict.reason


def test_the_fallback_passes_genuine_speech() -> None:
    verdict = _verdict(
        " ".join(["word"] * 60), decoded_seconds=None, retained_seconds=30.0
    )
    assert verdict.outcome is GuardOutcome.PASSED


# ---------------------------------------------------------------------------
# O10 — a guard that never fires must be diagnosable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        {"decoded_seconds": 29.0},
        {"decoded_seconds": None},
        {"decoded_seconds": 1.0, "fell_back": True},
    ],
    ids=["ran", "fallback", "skipped"],
)
def test_retained_seconds_is_always_reported(case: dict) -> None:
    """An over-trimming VAD shrinks the denominator and nothing about that is
    visible from the outcome alone. The evidence travels with the verdict,
    including on the paths where no judgement was made."""
    verdict = _verdict(retained_seconds=30.0, **case)
    assert verdict.retained_seconds == 30.0


def test_coverage_is_none_rather_than_zero_when_it_was_not_measured() -> None:
    """`None` and `0.0` mean opposite things here — not measured versus the
    decoder produced nothing — and confusing them is how a guard reports a
    catastrophe it never looked for."""
    verdict = _verdict(decoded_seconds=None)
    assert verdict.coverage is None


# ---------------------------------------------------------------------------
# resolve — choosing between two decodes
# ---------------------------------------------------------------------------


def _at(coverage: float, retained: float = 30.0) -> GuardVerdict:
    return _verdict(decoded_seconds=coverage * retained, retained_seconds=retained)


def test_a_recovered_decode_is_taken() -> None:
    final = resolve(_at(0.06), _at(0.97))

    assert final.outcome is GuardOutcome.RECOVERED
    assert final.retried is True
    assert final.chose_retry is True


def test_a_retry_that_does_not_help_leaves_the_verdict_failed() -> None:
    final = resolve(_at(0.06), _at(0.09))

    assert final.outcome is GuardOutcome.FAILED
    assert final.retried is True
    assert final.chose_retry is False


def test_a_worse_retry_is_discarded() -> None:
    """The original was acceptable; the retry was not. Substituting a decode
    that lost more of the audio would be the guard causing the failure it
    exists to catch."""
    final = resolve(_at(0.7), _at(0.2))

    assert final.outcome is GuardOutcome.PASSED
    assert final.chose_retry is False
    assert final.coverage == pytest.approx(0.7)


def test_a_better_retry_is_taken_even_when_the_first_would_have_passed() -> None:
    """The middle band. 30% of the audio never decoded is a real loss even
    though it clears the refusal gate, and the retry recovered it."""
    final = resolve(_at(0.7), _at(0.98))

    assert final.outcome is GuardOutcome.RECOVERED
    assert final.chose_retry is True


def test_no_retry_leaves_the_first_verdict_alone() -> None:
    first = _at(0.06)

    final = resolve(first, None)

    assert final.outcome is GuardOutcome.FAILED
    assert final.retried is False
    assert final.chose_retry is False


def test_a_suspect_first_decode_with_no_retry_still_passes() -> None:
    """`retry_advised` is not a refusal. Only coverage below the refusal gate
    withholds text, and a retry that could not be run does not change that."""
    final = resolve(_at(0.7), None)

    assert final.outcome is GuardOutcome.PASSED
    assert final.retried is False
