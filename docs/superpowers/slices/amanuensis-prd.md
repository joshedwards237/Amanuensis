---
task: "Amanuensis — fully local dictation tool (standing specification, AMANUENSIS_PRD.md v0.1, pre-implementation)"
task_slug: amanuensis-prd
date: 2026-07-30
carpaccio_model: claude-opus-5[1m]
inseparable: false
progressed_slice: null
slices:
  - id: S1
    title: "Prove the ASR path against G1 on target hardware"
    scope: "Mic capture through transcription to stdout with per-stage timings, on this machine, with whatever minimum scaffolding the measurement genuinely needs — plus the faster-whisper vs. Moonshine benchmark that resolves ADR 0001."
    decision_focus: "Does batch local ASR clear G1 here, on which engine, and how much of §6.3/§6.4 do we freeze before we know?"
    lens_used: decision-boundary
    sequencing_note: "Hard blocker on everything else. A miss re-opens §7.1 (streaming), which changes the TranscriptionEngine contract itself."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S2
    title: "First text at the cursor, triggered without a hotkey"
    scope: "TextInjector for one platform, invoked from the CLI (`manu transcribe --inject` or equivalent). Clipboard strategy with save/restore, keystroke fallback, non-destructive permission check with actionable remediation. No hotkey."
    decision_focus: "Which platform first, which injection strategy is the default, and what counts as an acceptable set of applications where paste fails?"
    lens_used: decision-boundary
    sequencing_note: "Depends on S1 producing a transcript. Isolates the Accessibility permission surface from the Input Monitoring one."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S3
    title: "Close the core loop with the hotkey and measure real G1"
    scope: "HotkeyListener for the default binding, push_to_talk only, DictationController wiring press → capture → transcribe → inject. First end-to-end G1 measurement from hotkey release to first character."
    decision_focus: "Does the full-path G1 number still clear the budget once hotkey-release and injection latency are in it, and what happens if it does not?"
    lens_used: decision-boundary
    sequencing_note: "Depends on S2. This is the first slice that can measure G1 as §2 actually defines it."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S4
    title: "Safety floor for a mic-holding, injecting daemon"
    scope: "Minimum unambiguous recording indicator visible without opening a menu (§5.4), and HistoryStore persistence wired to run before TextInjector.inject() (§8). Not the full TrayApp; not history retention, purge, or query surfaces."
    decision_focus: "Do the two hard constraints the PRD marks non-negotiable land with the slice that first makes them applicable, or are they knowingly suspended for two phases?"
    lens_used: decision-boundary
    sequencing_note: "The scheduling question IS the decision. Candidate to fold into S2 and S3 rather than follow them."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S5
    title: "Deterministic post-processing measured by edit rate"
    scope: "RuleBasedPostProcessor and VocabularyPostProcessor in an ordered chain, plus initial_prompt plumbing. Ten real dictations of ≥ 60 seconds, reporting what fraction of output needed manual correction and what kind."
    decision_focus: "What edit rate is acceptable before the LLM pass is even considered, and which correction classes are rules territory versus model territory?"
    lens_used: acceptance-criterion
    sequencing_note: "Depends on S3 for realistic long-form dictation input. VAD silence trimming deliberately excluded — see S1."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S6
    title: "A second person installs and runs it"
    scope: "Install path with checksummed, pinned model download; README documenting the clipboard-restore race as an unsolved cost; remaining capture modes behind their flags. Success is a second person getting to first dictation without the author's help."
    decision_focus: "Hugging Face at first run versus bundled installer (§11.3), and whether the repo is public before or after this lands (§11.4)."
    lens_used: decision-boundary
    sequencing_note: "Depends on S5. First slice whose user is not the author."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
  - id: S7
    title: "Optional LLM post-processing pass"
    scope: "LocalLLMPostProcessor behind the existing config flag, with the hard latency ceiling that skips rather than queues. A/B against S5 output on identical audio."
    decision_focus: "Does the measured quality gain justify the measured latency cost, or does this ship disabled with that stated in the README?"
    lens_used: independence
    sequencing_note: "Blocks nothing. Can land any time after S5, or never. The only slice whose acceptable outcome is 'built and turned off'."
    disposition: pending
    disposition_rationale: null
    file_as_issue: pending
    issue_url: null
    merged_into: null
---

The PRD already carries a six-phase plan in §9. This record does not restate it.
It applies the lenses to the same material and reports where the PRD's own
phasing is and is not end-to-end-complete. Two findings drive most of the
divergence: Phase 0 ships nothing observable and freezes contracts that Phase 1
may invalidate, and Phase 2 bundles two independent permission surfaces while
deferring two constraints the PRD itself calls non-negotiable.

## S1 — Prove the ASR path against G1 on target hardware — decision-boundary

**Context.** PRD §9 Phase 1 and §7.2. The PRD is explicit that the numbers in
the `model = "auto"` table are "pre-implementation estimates from the model
cards, not measured on target hardware," and that Phase 1 exists to replace
them. §10 lists "G1 unachievable on CPU-only hardware" as the only High-severity
risk with an explicit go/no-go attached.

**Decision content.** Four things resolve at one gate on one measurement run, so
they are one adjudication rather than four:

1. Does batch transcription clear p50 ≤ 400 ms on this machine, for a 10-second
   utterance? A miss re-opens §7.1 and the rejected streaming alternative.
2. faster-whisper or Moonshine (§7.2, ADR 0001). §7.2 argues that Moonshine's
   viability is *why* `TranscriptionEngine` is an ABC. If the benchmark shows it
   is not competitive, that justification weakens and should be re-argued rather
   than inherited.
3. Is the measurement taken with or without VAD silence trimming? §7.4 calls
   trimming "a free latency win on every mode," but §9 schedules it in Phase 3.
   Measuring the project's most consequential number without an optimization we
   have already decided to build is a choice, not a default.
4. How much of §6.3 and §6.4 is frozen before the number exists? PRD Phase 0
   commits to all ABCs, the full package tree, and a config schema whose keys
   CLAUDE.md forbids renaming without a PRD amendment. If G1 fails and §7.1 is
   renegotiated toward streaming, `transcribe(audio, sample_rate) -> str` is the
   wrong signature — it has no room for partial hypotheses or revision. Phase 0
   as written asks for a commitment to the shape of a design whose central
   premise is unverified.

**Dependencies.** None. This slice blocks every other slice in the record.

**Rationale.** Under the end-to-end lens, PRD Phase 0 does not survive as a
standalone slice. `manu --help` running and a malformed config producing a
useful error are real edge-to-edge behaviours for their own scope, but the
scope is a toolchain milestone with no observable product value — precisely the
internal-milestone shape the lens rejects. The right treatment is not to delete
the Phase 0 work but to make it subordinate: carry exactly the scaffolding this
measurement needs, and defer the rest of the freeze until the measurement says
whether the design survives. That inverts the PRD's ordering, and the inversion
is the finding, not an accident.

## S2 — First text at the cursor, triggered without a hotkey — decision-boundary

**Context.** PRD §7.3, §9 Phase 2, §10 (two Medium/High risks: opaque macOS
permissions, Electron and Java apps rejecting synthetic paste), §11.1 (primary
OS target, open).

**Decision content.** Which platform goes first — the PRD assumes macOS on the
reasoning that its permissions model is the most restrictive and will surface
the hardest problems earliest, and §11.1 leaves this open for confirmation.
Whether clipboard remains the default given that §7.3 already concedes the
restore race with clipboard managers is unavoidable rather than mitigable. And
the acceptance question the Phase 2 gate poses without answering: the gate says
"report where it fails" across TextEdit, VS Code, Chrome, and a terminal, but
does not say what failure set is tolerable. A slice that ships is a slice with
a threshold.

**Dependencies.** Requires S1 to produce a transcript. Requires nothing from the
hotkey layer — that is the point of the cut.

**Rationale.** PRD Phase 2 bundles HotkeyListener, the injector, permission
checks, and controller wiring into one gate. On macOS those are two distinct
permissions (Accessibility for injection, Input Monitoring for global key
capture), two distinct failure modes, and two distinct remediation messages.
Splitting them costs one temporary CLI trigger and buys the ability to
adjudicate each permission surface on its own evidence. The CLI-triggered
version is genuinely end-to-end and genuinely useful on its own: you can dictate
into a real application the day it lands, just not from a hotkey yet.

## S3 — Close the core loop with the hotkey and measure real G1 — decision-boundary

**Context.** PRD §5.1, §5.2, §6.3 (`DictationController`), §9 Phase 2.

**Decision content.** The measurement question is the material one. §2 defines
G1 as "from hotkey release to first character injected," but §9 Phase 1 states
"No hotkey, no injection" — so the Phase 1 gate compares a partial measurement
against a full-path budget. `LatencyBreakdown` names four stages and Phase 1 can
populate at most two of them. The number that decides the project's viability is
first available here, one to two slices after the gate that was supposed to
decide it. The human needs to settle in advance what happens if S1 passed at
360 ms and S3 lands at 520 ms: is the go/no-go re-run, or was it already spent?

Secondary: `push_to_talk` only. `toggle` and `vad_auto` stay out — §5.2 already
flags `vad_auto` as "the mode most likely to misfire."

**Dependencies.** S2. Interacts with S4, which may need to land alongside it.

**Rationale.** This is the slice where the product described in §1 exists. It is
also where the PRD's own defining constraint becomes measurable for the first
time, which makes the Phase 1 gate a lower-bound check rather than the go/no-go
§9 and §10 present it as. Naming that here rather than at the gate is the point
of slicing it separately.

## S4 — Safety floor for a mic-holding, injecting daemon — decision-boundary

**Context.** PRD §5.4 ("Non-negotiable"), §8 (crash behaviour: "Never lose a
transcript — write to history before injection"), §9 Phases 3 and 4. CLAUDE.md
lists both as hard constraints, and describes the persistence ordering as "an
ordering requirement, not a detail."

**Decision content.** Both constraints are scheduled after the phase that first
makes them applicable, and the gap is structural rather than cosmetic:

- §8 requires persisting before injecting. `HistoryStore` arrives in Phase 3.
  Phase 2 therefore ships an injection path that cannot honour the constraint,
  because the thing it must persist to does not exist.
- §5.4 requires the recording state to be visible without opening the tray menu,
  and grounds this in privacy rather than convenience — "regardless of where the
  audio goes." `TrayApp` arrives in Phase 4. Phases 2 and 3 run a daemon holding
  the microphone with no indicator, and the Phase 3 gate is ten real dictations
  of ≥ 60 seconds each, which is dogfooding, not a dry run.

The decision is binary and belongs to the human: fold a minimum version of each
into S2/S3, or knowingly suspend two stated-non-negotiable requirements for two
phases and say so on the record. Both are defensible; silently doing the second
is not.

**Dependencies.** The persistence half needs S2 to have something to persist
before. The indicator half needs only a daemon that holds the mic. Sequencing is
the open question rather than a settled answer.

**Rationale.** These two started as separate candidates and are clustered
because they share one decision — whether a constraint the PRD calls binding is
allowed to lag the slice that makes it binding — and because separately they
would each be a component-shaped slice rather than a decision-shaped one.
Clustered, they still pass the end-to-end filter: both halves are observable
(you can see the mic state; your words survive a failed paste). Scope is
deliberately the floor, not the feature: an indicator, not `TrayApp`; a write,
not history retention, purge, or `manu history`.

## S5 — Deterministic post-processing measured by edit rate — acceptance-criterion

**Context.** PRD §5.6, §7.5, §9 Phase 3. §7.5 argues that post-processing is
"the genuine gap between raw Whisper output and a polished dictation product."

**Decision content.** The Phase 3 gate is stated as a measurement — report edit
rate over ten real dictations, and what kind of correction was needed — with no
threshold attached. The testable behaviours that constitute this slice:
punctuation and capitalisation restored on unpunctuated model output; spoken
commands such as "new paragraph" honoured; `initial_prompt` biasing reaching the
engine; vocabulary substitutions applied case-insensitively on whole words only;
`strip_fillers` defaulting off because §5.3 calls it lossy. §5.6 is explicit
that the two vocabulary mechanisms are both required because "they fail in
different places," so shipping one is not shipping this slice.

**Dependencies.** S3, for realistic long-form input. VAD silence trimming is
excluded and relocated to S1.

**Rationale.** This is the one slice where decision-boundary does not
legitimately fit and the fallback is honest. §7.5 has already made the material
decision — rules first, deterministic, debuggable — and what remains is a set of
testable behaviours plus a measurement. Recording it as acceptance-criterion
rather than forcing a decision framing keeps the lens vocabulary meaningful.

Separately: PRD Phase 3 bundles VAD silence trimming with this work, but the
Phase 3 gate measures edit rate and trimming does not affect edit rate at all —
it affects latency. Two things measured by different gates should not share one.
Trimming belongs with S1, where it can improve the number that actually decides
something.

## S6 — A second person installs and runs it — decision-boundary

**Context.** PRD §7.6 (weights downloaded once at install, HTTPS, checksummed,
pinned revision, "Never at runtime"), §9 Phase 4, §10 (model download size
surprises users), §11.3 and §11.4.

**Decision content.** Hugging Face at first run versus a bundled installer
(§11.3) — the constraint that makes this non-obvious is §7.6's flat prohibition
on runtime download combined with a ~1.5 GB artefact, so "first run" has to mean
an explicit install step with a size prompt, not lazy fetch. Whether the repo is
public before or after this lands (§11.4). And what the README must concede:
§7.3 and CLAUDE.md both require the clipboard-restore race to be documented as
an unsolved cost rather than papered over, which is a decision about how the
project talks about its own defects at the moment it first has an audience.

**Dependencies.** S5. First slice whose user is not the author, which is the
whole test.

**Rationale.** The Phase 4 gate — "a second person installs it from the README
without your help" — is the strongest gate in the PRD because it cannot be
self-graded. It is kept as its own slice for that reason, with the tray polish
and remaining capture modes riding along rather than driving. The recording
indicator is deliberately not here; it is in S4, where it is needed three phases
earlier.

## S7 — Optional LLM post-processing pass — independence

**Context.** PRD §5.3 (`[postprocess.llm]` config block), §7.5, §9 Phase 5.

**Decision content.** Whether the measured quality gain from reflowing rambling
speech justifies 200–500 ms against a 400 ms p50 budget. §7.5 has already
pre-committed the shape of the answer — off by default, hard ceiling, skipped
rather than queued — and §9's Phase 5 gate explicitly permits "ship it disabled
and say so in the README" as a success outcome. What remains genuinely open is
whether it is worth building at all given that the config block already reserves
its place.

**Dependencies.** S5, for a baseline to A/B against. Blocks nothing.

**Rationale.** Recorded under the independence lens because it is the only piece
of the PRD that can land at any point after S5, or never, without blocking
anything else and without changing any other slice's scope. It is also the only
slice in this record whose acceptable outcome is "built and turned off," which
makes it the natural candidate to defer if the human wants to compress the
record. Kept thin for that reason.

## Sequencing recommendation

S1 is a hard blocker and is not negotiable in position. Everything downstream
assumes batch transcription clears G1; a miss re-opens §7.1, which changes the
`TranscriptionEngine` contract and therefore invalidates work in S2 and S3.

S2 then S3, in that order. The split exists to separate the Accessibility
permission surface from the Input Monitoring one; reversing it or merging them
recreates PRD Phase 2 and forfeits the benefit.

S4 is the open sequencing question, and that is deliberate. Its decision content
*is* whether it lands with S2/S3 or after them. If the human folds it in, S4
disappears as a slice and reappears as scope on S2 and S3 — which is a legitimate
`merged` disposition, not a failure of the slicing.

S5 after S3, since it needs realistic long-form dictation to measure against.
S6 after S5. S7 after S5, at any time, or never.

Note that S3, not S1, is the first point at which G1 is measurable as §2 defines
it. If the human wants the go/no-go to be real, the gate belongs at S3 or is run
twice. This is the sequencing consequence of the §2-versus-§9 gap recorded in S1
and S3.

## Explicitly not slicing on

- **PRD §9's phase boundaries taken as-is.** Phase 0 fails the end-to-end filter
  (scaffolding with no observable product value) and is folded into S1 as
  "carry only what the measurement needs." Phase 2 is split into S2 and S3.
  Phase 3's VAD trimming is relocated to S1 because it is measured by a
  different gate than the rest of Phase 3. Phase 4's recording indicator is
  pulled forward into S4 because §5.4 becomes binding two phases earlier. The
  remaining phase structure is left intact.

- **One slice per component or per directory in §6.4.** `AudioCapture`,
  `HistoryStore`, `TrayApp`, `VoiceActivityDetector` and the rest are
  code-organisation cuts. Each appears inside the slice whose decision it
  serves, never as a slice of its own.

- **One slice per ABC.** `TranscriptionEngine`, `TextInjector`,
  `TextPostProcessor` are layer cuts. A slice that defines an ABC and no
  implementation ships nothing observable — this is the same failure that
  removes Phase 0 as a standalone slice.

- **Capture modes as a slice.** `toggle` and `vad_auto` (§5.2) are largely
  pre-decided: `push_to_talk` is the default and `vad_auto` already ships behind
  a flag by the PRD's own instruction. Clustered into S3 (push_to_talk only) and
  S6 (the rest). Low adjudication value on their own.

- **History configuration as a slice.** Retention days, `store_audio` default,
  the `0600` file mode, and `manu history --purge` are all settled with defended
  defaults in §5.3, §5.5 and §7.6. Only the *ordering* requirement from §8 is
  live, and that is in S4.

- **The §11 open decisions as standalone slices.** Each is attached to the slice
  that forces it — §11.1 to S2, §11.3 and §11.4 to S6 — rather than adjudicated
  in the abstract. §11.2 (settings UI) is explicitly post-v1 and does not appear.

- **Kokoro and read-back (§12).** Out of scope by the PRD's own binding
  instruction. Not a slice, not a deferred slice, not a note on a slice.

- **Seven slices rather than the 3–5 bias.** The bias was widened deliberately:
  the input is an entire product specification spanning six phases and roughly
  a dozen technical decisions, not a single feature. Compression below seven
  would require merging S2 and S3 (which forfeits the permission-surface split
  that is this record's clearest finding) or dropping S4 (which buries the
  constraint-scheduling contradiction as a footnote). S7 is the most compressible
  slice if the human wants a shorter record.
