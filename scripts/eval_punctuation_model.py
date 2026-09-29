"""Score a punctuation-restoration model against the operator's own corpus.

**Why this candidate and not the one already measured.** The 3B instruct pass in
`phase5-feasibility.md` took `tiny.en` from 19.6% WER to **110%**, with four
failure modes: chat preamble emitted as literal text, 93 invented words, a
refusal pasted into the user's document, and half a sentence deleted. Every one
of those is a *word-level* failure.

This model is token classification. It emits one label per sub-token that
already exists — `<NULL> <ACRONYM> . , ?` plus a capitalisation flag — and no
text at all. It cannot invent, delete, refuse or leak a preamble. The whole
failure table above is unreachable by construction rather than by prompting,
which is what `phase5-experiments.md`'s monotone ordering predicts: error rate
tracked how much freedom each mechanism had, and this has the least of any
candidate yet tried.

`1-800-BAD-CODE/punctuation_fullstop_truecase_english`, 209 MB ONNX. It runs on
`onnxruntime`, which is already installed; **it does not need torch**, which is
2 GB and is not.

Scored with `gate_phase3.classify_edits` — the product's own classifier,
imported rather than reimplemented, because a second implementation's
disagreements read as findings about the product and two of three "findings" in
one sprint were exactly that.

Three things are asserted, not assumed:

* **Token identity.** The bare word sequence must be byte-identical before and
  after. This is the invariant the instruct pass could not offer and it is
  checked on every take — the existing `INVENT`/`SHRINK` guard does not transfer,
  because a punctuation model passes a word-count check trivially while being
  completely wrong.
* **A baseline on the same corpus.** The shipped chain is scored against the
  same ground truth with the same classifier. "Better" has to mean better than
  what ships, here, not better than a figure from a corpus whose audio is gone.
* **Latency p50 and p95.** Never a mean: a p50 from one clean sample said GO
  where the p95 over real data said the opposite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gate_phase3 import classify_edits  # noqa: E402

from amanuensis.config import AppConfig  # noqa: E402
from amanuensis.models.session import DictationSession  # noqa: E402
from amanuensis.postprocess.registry import build_chain  # noqa: E402
from amanuensis.postprocess.vocabulary import VocabularyLoader  # noqa: E402

MODEL_REPO = "1-800-BAD-CODE/punctuation_fullstop_truecase_english"
#: The model has 512 positional embeddings and was trained to 256.
_MAX_TOKENS = 256
#: Context carried either side of a chunk. A boundary predicted with nothing to
#: its right is the case the model is weakest on, and chunking manufactures it.
_OVERLAP = 32
_DEFAULT_CORPUS = REPO_ROOT / "tests/fixtures/phase3"


def bare(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


class Punctuator:
    """Labels an existing word sequence. Emits no text of its own."""

    def __init__(self) -> None:
        import onnxruntime as ort
        import sentencepiece as spm
        import yaml
        from huggingface_hub import hf_hub_download

        self._sp = spm.SentencePieceProcessor()
        self._sp.Load(hf_hub_download(MODEL_REPO, "spe_32k_lc_en.model"))
        self._session = ort.InferenceSession(
            hf_hub_download(MODEL_REPO, "punct_cap_seg_en.onnx"),
            providers=["CPUExecutionProvider"],
        )
        config = yaml.safe_load(open(hf_hub_download(MODEL_REPO, "config.yaml")))
        self._post_labels = config["post_labels"]

    def __call__(self, text: str) -> str:
        words = [w for w in (bare(w) for w in text.split()) if w]
        if not words:
            return text
        runs = [self._sp.EncodeAsIds(w) or [self._sp.unk_id()] for w in words]
        tokens = [i for run in runs for i in run]

        post = np.zeros(len(tokens), dtype=np.int64)
        cap = np.zeros(len(tokens), dtype=bool)
        stride = _MAX_TOKENS - 2 - 2 * _OVERLAP
        for start in range(0, len(tokens), stride):
            lo = max(0, start - _OVERLAP)
            hi = min(len(tokens), start + stride + _OVERLAP)
            # **BOS and EOS are mandatory.** Without them every prediction is
            # off by one: the first probe emitted a spurious `.` on word one and
            # put the opening capital on word two, which reads as a mediocre
            # model rather than as a wiring bug.
            ids = [self._sp.bos_id(), *tokens[lo:hi], self._sp.eos_id()]
            out = self._session.run(None, {"input_ids": np.asarray([ids], np.int64)})
            window_post = np.asarray(out[1])[0][1:-1]
            window_cap = np.asarray(out[2])[0][1:-1, 0].astype(bool)
            keep_hi = min(hi, start + stride)
            post[start:keep_hi] = window_post[start - lo : keep_hi - lo]
            cap[start:keep_hi] = window_cap[start - lo : keep_hi - lo]
            if hi == len(tokens):
                break

        rendered: list[str] = []
        cursor = 0
        for word, run in zip(words, runs, strict=True):
            token = word.upper() if self._is_acronym(post, cursor, run) else word
            if cap[cursor] and not token.isupper():
                token = token.capitalize()
            label = self._post_labels[post[cursor + len(run) - 1]]
            if label in (".", ",", "?"):
                token += label
            rendered.append(token)
            cursor += len(run)
        return " ".join(rendered)

    def _is_acronym(self, post: Any, cursor: int, run: list[int]) -> bool:
        return bool(self._post_labels[post[cursor + len(run) - 1]] == "<ACRONYM>")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    parser.add_argument(
        "--no-chain",
        action="store_true",
        help="skip the product's rules chain after the model",
    )
    args = parser.parse_args(argv)

    out = args.corpus.expanduser().resolve() / "corpus"
    record = json.loads((out / "decode.json").read_text())

    config = AppConfig()
    chain = build_chain(config.postprocess, VocabularyLoader())
    terms = set()
    punctuator = Punctuator()

    base_edits = base_words = cand_edits = cand_words = 0
    base_classes: dict[str, int] = {}
    cand_classes: dict[str, int] = {}
    latencies: list[float] = []
    violations: list[str] = []

    print(f"{'take':30} {'words':>6} {'shipped':>9} {'candidate':>10} {'ms':>6}")
    for slug, take in sorted(record["takes"].items()):
        corrected = (out / f"{slug}.txt").read_text().strip()
        shipped = take["injected"].strip()

        started = time.perf_counter()
        candidate = punctuator(take["raw"])
        latencies.append((time.perf_counter() - started) * 1000.0)
        # Captured before the chain. **The invariant is about the model**, and
        # the chain is allowed to delete words — `strip_fillers` and
        # `collapse_immediate_repeats` both do, by design, on the shipped path
        # too. Checking after the chain charged their deletions to the model and
        # reported three violations that were the harness's own.
        model_only = candidate

        if not args.no_chain:
            # The product's own chain, after the model. `capitalise_sentences`
            # is what turns the model's "flow. but" into "flow. But" — the
            # model labels each word independently and has no rule that a word
            # after a full stop is a sentence start.
            session = DictationSession(
                id=slug,
                started_at=None,  # type: ignore[arg-type]
                audio=None,
                sample_rate=16000,
                raw_transcript=candidate,
            )
            for processor in chain:
                candidate = processor.process(candidate, session)

        # **The invariant.** Checked before the score is believed: a model that
        # changed the words would score however it liked on punctuation.
        before = [bare(w) for w in take["raw"].split() if bare(w)]
        after = [bare(w) for w in model_only.split() if bare(w)]
        if before != after:
            first = next(
                (i for i, (a, b) in enumerate(zip(before, after, strict=False)) if a != b),
                min(len(before), len(after)),
            )
            violations.append(
                f"{slug}: word sequence changed at {first} "
                f"({before[first:first+3]} -> {after[first:first+3]})"
            )

        b = classify_edits(shipped, corrected, terms)
        c = classify_edits(candidate, corrected, terms)
        base_edits += b.edits
        base_words += b.reference_words
        cand_edits += c.edits
        cand_words += c.reference_words
        for name, n in b.classes.items():
            base_classes[name] = base_classes.get(name, 0) + n
        for name, n in c.classes.items():
            cand_classes[name] = cand_classes.get(name, 0) + n
        print(
            f"{slug:30} {b.reference_words:6d} {b.rate:8.2%} {c.rate:9.2%} "
            f"{latencies[-1]:6.0f}"
        )

    print()
    if violations:
        print("!! TOKEN IDENTITY VIOLATED — the score below means nothing")
        for line in violations:
            print(f"   {line}")
        print()
    else:
        print("token identity: every take unchanged word-for-word")

    base_rate = base_edits / base_words
    cand_rate = cand_edits / cand_words
    print(f"\nshipped chain : {base_edits:4d} edits over {base_words} words "
          f"= {base_rate:.2%}")
    print(f"with the model: {cand_edits:4d} edits over {cand_words} words "
          f"= {cand_rate:.2%}")
    delta = cand_rate - base_rate
    print(f"delta         : {delta:+.2%}  "
          f"({'BETTER' if delta < 0 else 'WORSE'})")

    print("\nedits by class (shipped -> candidate):")
    for name in sorted(set(base_classes) | set(cand_classes)):
        print(f"  {name:24} {base_classes.get(name,0):4d} -> "
              f"{cand_classes.get(name,0):4d}")

    ordered = sorted(latencies)
    p50 = ordered[(len(ordered) - 1) // 2]
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    print(f"\nmodel latency : p50 {p50:.0f} ms   p95 {p95:.0f} ms   "
          f"over {len(ordered)} takes of 156-225 words")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
