# Amanuensis — Project Conventions

Fully local, open-source dictation. Hotkey → speak → text at the cursor.
No account, no network, no audio leaving the machine.

Two documents govern this project and they do not overlap:

- **`AMANUENSIS_PRD.md`** — the standing specification. Answers *what* and *why*.
- **`HARNESS.md`** — the operating contract. Answers *how you are allowed to work*.

This file is the short brief an agent reads first. When it disagrees with the
PRD, the PRD wins.

---

## Status: Phase 3 built 2026-08-08. **Gate not yet run — it needs the operator.**

Post-processing exists. `postprocess_ms` is no longer structurally zero, the
dictionary is live on both mechanisms, and history retains and purges. What is
*not* done is the gate: §9 wants ten real dictations of >= 60 s judged on edit
rate, and that is dictation the operator has to do.

**What shipped.** `RuleBasedPostProcessor` (ported from
`experiments/scripts/exp4_rules_only.py`, not rewritten — that code has measured
numbers attached: p50 0.0445 ms, 0/6 INVENT, 0/6 SHRINK). `vocabulary.toml` with
`[replace]` as one compiled alternation and `[boost]` scoped per bundle
identifier. `manu vocab check`. `manu history` with `--pending`, `--purge`,
`--raw`. `retain_days` reaching `history.db` at last. Two harnesses:
`scripts/gate_phase3.py` and `scripts/measure_long_audio.py`.

**Three defects in shipped code, found by reviewing the spec rather than the
code**, and all three were live before this phase: a raising post-processor lost
the transcript; `end_session()` queued a session before stashing the focus, which
silently disabled §6.3's protection against injecting into the wrong
application; and `_why_no_retry` refused §5.7's recovery in exactly the
configuration §5.6 recommends.

**Four things to carry into Phase 4 and the gate:**

- **Fixing an instance is not fixing a shape.** The chain-guard fix (objection
  O1) was recorded as restoring §8's guarantee. It closed one third of the
  window: a raise in the guard's *retry* still discarded a transcript the decoder
  had produced, and the code review found it. Fifth instance of this
  specification asserting a guarantee the code did not honour.
- **Verify a test by breaking the code.** Two regression tests written for
  accepted dispositions could not fail — reverting the fix left 492 tests green.
  Both were written immediately after watching the bug fail, which is what makes
  it feel verified. It is not the same event. Ninety seconds of sabotage catches
  it; see `AGENTS.md`.
- **Instruments disagree with the product silently.** Two of the three problems
  reported from measurement this phase were in the harness, not the product —
  a pre-flight microphone check that could not fail, and a coverage figure that
  reimplemented `guard.evaluate` and did not clamp. Call the product's own
  function; `measure_g1.py` reusing `tier.percentile` is the precedent.
- **The rules pass keeps hiding hazards in rules nobody questioned.** Three
  separate defects in `collapse_immediate_repeats` alone. The first two were
  patched with conjuncts; the third was fixed by inverting the premise, which is
  what should have happened the first time.

**Still open, and the gate needs them:**

- **The short-utterance corpus does not exist.** `scripts/record_phase3_corpus.py
  --set short`. §5.7's false-positive direction is untested and the blind spot is
  at the *short* end — the ten 60-second takes measured coverage 1.0 across the
  board and the guard never fired, which is what objection O5 predicted and is
  not evidence about the direction that matters.
- **§2's decode model is loose at length.** Measured over ten ~74 s takes:
  p50 917–938 ms against a predicted 1069, and p95 1247–1345 ms against 1083, on
  two runs of the same files. A duration-only linear model cannot predict a
  single decode, and `_why_no_retry` spends that model as a budget.
- **G1 is missed at 75 s on decode alone** (p50 ~930 ms against an 800 ms p95).
  §2 binds G1 at ten seconds and recorded this prediction in advance; it is
  utterance length, not post-processing, and per objection O4 it is **not** a
  reject exemption.

**Stop at the Phase 3 gate.** Do not begin Phase 4 until Phase 3 is approved.

---

## Hard constraints

These are binding. Each one exists because the PRD argued it, and each has a
failure mode that is not recoverable by fixing it later.

- **Persist before injecting.** Write the transcript to `HistoryStore` *before*
  calling `TextInjector.inject()`. A crash or failed injection must never cost
  the user their words (PRD §8). This is an ordering requirement, not a detail.
- **Zero network at runtime.** Goal G3 is verified by packet capture. No
  telemetry, no crash reporting, no update check that phones home. Model weights
  download once at install, over HTTPS, checksum-verified, from a pinned
  revision — never at runtime (PRD §7.6).
- **Never `eval`/`exec` anything derived from a transcript.** Transcripts are
  injected as text and are never interpreted as commands in v1 (PRD §7.6).
- **Recording state is never ambiguous.** The daemon holds the microphone
  permanently. The user must always be able to tell whether the mic is live,
  without opening the tray menu (PRD §5.4). This is a privacy requirement
  regardless of where the audio goes.
- **PRD §3 non-goals are binding.** No streaming partial results, no
  diarization, no mobile, no cloud sync, no OS voice commands, no TTS. Scope
  creep into a meeting-transcription product is a named risk (PRD §10).
- **Do not import `kokoro` anywhere in the Phase 0–5 tree.** Kokoro is
  text-to-speech; this is a speech-to-text product. Read-back is a separate
  module with its own PRD (PRD §12).
- **Degrade rather than stall.** The optional LLM post-processing pass is
  *skipped* when it exceeds its latency ceiling, never queued (PRD §5.3, §7.5).
  Consistently 350 ms and slightly rougher beats occasionally 900 ms.
- **No hardcoded behaviour a user might want to change.** Every decision in the
  PRD that could reasonably go either way is a config key in
  `~/.config/amanuensis/config.toml` with a sane default (PRD §5.3). Config keys
  are `snake_case` and match the PRD §5.3 block exactly — do not rename one
  without amending the PRD.

## Latency is the product

Goal G1 — p50 ≤ 400 ms, p95 ≤ 800 ms from hotkey release to first character,
for a 10-second utterance. `LatencyBreakdown` exists as a *product* requirement,
not a debugging nicety: G1 cannot be defended without per-stage timings
(PRD §5.5). Every stage records into it.

The Phase 1 gate is an explicit go/no-go on G1. If it is missed there, stop and
renegotiate PRD §7.1 — no later phase makes this faster.

## Architecture boundaries

Full layout in PRD §6.4; contracts in §6.3. The rules that get violated first:

- `DictationController` owns orchestration and **nothing else**. It does not
  know how injection works on a given OS, which model is loaded, or how text
  is formatted.
- `TrayApp` is a status surface with **no business logic**.
- Every swappable boundary declares its ABC in `base.py`. Dispatch lives in
  `factory.py` (platform detection) or `registry.py` (config string → class).
- Each ABC exists because there is a real chance the implementation gets
  replaced — not for symmetry. `TranscriptionEngine` is an ABC because Moonshine
  is a genuine alternative to faster-whisper on CPU (PRD §7.2).
- Do not add a top-level package without amending PRD §6.4 at a phase gate.

## Phase gates

Execution is phase-gated (PRD §9). **Stop at the gate.** Do not begin phase N+1
until phase N is explicitly approved. At each gate, report: what was built, what
was verified, what was deferred, and what the phase revealed that the PRD got
wrong.

If implementation contradicts a decision recorded in the PRD, do not silently
diverge — open the disagreement at the gate with evidence, and if accepted,
amend PRD §7 with a dated revision note.

---

## Workflow

### Spec-first change discipline

Any change to application behaviour flows through the spec before implementation:

1. Update the spec — user stories, acceptance scenarios, FRs
2. Update the implementation plan
3. Write failing tests from the spec — confirm red first
4. Implement until the failing tests turn green
5. Refactor while keeping tests green

### Test-driven development

Red → green → refactor, strictly. No production code without a failing test first.

### Branch discipline

Never commit directly to `main`. Branch names are lowercase and
hyphen-separated (`add-vad-trimming`, `fix-clipboard-restore`).

> No git remote is configured yet, so the GitHub issue-per-task step and the
> `gh pr checks` loop below do not apply until one exists. Revisit at the
> Phase 4 gate — public repo timing is an open decision (PRD §11.4).

### Commit messages

Concise: what changed and why. No postamble, no attribution lines. The message
ends when the description ends.

### PR health check

Once a remote exists: after every push, run `gh pr checks <number> --watch`. On
failure, `gh run view <run-id> --log-failed`, fix every error, commit (never
amend) and push. Repeat until green.

---

## Build and Test

    # Install (editable, with dev extras)
    pip install -e ".[dev]"

    # Test
    pytest

    # Type check — must be clean; this is a Phase 0 gate condition
    mypy --strict src/

    # Lint
    ruff check src/ tests/

    # Format
    black src/ tests/

    # Smoke check
    manu --help

    # Phase 1 measurement harnesses (need the desk-mic corpus; see .gitignore)
    python scripts/measure_g1.py --runs 9          # G1 through the product classes
    python scripts/verify_g3.py                    # no network at runtime
    python scripts/bench_engines.py --runs 9 --trim # engine comparison, ADR 0001

---

## Code quality lenses

- **Literate programming** — invoke the `ai-literacy-habitat:literate-programming`
  skill when creating a new source file or significantly rewriting one. Every
  file opens with a narrative preamble: why it exists, key design decisions, and
  what it deliberately does *not* do. Comments explain WHY, not WHAT.
  This directly serves goal G5 — a developer can read the codebase in an
  afternoon (PRD §2).
- **CUPID** — invoke the `ai-literacy-habitat:cupid-code-review` skill when
  reviewing or refactoring: Composable, Unix philosophy, Predictable, Idiomatic,
  Domain-based.

## Document known costs, do not paper over them

PRD §7.3: clipboard paste clobbers the user's clipboard, and restore races with
clipboard manager apps. That race is a known, unavoidable leak of the strategy.
It gets documented in the README, not hidden. The `keystroke` strategy exists
for users who cannot accept it.

Technical decisions are recorded with the alternative they rejected, following
the pattern in PRD §7. Decisions made during implementation land as numbered
ADRs in `docs/adr/` (e.g. `0001-engine-selection.md`, the Phase 1 deliverable).

## Learnings

`REFLECTION_LOG.md` holds past session learnings — surprises, failures, and
improvement proposals. Read recent entries before starting work.

Reflections are written as per-entry fragments under
`reflections/active/<YYYY-MM-DD>-<slug>.md` via `/reflect`. `REFLECTION_LOG.md`
is a generated aggregate — read it, never edit it by hand.

> The aggregate's header points at `scripts/regenerate-reflection-log.sh`, which
> does not exist in this project. Use `/reflect`, which writes the fragment and
> regenerates the aggregate itself.
