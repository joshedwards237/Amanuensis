---
spec: AMANUENSIS_PRD.md
scope: amendments dated 2026-07-31 only
date: 2026-07-31
mode: spec
diaboli_model: claude-opus-5[1m]
objections:
  - id: A1
    category: implementation
    severity: critical
    claim: "The 2026-07-31 tier redefinition makes Phase 1's 'Rejects if' unreachable — Tier A is defined as 'measures inside G1's budget', so a machine cannot be both Tier A and miss G1, and a Tier B miss explicitly does not reject."
    evidence: "§7.2: 'Tier A — the selected model transcribes a 10-second utterance inside G1's budget on this machine.' §9 Phase 1: 'Rejects if: G1 is missed on a Tier A machine. A Tier B miss does not reject.' §10: 'the Phase 1 gate remains the real go/no-go... A miss here does stop the project.'"
    disposition: accepted
    disposition_rationale: "Verified against the PRD text before disposition. Tier A is redefined as an absolute measured bar (p50 <= 350 ms, p95 <= 700 ms, transcription share, VAD on) rather than a restatement of G1, and Phase 1's reject line now gates G1 on the machine the phase is built on, whatever tier it recorded. The tier became a recorded fact, not a gate condition."
  - id: A2
    category: premise
    severity: critical
    claim: "§9's Phase 5 section and §7.5 both contradict the feasibility record they cite: §9 schedules a design that record calls 'not shippable as scoped', and §7.5 still states Phase 5 is deferred."
    evidence: "§9: 'Feasibility is measured, not assumed... resolves self-corrections correctly at 278–390 ms.' phase5-feasibility.md: 'Answer: technically yes, but NOT with this design... it fails catastrophically', 'WER 19.6% → 110.0%', 'missed by 3×'. §7.5: 'This is not resolved now because Phase 5 is deferred (§9) and nobody is building against it.'"
    disposition: accepted
    disposition_rationale: "Verified. Phase 5 is now recorded as UNRESOLVED and corpus-blocked, carrying the four experiment results and the reason they are inconclusive rather than negative. Section 7.5's 'deferred, nobody is building against it' is corrected in place with a note on why both clauses were false when written."
  - id: A3
    category: implementation
    severity: high
    claim: "§7.2's re-derived model = \"auto\" table still selects base.en for the only v1 execution path, while the same-day benchmark records tiny.en + VAD as the only candidate meeting G1 — and the accuracy figure that would arbitrate lives in two irreconcilable aggregates."
    evidence: "§7.2 table: '| Apple Silicon / CPU | base.en, int8 | 352 ms |'. Revision log 2026-07-31: 'with it, tiny.en passes both p50 (328 ms) and p95 (420 ms).' phase5-feasibility.md: 'tiny.en with VAD is the only ASR candidate inside G1.' HANDOFF.md: 'tiny.en... has the worst WER (14.8%)' vs the same file's fixture line 'mean 19.62%'."
    disposition: accepted
    disposition_rationale: "Verified. The model = auto table now selects tiny.en + VAD at 328 ms p50 / 420 ms p95 for a single collapsed macOS row, with the still-provisional warning retained and strengthened. WER is declared macro-average throughout; the 14.8 percent micro-weighted figure is withdrawn."
  - id: A4
    category: specification quality
    severity: high
    claim: "The install-time tier check — the mechanism the whole tier redefinition rests on — is specified only by reference to the probe, which was a warmed median of five runs on one pre-recorded clip, with no p95, no VAD, and no injection stage."
    evidence: "§7.2: 'The tier is decided once, at install, by running the same measurement the pre-Phase-0 probe ran.' probe.md: 'Median of 5 runs, warmed, beam_size=1... This is transcription only.' Revision log: 'base.en on a 25 s sample takes 6,039 ms without VAD and 541 ms with it.'"
    disposition: accepted
    disposition_rationale: "Resolved together with A1, whose fix required specifying the install check to state what it compares against. Section 7.2 now fixes the audio, VAD state, warm-up, run count, model and comparison basis, and excludes model download from the timed measurement."
  - id: A5
    category: specification quality
    severity: high
    claim: "G1-CPU (p50 ≤ 2 000 ms) is presented as derived from §4's not-slower-than-typing bar, but that derivation licenses roughly 27 seconds, not two; and the bar carries no p95 on the tier whose documented failure mode is the tail."
    evidence: "§2: 'A 10-second utterance is roughly 25 words; at 40 wpm that is ~37 seconds to type. Two seconds is comfortably inside that.' §2's own G2 note: 'a number presented as derived when it was inherited is worse than one labelled as a guess.' HANDOFF.md: 'Any latency figure entering the PRD carries p50 and p95, or is labelled a floor.'"
    disposition: pending
    disposition_rationale: null
  - id: A6
    category: implementation
    severity: high
    claim: "The Half-Sync/Half-Async model names a pattern but leaves its handoff contract unspecified: end_session() returns a mutable session another thread populates, with no completion signal, no synchronisation rule, and a second queue that is described but not named."
    evidence: "§6.3: 'end_session() hands the buffer to the worker and returns... the session object, populated asynchronously — callers observe completion through the session, not by the call returning.' §6.3: '§6.2's AudioCapture ring buffer is already that queue' vs the table's 'one worker thread, draining sessions'."
    disposition: accepted
    disposition_rationale: "Verified against Phase 0 code committed the same day, which had encoded the defect faithfully. DictationSession gains a threading.Event with a stated write-then-signal ordering rule and a wait() method; the two queues are now named separately; and the overlapping-session hazard is resolved for v1 by declining to inject when the focused application changed between capture and injection."
  - id: A7
    category: risk
    severity: high
    claim: "The retain = false temp-file path reproduces the defect it was written to fix — unlink() no more erases bytes than DELETE does — while adding an orphan class on failed injection that no purge command reaches, and removing the recovery interface §8's guarantee exists for."
    evidence: "§5.5: 'written to a 0600 temp file and unlinked once injection succeeds', rejecting SQLite DELETE because it 'marks pages free for reuse rather than erasing bytes'. §8: 'If injection fails the user can still recover their words.' §5.5: 'manu history --purge wipes it' (the DB)."
    disposition: pending
    disposition_rationale: null
  - id: A8
    category: specification quality
    severity: medium
    claim: "cpu_threads = \"auto\" branches on operating system, not on whether the sysctl it names exists, leaving no defined value for macOS machines without performance-core levels — and its failure direction is the library default of 4 that produced the probe's NO-GO."
    evidence: "§7.2: 'On macOS that is sysctl -n hw.perflevel0.logicalcpu; elsewhere, physical cores.' §3: v1 is macOS-only. probe.md: 'The first run measured 4,413 ms and returned NO-GO. That was CTranslate2 defaulting to 4 threads.'"
    disposition: pending
    disposition_rationale: null
  - id: A9
    category: specification quality
    severity: medium
    claim: "The tier redefinition was applied in §2 and §7.2 but not in §4, §7.5, §9's probe gate or §9's Phase 4 README instruction, all of which still key on 'accelerated hardware' — a category §7.2 now says does not exist on the only v1 platform."
    evidence: "§4 (amended 2026-07-31): 'G1's budgets bind on accelerated machines (Tier A, §7.2).' §7.5: 'on the same accelerated-hardware and measurement basis as G1.' §9 probe: 'Rejects if: ...on accelerated hardware.' §7.2: 'CTranslate2 has no Metal backend... macOS, the only v1 platform, has no CUDA at all.'"
    disposition: pending
    disposition_rationale: null
---

> **Provenance.** Produced by the `advocatus-diaboli` sentinel on 2026-07-31,
> scoped to the 2026-07-31 amendment set only. The 12 objections adjudicated on
> 2026-07-30 live in `amanuensis-prd.md` and are untouched; IDs here are A1–A9
> because O1–O12 are still referenced by name throughout the PRD.
>
> **A1, A2 and A3 were independently verified against the PRD text before this
> file was written.** The remaining six were not re-verified line by line.
> All dispositions are `pending` and only a human resolves them.

## A1 — implementation — critical

### Claim

The 2026-07-31 revision of objection O1 moved the tier boundary from *what chip* to
*what measured*. In doing so it defined Tier A by the very predicate the Phase 1 gate
then tests, which makes that gate's rejection condition unreachable — and Tier B was
already exempt. The project's top risk therefore has a mitigation with no failing
state.

### Evidence

> **Tier A** — the selected model transcribes a 10-second utterance inside G1's
> budget on this machine. **G1 binds and is gated.**
> **Tier B** — it does not. (§7.2)

> **Rejects if:** G1 is missed on a Tier A machine. A Tier B miss does not reject; it
> is recorded and published. (§9, Phase 1)

> | G1 unachievable on any hardware class | High | ...the Phase 1 gate remains the real
> go/no-go. A miss here does stop the project (§9). | (§10)

Phase 1 also *contains* the classifier: "Phase 1 also carries... the **install-time
tier check** that decides Tier A versus Tier B."

### Why this matters

Trace the two branches. A machine that measures outside the budget at the install
check is Tier B, and §9 says a Tier B miss does not reject. A machine that measures
inside it is Tier A — and Phase 1 has "no hotkey, no injection," so its `g1_ms`
contains transcription plus a post-processing step the probe measured as
sub-millisecond. Phase 1's measurement is a near-subset of the measurement that
assigned the tier. There is no third branch.

The steel-man for the current wording is that the two measurements are not identical:
the install check uses a pre-recorded clip and Phase 1 uses live mic capture with VAD,
so variance could produce a miss. That residual does not rescue the gate, for two
reasons. First, a reject condition satisfiable only by measurement noise is not a
design gate. Second, if the developer's own machine lands in Tier B — entirely
possible on an Intel Mac, and Tier B is where §4 says the target user
disproportionately sits — then §9 rejects on nothing at all, and the build proceeds
with **no gated tier**, which is verbatim the outcome the revision log says the
redefinition was made to prevent ("the old split would have left no gated tier at all
in v1").

Note also what this does to the phase ordering. Phase 2b's identical *Rejects if* line
**can** fire, because it measures the full path including injection. So the real
go/no-go has silently migrated from Phase 1 to Phase 2b, while §9's Phase 1 text still
carries "no later phase makes this faster" and §10 still names Phase 1 as the go/no-go.
The document now points the reader at a gate that cannot stop the project.

## A2 — premise — critical

### Claim

§9's Phase 5 section presents the LLM second pass as un-deferred, feasible, and scoped
— four constraints, a named class, an A/B gate against a 700 ms budget. The record it
cites concluded the opposite on the same day, after the section's summary was written.
Separately, §7.5 was never amended and still asserts Phase 5 is deferred. A reader
working from the PRD alone would schedule an implementation phase for a design that has
already been falsified.

### Evidence

The PRD:

> **Phase 5 — LLM second pass — UN-DEFERRED 2026-07-31** ... Feasibility is measured,
> not assumed... Summary: an MLX-backed `Llama-3.2-3B-Instruct-4bit` resolves
> self-corrections correctly at **278–390 ms**... **The blocker is fidelity, not
> latency.**

The cited record:

> **Answer: technically yes, but NOT with this design.** Measured end-to-end on real
> ASR output it fails catastrophically.
> | `tiny.en` (+VAD) | 19.6% | **110.0%** |
> **Latency was also understated**... measured `tiny.en` + cleanup ranged **373–2,201
> ms**... The 700 ms Phase 5 budget is not marginally missed; it is missed by 3×.
> The feature is **not shippable as scoped**... it is a *generator* being asked to
> perform a *deletion*.

And, unamended, in §7.5:

> This is not resolved now because Phase 5 is deferred (§9) and nobody is building
> against it.

### Why this matters

Three distinct failures ride on this.

First, the PRD's Phase 5 gate — "A/B against Phase 3 output... Measure against Phase 5's
own budget — p50 ≤ 700 ms" — is scheduled against a number already measured at 3× over,
on the fastest hardware the product will see. The gate is pre-failed and the document
does not say so.

Second, §7.5's justification for leaving its budget unresolved is void: something *is*
being built against it. `HANDOFF.md` schedules four experiments to decide "what the LLM
second pass should be, or whether it should exist." That is the actual state of Phase 5
— an open research question with four untested candidates — and it appears nowhere in
the PRD. §9 records the reversal but not the reversal of the reversal.

Third, the four constraints are stated as things that "ship *with* the feature." The
record is stronger and more useful than that: the constraints were written from three
hand-written cases *before* the real test, and they caught 100% of the catastrophic
failures — which is evidence that a deterministic checkable property (deletion-only)
is doing the work, not the model. The PRD carries the constraints without carrying the
finding that made them the load-bearing part, so a future implementer could reasonably
swap the model and keep the prompt while discarding the checks.

§8's NFR table inherits the same problem at smaller scale: "measured 3.43 s with
`tiny.en` + `Llama-3.2-3B-4bit` both loaded" imports a number from a configuration the
same record says will not ship.

## A3 — implementation — high

### Claim

§7.2's `model = "auto"` table was re-derived from measurement on 2026-07-31 and still
selects `base.en` for the only execution path v1 has. Later the same day, with VAD in
the picture, `tiny.en` was recorded as the only candidate meeting G1. The PRD's stated
default and the project's stated finding disagree, and the accuracy evidence that would
arbitrate is itself reported in two different aggregates.

### Evidence

§7.2, after the amendment:

> | Apple Silicon / CPU | `base.en`, int8 | **352 ms** | *measured*, M3 Max, n=1 |
> | Slower CPU | `tiny.en`, int8 | **190 ms** | *measured*, M3 Max, n=1 |

> Benchmark it in Phase 1 against `base.en` — not `small.en`...

Later the same day:

> Without VAD **no candidate model passes G1's p95**; with it, `tiny.en` passes both
> p50 (328 ms) and p95 (420 ms). (revision log)

> `tiny.en` with VAD is the only ASR candidate inside G1. (`phase5-feasibility.md`)

> **`tiny.en` is the only model meeting G1** and has the worst WER (14.8%).
> (`HANDOFF.md`)

And on the accuracy side, in the same handoff document: the frozen fixture's mean raw
WER is **19.62%** — which is the arithmetic mean of the six per-sample figures in
`experiments/asr-baseline.json` (3.33, 18.97, 31.91, 2.04, 18.6, 42.86). The 14.8%
figure is not that mean. The most likely explanation is a word-count-weighted
aggregate, which the six-word `06-short` sample at 42.86% would pull down hard.

### Why this matters

The 352 ms that keeps `base.en` in the table is a no-VAD figure from a single clip.
The measurement that dethroned it added the one thing §7.4 now calls "the dominant
latency lever." §7.2 was amended for exactly this class of error — a table row that
was "a model-card guess and it was wrong by roughly 7×" — and the amended table now
carries the same defect one iteration later: a number measured under conditions the
product will not run in. The two rows are also inverted with respect to the finding:
the model that meets G1 sits in the "Slower CPU" row, and the model assigned to the
faster row does not.

The WER discrepancy compounds it rather than resolving it. Macro-average and
micro-average WER are both legitimate; using them interchangeably across the records
that feed a model-selection decision is not. 14.8% and 19.6% differ by a third
relative, and the open question `HANDOFF.md` poses — "whether cleanup compensates for
weaker ASR" — is answered against whichever one is picked. This is not on the
seven-item known-risks list.

Two secondary items follow. The table's row labels — "Apple Silicon / CPU" versus
"Slower CPU" — are undefined categories after §7.2's own text collapsed them ("'Apple
Silicon' and 'CPU only' are the same execution path"). Nothing states where the
boundary falls, yet the install-time tier check needs "the selected model" before it
can run, which means it needs this table resolved first. And §8's cold-start row is
already measured against `tiny.en`, so the PRD names two different defaults in two
sections.

## A4 — specification quality — high

### Claim

The install-time tier check is the mechanism the entire tier redefinition rests on, and
it is specified by a single sentence of reference to a deleted throwaway script. What
that script did — warmed, median of five, one pre-recorded clip, transcription only, no
VAD — is not what a per-user install check can or should do, and the difference decides
which users get a gated promise.

### Evidence

> The tier is decided **once, at install**, by running the same measurement the
> pre-Phase-0 probe ran, and recorded. (§7.2)

> Median of 5 runs, warmed, `beam_size=1`, `cpu_threads=10`, 10-second utterance...
> **This is transcription only.** G1 is `g1_ms` = transcribe + postprocess + inject.
> (`probe.md`)

> `base.en` leaves roughly 50 ms of the p50 budget for the other two stages.
> (`probe.md`)

> Measured: `base.en` on a 25 s sample takes **6,039 ms** without VAD and **541 ms**
> with it; `small.en` goes 23,886 → 1,438 ms. (revision log)

### Why this matters

Six things are undetermined, and each changes who lands in Tier A: what audio the check
transcribes (a bundled clip? the user's voice? a clip recorded in the user's room?);
whether the model must be downloaded first (185 s in the probe, on the install path);
whether warm-up runs first; how many runs; whether VAD is applied; and whether the
result is compared against the full `g1_ms` budget or only the transcribe share of it.

That last one is not a detail. The check measures transcription and the budget it is
compared against covers three stages. On the probe's own numbers the residual is ~50 ms
against a 400 ms p50 — so a machine measuring 380 ms transcribe is classified Tier A
and then ships a gated promise it will miss in normal operation. The classification is
systematically biased toward the tier that carries the guarantee.

And the check is a median. The evidence in this repo says the tail is where this
product dies: decoder repetition looping turned a 541 ms case into 6,039 ms on the same
model and the same sample. A single warmed median cannot see that, and it is being used
to decide whether a user's machine is one G1 binds on.

## A5 — specification quality — high

### Claim

G1-CPU is introduced with an explicit disclaimer that "the number should not be a
guess," followed by an arithmetic that does not produce it. The typing comparison, taken
at face value, licenses a latency an order of magnitude larger; 2 000 ms is chosen on
feel and dressed as derived — the precise failure §2's own G2 note names two paragraphs
earlier. It is also p50-only, on the tier where the tail is the documented hazard.

### Evidence

> The derivation, since the number should not be a guess: §4's own bar is that the tool
> must not be "slower than typing." A 10-second utterance is roughly 25 words; at 40 wpm
> that is ~37 seconds to type. Two seconds is comfortably inside that while still
> reading as a tool rather than a batch job. (§2)

> ...a number presented as derived when it was inherited is worse than one labelled as
> a guess. (§2, G2 note)

> Any latency figure entering the PRD carries **p50 and p95**, or is labelled a floor.
> (`HANDOFF.md`)

### Why this matters

The arithmetic is correct and the inference is not. If the standard is "faster than
typing the same content," the user has already spent the 10 seconds speaking, so the
comparison is 10 s + latency against ~37 s — which would justify anything under about
27 seconds. The clause that actually carries the decision is "while still reading as a
tool rather than a batch job," which is a judgement, not a derivation. §2 is candid
about G2's 5% being inherited; it is not candid about this one, and it is the newer of
the two.

The consequence is not academic. G1-CPU is the drop-the-tier threshold: "A Tier B
machine class that misses this is dropped in §3 rather than shipped." A ship/no-ship
decision for the majority of §4's stated audience turns on a number nobody can defend
the derivation of, and the PRD marks it *provisional* while §9 gives Phase 1 no
instruction to re-derive it — only to "confirm or move" it.

The missing p95 is the sharper half. Tier B runs a smaller model on slower hardware,
which is where a repetition-looping excursion is most likely and most costly. A
p50-only bar cannot fail on the failure mode this repo has already measured. That
combination — a threshold that decides shipping, stated only at the median — is the
same shape as the finding that a p50 from one clean sample said GO while the p95 said
the opposite.

## A6 — implementation — high

### Claim

The concurrency amendment names Half-Sync/Half-Async and assigns threads, then leaves
the handoff contract — the part of the pattern that is actually hard — unstated.
`end_session()` returns a mutable object another thread writes to, with no completion
signal, no synchronisation rule, and no ownership boundary. The queue the pattern
requires is asserted to be one that holds a different kind of thing.

### Evidence

> `end_session()` hands the buffer to the worker and returns; it does not wait for
> transcription. The `-> DictationSession` return in the contract above is the session
> object, populated asynchronously — callers observe completion through the session,
> not by the call returning. (§6.3)

> §6.2's `AudioCapture` ring buffer is already that queue. (§6.3)

> | Transcription, post-processing, injection | one worker thread, draining sessions |
> (§6.3)

`DictationSession` (§6.3) is a plain mutable dataclass with no completion flag, no
event, and no lock.

### Why this matters

"Callers observe completion through the session" describes an interface that does not
exist. There is no `is_complete`, no future, no callback, and no condition variable in
the contract — so the only available reading is polling a mutable dataclass across a
thread boundary, which is the thing the pattern is chosen to avoid. The tray needs to
know when to leave the *transcribing* state; §6.3 gives it `is_loaded` on the engine
and nothing on the session.

The queue claim is separately wrong in kind. The ring buffer carries audio frames from
the PortAudio callback; the table describes a worker draining *sessions*. Those are two
queues with different producers, different element types and different backpressure
behaviour, and only one is named. Half-Sync/Half-Async is cited as though it settles a
design that it has instead been used to label.

One consequence follows directly from making `end_session()` non-blocking, and the PRD
does not address it: sessions can now overlap. With a single serial worker, a user who
dictates twice in quick succession — or in `toggle` mode — can have session N's text
injected after focus has moved to a different application, because injection targets
whatever is focused at inject time, not at capture time. Under §5.2's `vad_auto` mode,
which §5.2 itself calls "the mode most likely to misfire," this is a routine path. §8's
persist-before-inject guarantee saves the words; it does not stop them from landing in
the wrong window.

## A7 — risk — high

### Claim

The `retain = false` path was changed to avoid relying on SQLite `DELETE` because
deletion marks pages free rather than erasing bytes. `unlink()` has exactly that
property. The amendment also creates an orphan class that no command reaches, and
removes any interface through which §8's crash guarantee can be exercised.

### Evidence

> When `retain = false`, the pre-injection transcript is written to a `0600` temp file
> and unlinked once injection succeeds — it never enters `history.db` at all. (§5.5)

> The earlier reading was write-then-`DELETE` in SQLite, which makes "nothing persists"
> a privacy claim resting on a statement that marks pages free for reuse rather than
> erasing bytes. (§5.5)

> Note the crash-order requirement: persist first, inject second. If injection fails the
> user can still recover their words. (§8)

> `manu history --purge` wipes it. (§5.5 — "it" being `history.db`)

### Why this matters

On a journalling copy-on-write filesystem, `unlink()` drops a directory entry and
releases blocks for reuse. That is the same guarantee `DELETE` gives, at a different
layer. The amendment's stated reason for the change — that the mechanism did not
support the claim "nothing persists" — applies unchanged to the mechanism that replaced
it. What the change *does* buy is real and worth keeping (the shared, long-lived
database no longer becomes load-bearing for a privacy promise), but the record now
reads as though the claim was repaired when the property was moved.

Two gaps are new. **Orphans:** the file is unlinked "once injection succeeds." Injection
failing is the case the whole ordering exists for, and §7.3 documents injection failing
in Electron and Java apps as a known hazard. Every failed injection, and every crash
between write and unlink, leaves a plaintext transcript behind. `manu history --purge`
wipes the database; nothing in §5.5 says it touches this location, and nothing says
where the location is — which also puts it outside §7.3's portability-floor item 2
requiring paths to resolve through `platformdirs`. The privacy-motivated user who set
`retain = false` is the one accumulating them.

**Recoverability:** §8 promises the user can recover their words when injection fails.
With `retain = true` that promise is discharged by `manu history`. With `retain = false`
the artefact is an unnamed temp file the user is never told about and no command
surfaces. The guarantee is mechanically preserved and practically unavailable, which
lands hardest on §4's secondary user — the one for whom "a dropped transcription is not
a minor annoyance."

## A8 — specification quality — medium

### Claim

`cpu_threads = "auto"` resolves by branching on operating system rather than on whether
the facility it names is present, leaving no defined value for macOS machines without
performance-core levels — and the undefined case falls back to the library value that
produced the probe's NO-GO. The rule is also generalised from a single 10P/4E machine.

### Evidence

> `cpu_threads = "auto"` resolves to the **performance-core count**... On macOS that is
> `sysctl -n hw.perflevel0.logicalcpu`; elsewhere, physical cores. Efficiency cores are
> deliberately excluded. (§7.2)

> The first run measured **4,413 ms** and returned NO-GO. That was CTranslate2
> defaulting to 4 threads on a 14-core machine. (`probe.md`)

> 10 was not tuned beyond "match the performance-core count" and is not claimed optimal.
> (`probe.md`)

### Why this matters

§3 makes macOS the only v1 platform, so "elsewhere" covers no shipping configuration.
The `hw.perflevel*` sysctls describe heterogeneous core clusters; a macOS machine
without that topology has no `perflevel0` to query. The spec's branch is on OS, so that
machine falls into the branch that does not apply, and the most likely implementation
outcome is the CTranslate2 default of 4 — the exact value the probe caught returning
NO-GO. A defaulting rule whose undefined case lands on the known-bad value is worth one
sentence to close.

The generalisation is the second half. "Exclude efficiency cores" was measured once, on
a machine with ten performance cores, where discarding four E-cores costs 29% of the
core count. On a 4P/4E machine it discards half, and per §4 that machine belongs to a
user in Tier B — the tier with no p95 bar (A5) and the smaller model. The rule is
plausible; it is being shipped as a default from n=1, on the axis where n=1 has already
been wrong twice in this project.

## A9 — specification quality — medium

### Claim

The tier redefinition was applied in §2 and §7.2 and not propagated. Four other
locations — one of them itself amended on 2026-07-31, one of them a gate's rejection
condition, one a README instruction — still key on "accelerated hardware," a category
§7.2 now states does not exist on the only v1 platform.

### Evidence

> G1's budgets bind on accelerated machines (Tier A, §7.2)... (§4, amended 2026-07-31)

> ...on the same accelerated-hardware and measurement basis as G1. (§7.5)

> **Rejects if:** transcription of a 10-second utterance takes longer than the CPU-tier
> bar in §2 on *accelerated* hardware. That would mean the accelerated path is slower
> than the floor set for the unaccelerated one... (§9, probe)

> The README also carries the **per-tier latency table** — the accelerated G1 figures
> and the CPU-tier G1-CPU figure... (§9, Phase 4)

Against:

> **CTranslate2 has no Metal backend.** "Apple Silicon" and "CPU only" are the same
> execution path... And macOS, the only v1 platform (§3), has no CUDA at all. (§7.2)

### Why this matters

This is not vocabulary drift. The probe's *Rejects if* line — added the same day, by
choice-story #12, specifically because it was the one gate lacking one — is now
unevaluable: it conditions on a hardware class the document says has no members. The
gate ran anyway, so the cost is retrospective there, but it sets the pattern for how a
reject line survives an amendment.

Forward-looking, §7.5 pins Phase 5's budget basis to "accelerated hardware," and §9's
Phase 4 instructs the README to publish "the accelerated G1 figures" — a user-facing
claim about a distinction the product does not make. §4's amendment is the most
consequential, because §4 is where choice-story #8 deliberately moved the tier split so
that it would be read as positioning: the positioning argument now rests on an axis
§7.2 retired. The correlation §4 asserts (privacy-motivated users get the slower tier)
may well survive the move from accelerator to core count, but the paragraph does not
make that argument — it makes the old one.

## Explicitly not objecting to

- **Idle RSS < 1.5 GB versus a 1.8 GB second resident model.** A real defect, but it is
  item 5 on `HANDOFF.md`'s known-risk list and §8 already carries a **Revisit** marker;
  restating it adds nothing.
- **G2 not being tier-aware.** Same reasoning — known-risk item 2, and it names its own
  fix (the O1 treatment on the accuracy axis).
- **The 6-sample, one-speaker corpus.** Known-risk item 6, and it states the right
  remedy ("more speakers would be worth more than more samples"). A5 and A3 lean on the
  *use* of thin evidence rather than on its thinness.
- **`warn_on_clipboard_manager` versus §5.3's new bounded exception.** The key silences
  the sole stated mitigation for a High risk in §10, which looks like the exception's
  own test firing. I decline it because §7.3 frames the key as an informed opt-out for
  users "who have read the README and accepted the trade," and §7.6's doctrine
  explicitly contemplates user action — that is a defensible reading, not an evasion.
- **Whether Phase 2's split into 2a/2b is the right seam.** The two-macOS-permissions
  argument is specific and well evidenced, and I could not construct a failure class the
  split leaves undetected.
- **The §7.0 Python decision and its rejected alternatives.** It is the strongest new
  section in the amendment set; the "probe ratifies the runtime if nobody decides" note
  pre-empts the objection I would otherwise have raised.
- **§7 "Where a decision goes."** It names its own unresolved tension (amend-in-place
  versus immutable ADRs) rather than claiming closure, so there is nothing to falsify
  that the section does not already concede.
