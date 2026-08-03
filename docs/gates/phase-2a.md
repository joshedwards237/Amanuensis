# Phase 2a gate — Text at the cursor, no hotkey yet

**Date:** 2026-08-02
**Branch:** `phase-2a-injection`
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), 36 GB, macOS 27.0
**Interpreter:** CPython 3.14.5
**Tier on this machine: A** (recorded at the Phase 1 gate)

**Verdict: PASS.**

Injection lands in all four named applications, on both strategies, verified by
reading the text back through the Accessibility API rather than by eye. §8's
persist-before-inject ordering is implemented and tested directly, and a
deliberately failed injection leaves the transcript recoverable on both
retention paths. The clipboard-manager exposure §7.3 argues about is now
**measured** rather than argued: a real manager captured the transcript inside
the default 150 ms restore window.

Two findings changed the product rather than the documentation, and both came
from running it rather than reading it.

---

## What the gate asked

PRD §9, Phase 2a:

> **Gate:** Dictate into TextEdit, VS Code, Chrome, and a terminal. Report where
> it fails. Confirm clipboard save/restore behavior with a clipboard manager
> running, and that the detection and tray indicator from §7.3 fire correctly.
> Confirm the transcript survives a deliberately failed injection.
>
> **Rejects if:** injection fails in **two or more** of the four named
> applications, or fails in a *native* text field. […] Also rejects if a
> transcript is lost when injection fails.

## What was measured

### Injection, in the four named applications

`scripts/gate_2a_inject.py` resolves each application, reads its focused
element's value through the Accessibility API, injects a unique marker, and
reads again. Nothing is judged by eye.

| Application | Field | clipboard | keystroke |
|---|---|---|---|
| TextEdit | native `AXTextArea` | **PASS** | **PASS** |
| Terminal | native | **PASS** | **PASS** |
| Visual Studio Code | Electron | **PASS** | **PASS** |
| Google Chrome | Blink (omnibox and page `<textarea>`) | **PASS** | **PASS** |

**Zero failures, on both strategies.** Neither reject condition is approached.

The read-back is an instrument, so it has a control: an `AXError` *before*
injection reports UNVERIFIED or MANUAL, never FAIL. A gate that fails by
measuring nothing is the same bug as one that passes by measuring nothing, and
this repository has shipped two of the latter (AGENTS.md GOTCHAS).

That control earned its place immediately — see finding 5.

### End-to-end, through the microphone

Two real dictations. The second, after the timing split in finding 1:

| Stage | ms |
|---|---|
| `capture_ms` | 10,236.3 (excluded from G1) |
| `vad_ms` | 34.5 |
| `transcribe_ms` | 163.9 |
| `asr_ms` | 198.4 |
| `persist_ms` | 4.1 |
| `inject_ms` | 29.1 |
| `restore_ms` | 154.8 (excluded from G1 — finding 1) |
| **`g1_ms`** | **231.6** |

Still a floor — post-processing is Phase 3 — and n=2, which is why the two new
stages were measured properly instead:

### The two stages Phase 2a adds, n=25 into TextEdit

Nearest-rank, no interpolation.

| Stage | p50 | p95 | min | max |
|---|---|---|---|---|
| `persist_ms` | 2.19 ms | 5.62 ms | 0.75 ms | 6.77 ms |
| `inject_ms` | 0.86 ms | 2.44 ms | 0.41 ms | 174.96 ms |
| `restore_ms` | 155.10 ms | 156.08 ms | 150.79 ms | 156.08 ms |
| **Phase 2a's addition to `g1_ms`** | **3.32 ms** | **6.89 ms** | 1.17 ms | 181.72 ms |

Phase 1 left ~100 ms of p50 headroom for post-processing and injection. Phase 2a
spends **3.32 ms** of it. Post-processing inherits essentially all of it.

`inject_ms`'s max of 174.96 ms is the first call and is finding 2.

### The transcript survives a failed injection

Fault-injected by forcing `CGPreflightPostEventAccess` to return False — the
one thing toggling Accessibility off in System Settings changes. Real store,
real injector, real ordering.

| `retain` | injected | what remains |
|---|---|---|
| `true` | False | one row in `history.db`, `injected = 0` |
| `false` | False | one `0600` JSON file under `pending/` |

Both paths keep the words. `mark_injected` is never called, so the row is not
flagged and the file is not unlinked — failure is the *absence* of a call
rather than a branch, which means the case the guarantee protects cannot be
broken by editing the code that handles success.

### Clipboard-manager exposure — now measured, not argued

Maccy 2.7.0 installed for the gate.

| | result |
|---|---|
| Detection fires and names the application | **yes** — `ClipboardExposure(detected=True, manager='Maccy')` |
| Save/restore still correct with a manager running | **yes** — previous contents returned |
| Control: an ordinary copy is captured by Maccy | **yes** (instrument works) |
| **Transcript captured with the default 150 ms restore window** | **YES** |
| Transcript captured with `restore_clipboard = false` | yes |

**This is the important row.** §7.3 says clipboard-manager capture is "the
normal operation of a clipboard manager, not a timing artefact", and that
`restore_delay_ms` "has no bearing on whether the transcript was recorded in
transit." Both statements are now measured rather than reasoned. A user running
a clipboard manager on default settings has their transcript recorded by it,
every time.

The first attempt at this measurement returned "not captured" and was **wrong**
— the read ran before Maccy flushed to disk. It was only caught because the
positive control was added afterwards and the ordinary copy came back captured
too. Without the control this gate would have recorded a false all-clear on the
product's most-argued privacy surface.

### G3 still holds with a new dependency in the tree

pyobjc is the first runtime dependency added since G3 was last verified.

| Subject | sockets | bytes in/out | exit |
|---|---|---|---|
| Full `manu transcribe` cycle | 0 | 0 / 0 | 0 |
| **Phase 2a surface only** (warm-up, detection, 5× persist+inject) | **0** | **0 / 0** | 0 |
| Positive control | 1 | 828 / 37 | 0 |

`verify_g3.py` gained `--inject`. Note what it *cannot* do: a 3-second capture
with no speech transcribes nothing, `write_pending` declines, and the run exits
before injecting — a clean socket count from a run that never reached the code
under test. Hence the separate injection-only subject above, which exits 0 after
five completed injections.

§7.3's scope limit stands and is Phase 4's obligation to state: packet capture
covers this process only, and the Maccy result above is precisely the egress it
cannot see.

## What was built

```
src/amanuensis/
├── injection/
│   ├── base.py            + warm_up() on the ABC (finding 2)
│   ├── macos.py           NEW — MacOSInjector, detect_clipboard_manager
│   └── factory.py         darwin -> MacOSInjector; the Phase 0 stub is gone
├── storage/
│   └── history.py         NEW — the §8 write, two retention paths
├── models/
│   ├── results.py         + ClipboardExposure, + InjectionResult.restore_ms
│   └── session.py         + persist_ms, + restore_ms, + DictationSession.engine
└── cli.py                 + `transcribe --inject`, _deliver, the two warnings

scripts/
├── gate_2a_inject.py      NEW — the four-application check, as a measurement
└── verify_g3.py           + --inject
```

184 tests (124 at the Phase 1 gate), `mypy --strict src/` clean across 26 files,
`ruff` clean, `black` clean.

## Deferred, by design

- **`DictationController` does not exist.** `_deliver` in `cli.py` is the §8
  ordering, and Phase 2b lifts it into the controller. Keeping it in the CLI
  meant it could be tested directly rather than through a microphone, which for
  the one invariant that cannot be repaired later was the right trade.
- **Orphan sweeping.** §5.5 puts it at daemon start; Phase 2a has no daemon.
  Under `retain = false`, every failed injection leaves a plaintext file behind
  and nothing yet removes it. Phase 2b.
- **`manu history` does not surface pending transcripts.** §5.5 gap 3. Phase 3.
- **The tray.** See finding 4.
- **Post-processing.** Every `g1_ms` here is still a floor.

## What this phase revealed that the PRD got wrong

Five findings. Four need a PRD amendment and are marked.

### 1. The clipboard restore is inside `inject_ms` and outside G1 — **amend §2, §6.3**

The first real dictation reported **`g1_ms` 421.9 ms**, over G1's 400 ms p50,
with **`inject_ms` 180.3 ms**. Roughly 150 of those milliseconds were
`restore_delay_ms` sleeping.

§2 defines G1 as ending when the text is **fully present in the focused
application**. The clipboard restore runs strictly after that — the user has
their words and is reading them while it happens. Charging it to G1 reports a
272 ms delivery as a 422 ms miss.

Only the injector can separate the two: `inject()` returns once, after both.
So `InjectionResult` gained `restore_ms`, `LatencyBreakdown` gained a
`restore_ms` field **outside `g1_ms` and inside `total_ms`**, and `_deliver`
subtracts. The second dictation reports **231.6 ms**.

This is the *third* instance of the same shape — `vad_ms` at the Phase 1 gate,
`persist_ms` and `restore_ms` here. §6.3's `LatencyBreakdown` was specified
before anyone knew what the stages were, and every phase since has found one
with nowhere to record. The pattern is worth stating in §6.3 rather than
patching a fourth time: **a stage inside G1's window with no field is a stage
that cannot be defended when G1 is missed, and a stage outside the window
recorded inside it is a miss that never happened.**

### 2. `TextInjector` needs a `warm_up`, and the PRD's own argument says why — **amend §6.3**

The first `inject()` costs **165.8 ms**; every subsequent one is under 2 ms.
The pyobjc bridges load on first use.

§6.3 gives `TranscriptionEngine` a `warm_up()` with the rationale "Run one
throwaway inference. First real call must not pay compile cost." The identical
problem exists at this boundary and the ABC has no such method — 165 ms against
a 400 ms budget, landing on the user's *first* dictation, which is the one that
decides whether they keep the tool.

Phase 2a avoided it **by accident**: the CLI checks permissions (loading Quartz)
and detects clipboard managers (loading AppKit) before the microphone opens.
Nothing required that ordering and a Phase 2b daemon need not preserve it.

`warm_up()` added, concrete and a no-op by default rather than abstract — an
injector with nothing to warm should not be made to write an empty method, and
forgetting it is slow once rather than silently wrong. One constraint is tighter
than the engine's and is stated on the ABC: the engine can afford a throwaway
inference; **an injector must not type a throwaway character into whatever
window has focus.** First injection is now 8.4 ms.

### 3. Synthetic keystrokes are rewritten by the target application — **amend §7.3**

§7.3 offers `strategy = "keystroke"` to users who cannot accept the clipboard
exposure, and states its cost as being slower and more failure-prone. There is a
third cost, larger than both, and it is silent. Injected into TextEdit:

```
sent    : don't use --dashes... "quoted" and i said so
landed  : don’t use —dashes… “quoted” and I said so
```

Five substitutions in one sentence — smart quotes twice, an em dash, an
ellipsis, and an autocapitalised "i". macOS text substitution applies to
synthetic keystrokes exactly as it does to real ones. **The identical string
pasted arrives byte-identical.**

This lands on §4's privacy-motivated primary user, who is precisely the person
the strategy exists for, and it cuts against §1: a tool that resolves your
self-corrections and then rewrites your punctuation has moved the problem rather
than solved it. Nothing in Amanuensis can reach into another application's
substitution settings, so it cannot be fixed here — only said.
`_keystroke_warning` says it at `--inject` time, symmetrically with the
clipboard warning.

Note also that the AX read-back **cannot** see this: it reads the raw injected
value before the substitution settles. The finding came from reading TextEdit's
own document text a second later. An instrument that verifies arrival does not
verify fidelity.

### 4. §9's Phase 2a gate requires a Phase 4 component — **amend §9**

The gate asks that "the detection and tray indicator from §7.3 fire correctly".
`TrayApp` is Phase 4. Phase 2b already carries the precedent — "a visible
indicator, not the full `TrayApp`" — and Phase 2a needs the same wording,
because `--inject` is the first thing that ever puts a transcript on a
clipboard.

Built as `_clipboard_warning`: a `ClipboardExposure` value plus a warning
printed before the microphone opens, so the user learns of the exposure while
they can still press Ctrl-C. Phase 4 renders the same state in the tray.

It prints nothing when no known manager is found, and **never an all-clear**.
§7.3 is explicit that the detection list is incomplete by nature, so "no known
manager detected" is the only true statement available and a reassuring message
would imply the one thing the detection cannot know.

### 5. `to_history_row()` omitted the engine — no amendment, the PRD was right

§5.5 lists engine among what history stores; the model did not carry it.
`DictationSession.engine` added, as `backend:model`. Recorded because it is the
kind of gap that only surfaces when something finally reads the row.

## Also worth recording

- **The gate harness produced three wrong verdicts about the product before it
  produced a right one.** A fixed launch sleep reported a cold VS Code as "not
  running". Electron ships its accessibility tree switched off, so VS Code read
  as unmeasurable until `AXManualAccessibility` was set — and one early run
  "passed" only because a throwaway probe had set the flag by hand minutes
  earlier, which is a gate whose result depended on something outside it. A
  fixed post-injection settle read an empty field for a 22-character keystroke
  marker and a populated one for 14, reporting **a native-field FAIL** — the
  single most consequential verdict this gate can return — for a harness
  artefact. All three are fixed and documented in the script.
- **The instrument's blind spot is worth stating.** The AX read-back verifies
  that text *arrived*; it does not verify that the text is *verbatim*, because
  it reads before the target's substitution runs. Finding 3 was found another
  way.
- **The first end-to-end dictation was contaminated by the harness.** The
  spoken cue was backgrounded with `&` and overlapped the ping, so the
  microphone caught its tail — the transcript opens with "You hear the ping."
  Reported by the speaker, not detected by the harness.
- **A self-correction survived the decoder in the wild.** The second dictation
  transcribed "It is July. No, it is August 2nd" — an unprompted marked repair,
  corroborating `docs/gates/phase5-disfluency.md` outside its own corpus.
- **`restore_ms` is 155 ms of pure latency in a 150 ms budget key.** It is
  outside G1 and therefore not a goal violation, but it is real time the process
  spends holding the user's transcript on the clipboard. Making the restore
  asynchronous would shorten the exposure window and free the worker thread.
  Not done in Phase 2a — it introduces a race with the next dictation and
  belongs with the concurrency model in Phase 2b.
- **Maccy was installed for this gate** and is still installed. Remove with
  `brew uninstall --cask maccy` if it is not wanted.

## Gate decision

**PASS.**

- `Rejects if: injection fails in two or more of the four named applications` —
  zero failures, on both strategies.
- `Rejects if: injection fails in a native text field` — TextEdit and Terminal
  both pass on both strategies.
- `Rejects if: a transcript is lost when injection fails` — verified on both
  retention paths under fault injection.

Phase 2b is released. It inherits: `_deliver` to lift into `DictationController`,
orphan sweeping at daemon start, the asynchronous-restore question, and the
warm-up call to place somewhere a daemon actually reaches.

Carried from Phase 1, unchanged: the tier-check reference clip's provenance
(blocks Phase 4), `beam_size` unswept, and the thread sweep still n=1.

## Rollback

Everything is additive on a branch. `git checkout main` restores the tree as of
the PR #3 merge. `pyobjc-framework-Cocoa` and `pyobjc-framework-Quartz` are new
runtime dependencies, both marked `sys_platform == "darwin"`;
`pyobjc-framework-ApplicationServices` is used only by `scripts/gate_2a_inject.py`
and is not a runtime dependency.
