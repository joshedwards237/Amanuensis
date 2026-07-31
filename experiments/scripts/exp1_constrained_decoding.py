"""Experiment 1 — constrained decoding as a structural no-invent guarantee.

WHY THIS EXISTS
---------------
`docs/gates/phase5-feasibility.md` measured an LLM cleanup pass (MLX,
`Llama-3.2-3B-Instruct-4bit`, directive prompt, unconstrained greedy decoding)
against real `tiny.en` output and found it made transcription 5-28x worse: mean
WER 19.6% -> 110.0%. The diagnosis in that record is architectural, not a
prompting complaint:

    "it is a *generator* being asked to perform a *deletion*, and nothing in
    its architecture constrains it to that."

This script tests the first of the four remedies that record proposed:
restrict the decoder's output to a **subsequence of the input token sequence**,
so insertion is structurally impossible rather than checked after the fact.

WHAT IS HELD CONSTANT
---------------------
Same model (`mlx-community/Llama-3.2-3B-Instruct-4bit`), same framework (MLX),
same greedy decoding (temp 0), same frozen fixture. The *only* thing that
changes versus the failed run is the set of tokens the decoder is permitted to
emit at each step. If results differ, the constraint is the cause.

THE CONSTRAINT — a subsequence automaton
----------------------------------------
The raw ASR text is tokenised once into `src`, a list of N token ids. Decoding
carries a pointer `i` into `src`, initially 0. At each step:

  * the permitted token set is `{src[j] for j >= i} u {eos}` — every token
    still available further along the input, plus the option to stop;
  * the model's logits are gathered down to just those candidates and argmax
    is taken over that small set;
  * emitting token `t` advances `i` to `first j >= i where src[j] == t`, plus
    one.

Greedy leftmost matching is complete for subsequence recognition, so this
accepts exactly the set of subsequences of `src` and nothing else. Two
consequences worth naming because they are the point of the experiment:

  1. The output cannot contain a token absent from the input. A chat preamble
     ("Here is the cleaned text:") is not merely unlikely, it is unreachable.
  2. Output length is bounded above by input length. The 2,201 ms tail in the
     feasibility record came from the model generating *more* than it was
     given; that is now impossible.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No prompt iteration. The feasibility record was un-deferred on three
hand-written cases that passed and killed the same day when measured on real
data (see REFLECTION_LOG). This script runs once, on frozen input, and reports
what happened. A negative result is the deliverable.

It also does not attempt a second candidate model, a beam search, or a
constrained-plus-fallback hybrid. Those are separate experiments; mixing them
in would make the number uninterpretable.

KNOWN LEAK IN THE GUARANTEE
---------------------------
Subsequence-of-*tokens* is not subsequence-of-*words*. BPE splits rare words
across several tokens ("aminesis" -> "amin" + "esis"); dropping a leading
subtoken while keeping a trailing one yields a word fragment that never
appeared in the input. The INVENT check below is run empirically rather than
asserted precisely so this leak, if it fires, shows up as a number.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import jiwer
import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "experiments" / "asr-baseline.json"
MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

# --------------------------------------------------------------------------
# Normalisation — lifted verbatim from scripts/bench_engines.py
# --------------------------------------------------------------------------
# Reused rather than reimplemented so the "before" WER this script computes is
# comparable to the fixture's `raw_wer` field, which came from that benchmark.
# Apostrophes are deleted rather than spaced so "don't" stays one token.

_APOSTROPHES = "'‘’ʼʻ`"


def normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, collapse whitespace, return words."""
    text = unicodedata.normalize("NFKC", text).lower()
    out_chars: list[str] = []
    for char in text:
        if char in _APOSTROPHES:
            continue
        if unicodedata.category(char).startswith("P") or unicodedata.category(char) == "Sm":
            out_chars.append(" ")
        else:
            out_chars.append(char)
    return "".join(out_chars).split()


# The two safety checks the feasibility record used. "Content word" is defined
# here rather than inherited, because the script that produced that record was
# never committed — so this definition is stated explicitly and applied
# identically to input and output.
_STOPWORDS = frozenset(
    """
    a an the and or but so if then than that this these those there here
    is are was were be been being am do does did doing have has had having
    i me my we us our you your he him his she her it its they them their
    to of in on at by for with from as into about over under up down out
    off no not nor too very can will just should now would could may might
    what which who whom when where why how all any both each few more most
    other some such only own same s t
    """.split()
)


def content_words(text: str) -> list[str]:
    return [w for w in normalise(text) if w not in _STOPWORDS]


def wer(reference: str, hypothesis: str) -> float:
    """WER over the normalised token streams, via jiwer."""
    ref = " ".join(normalise(reference))
    hyp = " ".join(normalise(hypothesis))
    if not ref:
        return 0.0
    if not hyp:
        return 1.0
    return float(jiwer.wer(ref, hyp))


# --------------------------------------------------------------------------
# The subsequence automaton
# --------------------------------------------------------------------------


class SubsequenceConstraint:
    """Accepts exactly the subsequences of a fixed token sequence.

    Held as a class rather than a closure because the decode loop needs both
    the candidate set (to mask logits) and the transition (to advance), and
    keeping the pointer in one place makes the invariant checkable.
    """

    def __init__(self, src: list[int], eos_ids: set[int]) -> None:
        self.src = src
        self.eos = sorted(eos_ids)[0]
        self.pos = 0

        # allowed[i] = distinct ids in src[i:], plus eos. Built from the right
        # so the whole table costs one pass rather than a scan per position.
        n = len(src)
        self._allowed: list[list[int]] = [[] for _ in range(n + 1)]
        seen: set[int] = set()
        acc: list[int] = [self.eos]
        self._allowed[n] = list(acc)
        for i in range(n - 1, -1, -1):
            if src[i] not in seen:
                seen.add(src[i])
                acc.append(src[i])
            self._allowed[i] = list(acc)

        # id -> ascending positions, for the leftmost-match transition.
        self._where: dict[int, list[int]] = {}
        for i, tok in enumerate(src):
            self._where.setdefault(tok, []).append(i)

    def candidates(self) -> list[int]:
        return self._allowed[self.pos]

    def advance(self, token: int) -> None:
        positions = self._where.get(token)
        if positions is None:
            raise AssertionError(f"token {token} is not in the source sequence")
        idx = bisect.bisect_left(positions, self.pos)
        if idx >= len(positions):
            raise AssertionError(f"token {token} has no occurrence at or after {self.pos}")
        self.pos = positions[idx] + 1

    @property
    def exhausted(self) -> bool:
        return self.pos >= len(self.src)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

# Directive, but stripped of everything the constraint already enforces. The
# model is not told to "output only the text" because it cannot do otherwise;
# it is told what to delete, which is the only decision left to it.
SYSTEM = (
    "You clean up dictated speech. You may ONLY delete words from the "
    "transcript. You may not add, reorder, or reword anything. Delete filler "
    "words and stutters. Where the speaker corrects themselves, delete the "
    "abandoned words and keep the correction. If nothing needs deleting, "
    "repeat the transcript unchanged."
)


@dataclass
class Generation:
    text: str
    tokens_emitted: int
    src_tokens: int
    latency_ms: float
    stopped_early: bool
    steps: list[int] = field(default_factory=list)


def clean(model, tokenizer, raw: str) -> Generation:
    started = time.perf_counter()

    src = tokenizer._tokenizer.encode(raw, add_special_tokens=False)
    eos_ids = set(tokenizer.eos_token_ids or {tokenizer.eos_token_id})
    constraint = SubsequenceConstraint(src, eos_ids)

    prompt_ids = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": raw},
        ],
        add_generation_prompt=True,
    )

    cache = make_prompt_cache(model)
    logits = model(mx.array(prompt_ids)[None], cache=cache)[:, -1, :]

    emitted: list[int] = []
    stopped_early = False
    # A subsequence cannot be longer than its source; this bound is structural,
    # not a safety valve, and it is the reason the runaway-generation tail in
    # the feasibility record cannot recur.
    for _ in range(len(src) + 1):
        cand = constraint.candidates()
        cand_arr = mx.array(cand)
        sub = mx.take(logits[0], cand_arr)
        choice = cand[int(mx.argmax(sub).item())]
        if choice == constraint.eos:
            stopped_early = not constraint.exhausted
            break
        emitted.append(choice)
        constraint.advance(choice)
        logits = model(mx.array([[choice]]), cache=cache)[:, -1, :]
    mx.eval(logits)

    text = tokenizer.decode(emitted).strip()
    return Generation(
        text=text,
        tokens_emitted=len(emitted),
        src_tokens=len(src),
        latency_ms=(time.perf_counter() - started) * 1000.0,
        stopped_early=stopped_early,
        steps=emitted,
    )


# --------------------------------------------------------------------------
# Safety checks (feasibility record, "What a shippable design has to include")
# --------------------------------------------------------------------------


@dataclass
class Safety:
    invented: int
    invented_words: list[str]
    shrink_pct: float
    in_content: int
    out_content: int

    @property
    def invent_violation(self) -> bool:
        return self.invented > 0

    @property
    def shrink_violation(self) -> bool:
        return self.shrink_pct > 25.0


def check(raw: str, cleaned: str) -> Safety:
    src = Counter(content_words(raw))
    out = Counter(content_words(cleaned))
    invented = {w: c - src.get(w, 0) for w, c in out.items() if c > src.get(w, 0)}
    n_in = sum(src.values())
    n_out = sum(out.values())
    shrink = 0.0 if n_in == 0 else max(0.0, (n_in - n_out) / n_in * 100.0)
    return Safety(
        invented=sum(invented.values()),
        invented_words=sorted(invented),
        shrink_pct=shrink,
        in_content=n_in,
        out_content=n_out,
    )


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    samples = json.loads(FIXTURE.read_text())

    load_started = time.perf_counter()
    model, tokenizer = load(MODEL)
    load_ms = (time.perf_counter() - load_started) * 1000.0

    # Warm-up: first call pays Metal kernel compilation. Discarded.
    warm = clean(model, tokenizer, samples[0]["raw_asr"])
    print(f"model load {load_ms:.0f} ms | warm-up {warm.latency_ms:.0f} ms (discarded)\n")

    rows = []
    for s in samples:
        gen = clean(model, tokenizer, s["raw_asr"])
        safety = check(s["raw_asr"], gen.text)
        before = wer(s["reference"], s["raw_asr"]) * 100
        after = wer(s["reference"], gen.text) * 100
        rows.append(
            {
                "id": s["id"],
                "wer_before": before,
                "wer_before_fixture": s["raw_wer"],
                "wer_after": after,
                "latency_ms": gen.latency_ms,
                "src_tokens": gen.src_tokens,
                "emitted_tokens": gen.tokens_emitted,
                "stopped_early": gen.stopped_early,
                "invented": safety.invented,
                "invented_words": safety.invented_words,
                "shrink_pct": safety.shrink_pct,
                "in_content": safety.in_content,
                "out_content": safety.out_content,
                "raw": s["raw_asr"],
                "cleaned": gen.text,
                "is_identity": gen.text.strip() == s["raw_asr"].strip(),
            }
        )
        flag = ""
        if safety.invent_violation:
            flag += f" INVENT({safety.invented})"
        if safety.shrink_violation:
            flag += f" SHRINK({safety.shrink_pct:.0f}%)"
        print(
            f"{s['id']:<18} WER {before:6.2f}% -> {after:6.2f}%  "
            f"{gen.latency_ms:7.0f} ms  {gen.tokens_emitted:3d}/{gen.src_tokens:3d} tok"
            f"{flag}"
        )
        print(f"    {gen.text}")

    lat = sorted(r["latency_ms"] for r in rows)
    p50 = statistics.median(lat)
    p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
    mean_before = statistics.mean(r["wer_before"] for r in rows)
    mean_after = statistics.mean(r["wer_after"] for r in rows)

    print(
        f"\nmean WER {mean_before:.2f}% -> {mean_after:.2f}%   "
        f"p50 {p50:.0f} ms  p95 {p95:.0f} ms  "
        f"(fixture mean_before {statistics.mean(r['wer_before_fixture'] for r in rows):.2f}%)"
    )
    print(f"identity outputs: {sum(r['is_identity'] for r in rows)}/{len(rows)}")
    print(f"total INVENT words: {sum(r['invented'] for r in rows)}")
    print("VERDICT vs p50 <= 700 ms:", "PASS" if p50 <= 700 else "FAIL")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                {
                    "model": MODEL,
                    "load_ms": load_ms,
                    "warmup_ms": warm.latency_ms,
                    "p50_ms": p50,
                    "p95_ms": p95,
                    "mean_wer_before": mean_before,
                    "mean_wer_after": mean_after,
                    "samples": rows,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
