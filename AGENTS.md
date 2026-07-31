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

- **Adjudicating objections creates new unmapped decisions.** Twelve accepted objections
  amended the PRD heavily in one day; the cartographer's second pass returned 13 stories,
  7 of them mapping choices the amendments had just introduced. Re-run the cartographer
  after a batch of accepted objections — a single pass maps the document as written, not
  what the fixes bring in.

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
