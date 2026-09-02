---
task: "Amanuensis Phase 4 — tray, modes, polish (PRD §9 Phase 4, §5.4, §7.3, §11.3)"
task_slug: phase-4-tray-modes
date: 2026-09-02
carpaccio_model: "claude-opus-5[1m]"
inseparable: false
progressed_slice: null
slices:
  - id: S1
    title: "A fresh machine reaches a first dictation, from written instructions, rehearsed"
    scope: "The README's install half written FIRST as the specification; the model download built to satisfy it; then a rehearsal in which the operator installs on a genuinely fresh machine following only the written text and records every gap. Excludes the latency table, the privacy section, and the n=1 gate itself."
    decision_focus: "Is the README a specification written before the install path, or a report written after it? The gate is n=1 and unrepeatable, and the plan leaves its only artifact until last."
    lens_used: end-to-end
    disposition: pending
    disposition_rationale: null
  - id: S2
    title: "Recording state a user believes, and errors they can read"
    scope: "TrayApp (ui/tray.py) with its menu, the NSPanel overlay, error text with room for words, and §7.3's clipboard-manager exposure as a persistent tray state. Plus a written confidence test, authored before the overlay is built, that decides overlay-vs-bundle. Excludes business logic (§6.2), mode switching, async restore."
    decision_focus: "What counts as 'confident the microphone is live', stated in advance? Operator decision 1 makes the bundle fallback turn on a confidence test that does not exist."
    lens_used: decision-boundary
    disposition: pending
    disposition_rationale: null
  - id: S3
    title: "Modes that leave the microphone open with no finger on a key"
    scope: "hotkey.mode = 'toggle' and hotkey.mode = 'vad_auto', both currently rejected at hotkey/macos.py:151, plus the streaming detector audio/vad.py:25 records vad_auto as needing. Excludes `manu toggle`, which is a different feature sharing the word."
    decision_focus: "push_to_talk's guarantee is physical — your finger is on the key. Both new modes remove it, and vad_auto opens the mic with no user action at all. §5.4 makes this a privacy question, not an ergonomics one. What replaces the finger?"
    lens_used: decision-boundary
    disposition: pending
    disposition_rationale: null
  - id: S4
    title: "A second process can read the daemon, and tell it to record"
    scope: "The IPC transport ABC (§7.3 portability floor item 3), the macOS unix socket behind it, and both verbs — `manu status` and `manu toggle`, today 'Phase 4' stubs at cli.py:85-86. Includes the socket's path, permissions and authority model, and the CLI-contract wording floor item 3 constrains."
    decision_focus: "A local socket that starts the microphone is an authority boundary. §7.6 forbids interpreting a transcript as a command; the sibling question — who may command the process holding the mic — has never been asked."
    lens_used: decision-boundary
    disposition: pending
    disposition_rationale: null
  - id: S5
    title: "The daemon's thread inventory, written down and asserted, with the async restore as its first test"
    scope: "§7.3 portability floor item 1 — the threading model named rather than implied — as §6.3 text plus a test that fails when AppKit is touched off the main thread; and the asynchronous clipboard restore moved off the worker with its failure reported. Excludes any change to what restore protects, because Phase 2a measured that it protects nothing."
    decision_focus: "What does the async restore actually buy? restore_ms is documented OUTSIDE g1_ms, so 155 ms is worker occupancy, not user-visible latency — and it costs the serial-worker property §6.3's focus check depends on."
    lens_used: decision-boundary
    disposition: pending
    disposition_rationale: null
  - id: S6
    title: "Benchmark Moonshine and Parakeet — and decide first whether the result may move the default"
    scope: "Both backends behind the existing TranscriptionEngine ABC; edit rate, punctuation classes, p50/p95 for all four engines on the Phase 3 corpus. Excludes switching the default. Requires a §6.4 amendment (parakeet.py is in §5.3's enum and not in §6.4's tree)."
    decision_focus: "If Parakeet wins, does the shipped default change inside Phase 4? Answered after the table is seen, that is outcome selection. Answered yes, Phase 4 is two phases wearing one number."
    lens_used: decision-boundary
    disposition: pending
    disposition_rationale: null
  - id: S7
    title: "The published claims — measured, generated, and qualified"
    scope: "G1 at ten seconds with the full shipped chain (~9 short dictations); the per-tier latency table labelled by what the machine measured; the privacy section carrying the second G3 capture with its §7.3 qualification; the clipboard caveat with the Phase 2a Maccy measurement. Excludes install instructions (S1)."
    decision_focus: "Is the README's latency table typed or generated? The site already refuses typed public figures — export from history.db, claims.json, two controls. A hand-typed README table is the same claim surface with none of that."
    lens_used: acceptance-criterion
    disposition: pending
    disposition_rationale: null
  - id: S8
    title: "Phase 3's instrument debt — two blind spots and a reject clause that has never fired for the right reason"
    scope: "§5.7's interior-loss blindness, addressed where avg_logprob, no_speech_prob and compression_ratio are discarded (faster_whisper.py:329); the sub-2.00 s unreachability of the refusal gate; and a synthetic corrections set where chain-attributable classes dominate, asserted to REJECT. Nothing in §9's Phase 4 text."
    decision_focus: "Does Phase 4 carry it, or does it become a named phase? 'Named as debt' is what §9's own language calls a floor item with no phase: a floor item that does not exist."
    lens_used: independence
    disposition: pending
    disposition_rationale: null
---

# Slicing record — Amanuensis Phase 4

The plan under review carried 13 numbered slices and 3 proposed additions. This
record returns 8. The compression is not tidying: three of the plan's slices
describe end-states that are **already shipped**, one is a waterfall wearing a
slice number, one dependency chain of four is largely invented, and the phase's
single most consequential artifact is scheduled last before an unrepeatable
measurement.

**The plan's slice 1 is a waterfall.** "Spec first — nothing below starts until
step 1 lands" batches four operator decisions and five PRD section amendments
into one document that arrives at the human all at once. `CLAUDE.md`'s spec-first
discipline reads *per change*. A single up-front amendment covering the whole
phase is the coherent, internally-consistent decision stream that acceptance is
the cheap response to. Dropped as a slice; distributed into the seven that own
its content.

**Three plan slices ship what already exists.** `ui/indicator.py` renders all
five `DictationState` values in the menu bar today, glyph-mapped and
main-queue-dispatched, so plan slice 6's stated end is Phase 2b's shipped
behaviour. `GLYPHS` already contains `ERROR` and `RECOVERED`, so plan slice 8's
"a failed injection is visible, not silent" is also partly shipped. What is
genuinely new in 6, 7 and 8 is one thing — a surface with **room for words** —
which is why they are one slice here.

**The 6 → 7 → 8 → 9 chain is mostly invented.** The overlay does not need
`TrayApp`; it needs a state source, and `DictationController` already feeds
`RecordingIndicator`. Error surfacing does not need the overlay unless the
overlay is chosen as its surface — a design choice not yet made, presented as
sequencing. Only 8 → 9 has an argument and it is soft. The one hard chain in the
whole plan is 11 → 12 → 13, and the plan puts it last.

**The dependency the plan is missing runs the other way.** Shipping `toggle`
before the affordance ships a mode with no finger on the key into a product whose
only mic-live signal is the glyph its own first user called insufficient. S2
precedes S3 here.

## S1 — end-to-end

*Delivers:* the README's install half — prerequisites, install command,
permission grants, first dictation, uninstall — written **first**, as the
specification the install path is built to satisfy. Then the mechanism. Then a
**rehearsal**: the operator installs on a genuinely fresh machine or VM following
only the written text, recording every place he had to know something the text
did not say.

*Newly possible:* a person who is not the author can install Amanuensis and
dictate. Today nobody can.

*Not included:* the latency table, privacy section, clipboard caveat (all S7).
**Not the gate** — the rehearsal is a defect hunt by the author and must never be
reported as the gate, which is silent observation of a second person.

*Decision content.* Is the README a specification written before the install
path, or a report written after it? The plan answered "after": slice 12 depended
on 9, 10 and 11 and slice 13 measured it. That means the artifact the gate
measures gets exactly one draft, unrehearsed, and the single opportunity to
measure it is spent on that draft. For an n=1 unrepeatable measurement that is
the wrong posture.

*Dependencies:* none. Needs only the `push_to_talk` daemon that already runs.

## S2 — decision-boundary

*Delivers:* `TrayApp` in `ui/tray.py` with its menu; the `NSPanel` overlay; error
surfacing with room for words — a glyph cannot say "Accessibility permission was
revoked"; and §7.3's clipboard-manager exposure rendered as a persistent tray
state, honouring `[injection] warn_on_clipboard_manager`, already a live config
key. Plus a written confidence test, authored **before** the overlay is built.

*Not included:* any business logic — §6.2 makes `TrayApp` a status surface. No
mode switching from the menu. No async restore. No settings panel.

*Decision content.* Operator decision 1 makes the bundle fallback turn on a test
that does not exist. The evidence base for the glyph being insufficient is one
person's reaction to one session, which the PRD rightly values because it came
from use — but it is n=1, and a criterion written after the overlay is seen will
be written to pass. Direct precedent: the site's headline band was picked from
five candidates by which one looked best, inside the section written to prevent
exactly that.

*Secondary decision the plan omits:* §7.3 assigns the clipboard-manager tray
state to Phase 4 explicitly — "Phase 4 renders the same state in the tray" — with
the standing constraint that absence of a warning must never be presented as an
all-clear.

*Dependencies:* none upstream. **S3 depends on this.**

## S3 — decision-boundary

*Delivers:* `hotkey.mode = "toggle"` and `hotkey.mode = "vad_auto"`. Both
validated by `config.py:345`, both rejected at `hotkey/macos.py:151`, so one gate
opens for both. `vad_auto` additionally needs the streaming detector
`audio/vad.py:25` already records as separate from the trimming VAD.

*Not included:* `manu toggle` (S4). Two different features sharing a word,
adjacent and undistinguished in the plan as slices 3 and 4. A README that does
not separate them will be read wrong.

*Decision content.* `push_to_talk`'s guarantee is physical: your finger is on the
key, so you know. Both new modes remove it, and `vad_auto` removes the user
action entirely — the microphone opens because a model decided you were speaking.
§5.4 makes unambiguous recording state non-negotiable on privacy grounds. The
question is not "do the modes work" but "what replaces the finger, and does it
hold when the machine decides for you". The PRD lists both in §5.3's enum and
never separately argues `vad_auto`'s privacy step.

*Dependencies:* **S2 must precede this**, and the plan does not have that edge.

## S4 — decision-boundary

*Delivers:* the IPC transport ABC (§7.3 floor item 3 — "a floor item with no
phase is a floor item that does not exist"), the macOS unix socket behind it, and
**both** verbs. Both are `"Phase 4"` stubs in `cli.py` today.

*Decision content, which the plan never surfaces: a local socket that starts the
microphone is an authority boundary.* §7.6 forbids interpreting a transcript as a
command; the sibling question — who may command the process that permanently
holds the microphone — has never been asked in this document. Socket path,
filesystem permissions, whether a `toggle` (a write that opens the mic) travels
the same channel and authority as a `status` (a read), and what happens when two
clients toggle concurrently, are one decision.

The plan's slice 2 is rescued from being a pure layer only by `manu status`,
which is a genuine second-process observable. The layer suspicion is correct in
shape and one step off in target: the real defect is that slice 3 removed the
second verb from the same decision.

*Dependencies:* none. Fully independent.

## S5 — decision-boundary

*Delivers:* §7.3 floor item 1 — "the threading model is named, not implied" — as
§6.3 text plus a test that fails when AppKit is touched off the main thread; and
the asynchronous clipboard restore moved off the worker.

*Newly possible:* dictate again immediately after a dictation instead of waiting
out the previous restore. That is the entire user-visible effect, and naming it
plainly is the point.

*Not included:* any change to what the restore protects. Phase 2a measured that
it protects nothing — Maccy 2.7.0 captured the transcript on default settings
with restore on at 150 ms, with a positive control proving the instrument could
see an ordinary copy. §7.3's own words: "a 150 ms window is not a mitigation."

*Decision content.* `LatencyBreakdown.restore_ms` is documented `# OUTSIDE G1 —
runs after the text is present`. So the 155 ms is worker-thread occupancy, not
user-visible latency: it buys throughput on back-to-back dictations, and it costs
the serial worker, which is what makes §6.3's focus check meaningful — the reason
Phase 2b declined it. The plan states the benefit and not the cost, which is
precisely the shape "write a setting's cost next to its benefit" exists to catch.

The threading model rides here because this phase forces the question.
`dictation_controller.py`'s preamble opens "Three threads meet." Phase 4 adds a
main-thread status item, an `NSPanel`, a socket listener and a restore that
outlives its session. §7.3 calls floor item 1 "the item that would actually
corner the project" and no phase has ever scheduled it.

*Dependencies:* soft on S2 and S4. Neither is hard.

## S6 — decision-boundary

*Delivers:* both backends behind the existing ABC — §6.4 already lists
`engines/moonshine.py`, and `parakeet` is in §5.3's enum with no file in §6.4's
tree, so this needs a §6.4 amendment, which `CLAUDE.md` says happens at a phase
gate.

*Newly possible for a user: nothing.* This slice ships a table. Its product is a
decision, and saying so plainly is why it is scoped separately rather than folded
into the README.

*Decision content, the phase-boundary question the plan does not ask: if Parakeet
wins, does the shipped default change inside Phase 4?*

- **Yes:** every latency figure in S1's and S7's README is measured against a
  component that changed underneath it, G1 re-opens against §7.1, and the n=1
  install gate measures a product whose core was replaced days earlier. Two
  phases wearing one number, and the second has no gate.
- **No:** say so in §7.2 *before* the benchmark runs, so the result cannot select
  its own consequence.

Deciding after seeing the table is outcome selection, and this repository has
that event on record.

*Dependencies:* independent for the *measurement*. Its **decision** must land
before S7.

*Flagged: the weakest end-to-end candidate in the record.* Its output is a
measurement artifact rather than a behaviour a user can exercise. It survives
because the artifact is a gate input and its decision is load-bearing for two
other slices — but if the record wants shortening, this is the slice to move out
of Phase 4 rather than the one to make thinner.

## S7 — acceptance-criterion

*Delivers:* G1 at ten seconds with the full shipped chain (~9 short dictations);
the per-tier latency table labelled by what the machine measured; the privacy
section carrying the second G3 capture with its §7.3 qualification; the clipboard
caveat with the Phase 2a measurement rather than the hypothesis.

*Decision content. Is the README's latency table typed, or generated?* This
project already refuses typed public figures on the site:
`scripts/export_site_session.py` computes every number from `history.db`,
components read `claims.json`, and `verify_site_claims.py` runs the export
against a committed fixture with a positive and a negative control. A hand-typed
README table is the same claim surface with none of that machinery.

*Second decision, narrower and sharper: which G1 number gets published.* The last
G1 measured at its own definition is the Phase 2b gate — p50 223.0 / p95 270.0 —
taken with `chain` **empty**. The product ships `chain = ["rules"]`. Publishing
223/270 is quoting a number measured under a configuration the product does not
ship, which is the `initial_prompt` event repeated on a user-facing surface. The
Phase 3 gate's own reasoning is sound as an argument and is not a measurement.

*Rationale:* the plan's item 14 is not an extra scoped in beside the phase — it is
a **precondition of this slice**. Listing it separately is what lets it be cut
independently of the table it exists to fill.

## S8 — independence

*Delivers:* §5.7's interior-loss blindness, addressed where `avg_logprob`,
`no_speech_prob` and `compression_ratio` are discarded at `faster_whisper.py:329`;
the sub-2.00 s unreachability; and a synthetic corrections set where
chain-attributable classes dominate, asserted to REJECT.

*Newly possible:* the user is told when a dictation lost words in the middle.
Today they are not, by construction, and the guard says everything is fine.

*Decision content. Does Phase 4 carry it, or does it become a named phase?* The
plan proposed "operator may cut; if cut, named as debt in the gate record." That
is weaker than this repository's own precedent supports. The collapse guard left
the dictionary feature entirely and shipped ahead of Phase 3 as a defect fix —
the slicing record argued the hazard was already in production, and a 30.5-second
dictation returning two words proved it three days later. And §9's own language,
quoted in the plan itself, names what "debt in the gate record" amounts to: *a
floor item with no phase is a floor item that does not exist.* The IPC transport
spent two phases in that state.

*Dependencies:* none, in either direction. The only slice with no Phase 4
coupling at all.

## Sequencing recommendation

**Hard chains, and there are only four:**

1. `S1 → gate.` The README-install and the install path are what the gate measures.
2. `S2 → S3.` The affordance precedes the modes that remove the finger.
3. `S6's decision → S7.` Not S6's table — its *answer*, writable into §7.2 today.
4. `S1 → S7.` The claims revise a README that already exists.

**Everything else is parallel.** S4 and S8 have no dependency in either
direction. S5 has two soft edges and no hard one.

**Recommended order:** S1, then S6's freeze decision (written, not measured),
then S2, then S3 and S4 in either order, then S5, then S7, then the gate. S8 and
S6's measurement land wherever there is budget, or in their own phase.

**What changes versus the plan.** The plan front-loaded the independent work and
back-loaded the only hard chain, terminating in an unrepeatable measurement whose
artifact had had one draft. This ordering does the reverse.

## Explicitly not slicing on

- **Layers.** An ABC and a socket ship nothing observable; only `manu status`
  makes that slice end-to-end.
- **Commit boundaries.** `manu status` then `manu toggle` as consecutive slices;
  `TrayApp` then `NSPanel` then error text as three. Both are the order the code
  would be committed in, not the order decisions arrive in.
- **The spec amendment as slice 1.** A waterfall — the exact shape that makes
  acceptance cheaper than disagreement.
- **§9's own sentence order.** A list of deliverables, not a build sequence.
- **Files.** `ui/tray.py` is not a slice; `engines/parakeet.py` is not a slice.
- **The gate.** Its conduct is already specified in §9 and needs no slicing.
- **`[feedback] sounds`.** §5.4's optional audio cue is Phase 4 territory by
  subject and appears in neither §9's paragraph nor the plan. Noted, not sliced —
  no decision content; belongs inside S2 if it is built at all.
- **Phase 5 subject matter.** The plan places it out of scope and that is correct;
  recorded here so the exclusion is visible in the record rather than only in the
  plan.
