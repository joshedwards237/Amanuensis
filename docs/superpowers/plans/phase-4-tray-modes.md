# Phase 4 plan — tray, modes, polish

**Status: revised 2026-09-02 after three sentinel records. Four dispositions
taken; one choice-story remains open. Slices proceed.**

Branch `phase-4-tray-modes`, developed in `../worktrees/phase-4-tray-modes/`,
off `origin/main` at `6ebcacf`.

Records against the first draft of this plan:

| Record | Path | Result |
|---|---|---|
| Slicing | `docs/superpowers/slices/phase-4-tray-modes.md` | 8 slices, from 13 + 3 |
| Objections | `docs/superpowers/objections/phase-4-plan.md` | 12 objections — 2 critical, 9 high, 1 medium |
| Choice stories | `docs/superpowers/stories/phase-4-plan.md` | 12 decisions, all silent |

Every disposition in all three records is `pending`. They are the operator's.

## What the review changed, and why

The first draft had 13 slices and a dependency graph. Three of its slices
described end-states `ui/indicator.py` already ships; one was a waterfall wearing
a slice number; the `6 → 7 → 8 → 9` chain was largely invented; and the phase's
only gate artifact — the README — was scheduled second-to-last, before an
unrepeatable n=1 measurement. The revision inverts that: **the README's install
half is written first, as the specification the install path is built to
satisfy, and rehearsed on a fresh machine before the tester exists.**

Two objections are critical and both land on operator decisions taken before the
review. They are not resolved below; they are put back.

## Operator dispositions, 2026-09-02

**D1 — the asynchronous clipboard restore: priced before deciding.**
`scripts/price_restore.py` reads 93 rows spanning 2026-08-03 to 2026-09-01 and
computes, for each of the 92 consecutive pairs, whether the worker was still
occupied when the next dictation arrived and whether the restore was what
occupied it.

    restore_ms          p50 155.2   p95 155.9   max 156.3
    slack               p50  92.4 s   p05 -4.8 s   min -5.5 s
    pairs the async restore would have helped:              0
    pairs where the worker was busy with real work anyway:  9

Nine pairs overlapped, every one by roughly **five seconds** against a restore of
0.155 s. Moving the restore off the worker shaves 155 ms off a 5,500 ms wait —
2.8% of the contention, in the only cases where there was any. In the other 83
the worker was idle by a median of 92 seconds. **Recommendation: decline, and
write the refusal into §7.3 with this number beside it**, which retires O4's
critical race, O5's `restore_ms`-to-zero shape and O6 together. The build call
remains the operator's; the interlock design is specified in O4's
counter-argument if he wants it.

**D2 — "first run" means the installer invoked by first launch.** `manu install`
stays; §7.6's *never at runtime* is unchanged; the packet capture's subject is
unchanged. §11.3 resolved accordingly, with the near-miss recorded: the phrase
"at first run" reads as the daemon's first start, which would have put an HTTPS
fetch inside the process whose network silence is G3's headline claim.

**D3 — the benchmark may not move the shipped default.** Written into §7.2
**before** the benchmark runs, so the result cannot select its own consequence.
The deliverable gains deletion counts, because ADR 0001 declined Moonshine on an
axis edit rate cannot see.

**D4 — S8 splits.** The reject-clause control is carried in Phase 4, because a
user-facing number depends on the instrument it governs. The guard's two blind
spots are **disclosed in the README** — not only in the gate record, which is the
one document the second person never opens — and fixed in their own named phase.

## Still undecided

**`spoken_commands`.** §5.3's comment carries a sunset clause — "if it changes
nothing, the code goes" — and the Phase 3 gate reported it never fired, on a
corpus that contains no spoken command and therefore could not have made it fire.
Three exits: delete the code, flip the default, or amend §5.3 to retire the
clause and say the key waits for Phase 5. Keeping it off and scheduling nothing
is the state the clause was written to prevent, and Phase 5 is unscheduled, so
"meanwhile" has no end. Choice-story #11 is the only disposition still `pending`.

## Slices

Hard chains only: `S1 → gate`, `S2 → S3`, `S6's decision → S7`, `S1 → S7`.
Everything else is parallel.

### S1 — A fresh machine reaches a first dictation, rehearsed
README install half written first as the spec; the download path built to satisfy
it; then the operator installs on a fresh machine following only the written text
and records every gap. **Not the gate** — this is a defect hunt by the author.

Carries from the review: **the download path verifies no digest today**
(`faster_whisper.py:195-213` pins a revision and checks nothing) while §7.6 claims
checksum verification — O8, a stated constraint the code does not honour. The
slice's criterion names the property, not the outcome. Blocked in part on **D2**.

### S2 — Recording state a user believes, and errors they can read
`TrayApp` with its menu, the `NSPanel` overlay, error text with room for words,
and §7.3's clipboard-manager exposure as a persistent tray state honouring
`[injection] warn_on_clipboard_manager`. Plus **a written confidence test,
authored before the overlay is built** (O10, story #6).

Added by the review: whether `TrayApp` replaces `RecordingIndicator` or coexists —
two live `NSStatusItem`s put two glyphs in one menu bar (story #7). `[feedback]
sounds = true` is promised at PRD:430 and exists in no config (story #5). Whether
the overlay gets config keys, or invokes §5.3's bounded exception (story #5).
**O9 stands unresolved here:** the `.app` bundle also carries the permission
identity — `injection/macos.py:29-35`, the Settings entry currently shows the
user's terminal, not Amanuensis — and the overlay cannot discharge that job.

### S3 — Modes that leave the microphone open with no finger on a key
`toggle` and `vad_auto`, both rejected at `hotkey/macos.py:151` today.

**S2 precedes this**, an edge the first draft did not have: shipping a
finger-free mode while the glyph is the only affordance ships it into the exact
insufficiency its own user reported. §5.2 asks `vad_auto` to ship behind a flag
and the draft named none. `vad_auto` needs its own silence window — sharing
`[vad] min_silence_duration_ms = 2000` means either two seconds of dead time per
dictation or a user silently moving the configuration every G1 figure was
measured under (story #4).

### S4 — A second process can read the daemon, and tell it to record
IPC transport ABC, macOS unix socket, **both** verbs. Splitting `manu toggle` out
was a commit boundary, not a decision boundary.

Added: **§6.3's thread table has four rows and none serves a socket** (story #1) —
the acceptor's thread affinity is floor item 1's failure shape one component over,
and §6.3 gains a row. The socket's **authority model** is undecided and unasked: a
local socket that opens the microphone is an authority boundary (S4 decision
focus). Which `platformdirs` accessor, and whether a stale socket survives a
reboot (story #2).

### S5 — The thread inventory written down and asserted
Floor item 1 as §6.3 text plus a test that fails when AppKit is touched off the
main thread. The async restore rides here as its first real test case — **blocked
on D1**.

### S6 — Benchmark Moonshine and Parakeet
Both behind the existing ABC. Needs a §6.4 amendment — `parakeet` is in §5.3's
enum at PRD:336 and absent from §6.4's tree at PRD:1358.

**Deliverables gain deletion counts.** ADR 0001 declined Moonshine on an axis
edit rate cannot see — 12–14 deletions against faster-whisper's 2–7 — and
`classify_edits`' `decoder_words` bucket merges substitution with deletion, so two
engines with identical edit rates and opposite failure modes score identically
(O1, story #9). Blocked on **D3** before it runs.

Flagged by the slicing record as the weakest end-to-end candidate in the phase:
its output is a table, its product is a decision. If the phase needs shortening,
this is the slice to move out rather than the one to thin.

### S7 — The published claims: measured, generated, and qualified
G1 at ten seconds with the full chain (~9 short dictations — **a precondition of
this slice, not an extra beside it**, O12); the per-tier latency table; the
privacy section with the second G3 capture and its §7.3 qualification; the
clipboard caveat carrying the Phase 2a measurement.

**Two unresolved claims.** No Tier B figure has ever been measured on a Tier B
machine — `docs/gates/phase-1.md:95-98`, the only one is a simulated constraint on
Tier A hardware (O3). And the last G1 at its own definition is Phase 2b's
223.0/270.0, taken with an **empty chain** (O12). Whether the table is typed or
generated from `history.db` the way the site's claims are is undecided.

### S8 — Phase 3's instrument debt
§5.7's interior-loss blindness at `faster_whisper.py:329`; the sub-2.00 s
unreachability of the refusal gate; a synthetic corrections set asserted to
REJECT. **Blocked on D4.** The diaboli's narrower form is worth carrying either
way: **if cut, the debt belongs in the README, not only in the gate record**, and
item 16 is the one that should not be cut, because a user-facing number depends on
the instrument it controls.

## Also carried, unassigned to a slice

- **The G2 revisit belongs in this gate and the draft dropped it** (story #8).
  `docs/gates/phase-3.md:330` puts it here explicitly.
- **`config_sha256` is declared in `HARNESS.md:149-165` with `Enforcement:
  unverified, Tool: none yet`**, and this phase produces at least three new
  measurement sets (O2).
- **`spoken_commands` has a sunset clause that has come due** — "if it changes
  nothing, the code goes" — and the Phase 3 gate reported it never fired. Keeping
  it off and scheduling nothing is the state the clause was written to prevent
  (story #11).
- **The gate's second person is unnamed** and at n=1 the choice of subject *is*
  the sampling design (story #12). §7.2 records a 185 s model download plus a
  nine-run tier check, both inside their 30-minute clock.
- **PRD:1243 says `DictationState` has "exactly §5.4's four values"; the code has
  five.** Stale sentence, not a plan defect.
- **§9 calls this gate "the last point before an audience sees it."** The
  repository has been public since 2026-07-31. That sentence justifies deferring
  things to "before an audience" and is no longer true.

## Gate (PRD §9)

A second person installs from the README unaided. Silent observation, no hints,
stop at 30 minutes, record every question — that list is the README's defect
report. n=1 and unrepeatable. Plus the second G3 packet capture against the
assembled product, qualified in writing to Amanuensis's own sockets only and
stating that transcripts transit the system clipboard where another process may
capture them. **Plus the G2 revisit** (story #8).
