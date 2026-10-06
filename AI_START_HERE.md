# Start here

You are an agent about to work on Amanuensis. This file is the entry point: it
tells you what to read, what will bite you, and how work is actually done here.
It is not a substitute for the PRD or the harness — it is the map to them.

**Read this whole file before your first edit.** It is shorter than the time you
will lose rediscovering what is in it.

---

## 1. What this is

Fully local, open-source dictation for macOS. Hotkey → speak → text at the
cursor. No account, no network, no audio leaving the machine.

Python 3.12, `faster-whisper` on CPU, PyObjC for everything macOS. 44 source
files, 808 tests, `mypy --strict` clean.

The product it is measured against is **Wispr Flow**. The differentiator is not
features — it is that the audio never leaves the device.

## 2. The nine documents, and which one answers your question

Nine markdown files at the repo root is too many and you will not guess right.
This one is the ninth, and it exists to stop you reading the other eight in the
wrong order.

| You want to know | Read | Size |
|---|---|---|
| **What to do right now** | this file | — |
| What the product must do, and why | `AMANUENSIS_PRD.md` | huge; search, don't read |
| What you are *allowed* to do | `HARNESS.md` | 939 lines |
| What is built, what is open, phase status | `CLAUDE.md` | the short brief, read it |
| Gotchas previous sessions hit | `AGENTS.md` | **stale since 2026-09-02** |
| How a user installs and runs it | `README.md` | current |
| Past session learnings | `REFLECTION_LOG.md` | generated — never hand-edit |
| Sprint 1 handoff | `HANDOFF.md` | **superseded, history only** |

**The live state is in `docs/gates/`, one record per phase.** That is the thing
to trust. A rolling handoff goes stale between the writing and the reading; a
dated gate record does not. `CLAUDE.md` summarises them and is kept current.

`docs/superpowers/` holds the slicing records, specs, objections and
choice-stories behind decisions. When you want to know *why* something is the
way it is and the PRD does not say, it is in there.

## 3. The constraints you cannot negotiate

From PRD §6.3 and §8. Breaking one is not a bug you fix later — it is a
different product.

1. **Persist before injecting.** The transcript reaches `HistoryStore` *before*
   `TextInjector.inject()`. A crash must never cost the user their words. This
   is an ordering requirement.
2. **Zero network at runtime.** Verified by packet capture (`verify_g3.py`). No
   telemetry, no crash reporting, no update check. Weights download once at
   install, checksum-verified, from a pinned revision.
3. **Recording state is never ambiguous.** The daemon holds the microphone
   permanently; the user must always be able to tell whether it is live without
   opening a menu. A live mic with a dead indicator is the failure §5.4 exists
   to name, and it has shipped twice.
4. **Never `eval`/`exec` anything derived from a transcript.**
5. **Degrade rather than stall.** An optional pass that exceeds its latency
   ceiling is *skipped*, never queued.
6. **No hardcoded behaviour a user might want to change.** It is a key in
   `~/.config/amanuensis/config.toml`, named exactly as PRD §5.3 names it.

**Latency is the product.** G1 is p50 ≤ 400 ms, p95 ≤ 800 ms from hotkey release
to first character for a 10-second utterance. Met at 312/345 ms. The landing
page publishes that band from `claims.json`, so relaxing G1 is a §9 amendment at
a gate — not a config change.

## 4. How work is done here

### Branch and worktree

Never commit to `main`. Never switch the lobby checkout's branch — the operator
works in it concurrently.

```sh
git worktree add -b <branch> ../worktrees/<branch> origin/main
# ...work there...
git worktree remove ../worktrees/<branch> && git branch -D <branch>
```

The lobby venv is an **editable** install pointing at the lobby `src/`. A
worktree therefore needs `PYTHONPATH=$(pwd)/src` on every command, or you will
test the lobby's code and believe it was yours.

### The loop

Spec → failing test → implement → `pytest` / `mypy --strict src/` / `ruff` →
commit → PR → `gh pr checks <n> --watch` → merge green → delete the branch.

Merging green PRs is pre-authorised; do not wait to be told.

**Delete the branch at merge.** A squash-merged branch that stays alive gets
commits pushed to it that never reach `main`, and nothing objects. That has
happened and cost four commits.

### Verification, which is the whole culture here

This repository has shipped a lot of green-but-wrong. Every rule below exists
because its absence shipped something.

- **Verify a regression test by breaking the code.** Revert the fix, confirm
  red, restore. A test written seconds after watching a bug is the *most* likely
  to be hollow.
- **A sabotage must be asserted to have applied.** A replacement whose anchor
  does not match prints PASS and is indistinguishable from a working test. This
  has happened twice, including once in the session that wrote this file.
- **Write two controls, never one.** A positive (the real signal must satisfy
  it) and a negative (the adjacent signal alone must not). Either alone is
  passed by a constant.
- **Call the product's own function in a harness.** Reimplementing a formula is
  a second implementation, and its disagreements read as findings about the
  product. Two of three "findings" in one sprint were the instrument.
- **Re-derive any number before quoting it.** Six documents agreeing is one
  unchecked claim with five copies. A test count was wrong in six places.
- **p50 AND p95, always.** A p50 from one clean sample said GO where the p95 over
  real data said the opposite.

### Fakes lie, and they lie in the forgiving direction

`tests/` fakes AppKit, Quartz and the HID APIs. **A fake that accepts a shape
the framework rejects is a second implementation with a bug**, and it is the
direction reading cannot catch.

Three real examples, all from one week:

- `CALayer.setFrame_` wants a *nested* `((x,y),(w,h))`. The fake stored any
  shape. A flat 4-tuple shipped and crashed on a user's machine — the second
  time that exact error reached a daemon.
- `CATransaction` is a class with class methods. A fake inventing
  `CATransactionBegin()` made a suite agree about an API that does not exist.
- `CGRequestPostEventAccess` and `CGRequestListenEventAccess` return success and
  **do nothing** on macOS 26.x. 707 tests were green against a permission that
  was never registered.

So: **ask the framework, not the stand-in.** Contract tests that `getattr` the
real symbols cost nothing and catch all three. Where a real object can be
exercised without putting a window on screen, do that too.

### A fix is unverified until it runs where it can fail

Both development machines ran macOS 27.0 holding every permission, so every
permission check passed for the same reason the bug was invisible. Build the
instrument before the third fix — `scripts/diagnose_permissions.py` exists
because two blind fixes cost six round trips with a remote tester.

## 5. Things that will waste your afternoon

- **`pip install .` is not editable and `git pull` does not update it.** A fix
  was once judged against code that was never running. `manu --version` prints
  the directory and whether git tracks it.
- **The corpora are gitignored and exist only in the lobby checkout.** A
  worktree has no `tests/fixtures/phase3/`, so a measurement run there measures
  nothing. Scripts take `--corpus`.
- **Transcripts are personal data.** `tests/fixtures/phase3/` and
  `corrections*.json` are gitignored with the reasoning written in `.gitignore`.
  They are the operator's week, his employer's work, a named colleague. Nothing
  about a voice recording reaches a public repository — including a path.
- **`black --check` is deliberately not in CI.** It fails on 21 files from a
  formatter version drift that predates the workflow. Do not run `black` across
  `src/` to fix one file; you will reformat twenty others and bury your change.
- **CI lints `src/` and `tests/` only**, not `scripts/`. Your script still gets
  linted by you.
- **The sentinel index is generated** and CI checks it is not stale. Editing a
  slicing record's frontmatter means running
  `scripts/regenerate-sentinel-index.py`.
- **`REFLECTION_LOG.md` is a generated aggregate.** Use `/reflect`. The header
  points at a regeneration script that does not exist.

## 6. Where the project actually is

**Phase 4 is built. Its gate has not closed.** The only thing holding it is
**lane 6 — an n=1 install walkthrough with a second person**, unbooked since
2026-09-16. The install path now works end to end on a stranger's machine, so
the blocker that justified the delay is gone.

Also open: **S6's reachability trial** for the overlay's ✕/✓ controls. Its
criterion was written 2026-09-10, before the controls existed, and **must not be
amended now that they do** — that is the entire point of having written it early.

**Do not open Phase 5.** §9's Phase 4 gate has not run.

### The punctuation problem, and three closed candidates

Dictations come out as run-on sentences; the decoder emits almost no full stops.
It is the dominant error class — 99 of 171 edits at the Phase 3 gate. Three
approaches have been measured and closed:

| candidate | result | record |
|---|---|---|
| LLM cleanup pass | 19.6% → **110% WER**; invented words, refusals pasted into documents | `phase5-feasibility.md` |
| pause-gated segment joins | **39% of real sentence ends have no pause at all** — a recall ceiling no data moves | `phase5-pause-hypothesis.md` |
| punctuation-restoration model | 26% precision alone, 88% at 18% recall; **+5 edits out of 164** | `phase5-punctuation-model.md` |

**The strongest remaining lead is the engine, and the Phase 3 gate said so on
2026-09-01:** *"The model may be the constraint, not the chain."* `small.en`
reached 7.88% against `tiny.en`'s 9.59% and was rejected on G1's latency alone —
a constraint the operator relaxed on 2026-09-29.

Testing it needs a **verbatim** reference. The existing corpus was corrected
"punctuation and case only, do not fix misheard words", which was right for the
pause question and makes it structurally unable to compare engines: `small.en`
took 65 edits for *hearing correctly*. `make_punctuation_corpus.py
--combine-words` produces the pass that fixes this, and it is waiting on 40
minutes of the operator's time.

### One unresolved number that qualifies two results

The operator's two correction passes disagree on sentence density by 60% — ~21
words per sentence at the Phase 3 gate, 33.9 in the current corpus. Asked
directly, he wants something between that and the model's 16.5.

**G2's 8.59% edit rate was computed against the denser one.** Every precision
figure in the two newest gate records is measured against the sparser one. This
is not a footnote; it is a live question for the Phase 5 gate.

## 7. How to talk to the operator

He is the only user, the only tester, and the author of every recorded
objection. Three things he has made clear by correcting them:

- **Lead with the answer.** No preamble, no narrating that you verified
  something, no framing sentence before the finding.
- **Disagree when you have evidence.** He treats agreement without evidence as
  noise. When he gives you a valid argument, concede clearly and say what
  changed your mind.
- **Do not round "the question I asked" up to "the question I meant to ask."**
  Gate records say what was actually measured, including when the criterion was
  not written in advance and when a positive control failed.

**Things only he can do:** record a corpus, correct a transcript, judge the
recording panel, run lane 6. When one of those is the next step, say so and stop
— do not build around it.

## 8. First five minutes

```sh
git log --oneline -5                      # where things are
cat CLAUDE.md                             # built / open / phase status
ls docs/gates/                            # the live record
./.venv/bin/python -m pytest -q           # expect 808 passed
./.venv/bin/manu --version                # confirms the install is editable
```

Then read the newest gate record in `docs/gates/`. It is where the last session
left the argument.
