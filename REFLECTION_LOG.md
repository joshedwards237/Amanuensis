# Reflection Log

<!-- GENERATED FILE — do not edit by hand.

     This file is a deterministic aggregate of the per-entry fragments in
     reflections/active/ (one file per reflection, so concurrent reflections
     never collide on a shared file and can never be silently dropped at
     merge time). Add a reflection with /reflect, which writes a fragment and
     regenerates this file; never append here directly. Regenerate with:
     scripts/regenerate-reflection-log.sh

     Each entry below mirrors one fragment. Fragment body format (no leading
     `---` — the separator belongs only to this aggregate):

     ---

     - **Date**: YYYY-MM-DD
     - **Agent**: integration-agent
     - **Task**: [one-sentence summary]
     - **Surprise**: [anything unexpected during the pipeline run]
     - **Proposal**: [pattern or gotcha to consider for AGENTS.md, or "none"]
     - **Improvement**: [what would make the pipeline smoother next time]
     - **Constraint**: [proposed constraint text, or "none"]

     Do NOT modify AGENTS.md directly from this log — only propose. Humans
     curate AGENTS.md. The value of this log is that it provides the raw
     material for curation, not that it auto-populates memory.

     -->

---

- **Date**: 2026-07-31
- **Agent**: main session (disposition pass)
- **Task**: Disposed 12 spec-mode objections as accepted over one working day, amending the PRD after each batch, then re-ran the choice-cartographer against the result.
- **Surprise**: Resolving objections *generates* silent decisions at roughly the rate it resolves them. The cartographer's second pass retired two of its ten original stories and returned thirteen — seven of them mapping choices the amendments themselves had just made. Concretely: fixing G1's measurability (O1) turned it into a hardware-tier property, which is a user-base segmentation nobody decided; fixing the LLM budget conflict (O11) produced a Phase 5 budget that is G1 plus the ceiling, so its gate cannot fail by construction; and adding `docs/gates/` (O9) created a fifth decision-record surface while choice-story #10 was pointing out there were already four with no routing rule between them. The adjudication pass is not a net reduction in unmapped decisions unless something re-reads the result.
- **Proposal**: Add to ARCH_DECISIONS or GOTCHAS — after a batch of accepted objections materially amends a spec, re-run the cartographer before treating the spec as settled. A single pass maps the document as written; it cannot map what the fixes introduce.
- **Improvement**: Run the cartographer *after* diaboli dispositions, as the pipeline intends. Running them concurrently cost a full second pass, and the first-pass record could cite no objection IDs at all. The sequencing is not ceremony.
- **Constraint**: none

---

- **Date**: 2026-07-31
- **Agent**: main session (probe, engine benchmark)
- **Task**: Measured whether G1 (p50 ≤ 400 ms) is reachable on target hardware, across five candidate ASR models.
- **Surprise**: Every serious latency problem this project had was a **default nobody had checked**, not a limit of the hardware or the model.
  1. **`vad_filter` was the whole p95 story.** `base.en` on a 25 s sample: 6,039 ms off, **541 ms** on. `small.en`: 23,886 → 1,438 ms. The cause is decoder repetition looping on silence — `condition_on_previous_text=False` alone recovers most of it. Without VAD *no* candidate passed G1's p95; with it, `tiny.en` passes both p50 (328 ms) and p95 (420 ms). The PRD called trimming "a free latency win on every mode"; it is actually what stands between the product and a 26-second worst case.
  2. **CTranslate2 defaults to 4 threads.** On a 14-core M3 Max that cost 1.8× — 4,413 ms vs 2,412 ms for the identical model. The probe's first run returned NO-GO on that default, which would have fired the project's top risk on a library setting rather than on physics.
  3. **The spec's own model table was wrong by ~7×.** §7.2 sent Apple Silicon to `distil-large-v3` (2,412 ms) where `base.en` does the job in 352 ms — because **CTranslate2 has no Metal backend**, so "Apple Silicon" was a CPU tier wearing an accelerator's name.
- **Proposal**: For GOTCHAS — when a latency budget is missed, check library defaults and preprocessing flags *before* changing model or architecture. The three fixes above were a config flag, a thread count, and a smaller model. None required a design change.
- **Improvement**: Latency work should start by measuring the **tail**, not the median. A p50 from one clean sample said GO; the p95 over six real samples said the opposite, and the p95 is what a user feels. The probe measured only p50 because it only had one clip — the corpus is what exposed it.
- **Constraint**: proposed — any latency figure entering the PRD carries both p50 and p95, or is labelled as a floor. A bare median has already misled this project once.

---

- **Date**: 2026-07-31
- **Agent**: main session (probe, Phase 1 benchmark, Phase 5 feasibility)
- **Task**: Ran the pre-Phase-0 probe and the Phase 1 engine benchmark, scoped the LLM second pass, and amended the PRD from the results.
- **Surprise**: Four of five claims made during this session were falsified within hours, by measurement, not by argument. `base.en` was named in §7.2 on a 352 ms p50 from one clip — its p95 over a real corpus was 5,810 ms against a 800 ms budget. The combined Phase 5 latency was estimated at 718 ms and measured at 373–2,201 ms. Cold start was flagged as a risk at 48 s and measured at 3.43 s (the 48 s was a *download*, not a load). Phase 5 was un-deferred on three hand-written cases and killed by the first real test. **The one claim that survived was the one made most defensively**: four safety constraints written *before* testing, which then caught 100% of catastrophic failures.
- **Proposal**: For GOTCHAS — a spec amendment justified by an estimate should carry the estimate's `n` in the amendment text, not only in the record it cites. §7.2 said "provisional" but named a model, and a named default is what gets built.
- **Improvement**: **Phase 5 was deferred, un-deferred, and killed in one day** — three positions in eight hours, and the whiplash was self-inflicted. The un-defer recommendation rested on three prompts I wrote myself, and the feasibility record I authored listed "untested on the ASR output that will actually feed it" as an open unknown. That unknown was the entire answer. The test that killed it cost about twenty minutes and could have run before the recommendation. **Rule: when a feasibility record names an untested assumption, test it before recommending, not after.** A self-authored n=3 is worse than no test — it manufactures confidence.
- **Constraint**: none

---

- **Date**: 2026-07-31
- **Agent**: main session (sentinel pipeline dispatch)
- **Task**: Ran carpaccio, advocatus-diaboli, choice-cartographer and cost-estimator against AMANUENSIS_PRD.md, then adjudicated all 12 objections and all 7 slices, and re-ran the cartographer against the amended PRD.
- **Surprise**: Three separate failure modes in the vendored habitat, none of which announce themselves:
  1. Every sentinel agent file declares its charter as `ai-literacy-superpowers/skills/<name>/SKILL.md` — a repo-relative path that resolves to nothing in an installed project. The real location is `~/.claude/plugins/cache/ai-literacy-habitat/ai-literacy-habitat/<version>/skills/`. An agent dispatched without an absolute path silently improvises its own charter and returns something that *looks* conformant.
  2. `scripts/sentinel-integrity-check.sh` globs `*.agent.md`; installed agents are `*.md`. It matches nothing, counts nothing, and exits 0 with `sentinel integrity: OK (0 role-tagged agent(s) checked)`. The `0` is the only tell.
  3. The installer discovers `CLAUDE.md` as absent, ships a 9.3 KB template for it, and has no write step that installs it. `ONBOARDING.md` is shipped and referenced nowhere in `src/`.
- **Proposal**: Add to GOTCHAS — when dispatching any sentinel, pass the resolved absolute skill path in the prompt, and treat `0 role-tagged agent(s) checked` from the integrity script as a failure signal rather than a pass.
- **Improvement**: Sentinels are read-only and return record content as message text. Two of four went idle without sending anything on first ask; the dispatch prompt must say explicitly "you have no write tools, message text is the only channel, do not describe the record — paste it." Also: the cost-estimator's own recommended output path (`observability/costs/`) contradicted the `/cost-estimate` command's canonical `cost-estimates/<date>-<slug>-estimate.md`. Check the command doc, not the agent's suggestion.
- **Constraint**: none
