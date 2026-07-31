"""Experiment 3 — token-level keep/delete classification as the Phase 5 second pass.

Why this file exists
--------------------
The Phase 5 feasibility record (docs/gates/phase5-feasibility.md) measured a
generative LLM cleanup pass and found it made transcription 5-28x worse: it
hallucinated, it refused, it leaked chat preamble into the user's document. The
diagnosis recorded there was architectural, not a tuning problem — "it is a
*generator* being asked to perform a *deletion*, and nothing in its architecture
constrains it to that."

Token-level classification is the structural answer to that diagnosis. Instead of
generating text, the model labels each input word keep-or-delete and a
deterministic reconstruction emits the surviving words. Insertion is not
something the model is prevented from doing; it is something it has no mechanism
to do. That is the hypothesis under test.

What this script deliberately does NOT do
-----------------------------------------
It does not tune anything. There is no threshold to sweep, no prompt to iterate,
no retry. It runs the checkpoint once over a frozen fixture and reports what
happened. A negative result is the finding — see HANDOFF.md, "Sad path is a real
result."

Two design decisions worth stating
----------------------------------
1. **The "cannot hallucinate" claim is verified empirically, not asserted.**
   The checkpoint's own model card claims deletion-only by construction. The
   reconstruction step merges subword predictions back to whitespace words and
   applies two label types (KEEP_STRIP_COMMA, KEEP_CAPITALIZE) that *mutate*
   token text. Detokenisation is precisely where an "impossible" insertion
   sneaks in, so this script checks the output against the input three ways:
   a case-insensitive content-word multiset check (matching the feasibility
   record's INVENT definition), a strict verbatim-subsequence check, and a
   character-level mutation log.

2. **A fluent-input control is included.** The fixture is read prose with real
   ASR errors, not spontaneous disfluent speech — it contains no filled pauses
   at all. A keep/delete model that correctly deletes nothing on it will show
   WER unchanged, which is *correct behaviour indistinguishable from a broken
   model that always predicts KEEP*. The CONTROL_CASES below are the three
   hand-written disfluent inputs from the feasibility record; running them
   separates competence from inertia. They are a probe, not a benchmark, and
   their numbers are reported separately from the headline four.
"""

from __future__ import annotations

import argparse
import json
import statistics
import string
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import jiwer
import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "experiments" / "asr-baseline.json"

DEFAULT_CHECKPOINT = "stillerman/fdt-disfluency-distilbert-66m-v3"

# The three hand-written disfluent cases from docs/gates/phase5-feasibility.md.
# Used only as a control probe: does the tagger fire at all when there IS
# something to delete? Not scored as WER — there is no reference transcript.
CONTROL_CASES: list[tuple[str, str]] = [
    (
        "ctl-button",
        "I want the button to be, um, red, no, blue, and it should be like, "
        "on the right side of the page, or actually the left.",
    ),
    ("ctl-send", "send that to uh Josh and and copy me on it"),
    (
        "ctl-meet",
        "let's meet on Monday, sorry, Tuesday at like three, no, four o'clock",
    ),
]

# Function words are excluded from the content-word counts so that SHRINK and
# INVENT measure what the feasibility record meant by them: the words that carry
# the user's meaning. A tagger dropping "the" is a style change; a tagger
# dropping "blue" is data loss.
FUNCTION_WORDS = frozenset(
    """
    a an the and or but if then than so as of at by for from in into on onto to
    with without about above below over under again further once here there all
    any both each few more most other some such no nor not only own same too very
    is am are was were be been being have has had having do does did doing will
    would shall should can could may might must i you he she it we they me him her
    us them my your his its our their this that these those what which who whom
    """.split()
)

# Words a disfluency tagger is *supposed* to remove. Used to classify each
# deletion as "disfluency" or "content" — the distinction this experiment was
# specifically asked to report. A tagger that improves WER by deleting content
# words is worse than one that changes nothing.
DISFLUENCY_MARKERS = frozenset(
    """
    um uh erm er ah hmm mm mhm like you know i mean sort kind of actually
    basically literally right okay ok well so anyway yeah yep nah oh
    """.split()
)

PUNCT_TABLE = str.maketrans("", "", string.punctuation)

# One normalisation, used for every WER number in this script — both the
# "before" we compute ourselves and the "after". Sharing it is the point: a
# before/after comparison across different normalisations measures the
# normalisation.
WER_TRANSFORM = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ]
)


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate as a percentage, under the shared normalisation."""
    return (
        jiwer.wer(
            reference,
            hypothesis,
            reference_transform=WER_TRANSFORM,
            hypothesis_transform=WER_TRANSFORM,
        )
        * 100
    )


def normalise_word(word: str) -> str:
    return word.lower().translate(PUNCT_TABLE).strip()


def content_words(text: str) -> list[str]:
    out = []
    for raw in text.split():
        w = normalise_word(raw)
        if w and w not in FUNCTION_WORDS:
            out.append(w)
    return out


@dataclass
class Deletion:
    """One word the tagger removed, and whether it was a disfluency."""

    word: str
    index: int

    @property
    def is_disfluency(self) -> bool:
        return normalise_word(self.word) in DISFLUENCY_MARKERS

    @property
    def is_content(self) -> bool:
        w = normalise_word(self.word)
        return bool(w) and w not in FUNCTION_WORDS and w not in DISFLUENCY_MARKERS


@dataclass
class Mutation:
    """A word the reconstruction kept but altered — capitalisation or comma."""

    before: str
    after: str
    label: str


@dataclass
class Result:
    sample_id: str
    raw: str
    cleaned: str
    fixture_wer: float | None
    wer_before: float
    wer_after: float
    latency_ms: float
    deletions: list[Deletion]
    mutations: list[Mutation] = field(default_factory=list)
    labels: Counter = field(default_factory=Counter)

    # -- safety checks, defined to match docs/gates/phase5-feasibility.md ----

    @property
    def invented(self) -> list[str]:
        """Content words present in output but absent from input (multiset).

        Must be empty for the deletion-only claim to hold. Case- and
        punctuation-insensitive, matching how the feasibility record counted.
        """
        before = Counter(content_words(self.raw))
        after = Counter(content_words(self.cleaned))
        extra = after - before
        return sorted(extra.elements())

    @property
    def is_verbatim_subsequence(self) -> bool:
        """Strict check: is every output word a character-exact input word, in order?

        Stricter than `invented` — this catches KEEP_CAPITALIZE and
        KEEP_STRIP_COMMA rewriting a token, which the case-insensitive check
        forgives. Reported separately because the two claims differ.
        """
        src = self.raw.split()
        i = 0
        for word in self.cleaned.split():
            while i < len(src) and src[i] != word:
                i += 1
            if i == len(src):
                return False
            i += 1
        return True

    @property
    def shrink_pct(self) -> float:
        before = len(content_words(self.raw))
        if before == 0:
            return 0.0
        after = len(content_words(self.cleaned))
        return (before - after) / before * 100

    @property
    def violations(self) -> list[str]:
        v = []
        if self.invented:
            v.append(f"INVENT({len(self.invented)})")
        if self.shrink_pct > 25:
            v.append(f"SHRINK({self.shrink_pct:.0f}%)")
        return v


class KeepDeleteTagger:
    """Wraps the checkpoint: words in, kept words out, plus an audit trail.

    Kept deliberately thin. The interesting property of this approach is that
    the model's entire output space is a label per input word, so the class that
    turns labels into text is the only place a surprise can enter — and it is
    fifteen lines long and reviewable in full.
    """

    def __init__(self, checkpoint: str, device: str) -> None:
        self.checkpoint = checkpoint
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        self.model = AutoModelForTokenClassification.from_pretrained(checkpoint)
        self.model.eval()
        self.model.to(device)
        self.id2label = self.model.config.id2label

    def tag(self, text: str) -> tuple[str, list[Deletion], list[Mutation], Counter]:
        words = text.split()
        if not words:
            return "", [], [], Counter()

        encoded = self.tokenizer(
            words,
            is_split_into_words=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        word_ids = encoded.word_ids(0)
        encoded = {k: v.to(self.device) for k, v in encoded.items()}

        with torch.no_grad():
            logits = self.model(**encoded).logits[0]
        predictions = logits.argmax(dim=-1).tolist()

        # One label per word: the first subword decides. Later subwords of the
        # same word are ignored rather than voted on — the model was trained
        # with labels on first subwords, so anything else is our invention.
        per_word: dict[int, str] = {}
        for position, wid in enumerate(word_ids):
            if wid is not None and wid not in per_word:
                per_word[wid] = self.id2label[predictions[position]]

        kept: list[str] = []
        deletions: list[Deletion] = []
        mutations: list[Mutation] = []
        counts: Counter = Counter()

        for idx, word in enumerate(words):
            # Any word the tokenizer truncated away is KEPT. Silently dropping
            # the tail of a long utterance would be exactly the invisible data
            # loss this whole experiment exists to avoid.
            label = per_word.get(idx, "KEEP")
            counts[label] += 1

            if label == "DELETE":
                deletions.append(Deletion(word=word, index=idx))
                continue
            if label == "KEEP_STRIP_COMMA":
                new = word.rstrip(",")
                if new != word:
                    mutations.append(Mutation(word, new, label))
                kept.append(new)
                continue
            if label == "KEEP_CAPITALIZE":
                new = word[:1].upper() + word[1:]
                if new != word:
                    mutations.append(Mutation(word, new, label))
                kept.append(new)
                continue
            kept.append(word)

        return " ".join(kept), deletions, mutations, counts


def run(checkpoint: str, device: str) -> None:
    samples = json.loads(FIXTURE.read_text())

    t0 = time.perf_counter()
    tagger = KeepDeleteTagger(checkpoint, device)
    load_ms = (time.perf_counter() - t0) * 1000

    # Warm up once. On mps the first kernel launch pays compilation cost that
    # belongs to neither load nor steady-state inference.
    tagger.tag("this is a warm up sentence so the first timed call is honest")

    results: list[Result] = []
    for sample in samples:
        raw = sample["raw_asr"]
        t = time.perf_counter()
        cleaned, deletions, mutations, counts = tagger.tag(raw)
        latency_ms = (time.perf_counter() - t) * 1000

        results.append(
            Result(
                sample_id=sample["id"],
                raw=raw,
                cleaned=cleaned,
                fixture_wer=sample.get("raw_wer"),
                wer_before=wer(sample["reference"], raw),
                wer_after=wer(sample["reference"], cleaned),
                latency_ms=latency_ms,
                deletions=deletions,
                mutations=mutations,
                labels=counts,
            )
        )

    report(checkpoint, device, load_ms, results)
    control_probe(tagger)


def report(checkpoint: str, device: str, load_ms: float, results: list[Result]) -> None:
    print(f"\ncheckpoint : {checkpoint}")
    print(f"device     : {device}")
    print(f"model load : {load_ms:.0f} ms (excluded from per-sample latency)\n")

    print("--- 1. WER before -> after -------------------------------------")
    print(
        f"{'sample':<16} {'fixture':>8} {'before':>8} {'after':>8} "
        f"{'delta':>8}  drift"
    )
    for r in results:
        drift = (
            "-"
            if r.fixture_wer is None
            else ("ok" if abs(r.fixture_wer - r.wer_before) < 0.05 else "DIFFERS")
        )
        fixture = "-" if r.fixture_wer is None else f"{r.fixture_wer:.2f}"
        print(
            f"{r.sample_id:<16} {fixture:>8} {r.wer_before:>8.2f} "
            f"{r.wer_after:>8.2f} {r.wer_after - r.wer_before:>+8.2f}  {drift}"
        )
    mean_before = statistics.mean(r.wer_before for r in results)
    mean_after = statistics.mean(r.wer_after for r in results)
    mean_fixture = statistics.mean(
        r.fixture_wer for r in results if r.fixture_wer is not None
    )
    print(
        f"{'MEAN':<16} {mean_fixture:>8.2f} {mean_before:>8.2f} "
        f"{mean_after:>8.2f} {mean_after - mean_before:>+8.2f}"
    )

    print("\n--- 2. Latency (ms) --------------------------------------------")
    latencies = sorted(r.latency_ms for r in results)
    for r in results:
        print(f"{r.sample_id:<16} {r.latency_ms:>8.1f}")
    p50 = statistics.median(latencies)
    # n=6: p95 taken as the max rather than interpolated. With six points there
    # is no honest 95th percentile; the max is the defensible upper bound.
    p95 = latencies[-1]
    print(f"{'p50':<16} {p50:>8.1f}")
    print(f"{'p95 (=max, n=6)':<16} {p95:>8.1f}")

    print("\n--- 3. Safety --------------------------------------------------")
    print(
        f"{'sample':<16} {'INVENT':>7} {'SHRINK%':>8} {'verbatim':>9}  "
        f"{'violations':<14} mutations"
    )
    for r in results:
        print(
            f"{r.sample_id:<16} {len(r.invented):>7} {r.shrink_pct:>8.1f} "
            f"{str(r.is_verbatim_subsequence):>9}  "
            f"{','.join(r.violations) or '-':<14} "
            f"{len(r.mutations)}"
        )
        if r.invented:
            print(f"{'':16}   invented words: {r.invented}")
        for m in r.mutations:
            print(f"{'':16}   mutation [{m.label}]: {m.before!r} -> {m.after!r}")

    print("\n--- Deletions per sample ---------------------------------------")
    print(f"{'sample':<16} {'words':>6} {'del':>5} {'disfl':>6} {'content':>8}  detail")
    for r in results:
        n_words = len(r.raw.split())
        disfl = [d for d in r.deletions if d.is_disfluency]
        cont = [d for d in r.deletions if d.is_content]
        detail = ", ".join(f"{d.word!r}@{d.index}" for d in r.deletions) or "(none)"
        print(
            f"{r.sample_id:<16} {n_words:>6} {len(r.deletions):>5} "
            f"{len(disfl):>6} {len(cont):>8}  {detail}"
        )

    print("\n--- Label distribution -----------------------------------------")
    total: Counter = Counter()
    for r in results:
        total.update(r.labels)
    for label, n in total.most_common():
        print(f"{label:<20} {n:>5}")

    print("\n--- 4. Verdict -------------------------------------------------")
    budget_ok = p50 <= 700
    print(f"p50 {p50:.1f} ms vs budget 700 ms -> {'PASS' if budget_ok else 'FAIL'}")
    print(f"mean WER {mean_before:.2f}% -> {mean_after:.2f}%")
    n_invent = sum(1 for r in results if r.invented)
    n_shrink = sum(1 for r in results if r.shrink_pct > 25)
    print(f"INVENT violations: {n_invent}/6   SHRINK violations: {n_shrink}/6")


def control_probe(tagger: KeepDeleteTagger) -> None:
    """Does the tagger fire at all when the input IS disfluent?

    Without this, "deleted nothing" on the fixture is indistinguishable from a
    model that is broken. No WER here — these have no reference transcript.
    """
    print("\n--- Control probe: hand-written disfluent inputs ----------------")
    print("(from docs/gates/phase5-feasibility.md; no reference, not scored)\n")
    for case_id, text in CONTROL_CASES:
        cleaned, deletions, mutations, _ = tagger.tag(text)
        # Reuse the same safety checks. The fixture fires the tagger barely at
        # all, so 0 INVENT there is weak evidence; these inputs actually
        # exercise the deletion path and so test the claim harder.
        probe = Result(
            sample_id=case_id,
            raw=text,
            cleaned=cleaned,
            fixture_wer=None,
            wer_before=0.0,
            wer_after=0.0,
            latency_ms=0.0,
            deletions=deletions,
            mutations=mutations,
        )
        print(f"{case_id}")
        print(f"  in  : {text}")
        print(f"  out : {cleaned}")
        deleted = ", ".join(f"{d.word!r}" for d in deletions) or "(none)"
        print(f"  del : {len(deletions)} -> {deleted}")
        for m in mutations:
            print(f"  mut : [{m.label}] {m.before!r} -> {m.after!r}")
        print(
            f"  safe: INVENT={len(probe.invented)} {probe.invented or ''} "
            f"SHRINK={probe.shrink_pct:.1f}% "
            f"verbatim={probe.is_verbatim_subsequence}"
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", default="cpu", choices=["cpu", "mps"])
    args = parser.parse_args()
    run(args.checkpoint, args.device)


if __name__ == "__main__":
    main()
