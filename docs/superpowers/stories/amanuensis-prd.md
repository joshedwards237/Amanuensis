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
    title: Blocking controller API for a concurrent daemon
    disposition: pending
    disposition_rationale: null
  - id: 3
    lens: [coherence, patterns]
    title: AppConfig is singleton and injected dependency
    disposition: pending
    disposition_rationale: null
  - id: 4
    lens: [patterns, alternatives]
    title: One ABC rationale over three different jobs
    disposition: pending
    disposition_rationale: null
  - id: 5
    lens: [defaults, consequences]
    title: Python 3.11, TOML and SQLite are one decision
    disposition: pending
    disposition_rationale: null
  - id: 6
    lens: [forces, consequences]
    title: Configurability over opinionation, stated as policy
    disposition: pending
    disposition_rationale: null
  - id: 7
    lens: [forces, consequences]
    title: Audio off by default weighs only privacy
    disposition: pending
    disposition_rationale: null
  - id: 8
    lens: [forces, coherence]
    title: Platform order by permission difficulty, not users
    disposition: pending
    disposition_rationale: null
  - id: 9
    lens: [patterns, consequences]
    title: Human gates on machine-checkable targets
    disposition: pending
    disposition_rationale: null
  - id: 10
    lens: [coherence, patterns]
    title: Four decision records, no routing rule
    disposition: pending
    disposition_rationale: null
---

> **Sequencing caveat.** In the designed pipeline the cartographer runs *after*
> spec-mode advocatus-diaboli dispositions are resolved, so that stories can
> cite adjudicated objections and avoid re-treading them. This record was drawn
> concurrently with the diaboli run, before any human adjudication and before
> `docs/superpowers/objections/amanuensis-prd.md` existed. Consequences: no
> story cites an objection ID, and the Routing Rule was applied against the
> cartographer's own judgment of what is failure-shaped rather than against a
> filed objection list. Two candidates were dropped to the diaboli on that
> basis (the G1 budget being specified on 10-second utterances while §7.1 calls
> 15–30 s realistic; `history.enabled = false` silently voiding §8's
> never-lose-a-transcript guarantee). If the diaboli did not raise them, they
> are unmapped by both agents.

## Story #1 — Python inherited from the ASR ecosystem

**Source:** `AMANUENSIS_PRD.md` (§8 Non-functional requirements)
**Lens:** defaults, consequences
**Refs:** —

**Context.** §8 states "Python | 3.11+" as a row in a requirements table,
sitting between "Idle CPU < 1%" and "Recovery from mic disconnect". §7 records
the rejected alternative for streaming, for the engine, for injection, for VAD,
and for post-processing — and records nothing for the language all of those run
inside. The implementation language of a latency-critical, always-resident
daemon is the one technical decision in this document that arrived without an
argument.

**Forces.** The ASR tooling is Python-first: faster-whisper/CTranslate2, ONNX
Runtime for Silero, sounddevice over PortAudio, llama.cpp bindings. Choosing
Python minimises integration cost and is what keeps §7.2's engine swap a
scheduling decision rather than a rewrite. Pulling the other way: a daemon that
must hold a real-time audio callback, a global hotkey listener, a tray run loop
and a several-hundred-millisecond inference call is a concurrency problem, and
Python is the language in which concurrency costs the most reasoning per line.
The PRD resolved toward integration cost, silently.

**Options not taken.** (a) A Rust or Go core with Python confined to inference
behind FFI or a subprocess — whisper.cpp and nerd-dictation, both on §13's
required-reading list, sit on the other side of exactly this line, and
whisper.cpp is C++ specifically to shed the Python runtime. (b) A Swift-native
macOS app calling Core ML / whisper.cpp directly — the best possible
permissions, hotkey and tray story on the platform §7.3 targets first, at the
cost of portability. (c) Python for orchestration with the hot path (capture →
inference → inject) as a compiled extension.

**Choice as written.** Python, by assertion in a table. The spec chose the
language by not treating the language as a choice.

**Consequences.** This is now the least reversible commitment in the document.
Every other §7 decision sits behind an ABC that makes it swappable; the runtime
sits underneath all of them. When §9's Phase 1 gate says "if G1 is missed here,
stop and renegotiate §7.1", it offers batch-vs-streaming as the lever — the
runtime is not on the list of things renegotiable at any gate. Accepting Python
also accepts Python's desktop-distribution story: §11.3 frames model
distribution as the open question, but shipping a ~1.5 GB Python daemon to a
non-developer is the same question wearing a smaller hat.

**Pattern.** — . No design pattern; this is a platform commitment. The nearest
named thing is the orchestration-language / hot-path-language split, which the
two projects in §13's reading list resolve in opposite directions. §13 asks the
team to read whisper.cpp and nerd-dictation without asking what their language
choices imply for this one.

**Notes.** The user's global engineering conventions declare Python the default
backend language for all projects. Worth confirming at disposition whether that
standing default — rather than anything specific to Amanuensis — is the actual
source. Naming a default's origin is the cheap part; the point is deciding to
own it.

## Story #2 — Blocking controller API for a concurrent daemon

**Source:** `AMANUENSIS_PRD.md` (§6.1 Process model, §6.3 Class contracts)
**Lens:** patterns, forces
**Refs:** #1

**Context.** §6.3 gives `DictationController` three methods: `start_session()
-> None`, `end_session() -> DictationSession`, `abort_session() -> None`.
`TranscriptionEngine.load()` is documented "Blocking." Nothing anywhere in the
PRD names a threading model, an event loop, or an async strategy. Meanwhile
§6.2 requires the daemon to simultaneously own an `AudioCapture` ring buffer fed
by a PortAudio callback, a `HotkeyListener` emitting press/release events, a
`TrayApp` run loop, and a multi-hundred-millisecond inference call.

**Forces.** A synchronous contract is the readable one, and readability is a
stated goal — G5 asks that a developer read the codebase in an afternoon, and
`end_session()` returning a fully populated `DictationSession` is the clearest
possible expression of §5.1's seven steps. Against that: the four subsystems
above run on independent clocks, and one of them — a macOS status item —
conventionally owns the process's main thread. The PRD resolved toward
readability by writing the interface as though the daemon were single-threaded,
and left reconciliation to Phase 2, where "`DictationController` wiring the
loop" is one clause of a gate description.

**Options not taken.** (a) Name an async model up front — an `asyncio` loop with
inference dispatched to a thread executor. (b) Name a queue model — capture
thread producing into the ring buffer, a worker thread consuming sessions, tray
on main; the ring buffer in §6.2 is already half of this. (c) State explicitly
that the concurrency model is a Phase 2 design deliverable with its own gate
criterion, rather than leaving it absent.

**Choice as written.** The spec chose a synchronous, single-threaded-looking
contract by not addressing concurrency at all. Deferring the model to
implementation is a defensible call for a v1; what is unrecorded is that a
deferral happened.

**Consequences.** §6.3 is the interface the code will be written to, so the
concurrency model gets retrofitted underneath a contract designed without it.
The predictable leak is semantic: `end_session()` acquires a meaning ("returns
when transcription has finished") that a tray run loop cannot honour unless the
controller learns about threads — and "the controller owns orchestration and
nothing else" is a hard constraint in both §6.3 and CLAUDE.md. The deferral also
means the daemon's most architecturally consequential property will be settled
by whoever writes Phase 2 first, without a gate to record it.

**Pattern.** The shape this daemon wants is Half-Sync/Half-Async (POSA vol. 2,
Schmidt et al. 2000): a synchronous service layer, an asynchronous I/O layer,
and a queue between them — and §6.2's ring buffer is already the queue.
`end_session()` returning a result object for work performed on another thread
is Active Object (POSA vol. 2) with the future elided. Naming either now costs a
paragraph; naming it during Phase 2 costs a refactor of the only class the PRD
says owns the loop.

**Notes.** Whether the unspecified model *breaks* is the diaboli's question and
is deliberately not claimed here. This story asserts only that a pattern is
being adopted without being named, and that the naming is cheapest now.

## Story #3 — AppConfig is singleton and injected dependency

**Source:** `AMANUENSIS_PRD.md` (§6.3 Class contracts, §6.4 Repository layout)
**Lens:** coherence, patterns
**Refs:** —

**Context.** §6.3 defines `DictationController.__init__` taking `config`,
`engine`, `injector`, `processors`, `history` — textbook constructor injection,
and the mechanism that makes the ABCs above it genuinely swappable. One sentence
later, without transition or rationale: "`AppConfig` is a singleton loaded once
at startup, exposed via `AppConfig.get()`." §6.4 ratifies it in the layout:
`config.py # AppConfig singleton, TOML load + validation`.

**Forces.** A singleton means any module — a post-processor, an injector, the
tray — reaches configuration without a parameter. That is precisely what makes
§5.3's "every behavioral decision is a config key" cheap to keep extending:
threading config through five layers so that `injection/macos.py` can read
`restore_delay_ms` is friction the singleton deletes. Against it: this is
process-global mutable state in a design whose entire testability story is
"boundaries are ABCs with injected implementations." The spec resolved toward
reach, and did not record that it now has two mechanisms for delivering the same
dependency.

**Options not taken.** (a) Inject config everywhere, following the controller's
own precedent — verbose but uniform, and every call site declares what it reads.
(b) Inject narrow per-component config objects (`InjectionConfig`,
`EngineConfig`) so that `MacOSInjector` structurally cannot read `[history]`.
(c) A module-level `load_config()` returning a frozen dataclass passed
explicitly, with no `.get()` accessor — identical load-once semantics, no
ambient access.

**Choice as written.** Both, simultaneously. The controller receives `config:
AppConfig` *and* every other object can call `AppConfig.get()`. The PRD does not
say which is authoritative, which means both will be used, and a reader at any
given call site cannot tell which instance is in play.

**Consequences.** Tests that vary configuration become order-dependent unless
the singleton is resettable, and a resettable singleton is a global variable
with extra ceremony. The Phase 0 gate ("config loads and rejects a malformed
file with a useful error") will be written against `AppConfig.get()`, fixing the
pattern before any component exists to argue with it. It also widens every
component's blast radius by default: `RuleBasedPostProcessor` can read
`[injection]`, and nothing structural objects.

**Pattern.** Singleton (GoF, 1994) supplying what is elsewhere Dependency
Injection. The `.get()` accessor makes it specifically Service Locator (Fowler,
2004) — the pattern that dependency injection was articulated in opposition to.
The PRD contains both halves of that debate in adjacent paragraphs, which is
worth resolving deliberately rather than by whichever gets written first.

## Story #4 — One ABC rationale over three different jobs

**Source:** `AMANUENSIS_PRD.md` (§6.2 Component boundaries, §6.3 Class contracts)
**Lens:** patterns, alternatives
**Refs:** #2

**Context.** §6.3 states the governing rule for abstract bases: "Every one of
these exists because there is a real chance we replace the implementation, not
for symmetry." CLAUDE.md repeats it as a hard architecture boundary. The claim
is exactly true of `TranscriptionEngine` — §7.2 names Moonshine and Parakeet as
live alternatives — and of `TextInjector`, where three OS implementations exist
and one is active per process. It is not the reason `TextPostProcessor` exists.

**Forces.** A single stated rationale is good governance: it gives a future
contributor a test to apply before adding an ABC, which is what CLAUDE.md's "not
for symmetry" line is for. Against it: the three boundaries have structurally
different shapes, and one sentence hides that. `TextPostProcessor` is not a
replacement point — §5.3's `chain = ["rules"]` and §6.2's "composed into an
ordered chain" make it a *composition* point, with several instances active at
once, ordered, each transforming the same value. `TextInjector` is a *selection*
point resolved once by platform (`factory.py`). Only `TranscriptionEngine` is a
true replacement point (`registry.py`, config string → class).

**Options not taken.** (a) State three rationales — replacement, platform
selection, composition — and derive each ABC's contract from its own. (b) Drop
the ABC for post-processing entirely in favour of `Callable[[str,
DictationSession], str]`, since `process` plus `name` is a function with a
label. (c) Apply the stated test literally and review anything that fails it —
which would put `hotkey/base.py` up for scrutiny, since §6.4 declares that ABC
while §6.2 and §6.3 never contract it or name an alternative implementation.

**Choice as written.** One justification, three boundaries with different
shapes, and a fourth ABC in the repository layout that the justification was
never applied to.

**Consequences.** The composition boundary is the one that will grow — rules,
vocabulary, LLM, and whatever the Phase 3 edit-rate report demands — and it is
the one with no stated contract for the properties composition actually needs.
Is chain order significant (§5.3 says "ordered", so yes)? Must `process` be
pure? May a processor read the audio off the session it is handed? What happens
when one raises mid-chain — does the transcript still reach the injector, given
§8's persist-before-inject rule? `TranscriptionEngine` got `load` / `warm_up` /
`is_loaded` because someone thought about its lifecycle; `TextPostProcessor` got
two members because it was assumed to be the same kind of thing.

**Pattern.** `TranscriptionEngine` and `TextInjector` are Strategy (GoF, 1994).
`TextPostProcessor` chained over a shared value is Pipes and Filters (POSA vol.
1, Buschmann et al. 1996), or Decorator (GoF) if composition turns out to be
nested rather than iterated. The distinction is not cosmetic: Pipes and Filters
makes stage ordering and stage failure semantics architectural concerns — which
is precisely the contract §6.3 omits.

## Story #5 — Python 3.11, TOML and SQLite are one decision

**Source:** `AMANUENSIS_PRD.md` (§5.3 Configuration, §5.5 History, §8)
**Lens:** defaults, consequences
**Refs:** #1

**Context.** §5.3 specifies a single TOML file at
`~/.config/amanuensis/config.toml`. §5.5 specifies SQLite at
`~/.local/share/amanuensis/history.db`. §8 requires Python 3.11+. Three
sections, three assertions, no rationale in any of them, and no acknowledgement
that they are related.

**Forces.** `tomllib` entered the standard library in Python 3.11 (PEP 680), and
`sqlite3` has always been there. TOML plus SQLite means the config and history
layers add zero third-party dependencies to a product whose security posture
(§7.6) is built on a small attack surface and no network, and whose install
already carries roughly 1.5 GB of weights. The 3.11 floor in §8 is not an
independent requirement — it is the price of TOML-without-a-dependency. The PRD
records the floor and the format in different sections and never connects them,
so a future contributor weighing a drop to 3.9 will not see what breaks.

**Options not taken.** (a) YAML or JSON config with a third-party parser, buying
a writer and comment preservation at the cost of a dependency. (b) JSONL or
plain per-session files for history, which fits an append-mostly log with a
purge command better than a relational store does. (c) TOML via the `tomli`
backport with a 3.9 floor, widening the supported Python range for one
dependency.

**Choice as written.** The standard library, three times, silently. Whoever set
the 3.11 floor made the TOML decision; whoever wrote §5.3 inherited it without
being told.

**Consequences.** `tomllib` reads and does not write. Today that costs nothing:
§11.2 defers a settings UI to post-v1 and §5.4 makes the tray a "status surface
only", so nothing writes config. The moment anything does — a tray toggle for
`[feedback] sounds`, a settings panel, a `manu config set` — the project needs a
comment-preserving TOML writer, or it destroys the annotated config block in
§5.3 that is currently serving as the product's user documentation. Separately,
`retain_days = 30` implies a retention sweep that nothing in §6.2 owns:
`HistoryStore` is listed with no lifecycle, and SQLite does not expire rows on
its own.

**Pattern.** — . This is the standard library as default supplier: the cheapest
and most defensible class of inherited default. The only cost is that nobody
noticed the version floor and the config format were a single decision.

## Story #6 — Configurability over opinionation, stated as policy

**Source:** `AMANUENSIS_PRD.md` (§5.2 Capture modes, §5.3 Configuration)
**Lens:** forces, consequences
**Refs:** #3

**Context.** §5.3 states it as a rule rather than a preference: "Every
behavioral decision in this PRD that could reasonably go either way is a config
key with a sane default. No behavior is hardcoded that a user might want to
change." The block that follows carries roughly twenty-five keys across seven
tables — before a single user has run the product, and before Phase 1 has
replaced the PRD's own admittedly unmeasured latency estimates with numbers.

**Forces.** §4's primary user "is comfortable with a config file", and §7.3's
clipboard-restore race has no fix — only `strategy = "keystroke"` for users who
will not accept it. Configurability is how this PRD discharges the tradeoffs it
cannot resolve: the clipboard leak, the lossiness of filler stripping, the LLM's
latency cost. Against it: every key is a permanent compatibility promise, a
branch in the test matrix, and a support surface — and a product whose sole
differentiator is speed has just made its behaviour a function of twenty-five
variables never measured in combination. G5 bounds the readability of the
*code*; nothing bounds the configuration surface.

**Options not taken.** (a) Opinionated defaults with an escape hatch — ship
three or four keys (hotkey, model, injection strategy) and add a key when a real
user asks for one. (b) Tiered configuration — a documented stable surface plus
an `[experimental]` table carrying no compatibility promise, which is what
§5.2's "ship [`vad_auto`] behind a flag" is reaching for without a mechanism.
(c) Resolve the tradeoffs in the product and accept that some users are not
served.

**Choice as written.** Maximal configurability, elevated to a principle — so
that every future key inherits the justification automatically without anyone
re-deciding.

**Consequences.** The rule ratchets: any future decision that "could reasonably
go either way" is now *required* to become a key, so the surface only grows.
`vad_auto` "behind a flag" is indistinguishable from every other setting,
because everything is a flag — the PRD's intent that it be provisional has no
carrier. And because config is globally reachable (#3), adding a key has no
structural cost at all; the two decisions compound, each making the other
cheaper to extend.

**Pattern.** The explicit inverse of Convention over Configuration (Rails,
2005). Note the standing tension with the project's own declared review lens:
CLAUDE.md invokes CUPID on every refactor, and CUPID's *Predictable* and *Unix
philosophy* properties both push toward fewer knobs and one job done well. The
PRD's §5.3 policy and CLAUDE.md's review skill will disagree at some point; it
is cheaper to decide which wins now.

## Story #7 — Audio off by default weighs only privacy

**Source:** `AMANUENSIS_PRD.md` (§5.3 Configuration, §5.5 History, §7.6)
**Lens:** forces, consequences
**Refs:** #6

**Context.** `store_audio = false` appears in §5.3 with the inline reason "off
by default; audio is the sensitive artifact". §5.5 restates it, and §7.6 lists
it under the security posture. The other side of the trade appears nowhere — not
in §10's risk table, not in the Phase 1 gate, not in the Phase 3 gate that
depends on it.

**Forces.** The product's entire thesis is that audio never leaves the device
(§1), and §5.4 already treats ambiguity about recording state as a privacy
problem "regardless of where the audio goes" — a default-on audio store would
contradict the argument the product is built to make. Pulling the other way: G2
is a WER target, the Phase 3 gate demands "edit rate — what fraction of output
needed manual correction, and what kind", §7.2 requires a faster-whisper
vs. Moonshine benchmark at the Phase 1 gate, and §5.6's two vocabulary
mechanisms are tuned by comparing outputs on the same input. Every one of those
wants retained audio. The PRD resolved toward privacy — correctly — without
noticing it was also deciding how its own quality gates obtain evidence.

**Options not taken.** (a) A bounded ring — retain the last N sessions' audio,
auto-expiring, under the same `0600` posture §7.6 gives the history DB. (b)
Session-scoped opt-in — `manu transcribe --keep-audio` for benchmarking runs,
daemon default unchanged. (c) Keep the default and state explicitly that gate
evidence comes from a deliberately recorded corpus, making that corpus a Phase 1
deliverable rather than an assumption.

**Choice as written.** Off by default, argued on one axis. The spec chose the
privacy default by not addressing what its own phase gates need in order to
produce numbers.

**Consequences.** The fastest debugging loop for a bad transcript — replay it
against a different model, a different quantization, a different post-processor
chain — is unavailable by default, so field reports arrive as "it got my name
wrong" with no artifact attached. §5.6 exists precisely because proper nouns
fail, and it is the feature whose tuning most wants that loop. The engine ADR
required at the Phase 1 gate will compare backends on whatever audio the
developer happened to record that afternoon, not on retained real utterances,
which makes the ADR's numbers weaker than the gate implies.

**Pattern.** — . This is privacy-by-default (Cavoukian, *Privacy by Design*,
1995 — "privacy as the default setting"), applied correctly and worth keeping.
What is unrecorded is the second-order cost, not the principle.

## Story #8 — Platform order by permission difficulty, not users

**Source:** `AMANUENSIS_PRD.md` (§7.3 Injection, §11.1 Open decisions)
**Lens:** forces, coherence
**Refs:** #4

**Context.** §7.3 commits Phase 2 to macOS "because its permissions model
(Accessibility + Input Monitoring) is the most restrictive and will surface the
hardest problems earliest", and adds that swapping the order is "a scheduling
decision, not an architectural one" because `TextInjector` is an ABC. §11.1 then
lists "Primary OS target" among the open decisions to resolve at the Phase 2
gate, under the heading "Do not guess."

**Forces.** The ordering principle at work is risk-first sequencing: do the work
most likely to invalidate the design before the work that merely takes time.
Unstated, and pulling the other way: the competing principle is audience-first —
build where your users are, on the platform whose failure modes you can observe
daily, and let the hard platform inherit a proven core. §4 never says which OS
the primary users run, so the audience-first argument has no data to stand on
and risk-first won partly by forfeit.

**Options not taken.** (a) Audience-first — ship the platform the author and
first users run daily, treating macOS permissions as a later, well-scoped chunk.
(b) Developer-velocity-first — order by whichever platform the author can debug
fastest, on the theory that Phase 2 is where the product either becomes real or
does not. (c) Two thin injectors in Phase 2 rather than one complete one, which
is the only thing that actually tests the "scheduling, not architectural" claim
before the project depends on it.

**Choice as written.** Risk-first, argued in §7.3 and simultaneously listed as
unresolved in §11.1. The genuine decision is the *criterion*, and §11.1 does not
ask the gate to confirm the criterion — it asks which OS, which is the output,
not the reasoning.

**Consequences.** The "swap the order freely" claim is load-bearing and only
partly true. The ABC covers injection; §7.3's reasoning does not cover the rest
of the platform surface. `hotkey/listener.py`, the tray, and the `manu toggle`
unix socket named in §6.1 are each platform-shaped, and only injection has a
`factory.py` in §6.4 — the unix socket in particular is a POSIX assumption
written into a CLI comment. Deferring the criterion to the gate also means
Phase 2 begins before §11.1's question is answered, so whichever platform is
built first answers it by sunk cost rather than by decision.

**Pattern.** Risk-first sequencing is the core move of the spiral model (Boehm,
1986): address the highest-risk item in each cycle before elaborating anything
else. Naming it makes the principle reusable at the other gates, where the same
ordering question recurs (Phase 3 vs. Phase 4, Phase 5 vs. shipping) and is
currently decided ad hoc each time.

## Story #9 — Human gates on machine-checkable targets

**Source:** `AMANUENSIS_PRD.md` (§9 Phases, "How to use this document")
**Lens:** patterns, consequences
**Refs:** —

**Context.** §9 defines six phases, each ending at an approval gate, with "Stop
at the gate" stated twice in the PRD and again in CLAUDE.md. The criteria are
heterogeneous: Phase 0's are mechanical (`manu --help` runs, `mypy --strict
src/` is clean), Phase 1's is a measurement wrapped in a judgment ("Report
measured latency... If G1 is missed here, stop"), Phase 3's is a report on edit
rate, Phase 4's is "a second person installs it from the README without your
help."

**Forces.** This is a solo project with no CI — HARNESS.md records 1 of 3
constraints enforced, with "Tests must pass" and "Consistent formatting" both
`unverified` — so a human is the only gate currently available. And the criteria
that matter most here genuinely resist automation: whether a transcript needed
editing, whether an install instruction was followable by a second person.
Against that: G1 and G2 are numeric, `LatencyBreakdown` exists as a stated
*product* requirement specifically so that G1 is testable (§5.5), and yet no
gate is expressed as an assertion a suite could run. The PRD resolved toward
human report for all six, uniformly.

**Options not taken.** (a) Split the criteria — mechanical gates as CI
assertions (latency budget, `mypy --strict`, WER against a fixed corpus), human
gates reserved for the judgment calls. (b) Express each gate as a checklist
artifact committed to the repo, so the gate leaves evidence rather than a
conversation. (c) Automated criteria with explicit human override, which is what
Phase 1's "go/no-go" already is in spirit.

**Choice as written.** Every gate is a human reading a report. The consequential
part is not that a human decides — it is that no gate leaves anything
mechanically re-checkable, so a Phase 4 regression against a Phase 1 target has
nothing to fail against.

**Consequences.** Gate outcomes have no durable home. §9 asks each gate to
report "what the phase revealed that this PRD got wrong" — a genuinely valuable
artifact, and no file is specified to hold it. Phase 1's measured latencies are
the baseline every later phase implicitly regresses against, and they exist only
in the gate conversation unless someone deliberately files them in the engine
ADR. The phase structure also serialises work with no real dependency —
post-processing rules (Phase 3) do not require injection (Phase 2) — which is a
genuine cost knowingly accepted for a genuine benefit: nothing gets built on an
unproven ASR path.

**Pattern.** This is stage-gate development (Cooper, 1986) — phases separated by
go/kill decision points with defined deliverables — laid over a walking-skeleton
build order (Cockburn), in which Phase 1 proves the riskiest path end-to-end
before anything is made pleasant. Both are sound, and naming them tells a future
contributor which parts of §9 are load-bearing (the go/kill at Phase 1) and
which are convention (that there are six phases, and where their boundaries
fall).

## Story #10 — Four decision records, no routing rule

**Source:** `AMANUENSIS_PRD.md` (§7 preamble, §6.4, §9), `HARNESS.md` (Constraints)
**Lens:** coherence, patterns
**Refs:** #9

**Context.** This project now has four mechanisms for recording a decision: §7
of the PRD with dated revision notes ("update §7 with a dated revision note");
`docs/adr/` numbered ADRs (§6.4, with `0001-engine-selection.md` required at the
Phase 1 gate); the diaboli objection records that HARNESS.md makes a merge
constraint; and this choice-story record, which HARNESS.md also makes a merge
constraint. §7's amendment instruction overlaps the ADR directory's job without
distinguishing it.

**Forces.** The PRD wants to remain the single standing specification, which
argues for amending §7 in place so there is one place to read. ADRs want
decisions to be immutable and dated, which argues for never rewriting §7 at all.
Both instructions are written down; the routing rule between them is not. Add
the two harness-mandated record types and the project has more
decision-capture surface than it currently has source files — Phase 0 has not
started.

**Options not taken.** (a) §7 becomes a stable index that links out; every
actual decision lives in a numbered ADR, and amendments are new ADRs that
supersede — the standard Nygard discipline. (b) §7 stays authoritative and
`docs/adr/` is reserved for decisions below PRD granularity (which quantization,
which ONNX opset, which clipboard API), with that boundary written down. (c)
Collapse to one mechanism and accept that the PRD becomes part changelog.

**Choice as written.** Both PRD-amendment and ADRs, each described in its own
section, never compared. The spec chose duplication by not addressing routing.

**Consequences.** The failure mode is not confusion, it is silence — a
contributor unsure which artifact a decision belongs in writes it in neither,
which is exactly the intent debt all four mechanisms exist to prevent. The
Phase 1 gate is the first live test: it requires an ADR for engine selection,
and §7.2 already contains the engine decision, so `0001-engine-selection.md`
either duplicates §7.2 or supersedes it, and §9 does not say which. HARNESS.md's
two merge constraints will keep generating one objection record and one story
record per spec indefinitely, so the routing question grows rather than shrinks.

**Pattern.** Architecture Decision Records (Nygard, 2011). Nygard's discipline
is specifically that a decision record is immutable and *superseded* rather than
edited — §7's "update with a dated revision note" is the mutable variant, and
the two conventions cannot both be applied to the same decision. Choosing which
one governs is a one-paragraph decision now and an archaeology project later.
