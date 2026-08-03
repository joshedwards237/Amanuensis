# Handoff — Sprint 1 close → Sprint 2 start

> **SUPERSEDED 2026-08-02. Kept as history; do not act on it.** Everything below
> was written before Phase 0 was built. Phases 0, 1 and 2a have since closed and
> several of its assumptions are now wrong — including the engine choice, the
> `cpu_threads` reasoning, and the claim that the Phase 5 experiments would be
> decided against the existing corpus.
>
> **Current state lives in the gate records**, one per phase, in
> [`docs/gates/`](docs/gates/) — read `phase-2a.md` first, then `CLAUDE.md` for
> what is built and what is still a contract. That pairing replaced this file:
> a single rolling handoff went stale between the writing and the reading, where
> a per-gate record is dated, scoped, and never needs revising.

**Written 2026-07-31.** Sprint 1 produced a specification, not a product. Sprint 2
builds Phase 0 and resolves the Phase 5 approach.

---

## Current goal

Two tracks, independent — Phase 0 is **not blocked** by the experiments.

1. **Phase 0** (PRD §9) — scaffolding. `src/amanuensis/` per §6.4, `pyproject.toml`,
   ruff + black + mypy --strict, `load_config()`, CLI skeleton, all ABCs with **no**
   implementations, `platformdirs`, `hotkey/factory.py`.
2. **Four Phase 5 experiments** — decide what the LLM second pass should be, or whether
   it should exist. All four run against a frozen fixture; see below.

They do not interact. Every candidate approach satisfies the same
`TextPostProcessor.process(text, session) -> str` signature, so §6.3's contract is safe
to freeze now.

---

## State: what is measured and holding

| Fact | Value | Source |
|---|---|---|
| ASR engine meeting G1 | `tiny.en` + VAD, **p50 328 ms / p95 420 ms** | Phase 1 benchmark |
| VAD is mandatory, not optional | `base.en` 6,039 → **541 ms**; `small.en` 23,886 → 1,438 ms | probe + benchmark |
| `cpu_threads` | 10 (performance cores). Library default of 4 costs **1.8×** | probe |
| Cold start, both models resident | **3.43 s** vs a < 15 s NFR | feasibility record |
| LLM cleanup as scoped | **Fails.** WER 19.6% → 110% on real ASR output | feasibility record |
| Safety constraints | Caught **100%** of catastrophic failures | feasibility record |

Records: `docs/gates/probe.md`, `docs/gates/phase5-feasibility.md`.

## State: adjudication

**32/32 dispositions resolved** — 12 objections, 13 choice stories, 7 slices. Index is
generated (`scripts/regenerate-sentinel-index.py`, CI-checked).

**Gap:** the 2026-07-31 amendments — the tier redefinition, `tiny.en`'s selection, the
five probe amendments, un-deferring then killing Phase 5 — have had **no independent
adversarial review**. Three `advocatus-diaboli` spawns failed to deliver (six idle
notifications, zero records). **Run `/diaboli` in a fresh session before Phase 0
hardens.** See the memory note `advocatus-diaboli-agents-fail-to-deliver`.

---

## Track 1 — Phase 0

**Deliverables** (PRD §9, plus the portability floor from §7.3):

- `src/amanuensis/` exactly per §6.4 — do not add a top-level package without amending it
- `pyproject.toml`, PEP 621; ruff + black + mypy `--strict`
- `load_config() -> AppConfig`, **frozen dataclass**. No singleton, no `.get()`
- CLI skeleton — `manu daemon | toggle | status | history`
- All ABCs, no implementations, classified per §6.3's three-rule table
- Paths via `platformdirs` — **not** hardcoded XDG
- `hotkey/factory.py` alongside `injection/factory.py`
- `cpu_threads = "auto"` resolving to performance-core count

**Gate — Rejects if:** `manu --help` fails, `mypy --strict src/` is unclean, a malformed
config is not rejected with a useful error, a config/history path is hardcoded, or
`config.py` exposes a module-level instance or ambient accessor.

Writes `docs/gates/phase-0.md`.

**Do not** implement engines, injection, hotkey listening, or post-processing. Phase 0 is
contracts and toolchain only.

---

## Track 2 — the four experiments

**Fixture:** `experiments/asr-baseline.json` — six samples, `tiny.en` + VAD transcripts,
references, raw WER (mean **19.62%**). Frozen deliberately: every approach must run on
identical input or it measures ASR variance alongside the thing under test. Committed,
text only, no audio.

**The four** (from `docs/gates/phase5-feasibility.md`):

| # | Approach | Hypothesis |
|---|---|---|
| 1 | **Constrained decoding** — restrict output to a subsequence of the input | Insertion becomes structurally impossible, not merely checked |
| 2 | **Fine-tuned seq2seq** — a disfluency-removal model | Trained for the actual task; public datasets exist |
| 3 | **Token-level keep/delete classification** | Cannot hallucinate. Loses self-correction resolution |
| 4 | **Rules-only** — the control | Establishes what deterministic processing alone achieves |

**Every experiment reports the same four numbers**, or it is not comparable:
WER before → after (per sample and mean) · latency per sample · safety violations
(invented words, shrink %) · verdict against the p50 ≤ 700 ms budget.

**Operational constraints — these matter:**

- **No worktree isolation.** The corpus `.wav` files are gitignored; a worktree would not
  have them. Agents work in the main checkout, **read-only** on everything except their
  own result file.
- **Each agent gets its own venv.** Concurrent `pip install` into the shared `.venv`
  collides.
- **Do not modify** `AMANUENSIS_PRD.md`, `HARNESS.md`, the corpus, `.venv/`, or another
  agent's output.
- **Sad path is a real result.** "This approach does not work, here is the evidence" is
  the finding. Do not tune a prompt until it passes — that is how Phase 5 got un-deferred
  on n=3 in the first place.

---

## Known risks and open questions

1. **`tiny.en` is the only model meeting G1 and has the worst WER (14.8%).** All five
   candidates are statistically indistinguishable on a 6-sample corpus — every Wilson
   interval overlaps. There is **no evidence-based way to select a model** yet. Whether
   cleanup compensates for weaker ASR is what Track 2 answers.
2. **G2 is not tier-aware.** A Tier B machine runs a smaller model and will have a worse
   edit rate; G2 says `≤ 5%` with no qualifier. Same defect O1 fixed on the latency axis,
   still standing on the accuracy axis.
3. **The 5% edit-rate threshold is provisional** — inherited from a WER number it was
   never converted from.
4. **Phase 5's 700 ms budget is arithmetic, not tolerance** (choice-story #9). Now has
   numbers against it: `tiny.en` + 3B measured 373–2,201 ms.
5. **Idle RSS.** §8 says < 1.5 GB with "model" singular. Phase 5 makes it two. Unmeasured.
6. **The corpus is thin** — 6 samples, one speaker, one room, mean 18.6 s against a G1
   defined on 10 s. `05-noisy` measured no noisier than the quiet samples and currently
   tests nothing. **More speakers would be worth more than more samples.**
7. **`02-code`'s reference penalises correct behaviour** — it spells out "eight"/"sixteen"
   where every engine emits digits, which is what a user wants.

---

## Conventions that will bite

- Read `AGENTS.md` GOTCHAS first — 10 entries, all from real incidents.
- Sentinel agents are **read-only**; their record only arrives as message text. Pass the
  **absolute** skill path or they improvise a charter.
- `sentinel-integrity-check.sh` globs `*.agent.md` against `*.md` files — it passes by
  checking nothing. Read the count, not the word OK.
- Voice recordings are **never** committed. `.gitignore` covers `.audio/`,
  `tests/fixtures/asr/*.wav`, `probe.wav`.
- `gh` has two accounts on this machine; the repo is under **`joshedwards237`**. Run
  `gh auth switch --user joshedwards237` before pushing or it 403s.
- Any latency figure entering the PRD carries **p50 and p95**, or is labelled a floor.
