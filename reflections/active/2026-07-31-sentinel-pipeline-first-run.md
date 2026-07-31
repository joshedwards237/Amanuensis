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
