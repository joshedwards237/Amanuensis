---
spec: docs/superpowers/specs/phase-3-postprocessing.md
task_slug: phase-3-postprocessing
date: 2026-08-08
mode: spec
cartographer_model: claude-opus-5
authored_by: "choice-cartographer sentinel, dispatched without `name:` against revision 2, after all 12 diaboli objections were dispositioned. Third delivering sentinel in this repository."
stories:
  - id: 1
    lens: [patterns, consequences]
    title: An optional-capability Protocol keeps the ABC frozen
    disposition: accepted
    disposition_rationale: "The Extension Interface reading is correct and the naming is useful — this is Go's optional-interface upgrade idiom and the spec named neither the pattern nor its cost. The consequence that changes the build: `runtime_checkable` checks METHOD PRESENCE ONLY, so a processor declaring `process_traced(self, text)` satisfies `isinstance` and fails at the call. The first contract has a guard test and the second would have had none. `tests/test_contracts.py` therefore gains a signature check for `TracedPostProcessor` — parameter names and count, matching what `test_postprocessor_process_takes_the_session_it_must_not_mutate` already does for the ABC. The third consequence is accepted as a stated cost rather than fixed: a user reading `chain` cannot tell whether `fired_entries` will be populated, because the chain names processors and not capabilities. Fixing that means surfacing capabilities in config, which is a worse trade than a documented asymmetry."
  - id: 2
    lens: [defaults, coherence]
    title: "\"Off by default\" is now the unwritten evidence bar"
    disposition: accepted
    disposition_rationale: "The trap is real and I had walked into it: `spoken_commands = false` guarantees the gate reports a firing rate of zero, and zero reads as 'it did no harm' to the author and as 'delete the code' to `04-rules-only.md` §7.3's fifth constraint. A gate line item disarmed by the same default that admitted the code is not a counterweight. The dry-run alternative is adopted, in the form the record did not propose and which costs nothing: **the rule always counts its candidate matches into the trace and transforms only when enabled.** No tri-state key, no new config value, no lossiness — the gate gets a real firing rate from ten sixty-second dictations while the transformation stays off. That is the fifth constraint satisfied rather than deferred. The policy question the record raises — what 'off by default' is FOR, quarantine or permanent optionality — is answered in §5.3 as part of this phase: quarantine carries an obligation to measure, and this is the mechanism that discharges it."
  - id: 3
    lens: [consequences, alternatives]
    title: Rules stay context-blind while boosting learns context
    disposition: revisit
    disposition_rationale: "Deferred to Phase 4, unchanged, and the deferral now carries the record's strongest point rather than only O7's evidence: by the time Phase 4's second consumer arrives, `[boost.apps]` is a SHIPPED CONFIG FORMAT users have written files against, so generalising it into an `[apps]` table is a migration rather than a design. That cost is created by this phase and paid by the next one, and it is recorded here so Phase 4 inherits the reasoning instead of the conclusion. The record also catches something the spec did not state: §A2's rejection of R2 forecloses the transcript-conditioned alternative — 'do not append when the text looks like a path or a URL' — because that is the same silent heuristic A2 refuses. So the deferral is not between a global boolean and a cheap fix; it is between a global boolean and per-application configuration, and there is no third option. §A4 is amended to say so."
  - id: 4
    lens: [forces, coherence]
    title: "`chain` is the bounded exception's fourth collision"
    disposition: accepted
    disposition_rationale: "The sharpest structural finding in the record. §5.3 warned that enumerating a fourth EXCEPTION would be the wrong response to the next collision; what arrived is a fourth TECHNIQUE — qualify the guarantee rather than remove the key — and the warning does not cover it. The project now has two ways to reconcile a key with a guarantee and nothing says which applies when. Accepted and written into §5.3 under the name the record supplies: G1 has a REFERENCE CONFIGURATION (Tier A, ten seconds, `chain = [\"rules\"]`), and a guarantee measured against one is qualified by it rather than protected by withholding the key. The record is also right that G2 is next in line and that E3's freeze-and-digest is the same move applied to it — which is worth seeing before it is done a third time by accident. The `chain`-must-start-with-rules validator is REJECTED: it would make every legal chain a superset of G1's basis by fiat, which is a constraint on the user to protect a number rather than a statement about the number."
  - id: 5
    lens: [defaults, coherence]
    title: A second config file with a different lifecycle contract
    disposition: accepted
    disposition_rationale: "The consequence is the part that changes the build, and it is C3's original complaint reintroduced one layer down: a user who edits `vocabulary.toml` WHILE THE DAEMON IS RUNNING never sees B8's load error, so the validation surface they meet depends on whether the daemon happened to be running when they saved. That reads as 'my entry did not work'. Three surfacings, all cheap: the daemon prints the parse error to stderr once per distinct failure rather than silently keeping the old map; the session records it; and `manu vocab check` re-reads the file directly, so it raises the real `ConfigError` with the key named — which makes the debugging verb the place the error is actually legible, and is the reason V4 survives at all. The two-contract split is accepted as stated rather than unified: strict at startup, permissive at reload, because at reload the daemon is holding a transcript and §8's posture rejects losing it to a typo. The record is right that a third user-editable artefact has nothing to inherit; §5.3 now states the split as a rule rather than per file."
  - id: 6
    lens: [consequences, forces]
    title: The user's own file now spends the gated budget
    disposition: accepted
    disposition_rationale: "Verified against the spec before dispositioning and the gap is exactly as described: E1's only ceiling is `postprocess_ms` p95 <= 5 ms, and `vocab_ms` has a field, a column, a gate measurement and NO BAR. The phase's one new unbounded-input stage is the one stage with no budget, and its cost is a function of an artefact the user authors — so a large enough `vocabulary.toml` moves a published guarantee with no code change (the dictionary spec measured 18.4 ms at 5000 entries for match time alone). E1 gains a second ceiling: **`vocab_ms` p95 <= 10 ms**, derived the same way the first was — the compile is paid only on the dictation after an edit, and 10 ms is the point past which the user testing their new entry would feel it. The third-category option is REJECTED: excluding a stage from `g1_ms` because its cost is the user's would let any future stage escape the same way, and §2's exclusions (`capture_ms`, `restore_ms`) are both justified by falling outside the hotkey-release-to-text window, not by whose fault the cost is. The record's third consequence is accepted verbatim into the gate record's structure: the dictionary's cost lands in G1 and its benefit in G2, reported against different criteria at the same gate, so the trade the feature rests on is never stated in one place. The gate record states it in one place."
  - id: 7
    lens: [forces, consequences]
    title: Empty terms and a key space the product never shows
    disposition: accepted
    disposition_rationale: "The discoverability gap is real and foreclosed by silence rather than by reasoning — §6.1's argument against `add`/`list`/`boost` is that they duplicate a text editor, and printing the frontmost bundle identifier duplicates nothing the user can do without `osascript`. Adopted in the additive form the record proposes: **`manu vocab check --app`** prints the frontmost application's bundle identifier and the boost terms currently resolved for it. One flag on a verb that already exists. Without it, `[boost.apps]` is a first-class config key whose values a user can only obtain from a platform incantation they have to find, and dictionary story C6 — 'the user is assumed to be someone who edits TOML by hand', still pending — was raised against a flat word list and is raised harder by per-application keying. C6 should be dispositioned against this version, not the one it was written about. The inherited consequence is correctly NOT re-attributed and is worth carrying forward: with `terms = []` and no `initial_prompt`, the new 'was any bias applied' question answers no for the shipping default, so `DictationState.RECOVERED` is unreachable out of the box — dictionary C4's recorded consequence, now true of the recommended configuration rather than an edge case."
  - id: 8
    lens: [consequences, coherence]
    title: Un-excusing proper nouns binds phases that cannot reach them
    disposition: accepted
    disposition_rationale: "Accepted, and the remedy is NARROWED to the record's second option, which is materially better than what E1 wrote. Un-excusing proper nouns wholesale makes the gate fail on the CORPUS'S SCOPE rather than on the DICTIONARY'S MISSES — entry count is not coverage, and a proper-noun failure would have had two causes the instruments cannot separate. So §9's amended clause counts proper-noun errors **for terms present in the frozen `vocabulary.toml`**; proper nouns the vocabulary does not cover stay excused, because for those §9's original reasoning is still correct — they do point at §5.6 rather than at a phase failure. This also answers the record's second consequence, which is the one with the longest reach: `04-rules-only.md` §5 measured 87.2% of corpus errors as ASR mistranscription that no downstream pass can recover, and a wholesale un-excusing would have handed Phase 5 a reject clause counting a class it structurally cannot address — §7.5 has already recorded one Phase 5 criterion that could not do its job. The third consequence is accepted as a disclosure rather than a change: §9 still permits moving G2's 5% with a stated reason, so the qualitative escape is closed and the numeric one is not, and both are exercised by the same person at the same sitting. The gate record names that pairing."
  - id: 9
    lens: [alternatives, consequences]
    title: A second door into daemon state, one phase before IPC
    disposition: accepted
    disposition_rationale: "The temporary-shape-becomes-the-shape consequence is the durable one and is recorded rather than designed away: after this phase, IPC arrives into a world where history already works without it, so floor item 3's only real consumer is `toggle`/`status`. That is a genuine cost of shipping the verb now, and it is accepted because §5.5 gap 3 has been open since Phase 2a and the orphans are plaintext transcripts the user was never told about. The read-only-now option is rejected for the same reason: §5.5 names `--purge` and a user who cannot purge is a user accumulating the artefact the command exists to remove. The concrete change the record produces: **WAL adds `-wal` and `-shm` sidecar files, and `--purge`'s inventory has to grow to cover them**, in the code and in the README. §5.5's erasure disclaimer already absorbs the semantics — it explicitly declines to reason about `secure_delete`, `VACUUM` and WAL checkpointing — so what is owed is the inventory, not a new privacy claim."
  - id: 10
    lens: [consequences, coherence]
    title: Two transcripts stored, one shown, neither named canonical
    disposition: accepted
    disposition_rationale: "The spec chose by silence and the record is right that the silence is the decision. The phase that makes the rule trace persistable was shipping the only viewer of that data with no way to see what the rules changed — a user suspecting a `[replace]` misfire could read `fired_entries`, re-run `manu vocab check`, and could not see the raw text without opening SQLite by hand. That is dictionary O5's complaint surviving its own fix. Adopted: **`manu history --last` prints both when they differ**, labelled, and `--raw` prints the raw alone. Cheap, and it closes the loop O5 opened. The deeper question — which column IS the §8 artefact — is NOT settled here and is recorded as open rather than answered by implication: naming `raw` canonical would make the crash guarantee independent of the processor chain, which is what §7.5's Phase 5 constraint assumes, and would also make `manu history --last` show text the user did not receive. That trade needs Phase 5's evidence. What this phase fixes is that the question is now ANSWERABLE, which it was not before B0. E2's per-dictation list gains the pair, since it is where the two would first have been compared."
---

# Choice-story record — Phase 3, post-processing and retention

**Target:** `docs/superpowers/specs/phase-3-postprocessing.md` (revision 2)
**Companion:** `docs/superpowers/objections/phase-3-postprocessing.md` — 12 objections, all accepted.
**Ten stories. All ten dispositioned: nine accepted, one deferred to Phase 4.**

## Provenance

**A sentinel produced this**, dispatched without `name:` against revision 2 after
every objection was dispositioned — the sequence the pipeline intends. Third
delivering sentinel in this repository, and the second in a row.

That sequencing is why the record can cite objection IDs, and it is also why
**six of the ten stories map decisions the dispositions themselves introduced**:
the Protocol beside the ABC, the `terminal_punctuation` key, `vocab_ms` inside
`g1_ms`, the §9 amendment, the second-writer posture, and the pinned `chain`
default did not exist in draft 1. The 2026-07-31 reflection predicted exactly
this — adjudication generates silent decisions at roughly the rate it resolves
them — and this run reproduces the ratio.

**Four stories changed the spec after it was called ready**, which is the
argument for running the cartographer at all rather than treating the objection
record as the end of review:

| | what it changed |
|---|---|
| #2 | `spoken_commands` counts candidate matches even when disabled, so the gate gets a real firing rate at zero lossiness |
| #6 | `vocab_ms` gains a p95 ceiling — the phase's one unbounded-input stage had a field, a column, a gate measurement and no bar |
| #8 | §9's un-excusing is narrowed to proper nouns the frozen vocabulary **covers**, so the gate fails on the dictionary's misses rather than the corpus's scope |
| #10 | `manu history --last` shows raw and final when they differ, closing dictionary O5 at the surface its own fix had left blind |

Two more produced smaller concrete work: #1 a signature guard for the new
Protocol, #7 the `--app` flag, #5 three surfacings of a reload error, #9 the
WAL sidecar files in `--purge`'s inventory.

## Decisions this record does not re-attribute

Named because a reviewer that claims every decision has read none of the prior
records. Each was made elsewhere and is inherited:

| decision | where |
|---|---|
| Hot-reloading `vocabulary.toml` | dictionary choice-story **C3**, human decision 2026-08-04 |
| Scoping `[boost]` per application | dictionary choice-story **C2**, 2026-08-04 |
| `vocabulary.toml` as a separate file; two tables | PRD §5.6, dictionary spec rev 2 §5.1, story **C7** |
| The retry having nothing to drop with no bias configured | dictionary choice-story **C4** |
| History storing post-processed text | dictionary choice-story **C5**, still `pending` — story #10 is the half C5 could not raise |

## The stories, in brief

Full analysis is the sentinel's and the disposition rationales above carry it.
One paragraph each, so the record is readable without them.

**#1 — An optional-capability Protocol keeps the ABC frozen.** `TracedPostProcessor`
beside `TextPostProcessor`, feature-detected at the call site. Alternatives: widen
the ABC and renegotiate its guard test; a second nominal ABC with `isinstance`;
a result object from `process`. The pattern is **Extension Interface** (POSA vol. 2)
and the spec named neither it nor its cost — `runtime_checkable` checks presence,
not shape, so the second contract needs a guard the first already has.

**#2 — "Off by default" is now the unwritten evidence bar.** Four rules, four
verdicts, three bars — and `spoken_commands` ships off with no measurement at all.
The unnamed force: not shipping leaves a §7.5 gap open across a phase boundary,
and shipping off costs nothing visible. Resolved by counting candidate matches
while disabled, so the gate reports a real rate rather than a structural zero.

**#3 — Rules stay context-blind while boosting learns context.** The phase builds
per-application configuration and declines to use it for the rule that fires 7
times in 10. Deferred to Phase 4 — and the deferral costs a migration, because
`[boost.apps]` will be a shipped format by then. §A2's rejection of R2 also
forecloses the transcript-conditioned alternative, which the spec had not noticed.

**#4 — `chain` is the bounded exception's fourth collision.** G1 is defined
against `chain = ["rules"]`, so a user enabling the dictionary leaves the
configuration the guarantee was measured under. §5.3's exception would say remove
the key, which is absurd here. The spec instead qualified the guarantee — a fourth
*technique*, where §5.3 warned only about a fourth *exception*. Named now:
G1 has a **reference configuration**.

**#5 — A second config file with a different lifecycle contract.** Load-once vs.
reload, fail-fast vs. fail-soft, injected vs. resolved-at-use: three axes, one file
boundary, no stated rule. The user-visible cost is that the validation surface
depends on whether the daemon was running when they saved.

**#6 — The user's own file now spends the gated budget.** `vocab_ms` is inside
`g1_ms`, correctly and mechanically. The property that introduces: a stage whose
cost is a function of a user-authored artefact now sits inside the number the
project gates on — and it was the only stage with no ceiling.

**#7 — Empty terms and a key space the product never shows.** `[boost.apps]` is
keyed on an identifier the product never displays, so the mechanism serves a user
who edits TOML *and* can name their applications the way macOS does. §4's
secondary user is furthest from that bar and is invoked elsewhere to justify
exactly this kind of recovery path.

**#8 — Un-excusing proper nouns binds phases that cannot reach them.** Removing
§9's excuse wholesale makes a proper-noun failure ambiguous between a weak
mechanism and a thin vocabulary, and hands Phase 5 a reject clause counting the
87.2% of errors no downstream pass can recover. Narrowed to covered terms.

**#9 — A second door into daemon state, one phase before IPC.** `manu history`
writes the database the daemon holds, and the transport that would avoid it is
Phase 4. The durable cost: history will work without IPC before IPC exists, so
the temporary shape becomes the shape.

**#10 — Two transcripts stored, one shown, neither named canonical.** B0 makes
"did the processors change my words?" answerable for the first time, and C2 ships
the only viewer without answering it. Fixed at the surface; which column is §8's
artefact is left open for Phase 5's evidence rather than settled by implication.

## Selectivity

Ten stories against a 5–8 bias. Four candidates were dropped by the sentinel and
the drops are recorded because a record that keeps everything has selected
nothing: `postprocess/registry.py` (argued in the spec, and the diaboli
explicitly declined to object); `--purge`'s confirmation prompt (thin);
the ISO-8601 cutoff (fully covered by objection O12); and `LEGITIMATE_DOUBLES` as
a hand-maintained guard list (failure-shaped, and inherited from
`exp4_rules_only.py` rather than decided here).
