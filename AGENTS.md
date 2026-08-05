# Compound Learning

<!-- This file is the project's persistent memory across AI sessions.
     It accumulates patterns, gotchas, and decisions so that each session
     builds on what previous sessions learned — rather than rediscovering
     the same things from scratch.

     IMPORTANT: This file is often generated or updated by LLM agents.
     Review new entries with the same scepticism you would apply to any
     generated content. Entries should reflect observed reality in the
     codebase, not aspirational conventions. An entry in GOTCHAS that
     does not reflect an actual problem that was actually solved is noise
     that increases the cognitive cost of every future session. -->

## STYLE

<!-- Patterns and idioms that work well in this codebase.
     Each entry: what to do, and why it works here. -->

<!-- Example:
- Prefer early returns over nested conditionals in handlers — the codebase
  uses flat control flow throughout and deep nesting has caused review
  friction on every PR that introduced it.
-->

## GOTCHAS

<!-- Traps, surprises, and non-obvious constraints. Initially empty — entries
     accumulate as the pipeline discovers them.
     Each entry: what the trap is, and how to avoid it. -->

- **Sentinel agents cannot find their own charter.** Every file in
  `.claude/agents/` declares its skill as `ai-literacy-superpowers/skills/<name>/SKILL.md`
  — a repo-relative path that resolves to nothing in an installed project. Pass the
  absolute path (`~/.claude/plugins/cache/ai-literacy-habitat/ai-literacy-habitat/<version>/skills/<name>/SKILL.md`)
  in the dispatch prompt. Without it the agent silently improvises a charter and
  returns output that looks conformant. Found 2026-07-31 dispatching all four sentinels.

- **`sentinel-integrity-check.sh` passes by checking nothing.** It globs
  `*.agent.md`; installed agents are `*.md`. It exits 0 with
  `sentinel integrity: OK (0 role-tagged agent(s) checked)`. Read the count, not the
  word OK — `0` means the gate did not run. Upstream bug, present in all three copies
  on this machine. Verify by hand until fixed.

- **Sentinels have no write tools, and some go idle without delivering.** They return
  record content as message text only. Two of four went quiet on first ask. The dispatch
  prompt must say explicitly: paste the complete record as your message, do not
  summarise it, do not reference a file path.

  **Upgraded 2026-08-03: assume they will not deliver, and budget to do the work
  yourself.** Three sentinels were dispatched for the dictionary spec —
  advocatus-diaboli, choice-cartographer, carpaccio — each with the absolute
  charter path this file already recommends AND an explicit output contract
  spelling out that message text is the only channel. **All three returned zero
  output.** Advocatus-diaboli was re-asked twice, the second time with the ask
  reduced to "three objections, plain prose, no format", and went idle again.
  The advice above ("say so in the dispatch") was followed in full and did not
  help.

  **CAUSE FOUND 2026-08-04, and it is the `name` parameter.** Passing `name:` to
  the Agent tool turns a sentinel into a persistent addressable teammate: it
  finishes its turn, emits an `idle_notification`, and **waits in a mailbox**.
  Its final message is not returned to the caller, because a named teammate is
  expected to deliver via `SendMessage` — which these agent definitions know
  nothing about, since their charters tell them their final message IS the
  return value. Every failed dispatch in this repo used `name:`.

  **Dispatch sentinels WITHOUT `name:`.** An unnamed agent runs in the
  background and its final text arrives in the completion notification.
  Verified: the same advocatus-diaboli agent, same charter path, same spec, no
  `name` — returned three substantial objections in 64 seconds after three
  named dispatches of the identical ask returned nothing. Use `name:` only when
  you genuinely intend to hold a conversation with the agent.

  What worked instead: writing the objection record, the slicing record and the
  choice-story record in the main session, each marked with a provenance line
  naming the sentinel that failed. That is weaker — a reviewer reviewing its own
  draft is not an independent one — and saying so in the record is the honest
  minimum. **Do not present self-authored records as sentinel-reviewed.** Dispatch
  them if you like, bound the wait, and start the work in parallel rather than
  blocking on output that has not arrived in four attempts across two features.

- **Adjudicating objections creates new unmapped decisions.** Twelve accepted objections
  amended the PRD heavily in one day; the cartographer's second pass returned 13 stories,
  7 of them mapping choices the amendments had just introduced. Re-run the cartographer
  after a batch of accepted objections — a single pass maps the document as written, not
  what the fixes bring in.

- **When a latency budget is missed, check defaults before changing design.** Every
  serious latency problem in this project was an unchecked default. `vad_filter=False`
  cost 11x (`base.en` 6,039 ms -> 541 ms on a 25 s sample; `small.en` 23,886 -> 1,438 ms)
  because the decoder repetition-loops on silence. CTranslate2 defaults to **4 threads**
  regardless of core count — worth 1.8x on a 14-core machine. And §7.2's model table was
  wrong by ~7x because CTranslate2 has **no Metal backend**, so "Apple Silicon" was a CPU
  tier named after an accelerator. A config flag, a thread count, and a smaller model —
  none of it needed a design change. Found 2026-07-31.

- **Measure the tail, not the median.** A p50 from one clean sample said GO; the p95 over
  six real samples was 14x worse and said the opposite. `base.en` measured 352 ms p50 on
  the probe and 5,810 ms p95 on the corpus. A bare median has already misled this project
  once — any latency figure entering the PRD carries p50 *and* p95, or is labelled a floor.

- **Hand-written test cases for an LLM feature will pass while real pipeline output
  fails.** The Phase 5 cleanup pass handled three self-authored disfluent inputs
  correctly and then made real ASR output **5-28x worse** (WER 19.6% -> 110%), emitting
  chat preamble into the document, hallucinating 93 words on a sample the ASR got right,
  and refusing outright. Test against frozen real output before recommending, not after.
  A self-authored n=3 is worse than no test: it manufactures confidence.

- **Wrap a probabilistic step in deterministic checks, and design them before you need
  them.** Four constraints written *before* the Phase 5 test — persist raw, reject output
  containing words absent from the input, fall back if >25% of content words vanish, and
  one-keystroke undo — caught **every** catastrophic failure. Deletion-only is a checkable
  property; that is what made the failures catchable at all. They turned silent corruption
  into a visible no-op.

- **A macOS run loop is a trap for Python signal handlers, and `stop_` is a trap
  on top of it.** `manu daemon` could not be stopped: Ctrl-C and SIGTERM both did
  nothing and only `kill -9` worked. Two independent causes, and fixing either
  alone leaves it broken. CPython runs a signal handler *between bytecodes on the
  main thread*, and the main thread sits inside `NSApplication.run()` — a C call
  that does not return until the loop ends, so the signal is recorded and never
  delivered. And `NSApplication.stop_` does not end the loop; it sets a flag
  checked the next time an event is **dequeued**, which an idle daemon never has.
  Fix: a repeating `NSTimer` (250 ms) to yield to the interpreter, plus a posted
  application-defined event with `atStart=True`. Found 2026-08-03. Applies to any
  long-running pyobjc process, not only this one.

- **`kCGEventFlagMaskAlternate` cannot tell you which option key is down.** The
  generic modifier bits are set while *either* side is held, so releasing
  right-option while left-option is down does not change the mask — a hotkey
  listener reading it never sees the release and records forever. Use the
  device-dependent per-side bits from IOKit's `IOLLEvent.h`
  (`NX_DEVICERALTKEYMASK` = 0x40, `NX_DEVICELALTKEYMASK` = 0x20, and so on).
  They are absent from the CoreGraphics headers and present in `CGEventFlags` on
  every `flagsChanged` event. Found 2026-08-03.

- **`print()` to a pipe is block-buffered, and a quiet log reads exactly like a
  hang.** Three minutes went into a sampling profiler on a daemon that was
  running perfectly — the "listening" line was sitting unflushed because stdout
  was a pipe rather than a tty. Before diagnosing a process as stuck, ask whether
  the thing reporting it stuck is an *observer* rather than the subject. Any
  long-running command whose output a harness reads needs `flush=True`.
  Found 2026-08-03.

- **A PRD amendment that withdraws a number must reach the tooling that can
  regenerate it.** §7.2 declared WER macro-average and withdrew a 14.8%
  micro-average on 2026-07-31. `scripts/bench_engines.py` kept computing the
  micro figure and printed **14.77%** into the file destined to become ADR 0001
  — the withdrawn number, regenerated on demand, two months after its
  withdrawal. Macro was 19.33%. Nothing in this project's process checks
  tooling against amendments. Found 2026-08-01.

  **Second instance, 2026-08-03.** Phase 2a added `restore_ms` to
  `LatencyBreakdown` as its headline finding and argued it across two PRD
  sections. The `history.db` schema never grew the column, so `to_history_row()`
  emitted the value and `_insert` silently dropped it on every row written for
  the whole of that phase — found only by reading a real row at the next gate.
  The regression test now iterates `dataclasses.fields(LatencyBreakdown)` and
  requires a column for each, rather than naming the field: the defect was a
  hand-maintained list that had stopped being checked against the dataclass, and
  adding one more name to that list would not have fixed it. **When an amendment
  adds a field, grep for every hand-maintained list that has to grow with it.**

- **A null measurement proves nothing until a positive control proves the
  instrument works — per instrument.** The G3 check watches sockets *and*
  bytes. Its first control fetched a URL and exited: the byte meter saw 869
  bytes, and the socket poller reported **zero sockets on a run that had
  certainly opened one**, because `lsof` samples every 250 ms and an HTTP round
  trip closes faster. A clean socket count from the subject would have been
  unearned. The control now holds the connection open and each instrument is
  validated separately. This is the second gate in this repo that could have
  passed by measuring nothing.

  **Extended 2026-08-02: the same applies to negative and failing results, and
  it bit twice in one day.** The clipboard-exposure check first reported "the
  transcript was NOT captured by the manager" — a false all-clear on the
  most-argued privacy surface in the PRD — because the read ran before the
  manager flushed to disk. It was caught only because a control copy was added
  afterwards and came back captured. Separately, `gate_2a_inject.py` reported a
  **native-field FAIL**, the one verdict §9 rejects Phase 2a on, for a settle
  window too short to see a 22-character keystroke marker land. Three of that
  harness's first four verdicts about the product were the instrument.
  **Before believing any gate verdict, ask what would have to be true for the
  instrument to produce it by accident.**

- **An instrument that verifies arrival does not verify fidelity.** The
  Accessibility read-back in `gate_2a_inject.py` confirms injected text reached
  the target, and it cannot see macOS text substitution, because it reads the
  raw value before the substitution settles. A clean four-application PASS was
  one step from being recorded while the keystroke strategy was silently
  rewriting every transcript. When a check answers "did X arrive?", ask
  separately whether it answers "did X arrive *unchanged*?"

- **Check which model a performance rule was measured on before inheriting it.**
  §7.2's 1.8x `cpu_threads` penalty was measured on `distil-large-v3` — the
  model the same revision rejected by ~7x. On `tiny.en`, the model it selects,
  4 threads is 1.02x of the performance-core count and the optimum is 6-8,
  *below* it. The E-core half of the rule survived and is worth more than
  claimed (14 threads costs 2.08x). A rule and its evidence can outlive the
  thing the evidence was about. Found 2026-08-01.

- **A corpus can be unable to answer the question it looks built for.** §7.4
  calls silence trimming the dominant latency lever; over the Phase 1 corpus it
  removed **9%** and cost 30 ms p50, close to net-negative. The corpus was
  recorded with `ffmpeg -t`, tightly cropped, with no dead air in it. Real
  dictation has dead air — `manu transcribe` trimmed one 9.9 s capture to 2.0 s.
  Nothing about the corpus signals the limit; it just quietly measures a
  different thing.

- **Freeze the input before comparing approaches.** `experiments/asr-baseline.json` holds
  the `tiny.en` transcripts once, so candidate post-processing approaches are compared on
  identical data rather than each re-running ASR and measuring its variance too.

- **A generated index that names filenames is green on records it cannot see.**
  `scripts/regenerate-sentinel-index.py` hardcoded three exact paths, so a *second*
  objection record in the same directory was invisible: it reported
  `sentinel index: up to date` with nine pending objections on disk, and `--check` is
  a CI constraint. Same failure as `sentinel-integrity-check.sh` passing on zero
  agents — green because it looked at nothing. Fixed 2026-07-31 to glob the record
  directories. **When a checker reports clean, confirm what it enumerated.** Both
  instances of this bug on this project were discovered by asking that question, not
  by the checker.

- **A corpus built to measure one thing cannot be reused to measure another.**
  `tests/fixtures/asr/` was recorded by reading prepared scripts, because measuring
  WER requires a known reference. Four Phase 5 experiments were then run against it
  to test *disfluency removal* — and none improved WER, because reading a script
  produces no disfluencies. `05-noisy`'s own reference says "while I read this
  sentence". The result looked like four converging negatives and was actually one
  confound. **Before reusing a fixture, state what its construction guarantees is
  present, not just what it contains.** An experiment record then claimed the
  disfluencies "do not survive Whisper's decoder" — an assertion nothing had tested,
  stated with the confidence of a measurement.

- **`advocatus-diaboli` delivered on the third ask, in a minimal format.** Two full
  re-asks produced idle notifications and nothing else; the ask that worked was
  *"reply with four lines, each naming a section and its strongest objection"* — and
  it then resent the complete nine-objection record unprompted. Ask for the smallest
  useful shape rather than the record, and the record often follows. Also: it opened
  with "my earlier output went to plain text, which you cannot see", which means the
  analysis had been completing all along and only the delivery channel was failing.

- **macOS text substitution rewrites synthetic keystrokes.** `strategy =
  "keystroke"` is not a slower-but-faithful alternative to clipboard paste.
  Injected into TextEdit, `don't use --dashes... "quoted" and i said so` arrives
  as `don't use —dashes… "quoted" and I said so` — smart quotes, em dash,
  ellipsis and autocapitalisation, five changes in one sentence. Pasting the
  same string is byte-identical. Nothing in this app can reach another app's
  substitution settings. Found 2026-08-02.

- **The Accessibility grant belongs to the hosting binary, not to `manu`.**
  `CGPreflightPostEventAccess()` returned True on a machine that had never seen
  this project, because the terminal running Python already held the grant. Any
  remediation message must name the *terminal*, not "Amanuensis", until Phase 4
  packages an `.app`. Corollary: a permission check passing locally says nothing
  about a packaged build.

- **Electron ships its accessibility tree switched off.** VS Code answers
  `kAXErrorNoValue` (-25212) to every AX query until
  `AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)` is set —
  and it does not appear synchronously afterwards, so the read has to be
  retried. `scripts/gate_2a_inject.py` first reported VS Code as unmeasurable,
  then "passed" only because a throwaway probe had set the flag by hand minutes
  earlier. **A gate whose result depends on something a previous command did is
  not a gate.**

- **A stage that runs after the user has their text is not in G1.** §2 ends G1
  at "text fully present in the focused application". The clipboard restore runs
  after that and cost ~155 ms; charging it to `inject_ms` reported a 272 ms
  delivery as a 422 ms G1 *miss* on the first real dictation. Three phases
  running have now found a stage `LatencyBreakdown` could not express —
  `vad_ms`, `persist_ms`, `restore_ms`. Before adding a stage, decide which side
  of "fully present" it falls on.

- **Lazy imports move a cost, they do not remove it.** The first `inject()` cost
  **165.8 ms** and every later one under 2 ms, because `import AppKit` and
  `import Quartz` land inside it — 165 ms against a 400 ms budget, on the user's
  *first* dictation. Phase 2a avoided it only because the permission check and
  the clipboard-manager detection happen to touch both bridges first. Any lazily
  imported dependency on a latency-gated path needs a `warm_up` that something
  actually calls.

- **Check the command doc for output paths, not the agent's suggestion.** The
  cost-estimator recommended `observability/costs/`; the canonical path in
  `commands/cost-estimate.md` is `cost-estimates/<YYYY-MM-DD>-<slug>-estimate.md`.
  Writing to the former would have let a prospective estimate be read back later as a
  retrospective cost snapshot.

## ARCH_DECISIONS

<!-- Key architectural decisions and the reasoning behind them.
     Each entry: what was decided, why, and what the alternatives were. -->

<!-- Example:
- Decision: use event sourcing for order state rather than a status column.
  Reason: audit requirements demand a complete history. A status column
  discards intermediate states. Alternatives considered: audit log table
  (rejected — dual-write consistency risk), soft deletes (rejected — does
  not capture partial fulfilment events).
-->

## TEST_STRATEGY

<!-- How tests are structured in this project. Helps agents write consistent
     tests without reading every test file from scratch. -->

<!-- Example:
- Unit tests live alongside source files as _test.go (Go) or *Spec.kt (Kotlin)
- Integration tests are in tests/integration/ and require a running database
- Use table-driven tests for anything with more than three input variations
- Mock at the interface boundary, not the concrete type
-->

## DESIGN_DECISIONS

<!-- Interface contracts, data shapes, and design choices that are stable and
     that agents should not second-guess without good reason. -->

<!-- Example:
- All public API endpoints accept and return JSON with the envelope shape:
  { "data": ..., "error": null | { "code": string, "message": string } }
  Changing this shape would break the mobile clients.
-->
