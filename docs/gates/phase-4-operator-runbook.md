# Phase 4 — your runbook

Everything left needs you specifically. **Total: about 75 minutes of your time,
plus 30 minutes of somebody else's.**

Each step says where to go, what to click, what you should see, and what to
write down. Where a step has a pass/fail criterion, that criterion was fixed
*before* the thing was built — a criterion written afterwards is a criterion
written to pass.

---

## Timeline

| When | Step | Your time | Needs |
|---|---|---|---|
| Today, 5 min | **1. Check the daemon starts and stops** | 5 min | nothing |
| Today, 10 min | **2. Judge the recording panel** (§5.4) | 10 min | a full-screen app |
| Today, 15 min | **3. Run the network capture** (G3) | 15 min | terminal, `sudo` |
| Today, 20 min | **4.** *Optional:* ten short corrections | 20 min | quiet room |
| Today, 5 min | **4b. The latch and the second daemon** (§5.2, §9) | 5 min | two terminals |
| Whenever, 5 min | **5. Write the gate record** | 25 min | steps 1–4b done |
| Book it | **6. The install gate** | watch only | **a second person**, 30 min |

Steps 1–4b are independent. **5 needs 1–3 and 4b. 6 is the gate and should be
last** — its output is a defect list you may want to fix before anyone else
sees it.

---

## Step 1 — the daemon starts and stops (5 minutes)

New today, and it needs one real test before you rely on it.

**Do this:**

1. Go to your **Desktop**. Double-click **`Start Amanuensis.command`**.
2. A Terminal window opens. macOS may say *"cannot be opened because it is from
   an unidentified developer"* — if so: **System Settings → Privacy & Security**,
   scroll to the bottom, click **Open Anyway**, then double-click again.

**What you should see:**

- The Terminal window prints `Amanuensis — hold RIGHT OPTION to dictate.`
- Then `loading tiny.en (10 threads)...` and `listening —`
- A **`○`** appears at the right end of your menu bar.

**Now test the stop button, which is the point of this step:**

3. Click the **`○`** in the menu bar. A menu opens.
4. You should see a status line (*"Amanuensis — idle, the microphone is not
   live"*) and **Quit Amanuensis** at the bottom.
5. Click **Quit Amanuensis**.

**What you should see:** the menu-bar icon disappears, and the Terminal window
prints `stopped.`

> **Why this step exists at all.** Until this morning that menu item rendered
> and did nothing — it had no target and no action. With a desktop launcher and
> no working quit, a daemon holding your microphone would have had no way to be
> stopped except finding the Terminal window. If **Quit Amanuensis** does not
> work, stop here and tell me; do not proceed to step 2.

**Second escape hatch, so you always have one:** Ctrl-C in the Terminal window.

**Write down:** whether the menu quit worked, first try.

---

## Step 2 — judge the recording panel (10 minutes)

**This is a decision, not a check.** Its outcome decides whether Phase 4 also
has to build a real `.app` bundle, which is days of work.

**The criterion, written 2026-09-02 before the panel existed:**

> With a full-screen application focused and the menu bar auto-hidden, you can
> answer **"is the microphone live right now?"** correctly, without moving the
> pointer, without keyboard input, and without waiting — on both a live and an
> idle daemon, three trials each. **Six of six.**

**Set up the condition:**

1. **System Settings → Control Centre → Menu Bar Only** → set
   **Automatically hide and show the menu bar** to **Always**.
2. Open something full-screen with a lot of white — a document, a browser page.
   Press the green button or `Ctrl-⌘-F`.claud
3. Start the daemon (Desktop shortcut, step 1).

**Run the trials:**

4. Six trials. In each, either hold right-option or don't — decide by coin flip,
   or have someone else do it out of your sight.
5. Each trial: **answer out loud "live" or "idle" before looking anywhere else.**
   Do not move the mouse to reveal the menu bar. Do not wait to see if text
   appears.
6. Score six trials. Three should be live, three idle.

**What to look for:** a `● RECORDING` panel near the bottom of the screen while
the key is held, and nothing when it isn't.

**Write down the score, and the decision it forces:**

- **6 / 6** → §5.4 is discharged by the panel. The `.app` bundle **stays
  deferred**, and that is a decision to record explicitly, not an omission.
- **Anything less** → the bundle gets built. Note *how* it failed: invisible?
  too small? too slow to appear? ambiguous? Each points somewhere different.

**Also note two things while you are there:**

- Is the panel in the way of your cursor? `[feedback] overlay_position` in
  `~/Library/Application Support/amanuensis/config.toml` accepts `bottom`
  (default) or `top`.
- Turn the menu-bar auto-hide back off afterwards if you don't like it.

---

## Step 3 — the network capture (15 minutes)

Goal G3 is "no network at runtime" and it is the product's headline claim. The
last capture was Phase 1; since then the tray, a panel, a socket and the install
path have all been added.

**Do this, in a terminal:**

```sh
cd /Users/joshuaedwards/Development/personal/worktrees/phase-4-tray-modes
PYTHONPATH="$PWD/src" /Users/joshuaedwards/Development/personal/Amanuensis/.venv/bin/python scripts/verify_g3.py
```

It will likely ask for **`sudo`** — packet capture needs it.

**What you should see:** a PASS with **0 sockets and 0 bytes** for the subject,
and a non-zero control. If the control shows zero too, the instrument is broken
and the PASS means nothing — that is the whole reason a control is there.

**Then the part the default mode cannot do, and my earlier instruction here
was wrong.** The default mode watches only the subprocess it spawns, so a daemon
running alongside it is a different PID and **invisible** — running it "with the
daemon up" produces an identical result that establishes nothing new. §9 asks for
the capture against *the assembled product*, which needs a different mode:

```sh
# leave the daemon running, tray drawn, then:
PYTHONPATH="$PWD/src" /Users/joshuaedwards/Development/personal/Amanuensis/.venv/bin/python \
  scripts/verify_g3.py --daemon 20
```

**Dictate during the window.** It observes for 20 seconds and reports what the
daemon actually did; if you sit still it is a reading of an idle process, and the
script says so in its own output. Record which it was.

It refuses to run if **two** daemons are up, because observing one while the
other is also live would be a clean reading of half the product.

**Write down, in the gate record, in these words or close to them:**

1. "This capture covers **Amanuensis's own sockets only**." It says nothing
   about anything else on the machine.
2. "**Transcripts transit the system clipboard**, where another process may
   capture them." Measured: Maccy 2.7.0 captured every one.

Both are required. An unqualified "G3 verified" is the specific failure
objection O12 was raised about.

**One new fact for that record:** `MoonshineEngine.load()` makes two connection
attempts to `huggingface.co:443`. Moonshine is **not** installed as a dependency
and nothing in the shipped path imports it, so G3 is intact — but note it, because
if that ever changes this result changes with it.

---

## Step 4 — ten short corrections (20 minutes) — **optional**

The only optional step. Skip it and the gate record says the short-utterance
punctuation comparison is unmeasured, which is honest and fine.

**What it answers:** whether a different ASR engine punctuates better at *your
usual dictation length*. Long-form is already settled — Moonshine collapses at
67–97 s. Short is not.

**Do this:**

1. **Run nothing else on the machine.** No test suites, no builds. A previous
   attempt was ruined this way.
2. Start the daemon. Dictate **ten ordinary short things** — 8 to 12 seconds
   each, whatever you actually needed to write today. Real work, not read aloud.
3. For each one: `manu history --last` right after, and note the row id.
4. Create `corrections-short-2026-09-XX.json` shaped like the existing
   `corrections-2026-09-01.json`:
   ```json
   {"<row id>": {"started_at": "...", "seconds": 9.4,
                 "injected": "<what appeared>", "corrected": "<what you meant>"}}
   ```
5. Then: `python scripts/bench_punctuation.py --corrections corrections-short-2026-09-XX.json`

> **Do not use a script you read aloud as the reference.** That was tried and
> withdrawn: it scored the *shipped* product at 54.09% against its real 8.59%,
> because you contract naturally when reading ("I have started" → "I've
> started") and the comparison charged your own speech as decoder error. The
> reference has to be **what you said**, corrected by you.

---

## Step 4b — the latch and the second daemon (5 minutes)

Both shipped 2026-09-03 and both are gestures rather than output, so nothing
in the suite can tell you they *feel* right. Two minutes each.

**The double-tap latch** (§5.2). Push-to-talk is unchanged: hold, speak,
release. What is new is that a **double-tap starts a hands-free session and a
single tap ends it**, on the same key, with no mode switch.

1. Start the daemon in `push_to_talk` (the default).
2. **Hold and speak as usual.** It must behave exactly as it did yesterday —
   this is the one that matters most, because the latch is only affordable if
   an ordinary dictation is untouched. If your text feels like it arrives
   later than it used to, stop and say so: that is a G1 regression and the
   design says it cannot happen.
3. **Double-tap.** The panel should come up and stay up with your hands off
   the key. Speak for twenty seconds. **Single-tap** to end it.
4. **Nothing should land at the cursor from the first tap.** A stray word
   there means the fragment reached the decoder, which is the failure §5.2
   rejects by name.
5. **Hold the key mid-latch and let go.** Nothing should happen — the latch
   survives a hold, deliberately.

**What to look for:** whether **350 ms** is your hand. If your double-taps are
not registering, it is too short for you; if a deliberate quick correction gets
swallowed into a latch, it is too long. `double_tap_ms` in `config.toml` is the
dial, `0` turns the latch off entirely, and the number is marked **UNMEASURED**
in §5.3 precisely because it is a motor threshold and nobody has measured
yours. **Write down the value you end up on** — that is the only measurement
this step produces and it belongs in the gate record.

**The second daemon** (§9 Phase 4 addition 4). This is what cost you nine gate
dictations on 2026-08-18.

1. With one daemon running, open a second terminal and run `manu daemon` again.
2. It must **refuse**, print a sentence naming `manu status`, and exit.
3. **Check your menu bar.** There must still be exactly **one** glyph. A second
   one appearing even briefly is the bug — the refusal used to happen after the
   microphone was already open.
4. `manu status` should answer from the daemon that is running.

---

## Step 5 — write the gate record (25 minutes)

Create `docs/gates/phase-4.md`. It carries what was built, what was verified,
what was deferred, and what the phase revealed the PRD got wrong.

**Results from steps 1–4b**, plus this list, so none of it closes by silence:

- [ ] **`double_tap_ms`: the value you settled on, and that it is still
      unmeasured.** Step 4b produces one number and it is a fact about your
      hand, not about the software. §5.3 marks 350 as UNMEASURED; if you moved
      it, the record says what to and why, and it stays marked unmeasured
      either way — n=1 on one person is not a measurement of a threshold.
- [ ] **Four commits of Phase 3 work were never on `main`, and the branch
      count was the signal nobody read.** Recovered 2026-09-03: the latch
      specification, the `initial_prompt` mechanism, §5.7's interior blindness,
      two gate clauses that could not fail, a real audio defect, and a sentinel
      record. All five stale branches are audited and deleted. **The Phase 3
      gate record cites a `store_audio` clause that could not fail at the time
      it ran** — say so there rather than only here.

- [ ] **G2's revisit — and it is now actionable.** You deferred it on
      2026-09-02 to "the Phase 4 gate, where the model question is settled". It
      is settled: the engine is **not** the constraint. Moonshine is disqualified
      on G3 grounds and collapses on long form, so the 8.59% belongs to the
      decoder and the chain — and §7.5 records that 99 of 171 edits are a class
      no rule reaches. **Confirm 5% again, or move it with the reason stated.**
      §9 permits either; it does not permit silence.
- [ ] **G1 at ten seconds: p50 312.4 ms / p95 344.5 ms.** Measured, with the
      full chain, config digest recorded. See `g1-at-ten-seconds.md`, including
      the contaminated first attempt.
- [ ] **No Tier B machine has ever been measured.** Not a missed goal — an
      unmeasured one. §2 gives Tier B a bar; nothing has run against it.
- [ ] **Parakeet has never been benchmarked.** NeMo has no CoreML or Metal path
      on macOS.
- [ ] **§5.7's guard has two blind spots**, both fail open, both disclosed in
      the README, neither fixed: interior loss invisible by construction, and
      refusal unreachable below 2.00 s of speech.
- [ ] **§5.5's retention cannot reach orphaned audio.** Found 2026-09-03.
- [ ] **`config_sha256` is declared in `HARNESS.md` and unimplemented.** It is
      the constraint that would have caught the 2026-09-02 contamination in the
      data instead of by inspection.
- [ ] **The `.app` bundle**, deferred or scheduled, per step 2's score.

---

## Step 6 — the install gate (30 minutes of someone else's time)

**This is the gate.** Everything above feeds it.

**Before they arrive:**

1. Decide **who**, and write down which kind of user they are. At n = 1 the
   choice of subject *is* the sampling design. A developer gives you a shorter
   list and routes around the gaps this exists to find. A non-technical person
   may spend the whole 30 minutes on the two permission dialogs — and then you
   have measured the permission model, not the README.
2. Note their **starting environment**: macOS version, whether Python 3.12 is
   already installed, whether the Xcode command line tools are.
3. Have them work on **their own machine** if at all possible. A fresh one is
   the point.

**During — the conduct, fixed by §9 in advance:**

- **Say nothing.** No hints. Not one, however uncomfortable it gets.
- **Stop at 30 minutes**, wherever they are.
- **Write down every question they ask.** That list *is* the output of this
  gate. It is the README's defect report.

**Point them at:** the repository's `README.md`, section **Install**, and
nothing else.

**What they will hit, and it is already known:** at step 4 the System Settings
entry carries **their terminal's name**, not "Amanuensis", because macOS
attaches the grant to whatever launched the process. The README says so.
Whether that is enough is precisely what this gate measures.

**Also ask them step 2's overlay question.** They are the only non-author user
this phase contains, and a first reaction cannot be had twice.

**Rejects if:** they cannot reach a first successful dictation from the README
alone, or they ask a question the README should have answered.
