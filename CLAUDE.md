# Amanuensis — Project Conventions

Fully local, open-source dictation. Hotkey → speak → text at the cursor.
No account, no network, no audio leaving the machine.

Two documents govern this project and they do not overlap:

- **`AMANUENSIS_PRD.md`** — the standing specification. Answers *what* and *why*.
- **`HARNESS.md`** — the operating contract. Answers *how you are allowed to work*.

This file is the short brief an agent reads first. When it disagrees with the
PRD, the PRD wins.

---

## Status: **Phase 3 gate PASSED 2026-09-01** — `docs/gates/phase-3.md`

Edit rate **8.59%** over ten real dictations of 67–97 s. The gate does not
reject because 163 of 171 edits are decoder-side; the rules chain missed **8**
and the frozen dictionary missed **0**. `postprocess_ms` p95 0.478 ms against a
5 ms ceiling, `vocab_ms` p95 0.171 ms against 10 ms. Guard reported on all ten.

**G2 is missed and the threshold stays at 5%** (operator disposition 2026-09-02).
§9 allows moving it and requires the reason stated; the reason was measured and
the number was deliberately not moved — `small.en` reaches 7.88% on the same
corpus, so relaxing the target before the Phase 4 gate settles the engine
question would ratify 8.59% on evidence that gate may overturn. Carried as debt,
revisited at the Phase 4 gate.

Four things to carry into Phase 4.

- **The corpus was recorded twice, and the first one measured a dead config.**
  The 2026-08-18 takes were decoded under an `initial_prompt` removed from
  `config.toml` at 15:41 the same afternoon — 8m39s after the last take. One
  take lost **21.7 seconds** of speech to it and the guard passed it at 100%.
  Re-recording moved `transcribe_ms` p95 from 4018 ms to 1120 ms. Before quoting
  any measurement, check what config produced it.
- **§5.7's guard has two blind spots, both with controls.** Coverage measures
  *where decoding stopped*, not how much came back, so an interior hole is
  invisible by construction. And its numerator quantises to whole seconds below
  ~3 s, so the refusal gate is unreachable under 2.00 s of speech — which is the
  operator's ordinary utterance. Neither is fixed.
- **The model may be the constraint, not the chain.** `small.en` reaches 7.88%
  against `tiny.en`'s 9.59% at 4.2× the decode; `base.en` is worse *and* slower;
  **no size fixes the stray capitals**. PRD §7.2 carries the table and a dated
  revision note. Revisit at the Phase 4 gate.
- **The dominant error class is unreachable by a rule.** 58 missing sentence
  marks and 41 stray capitals. The obvious fix — a mark at each Whisper segment
  join — was measured and **rejected**: 29 right, 66 invented, +55 edits. That
  is the subject matter Phase 5 was missing.

Two harness defects fixed at this gate, both of the same species this repository
keeps producing: `fired_any` was satisfied by `collapse_whitespace` rather than
by the dictionary, and a **stale corrections file scored 0 edits over 0 words and
printed PASS**. `classify_edits` now buckets by *responsibility* rather than by
the shape of a difference — the surface split called 107 of 171 edits
chain-attributable and fired the reject clause; the responsibility split puts 8
inside the chain, on the same file.

**Phase 4 is next** (PRD §9): `TrayApp`, `toggle` and `vad_auto`, `manu toggle` /
`manu status` and the IPC transport, error surfacing, the README with the
clipboard caveat and the per-tier latency table, and the checksummed install
path. Its gate is a second person installing from the README unaided, plus the
second G3 packet capture against the assembled product.

---

## The landing page (`site/`), added 2026-08-27

A static Astro site at `site/`, deployed to GitHub Pages, specified in
`docs/site/SITE_PRD.md`. Parallel track: it does not touch `src/`, adds no
runtime dependency, and is excluded from `mypy` and `ruff`. The dependency
direction is one-way — the site depends on the product, never the reverse.

Four things here will bite again.

- **No page figure is ever typed.** `scripts/export_site_session.py` computes
  every public number from `history.db`; components read `claims.json`.
  `scripts/verify_site_claims.py` runs the export against a committed fixture and
  diffs it against goldens, with two controls — a perturbed row **must** produce
  a diff, and the clean fixture **must not**. If you hand-edit `claims.json` the
  positive control catches it. If you make the export blind to a column, only the
  *negative* control catches it: verified by sabotage, and the positive control
  passed the whole time.
- **The headline band is chosen by the specification, not by the data.** PRD §2
  binds G1 at ten seconds, so the published band is `≤ 10 s` and
  `HEADLINE_BAND` is a constant. An earlier revision of the site spec picked
  `7–16 s` from five candidates — half the rows and a p95 47% better — which is
  outcome selection inside the section written to prevent it. CI asserts the band
  from `claims.json` rather than trusting prose.
- **Zero third-party origins is a build gate, not a preference.**
  `scripts/verify_site_network.py` fails on any origin that is not our own, with
  no allowlist, because an earlier revision exempted a font CDN *inside the
  criterion meant to catch it*. Fonts are self-hosted in `site/public/fonts/`.
  The check is static analysis, so the interaction surface is **not** covered —
  it says so in its own output rather than reporting a clean pass over less than
  its criterion.
- **A branch deploy overwrites what `main` published.** There is one Pages site
  and `workflow_dispatch` can deploy any allowlisted branch to it. On 2026-08-27
  a branch build replaced main's nine minutes after it landed. `scripts/smoke-site.sh`
  prints the deployed ref for exactly this reason. Remove the manual path once
  the page has an audience.

`scripts/smoke-site.sh` verifies the deploy: routes, real content, that the
self-hosted fonts resolve (a 404 there falls back silently rather than erroring),
no third-party origins, and the deployed ref. `SINCE=<date>` fails a stale build.

**The demo corpus does not exist.** Every number on the published site currently
comes from a synthetic fixture and the waveform is a flat placeholder that says
so. `--require-audio` makes the production export refuse it. Recording it is
SITE_PRD §10.2 and it is the one task nobody can delegate.

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

> The remote is `origin` → `github.com/joshedwards237/Amanuensis`, **public since
> 2026-07-31**. The `gh pr checks` loop below applies. PRD §11.4 was resolved by
> action rather than by decision — see the note there.

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
