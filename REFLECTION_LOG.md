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
- **Agent**: main session (sentinel pipeline dispatch)
- **Task**: Ran carpaccio, advocatus-diaboli, choice-cartographer and cost-estimator against AMANUENSIS_PRD.md, then adjudicated all 12 objections and all 7 slices, and re-ran the cartographer against the amended PRD.
- **Surprise**: Three separate failure modes in the vendored habitat, none of which announce themselves:
  1. Every sentinel agent file declares its charter as `ai-literacy-superpowers/skills/<name>/SKILL.md` — a repo-relative path that resolves to nothing in an installed project. The real location is `~/.claude/plugins/cache/ai-literacy-habitat/ai-literacy-habitat/<version>/skills/`. An agent dispatched without an absolute path silently improvises its own charter and returns something that *looks* conformant.
  2. `scripts/sentinel-integrity-check.sh` globs `*.agent.md`; installed agents are `*.md`. It matches nothing, counts nothing, and exits 0 with `sentinel integrity: OK (0 role-tagged agent(s) checked)`. The `0` is the only tell.
  3. The installer discovers `CLAUDE.md` as absent, ships a 9.3 KB template for it, and has no write step that installs it. `ONBOARDING.md` is shipped and referenced nowhere in `src/`.
- **Proposal**: Add to GOTCHAS — when dispatching any sentinel, pass the resolved absolute skill path in the prompt, and treat `0 role-tagged agent(s) checked` from the integrity script as a failure signal rather than a pass.
- **Improvement**: Sentinels are read-only and return record content as message text. Two of four went idle without sending anything on first ask; the dispatch prompt must say explicitly "you have no write tools, message text is the only channel, do not describe the record — paste it." Also: the cost-estimator's own recommended output path (`observability/costs/`) contradicted the `/cost-estimate` command's canonical `cost-estimates/<date>-<slug>-estimate.md`. Check the command doc, not the agent's suggestion.
- **Constraint**: none
