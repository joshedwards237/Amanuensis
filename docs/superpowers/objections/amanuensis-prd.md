---
spec: AMANUENSIS_PRD.md
date: 2026-07-30
mode: spec
diaboli_model: claude-opus-5[1m]
objections:
  - id: O1
    category: premise
    severity: high
    claim: "The PRD holds two incompatible premises about whether locality buys tolerance for slower or rougher output, and the Phase 1 kill gate resolves differently depending on which one is operative."
    evidence: "§1 'The differentiator is not features — it is that the audio never leaves the device' vs §4 'They will not tolerate a tool that is slower than typing' and §9 Phase 1 'If G1 is missed here, stop.'"
    disposition: pending
    disposition_rationale: null
  - id: O2
    category: premise
    severity: high
    claim: "The spec measures itself against a cloud competitor while listing two shipping local, open-source dictation tools as reading material, never establishing that the claimed differentiator is still unoccupied."
    evidence: "§1 'The product it is measured against is Wispr Flow'; §13 lists 'nerd-dictation (Linux) — the injection layer, done well' and 'Talon Voice' under 'Prior art to read before Phase 1'."
    disposition: pending
    disposition_rationale: null
  - id: O3
    category: alternatives
    severity: high
    claim: "§7.1 rejects streaming using arguments that apply only to on-screen partial results, and therefore never weighs speculative inference during the hold — the one design lever that directly attacks G1's clock."
    evidence: "§7.1 'it triples complexity — chunk boundary handling, hypothesis revision, partial-text injection and retraction'; §2 G1 measures 'from hotkey release'."
    disposition: pending
    disposition_rationale: null
  - id: O4
    category: alternatives
    severity: medium
    claim: "The go/no-go experiment for the project's hardest goal is scheduled after two phases of scaffolding, when a throwaway script would answer it in an hour."
    evidence: "§9 Phase 0 requires 'ruff + black + mypy strict, AppConfig with TOML load and validation, CLI skeleton, all ABCs defined' before Phase 1's latency measurement; §10 mitigation for the High risk is 'Phase 1 gate is explicitly a go/no-go.'"
    disposition: pending
    disposition_rationale: null
  - id: O5
    category: scope
    severity: high
    claim: "G3 — the goal that carries the entire product premise — is verified by no phase gate in §9."
    evidence: "§2 G3 'Zero network traffic at runtime | Verified by packet capture with the app under load'; no gate in §9 mentions packet capture or network verification."
    disposition: pending
    disposition_rationale: null
  - id: O6
    category: scope
    severity: high
    claim: "WindowsInjector and LinuxInjector are mandated by the architecture and the repository layout, built by no phase, and declared out of scope by no non-goal."
    evidence: "§6.2 lists 'MacOSInjector / WindowsInjector / LinuxInjector'; §6.4 requires 'injection/macos.py, windows.py, linux.py'; §9 Phase 2 builds 'MacOSInjector (or Windows, per §7.3)'; §3 non-goals list neither platform."
    disposition: pending
    disposition_rationale: null
  - id: O7
    category: specification quality
    severity: high
    claim: "G2 is stated as a WER threshold against an undefined corpus, and no phase in §9 measures WER at all."
    evidence: "§2 G2 '≤ 5% WER on clean desk-mic English'; §9 Phase 3 gate measures 'edit rate — what fraction of output needed manual correction'."
    disposition: pending
    disposition_rationale: null
  - id: O8
    category: specification quality
    severity: critical
    claim: "G1's measurement window excludes capture, but LatencyBreakdown.total_ms includes it and HARNESS.md directs latency tests at LatencyBreakdown — so the project's kill criterion is computed from an instrument that measures something else."
    evidence: "§2 G1 'from hotkey release to first character injected, for a 10-second utterance'; §6.3 LatencyBreakdown fields 'capture_ms ... total_ms'; HARNESS.md 'Latency assertions test against the G1 budgets in PRD §2 ... using LatencyBreakdown'; §7.1 sets the revisit trigger at 'realistic 15–30 second utterances'."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-30. G1 redefined as hotkey release to text FULLY PRESENT in the focused application, measured by a new LatencyBreakdown.g1_ms property (transcribe + postprocess + inject); total_ms retained for diagnostics only. Closes defect 1 (capture_ms in the instrument, outside the metric) and defect 3 (first-character undefined for atomic clipboard paste, and gameable under keystroke). Defect 2 — the 10 s goal versus the 15-30 s revisit trigger — is NOT closed by the redefinition and was resolved separately with an explicit precedence statement: G1 binds at 10 s, §7.1's 15-30 s is a distinct revisit signal, and neither overrides the other. Applied to PRD §2 (G1 row plus a new G1 measurement note), PRD §6.3, and the HARNESS.md test-framework line that had directed assertions at the unqualified instrument."
  - id: O9
    category: specification quality
    severity: high
    claim: "Three of six phase gates state an activity rather than a pass condition, so the document's primary control mechanism cannot fail on its own terms."
    evidence: "§9 Phase 2 'Report where it fails'; Phase 3 'Report edit rate'; Phase 4 'A second person installs it from the README without your help' — compare Phase 0's 'mypy --strict src/ is clean'."
    disposition: pending
    disposition_rationale: null
  - id: O10
    category: implementation
    severity: high
    claim: "The unconditional crash guarantee in §8 is implemented entirely by a subsystem that §5.3 lets the user switch off."
    evidence: "§8 'Crash behavior | Never lose a transcript — write to history before injection'; §5.3 '[history] enabled = true'; §5.5 'retain_days = 30'."
    disposition: pending
    disposition_rationale: null
  - id: O11
    category: implementation
    severity: high
    claim: "The LLM post-processing budget arithmetic is unsatisfiable against G1: the skip ceiling alone consumes 75% of the p50 budget, and neither §7.5 nor §9 Phase 5 states that G1 is relaxed when the pass is enabled."
    evidence: "§2 G1 'p50 ≤ 400 ms'; §7.5 'It also adds 200–500 ms, which directly threatens G1'; §5.3 'max_latency_ms = 300' with the comment that an over-budget pass is skipped rather than queued."
    disposition: pending
    disposition_rationale: null
  - id: O12
    category: risk
    severity: critical
    claim: "The default injection strategy routes every transcript through the system clipboard where third-party managers may capture and cloud-sync it, and G3's stated verification method structurally cannot detect that egress."
    evidence: "§5.3 injection strategy defaults to clipboard; §7.3 'the manager may capture the transcript before restore lands. This is a known, unavoidable leak'; §2 G3 'Verified by packet capture with the app under load'."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-30. Clipboard REMAINS the default — the §7.3 latency argument holds, and keystroke is slower and more failure-prone for exactly the §4 secondary user who can least afford it. The exposure is handled by making it visible rather than by changing the default: detect known clipboard managers at daemon start, surface a persistent tray indicator on the §5.4 precedent that a privacy-relevant condition must be visible without opening a menu, and gate it behind a new [injection] warn_on_clipboard_manager key. The detection list is explicitly incomplete and the README must say that absence of a warning means 'no known manager detected', never 'no manager present'. The G3 verification blind spot is treated as part of the same objection: §2's G3 row now scopes packet capture to this process only and points at §7.3 for the cross-process path. Applied to PRD §2 (G3 row), §5.3, §5.4, and §7.3."
---

## O1 — premise — high

### Claim

The PRD asserts that its differentiator is locality rather than features, and
simultaneously sets acceptance criteria at cloud-product parity with a hard kill
gate attached. These are two different premises about the same product, and the
Phase 1 go/no-go decision resolves differently depending on which one is live.

### Evidence

> §1: "The differentiator is not features — it is that the audio never leaves
> the device and the user owns the stack."

> §4: "They will not tolerate a tool that is slower than typing."

> §9 Phase 1: "**If G1 is missed here, stop and renegotiate §7.1 before
> continuing** — no later phase makes this faster."

§10 reinforces the tension from the other side: the mitigation for "G1
unachievable on CPU-only hardware" is that "CPU tier **may ship** with a smaller
model and a documented latency expectation rather than a broken promise" — which
is the locality-buys-forgiveness premise, contradicting the Phase 1 stop
instruction it is supposed to mitigate.

### Why this matters

Steel-manned, the position is coherent for one hardware tier: on Apple Silicon
and CUDA, locality costs nothing, so demanding parity is free and the honesty of
G1 protects users from a bad product. The problem is that the spec never says
G1 is tier-conditional, and §9 Phase 1's stop instruction is unconditional.

Two failures follow. If the parity premise governs, a CPU-tier miss halts a
project that would have shipped acceptably to privacy-constrained users who have
no fast alternative. If the locality premise governs, the Phase 1 gate cannot
fail — any miss is redescribed as "a documented latency expectation" per §10 —
and the project's only real quality control evaporates. The spec must say which
tiers G1 binds on, and what "stop" means when only one tier misses.

---

## O2 — premise — high

### Claim

The spec establishes the problem by naming a cloud competitor, then lists two
shipping local dictation tools in a reading list rather than a competitive
analysis. Nothing in the document establishes that the claimed differentiator —
local, open-source, user-owns-the-stack dictation — is still unoccupied.

### Evidence

> §1: "The product it is measured against is Wispr Flow. The differentiator is
> not features — it is that the audio never leaves the device and the user owns
> the stack."

> §13: "**nerd-dictation** (Linux) — the injection layer, done well" and
> "**Talon Voice** — the accessibility bar, and what a mature hotkey/injection
> layer handles."

The spec's own text credits nerd-dictation with doing the injection layer "well"
and Talon with a "mature hotkey/injection layer." Both are local. Both are the
two hardest components in §6.2. Neither is anywhere evaluated as an alternative
to building.

### Why this matters

Steel-manned: nerd-dictation is Linux-only and Talon is a voice-control system
with a different interaction model and licensing posture, so a gap plausibly
exists. But the spec never makes that argument, and §7's discipline — "Each
decision records the alternative rejected" — is applied to engines, injection
strategy, and VAD while the build-versus-adopt decision at the top of the tree
is never recorded at all.

If the gap is real, one paragraph closes this objection permanently and sharpens
the positioning. If it is not real, every downstream artefact is invalidated,
and the cheapest moment to discover that is now. This is also the objection most
likely to change §2: measuring against Wispr Flow produced G1 and G2; measuring
against the local field would likely produce different goals.

---

## O3 — alternatives — high

### Claim

§7.1's rejection of streaming is argued entirely from costs that arise only when
partial hypotheses are shown to the user. That argument does not reach the
adjacent option — running inference on buffered audio *while the hotkey is still
held*, displaying nothing — which attacks G1 directly because G1's clock starts
at release. The spec never weighs it.

### Evidence

> §7.1: "Streaming with partial hypotheses is what makes competitors feel
> instant, but it triples complexity — chunk boundary handling, hypothesis
> revision, partial-text injection and retraction — and Whisper-family models
> are not natively streaming."

> §2 G1: "from hotkey release to first character injected, for a 10-second
> utterance"

Of the three named costs, two (hypothesis revision, partial-text injection and
retraction) exist only because partial results are surfaced. Nothing is
surfaced before release in the design under §5.1, where injection is step 7 and
release is step 4.

### Why this matters

Steel-manned, §7.1 is a good decision well argued: batch is simpler, and chunk
boundary handling is a genuine cost that survives even without display. The
objection is not that batch is wrong — it is that the section's own framing
("Each decision records the alternative rejected") records a rejection of the
wrong alternative, so the reader cannot tell whether the cheaper variant was
considered and dismissed or simply not seen.

The consequence is concentrated at the Phase 1 gate. If G1 is missed, §9 sends
the project to "renegotiate §7.1," and the only option §7.1 has documented is
full streaming with retraction — the most expensive possible response. A project
that halts on latency without having weighed pre-release inference will either
kill itself prematurely or take on triple complexity it did not need.

---

## O4 — alternatives — medium

### Claim

The experiment that decides whether the project is viable is scheduled behind
two phases of production scaffolding. A materially cheaper sequencing exists,
and the spec does not weigh it — which is why the §10 mitigation reads as a
deferral rather than a mitigation.

### Evidence

> §10: "G1 unachievable on CPU-only hardware | High | Phase 1 gate is
> explicitly a go/no-go."

> §9 Phase 0: "Repo structure per §6.4, `pyproject.toml`, ruff + black + mypy
> strict, `AppConfig` with TOML load and validation, CLI skeleton, all ABCs
> defined with no implementations."

> §7.2: "these are pre-implementation estimates from the model cards, not
> measured on target hardware. Phase 1 exists to replace them with numbers."

### Why this matters

Steel-manned, the ordering is defensible: measuring latency inside the real
`AudioCapture` and `LatencyBreakdown` path produces numbers that reflect the
shipping architecture, and a throwaway benchmark can flatter itself by skipping
real capture and real model residency.

But the decision at stake is binary and coarse — does a target-hardware
transcription of ten seconds of audio complete in a few hundred milliseconds, or
in several seconds? A twenty-line script against a pre-recorded WAV answers that
to within an order of magnitude, and an order of magnitude is all the go/no-go
needs. Placing the answer after Phase 0 and most of Phase 1 means the cost of a
"no" is the entire scaffold plus the capture layer.

A gate is a mitigation when it can change the decision before the cost is
incurred. Here it is positioned after. The spec should either move a
throwaway latency probe ahead of Phase 0 or state explicitly that the Phase 0
scaffold is considered worth building regardless of the G1 outcome — which may
well be true, but is currently unstated.

---

## O5 — scope — high

### Claim

G3 is the goal that carries the product premise, it names its own verification
method, and no phase gate in §9 performs that verification or anything like it.

### Evidence

> §2 G3: "Zero network traffic at runtime | Verified by packet capture with the
> app under load"

The six gates in §9 verify, in order: CLI help and mypy cleanliness (Phase 0);
measured latency and an engine benchmark (Phase 1); injection across four
applications and clipboard restore behaviour (Phase 2); edit rate over ten
dictations (Phase 3); a second person installing from the README (Phase 4); an
A/B on LLM output quality (Phase 5). None captures packets. None inspects
network behaviour at all.

### Why this matters

The gap is not that the code will make network calls deliberately — §7.6 is
clear that it must not. It is that the dependency surface makes silent egress
the default failure mode: `faster_whisper` and Hugging Face tooling resolve
model repositories over the network unless explicitly pinned to a local
directory, ONNX runtime and tray toolkits pull their own transitive
dependencies, and any of these can attempt a fetch on a cache miss. §7.6 already
recognises the hazard ("Never at runtime") but attaches no verification to it.

The consequence is asymmetric. Latency misses are visible to the user and get
fixed. A silent model-repository HEAD request on daemon start is invisible,
survives to release, and is the one defect that falsifies the product's only
claimed differentiator. §11 lists four open decisions; "when is G3 verified" is
not among them, which suggests the omission is an oversight rather than a
deferral.

---

## O6 — scope — high

### Claim

Two of the three platform injectors are required by the architecture and the
repository layout, are produced by no phase, and are excluded by no non-goal.
The spec therefore has no consistent statement of which platforms v1 supports.

### Evidence

> §6.2: "TextInjector ← ABC / ├── MacOSInjector / ├── WindowsInjector / └──
> LinuxInjector"

> §6.4 requires `injection/macos.py`, `injection/windows.py`,
> `injection/linux.py`, and `injection/factory.py # platform detection →
> injector`.

> §5.1: "default: `Right Option` on macOS, `Right Alt` on Windows"

> §9 Phase 2: "`MacOSInjector` (or Windows, per §7.3)"

> §3 non-goals: lists mobile, but neither Windows nor Linux.

§7.3 frames the choice as scheduling — "the ABC makes this a scheduling
decision, not an architectural one" — but §9 contains no later slot in which the
other platforms are scheduled.

### Why this matters

Steel-manned, the ABC genuinely does make the second platform cheap relative to
the first, and shipping macOS-only v1 is an entirely reasonable scope. The
objection is that the spec does not say that. Three readers get three answers:
that v1 is macOS-only (from §9), that v1 is tri-platform (from §6.2 and §6.4),
or that it is macOS-plus-Windows (from §5.1's dual hotkey defaults).

Concrete consequences: `factory.py` must decide what to do on an unsupported
platform, and the spec gives it no rule; the Phase 4 README must state supported
platforms, and the spec gives it no answer; §6.4 mandates two files that Phase 5
ends with empty, which directly damages G5 — a reader who opens
`injection/linux.py` and finds a stub learns that the layout does not describe
the product. If Windows and Linux are post-v1, they belong in §3. If they are in
v1, they need a phase.

---

## O7 — specification quality — high

### Claim

G2 sets a numeric accuracy threshold against a corpus that does not exist and is
not described well enough to construct, and no phase in §9 measures the metric
G2 is stated in.

### Evidence

> §2 G2: "Transcription is accurate enough to not require editing | ≤ 5% WER on
> clean desk-mic English"

> §9 Phase 3 gate: "Ten real dictations of ≥ 60 seconds. Report edit rate —
> what fraction of output needed manual correction, and what kind."

"Clean desk-mic English" fixes neither corpus, speaker set, accent range,
utterance length, nor reference-transcript methodology. WER requires a reference
transcript; edit rate requires a human's judgement about what needed correcting.
They have different denominators and are not convertible.

### Why this matters

Steel-manned, §9 Phase 3's choice is arguably the better instrument: edit rate
measures what the user actually experiences, and WER punishes a model for
transcribing "gonna" where the speaker said "gonna." A dictation product that
optimises WER against read-aloud corpora can lose to one that optimises for
post-edit effort.

But then G2 is stated in the wrong unit, and the divergence is expensive.
Different implementers will operationalise "≤5% WER on clean desk-mic English"
as LibriSpeech test-clean (not desk-mic, read speech, flattering), Common Voice
(desk-mic, heavily accented, punishing), or ten self-recorded utterances
(n too small for a 5% threshold to mean anything). These differ by more than the
5% threshold itself, so the goal is satisfiable or unsatisfiable at the
implementer's discretion.

Worse, §7.2's engine choice depends on this. The Phase 1 gate requires an ADR
selecting between faster-whisper and Moonshine, a decision that trades accuracy
against latency — and the accuracy side of that trade has no defined
measurement. The ADR will be written on latency numbers and vibes.

---

## O8 — specification quality — critical

### Claim

G1's measurement window and the instrument the project builds to measure it do
not describe the same quantity. `LatencyBreakdown` includes a stage G1 excludes,
`total_ms` therefore cannot be compared to G1's budgets, and HARNESS.md
nonetheless directs the test suite to do exactly that. The project's kill
criterion is not operationally defined.

### Evidence

> §2 G1: "p50 ≤ 400 ms, p95 ≤ 800 ms **from hotkey release to first character
> injected**, for a 10-second utterance"

> §6.3: "`class LatencyBreakdown:` ... `capture_ms: float = 0.0` ...
> `@property def total_ms(self) -> float: ...`"

> HARNESS.md, Stack: "Latency assertions test against the G1 budgets in PRD §2
> (p50 ≤ 400 ms, p95 ≤ 800 ms) using `LatencyBreakdown`, which exists as a
> product requirement precisely so those targets are testable."

Three distinct defects compound here:

1. **`capture_ms` is inside the instrument and outside the metric.** For a
   ten-second utterance under the natural reading, `capture_ms` is
   approximately 10,000 ms, so `total_ms` is approximately 10,400 ms and an
   assertion of `total_ms <= 400` fails unconditionally. Under an alternative
   reading — buffer finalisation only — `capture_ms` is a few milliseconds. The
   spec does not say which, and the two readings differ by three orders of
   magnitude.

2. **The utterance length in the goal and in the revisit trigger disagree.**
   §2 fixes 10 seconds; §7.1 sets the escalation condition at "realistic 15–30
   second utterances." Whisper-family inference time scales with audio duration,
   so a result that passes at 10 s and fails at 30 s is both a G1 pass and a
   §7.1 trigger, with no stated precedence.

3. **"First character injected" is not defined for the default strategy.**
   §7.3 makes clipboard paste the default and describes it as atomic
   ("near-instant"); there is no first character distinct from the last. Under
   `strategy = "keystroke"`, first-character and last-character diverge by
   potentially seconds on a 300-character paragraph — and §7.3's own argument
   for rejecting keystroke is that it "is too slow for a 300-character
   paragraph," a slowness G1 is defined so as not to measure.

### Why this matters

This is rated critical because §9 Phase 1 converts this number into a
stop-the-project decision — "If G1 is missed here, stop" — and §10 rates
G1-unachievability as the top risk. A go/no-go computed from an undefined metric
is not a control; it is a coin flip whose bias is set by whichever reading the
implementer picked, and the implementer is the same person who wants the answer
to be "go."

Defect 3 additionally lets the metric be gamed without anyone intending to:
measuring to first character under a strategy §7.3 rejects for slowness reports
a fast number for a slow experience. The right fix is probably to define G1 as
release-to-text-fully-present, which is what the §4 user actually experiences,
but that is a decision for the human — the objection is that the current
definition cannot be implemented without one.

---

## O9 — specification quality — high

### Claim

The document's central control is the phase gate, and half the gates state an
activity to perform rather than a condition to meet. A gate with no pass
criterion cannot fail, which reduces §9 to discretionary approval by the person
whose work is being gated.

### Evidence

Gates with criteria:

> Phase 0: "`manu --help` runs, `mypy --strict src/` is clean, config loads and
> rejects a malformed file with a useful error."

Gates without:

> Phase 2: "Dictate into TextEdit, VS Code, Chrome, and a terminal. **Report
> where it fails.**"

> Phase 3: "Ten real dictations of ≥ 60 seconds. **Report edit rate** — what
> fraction of output needed manual correction, and what kind."

> Phase 4: "A second person installs it from the README without your help."

Phase 1 sits in between: "Report measured latency on your actual hardware
against G1" is a report, but the following sentence supplies the criterion
("If G1 is missed here, stop"). Phase 5 supplies a criterion but no threshold
("If quality gain does not justify measured latency cost").

### Why this matters

Steel-manned, exploratory gates are legitimate: nobody knows in advance which
Electron apps reject synthetic paste, so demanding a pass threshold at Phase 2
would either be arbitrary or would force a guess into the spec. "Report where it
fails" is honest about the state of knowledge, and §10 already anticipates that
some apps will fail without treating that as fatal.

The cost is that the report and the decision are never connected. Phase 2 can
report that injection fails in VS Code and Chrome — two of the four named
targets and a direct miss on G4, "Works in any focused application" — and
proceed, because the gate asked for a report and got one. Phase 3 can report an
edit rate of 30% and proceed, because no rate was declared unacceptable, and G2
supplies no help (see O7).

Phase 4's gate has a further problem specific to it: n=1, unrepeatable, no
success definition (installed? successfully dictated? within what time? after
how much silent struggle?), and no stated conduct rule for the observer. As
written it is satisfied by a friend who eventually gets there after an hour of
guessing, and failed by one who gives up in five minutes on a machine with an
unrelated Python problem. It measures the tester more than the README.

Each gate that reports rather than decides should state what result would cause
the phase to be rejected. That sentence is what makes it a gate.

---

## O10 — implementation — high

### Claim

The crash-safety guarantee in §8 is stated unconditionally and implemented
entirely by a subsystem that §5.3 exposes as a user-settable boolean. When a
user sets `enabled = false`, the guarantee has no mechanism, and the spec does
not say what happens.

### Evidence

> §8: "Crash behavior | Never lose a transcript — write to history before
> injection" and "Note the crash-order requirement: persist first, inject
> second. If injection fails the user can still recover their words."

> §5.3: "`[history]` / `enabled = true`"

> §5.5: "`manu history --purge` wipes it." / "`retain_days = 30`"

CLAUDE.md escalates the guarantee further, listing "Persist before injecting" as
a hard constraint with "a failure mode that is not recoverable by fixing it
later" — while also binding the implementer to "No hardcoded behaviour a user
might want to change," which is the rule that makes `enabled` a config key.
The two hard constraints collide on this exact key.

### Why this matters

Three readings are available to an implementer and the spec does not choose:
(a) `enabled = false` disables retention but a pre-injection write still occurs
and is deleted after injection succeeds — preserving the guarantee, contradicting
the plain meaning of the key; (b) `enabled = false` disables the write, silently
voiding a guarantee the user was never told depended on it; (c) `enabled = false`
is rejected at config load, contradicting §5.3's premise that every such
decision is user-settable.

Reading (b) is the likely default and the damaging one, because the user who
disables history is precisely the privacy-motivated §4 primary user, and the
user who most needs recovery after a failed injection is the §4 secondary user
with motor impairment. The design silently trades their safety net for their
privacy without telling either that the trade exists.

A related question the spec should answer at the same time: persist-before-inject
means the transcript is on disk before the user has seen it, so aborted and
misfired sessions are retained for 30 days by default. §5.3 defaults
`store_audio = false` on the reasoning that "audio is the sensitive artifact" —
but the transcript of what a user dictated into a password manager or a private
message is not obviously less sensitive than the recording of it. §7.6's `0600`
file mode addresses other local users, not the retention decision itself.

---

## O11 — implementation — high

### Claim

The latency budget for optional LLM post-processing cannot be reconciled with
G1. The skip ceiling alone is 75% of the p50 budget, the pass's own estimated
cost exceeds the ceiling at the top of its range, and neither §7.5 nor the
Phase 5 gate states that G1 is suspended when the pass is enabled.

### Evidence

> §2 G1: "p50 ≤ 400 ms, p95 ≤ 800 ms"

> §7.5: "It also adds 200–500 ms, which directly threatens G1. Therefore: **off
> by default, hard latency ceiling, and it is skipped rather than queued when it
> exceeds budget.**"

> §5.3: "`max_latency_ms = 300`", commented as meaning that a pass exceeding the
> ceiling is skipped rather than queued.

> §9 Phase 5 gate: "A/B against Phase 3 output on the same audio. If quality
> gain does not justify measured latency cost, ship it disabled and say so in
> the README."

### Why this matters

Steel-manned, the design intent is clearly right and well argued: §7.5's closing
line — "A dictation tool that sometimes takes 900 ms is worse than one that is
consistently 350 ms and slightly rougher" — is the correct instinct, and
skip-rather-than-queue is the correct mechanism. The objection is that the
numbers chosen do not implement the instinct.

The arithmetic: if the base pipeline lands at the p50 target of 400 ms, adding a
pass with a 300 ms ceiling produces 700 ms in the best case where the ceiling
holds. The ceiling is not a saving; it is a bound on the overrun. And the
mechanism has a cost on its own failing path — a pass that is abandoned at
300 ms has already spent 300 ms and produces nothing, so the worst case
(pay the full ceiling, discard the result) is strictly worse than either not
running it or letting it finish. §7.5 does not acknowledge that the skip path
costs the ceiling.

Two things need to be stated. First, whether skipping on budget overrun means a
cancellation deadline (the only implementable reading — you cannot know the cost
before paying it) or a predictive check (which would need a predictor the spec
does not describe). Second, whether G1 is defined with post-processing off. If
it is, say so in §2, because HARNESS.md currently treats G1 as an unconditional
test assertion. If it is not, Phase 5's deliverable violates G1 on every
invocation and the gate's "if quality gain does not justify measured latency
cost" is deciding a question §2 already answered.

---

## O12 — risk — critical

### Claim

The default injection strategy writes every transcript to the system clipboard,
where any installed clipboard manager may capture it and — for the common
managers that offer sync — transmit it off the device. §7.3 acknowledges the
capture and treats it as a clipboard-hygiene annoyance; it is in fact a direct
breach of the product's only stated differentiator, and G3's declared
verification method cannot detect it.

### Evidence

> §5.3: "`[injection]` / `strategy = "clipboard"`"

> §7.3: "**The cost, stated plainly:** it clobbers the user's clipboard.
> Mitigate by saving and restoring, but restoration races with clipboard manager
> apps — the manager may capture the transcript before restore lands. This is a
> known, unavoidable leak of the strategy, and it must be documented in the
> README rather than papered over."

> §1: "No account, no network, no audio leaving the machine."

> §2 G3: "Zero network traffic at runtime | Verified by packet capture with the
> app under load"

> §10: "Clipboard restore races with clipboard managers | **Medium** | Document
> it. Offer `keystroke` strategy. Do not claim it is solved."

### Why this matters

Steel-manned, §7.3 is the most intellectually honest passage in the document. It
names a cost, refuses to claim it is solved, provides an escape hatch, and
requires it in the README. That is better behaviour than most specs manage, and
the objection should not be read as accusing the spec of hiding anything.

The objection is about what kind of thing the leak is. §7.3 and §10 both frame
it as a race — restore versus capture — which makes it sound transient and
low-consequence. It is neither:

- The capture is not a race artefact but the normal operation of the class of
  app in question. A clipboard manager that did not capture the transcript would
  be broken. Restore timing (`restore_delay_ms = 150`) affects only whether the
  *previous* clipboard contents come back, not whether the transcript was
  recorded on the way through.
- Several widely used managers on the target platform offer cross-device sync.
  For those users, a transcript reaches another machine, and possibly a vendor's
  servers, as a direct consequence of the default configuration. §1's promise is
  scoped to audio ("no audio leaving the machine"), which is technically
  preserved — but the transcript is the thing the user actually cares about
  keeping private, and no reader of §1 will parse that distinction.
- G3's verification is "packet capture with the app under load." Amanuensis's
  own sockets stay silent; the egress happens in a different process. The
  project's headline privacy claim would be verified green while the leak is
  live. This is a verification blind spot, not merely an unmitigated risk.

Rated critical because it says the default should not ship as described. The
available responses are all cheap relative to the exposure: default to
`keystroke` for short transcripts with clipboard as an opt-in for long ones;
detect known clipboard managers at startup and surface the exposure in the tray
per §5.4's precedent; use a platform-specific transient/concealed clipboard type
where one exists; or narrow §1's promise and G3's verification to state
explicitly that transcripts transit the system clipboard by default. The one
response the spec currently specifies — a README note — asks the user to
understand a cross-process data flow in order to opt out of a default they were
told was private, and §4's secondary user, for whom the `keystroke` alternative
is also the slower and more failure-prone path, gets the worst of both.

---

## Explicitly not objecting to

- **Batch over streaming as the v1 decision (§7.1)**: the reasoning is sound and
  the complexity estimate is credible; O3 objects only to the alternative that
  the rejection argument fails to reach, not to the choice itself.
- **The ABC set in §6.2–6.3**: the spec justifies each abstraction by a real
  swap candidate rather than symmetry ("Every one of these exists because there
  is a real chance we replace the implementation"), which is the correct test,
  and Moonshine genuinely is that candidate for `TranscriptionEngine`.
- **Excluding Kokoro/TTS from v1 (§12)**: the reasoning is correct and the
  discipline is exactly right — read-back is a different product surface with a
  different failure model, and §12 both names the accessibility value and
  defers it explicitly rather than silently, which is the honest form of a
  deferral.
- **`AppConfig` as a singleton with `AppConfig.get()` alongside constructor
  injection into `DictationController` (§6.3)**: this is a testability
  irritation, not a structural flaw, and belongs at code-time review rather than
  spec-time.
- **The §7.6 security posture**: no telemetry, checksum-verified pinned model
  downloads, `0600` history, audio storage defaulting off, and no `eval`/`exec`
  of transcript-derived content are all correct and correctly scoped for a
  no-backend local product.
- **G5 ("a developer can read the codebase in an afternoon") being enforced by
  structure rather than measured**: the claim that §6's layout implies
  readability is unfalsifiable, but the goal is genuinely hard to operationalise
  and the layout is a reasonable proxy — this did not clear the evidence bar.
- **Displaced by the 12-objection cap, not by weakness**: (a) `model = "auto"`
  in §7.2 resolves to one of four models while §7.6 forbids runtime downloads
  and §11.3 defers distribution to Phase 4 — a user who edits `[engine] model`
  to an undownloaded model forces either a G3 violation or an unspecified
  failure; (b) §5.1 step 7 injects into "the focused application" 400–800 ms
  after release, with no requirement to capture focus at session start, so a
  focus change lands dictated text in the wrong window; (c) `max_duration_seconds
  = 300` under batch transcription implies a long unbounded wait with
  `abort_session` defined in §6.3 but bound to no hotkey, config key, or UI
  affordance; (d) §4's secondary user is said to "raise the bar on reliability"
  but no requirement, NFR, or gate in the document is traceable to that raised
  bar. Each of these has a real failure shape and would have been raised with
  more slots.
