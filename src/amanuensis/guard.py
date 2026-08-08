"""Did the decoder traverse the audio it was given? (PRD §5.7)

`initial_prompt` can silently destroy a transcript. It shipped in Phase 1 with
nothing watching it, and on 2026-08-05 a 30.5-second dictation returned two
words — no error, buffer full, text injected at the cursor as though it were
what had been said. This module is what watches it.

**Why coverage and not words per second.** The obvious instrument is a rate
floor: the transcript is too short for the speech, so divide one by the other.
This module was drafted that way and the draft was wrong, for three reasons
worth keeping because the wrong version is the intuitive one.

1. *It measures the speaker.* Words per second is how the user talks divided by
   how long they talked. The failure is where the decoder stopped. The proxy
   carries a confound — speaking rate — that the product has no evidence about,
   and its false-positive population is people who talk slowly or quietly,
   which overlaps the §4 user for whom "a dropped transcription is not a minor
   annoyance."
2. *It cannot judge short audio at all.* Word count is an integer, so at two
   seconds the rate quantises to 0.5 w/s **per word**: a genuine one-word "Yes."
   and a transcript collapsed to one word are the same measurement. That is why
   the draft needed a `min_audio_seconds` exemption — not policy, arithmetic —
   and short utterances are this product's ordinary case, so the exemption was
   a blind spot over the most common input.
3. *The real signal was already in hand.* faster-whisper returns segments
   carrying `start` and `end`, and the engine was joining the texts and
   discarding the rest.

**Coverage** is the last segment's end over retained speech. It reads 6.5% on
the live failure and about 95% on genuine speech of any length, it is
duration-independent, and it distinguishes a decoder that stopped early from
one that drifted — which is the question dictionary objection O3 left open.

**Two gates, not one.** Spending a decode and withholding the user's words have
costs that differ by orders of magnitude (objection O4). `retry_below_coverage`
triggers a re-decode; `min_decoded_coverage` gates the refusal.

What this module deliberately does *not* do: decide whether to run the retry.
Predicting its cost and calling the engine is scheduling, which belongs to
`DictationController`. Choosing between two decodes once both exist is a
judgement about transcripts, which belongs here — hence `resolve`.

What the guard cannot see: a hallucinated *expansion*, and a decode that
traverses the audio and gets the words wrong. §7.5 carries a no-invent check
for the first and it is a Phase 5 concern. Recording the gap is the honest
alternative to implying one instrument covers every failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from amanuensis.models.results import GuardOutcome, GuardVerdict

if TYPE_CHECKING:
    from amanuensis.config import GuardConfig

__all__ = ["evaluate", "resolve"]


def evaluate(
    text: str,
    *,
    decoded_seconds: float | None,
    retained_seconds: float,
    fell_back: bool,
    config: GuardConfig,
) -> GuardVerdict:
    """Judge one decode. Pure — no clock, no engine, no session.

    `decoded_seconds` is `None` from an engine that cannot report where
    decoding stopped, which routes to the fallback floor rather than to a pass.
    Treating "cannot tell" as "fine" would make the guard silently absent on a
    supported backend, which is this repository's recurring failure: green
    because it looked at nothing.
    """
    if config.min_decoded_coverage <= 0.0:
        return _skipped(
            retained_seconds, "the guard is disabled (min_decoded_coverage = 0)"
        )

    if fell_back:
        # No speech was detected, so `retained_seconds` is the whole clip
        # rather than speech, and every ratio below divides by the wrong thing.
        return _skipped(
            retained_seconds,
            "the VAD fell back — no speech was detected to measure against",
        )

    if retained_seconds <= 0.0:
        return _skipped(retained_seconds, "no speech was retained")

    if decoded_seconds is None:
        return _by_rate(text, retained_seconds, config)
    return _by_coverage(decoded_seconds, retained_seconds, config)


def resolve(first: GuardVerdict, second: GuardVerdict | None) -> GuardVerdict:
    """Settle a first decode against the unbiased retry, if one was run.

    The rule is *take the decode that got further*, and it is deliberately not
    "take the retry when the first one failed". A retry that covered less of the
    audio is a worse transcript, and substituting it would make the guard cause
    the failure it exists to catch.

    Substitution is the part with a user-visible cost: the retry was decoded
    without the vocabulary bias the user configured, so it is systematically
    worse at exactly the proper nouns `initial_prompt` exists for. §5.4's
    indicator therefore reports recovery distinctly from success — a transcript
    the product quietly swapped is dictionary objection O5 re-committed.
    """
    if second is None:
        return _final(first)

    # Two conditions, and the second is the one that matters. A retry that
    # improved coverage from 6% to 9% got further and is still a destroyed
    # transcript; calling that "recovered" would report a rescue that did not
    # happen, and would swap the stored record for no gain.
    recovered = (
        _score(second) > _score(first) and second.outcome is not GuardOutcome.FAILED
    )
    chosen = second if recovered else first

    reason = chosen.reason
    if not recovered and first.outcome is GuardOutcome.FAILED:
        reason = "the unbiased retry did not recover the transcript either"

    return GuardVerdict(
        outcome=GuardOutcome.RECOVERED if recovered else _final(chosen).outcome,
        retained_seconds=chosen.retained_seconds,
        coverage=chosen.coverage,
        words_per_second=chosen.words_per_second,
        reason=reason,
        retried=True,
        chose_retry=recovered,
    )


# ---------------------------------------------------------------------------
# The two instruments
# ---------------------------------------------------------------------------


def _by_coverage(
    decoded_seconds: float, retained_seconds: float, config: GuardConfig
) -> GuardVerdict:
    # Whisper timestamps are approximate and can run past the end of the clip.
    # Coverage above 1.0 is a rounding artefact, never a failure, so it is
    # clamped rather than allowed to look like an anomaly.
    coverage = min(decoded_seconds / retained_seconds, 1.0)
    failed = coverage < config.min_decoded_coverage
    return GuardVerdict(
        outcome=GuardOutcome.FAILED if failed else GuardOutcome.PASSED,
        retained_seconds=retained_seconds,
        coverage=coverage,
        reason=(
            f"the decoder covered {coverage:.0%} of {retained_seconds:.1f}s of speech"
            if failed
            else None
        ),
        retry_advised=coverage < config.retry_below_coverage,
    )


def _by_rate(text: str, retained_seconds: float, config: GuardConfig) -> GuardVerdict:
    """The fallback, for an engine that cannot say where decoding stopped.

    §7.2's Moonshine and Parakeet are genuine alternatives and may not report
    segments. The `min_audio_seconds` exemption below is a **blind spot**, not
    a feature: under this instrument short dictation is unguarded, because the
    quantisation described in the module docstring makes it unjudgeable.
    """
    if retained_seconds < config.min_audio_seconds:
        return _skipped(
            retained_seconds,
            f"under the fallback floor, speech shorter than min_audio_seconds "
            f"({config.min_audio_seconds}s) cannot be judged — a known blind spot",
        )

    rate = len(text.split()) / retained_seconds
    failed = rate < config.min_words_per_second
    return GuardVerdict(
        outcome=GuardOutcome.FAILED if failed else GuardOutcome.PASSED,
        retained_seconds=retained_seconds,
        words_per_second=rate,
        reason=(
            f"{rate:.2f} words per second of speech, against a floor of "
            f"{config.min_words_per_second}"
            if failed
            else None
        ),
        retry_advised=failed,
    )


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------


def _skipped(retained_seconds: float, reason: str) -> GuardVerdict:
    """A verdict that made no judgement, and says why it made none.

    The reason is never optional. Objection O10's failure is a guard that
    silently never fires, and "no outcome" is indistinguishable from "fine"
    unless the record says which one it was.
    """
    return GuardVerdict(
        outcome=GuardOutcome.SKIPPED,
        retained_seconds=retained_seconds,
        reason=reason,
    )


def _score(verdict: GuardVerdict) -> float:
    """How far this decode got, on whichever instrument judged it.

    The two are never mixed: a pair of verdicts being compared came from the
    same engine on the same audio, so either both have coverage or neither
    does. A skipped verdict scores below everything, because it is not a claim
    that the decode was good.
    """
    if verdict.outcome is GuardOutcome.SKIPPED:
        return -1.0
    if verdict.coverage is not None:
        return verdict.coverage
    return verdict.words_per_second if verdict.words_per_second is not None else -1.0


def _final(verdict: GuardVerdict) -> GuardVerdict:
    """Strip `retry_advised` from a verdict that is now the last word.

    `retry_advised` is advice to a caller that has already acted or declined to
    act. Leaving it set on a stored verdict would read as a retry that was
    owed and never happened.
    """
    if not verdict.retry_advised:
        return verdict
    return GuardVerdict(
        outcome=verdict.outcome,
        retained_seconds=verdict.retained_seconds,
        coverage=verdict.coverage,
        words_per_second=verdict.words_per_second,
        reason=verdict.reason,
        retried=verdict.retried,
        chose_retry=verdict.chose_retry,
    )
