"""Experiment 2 — does a seq2seq model fine-tuned on disfluency removal beat a
general instruct model at cleaning ASR output?

WHY THIS EXISTS
---------------
`docs/gates/phase5-feasibility.md` measured a 3B general instruct model
(Llama-3.2-3B-Instruct-4bit, MLX, directive prompt) over the frozen ASR corpus
and found it made transcription 5-28x worse: mean WER 19.6% -> 110.0%. The
diagnosis recorded there is that the instrument was wrong — "a *generator* being
asked to perform a *deletion*, and nothing in its architecture constrains it to
that."

That diagnosis implies a testable alternative, listed as option 2 in the gate
record: a seq2seq model *fine-tuned* on disfluency removal. Disfluency removal
is a well-studied task with public datasets (Switchboard's disfluency
annotations; Google's DISFL-QA). The hypothesis is that a model trained for the
actual job does the job, where a model prompted into it does not.

This script tests that hypothesis and nothing else. It does not try to make it
succeed. A negative result is the deliverable.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
- It does not fine-tune anything. Out of scope for a one-shot experiment; if no
  public checkpoint fits, that absence *is* the finding.
- It does not re-run ASR. `experiments/asr-baseline.json` is frozen so that all
  four Track 2 experiments run on byte-identical input.
- It does not tune prompts/prefixes against the fixture. The prefix probe
  (`--probe`) runs on hand-written sentences that are NOT in the corpus, purely
  to confirm each checkpoint is being invoked the way its author intended.
  Tuning against the measurement set is exactly how Phase 5 got un-deferred on
  n=3 in the first place.

MEASUREMENT DECISIONS WORTH KNOWING
-----------------------------------
- Normalisation is a port of `scripts/bench_engines.py::normalise`, so the
  "before" WER computed here is directly comparable to the `raw_wer` field in
  the fixture and to every other latency/accuracy number in the project. It is
  deliberately minimal and does NOT normalise numbers (see that function's
  docstring for why that inflates absolute WER but keeps comparisons honest).
- WER itself comes from `jiwer` operating on the normalised token stream, per
  the experiment brief. The fixture's own `raw_wer` was produced by
  bench_engines' hand-rolled Levenshtein; agreement between the two is checked
  and reported rather than assumed.
- Latency excludes model load and excludes the first (warm-up) inference.
  Load time is reported separately because the daemon pays it once at start-up,
  against a different budget (NFR §8, < 15 s) than the per-utterance one.
- Safety checks reproduce the two the feasibility record used, because the whole
  point of running four experiments on one fixture is comparability:
    INVENT — content words present in the output but absent from the input.
             A seq2seq decoder can emit any token in its vocabulary, so unlike
             a keep/delete classifier it *can* invent. This check matters here.
    SHRINK — more than 25% of input content words removed.
  "Content word" needs a definition and the gate record does not give one, so
  one is fixed here explicitly (`_STOPWORDS` below) and reported alongside the
  numbers. Changing it changes the counts.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import jiwer
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "experiments" / "asr-baseline.json"

# The Phase 5 budget from PRD §7.5, restated as the number this experiment is
# graded against. The cleanup pass alone must fit alongside tiny.en's measured
# 328 ms p50; the brief grades the pass in isolation at p50 <= 700 ms.
P50_BUDGET_MS = 700.0

# Candidate checkpoints, in the order they were shortlisted. See the result file
# for the search that produced this list. `prefix` is the task prefix the
# checkpoint's author documented (T5 finetunes are prefix-sensitive; none of
# these recorded a custom prefix in `task_specific_params`, so the README is the
# only source and an empty prefix is the honest default where there is none).
CANDIDATES: list[dict[str, str]] = [
    {
        "id": "t5-base-disfluent-cleaner",
        "repo": "abdulbaseermohammedkhan/t5_disfluent_cleaner",
        "prefix": "",
        "note": "t5-base finetune; card reports exact-match 0.734, ROUGE-L 0.958",
    },
    {
        "id": "t5-small-disfluency-correction",
        "repo": "vamshi0310/finetuned-disfluency-correction",
        "prefix": "correct disfluency: ",
        "note": "t5-small finetune; card documents this exact prefix; ChrF++ 99.26",
    },
    {
        "id": "bart-base-disfl-qa",
        "repo": "Galmieux/bart_disfl_qa",
        "prefix": "",
        "note": "BART finetune on Google DISFL-QA — the canonical public dataset",
    },
    {
        "id": "t5-base-disfluent-fluent",
        "repo": "EmnaBou/t5-base-disfluent-fluent",
        "prefix": "",
        "note": "t5-base disfluent->fluent; card reports BLEU 13.8 (low for a near-copy task)",
    },
]

# Hand-written probe sentences. These are NOT corpus samples — they exist only to
# confirm a checkpoint responds to its documented invocation at all, before the
# frozen fixture is touched.
PROBE_SENTENCES = [
    "I I um want to to go to the the market",
    "send that to uh Josh and and copy me on it",
    "what is the uh no I mean what is the capital of France",
]

# Closed-class words excluded from the content-word counts the safety checks use.
# Deliberately small: the checks are meant to catch "the model invented a noun"
# and "the model deleted half the sentence", not to arbitrate function-word
# rephrasing. A larger list would make SHRINK harder to trip and INVENT quieter.
_STOPWORDS = frozenset(
    """
    a an the and or but if then than so as at by for from in into of off on onto
    out over to up with without within about after before between during under
    is are was were be been being am do does did doing done have has had having
    will would shall should can could may might must
    i me my mine you your yours he him his she her hers it its we us our ours
    they them their theirs this that these those there here
    not no nor too very just also only
    """.split()
)

_APOSTROPHES = "'‘’ʼʻ`"


def normalise(text: str) -> list[str]:
    """Port of `scripts/bench_engines.py::normalise` — kept byte-identical in
    behaviour so WER here is comparable to every other WER in this project."""
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


def wer_pct(reference: str, hypothesis: str) -> float:
    """WER as a percentage, over the normalised token stream.

    jiwer is handed pre-normalised, space-joined text and no transform, so the
    normalisation above is the only normalisation applied — no hidden second
    pass from jiwer's defaults.
    """
    ref = " ".join(normalise(reference))
    hyp = " ".join(normalise(hypothesis))
    if not ref:
        return 0.0
    if not hyp:
        return 100.0
    return jiwer.wer(ref, hyp) * 100.0


def content_words(text: str) -> list[str]:
    return [w for w in normalise(text) if w not in _STOPWORDS]


@dataclass
class Safety:
    """The two deterministic checks from the feasibility record.

    Both are *bags*, not sets: if the model emits "blue" three times and the
    input had it once, that is two invented words. Multiset accounting is what
    makes repetition-loop failures visible, and small seq2seq models loop.
    """

    invented: list[str] = field(default_factory=list)
    shrink_pct: float = 0.0
    input_content: int = 0
    output_content: int = 0

    @property
    def invent_violation(self) -> bool:
        return bool(self.invented)

    @property
    def shrink_violation(self) -> bool:
        return self.shrink_pct > 25.0

    @property
    def verdict(self) -> str:
        flags = []
        if self.invent_violation:
            flags.append(f"INVENT ({len(self.invented)})")
        if self.shrink_violation:
            flags.append(f"SHRINK ({self.shrink_pct:.0f}%)")
        return " + ".join(flags) if flags else "passed"


def check_safety(raw: str, cleaned: str) -> Safety:
    from collections import Counter

    src = Counter(content_words(raw))
    out = Counter(content_words(cleaned))
    invented = list((out - src).elements())
    n_in = sum(src.values())
    kept = sum((src & out).values())
    shrink = 0.0 if n_in == 0 else (n_in - kept) / n_in * 100.0
    return Safety(invented=invented, shrink_pct=shrink, input_content=n_in, output_content=sum(out.values()))


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile.

    With n=6 the p95 is essentially the maximum. That is stated rather than
    hidden — HANDOFF requires p50 and p95 on any latency figure, and a p95 from
    six samples is a floor on the real tail, not an estimate of it.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def pick_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    # mps is available on this hardware, but for encoder-decoder models this
    # small the kernel-launch overhead can dominate. Measured, not assumed —
    # `--device` lets both be run and compared.
    return torch.device("cpu")


def load(repo: str, device: torch.device) -> tuple[object, object, float]:
    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(repo)
    model = AutoModelForSeq2SeqLM.from_pretrained(repo)
    model.to(device)
    model.eval()
    if device.type == "mps":
        torch.mps.synchronize()
    return model, tokenizer, (time.perf_counter() - t0) * 1000.0


@torch.inference_mode()
def clean(model, tokenizer, device: torch.device, prefix: str, text: str, max_new: int) -> str:
    """One cleanup pass. Greedy decoding — beam search would be a second variable
    and the feasibility record's LLM baseline used greedy (`temp=0.0`) too."""
    enc = tokenizer(prefix + text, return_tensors="pt", truncation=True, max_length=512)
    # Two of these checkpoints were published with a BERT-style `vocab.txt`
    # tokenizer rather than a SentencePiece one, so they emit `token_type_ids`
    # that the T5 decoder rejects. Keeping only the two fields every
    # encoder-decoder accepts is safer than special-casing per checkpoint.
    enc = {k: v.to(device) for k, v in enc.items() if k in ("input_ids", "attention_mask")}
    out = model.generate(**enc, max_new_tokens=max_new, num_beams=1, do_sample=False)
    if device.type == "mps":
        torch.mps.synchronize()
    return tokenizer.decode(out[0], skip_special_tokens=True)


def run_probe(device: torch.device, max_new: int) -> None:
    """Confirm each checkpoint is invoked correctly, on non-corpus sentences."""
    for cand in CANDIDATES:
        print(f"\n===== {cand['id']}  ({cand['repo']})")
        try:
            model, tokenizer, load_ms = load(cand["repo"], device)
        except Exception as exc:  # noqa: BLE001 — a checkpoint that will not load is a result
            print(f"  LOAD FAILED: {type(exc).__name__}: {exc}")
            continue
        print(f"  load: {load_ms:.0f} ms")
        for prefix in {cand["prefix"], "", "correct disfluency: ", "disfluent to fluent: "}:
            print(f"  -- prefix={prefix!r}")
            for sent in PROBE_SENTENCES:
                print(f"     in : {sent}")
                print(f"     out: {clean(model, tokenizer, device, prefix, sent, max_new)}")
        del model


def run_measurement(device: torch.device, max_new: int, only: str | None) -> dict:
    samples = json.loads(FIXTURE.read_text())
    report: dict = {"device": str(device), "max_new_tokens": max_new, "checkpoints": []}

    # "Before" WER, computed here rather than trusted from the fixture. The
    # brief requires both ends measured with the same normalisation; agreement
    # with the fixture's `raw_wer` is then evidence the port is faithful.
    for s in samples:
        s["measured_raw_wer"] = wer_pct(s["reference"], s["raw_asr"])
    report["baseline"] = {
        "per_sample": [
            {"id": s["id"], "fixture_raw_wer": s["raw_wer"], "measured_raw_wer": round(s["measured_raw_wer"], 2)}
            for s in samples
        ],
        "mean_fixture": round(statistics.mean(s["raw_wer"] for s in samples), 2),
        "mean_measured": round(statistics.mean(s["measured_raw_wer"] for s in samples), 2),
    }

    for cand in CANDIDATES:
        if only and cand["id"] != only:
            continue
        entry: dict = {"id": cand["id"], "repo": cand["repo"], "prefix": cand["prefix"], "note": cand["note"]}
        try:
            model, tokenizer, load_ms = load(cand["repo"], device)
        except Exception as exc:  # noqa: BLE001
            entry["load_error"] = f"{type(exc).__name__}: {exc}"
            report["checkpoints"].append(entry)
            continue
        entry["load_ms"] = round(load_ms, 0)

        # Warm up once, off-corpus, so the first timed sample is not paying for
        # lazy kernel compilation.
        clean(model, tokenizer, device, cand["prefix"], PROBE_SENTENCES[0], max_new)

        rows = []
        for s in samples:
            t0 = time.perf_counter()
            cleaned = clean(model, tokenizer, device, cand["prefix"], s["raw_asr"], max_new)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            safety = check_safety(s["raw_asr"], cleaned)
            rows.append(
                {
                    "id": s["id"],
                    "cleaned": cleaned,
                    "wer_before": round(s["measured_raw_wer"], 2),
                    "wer_after": round(wer_pct(s["reference"], cleaned), 2),
                    "latency_ms": round(latency_ms, 1),
                    "invented_count": len(safety.invented),
                    "invented_words": safety.invented[:12],
                    "shrink_pct": round(safety.shrink_pct, 1),
                    "safety": safety.verdict,
                }
            )
        lat = [r["latency_ms"] for r in rows]
        entry["samples"] = rows
        entry["mean_wer_before"] = round(statistics.mean(r["wer_before"] for r in rows), 2)
        entry["mean_wer_after"] = round(statistics.mean(r["wer_after"] for r in rows), 2)
        entry["p50_ms"] = round(percentile(lat, 0.50), 1)
        entry["p95_ms"] = round(percentile(lat, 0.95), 1)
        entry["min_ms"] = round(min(lat), 1)
        entry["max_ms"] = round(max(lat), 1)
        entry["invent_violations"] = sum(1 for r in rows if r["invented_count"] > 0)
        entry["shrink_violations"] = sum(1 for r in rows if r["shrink_pct"] > 25.0)
        entry["verdict"] = "PASS" if entry["p50_ms"] <= P50_BUDGET_MS else "FAIL"
        report["checkpoints"].append(entry)
        del model

    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="prefix probe on non-corpus sentences")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps"])
    ap.add_argument("--max-new-tokens", type=int, default=200)
    ap.add_argument("--only", default=None, help="run a single checkpoint id")
    ap.add_argument("--json-out", default=None, help="write the full report as JSON")
    args = ap.parse_args()

    device = pick_device(args.device)
    torch.manual_seed(0)

    if args.probe:
        run_probe(device, args.max_new_tokens)
        return

    report = run_measurement(device, args.max_new_tokens, args.only)
    text = json.dumps(report, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
