---
spec: docs/superpowers/plans/phase-4-tray-modes.md
date: 2026-09-02
mode: spec
diaboli_model: claude-opus-5[1m]
objections:
  - id: O1
    category: premise
    severity: high
    claim: "Slice 12 publishes a user-facing accuracy claim while G2 is missed by 72% relative, and slice 10's stated outputs cannot measure the axis on which the leading alternative engine was already rejected."
    evidence: "Plan L18-19, L34, L36. docs/gates/phase-3.md:330-336. docs/adr/0001-engine-selection.md:112-118. docs/gates/phase-3.md:62-69 (the classifier's seven buckets)."
    disposition: accepted
    disposition_rationale: "S7.2 amended 2026-09-02: the Phase 4 default is frozen before the benchmark runs, and the benchmark's deliverable gains deletion counts so the axis ADR 0001 decided on is measurable."
  - id: O2
    category: scope
    severity: high
    claim: "The plan produces at least three new measurement sets while the constraint added at the previous gate to stop exactly that class of loss — a stored measurement carrying the config that produced it — is unimplemented and unscheduled."
    evidence: "HARNESS.md:149-165 ('Enforcement: unverified. Tool: none yet — needs a config_sha256 column'). Plan L34, L37, L41-43."
    disposition: deferred
    disposition_rationale: "Real and unscheduled. config_sha256 is harness work with no owner; named in the plan's carried section rather than given a Phase 4 slice. Not dismissed - it is the constraint the August corpus loss produced."
  - id: O3
    category: scope
    severity: high
    claim: "Slice 12 publishes a per-tier latency table, and no Tier B figure has ever been measured on a Tier B machine; the only one that exists is a simulated constraint on Tier A hardware."
    evidence: "Plan L36. docs/gates/phase-1.md:95-98. AMANUENSIS_PRD.md:2609-2614, 147-149."
    disposition: accepted
    disposition_rationale: "The README states in its own text that no Tier B machine has ever been measured and points the reader at manu install for their own number. Folded into S7."
  - id: O4
    category: implementation
    severity: critical
    claim: "The asynchronous restore reintroduces a race the injector's own source names as worse than the clipboard-manager one and entirely self-inflicted; its failure mode is the user's previous clipboard pasted into their document, which a tray report cannot undo."
    evidence: "Plan L15-17, L33. src/amanuensis/injection/macos.py:132-137. AMANUENSIS_PRD.md:1320-1332."
    disposition: accepted
    disposition_rationale: "D1: priced from the operator's own 92 consecutive pairs. 0 would have been helped. The build-or-decline call returns to the operator with the number in hand."
  - id: O5
    category: implementation
    severity: high
    claim: "A restore that outlives inject() breaks the one synchronisation rule the concurrency model has, and makes restore_ms structurally zero in history.db — the same shape as the missing column this project already shipped once."
    evidence: "src/amanuensis/controllers/dictation_controller.py:210-221, 454-464. AMANUENSIS_PRD.md:1305-1318. src/amanuensis/storage/history.py:211-214, 650-668."
    disposition: accepted
    disposition_rationale: "Same measurement. If the restore is declined the restore_ms-goes-to-zero shape never arises; if it is built, the interlock and the completion-event ordering are both explicit requirements."
  - id: O6
    category: alternatives
    severity: high
    claim: "The plan does not weigh doing nothing: the 155 ms is already outside G1 by the PRD's own boundary, and nothing measures how often worker occupancy costs a user anything."
    evidence: "Plan L33. AMANUENSIS_PRD.md:88-93, 1018-1026. No contention figure appears in the plan, the PRD, or docs/gates/phase-3.md."
    disposition: accepted
    disposition_rationale: "This objection is what D1 answered. The benefit was stated in milliseconds and never priced; it is now priced at 0 of 92 pairs over a month of real dictation."
  - id: O7
    category: risk
    severity: critical
    claim: "Decision 2 puts a network fetch on the daemon's first run, which is the path 7.6 forbids, and slice 13 states no rule for what its capture is permitted to see — leaving a check that either passes by excluding the thing it was asked to observe, or fails by construction."
    evidence: "Plan L13-14, L35, L37, L67-70. AMANUENSIS_PRD.md:2025-2026 ('Never at runtime'). src/amanuensis/engines/faster_whisper.py:11-19. scripts/verify_g3.py:236-241, 282-283, 77-78."
    disposition: accepted
    disposition_rationale: "D2: 'first run' means the installer invoked by first launch. manu install stays, S7.6's never-at-runtime is unchanged, and the packet capture keeps its current meaning. S11.3 resolved accordingly."
  - id: O8
    category: risk
    severity: high
    claim: "No checksum verification exists in the download path today, slice 11's completion criterion is satisfied without one, and slice 10 introduces two engines whose weights have no pinned revision at all."
    evidence: "src/amanuensis/engines/faster_whisper.py:195-213 (revision pin only, no digest), 101-105. Plan L34-35. AMANUENSIS_PRD.md:2025-2026."
    disposition: accepted
    disposition_rationale: "download_weights verifies no digest while S7.6 claims checksum verification - a stated constraint the code does not honour, sixth instance. S1's criterion names the property rather than the outcome."
  - id: O9
    category: implementation
    severity: high
    claim: "Decision 1 defers the .app bundle on 5.4 confidence grounds alone, but the bundle also carries the permission identity the n=1 install gate depends on — and the overlay cannot discharge that job."
    evidence: "Plan L10-12, L31, L65-66. src/amanuensis/injection/macos.py:29-35, 108-112. AMANUENSIS_PRD.md:2776, 1186-1193."
    disposition: deferred
    disposition_rationale: "The bundle deferral stands on cost grounds. The permission-identity risk is recorded and the README instructs the tester to grant to their terminal, which the shipped remediation text already does well. Revisit if the gate's defect list is dominated by it."
  - id: O10
    category: specification quality
    severity: high
    claim: "Slice 6's completion criterion is already satisfied by shipped code, slice 7's is unfalsifiable, and decision 1's deciding test has no criterion, no tester and no threshold."
    evidence: "Plan L30-31, L10-12. src/amanuensis/ui/indicator.py:53-72, src/amanuensis/cli.py:647-650. AMANUENSIS_PRD.md:2092-2097."
    disposition: accepted
    disposition_rationale: "The confidence test is written before the overlay is built. Slice criteria renamed to name what is new rather than what ui/indicator.py already ships."
  - id: O11
    category: risk
    severity: high
    claim: "Items 15 and 16 are offered as cuttable against 'named as debt in the gate record', which is a record and not a mitigation — and the two readers who need those facts read the README and the engine comparison, not the gate record."
    evidence: "Plan L44-54. docs/gates/phase-3.md:117-127, 155-173. HARNESS.md:176-182."
    disposition: accepted
    disposition_rationale: "D4, in the diaboli's own narrower form: item 16 is carried in Phase 4 because a user-facing number depends on the instrument it controls; item 15 is disclosed in the README - not only the gate record - and fixed in its own named phase."
  - id: O12
    category: specification quality
    severity: medium
    claim: "The README depends on slices 9, 10 and 11 but not on item 14, so the per-tier latency table can publish with G1 at ten seconds still unmeasured, and the n=1 gate sits behind the two largest slices with no stated fallback."
    evidence: "Plan L36, L41-43. docs/gates/phase-3.md:142-145, 344-346, 89-92."
    disposition: accepted
    disposition_rationale: "G1 at ten seconds is a precondition of S7 rather than an item beside the phase, so the latency table cannot publish without it."
---

# Objection record — Amanuensis Phase 4 plan

Dispatched 2026-09-02 against the plan sketch, deliberately before it was
defended. Twelve objections; eleven high or critical. Every disposition is
`pending` — resolving one is a human act, which is what the read-only tool
boundary on this agent enforces.

Every claim below was re-verified against the source before being recorded here.
The three that carry the most weight — O4, O7 and O8 — were checked verbatim.

## O1 — premise — high

Slice 12 publishes a user-facing accuracy claim beside the latency table. G2 is
missed at 8.59% against 5%, and the operator's recorded disposition defers the
number to this gate on the grounds that slice 10 settles whether the engine
closes the gap. Slice 10's stated outputs cannot answer the question the
previous engine decision turned on.

`docs/adr/0001-engine-selection.md:112-118` rejected Moonshine on an axis none
of edit rate, punctuation classes or p50/p95 expresses: it "deletes 12-14 words
where the faster-whisper models delete 2-7 … A deleted word is **silent data
loss**." `docs/gates/phase-3.md:62-69` shows `decoder_words` is one bucket
covering substitution and deletion together. Two engines with identical edit
rates and opposite failure modes score identically. The instrument slice 10 uses
is blind to the property that decided the question last time.

The plan also states no decision rule for what the README says under any
outcome. A phase whose last slice is a published number needs the rule that
turns measurements into that number written before the measurements exist —
otherwise the number is chosen after seeing the data, which is the
outcome-selection failure already recorded once here on the site's headline band.

**Counter-argument.** §9 assigns the engine question to this phase and the Phase
3 gate named the two engines as unbenchmarked *for punctuation* specifically, so
measuring punctuation classes is responsive to what was asked. The operator may
reasonably intend to apply ADR 0001's reasoning by hand at the gate. A decision
rule written from the wrong prior can be worse than judgement applied after.

## O2 — scope — high

`HARNESS.md:149-165`, added 2026-09-02 — the same day this plan was written:
every row in `history.db` records a digest of the configuration that produced it,
and a gate refuses a set whose rows do not share one. **Enforcement: unverified.
Tool: none yet.** The plan produces at least three new measurement sets and
mentions it nowhere.

Slice 10 is a worse case than the one that produced the constraint: four engines
scored against one corpus means four configurations differing in the one field
that decides the result, replayed from stored audio whose original decode config
is not recorded either. The August corpus disaster was found by accident. A
constraint declared and left with no tool is the same artefact as a risk written
into a spec: it reads as handled.

**Counter-argument.** Slice 10's comparison runs inside one script run, so the
config cannot drift mid-run and the digest buys nothing there. The constraint is
honestly marked unverified, and scheduling it competes with slices that ship
product.

## O3 — scope — high

`docs/gates/phase-1.md:95-98`: "That is a simulated constraint, not a measured
machine … **A real Tier B number requires a real Tier B machine, and this gate
does not have one.**" §9 requires the README to carry Tier A and Tier B figures
"each labelled with what the machine measured." The plan lists the table as one
line and acquires no second machine.

§4 makes this the caveat that has to live where users are: the privacy-motivated
and offline-constrained users the product exists for are disproportionately the
ones on the slower tier. Publishing a figure derived by pinning `cpu_threads = 4`
on an M3 Max, in a table labelled by what a machine measured, is a measurement
quoted without the machine that produced it.

**Counter-argument.** The tier check ships and runs at install, so every real
user gets a measured number for their own machine. The table is orientation and
could honestly say no Tier B machine has been measured. That is a one-line README
decision, not a slice.

## O4 — implementation — critical

`src/amanuensis/injection/macos.py:132-137`, verbatim:

> The paste is asynchronous — the target application reads the pasteboard on its
> own run loop — so restoring immediately would race the paste itself, **which is
> a worse race than the clipboard-manager one and entirely self-inflicted.**

The 150 ms sleep at `macos.py:288` exists solely to lose that race safely. Moving
the restore to another thread does not remove the sleep; it removes the guarantee
that nothing else touches the pasteboard during it. Session N's restore now runs
concurrently with session N+1's `clearContents()` / `setString_forType_()` / ⌘V
at `macos.py:280-282`.

The plan makes overlap ordinary rather than rare: slice 5 ships `vad_auto`, which
`AMANUENSIS_PRD.md:1320-1332` names as the mode most likely to produce exactly
this. §5.2 asks that `vad_auto` ship behind a flag; slice 5 does not mention one.

The failure is not "the restore failed" — it is the user's *previous* clipboard
contents landing in their document. Observability is a mitigation when the user
can act on what they observe; here the observable event arrives after the wrong
text is already in the document. That is a recorded risk mistaken for a
mitigation, and the lesson is already written down in this repository.

**Counter-argument.** Overlap requires session N's restore thread to still be
sleeping when session N+1 reaches injection — two dictations within roughly
155 ms plus decode, i.e. a `vad_auto` misfire or a hotkey bounce. A restore
thread that checks a shared paste-in-flight flag and skips its write eliminates
the race and still returns the 155 ms. The objection is then to the plan's
silence about the mechanism, not to the decision.

## O5 — implementation — high

`AMANUENSIS_PRD.md:1309-1318`: "The worker populates every field *before* setting
the event, so any thread that observes it set sees a fully written session.
**That ordering is the synchronisation rule; nothing else guards the fields, and
nothing else needs to.**" The event is set in a `finally` at
`dictation_controller.py:459-464`, immediately after `_process` returns.

`dictation_controller.py:215-221` computes `inject_ms = max(0.0, elapsed_ms -
result.restore_ms)` from a value that, under an async restore, has not happened
yet — then calls `mark_injected`, whose `_complete` writes `restore_ms` in the
same statement. `InjectionResult` is frozen, so the restore thread cannot hand
its figure back to a result the caller already consumed.

The precedent is on file at `storage/history.py:211-214`: `restore_ms` "is the
first entry and is here because it was missed" — Phase 2a added the field and the
schema never grew the column. A zero in a `NOT NULL DEFAULT 0` column is
indistinguishable from a real measurement of an instantaneous restore. Same
defect, different route.

§8's persist-before-inject ordering survives — the write is upstream of injection
and the plan does not move it. What does not survive is the ability to say
anything true about the clipboard exposure window, at exactly the moment the
change makes that window longer and less predictable.

**Counter-argument.** The restore thread can be given the session and write its
own timing; the completion event can fire after the restore joins. Both small.
And `restore_ms` is outside `g1_ms` by design, so nothing gated depends on it.

## O6 — alternatives — high

The plan states the benefit as "155 ms off the worker" and nothing else. The
restore is already outside G1 by the PRD's own boundary
(`AMANUENSIS_PRD.md:88-93`) because "it runs while the user is already reading
their words." The only thing it occupies is worker time between consecutive
dictations, and no figure anywhere says how often that matters.

The data to price it exists: `history.db` holds `started_at` for every dictation
in both Phase 3 corpora, so the distribution of inter-dictation gaps is one
query. The plan quotes no such figure. Phase 2b declined this on the grounds that
the serial worker is what makes the focus check meaningful; the plan reverses the
decision without touching that argument.

This project's standing rule is to write a setting's cost next to its benefit and
run the comparison both ways on real input.

**Counter-argument.** 155 ms is 12% of the measured p95 `g1_ms` at length. And
the Phase 3 corpus is a deliberately structured recording session — the worst
possible sample for estimating how a user dictates in ordinary work, where short
consecutive utterances are the normal case §7.4 is built around. Sizing from that
corpus would be calibrating to the wrong population.

## O7 — risk — critical

`AMANUENSIS_PRD.md:2025-2026`: "Model weights are downloaded once at install over
HTTPS with checksum verification, from a pinned revision. **Never at runtime.**"

`src/amanuensis/engines/faster_whisper.py:16-19`: "`load()` resolves a path with
`local_files_only=True` first, and a cold cache raises an error naming
`manu install` rather than reaching for the network… **this makes the property
structural.**"

The instrument that would run slice 13 has no concept of permitted traffic.
`scripts/verify_g3.py:77-78` — `saw_traffic` is true on **one socket or one
byte**. `verify_g3.py:282-283` fails the run if it is true.

The two ways slice 13 can be run are both bad and the plan picks neither. Run the
capture over a window including the download and it fails by construction on
traffic the design intends. Run it over a window excluding the download —
a warm daemon at steady state — and it passes for exactly the reason the Phase 1
capture passed, having observed neither the install path nor the tray nor the new
dependency surface the gate exists to cover. A gate that cannot fail for the
reason it claims, in the one place it would be least visible: a green G3 line in
a public README.

"First run" is also a change from what ships. `manu install` exists
(`cli.py:189-198`) and the error text at `faster_whisper.py:186-191` sends the
user to it by name. §11.3's open question was *Hugging Face at first run vs.
bundled installer*; an explicit `manu install` step is neither, and decision 2
silently retires it.

**Counter-argument.** "First run" may mean only that the installer is invoked by
the first launch rather than by a separate command — a packaging detail that
measurably improves the n=1 gate's odds by removing a command the tester must
discover. The capture can be scoped in writing to the post-install steady state,
exactly as it is already scoped to Amanuensis's own sockets. The objection then
reduces to: say which, in the plan, before the gate.

## O8 — risk — high

`src/amanuensis/engines/faster_whisper.py:195-213` — `download_weights` calls
`download_model(..., local_files_only=False, revision=PINNED_REVISIONS.get(model))`
and **verifies no digest**. §7.6 says "with checksum verification." The code does
not honour it.

`PINNED_REVISIONS` holds three entries, all faster-whisper. `.get(model)` returns
`None` for anything else — it downloads at its default revision. Slice 10 adds two
engines whose weights are the input to the accuracy claim in slice 12.

Two failures share one slice. The criterion — "fresh machine reaches a first
dictation" — is satisfied by a path that is neither checksummed nor pinned, so
the plan's own phrasing gives the slice a green light its title does not earn.
And `PINNED_REVISIONS` was fixed as an instance for three models while a
neighbouring slice adds two engines that walk straight past it: fixing an
instance rather than a shape, inside the plan that adds the new instances.

**Counter-argument.** `huggingface_hub` verifies file integrity against the
repo's own metadata on download, and a pinned revision plus HTTPS plus that
verification is a defensible reading of "checksum-verified" — a separate digest
table would verify the hub against itself. And pinning revisions for candidates
that may be declined is bookkeeping. The narrower objection stands regardless:
slice 11's criterion should name the property, not the outcome.

## O9 — implementation — high

`src/amanuensis/injection/macos.py:29-35`: "**The grant belongs to the hosting
application, not to `manu`.** … both preflight calls returned True on a machine
that had never heard of this project, because the terminal running Python already
held the grant. **Until Phase 4 packages an `.app`, the entry the user must find
in System Settings carries their terminal's name.**"

The shipped remediation says so verbatim: "look for your terminal in the list
(Terminal, iTerm, Ghostty, VS Code), not for 'Amanuensis'."
`AMANUENSIS_PRD.md:2776` rates permissions opacity **High**.

The gate is n=1, unrepeatable, capped at 30 minutes. Its most likely consumer of
that budget is a stranger granting Accessibility and Input Monitoring to an
application called "Ghostty" for a product called Amanuensis, twice, in two
Settings panes. Decision 1's conditional — build the bundle only if the *overlay*
disappoints — is not connected to that. A failure there is ambiguous between "the
README is bad" and "the packaging is wrong", and the gate was supposed to
separate README defects from everything else.

**Counter-argument.** The bundle is genuinely large — signing, notarisation, a
launch agent, its own permission entries — and putting it before the overlay
would consume the phase. §5.4 is explicit that macOS's own microphone indicator
discharges the correctness half, so the overlay is for confidence, which is what
decision 1 orders correctly.

## O10 — specification quality — high

Slice 6's criterion — "menu-bar item reflecting every `DictationState`" —
describes `src/amanuensis/ui/indicator.py` as it stands: `GLYPHS` maps all five
values, `_TOOLTIPS` labels them, and it is wired into the daemon on the main
thread at `cli.py:647-650`. The one thing `TrayApp` adds over the shipped
indicator — a menu — is not in the criterion. The plan never says whether
`TrayApp` replaces `RecordingIndicator` or coexists with it, while slice 7's
`NSPanel` becomes a third main-thread AppKit surface in the same process.

Slice 7's criterion — "mic-live state visible without the menu bar" — is
satisfied by an `NSPanel` existing.

Decision 1 makes "the overlay still fails the confidence test at the gate" the
trigger for the largest deferred item in the phase and defines nothing about that
test. On the plain reading the evaluator is the builder.
`AMANUENSIS_PRD.md:2092-2097`: "three of six gates named an activity … with no
condition attached, so they could not fail on their own terms and **reduced to
discretionary approval by the person whose work was being gated.**"

**Counter-argument.** These are one-line criteria in a sketch. Requiring a
falsifiable predicate for "the microphone is visibly live" risks the opposite
failure — something satisfiable by a pixel test that a user still cannot read at
a glance — and §5.4's provenance is that a requirement met to the letter was
reported inadequate by its user.

## O11 — risk — high

Item 15 is the guard's two blind spots. `docs/gates/phase-3.md:117-121`:
"`min_decoded_coverage = 0.5` therefore requires **speech > 2.00 s** before the
refusal gate is reachable at all… **The refusal gate was unreachable on 11 of
11.**" And an interior loss of 56 words over 21.7 s recorded **coverage 100.0%,
passed**. The README slice lists clipboard caveat, latency table and privacy
section — the guard's limits are in none of them.

Item 16 is the reject clause's own control. `HARNESS.md:176-182`: "`classify_edits`
has nine controls; the reject clause built on top of it has none… **A failing
state observed only as an instrument bug has not been observed.**" That instrument
is what slice 10 uses to rank four engines for the README's accuracy claim.

Shipping to a second person and recording the limits in `docs/gates/phase-4.md`
puts the disclosure in the one document that reader will never open.

**Counter-argument, and it is a real one on item 15.** The guard fails **open**
below two seconds: a short collapse is injected, the user sees it at their own
cursor, and the cost is a noticing and an undo — which is §5.7's own stated reason
that refusal is defensible only when the words are retrievable. The Phase 3 gate
could not manufacture a true positive at short length at all: prompt echo is a
long-clip phenomenon and `initial_prompt` is empty in the shipped config, so the
one documented trigger is disabled. The honest form is narrower than "do not cut":
**if cut, the debt belongs in the README, not only in the gate record** — and item
16 is the one that should not be cut, because a user-facing number depends on it.

## O12 — specification quality — medium

Slice 12 depends on 9, 10 and 11. Item 14 — G1 at ten seconds with the full
chain — carries no slice number and no dependency edge, so the per-tier latency
table can publish while it remains unmeasured. If item 14 slips, slice 12 still
completes and the README publishes 223/270 ms measured on an **empty chain** at a
different phase. A number quoted without the config that produced it, in the one
document written for people who cannot check.

The scheduling half is softer: slices 10 and 11 are the two largest, both feed
slice 12, and slice 12 feeds a gate whose subject is a human being whose
availability the plan does not control.

**Counter-argument.** The dependency column is a build order, not a permission
structure, and item 14 is nine short dictations. Drafting the README earlier
against provisional numbers has its own documented failure mode here — a document
written one commit behind, whose stale claims propagated into two reviews.

## Explicitly not objected to

- **The IPC and modes sequence.** It follows §7.3 floor item 3 exactly, and
  `cli.py:77-87` already records `toggle` and `status` as Phase 4 with the reason.
- **Spec-first ordering with the PRD amendment gating.** This project's stated
  discipline, and the plan names the specific sections rather than gesturing.
- **The gate's n=1, unrepeatable design.** A repeatable README test would measure
  testers, not the README. The objections are about what is *behind* the gate.
- **The G3 qualification language.** Exactly what choice-story #11 obliges,
  carried forward verbatim. The one thing in the gate that is already right.
- **Excluding Phase 5 / transcript structure.** Correct scoping for a phase
  already carrying an engine benchmark.
- **`AMANUENSIS_PRD.md:1243`'s "exactly §5.4's four values" against the code's
  five states.** A stale PRD sentence, not a defect in the plan. §5.4 gained
  `RECOVERED` on 2026-08-05. Slice 1 is the natural place it gets fixed.
- **PRD §11.4's resolution making "the last point before an audience sees it"
  false.** The repository has been public since 2026-07-31, so §9's framing of
  this gate as the pre-audience moment is no longer accurate. Not an objection to
  a slice — but it is the sentence that justifies deferring things to "before an
  audience", and it deserves a line in the slice 1 amendment.

## Summary

premise 1 · scope 2 · implementation 3 · risk 3 · alternatives 1 ·
specification quality 2 — **12 total**. Critical 2 (O4, O7), high 9, medium 1.

| Failure shape, by this repository's own name for it | Where |
|---|---|
| A check that cannot fail by construction | O7, O8, O10 |
| A stated constraint the code does not honour | O7, O8, O5 |
| Fixing an instance rather than the shape | O8, O5 |
| A measurement quoted without the config that produced it | O3, O2, O12 |
| A recorded risk mistaken for a mitigation | O4, O11 |
| A rule sized on recall when it is priced on precision | O1 |
