---
target: AMANUENSIS_PRD.md
target_kind: spec
generated_at: 2026-07-30T00:00:00Z
generated_by: "cost-estimator / claude-opus-5"
grounding_sources:
  - path: MODEL_ROUTING.md
    kind: model-routing
  - path: observability/costs/
    kind: cost-snapshot
tokens: { low: 580000, high: 1750000 }
tokens_by_stage:
  - stage: carpaccio
    tokens: { low: 24000, high: 96000 }
    model_tier: Flagship
  - stage: spec-writer
    tokens: { low: 96000, high: 240000 }
    model_tier: Flagship
  - stage: advocatus-diaboli
    tokens: { low: 96000, high: 480000 }
    model_tier: Flagship
  - stage: choice-cartographer
    tokens: { low: 48000, high: 240000 }
    model_tier: Flagship
  - stage: cost-estimator
    tokens: { low: 24000, high: 96000 }
    model_tier: Balanced
  - stage: tdd-agent
    tokens: { low: 48000, high: 120000 }
    model_tier: Balanced
  - stage: implementer
    tokens: { low: 150000, high: 240000 }
    model_tier: unrouted
  - stage: code-reviewer
    tokens: { low: 48000, high: 120000 }
    model_tier: Balanced
  - stage: integration-agent
    tokens: { low: 24000, high: 60000 }
    model_tier: Efficient
  - stage: orchestrator
    tokens: { low: 24000, high: 60000 }
    model_tier: Flagship
agent_compute_time: { low: 1h, high: 8h45m }
human_gate_time: "human-gate latency dominates total wall-clock and is not estimated numerically at S1; it depends on when a human next disposes a gate, not on the work. This target is unusually gate-heavy: §9 defines six approval gates, and the orchestrator adds Slice Adjudication, Objection Adjudication, Plan Approval, and Integration Approval per pipeline run — several of the §9 gates additionally require the human to run hardware measurements, dictate into four applications, or recruit a second installer before the gate can be disposed."
confidence:
  tokens: medium
  time: low
failure_direction: likely-underrun
---

## Included

The full agent pipeline the orchestrator defines (`.claude/agents/orchestrator.md` §Pipeline: T0 cost-estimator → carpaccio → spec-writer → advocatus-diaboli spec-mode → choice-cartographer → tdd-agent → implementers → code-reviewer → advocatus-diaboli code-mode → integration-agent), applied across PRD §9 Phase 0 through Phase 5, each stage at the literal tier this repo's `MODEL_ROUTING.md` Agent Routing Table assigns it. The `advocatus-diaboli` entry covers both of its per-run invocations (spec-mode 1a and code-mode 4a) in one figure.

Token figures are **generation tokens**, anchored on this repo's Token Budget Guidance table, which supplies **per-invocation suggested maxima** (Spec writing 8 000; Test generation 4 000; Implementation per file 6 000; Code review 4 000; CHANGELOG + commit 2 000; Orchestrator planning 2 000) rather than the per-role whole-stage ranges the estimation methodology's worked examples assume. Two derived multipliers convert those caps into stage totals, and both are assumptions stated here rather than read from a table:

- **Implementation:** PRD §6.4 enumerates 25 source files; allowing for files touched in more than one phase, plus tests, the estimate assumes 25–40 file-touches at the 6 000 per-file cap. The §6.4 tree is counted as written, including `injection/windows.py` and `injection/linux.py`, which §9 never explicitly schedules.
- **Pipeline runs:** the estimate assumes 12–30 full pipeline runs across the six phases (carpaccio slices each phase into thin end-to-end pieces; the six phases are not six PRs), and 6–12 task-level dispatches for carpaccio and the T0 cost-estimator, which run once per task rather than once per slice.

Four exercised stages — carpaccio, advocatus-diaboli, choice-cartographer, cost-estimator — have **no row of their own** in the Token Budget Guidance table. Their per-invocation figures are anchored by a disclosed **budget-row proxy**: bracketed between the Code review row (4 000, low) and the Spec writing row (8 000, high), on the grounds that all four emit a review- or spec-shaped prose record. This is a token-budget proxy only; it is unrelated to the cost cross-tier proxy, which is not in play here because cost is omitted.

Agent-compute time is derived from the whole-record token range via the default throughput band of ~1–3 minutes per 10k tokens generated, stated here as an assumption, not an observed actual. The band and the token figure are consistent in scope — both are generation-side.

The whole-record token band (580 000–1 750 000) is the rounded arithmetic sum of the per-stage bands (582 000–1 752 000). The stages are **positively correlated** — nearly all of them scale with the same underlying slice-count driver — so the joint all-low and all-high outcomes are plausible and the sum is not narrowed toward the middle as it would be for independent stages.

## Excluded

**cost_usd: omitted** — `observability/costs/` was inspected and contains only a `.gitkeep`; no snapshot exists, so no observed $/token rate is available and cost is not estimated. There is no list-price fallback; token and time figures stand. `cost_basis` and the `confidence.cost` axis are absent for the same reason.

A second, independent obstacle to pricing is recorded here so it is not mistaken for a consequence of the empty directory: this repo's `MODEL_ROUTING.md` names the tiers **Flagship / Balanced / Efficient**, while the estimate-record binding table is keyed on **Most capable / Standard / Standard / Capable**. The two vocabularies share no label, so the binding table has **no join key** against this repo and **no substitute mapping was invented**. Each stage's `model_tier` records the literal label this repo's routing table assigns. Because cost is omitted for want of a snapshot, this mismatch changes no number in this record — but a snapshot landing tomorrow would not by itself make these tiers resolvable to model families. No stage here carries a slashed tier label, so the split-tier widening rule is not exercised.

**No `implementer` agent exists** in `.claude/agents/` and the Agent Routing Table has no `implementer` row. The orchestrator's step 3 dispatches implementers per language or implementation domain, so the stage is exercised; its tier is therefore excluded from this record rather than assigned, and is recorded as `unrouted`.

Also excluded:

- **Input and context tokens.** The Token Budget Guidance table caps generation only; per-invocation input (agent definitions, the PRD, the spec, prior test and source files, conversation history) is not covered by any grounding source read here and is not estimated. This is the largest single omission in the record.
- **Human-gate latency** — gates cost wall-clock, not tokens.
- **Human work the gates require but agents do not perform**: the Phase 1 latency measurement on real hardware, the Phase 1 faster-whisper vs. Moonshine benchmark run, the Phase 2 dictation trials across four applications, the Phase 3 ten real ≥60-second dictations and edit-rate tally, and the Phase 4 second-person install. These consume no agent tokens and are absent from `agent_compute_time`.
- **Re-runs beyond one pass**: the code-reviewer → implementer loop (up to `MAX_REVIEW_CYCLES = 3`), carpaccio re-dispatch on `disposition: revised` slices, and spec re-work following objection dispositions.
- **Stages outside the build pipeline** that this target does not exercise: `assessor`, `governance-auditor`, `reservoir-warden`, and the four `harness-*` agents.
- **PRD §12 read-back / Kokoro**, which §12 places outside the Phase 0–5 tree, and the §11 open decisions (settings UI, model-distribution mechanism) to the extent they are unresolved.

## Confidence rationale

**tokens: medium** — the `target_kind` ceiling is `high`, and the PRD earns that ceiling on **scope**: §6.2 fixes the component boundaries, §6.3 the class contracts, §6.4 a near-complete file tree, and §9 a six-phase plan with gates. The axis nonetheless sits one tier below the cap because the **token grounding** is thin where the scope grounding is thick. Three layers of derived judgment separate the routing table from these figures: the budget table supplies per-invocation caps, not stage totals; four exercised stages are priced by the budget-row proxy described in `Included` (the `advocatus-diaboli` entry, at 96k–480k, is the single largest proxy-derived contributor and exceeds the implementer stage at its high bound); and the 12–30 pipeline-run multiplier is a 2.5× assumption read off the phase structure, not off any record. `observability/costs/per-pr/` does not exist, so no per-PR actuals were available to calibrate the ranges against this repo's own history — the figures are generic budget-derived, exactly the pre-calibration day-one state. The §6.4 tree is also not exhaustive against §6.2: `ParakeetEngine` appears in the component diagram with no corresponding file, which is one indication that the file count is a floor rather than a census.

**time: low** — one tier below tokens, for compounding reasons. The throughput band is an assumption rather than an observed actual; it is applied to a token range that is itself an assumption-laden band spanning 3×; and the band yields **serial** agent-compute, while orchestrator step 3 dispatches implementers in parallel, which compresses real wall-clock by an unmodelled factor. The resulting 1h–8h45m band should be read as a rough order of magnitude for agent generation time only.

**cost** — no axis is present; see `Excluded`.

**On the coarseness of a single whole-product band.** A 580k–1 750k token range spanning six phases is a coarse instrument, and the 3× spread is the honest expression of that coarseness rather than a defect to be tuned away. Most of the width comes from the slice-count assumption, which the PRD does not fix and which only carpaccio can resolve per phase. The record's structure decomposes by **stage**, not by phase, so it cannot localise the width to Phase 2 versus Phase 5; a per-phase estimate against a per-phase slicing record would be a different and materially narrower record, and this one does not stand in for it.

## Failure direction

**likely-underrun.** Several drivers bear on the direction and they do not all point the same way. Pushing toward underrun, in rough order of magnitude: input and context tokens are excluded entirely, and in an agent pipeline they typically exceed generation tokens by a large multiple; the 12–30 pipeline-run assumption is anchored on six phases that carpaccio will slice more finely; the review loop, carpaccio re-dispatches, and post-objection spec re-work are all counted at one pass only; and total wall-clock omits both human-gate latency and the substantial human measurement work the §9 gates require. Pushing toward overrun, and smaller: the budget-table figures are "suggested max" ceilings that many invocations will land below, and the four proxy-anchored stages could be over-bracketed at the 8 000 high end. The excluded-input driver alone is larger than the ceiling-slack driver, so the dominant direction is underrun.
