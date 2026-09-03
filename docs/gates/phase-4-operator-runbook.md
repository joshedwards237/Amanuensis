# Phase 4 — what only the operator can do

Four things remain and none can be delegated. Each is written with its conduct
fixed **in advance**, because each is `n = 1` or unrepeatable, and a criterion
written afterwards is a criterion written to pass.

Do them in this order. **1 and 2 are cheap and independent. 3 must come before
4**, because 4 is the gate and 3 is one of its inputs.

---

## 1. The overlay confidence test (§5.4) — 5 minutes

**Why you and not me:** the requirement exists because you used the Phase 2b
glyph and reported it insufficient. §5.4 records that "a requirement met to the
letter and reported as inadequate by its user is worth more than one argued
into the spec." I can assert the AppKit flags are set; I cannot see the screen.

**The criterion, fixed 2026-09-02 before the overlay was built:**

> With a full-screen application focused and the menu bar auto-hidden, you can
> answer **"is the microphone live right now?"** correctly, without moving the
> pointer, without keyboard input, and without waiting — on both a live and an
> idle daemon, three trials each, **six of six**.

**Conduct.** Full-screen something with a lot of white (a document, a browser).
Turn on *System Settings → Control Centre → Automatically hide and show the menu
bar*. Start the daemon. Have someone else hold or release the hotkey out of your
sight, or alternate blind yourself with a timer. Answer before looking anywhere
else.

**Record the result either way**, in `docs/gates/phase-4.md`:

- **Six of six** → §5.4 is discharged by the overlay and the `.app` bundle stays
  deferred. Say so explicitly; that is the decision, not an omission.
- **Anything less** → the bundle is built. §9 already scopes it, and objection
  O9 notes it also carries the permission identity — the System Settings entry
  currently shows your terminal's name, not Amanuensis, which the install gate
  will meet head-on.

Also worth one line: whether the panel's **position** is right. `[feedback]
overlay_position` accepts `bottom` (default) and `top`, and it exists because
the panel must not cover the caret.

---

## 2. The second G3 packet capture (§9, objection O5) — 15 minutes

**Why now:** the Phase 1 capture verified a narrower system. Since then the tray,
an `NSPanel`, a socket acceptor and the install path have all been added, and
this is the last point before an audience.

```sh
cd /Users/joshuaedwards/Development/personal/worktrees/phase-4-tray-modes
PYTHONPATH="$PWD/src" /Users/joshuaedwards/Development/personal/Amanuensis/.venv/bin/python scripts/verify_g3.py
```

**Then the part the script does not cover.** §9 requires the capture run against
*the assembled product* — tray running, install path exercised, model download
performed. `verify_g3.py` observes a `manu transcribe` subprocess, so run it a
second time with a daemon up and the tray drawn, and record both.

**Two things must be written into the record, not left implied** (choice-story
#11 — an unqualified "G3 verified" is the failure objection O12 described):

1. The capture covers **Amanuensis's own sockets only**. It says nothing about
   what else on the machine is talking.
2. **Transcripts transit the system clipboard by default**, where another
   process may capture them — measured against Maccy 2.7.0, which captured every
   one. That is a transcript-egress path the capture structurally cannot see.

**And one new fact for the record:** `MoonshineEngine.load()` makes two
connection attempts to `huggingface.co:443`. Moonshine is **not** installed as a
dependency and nothing in the shipped path imports it, so G3 is intact — but if
that ever changes, it changes this result. ADR 0001's reconsideration note has
the detail.

---

## 3. Ten short corrected transcripts (§7.2's remaining open question) — 20 minutes

**Optional, and the only one that is.** Skip it and the Phase 4 gate records the
short-utterance punctuation comparison as unmeasured, which is honest.

The long-form comparison is done: Moonshine collapses at 67–97 s (715 and 866
deletions against faster-whisper's 3). What is unmeasured is **short** utterances
— the length Moonshine is built for and your ordinary case.

**Do not use read scripts as the reference.** That was tried on 2026-09-02 and
withdrawn: it scored the *shipped* product at 54.09% against its real 8.59%,
because you contracted naturally while reading ("I have started" → "I've
started") and the alignment charged your own speech as decoder error. A
reference has to be what you *said*.

**Conduct.** Dictate ten ordinary short things — 8 to 12 seconds, whatever you
actually needed to write. Then:

```sh
PYTHONPATH="$PWD/src" .venv/bin/manu history --last     # for each, one at a time
```

and write a corrections file in the same shape as `corrections-2026-09-01.json`:
`{"<row id>": {"started_at": ..., "seconds": ..., "injected": ..., "corrected": ...}}`,
where `corrected` is what you meant. Then:

```sh
PYTHONPATH="$PWD/src" .venv/bin/python scripts/bench_punctuation.py \
  --corrections corrections-short-2026-09-XX.json
```

**Do not run anything else while dictating.** That is what produced the 4014 ms
p95 on 2026-09-02.

---

## 4. The gate: a second person installs from the README — 30 minutes of theirs

**This is the gate.** Everything above is an input to it.

**Conduct, fixed by §9 in advance so the gate measures the README rather than the
tester:**

- **Observe silently. No hints.** Not one, however painful.
- **Stop at 30 minutes.**
- **Write down every question they ask.** That list is the README's defect
  report and is the actual output of this gate.
- **Note their starting environment** — macOS version, whether Python 3.12 was
  already there, whether Xcode command line tools were installed.

**Choose the person deliberately and record which archetype they are**
(choice-story #12). At `n = 1` the choice of subject *is* the sampling design. A
developer produces a systematically shorter list and will route around a README
gap the gate exists to find. §4's secondary user — the accessibility case — may
not clear the two permission dialogs inside 30 minutes, and then the gate
measures the permission model rather than the README.

**What they will hit, and it is already known:** the System Settings entry
carries *their terminal's* name, not "Amanuensis", because macOS attaches the
grant to whatever launched the process. The README says so at step 4. Whether
that is enough is exactly what this gate measures.

**Ask them the overlay question too** (item 1). They are the only non-author
user this phase contains and a first reaction cannot be had twice.

**Rejects if:** they cannot reach a first successful dictation from the README
alone, or they ask a question the README should have answered.

---

## What the gate record must also carry

Named here so none of it is closed by silence:

- **G2 stays at 5% and 8.59% is still the measurement.** Your 2026-09-02
  disposition deferred the revisit to this gate "where the model question is
  settled". It is now settled: the engine is not the constraint — Moonshine is
  disqualified on G3 grounds and collapses on long form. So the gap is the
  chain's and the decoder's, and §7.5 records that 99 of 171 edits are a class
  no rule reaches. **Confirm 5% again, or move it with the reason stated.**
- **No Tier B machine has ever been measured.** The README says so. It is not a
  missed goal, it is an unmeasured one, and §2 gives Tier B a bar to clear.
- **Parakeet has never been benchmarked at all.** NeMo has no CoreML or Metal
  path on macOS.
- **§5.7's two guard blind spots** — interior loss invisible by construction,
  refusal unreachable below 2.00 s of speech. Disclosed in the README, fixed in
  neither. Both fail open.
- **§5.5's retention cannot reach orphaned audio.** Found 2026-09-03.
- **`config_sha256` is declared in `HARNESS.md` and unimplemented.** It is the
  constraint that would have made the 2026-09-02 contamination visible in the
  data rather than by inspection.
