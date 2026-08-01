#!/usr/bin/env python3
"""Experiment 4 — rules-only post-processing. The control.

WHY THIS EXISTS
---------------
Three sibling experiments test ML approaches to cleaning ASR output (constrained
decoding, a fine-tuned seq2seq, token-level keep/delete classification). This one
tests nothing clever at all: deterministic string rules, no model, no network, no
inference. It is the floor. Any ML approach that cannot beat this number has not
earned the milliseconds, the disk space, or the hallucination risk it brings with it.

A negative result here is a *complete* result. If rules move nothing, that is the
finding: Amanuensis is a verbatim transcriber and should say so in its README.

WHAT THIS IS NOT A THROWAWAY OF
-------------------------------
`RuleBasedPostProcessor` below is a Phase 3 deliverable (PRD §6.2, §7.5), not
scaffolding. It implements the real `TextPostProcessor.process(text, session) -> str`
contract from §6.3, and honours that contract's three obligations:

  * pure with respect to the session — it never reads or mutates `DictationSession`,
    so a chain is replayable against a stored transcript;
  * order is significant — rules run in a fixed, declared sequence;
  * total — it raises nothing, so it can never cost the transcript.

The `session` parameter is accepted and deliberately unused. That is the contract,
not an oversight.

DESIGN DECISION: every rule must be arguable in a code review
-------------------------------------------------------------
The named failure mode of this whole experiment track is tuning until the number
improves. With n=6 that is trivially easy and completely worthless. So the bar for
including a rule here is: *would you defend this rule to a reviewer who had never
seen the fixture?* A rule that fires on exactly one sample is overfitting wearing a
lab coat, and it is excluded even when it would help the score.

Two rules were considered and rejected on exactly that ground. They are documented
in `_REJECTED_RULES` below rather than silently omitted, because the temptation is
part of the finding.

DESIGN DECISION: WER is not the only axis, and it is the blinder one
--------------------------------------------------------------------
Standard WER normalisation lowercases the text and strips punctuation. Every
capitalisation and punctuation rule in this file is therefore *invisible* to WER by
construction — it cannot move the number in either direction. This is not a flaw in
the rules; it is a flaw in using WER alone to judge a dictation product, where the
difference between "the hard part" and "the hard part." is something the user has to
fix by hand. The report states both: WER effect (zero, necessarily) and firing counts
(non-zero, and user-visible).

WHAT THIS FILE DELIBERATELY DOES NOT DO
---------------------------------------
  * No self-correction resolution ("red, no, blue"). That is a semantic operation,
    it is what the LLM pass was for, and no rule can do it. Out of scope by nature.
  * No lowercasing of spurious mid-sentence capitals. Telling `... sentences Which
    means ...` from `... met Josh in July` requires knowing which token is a proper
    noun. A rule that guesses destroys proper nouns, which PRD §5.6 already flags as
    the corpus's weakest area. Documented as a known limit, not papered over.
  * No vocabulary substitution. That is `VocabularyPostProcessor` (§6.2), a separate
    processor with a user-supplied wordlist, and folding it in here would let this
    experiment claim credit for a fixture-specific dictionary.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import jiwer

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "experiments" / "asr-baseline.json"

# Repeats per sample for the latency measurement. Rules run in microseconds, so a
# single timed call measures clock resolution rather than the code.
LATENCY_REPEATS = 200

# PRD §7.5 / Phase 5 budget. Stated as the whole-pipeline p50, so the rules pass is
# compared against it net of the measured ASR cost.
BUDGET_P50_MS = 700.0
ASR_P50_MS = 328.0  # tiny.en + VAD, Phase 1 benchmark


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

# Disfluency tokens. Kept small and unambiguous on purpose: every entry here is a
# token that is *never* a word in written English, so removing it cannot destroy
# meaning. "like", "you know", "I mean" are excluded — they are all legitimate
# content in some contexts and removing them is a semantic judgement, not a rule.
FILLERS = frozenset(
    {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm", "mmm"}
)

# Words that legitimately double in English. Without this guard, collapsing adjacent
# repeats corrupts real sentences ("the food that that restaurant serves", "he had
# had enough"). The guard is the reason the rule is defensible at all.
LEGITIMATE_DOUBLES = frozenset({"had", "that", "is", "who", "no", "very", "ha"})

# Closed-class function words. Used only by the safety checks, to decide what counts
# as a "content" word — the same definition the feasibility record's INVENT/SHRINK
# checks used.
FUNCTION_WORDS = frozenset(
    """a an the and or but if then than that this these those of in on at to from by
    for with without about into over under again further is are was were be been being
    am do does did doing have has had having i you he she it we they me him her us them
    my your his its our their as so not no nor too very can will just should now s t
    don t ll re ve m d o""".split()
)

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULTIPLIERS: dict[str, int] = {"hundred": 100, "thousand": 1000, "million": 1_000_000}

_SENTENCE_END = re.compile(r"([.!?])(\s+|$)")
_TERMINAL_CHARS = ".!?"


def collapse_whitespace(text: str) -> str:
    """Runs of whitespace become one space; leading/trailing whitespace goes.

    ARGUMENT: no dictated text ever wants a double space or a trailing newline at the
    cursor. There is no input for which this rule is wrong. It is the cheapest rule
    here and the only one with a genuinely empty failure set.
    """
    return " ".join(text.split())


def normalise_punctuation_spacing(text: str) -> str:
    """No space before `,.!?;:`; exactly one space after.

    ARGUMENT: engines concatenating VAD segments can emit ` .` or `word,word` at a
    join. Both are unambiguously wrong in English prose. The rule is deliberately
    blind to `.` inside tokens with no surrounding space (`file.py`, `3.5`) because
    it only ever acts on a space that is already there, or a missing space after a
    mark followed by a letter.
    """
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", text)
    # Only split `.`/`!`/`?` from a following letter when that letter is uppercase —
    # a sentence boundary. Lowercase implies an identifier or a decimal, not prose.
    text = re.sub(r"([.!?])(?=[A-Z])", r"\1 ", text)
    return text


def strip_fillers(text: str) -> str:
    """Remove standalone filler tokens.

    ARGUMENT, AND THE ARGUMENT AGAINST: fillers carry no propositional content and
    users delete them by hand. But removal is *lossy and invisible* — the same class
    of hazard as the LLM pass's silent deletions (feasibility record). PRD §5.3 sets
    `strip_fillers = false` for that reason, and this function is only reachable when
    a user has opted in. Measured both ways in the report.
    """
    kept = [w for w in text.split() if _bare(w) not in FILLERS]
    return " ".join(kept)


def collapse_immediate_repeats(text: str) -> str:
    """Collapse an exact adjacent duplicate token (`the the` -> `the`).

    ARGUMENT: a stutter reproduced verbatim by the engine is an artefact of speech
    production, not of intent. The rule is guarded by `LEGITIMATE_DOUBLES` because a
    handful of English words genuinely double; without that guard the rule would be
    indefensible, and with it the residual risk is a rare proper-noun repetition.

    Comparison is case-insensitive and punctuation-insensitive on the *comparison*
    only; the surviving token keeps its original surface form.
    """
    words = text.split()
    out: list[str] = []
    for word in words:
        bare = _bare(word)
        if out and bare and bare == _bare(out[-1]) and bare not in LEGITIMATE_DOUBLES:
            # Keep whichever surface form carries the punctuation, i.e. the later one.
            out[-1] = word
            continue
        out.append(word)
    return " ".join(out)


def capitalise_sentences(text: str) -> str:
    """Uppercase the first letter of the text and of each sentence after `.!?`.

    ARGUMENT: sentence-initial capitalisation is a hard orthographic rule of written
    English with no exceptions a dictation tool will meet. Note the asymmetry — this
    rule only ever *raises* case. It never lowercases, because a mid-sentence capital
    is indistinguishable from a proper noun without a model, and destroying proper
    nouns is a worse failure than leaving a stray capital. See the module docstring.
    """
    if not text:
        return text
    chars = list(text)
    at_boundary = True
    for i, ch in enumerate(chars):
        if at_boundary and ch.isalpha():
            chars[i] = ch.upper()
            at_boundary = False
        elif ch in _TERMINAL_CHARS:
            at_boundary = True
    return "".join(chars)


def ensure_terminal_punctuation(text: str) -> str:
    """Append `.` when the text ends on a word character.

    ARGUMENT: an utterance is a complete thought and the user is about to type after
    it. Engines truncate the final mark when the audio ends on the last syllable —
    04-fast in this corpus does exactly that. The rule adds one character and is
    trivially undoable by the user, which is the right side of the lossy/lossless
    line.
    """
    if text and text[-1].isalnum():
        return text + "."
    return text


def spoken_to_written_numbers(text: str) -> str:
    """Fold spoken number words into digits (`four hundred` -> `400`).

    ARGUMENT: users dictating `set the timeout to thirty seconds` want `30`. This is
    the one rule here that can *insert a token absent from the input*, and the report
    counts that honestly as an INVENT rather than defining it away.

    OFF BY DEFAULT, and the reason is specific to what this corpus revealed: the
    engine already emits written form (`400`, `80%`) while the fixture's *references*
    spell numbers out. Running this rule therefore moves WER in the wrong direction
    while moving user-visible quality in the right one. That divergence is a finding,
    so the rule ships behind a flag and is measured as its own variant.
    """
    words = text.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        span, value = _match_number_span(words, i)
        if span == 0:
            out.append(words[i])
            i += 1
            continue
        # Preserve any trailing punctuation from the last token of the span.
        tail = _trailing_punct(words[i + span - 1])
        out.append(f"{value}{tail}")
        i += span
    return " ".join(out)


def _match_number_span(words: Sequence[str], start: int) -> tuple[int, int]:
    """Greedily match a spoken cardinal starting at `start`. Returns (length, value).

    Handles `four hundred`, `twenty five`, `three thousand two hundred`. Returns
    (0, 0) when the token is not a number word, which is the overwhelmingly common
    case and the reason this is cheap.
    """
    if _bare(words[start]) not in _NUMBER_WORDS:
        return 0, 0
    total = 0
    current = 0
    length = 0
    i = start
    while i < len(words):
        bare = _bare(words[i])
        if bare in _NUMBER_WORDS:
            current += _NUMBER_WORDS[bare]
        elif bare in _MULTIPLIERS and (current or total):
            mult = _MULTIPLIERS[bare]
            if mult >= 1000:
                total = (total + current) * mult
                current = 0
            else:
                current *= mult
        else:
            break
        i += 1
        length += 1
    return length, total + current


# Rules considered and NOT implemented, recorded because the temptation to write them
# is itself evidence about this fixture's size. Each would have improved the score on
# exactly one sample and generalises to nothing.
_REJECTED_RULES: dict[str, str] = {
    "near-duplicate collapse": (
        "03-proper-nouns contains `were near nerd dictation` where the reference has "
        "`were nerd dictation`. A rule collapsing phonetically-similar adjacent tokens "
        "would delete `near` and save one error. It would also delete the first half of "
        "any legitimate alliterative pair and has no principled similarity threshold. "
        "n=1. Rejected."
    ),
    "compound-identifier joining": (
        "02-code has `py test` where the reference has `pytest`. A rule joining "
        "`py`+`test` requires a dictionary of software tool names, which is "
        "`VocabularyPostProcessor`'s job (PRD §6.2) with a user-supplied wordlist — not "
        "a general rule. Implementing it here would let this experiment claim credit for "
        "a fixture-specific dictionary. n=1. Rejected."
    ),
}


@dataclass(frozen=True)
class RuleConfig:
    """Mirrors the `[postprocess]` block in PRD §5.3. Defaults match it exactly."""

    strip_fillers: bool = False
    # Not a §5.3 key. Proposed here; see `spoken_to_written_numbers` for why it is off.
    spoken_forms: bool = False


class RuleBasedPostProcessor:
    """Deterministic post-processing. Implements PRD §6.3's `TextPostProcessor`.

    Rule order is fixed and significant:

      1. whitespace          — normalise the field the later rules tokenise on
      2. fillers             — remove tokens before repeat-collapse sees them, so
                               `um um the` collapses correctly when enabled
      3. repeats             — collapse stutters
      4. spoken forms        — fold number words while still lowercase-insensitive
      5. punctuation spacing — fix joins created by the deletions above
      6. capitalisation      — after spacing, so sentence boundaries are detectable
      7. terminal mark       — last, so it is not re-processed

    Steps 5-7 must follow the deletion steps: deleting a token can create a ` ,` or
    expose a new sentence-initial word, and running orthography first would miss it.
    """

    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()
        self._rules: list[tuple[str, Callable[[str], str]]] = [
            ("collapse_whitespace", collapse_whitespace),
        ]
        if self.config.strip_fillers:
            self._rules.append(("strip_fillers", strip_fillers))
        self._rules.append(("collapse_immediate_repeats", collapse_immediate_repeats))
        if self.config.spoken_forms:
            self._rules.append(("spoken_to_written_numbers", spoken_to_written_numbers))
        self._rules.extend(
            [
                ("normalise_punctuation_spacing", normalise_punctuation_spacing),
                ("capitalise_sentences", capitalise_sentences),
                ("ensure_terminal_punctuation", ensure_terminal_punctuation),
            ]
        )

    def process(self, text: str, session: Any = None) -> str:
        """PRD §6.3 contract. `session` is accepted and unused — the contract requires
        purity with respect to it."""
        for _, rule in self._rules:
            text = rule(text)
        return text

    def process_traced(self, text: str, session: Any = None) -> tuple[str, list[str]]:
        """`process`, plus the names of the rules that actually changed the text.

        Firing counts are the only way to distinguish "the rule is useless" from "the
        rule is invisible to WER", and those are very different conclusions.
        """
        fired: list[str] = []
        for name, rule in self._rules:
            after = rule(text)
            if after != text:
                fired.append(name)
            text = after
        return text, fired


def _bare(word: str) -> str:
    """Lowercase, punctuation-stripped comparison form of a token."""
    return re.sub(r"[^\w%]", "", word).lower()


def _trailing_punct(word: str) -> str:
    match = re.search(r"[^\w]+$", word)
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# The same normalisation the fixture's `raw_wer` was produced under, verified below.
WER_TRANSFORM = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ]
)


# Case- and punctuation-sensitive scoring. `WER_TRANSFORM` lowercases and strips
# punctuation, which makes every orthographic rule in this file structurally incapable
# of moving the number. That is a property of the metric, not of the rules — and in a
# dictation tool the user has to fix a missing full stop by hand exactly as they would
# fix a wrong word. This second metric is the one those rules can move.
STRICT_TRANSFORM = jiwer.Compose(
    [
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ]
)


def wer(reference: str, hypothesis: str) -> float:
    """WER as a percentage, under `WER_TRANSFORM`."""
    out = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=WER_TRANSFORM,
        hypothesis_transform=WER_TRANSFORM,
    )
    return out.wer * 100.0


def strict_wer(reference: str, hypothesis: str) -> float:
    """WER with case and punctuation retained."""
    out = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=STRICT_TRANSFORM,
        hypothesis_transform=STRICT_TRANSFORM,
    )
    return out.wer * 100.0


def _tokens(text: str) -> list[str]:
    return WER_TRANSFORM(text)[0]


def content_words(text: str) -> list[str]:
    return [t for t in _tokens(text) if t not in FUNCTION_WORDS]


@dataclass
class SafetyResult:
    """The two deterministic checks from the feasibility record, §'What a shippable
    design has to include' constraints 2 and 3. Reused verbatim so this experiment's
    numbers are comparable with the LLM run's."""

    invented: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    shrink_pct: float = 0.0

    @property
    def invent(self) -> bool:
        return bool(self.invented)

    @property
    def shrink(self) -> bool:
        return self.shrink_pct > 25.0


def check_safety(raw: str, processed: str) -> SafetyResult:
    """INVENT: content words present in output but absent from input.
    SHRINK: >25% of input content words removed.

    Multiset semantics, so a duplicated word counts. Rules *can* trip INVENT — a
    spoken-form rule emitting `400` where the input said `four hundred` produces a
    token absent from the input. That is reported, not defined away."""
    raw_content = content_words(raw)
    out_content = content_words(processed)
    raw_pool = list(raw_content)
    invented: list[str] = []
    for word in out_content:
        if word in raw_pool:
            raw_pool.remove(word)
        else:
            invented.append(word)
    out_pool = list(out_content)
    removed: list[str] = []
    for word in raw_content:
        if word in out_pool:
            out_pool.remove(word)
        else:
            removed.append(word)
    shrink = (len(removed) / len(raw_content) * 100.0) if raw_content else 0.0
    return SafetyResult(invented=invented, removed=removed, shrink_pct=shrink)


def measure_latency_ms(proc: RuleBasedPostProcessor, text: str) -> float:
    """Median wall-clock of `LATENCY_REPEATS` calls, in milliseconds.

    Median rather than mean, and repeated rather than single-shot, because the pass
    is fast enough that a single timing measures scheduler noise. Same basis as the
    sibling experiments: `perf_counter`, warmed, median of repeats.
    """
    proc.process(text)  # warm
    samples: list[float] = []
    for _ in range(LATENCY_REPEATS):
        start = time.perf_counter()
        proc.process(text)
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples)


def percentile(values: Iterable[float], pct: float) -> float:
    """Linear-interpolation percentile. With n=6, p95 is effectively the max; stated
    plainly in the report rather than dressed up as a tail estimate."""
    data = sorted(values)
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * pct / 100.0
    low = int(pos)
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (pos - low)


# ---------------------------------------------------------------------------
# Error taxonomy — the question this experiment is uniquely placed to answer
# ---------------------------------------------------------------------------
#
# "How much of the 19.6% mean WER is even addressable by rules?" No ML experiment can
# answer this, because each of them can only report what its own model happened to
# fix. Classifying every individual word-level error answers it directly, and the
# answer bounds what ANY post-processor can achieve.

CATEGORY_DISFLUENCY = "disfluency"
CATEGORY_REFERENCE_ARTEFACT = "reference-artefact"
CATEGORY_ORTHOGRAPHY = "orthography"
CATEGORY_ASR = "asr-mistranscription"


def _spoken_written_equivalent(ref_side: Sequence[str], hyp_side: Sequence[str]) -> bool:
    """True when the two sides differ only in spoken-vs-written number form.

    This is the mechanical test for a reference artefact: the engine emitted what a
    user wants to see and the reference penalised it for that.

    `percent` and `%` are erased from both sides before comparison. That is not a
    convenience — `WER_TRANSFORM` strips `%` as punctuation, so the engine's `80%`
    arrives at the scorer as the single token `80` and can never match the
    reference's two tokens `eighty percent`. The residual mismatch is manufactured by
    the scoring normalisation, not by the engine.
    """

    def fold(side: Sequence[str]) -> str:
        text = spoken_to_written_numbers(" ".join(side))
        text = re.sub(r"\bpercent\b|%", "", text)
        return _bare(text.replace(" ", ""))

    return fold(ref_side) == fold(hyp_side)


def _merge_error_regions(alignment: Sequence[Any]) -> list[tuple[int, int, int, int]]:
    """Merge adjacent non-`equal` chunks into contiguous error regions.

    WHY THIS IS NECESSARY: jiwer reports `four hundred` -> `400` as *two* chunks — a
    substitution (`four`->`400`) and a deletion (`hundred`->nothing). Classified
    separately, neither is recognisably a number equivalence and both get charged to
    the engine. Merging first is the difference between attributing that error to
    `tiny.en` and attributing it to the reference, which is the central question this
    taxonomy exists to answer.
    """
    regions: list[tuple[int, int, int, int]] = []
    for chunk in alignment:
        if chunk.type == "equal":
            continue
        span = (
            chunk.ref_start_idx,
            chunk.ref_end_idx,
            chunk.hyp_start_idx,
            chunk.hyp_end_idx,
        )
        if regions and regions[-1][1] == span[0] and regions[-1][3] == span[2]:
            prev = regions[-1]
            regions[-1] = (prev[0], span[1], prev[2], span[3])
        else:
            regions.append(span)
    return regions


def _categorise(
    ref_side: Sequence[str], hyp_side: Sequence[str], hyp: Sequence[str], hyp_start: int
) -> str:
    """Category for one error region. Precedence order is deliberate.

      1. DISFLUENCY          — the hypothesis-side tokens are fillers, or repeat an
                               adjacent token. This is what every ML approach in the
                               track is built to remove.
      2. REFERENCE ARTEFACT  — the two sides are equivalent modulo spoken/written
                               number form. The engine is right and the reference is
                               penalising it. HANDOFF risk #7.
      3. ORTHOGRAPHY         — case or punctuation only. Cannot survive
                               `WER_TRANSFORM`, which strips both; kept so the
                               category's emptiness is a measured fact rather than an
                               assumption.
      4. ASR MISTRANSCRIPTION — everything else. The engine heard the wrong word. No
                                post-processor can recover this: the information is
                                not in the text.
    """
    if hyp_side and all(w in FILLERS for w in hyp_side):
        return CATEGORY_DISFLUENCY
    if not ref_side and _is_adjacent_repeat(hyp, hyp_start, hyp_start + len(hyp_side)):
        return CATEGORY_DISFLUENCY
    if _spoken_written_equivalent(ref_side, hyp_side):
        return CATEGORY_REFERENCE_ARTEFACT
    if " ".join(ref_side).lower() == " ".join(hyp_side).lower():
        return CATEGORY_ORTHOGRAPHY
    return CATEGORY_ASR


def classify_errors(reference: str, hypothesis: str) -> list[dict[str, Any]]:
    """Every word-level error, assigned a category.

    Two-pass, because a single pass mis-attributes mixed regions. `float sixteen` ->
    `flip 16` is one region containing one genuine mishearing (`float`/`flip`) and one
    reference artefact (`sixteen`/`16`). Charging both to the engine overstates what
    ASR got wrong; charging both to the reference overstates the artefact. So an
    equal-length substitution region that is not *wholly* one category is split and
    its word pairs are classified independently.
    """
    out = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=WER_TRANSFORM,
        hypothesis_transform=WER_TRANSFORM,
    )
    ref, hyp = out.references[0], out.hypotheses[0]
    blocks: list[dict[str, Any]] = []

    for r0, r1, h0, h1 in _merge_error_regions(out.alignments[0]):
        ref_side, hyp_side = ref[r0:r1], hyp[h0:h1]
        category = _categorise(ref_side, hyp_side, hyp, h0)

        # Split a mixed equal-length substitution into its word pairs.
        if (
            category == CATEGORY_ASR
            and len(ref_side) == len(hyp_side) > 1
            and any(
                _spoken_written_equivalent([r], [h])
                for r, h in zip(ref_side, hyp_side)
            )
        ):
            for r, h in zip(ref_side, hyp_side):
                blocks.append(
                    {
                        "ref": r,
                        "hyp": h,
                        "errors": 1,
                        "category": _categorise([r], [h], hyp, h0),
                    }
                )
            continue

        blocks.append(
            {
                "ref": " ".join(ref_side),
                "hyp": " ".join(hyp_side),
                "errors": max(len(ref_side), len(hyp_side)),
                "category": category,
            }
        )
    return blocks


def _is_adjacent_repeat(hyp: Sequence[str], start: int, end: int) -> bool:
    """An inserted span that duplicates the token immediately before or after it."""
    span = hyp[start:end]
    if not span:
        return False
    before = hyp[start - 1] if start > 0 else None
    after = hyp[end] if end < len(hyp) else None
    return all(w == before for w in span) or all(w == after for w in span)


def reference_artefact_corrected_wer(reference: str, hypothesis: str) -> float:
    """WER with spoken-form numbers folded to digits on BOTH sides.

    This is a *scoring* change, not a post-processor. It answers: what would the WER
    be if the reference did not penalise the engine for emitting `400` instead of
    `four hundred`? The gap between this and the raw WER is the size of HANDOFF
    risk #7.
    """
    ref = re.sub(r"\s+percent\b", "%", spoken_to_written_numbers(reference))
    hyp = re.sub(r"\s+percent\b", "%", spoken_to_written_numbers(hypothesis))
    return wer(ref, hyp)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_variant(samples: list[dict[str, Any]], config: RuleConfig) -> dict[str, Any]:
    proc = RuleBasedPostProcessor(config)
    rows: list[dict[str, Any]] = []
    for sample in samples:
        raw = sample["raw_asr"]
        processed, fired = proc.process_traced(raw)
        before = wer(sample["reference"], raw)
        after = wer(sample["reference"], processed)
        safety = check_safety(raw, processed)
        rows.append(
            {
                "id": sample["id"],
                "fixture_wer": sample["raw_wer"],
                "wer_before": before,
                "wer_after": after,
                "delta": after - before,
                "strict_before": strict_wer(sample["reference"], raw),
                "strict_after": strict_wer(sample["reference"], processed),
                "latency_ms": measure_latency_ms(proc, raw),
                "fired": fired,
                "invent": safety.invent,
                "invented": safety.invented,
                "shrink": safety.shrink,
                "shrink_pct": safety.shrink_pct,
                "output": processed,
                "changed": processed.strip() != raw.strip(),
            }
        )
    latencies = [r["latency_ms"] for r in rows]
    return {
        "config": config,
        "rows": rows,
        "mean_before": statistics.mean(r["wer_before"] for r in rows),
        "mean_after": statistics.mean(r["wer_after"] for r in rows),
        "mean_strict_before": statistics.mean(r["strict_before"] for r in rows),
        "mean_strict_after": statistics.mean(r["strict_after"] for r in rows),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "n_invent": sum(1 for r in rows if r["invent"]),
        "n_shrink": sum(1 for r in rows if r["shrink"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    samples = json.loads(args.fixture.read_text())

    variants = {
        "A: PRD default (strip_fillers=false)": RuleConfig(),
        "B: strip_fillers=true": RuleConfig(strip_fillers=True),
        "C: default + spoken_forms=true": RuleConfig(spoken_forms=True),
    }
    results = {name: run_variant(samples, cfg) for name, cfg in variants.items()}

    # --- taxonomy -------------------------------------------------------------
    taxonomy: dict[str, int] = {
        CATEGORY_DISFLUENCY: 0,
        CATEGORY_REFERENCE_ARTEFACT: 0,
        CATEGORY_ORTHOGRAPHY: 0,
        CATEGORY_ASR: 0,
    }
    per_sample_blocks: dict[str, list[dict[str, Any]]] = {}
    corrected: list[tuple[str, float, float]] = []
    for sample in samples:
        blocks = classify_errors(sample["reference"], sample["raw_asr"])
        per_sample_blocks[sample["id"]] = blocks
        for block in blocks:
            taxonomy[block["category"]] += block["errors"]
        corrected.append(
            (
                sample["id"],
                wer(sample["reference"], sample["raw_asr"]),
                reference_artefact_corrected_wer(sample["reference"], sample["raw_asr"]),
            )
        )
    total_errors = sum(taxonomy.values())

    if args.json:
        print(
            json.dumps(
                {
                    "variants": {
                        name: {
                            k: v
                            for k, v in res.items()
                            if k not in {"config"}
                        }
                        for name, res in results.items()
                    },
                    "taxonomy": taxonomy,
                    "total_errors": total_errors,
                    "corrected_wer": [
                        {"id": i, "raw": r, "corrected": c} for i, r, c in corrected
                    ],
                },
                indent=2,
            )
        )
        return

    # --- report ---------------------------------------------------------------
    print("=" * 78)
    print("EXPERIMENT 4 — RULES-ONLY POST-PROCESSING (CONTROL)")
    print("=" * 78)

    print("\n--- Baseline check: my WER vs the fixture's raw_wer ---")
    print(f"{'sample':<18}{'fixture':>10}{'mine':>10}{'diff':>10}")
    for row in results["A: PRD default (strip_fillers=false)"]["rows"]:
        d = row["wer_before"] - row["fixture_wer"]
        print(
            f"{row['id']:<18}{row['fixture_wer']:>10.2f}{row['wer_before']:>10.2f}"
            f"{d:>+10.2f}"
        )
    mine = results["A: PRD default (strip_fillers=false)"]["mean_before"]
    print(f"{'MEAN':<18}{19.62:>10.2f}{mine:>10.2f}{mine - 19.62:>+10.2f}")

    for name, res in results.items():
        print(f"\n--- {name} ---")
        print(
            f"{'sample':<18}{'WER before':>12}{'WER after':>12}{'delta':>9}"
            f"{'strictB':>9}{'strictA':>9}"
            f"{'ms':>9}{'INVENT':>8}{'SHRINK%':>9}  rules fired"
        )
        for row in res["rows"]:
            print(
                f"{row['id']:<18}{row['wer_before']:>12.2f}{row['wer_after']:>12.2f}"
                f"{row['delta']:>+9.2f}"
                f"{row['strict_before']:>9.2f}{row['strict_after']:>9.2f}"
                f"{row['latency_ms']:>9.4f}"
                f"{('YES' if row['invent'] else '-'):>8}{row['shrink_pct']:>9.1f}"
                f"  {', '.join(row['fired']) or '(none)'}"
            )
        print(
            f"{'MEAN':<18}{res['mean_before']:>12.2f}{res['mean_after']:>12.2f}"
            f"{res['mean_after'] - res['mean_before']:>+9.2f}"
            f"{res['mean_strict_before']:>9.2f}{res['mean_strict_after']:>9.2f}"
        )
        print(
            f"  latency p50 {res['p50_ms']:.4f} ms · p95 {res['p95_ms']:.4f} ms"
            f"  ·  INVENT {res['n_invent']}/6 · SHRINK {res['n_shrink']}/6"
        )
        for row in res["rows"]:
            if row["invented"]:
                print(f"    {row['id']} invented: {row['invented']}")

    print("\n--- Error taxonomy: what is even addressable ---")
    print(f"{'category':<26}{'errors':>8}{'share':>9}")
    for cat, n in taxonomy.items():
        print(f"{cat:<26}{n:>8}{n / total_errors * 100:>8.1f}%")
    print(f"{'TOTAL':<26}{total_errors:>8}")

    print("\n--- Per-sample error blocks ---")
    for sid, blocks in per_sample_blocks.items():
        print(f"\n  {sid}")
        for b in blocks:
            print(
                f"    [{b['category']:<20}] {b['errors']}x  "
                f"REF({b['ref'] or '-'}) -> HYP({b['hyp'] or '-'})"
            )

    print("\n--- Reference-artefact-corrected WER (numbers folded on both sides) ---")
    print(f"{'sample':<18}{'raw':>10}{'corrected':>12}{'delta':>10}")
    for sid, raw_w, corr in corrected:
        print(f"{sid:<18}{raw_w:>10.2f}{corr:>12.2f}{corr - raw_w:>+10.2f}")
    mr = statistics.mean(r for _, r, _ in corrected)
    mc = statistics.mean(c for _, _, c in corrected)
    print(f"{'MEAN':<18}{mr:>10.2f}{mc:>12.2f}{mc - mr:>+10.2f}")

    print("\n--- Verdict against the p50 <= 700 ms budget ---")
    a = results["A: PRD default (strip_fillers=false)"]
    total = ASR_P50_MS + a["p50_ms"]
    print(f"  tiny.en + VAD p50   {ASR_P50_MS:.1f} ms")
    print(f"  rules pass p50      {a['p50_ms']:.4f} ms")
    print(f"  pipeline p50        {total:.1f} ms   budget {BUDGET_P50_MS:.0f} ms")
    print(f"  => {'PASS' if total <= BUDGET_P50_MS else 'FAIL'}")

    print("\n--- Rules considered and rejected as overfitting ---")
    for name, reason in _REJECTED_RULES.items():
        print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()
