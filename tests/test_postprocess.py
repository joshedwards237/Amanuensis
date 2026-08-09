"""The deterministic rules pass, and the two things it must never do.

`RuleBasedPostProcessor` is **ported** from `experiments/scripts/exp4_rules_only.py`,
which measured it against the Phase 1 corpus on 2026-07-31: WER movement +0.00,
strict WER 24.66 → 24.32, latency p50 0.0445 ms / p95 0.0505 ms, and 0/6 on both
safety checks. So the tests here are not exploring a design — they are pinning
behaviour that already has numbers attached, and the two most important ones are
about what the pass *declines* to do:

**It never lowercases.** A mid-sentence capital is indistinguishable from a
proper noun without a model, and PRD §7.3's standing finding is that silent
heuristic rewriting of the user's words is unacceptable. Three separate records
reached that conclusion independently — the experiment, the disfluency gate's
15-flagged/~10-real count, and this phase's objection O6.

**It never converts spoken numbers.** `one thought ends and the next one starts`
became `1 thought ends and the next 1 starts` on the first real corpus it met.

The safety checks are the experiment's, reused unmodified: a rule must not
INVENT a content word absent from the input, and must not SHRINK the content-word
multiset. They caught the experiment's own opt-in rule inventing `8`, which is
the only reason to trust them here.
"""

from __future__ import annotations

import re

import pytest

from amanuensis.config import PostprocessConfig
from amanuensis.models.session import DictationSession
from amanuensis.postprocess.base import TextPostProcessor, TracedPostProcessor
from amanuensis.postprocess.rules import RuleBasedPostProcessor

# The experiment's closed-class list, so "content word" means here what it meant
# there. A check whose definition drifted from the one that produced the 0/6
# would not be comparable to it.
_FUNCTION_WORDS = frozenset(
    """a an the and or but if then than that this these those of in on at to from by
    for with without about into over under again further is are was were be been being
    am do does did doing have has had having i you he she it we they me him her us them
    my your his its our their as so not no nor too very can will just should now s t
    don t ll re ve m d o""".split()
)


def _content_words(text: str) -> list[str]:
    bare = [re.sub(r"[^\w%]", "", token).lower() for token in text.split()]
    return sorted(word for word in bare if word and word not in _FUNCTION_WORDS)


def _session() -> DictationSession:
    from datetime import UTC, datetime

    return DictationSession(
        id="pp-1",
        started_at=datetime(2026, 8, 8, tzinfo=UTC),
        audio=None,
        sample_rate=16000,
    )


def _processor(**overrides: object) -> RuleBasedPostProcessor:
    config = PostprocessConfig(**overrides)  # type: ignore[arg-type]
    return RuleBasedPostProcessor(config)


# ---------------------------------------------------------------------------
# What it does
# ---------------------------------------------------------------------------


def test_it_is_a_text_post_processor() -> None:
    assert isinstance(_processor(), TextPostProcessor)
    assert _processor().name == "rules"


def test_leading_whitespace_goes() -> None:
    """10 of 10 takes carried it (docs/gates/phase5-disfluency.md).

    The highest-frequency defect the rules pass addresses, and the only rule in
    the set with a genuinely empty failure set.
    """
    assert _processor().process("   hello there.", _session()) == "Hello there."


def test_a_missing_terminal_stop_is_added() -> None:
    """7 of 10 transcripts ended without one. Engines truncate the final mark
    when the audio ends on the last syllable."""
    assert _processor().process("that is the hard part", _session()) == (
        "That is the hard part."
    )


def test_an_existing_terminal_mark_is_left_alone() -> None:
    for ending in ("done.", "done?", "done!"):
        assert _processor().process(f"it is {ending}", _session()).endswith(ending)


def test_terminal_punctuation_can_be_turned_off() -> None:
    """The rule fires on 7 of 10 dictations and appends into whatever has focus
    — a URL bar, a shell prompt, a filename field (objection O7). §5.3's rule is
    that a decision which could go either way is a key."""
    processor = _processor(terminal_punctuation=False)
    assert processor.process("cd ~/src/amanuensis", _session()) == (
        "Cd ~/src/amanuensis"
    )


def test_the_first_letter_is_capitalised() -> None:
    assert _processor().process("and requested analysis.", _session()) == (
        "And requested analysis."
    )


def test_a_stutter_is_collapsed() -> None:
    assert _processor().process("send the the file.", _session()) == ("Send the file.")


def test_a_legitimate_double_survives() -> None:
    """Without this guard the repeat rule is indefensible: `he had had enough`
    and `the food that that restaurant serves` are both correct English."""
    assert "had had" in _processor().process("he had had enough.", _session())


def test_punctuation_spacing_is_normalised() -> None:
    assert _processor().process("the file , and then this .", _session()) == (
        "The file, and then this."
    )


def test_a_decimal_and_a_filename_are_left_alone() -> None:
    """The rule only ever acts on a space that is already there, or a missing
    space after a mark followed by an *uppercase* letter. Lowercase implies an
    identifier or a decimal, not a sentence boundary."""
    out = _processor().process("open file.py and set it to 3.5.", _session())
    assert "file.py" in out
    assert "3.5" in out


# ---------------------------------------------------------------------------
# What it refuses to do — the two rules with measurements behind the refusal
# ---------------------------------------------------------------------------


def test_a_mid_sentence_capital_is_never_lowercased() -> None:
    """The rule that is not written, and three records say so.

    `04-rules-only.md` §6 implemented capitalisation as raise-only on purpose.
    `phase5-disfluency.md` measured 15 flagged capitals of which ~10 were real,
    the balance being `CDE`, `Renee` and other proper nouns. Objection O6 found
    the general case: the "same token appears lowercase elsewhere" test that
    would make the rule safe is *the definition of a homograph*.
    """
    text = "I met Mark, and he asked me to mark the invoice."
    assert _processor().process(text, _session()) == text


def test_proper_nouns_survive_a_transcript_that_also_lowercases_them() -> None:
    for text in (
        "Ask Bill about the bill.",
        "Paste it into Word, word for word.",
        "I use Slack when there is slack in the schedule.",
    ):
        assert _processor().process(text, _session()) == text


def test_spoken_numbers_are_not_converted() -> None:
    """Measured harmful: `one` is a pronoun and a determiner as often as it is a
    numeral, and no token-level rule can tell which. 2/6 INVENT, +0.97 WER."""
    text = "One thought ends and the next one starts."
    assert _processor().process(text, _session()) == text
    assert "1" not in _processor().process(text, _session())


def test_fillers_are_kept_by_default() -> None:
    """Removal is lossy and invisible — the same hazard class as the LLM pass's
    silent deletions. It also fires zero times on Whisper output."""
    text = "So um the thing is uh this."
    assert "um" in _processor().process(text, _session())


def test_fillers_go_when_the_user_asks() -> None:
    out = _processor(strip_fillers=True).process("So um the thing is.", _session())
    assert "um" not in out.split()


@pytest.mark.parametrize(
    "text",
    [
        "the small conference room is booked",
        "set the timeout to thirty seconds and retry four hundred times",
        "Ask Bill about the bill and the CDE audit",
        "  leading space and no full stop  ",
        "he had had enough of the the whole thing",
    ],
)
def test_the_default_configuration_neither_invents_nor_shrinks(text: str) -> None:
    """The experiment's two safety checks, reused unmodified.

    In the shipped configuration the only tokens the pass ever adds are a full
    stop and a capital letter, neither of which is a content word. These caught
    the experiment's own opt-in rule inventing `8`, which is why they are here
    rather than being assumed.
    """
    after = _processor().process(text, _session())
    before_words = _content_words(text)
    after_words = _content_words(after)

    assert not (
        set(after_words) - set(before_words)
    ), "the pass invented a content word"
    assert len(after_words) >= len(before_words), "the pass deleted a content word"


# ---------------------------------------------------------------------------
# Spoken commands — off, and counted anyway
# ---------------------------------------------------------------------------


def test_spoken_commands_are_off_by_default() -> None:
    """The rule deletes content words and nothing measures it — no take in
    either corpus contains one."""
    text = "First point. New paragraph. Second point."
    assert "new paragraph" in _processor().process(text, _session()).lower()


def test_spoken_commands_are_counted_even_while_disabled() -> None:
    """Otherwise the gate is rigged (choice-story #2).

    `04-rules-only.md` §7.3 asks for a fifth safety constraint — measure the
    firing rate, and if a post-processor changes nothing on real input, delete
    the code. But a rule that is off produces a firing rate of *structurally
    zero*, which reads as "harmless" to an author and "delete it" to the
    constraint. So it detects and counts always, and transforms only when
    enabled: a real measurement at zero lossiness.
    """
    processor = _processor()
    text = "First point. New paragraph. Second point."
    out, fired = processor.process_traced(text, _session())

    assert "new paragraph" in out.lower(), "it must not transform while disabled"
    assert any(
        "spoken_commands" in entry for entry in fired
    ), "a disabled rule still has to report that it would have fired"


def test_a_counted_candidate_is_not_reported_as_a_change() -> None:
    """The trace has to distinguish "fired" from "would have fired", or the gate
    reads a count of near-misses as a count of edits."""
    _, fired = _processor().process_traced("First. New paragraph. Second.", _session())
    assert "spoken_commands" not in fired
    assert "spoken_commands:candidate" in fired


def test_spoken_commands_transform_when_enabled() -> None:
    out = _processor(spoken_commands=True).process(
        "First point. New paragraph. Second point.", _session()
    )
    assert "\n\n" in out
    assert "new paragraph" not in out.lower()


def test_a_spoken_command_inside_a_sentence_is_left_alone() -> None:
    """`new paragraph` is a phrase before it is a command. The rule matches only
    when it stands alone as a sentence."""
    text = "We agreed the new paragraph structure was better."
    assert _processor(spoken_commands=True).process(text, _session()) == text


# ---------------------------------------------------------------------------
# The trace — an optional capability, not an ABC method
# ---------------------------------------------------------------------------


def test_the_processor_satisfies_the_traced_protocol() -> None:
    assert isinstance(_processor(), TracedPostProcessor)


def test_the_trace_names_the_rules_that_changed_the_text() -> None:
    """Firing counts are the only way to tell "the rule is useless" from "the
    rule is invisible to WER", and those are very different conclusions."""
    _, fired = _processor().process_traced("  that is the hard part", _session())

    assert "collapse_whitespace" in fired
    assert "ensure_terminal_punctuation" in fired
    assert "capitalise_sentences" in fired
    assert "collapse_immediate_repeats" not in fired


def test_the_trace_and_the_plain_call_agree() -> None:
    """`process` must not be a different pass from `process_traced`, or the
    firing rate the gate reports describes code the user never ran."""
    text = "  send the the file , and then this "
    session = _session()
    assert _processor().process(text, session) == (
        _processor().process_traced(text, session)[0]
    )


def test_process_does_not_mutate_the_session() -> None:
    """The ABC's contract, and the reason the trace is a return value rather
    than instance state (objection O8)."""
    session = _session()
    before = (session.raw_transcript, session.final_text, session.error)
    _processor().process("anything at all", session)
    assert (session.raw_transcript, session.final_text, session.error) == before


# ---------------------------------------------------------------------------
# Registry — config string to class, per HARNESS.md's dispatch convention
# ---------------------------------------------------------------------------


def test_the_registry_builds_the_rules_processor() -> None:
    from amanuensis.postprocess.registry import create_processor

    assert isinstance(create_processor("rules", PostprocessConfig()), TextPostProcessor)


def test_an_unknown_processor_lists_the_ones_that_exist() -> None:
    from amanuensis.postprocess.registry import create_processor

    with pytest.raises(ValueError) as excinfo:
        create_processor("spellcheck", PostprocessConfig())
    assert "rules" in str(excinfo.value)


def test_a_known_but_unbuilt_processor_says_which_phase_builds_it() -> None:
    """Same contract as `engines/registry.py`: a name the config validator
    accepts but nothing implements must name its phase rather than raising a
    lookup error the user cannot act on."""
    from amanuensis.postprocess.registry import create_processor

    with pytest.raises(ValueError) as excinfo:
        create_processor("llm", PostprocessConfig())
    assert "Phase 5" in str(excinfo.value)


def test_the_chain_is_built_in_order() -> None:
    from amanuensis.postprocess.registry import build_chain

    chain = build_chain(PostprocessConfig(chain=("rules",)))
    assert [processor.name for processor in chain] == ["rules"]


# ---------------------------------------------------------------------------
# Code review (2026-08-08): four rules that corrupted real text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "it was really really good",
        "that is so so wrong",
        "we had many many problems",
        "ok bye bye",
        "extension 4 4",
        "the score was 2 2",
    ],
)
def test_reduplication_is_not_a_stutter(text: str) -> None:
    """C1. `LEGITIMATE_DOUBLES` was a seven-word list standing against an open
    class, and English reduplication is open: really/so/many/very/bye, and every
    repeated digit.

    The rule's premise — an adjacent exact duplicate is a stutter — is what was
    wrong, not the size of the allowlist. The guard is inverted: only a
    **function word** may be collapsed, which makes the no-deleted-content-word
    property structural instead of something a test has to remember to probe.
    """
    before = _content_words(text)
    after = _content_words(_processor().process(text, _session()))
    assert len(after) >= len(before), "the pass deleted a content word"
    assert set(before) - set(after) == set()


def test_a_stuttered_function_word_still_collapses() -> None:
    """The case the rule exists for, and the only one it can now reach."""
    assert _processor().process("send the the file.", _session()) == "Send the file."


def test_a_transcript_starting_with_a_number_does_not_capitalise_a_later_word() -> None:
    """C3. `at_boundary` was only cleared by uppercasing a letter, so a leading
    digit left it set and the first *letter* got capitalised wherever it was:
    `20 minutes left` -> `20 Minutes left.`

    The rule this module argues hardest about is the one it declines to write,
    on the grounds that a spurious mid-sentence capital is a cost worth
    documenting rather than fixing badly. This rule was *creating* them.
    """
    assert _processor().process("20 minutes left", _session()) == "20 minutes left."
    assert _processor().process("15 people attended", _session()) == (
        "15 people attended."
    )


def test_a_leading_quote_still_capitalises_the_first_word() -> None:
    """The behaviour the buggy version got right, kept deliberately."""
    assert _processor().process('"hello there', _session()) == '"Hello there.'


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the U.S. economy is fine", "The U.S. economy is fine."),
        ("J.R.R. Tolkien wrote it", "J.R.R. Tolkien wrote it."),
        ("open Report.PDF now", "Open Report.PDF now."),
    ],
)
def test_acronyms_and_initials_are_not_split(text: str, expected: str) -> None:
    """C4. `([.!?])(?=[A-Z])` treated every dot-then-capital as a sentence
    boundary. It is the defect the port already found in `capitalise_sentences`
    (`file.py` -> `file.Py`) with the case flipped, and the test written for
    that one asserted only lowercase, so it could not fail here.

    Worse, it compounded: the injected `". "` created a boundary that
    `capitalise_sentences` then acted on, so `the U.S. economy` became
    `The U. S. Economy`. Two rules, one input, three corruptions.
    """
    assert _processor().process(text, _session()) == expected


def test_a_real_sentence_boundary_is_still_split() -> None:
    """The rule keeps its job: a VAD segment join really can produce this."""
    assert _processor().process("that is done.Then we ship", _session()) == (
        "That is done. Then we ship."
    )


def test_a_sentence_beginning_with_the_command_words_survives() -> None:
    """C11. The guard excluded the phrase mid-sentence and admitted it exactly
    where it was dangerous — sentence-initial, which is where a command lives
    *and* where `New line items are on order` lives.

    `Add a note. New line items are on order.` lost three words. The phrase now
    has to be a complete sentence: terminated, or at the end of the transcript.
    """
    text = "Add a note. New line items are on order."
    assert _processor(spoken_commands=True).process(text, _session()) == text


def test_a_terminated_command_still_fires() -> None:
    out = _processor(spoken_commands=True).process(
        "First point. New line. Second point.", _session()
    )
    assert "\n" in out and "new line" not in out.lower()


def test_a_command_at_the_end_of_the_transcript_fires() -> None:
    out = _processor(spoken_commands=True).process(
        "Done for now. New paragraph", _session()
    )
    assert out.endswith("\n\n") or "\n\n" in out


def test_a_candidate_is_not_counted_for_a_sentence_that_merely_starts_with_it() -> None:
    """The counter feeds the gate's firing rate (choice-story #2). A counter
    with the same false-positive population as the rule reports a rate for a
    rule more dangerous than the number suggests."""
    _, fired = _processor().process_traced(
        "Add a note. New line items are on order.", _session()
    )
    assert not any("spoken_commands" in entry for entry in fired)
