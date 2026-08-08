# Amanuensis — Project Conventions

Fully local, open-source dictation. Hotkey → speak → text at the cursor.
No account, no network, no audio leaving the machine.

Two documents govern this project and they do not overlap:

- **`AMANUENSIS_PRD.md`** — the standing specification. Answers *what* and *why*.
- **`HARNESS.md`** — the operating contract. Answers *how you are allowed to work*.

This file is the short brief an agent reads first. When it disagrees with the
PRD, the PRD wins.

---

## Status: Phase 2b closed 2026-08-03, follow-up fix closed 2026-08-07. Phase 3 next.

The loop is closed. `manu daemon` holds the model and the microphone, a
listen-only `CGEventTap` watches right-option, and `DictationController` runs
press → capture → transcribe → **persist** → inject on one serial worker. A
menu-bar glyph reports idle / recording / transcribing / error.

**G1 is met: p50 223.0 ms / p95 270.0 ms** against 400/800, over ten real
dictations in the 7–16 s band, read from the daemon's own `history.db` rows —
`LatencyBreakdown` already persists, so the daemon measures itself and there is
no harness between a voice and the number. Still a floor: `postprocess_ms` is
the one unfilled stage, and Phase 3 fills it.

**The Phase 2b follow-up shipped 2026-08-07** — the collapse guard, PRD §5.7,
record at `docs/gates/phase-2b-followup.md`. `initial_prompt` could silently
destroy a transcript and had shipped in Phase 1 with nothing watching it; a
30.5-second dictation returned two words and injected them. The guard measures
**decoded coverage** — how much of the retained speech the decoder got through —
and below `min_decoded_coverage` the text is not injected. Verified on real
audio: 8.3% on a reproduced collapse, 82.8% floor on six genuine samples, zero
false positives.

Three things from it that will bite again:

- **A guard that measures the user is measuring the wrong thing.** The first
  design was words per second. It carries speaking rate as a confound, and it
  cannot judge short audio at all — word count is an integer, so at two seconds
  the rate quantises to 0.5 w/s *per word* and a genuine "Yes." is the same
  measurement as a collapse. Short dictation is the ordinary case here, so the
  duration exemption that fell out of it was a blind spot over the most common
  input.
- **A verification written against a remembered failure is written against a
  description.** The first `verify_guard.py` used a prompt reconstructed from
  the gate record's prose, collapsed nothing, ran the negative control twice and
  printed PASS. Fourth instance of a check that could not fail.
- **`mypy --strict` is not optional after a contract change.** 337 tests went
  green with `manu transcribe` broken by the `str` → `Transcription` return
  type. The suite mocks past those callers; the type checker names both lines.

`docs/gates/phase-2b.md` is the gate record. Six findings, four amended the PRD.
Three are worth carrying:

- **G1's number is the best case of a linear relationship.** `transcribe_ms ≈
  48.8 + 13.69 × seconds_of_audio`. A 60-second dictation lands at ~909 ms —
  over G1's p95. Not a violation (§2 binds G1 at 10 s) and **Phase 3's gate is
  ten dictations of ≥ 60 s**, so it will run straight into this. It is the
  utterance length, not post-processing.
- **The daemon could not be stopped.** Ctrl-C and SIGTERM both did nothing; only
  `kill -9` worked. A Python signal handler cannot run while the main thread is
  inside `NSApplication.run()`, and `stop_` needs a dequeued event to be
  noticed. Both halves are fixed in `ui/indicator.py`. The indicator was correct
  the whole time — the failure was that knowing did not help.
- **`restore_ms` had no column in `history.db`** for the whole of Phase 2a,
  which added the field as its headline finding. Second instance of "an
  amendment must reach the tooling".

Still contracts: post-processing, the tray, `toggle`/`status` and their IPC
transport. `history` refuses and names Phase 3; `toggle` and `status` refuse and
now name Phase 4.

**Stop at the Phase 3 gate.** Do not begin Phase 4 until Phase 3 is approved.

---

## Previously: Phase 2a closed 2026-08-02.

Text reaches the cursor. `MacOSInjector` does clipboard paste with save/restore
and a keystroke fallback; `HistoryStore` is the minimum §8 write. Injection
passes in TextEdit, Terminal, VS Code and Chrome on both strategies, verified by
Accessibility read-back rather than by eye (`scripts/gate_2a_inject.py`).

One finding there is a standing hazard: **`strategy = "keystroke"` is silently
rewritten by the target application's text substitution** — five changes in one
sentence into TextEdit, where paste is byte-identical.

## Previously: Phase 1 closed 2026-08-01.

The ASR path works. `manu install` downloads the model once and records this
machine's tier; `manu transcribe --seconds 10` records from the microphone and
prints the transcript with per-stage timings.

G1 is met: ASR p50 299.7 ms / p95 373.3 ms through the product classes, against
400/800 ms. Tier A. G3 verified — zero sockets, zero bytes, positive control.
Engine chosen in `docs/adr/0001-engine-selection.md`: faster-whisper `tiny.en`.

`docs/gates/phase-1.md` lists ten findings, four of which amended the PRD. One
item there still blocks Phase 4: the tier check's reference clip has unsettled
provenance and is not committed, so `manu install` needs
`scripts/make_tier_clip.sh` or `--clip PATH` first.

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
