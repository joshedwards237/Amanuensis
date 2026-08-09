"""Deterministic post-processing. The rules, and the rules deliberately absent.

**This is ported, not designed.** `experiments/scripts/exp4_rules_only.py`
implemented this pass and `experiments/results/04-rules-only.md` measured it
against the Phase 1 corpus on 2026-07-31. Porting rather than rewriting is the
point: the numbers below describe *this* code, and a reimplementation would
inherit the conclusions without inheriting the measurements.

| | measured |
|---|---|
| Latency | p50 **0.0445 ms**, p95 **0.0505 ms** |
| WER movement | **+0.00**; strict WER 24.66 -> **24.32** |
| Safety | **0/6 INVENT**, **0/6 SHRINK** in the shipping configuration |

The WER result is worth reading correctly. Standard WER normalisation lowercases
and strips punctuation, which makes three of these rules *structurally incapable*
of moving the number — they cannot help and cannot hurt. That is a property of
the metric, not of the rules. A user does not experience it that way: a missing
full stop costs them the same keystroke as a wrong word, and strict WER (case and
punctuation retained) is where the only real movement showed up.

Rule order is fixed and significant. **Deletion rules run before orthography
rules**, because deleting a token can create a ` ,` join or expose a new
sentence-initial word, and running orthography first would miss it.

Two rules are deliberately not here
-----------------------------------
**Lowercasing a spurious mid-sentence capital.** Three records reject it
independently. The experiment: "a mid-sentence capital is indistinguishable from
a proper noun without a model, and destroying proper nouns is a worse failure
than leaving a stray capital." `docs/gates/phase5-disfluency.md`: 15 capitals
flagged, ~10 real, the balance being `CDE`, `Renee` and other proper nouns — a
naive flagger is wrong about a third of what it touches, in the corpus region
with the worst WER. And this phase's objection O6 found the general case: the
"same token appears lowercase elsewhere" test that would make the rule safe is
*the definition of a homograph*. `Ask Bill about the bill.` PRD §7.3's standing
finding is that silent heuristic rewriting of the user's words is the hazard;
doing it from inside the product is worse than suffering it from macOS, because
§7.3's excuse — that Amanuensis cannot reach another application's settings —
does not apply to Amanuensis.

**Folding spoken numbers into digits.** Measured harmful on the first real corpus
it met: `one thought ends and the next one starts` became `1 thought ends and the
next 1 starts`. Two INVENT violations across 2 of 6 samples, +0.97 mean WER.
`one` is a pronoun and a determiner as often as it is a numeral, and no
token-level rule can tell which. It needs a part-of-speech guard; there is no
tagger in this product.

One defect found in the port
----------------------------
`capitalise_sentences` treated any `.` as a sentence boundary, so `open file.py`
became `open file.Py`. The experiment's corpus never contained a `.` followed
immediately by a letter inside a token *and* a following word, so it could not
show. A terminator only opens a boundary when whitespace or end-of-string
follows it — which is the same reasoning `normalise_punctuation_spacing` already
used for the inverse case, and was simply not applied here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from amanuensis.config import PostprocessConfig
from amanuensis.models.session import DictationSession
from amanuensis.postprocess.base import TextPostProcessor

__all__ = ["RuleBasedPostProcessor"]

#: Standalone filler tokens. `like`, `you know` and `I mean` are excluded: they
#: are legitimate content in some contexts, and removing them is a semantic
#: judgement rather than a rule.
FILLERS: Final = frozenset(
    {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm", "mmm"}
)

#: Words that legitimately double in English. Without this guard the
#: repeat-collapse rule corrupts real sentences — "he had had enough", "the food
#: that that restaurant serves". The guard is what makes the rule defensible at
#: all, and the residual risk is a rare repeated proper noun.
LEGITIMATE_DOUBLES: Final = frozenset({"had", "that", "is", "who", "no", "very", "ha"})

_TERMINAL_CHARS: Final = ".!?"

#: Spoken commands, and the shape they must have to count as one. The phrase
#: only counts at the start of the transcript or immediately after a sentence
#: terminator — `we agreed the new paragraph structure was better` must survive
#: untouched, because `new paragraph` is a phrase before it is a command.
_COMMANDS: Final[dict[str, str]] = {
    "new paragraph": "\n\n",
    "new line": "\n",
}
_COMMAND_RE: Final = re.compile(
    r"(?:^|(?<=[.!?]))\s*(" + "|".join(_COMMANDS) + r")\s*[.!?]?\s*",
    re.IGNORECASE,
)

#: Suffix marking a rule that matched but was not allowed to act. Reported
#: separately from a real firing so a gate record cannot read a count of
#: near-misses as a count of edits.
CANDIDATE_SUFFIX: Final = ":candidate"


def _bare(word: str) -> str:
    """Lowercase, punctuation-stripped comparison form of a token."""
    return re.sub(r"[^\w%]", "", word).lower()


def collapse_whitespace(text: str) -> str:
    """Runs of whitespace become one space; leading and trailing whitespace goes.

    The highest-frequency defect the pass addresses — **leading whitespace on
    10 of 10 takes** — and the only rule here with a genuinely empty failure
    set. No dictated text wants a double space or a trailing newline at the
    cursor.
    """
    return " ".join(text.split())


def normalise_punctuation_spacing(text: str) -> str:
    """No space before `,.!?;:`; exactly one space after.

    Engines concatenating VAD segments emit ` .` and `word,word` at a join, and
    both are unambiguously wrong in English prose. Deliberately blind to `.`
    inside a token: it only ever acts on a space that is already there, or on a
    missing space after a mark followed by an *uppercase* letter. Lowercase
    implies an identifier or a decimal — `file.py`, `3.5` — not a boundary.
    """
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", text)
    return re.sub(r"([.!?])(?=[A-Z])", r"\1 ", text)


def strip_fillers(text: str) -> str:
    """Remove standalone filler tokens. Opt-in, and it fires on nothing here.

    Fillers carry no propositional content and users delete them by hand. But
    removal is lossy and *invisible* — the same hazard class as the LLM pass's
    silent deletions — which is why §5.3 defaults it off. On Whisper output it
    is also inert: the decoder removes filled pauses before any post-processor
    sees the text (0 in 403 words, three model sizes).
    """
    return " ".join(word for word in text.split() if _bare(word) not in FILLERS)


def collapse_immediate_repeats(text: str) -> str:
    """Collapse an exact adjacent duplicate token (`the the` -> `the`).

    A stutter reproduced verbatim by the engine is an artefact of speech
    production, not of intent. Three conditions, and **two of them were added
    here after the port destroyed a proper noun**:

    1. `LEGITIMATE_DOUBLES` — a handful of English words genuinely double
       (`he had had enough`, `the food that that restaurant serves`). Without
       this the rule is indefensible; the experiment had it.

    2. **The earlier token must not carry trailing punctuation.** `Paste it into
       Word, word for word.` is not a stutter — a comma separates two different
       words — and the experiment's punctuation-insensitive comparison collapsed
       it to `Paste it into word for word.`, deleting the proper noun and
       keeping the common one.

    3. **The two must match in case.** A decoder repeating itself emits the same
       surface form both times, so a case difference is evidence of two
       different words rather than one said twice. `Word`/`word`, `Mark`/`mark`,
       `Bill`/`bill`.

    Conditions 2 and 3 put this rule in the same hazard class as the one this
    module deliberately does *not* implement: silently rewriting a proper noun
    into its lowercase homograph. That the risk arrived through the *repeat*
    rule rather than the capitalisation rule is the useful part — the module
    docstring argues at length about a rule it declines to write, and the
    danger was already present in a rule it inherited without re-examining.

    The surviving token keeps the *later* surface form, which is the one
    carrying any sentence punctuation.
    """
    out: list[str] = []
    for word in text.split():
        bare = _bare(word)
        previous = out[-1] if out else ""
        is_repeat = (
            bool(out)
            and bool(bare)
            and bare == _bare(previous)
            and bare not in LEGITIMATE_DOUBLES
            # Condition 2: a boundary mark on the first token means these are
            # two words with punctuation between them, not one word twice.
            and not re.search(r"[^\w%]$", previous)
            # Condition 3: same word, same casing — or it is not a repetition.
            and previous.rstrip(".,!?;:") == word.rstrip(".,!?;:")
        )
        if is_repeat:
            out[-1] = word
            continue
        out.append(word)
    return " ".join(out)


def capitalise_sentences(text: str) -> str:
    """Uppercase the first letter of the text and of each sentence after `.!?`.

    **Note the asymmetry: this rule only ever raises case.** It never lowercases,
    because a mid-sentence capital is indistinguishable from a proper noun
    without a model, and destroying proper nouns is the worse failure. See the
    module docstring for the three records that settled this.

    A terminator opens a boundary only when whitespace or end-of-string follows
    it. Without that clause `open file.py` becomes `open file.Py` — the defect
    found while porting, which the experiment's corpus could not reveal.
    """
    if not text:
        return text
    chars = list(text)
    at_boundary = True
    for index, char in enumerate(chars):
        if at_boundary and char.isalpha():
            chars[index] = char.upper()
            at_boundary = False
        elif char in _TERMINAL_CHARS:
            following = chars[index + 1] if index + 1 < len(chars) else " "
            at_boundary = following.isspace()
    return "".join(chars)


def ensure_terminal_punctuation(text: str) -> str:
    """Append `.` when the text ends on an alphanumeric character.

    An utterance is a complete thought and the user is about to type after it.
    Engines truncate the final mark when the audio ends on the last syllable.
    The rule adds one character and is trivially undoable, which is the right
    side of the lossy/lossless line — but it fires on **7 of 10** transcripts
    and appends into whatever has focus, so it is behind a key (objection O7).
    """
    return text + "." if text and text[-1].isalnum() else text


def apply_spoken_commands(text: str) -> str:
    """`new paragraph` -> a blank line, when the phrase stands alone.

    The one rule here that **deletes content words**, and nothing measures it —
    no take in either corpus contains a spoken command. Off by default for that
    reason; see `RuleBasedPostProcessor.process_traced` for how it is measured
    anyway.
    """
    return _COMMAND_RE.sub(lambda match: _COMMANDS[match.group(1).lower()], text)


class RuleBasedPostProcessor(TextPostProcessor):
    """The `rules` entry in `[postprocess] chain`.

    Takes the `[postprocess]` slice rather than the whole config (§6.3,
    choice-story #3), so it structurally cannot read `[injection]`.
    """

    def __init__(self, config: PostprocessConfig | None = None) -> None:
        self._config = config if config is not None else PostprocessConfig()
        rules: list[tuple[str, Callable[[str], str]]] = [
            ("collapse_whitespace", collapse_whitespace),
        ]
        if self._config.strip_fillers:
            rules.append(("strip_fillers", strip_fillers))
        rules.append(("collapse_immediate_repeats", collapse_immediate_repeats))
        # Before the orthography rules: it inserts newlines, and every rule
        # after it must be one that tolerates them. `collapse_whitespace` would
        # not, which is why it is first rather than last.
        rules.append(("spoken_commands", apply_spoken_commands))
        rules.extend(
            [
                ("normalise_punctuation_spacing", normalise_punctuation_spacing),
                ("capitalise_sentences", capitalise_sentences),
            ]
        )
        if self._config.terminal_punctuation:
            rules.append(("ensure_terminal_punctuation", ensure_terminal_punctuation))
        self._rules = tuple(rules)

    @property
    def name(self) -> str:
        return "rules"

    def process(self, text: str, session: DictationSession) -> str:
        """Delegates to `process_traced` and drops the trace.

        Deliberately one implementation rather than two loops. The alternative
        keeps a duplicate pass that can silently diverge from the traced one —
        and a firing rate measured on code the user did not run is worse than no
        firing rate. The cost is a discarded tuple, against a 44 microsecond
        budget.
        """
        return self.process_traced(text, session)[0]

    def process_traced(
        self, text: str, session: DictationSession
    ) -> tuple[str, tuple[str, ...]]:
        """Run the chain, and report what acted — including what was not allowed to.

        **A disabled rule still reports its candidates**, and that is not a
        nicety (choice-story #2). `04-rules-only.md` §7.3 asks for a fifth
        safety constraint — measure the firing rate, and if a post-processor
        changes nothing on real input, ship the no-op and delete the code. A
        rule that is off produces a firing rate of *structurally zero*, which an
        author reads as "it did no harm" and the constraint reads as "delete
        it". Neither is a measurement.

        So `spoken_commands` matches always and transforms only when enabled,
        and reports itself with `CANDIDATE_SUFFIX` when it matched without
        acting. The Phase 3 gate gets a real rate from real dictation at zero
        lossiness, which is what the constraint actually asked for.
        """
        fired: list[str] = []
        for rule_name, rule in self._rules:
            if rule_name == "spoken_commands" and not self._config.spoken_commands:
                if _COMMAND_RE.search(text):
                    fired.append(rule_name + CANDIDATE_SUFFIX)
                continue
            after = rule(text)
            if after != text:
                fired.append(rule_name)
            text = after
        return text, tuple(fired)
