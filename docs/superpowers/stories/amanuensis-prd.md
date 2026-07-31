---
spec: AMANUENSIS_PRD.md
date: 2026-07-30
mode: spec
cartographer_model: "claude-opus-5[1m]"
stories:
  - id: 1
    lens: [defaults, consequences]
    title: Python inherited from the ASR ecosystem
    disposition: pending
    disposition_rationale: null
  - id: 2
    lens: [patterns, forces]
    title: Unstated threading model now argues against alternatives
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-31: name the concurrency model in Phase 0. §6.3 now specifies it — Half-Sync/Half-Async, with tray on main (a macOS status item requires it), HotkeyListener on the OS event tap, AudioCapture on the PortAudio callback thread, and one worker draining transcribe -> post-process -> inject. §6.2's ring buffer was already the queue. The consequences are written as requirements rather than left implicit: DictationController must not block the event-tap thread, end_session() hands off and returns rather than waiting, and nothing touching UI runs off main. This also removes the force the story identified as most corrosive — §7.1 was using the unstated model as an argument against pre-release inference, so a deferral had started doing work in another decision. It is no longer a deferral. Adopted as item 1 of §7.3's portability floor, because only one row of that table (which thread the tray needs) is macOS-specific, which is what keeps a Windows port a port rather than a redesign."
  - id: 3
    lens: [coherence, patterns]
    title: AppConfig deferred to a nonexistent review mode
    disposition: pending
    disposition_rationale: null
  - id: 4
    lens: [patterns, alternatives]
    title: An ABC kept for an unscheduled port
    disposition: pending
    disposition_rationale: null
  - id: 5
    lens: [defaults, consequences]
    title: SQLite delete became a privacy mechanism
    disposition: pending
    disposition_rationale: null
  - id: 6
    lens: [forces, consequences]
    title: Config policy survived collision by redefining a key
    disposition: pending
    disposition_rationale: null
  - id: 7
    lens: [forces, consequences]
    title: Audio never stored, transcripts always written
    disposition: pending
    disposition_rationale: null
  - id: 8
    lens: [forces, consequences]
    title: Tier-conditional G1 splits promise from differentiator
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-31: positioning AND a CPU threshold. Both halves of the story are adopted. (1) POSITIONING — §4 now states that hardware splits the primary user group and that this is a positioning fact rather than an implementation detail, naming the tension the story identified: privacy motivation and offline constraint correlate with older, cheaper machines, so the users the product exists for are disproportionately the ones on the slower tier. §9 Phase 4 requires the README to carry a per-tier latency table labelled by hardware, in the same place it makes the speed claim. (2) THRESHOLD — the CPU tier gains G1-CPU, provisional p50 <= 2000 ms, and a tier that misses it is dropped in §3 rather than shipped. This closes the gap the story named precisely: §10's 'unusable rather than merely slow' was undefined in exactly the way objection O9 rejected for gates, leaving the CPU tier's ship/drop call as the one criterion in the document without a reject condition. The number is DERIVED rather than invented, from §4's own bar that the tool must not be slower than typing: a 10-second utterance is roughly 25 words, ~37 seconds at 40 wpm, so 2 seconds sits comfortably inside while still reading as a tool. Labelled provisional like G2's 5%; Phase 1 confirms or moves it with a stated reason."
  - id: 9
    lens: [forces, alternatives]
    title: Phase 5's budget was computed, not chosen
    disposition: pending
    disposition_rationale: null
  - id: 10
    lens: [patterns, coherence]
    title: A key documented to mean something else
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-31: rename to `retain`. The key now says what it does — `[history] retain = false` still writes the transcript before injection (§8, unconditional) and deletes it once injection succeeds. §5.5's instruction to read the key as retain-rather-than-use is deleted, because it is no longer needed. The story's argument is adopted as stated: the name is the interface, and the gloss would otherwise have had to survive translation into the README, the tray, any settings UI (§11.2) and every validation error message, each a fresh opportunity for the plain reading to win — and it is the kind of mismatch config validation structurally cannot catch, because nothing is invalid. Free to do now: Phase 0 has not started and no user has a config file. The continuity cost the story weighed on the other side is one day of drafts."
  - id: 11
    lens: [patterns, forces]
    title: Disclosure chosen over prevention, now twice
    disposition: pending
    disposition_rationale: null
  - id: 12
    lens: [coherence, consequences]
    title: The probe deletes its own instrument
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-31: write docs/gates/probe.md, delete the code. The probe stays throwaway as objection O4 intends — the exemption from §6.4 and HARNESS.md is deliberate and stays — but its ANSWER is now recorded: date, hardware, the model that `auto` resolved to, the input file, measured transcribe time, verdict, and the standing caveat that the number skips capture, residency, post-processing and injection and is therefore a floor. The story's argument is exactly right and is the same argument that produced docs/gates/ in the first place: O9 required every gate to leave a record because numbers living only in a conversation cannot be regressed against, and this is the number with the least surrounding context to reconstruct — it commits the project to the entire Phase 0 scaffold and would have been unreproducible an hour later. The story also caught that the probe was the one gate in §9 with no Rejects-if line; it now has one, keyed to the new G1-CPU bar, on the reasoning that an accelerated run slower than the unaccelerated floor is a broken setup rather than a slow result."
  - id: 13
    lens: [coherence, patterns]
    title: Six decision surfaces and a stale index
    disposition: accepted
    disposition_rationale: "Human decision, 2026-07-31: write the routing rule AND generate §14. (1) ROUTING — §7 gains a 'Where a decision goes' table splitting the six surfaces by granularity: §7 for product-level decisions, docs/adr/ for implementation-level, docs/gates/ for measurements and gate calls, docs/superpowers/* for review artefacts and their dispositions. The collision rule is stated — a gate record reports, an ADR decides, §7 governs — and applied to Phase 1, the first live collision, where §7.2, 0001-engine-selection.md and docs/gates/phase-1.md all claim the engine decision. The story's deeper point is NOT claimed as resolved and is recorded as a standing tension: §7's amend-in-place convention and Nygard's immutable-and-superseded discipline cannot both govern one decision, and the split by granularity keeps them apart rather than reconciling them. A decision migrating from implementation-level to product-level still has no rule. (2) §14 — the hand-maintained table is replaced by scripts/regenerate-sentinel-index.py, which parses each record's YAML frontmatter with the four-space indentation rule so prose occurrences of a disposition token are never counted. Wired into .github/workflows/harness.yml with --check, making it the first genuine constraint step that skeleton workflow has carried."
---

> **Second pass.** The first pass was drawn concurrently with the
> advocatus-diaboli run, before any objection had been adjudicated — a
> sequencing inversion that record flagged and §14 of the PRD repeats. That
> condition is now satisfied: all twelve spec-mode objections carry an accepted
> disposition, the PRD has thirteen revision-log rows dated 2026-07-30, and
> HARNESS.md's latency guidance has been rewritten with three qualifiers. This
> record replaces the first pass in full. Every story here cites objection IDs
> where they informed it; the first pass could cite none.
>
> **Disposition of the first pass's ten stories:**
>
> | First pass | Verdict | Now |
> |---|---|---|
> | #1 Python inherited from the ASR ecosystem | stands | #1 |
> | #2 Blocking controller API for a concurrent daemon | changed | #2 |
> | #3 AppConfig is singleton and injected dependency | changed | #3 |
> | #4 One ABC rationale over three different jobs | changed | #4 |
> | #5 Python 3.11, TOML and SQLite are one decision | changed | #5 |
> | #6 Configurability over opinionation, stated as policy | changed | #6 |
> | #7 Audio off by default weighs only privacy | changed | #7 |
> | #8 Platform order by permission difficulty, not users | **resolved** (O6) | retired |
> | #9 Human gates on machine-checkable targets | **resolved** (O9) | retired |
> | #10 Four decision records, no routing rule | **superseded** | #13 |
>
> Two retirements, and both are clean. O6 made v1 macOS-only, moved Windows and
> Linux to §3, resolved §11.1, and recorded in §7.3 the two caveats the story
> raised — that the ABC covers injection only, and that the hotkey listener, the
> tray and the `manu toggle` socket are platform-shaped with no factory. §11.1
> goes further than the story did: "§7.3's 'swap the order freely' claim was
> never tested, and is now not relied upon for v1." O9 gave every gate a *Rejects
> if* line and required `docs/gates/phase-<n>.md`, which was story #9's exact
> consequence — its own rationale credits "objection O9 and choice-story #9".
> Neither decision is silent any longer, so neither needs a map.
>
> Story #10 is superseded rather than resolved: nothing addressed the
> PRD-amendment-versus-ADR routing question, and the amendments added two further
> surfaces (`docs/gates/`, §14) while it stood. The replacement is #13.

## Story #1 — Python inherited from the ASR ecosystem

**Source:** `AMANUENSIS_PRD.md` (§8 Non-functional requirements)
**Lens:** defaults, consequences
**Refs:** —

**Context.** Unchanged across thirteen revisions. §8 still states "Python |
3.11+" as a table row between "Idle CPU < 1%" and "Recovery from mic
disconnect". §7 now records rejected alternatives for streaming, pre-release
inference, engines, injection, VAD, post-processing, platform scope, history
semantics and two latency budgets — and still records nothing for the language
all of it runs inside. Twelve objections were adjudicated and none touched it.

**Forces.** The ASR tooling is Python-first: faster-whisper/CTranslate2, ONNX
Runtime for Silero, sounddevice over PortAudio, llama.cpp bindings. Python
minimises integration cost and is what keeps §7.2's engine swap a scheduling
decision. Against it: a resident daemon holding a real-time audio callback, a
hotkey listener, a tray run loop and an inference call is a concurrency problem,
and Python is the language in which concurrency costs the most reasoning per
line. The PRD resolved toward integration cost, silently, and the amendments did
not revisit it.

**Options not taken.** (a) A Rust or Go core with Python confined to inference
behind FFI or a subprocess — whisper.cpp and nerd-dictation, both on §13's
required-reading list, sit on the other side of this line. (b) A Swift-native
macOS app calling Core ML or whisper.cpp directly, which the move to macOS-only
(O6) makes materially more attractive than it was on the first pass: the
portability cost of a native app has just been written off as a non-goal. (c)
Python for orchestration with the hot path as a compiled extension.

**Choice as written.** Python, by assertion in a table. The spec chose the
language by not treating the language as a choice — and O6's narrowing to a
single platform removed the strongest remaining argument for the choice without
reopening it.

**Consequences.** This remains the least reversible commitment in the document.
Every §7 decision sits behind an ABC; the runtime sits under all of them. §9's
new pre-Phase-0 probe will produce the project's first real latency number
(story #12) using this runtime, and a "go" on that probe ratifies the language
without anyone deciding to.

**Pattern.** — . A platform commitment, not a design pattern. The
orchestration-language / hot-path-language split is the nearest named thing, and
§13's two exemplars resolve it in opposite directions.

**Notes.** The user's standing engineering conventions declare Python the
default backend language across all projects. Worth confirming whether that
default, rather than anything specific to Amanuensis, is the source.

## Story #2 — Unstated threading model now argues against alternatives

**Source:** `AMANUENSIS_PRD.md` (§6.3 Class contracts, §7.1 pre-release inference)
**Lens:** patterns, forces
**Refs:** #1, O3

**Context.** §6.3 still gives `DictationController` three blocking-shaped
methods and the PRD still names no threading model, event loop or async
strategy. What changed is that the silence has acquired a job. §7.1's new
pre-release-inference paragraph rejects that alternative partly because "it adds
a concurrency burden to a daemon whose threading model is already unstated", and
O3's accepted rationale cites this story by number as its authority for the
point.

**Forces.** A synchronous contract is the readable one, and G5 is a stated goal.
Against it: the four subsystems in §6.2 run on independent clocks and a macOS
status item conventionally owns the main thread. The new force, absent from the
first pass: an unspecified model is now cheaper to preserve than to specify,
because specifying it would remove an argument the PRD is currently using. A
deferral that has started doing work in other decisions is no longer neutral.

**Options not taken.** (a) Name an async model — `asyncio` with inference in a
thread executor. (b) Name a queue model — capture thread producing into the ring
buffer, worker consuming, tray on main. (c) Make the threading model a stated
Phase 2 deliverable with its own *Rejects if* line, which is now the obvious move
given that O9 gave every other gate one.

**Choice as written.** The spec chose a synchronous-looking contract by not
addressing concurrency, and has now cited that non-addressing as a cost driver
against a cheaper latency strategy. Both halves are defensible; the pairing is
what is unrecorded.

**Consequences.** The concurrency model will be retrofitted under an interface
designed without it, in a Phase 2 whose gate criteria (O9) test injection
targets and clipboard detection and say nothing about threading. More
consequentially: if Phase 1 misses G1, §9 sends the project to renegotiate §7.1,
where the cheap option is discounted on grounds the project could remove at any
time by making a decision it has not made. The recorded reason for not building
the cheap option is contingent on a gap nobody has been assigned to close.

**Pattern.** Half-Sync/Half-Async (POSA vol. 2, Schmidt et al. 2000) is the shape
the daemon wants — synchronous service layer, asynchronous I/O layer, queue
between them, and §6.2's ring buffer is already the queue. `end_session()`
returning a result for work done elsewhere is Active Object (POSA vol. 2) with
the future elided.

**Notes.** Whether the unspecified model breaks is the diaboli's question and is
not claimed here. O3 was adjudicated without the threading gap being raised as
an objection in its own right.

## Story #3 — AppConfig deferred to a nonexistent review mode

**Source:** `AMANUENSIS_PRD.md` (§6.3); objections record, "Explicitly not objecting to"
**Lens:** coherence, patterns
**Refs:** —

**Context.** §6.3 is unamended: `DictationController.__init__` takes `config`
alongside four injected collaborators, and one sentence later `AppConfig` is "a
singleton loaded once at startup, exposed via `AppConfig.get()`". The new fact is
that a second sentinel examined this and declined it — the objections record
lists it under "Explicitly not objecting to", reasoning that it is "a testability
irritation, not a structural flaw, and belongs at code-time review rather than
spec-time."

**Forces.** That routing judgment is reasonable on its face and pulls against one
thing: code-mode review does not exist in this release. The spec-mode-only
constraint is stated in both sentinel skills, and code-mode is tracked as
follow-up work. So the decision has been routed to a reviewer that cannot
receive it, at the only moment when changing it is free — before Phase 0 writes
`config.py`, whose singleton is a Phase 0 gate deliverable.

**Options not taken.** (a) Inject config everywhere, per the controller's own
precedent. (b) Inject narrow per-component config objects so `MacOSInjector`
cannot reach `[history]`. (c) A `load_config()` returning a frozen dataclass with
no ambient accessor — same load-once semantics, no global reach. (d) Record the
deferral to code-mode explicitly in the PRD, so that whoever eventually runs
code-mode knows a prior reviewer sent it there deliberately.

**Choice as written.** Both mechanisms retained, and now with a second sentinel's
explicit decision not to press the point at spec time. The choice is no longer
merely unrecorded — it is recorded as *not yet due*, in a queue with no consumer.

**Consequences.** Phase 0's gate ("config loads and rejects a malformed file with
a useful error") will be written against `AppConfig.get()`, which fixes the
pattern before any component exists to argue with it — and the review pass that
was supposed to catch it arrives, if at all, after the code it would have
shaped. Every component keeps default reach into every config section:
`RuleBasedPostProcessor` can read `[injection]`, and nothing structural objects.

**Pattern.** Singleton (GoF, 1994) supplying what is elsewhere Dependency
Injection; the `.get()` accessor makes it Service Locator (Fowler, 2004), the
pattern DI was formulated against. Both halves of that debate still sit in
adjacent paragraphs of §6.3.

## Story #4 — An ABC kept for an unscheduled port

**Source:** `AMANUENSIS_PRD.md` (§6.2, §6.3, §7.3 platform paragraph)
**Lens:** patterns, alternatives
**Refs:** O6

**Context.** §6.3 still says every ABC "exists because there is a real chance we
replace the implementation, not for symmetry", and the objections record endorses
that test explicitly under "Explicitly not objecting to". O6 then removed
`WindowsInjector` and `LinuxInjector` from §6.2 and §6.4 and made both platforms
§3 non-goals. `TextInjector` is now an abstract base with exactly one
implementation, retained for a port that no phase in §9 schedules — and §7.3 says
of the swappability claim that it "is no longer load-bearing for v1 and should
not be trusted without evidence."

**Forces.** Keeping the ABC costs one file and preserves the option; removing it
would make a later port a refactor rather than an addition. Against it: the
stated test is "a real chance we replace the implementation", and O6 moved the
replacement from unscheduled-but-implied to explicitly-out-of-scope. The
amendment kept the abstraction and weakened its own justification in the same
paragraph, which is the honest thing to do and leaves the rule quietly
unenforceable.

**Options not taken.** (a) Restate the rule to cover three distinct jobs —
replacement (`TranscriptionEngine`, `registry.py`), platform selection
(`TextInjector`, `factory.py`), composition (`TextPostProcessor`, the ordered
chain) — and let each contract follow from its own. (b) Collapse `TextInjector`
to a concrete class now and reintroduce the ABC when a second platform is
scheduled, which is what the stated test literally implies. (c) Apply the test to
`hotkey/base.py`, which §6.4 still declares while §6.2 and §6.3 never contract
it and no alternative implementation is named anywhere.

**Choice as written.** One justification, now covering a single-implementation
platform boundary, a genuine replacement boundary, a composition boundary, and a
fourth ABC the justification was never applied to.

**Consequences.** The composition boundary is still the one that will grow, and
still has no stated contract for what composition needs: whether `process` may
raise and what happens to §8's persist-before-inject ordering if it does,
whether order is significant (§5.3 says "ordered", so yes), whether a processor
may read the session's audio. `TranscriptionEngine` got `load` / `warm_up` /
`is_loaded` because its lifecycle was considered; `TextPostProcessor` still has
two members.

**Pattern.** `TranscriptionEngine` is Strategy (GoF, 1994). `TextInjector` is now
Strategy with one strategy — closer to a seam kept open on principle.
`TextPostProcessor` chained over a shared value is Pipes and Filters (POSA vol.
1, Buschmann et al. 1996), which makes stage ordering and stage failure semantics
architectural concerns rather than implementation details.

## Story #5 — SQLite delete became a privacy mechanism

**Source:** `AMANUENSIS_PRD.md` (§5.3, §5.5 history semantics, §8)
**Lens:** defaults, consequences
**Refs:** #1, O10

**Context.** The first pass mapped TOML, SQLite and the 3.11 floor as one silent
stdlib decision — `tomllib` landed in 3.11 (PEP 680), so the version floor *is*
the config-format choice. That still stands. What changed is that O10 gave the
storage engine a job it did not previously have: with `[history] enabled =
false`, the row is written before injection and "deleted immediately after
injection succeeds — so nothing persists".

**Forces.** The stdlib choice buys zero dependencies for a product whose security
posture is a small attack surface, and SQLite gives the `0600` single file §7.6
wants. Against it, newly: "nothing persists" is now a privacy claim resting on
`DELETE`, and a `DELETE` in SQLite marks pages free for reuse rather than erasing
bytes — `secure_delete`, `VACUUM`, and WAL checkpoint behaviour all bear on
whether the transcript is actually gone, and none is specified. The amendment
reasoned about the *logical* row and inherited the engine's physical semantics
without naming them.

**Options not taken.** (a) Specify the durable-delete posture — `PRAGMA
secure_delete=ON`, or WAL disabled for the transient path, so the claim and the
mechanism agree. (b) Keep the pre-injection write out of SQLite entirely on the
disabled path: a `0600` temp file unlinked after injection has simpler erase
semantics than a shared database file. (c) State that "nothing persists" means
"nothing is queryable through `manu history`", which is the claim the current
mechanism actually supports.

**Choice as written.** SQLite, chosen silently for retention, is now also the
mechanism for non-retention. The spec chose the erase semantics by not addressing
them.

**Consequences.** `tomllib` still reads and does not write, so a settings UI
(§11.2, post-v1) or a tray toggle needs a comment-preserving TOML writer or it
destroys the annotated §5.3 block that serves as user documentation. On the
history side, `retain_days = 30` still implies a sweep no component in §6.2 owns
— and O10's rationale explicitly records `retain_days` and aborted-session
retention as deliberately not addressed, so that gap is now a known open rather
than an oversight.

**Pattern.** — . The standard library as default supplier: the cheapest and most
defensible class of inherited default. The cost is that a component chosen for
convenience is now load-bearing for a privacy promise.

## Story #6 — Config policy survived collision by redefining a key

**Source:** `AMANUENSIS_PRD.md` (§5.3), `CLAUDE.md` (Hard constraints)
**Lens:** forces, consequences
**Refs:** #3, O10

**Context.** §5.3's rule is unamended: "Every behavioral decision in this PRD
that could reasonably go either way is a config key with a sane default. No
behavior is hardcoded that a user might want to change." O10's objection found
the rule's first real collision — CLAUDE.md lists both "Persist before
injecting" and "No hardcoded behaviour a user might want to change" as hard
constraints, and they meet on `[history] enabled`. The resolution kept the key,
kept the rule, and redefined what the key means. The amendments also added a
twenty-sixth key, `warn_on_clipboard_manager`.

**Forces.** §4's primary user is comfortable with a config file, and
configurability is how this PRD discharges tradeoffs it cannot resolve — the
clipboard exposure, filler-stripping loss, LLM latency. Against it: every key is
a permanent compatibility promise and a test-matrix branch, and the collision
demonstrated that the rule can generate keys whose plain meaning contradicts a
guarantee stated elsewhere. The resolution chose to preserve the rule at the cost
of the key's name (story #10) rather than to admit a bounded exception.

**Options not taken.** (a) Admit the exception — some behaviour is not
user-settable because a guarantee depends on it, stated once in §5.3 so the next
collision has a precedent. (b) Split the key: `[history] retain` for the
user-settable part, with the pre-injection write outside config entirely. (c)
Tiered config — a stable surface plus an `[experimental]` table with no
compatibility promise, which is what §5.2's "ship `vad_auto` behind a flag" still
reaches for with no mechanism, since everything is a flag.

**Choice as written.** The rule holds without exception; where a key collided
with a guarantee, the key's meaning moved. That is a real decision about which of
two hard constraints yields, made inside a resolution about history semantics.

**Consequences.** The rule remains self-ratcheting — any future decision that
"could reasonably go either way" is now required to become a key — and it has
acquired a precedent for resolving collisions by redefinition rather than
exception. Because config is globally reachable (#3), adding a key still has no
structural cost. The next collision will be resolved the same way unless someone
decides otherwise.

**Pattern.** The explicit inverse of Convention over Configuration (Rails, 2005).
The standing tension with CLAUDE.md's declared review lens is unchanged: CUPID's
*Predictable* and *Unix philosophy* both push toward fewer knobs, and CUPID is
the skill invoked on every refactor.

## Story #7 — Audio never stored, transcripts always written

**Source:** `AMANUENSIS_PRD.md` (§5.3, §5.5, §8, §7.6)
**Lens:** forces, consequences
**Refs:** #6, O10

**Context.** The first pass mapped `store_audio = false` as a privacy default
argued on one axis. The amendments moved the other artefact in the opposite
direction: O10 makes the transcript write to disk **unconditional**, before
injection, regardless of the history setting. The PRD now holds two defaults
about two artefacts from the same utterance — audio is never written unless
explicitly enabled; the transcript is always written, even when the user has
turned history off.

**Forces.** Each default is individually well argued. Audio is "the sensitive
artifact" (§5.3, §7.6). The unconditional transcript write is what makes §8's
never-lose-a-transcript guarantee real, and O10's rationale is precise about who
it protects: the privacy-motivated primary user is the one most likely to disable
history, and the §4 secondary user with motor impairment is the one who most
needs the recovery path. What is unweighed is the comparison. O10's own rationale
names it and sets it aside: "the transcript of what a user dictated into a
password manager or a private message is not obviously less sensitive than the
recording of it", and `retain_days` and aborted-session handling "remain as
written and are open for a later pass."

**Options not taken.** (a) Symmetric treatment — if the transcript must be
written for crash safety, say so in §7.6's security posture alongside the audio
default, so both artefacts' handling is stated in one place. (b) Scope the
unconditional write to sessions that reach injection, so an aborted or misfired
session leaves nothing. (c) Revisit `store_audio` in light of the new position:
if transcripts are already written unconditionally, a bounded audio ring is a
smaller marginal privacy step than it looked when nothing was written by default.

**Choice as written.** Two artefacts, two opposite defaults, one of them argued
on sensitivity and the other on durability, with the comparison explicitly
deferred. The spec chose the asymmetry by resolving the artefacts in separate
sections on separate criteria.

**Consequences.** The debuggability cost the first pass mapped is unchanged: with
no audio, a bad transcript cannot be replayed against a different model or chain,
and §5.6's vocabulary mechanisms are exactly what wants that loop. Newly: the
default install now writes every dictated transcript to disk before the user has
seen it, retains it for thirty days when history is enabled, and retains aborted
sessions on the same terms — which is a materially different privacy profile from
the one §5.3's `store_audio` comment implies, and the README's privacy section
(§9 Phase 4) is where the mismatch will surface.

**Pattern.** — . Privacy-by-default (Cavoukian, 1995) applied to one artefact and
durability-by-default applied to the other. Both principles are sound; the
project has not decided which governs when they meet on the same utterance.

## Story #8 — Tier-conditional G1 splits promise from differentiator

**Source:** `AMANUENSIS_PRD.md` (§2 G1 row and measurement note item 4, §9 Phase 1, §10)
**Lens:** forces, consequences
**Refs:** O1

**Context.** O1 made G1 tier-conditional: it binds on the CUDA and Apple Silicon
rows of §7.2's table, and does not gate the CPU-only tier, which "ships with a
measured, documented latency expectation instead". §9's stop instruction is
scoped to the tiers G1 binds on. The resolution is well reasoned and closes a
real defect — previously §2 and §9 demanded parity while §10 quietly let the CPU
tier ship anyway, so the gate could not fail. The decision it makes along the way
is not recorded as a decision.

**Forces.** The stated force is honesty toward the offline-constrained user: "a
slower tool with an honest number serves them; shipping them nothing does not."
Against it, unstated: §1's differentiator is locality, and §4's primary user is
defined by privacy motivation or offline constraint — a population that
correlates with older, cheaper, unaccelerated hardware. §4's other clause is that
they "will not tolerate a tool that is slower than typing." The product's speed
promise now binds on the hardware tier, while the promise that justifies the
product binds on everyone. Those are different populations, and the PRD names
neither.

**Options not taken.** (a) State the tier split as a product-positioning decision
in §1 or §4 rather than as item 4 of a measurement note, so the README and the
positioning inherit it. (b) Give the CPU tier its own budget — a number it must
beat to ship, rather than a number it must publish — which is what "not gated is
not unmeasured" stops one step short of. (c) Drop the CPU tier from v1 and add it
when there is a model that meets a stated bar, which §10 contemplates as a
failure response but not as an option.

**Choice as written.** G1 became a property of a hardware tier. The spec chose to
segment its user base by accelerator availability without saying that it had, and
without revisiting §4, §1 or the README positioning that still describe one
product with one speed promise.

**Consequences.** The CPU tier now has a published number and no threshold, which
makes it a disclosure rather than a goal — §10's escape clause is that "if that
number turns out to be unusable rather than merely slow, the honest response is
to drop the tier in §3", and "unusable" is undefined in precisely the way O9
objected to for gates. Every gate in §9 now names what rejects it; the CPU tier's
ship/drop decision does not. Positioning follows: a tool marketed on locality
whose speed claim holds only on accelerated hardware needs that caveat where
users read it, not only where implementers do.

**Pattern.** — . This is a segmentation decision (tiered service levels) arrived
at through a measurement fix. Naming it as segmentation is what makes it visible
to §1, §4 and the README rather than only to the test suite.

## Story #9 — Phase 5's budget was computed, not chosen

**Source:** `AMANUENSIS_PRD.md` (§7.5 budget paragraph, §9 Phase 5)
**Lens:** forces, alternatives
**Refs:** #8, O11

**Context.** O11 established that G1 assumes `chain = ["rules"]` and gave Phase 5
its own budget: p50 ≤ 700 ms, p95 ≤ 1100 ms with the LLM pass enabled. §7.5
supplies the derivation in the same breath: "A base pipeline at the 400 ms p50
target plus a 300 ms ceiling is ~700 ms." The p95 figure follows the same
addition — 800 plus 300. Both numbers are G1 plus `max_latency_ms`.

**Forces.** Arithmetic consistency is the stated force, and it is a real one: a
budget that ignores the ceiling it just defined would repeat the defect O11
found. Against it, unstated: a budget is a statement about what a user will
tolerate, and these numbers are statements about what the mechanism will cost.
The two coincide only by luck. §7.5's own argument names the tolerance directly —
"A dictation tool that sometimes takes 900 ms is worse than one that is
consistently 350 ms and slightly rougher" — and the new p95 budget of 1100 ms is
above the figure that sentence rejects. The section now permits a latency it
argues against, because the permitted number was computed rather than judged.

**Options not taken.** (a) Set the Phase 5 budget from tolerance and derive
`max_latency_ms` from it — if 900 ms is the stated intolerable point, the ceiling
that follows is roughly 100–200 ms, and the honest conclusion may be that the
pass does not fit. (b) Keep the arithmetic budget but state explicitly that it
supersedes §7.5's 900 ms line, so the section does not hold both. (c) Make the
Phase 5 budget conditional on cancellation rate rather than absolute latency,
since the gate already reports how often the deadline fires.

**Choice as written.** The product now has two latency identities, and the second
one was obtained by adding the ceiling to the first. Nothing in §7.5 or §9 says
whether 700 ms is a number a user would accept — only that it is what the parts
sum to.

**Consequences.** The Phase 5 gate measures against a budget the mechanism cannot
fail by construction: base plus ceiling is the definition of the worst case, so
any run that respects the deadline is inside budget, and the gate's real content
is the A/B quality judgment plus the cancellation rate. §7.5's cancellation path
is honestly costed — a cancelled pass spends the full ceiling and returns nothing
— which means the tier's median experience is not the p50 figure but a mixture
the budget does not describe. The README publishes both numbers (§7.5), so the
user choosing the feature is choosing an arithmetic bound, not a tested
experience.

**Pattern.** — . This is worst-case-sum budgeting, the natural instinct when
composing latency, and it is the opposite of the error-budget discipline (Beyer
et al., *Site Reliability Engineering*, 2016) in which the tolerable number is
fixed first and component budgets are allocated within it. Both are legitimate;
they produce different products, and the PRD has not said which it is doing.

## Story #10 — A key documented to mean something else

**Source:** `AMANUENSIS_PRD.md` (§5.3 history block, §5.5, §8)
**Lens:** patterns, coherence
**Refs:** #6, O10

**Context.** O10 resolved the crash-guarantee collision by redefining `[history]
enabled`: the pre-injection write is unconditional, and `false` means the row is
deleted after injection succeeds. §5.5 then instructs the reader — "Read the key
as *retain* history, not *use* history." The config block carries a three-line
comment explaining that the key does not mean what it says. Renaming it to
`retain` was available and costs nothing: Phase 0 has not started, no user has a
config file, and §5.3's own rule is that keys are amendable through the PRD.

**Forces.** Keeping the name preserves continuity with the config block as
already circulated and with any reader who has internalised it — a real force
after thirteen revisions in one day. Against it: the name is the interface. A
user reading `enabled = false` reasonably concludes that history is not
happening, and the correct reading lives in §5.5, two sections away from the
place the decision is made. The spec resolved toward continuity and paid for it
in documentation.

**Options not taken.** (a) Rename to `retain = false`, which states the semantics
without a gloss and makes §5.5's instruction unnecessary. (b) Split into
`retain_history` and leave the unconditional write out of config entirely, since
§8 says it is not user-settable. (c) Keep `enabled` and make it mean what it
says, accepting a documented exception to the crash guarantee — the reading O10
rejected, for reasons its rationale states well.

**Choice as written.** The key keeps a name that contradicts its behaviour, and
the contradiction is handled by telling readers to read it differently. That is a
decision about where meaning lives — in the identifier or in the prose — made
without being posed as one.

**Consequences.** Every future reader of the config block needs §5.5 to
understand it, which is a permanent tax on the file §5.3 designed to be
self-documenting. The gloss also has to survive translation into the README, the
tray, any settings UI (§11.2), and validation error messages — each of which is a
fresh opportunity for the plain reading to win. And the mismatch is exactly the
kind a config-validation error message cannot fix, because nothing is invalid.

**Pattern.** This is where Henney's claim that names compress cognition
(*Pattern Stories*, POSA vol. 5, 2007) is directly in play, and the resolution
went the other way: the name now decompresses into a paragraph. Compare the
project's own naming convention in HARNESS.md — abstract bases named for the role
they abstract — which is the same principle applied consistently one layer up.

## Story #11 — Disclosure chosen over prevention, now twice

**Source:** `AMANUENSIS_PRD.md` (§5.4, §7.3 transcript-egress paragraph, §2 G3 row)
**Lens:** patterns, forces
**Refs:** #7, O12

**Context.** O12 was rated critical and its claim was that the default injection
strategy routes every transcript through the system clipboard where managers may
capture and cloud-sync it, invisibly to G3's packet capture. The resolution keeps
clipboard as the default and handles the exposure "by making it visible rather
than silent": detect known managers at startup, show a persistent tray indicator,
add `warn_on_clipboard_manager`, and scope G3's row to this process only. §7.3
cites §5.4's recording-state precedent as the authority. That precedent is the
first instance; this is the second.

**Forces.** The stated force is that `keystroke` is slower and more
failure-prone precisely for the §4 secondary user who can least afford either —
so switching the default would move harm rather than remove it. That reasoning is
sound. Against it, unstated: disclosure discharges responsibility only when the
user has an action available, and here the available action is the alternative
§7.3 rejects on their behalf. The user is told about an exposure whose only
remedy the document argues they should not take. Two instances now share a
resolution shape, and a third exposure will inherit it by precedent.

**Options not taken.** (a) Reduce the exposure rather than disclose it — a
platform-specific transient or concealed clipboard type where one exists, which
O12 listed and the resolution did not address. (b) Strategy by length: keystroke
for short transcripts, clipboard for long ones, which bounds the exposure without
paying keystroke's cost on the paragraphs it is bad at. (c) State the doctrine
explicitly — privacy-relevant conditions are surfaced, not prevented, unless
prevention is free — so the next exposure is evaluated against a stated policy
instead of a precedent chain.

**Choice as written.** Disclosure over prevention, applied twice and named
neither time. §7.3 reasons from §5.4 as precedent, which is how a doctrine forms
without being decided.

**Consequences.** The detection list is stated as incomplete and must be
presented that way — absence of a warning means "no known manager detected",
never "no manager present" — which means the tray indicator is a partial signal
carrying a privacy claim, and the burden of the gap falls on the user. G3's
narrowing is the other half: the product's headline privacy verification now
explicitly does not cover the path most likely to leak, and §7.3 says whatever
gate verifies G3 "must cover the cross-process path or explicitly state that it
does not" — an obligation assigned to no gate. §9's Phase 1 and Phase 4 packet
captures both run inside the boundary O12 established they cannot see past.

**Pattern.** — . The nearest named thing is the informed-consent posture in
privacy engineering, and its known limit is the one operating here: notice
without a viable alternative shifts responsibility rather than reducing risk.
Contrast §5.4's recording indicator, where the user's action — stop talking — is
free. Naming the doctrine is what lets the team notice the two cases differ.

## Story #12 — The probe deletes its own instrument

**Source:** `AMANUENSIS_PRD.md` (§9 Probe, §10 top risk row)
**Lens:** coherence, consequences
**Refs:** #8, O4

**Context.** O4 added a throwaway probe before Phase 0: a script "no package, no
ABCs, no config, deliberately not to §6.4" that transcribes a pre-recorded
10-second WAV and prints elapsed transcribe time. "Delete it afterwards; it is
not a deliverable." The reasoning is good and the objection was right — a gate
positioned after the cost is incurred is a deferral, not a mitigation. Two
decisions ride along unrecorded.

**Forces.** Speed is the whole point: an hour to a first number, and every
convention the probe skips is an hour it does not spend. Against it: the same
day's amendment (O9) added `docs/gates/phase-<n>.md` on the reasoning that
"without it, Phase 1's measured latencies exist only in a conversation, and every
later phase implicitly regresses against a baseline that was never written down."
The probe produces the project's *first* latency number, its gate is the earliest
point the project can be killed, it is numbered by no phase, and its instrument
is destroyed by instruction. The argument that produced `docs/gates/` applies to
it more strongly than to anything else in §9.

**Options not taken.** (a) Keep the script under `tests/fixtures/` or
`scripts/probe.py` — twenty lines, exempt from §6.4 by an explicit note, so the
number can be reproduced when hardware or a model version changes. (b) Write
`docs/gates/probe.md` with the number, the hardware, the model resolution and the
date, and delete only the code. (c) Fold the probe into Phase 1's ADR as a
recorded baseline, since `0001-engine-selection.md` already has to carry
comparative latency figures.

**Choice as written.** The project authorised one artefact exempt from every
convention in HARNESS.md and CLAUDE.md, mandated its deletion, and left its
output with no record — on the same day it required every other gate to write
one. The exemption is deliberate and stated; the record gap is neither.

**Consequences.** A "go" from the probe is the decision that commits the project
to the entire Phase 0 scaffold, and it will be unreproducible an hour after it is
made: no script, no stated hardware, no model revision, no file. If Phase 1's
number later disagrees with the probe's — likely, since the probe is optimistic
by construction and skips capture, residency, post-processing and injection —
there is nothing to compare against to learn which assumption broke. The probe's
gate is also the one gate in §9 with no *Rejects if* line, phrased as "an order of
magnitude is all this needs to answer", with ambiguity resolved as a pass.

**Pattern.** This is a spike (XP; Beck, *Extreme Programming Explained*, 1999) —
throwaway code answering a technical question. The discipline that goes with the
practice is that the spike is discarded and *its answer is written down*; here
the first half is mandated and the second is not.

## Story #13 — Six decision surfaces and a stale index

**Source:** `AMANUENSIS_PRD.md` (§7 preamble, §6.4, §9, §14, revision log)
**Lens:** coherence, patterns
**Refs:** #12, O9

**Context.** The first pass mapped four decision-record mechanisms with no
routing rule between them. The count is now six: §7 amended in place with dated
revision notes; `docs/adr/`; `docs/gates/phase-<n>.md` (added by O9);
`docs/superpowers/objections/`; `docs/superpowers/stories/`; and
`docs/superpowers/slices/`. §14 was added to index four of them, with disposition
counts. The routing question the first pass raised — PRD-amendment versus ADR —
is untouched, and the revision log now has thirteen rows, so the mutable variant
is being exercised heavily.

**Forces.** Each surface earned its place on its own merits, which is exactly how
this happens: O9's gate records fix a real gap (story #12 argues they do not go
far enough), and §14 makes four scattered records discoverable from the document
they review. Against it: §14 is a hand-maintained cache of four files'
frontmatter, including counts that go stale the moment a human dispositions one —
and this second pass has just invalidated that row. §14 also carries an
instruction to re-run the cartographer, which is workflow state stored in a
specification.

**Options not taken.** (a) §7 becomes a stable index that links out; every
decision lives in a numbered ADR and amendments supersede rather than edit — the
Nygard discipline the project has half-adopted. (b) Generate §14 rather than
maintain it, since the counts are computable from the four records' frontmatter
and a stale count is worse than no count. (c) Write the routing rule once — which
surface receives which class of decision — as the one paragraph that makes the
other five navigable.

**Choice as written.** Two more surfaces and an index, added while the routing
question stood open. The spec chose accumulation by resolving each record's need
individually and never asking where a decision goes.

**Consequences.** The failure mode is still silence rather than confusion: a
contributor unsure which artefact a decision belongs in writes it in none, which
is the intent debt all six mechanisms exist to prevent. Phase 1 is the first live
test and now has three claimants for the same content — §7.2 already holds the
engine decision, `0001-engine-selection.md` is a required gate deliverable, and
`docs/gates/phase-1.md` must carry the measurements and what the phase revealed
that the PRD got wrong. Nothing says which is authoritative when they disagree,
and §7's amendment instruction means the PRD can be edited to agree with either
after the fact.

**Pattern.** Architecture Decision Records (Nygard, 2011), whose defining
discipline is that a record is immutable and superseded rather than edited. §7's
"update with a dated revision note" is the mutable variant, and thirteen rows in
one day is that variant working as designed — which is precisely why the two
conventions cannot both govern the same decision.
