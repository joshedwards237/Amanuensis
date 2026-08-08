---
spec: docs/superpowers/specs/phase-3-postprocessing.md
target: "DESIGN SKETCH, draft 1, 2026-08-08"
task_slug: phase-3-postprocessing
date: 2026-08-08
mode: spec
diaboli_model: claude-opus-5
authored_by: "advocatus-diaboli sentinel, dispatched without `name:` against the design sketch. Second delivering sentinel in this repository."
objections:
  - id: O1
    category: implementation
    severity: critical
    claim: "A3 says 'nothing about the loop changes'. The loop violates the TextPostProcessor contract and §8: a processor that raises loses the transcript entirely, and Phase 3 is the first phase in which a processor exists to raise."
    evidence: "dictation_controller.py:509-517 has no per-processor guard; the outer except at :522 returns at :525 before deliver() at :517 ever calls write_pending. base.py:20-25 and PRD §6.3:989-990 both assert the write has already run. It has not."
    disposition: accepted
    disposition_rationale: "Verified independently against the source before dispositioning. The claim holds in full and it is a live defect rather than a spec objection — it has been unreachable for three phases only because cli.py passes processors=[]. Two changes follow, and the second is the one the objection did not ask for. (1) The chain loop gets a per-processor guard: a raising processor abandons the chain, the last good text proceeds, the error is recorded on the session, and deliver() still runs — so the §8 write happens. (2) PRD §6.3 and postprocess/base.py are amended, because both state that the §8 write has ALREADY run when a processor raises, and in the controller the chain precedes the write. Guarding the loop without correcting the documents would leave the same false statement in place for the next reader to rely on. This is the fourth instance in this repository of the PRD stating a constraint the code cannot honour."
  - id: O2
    category: premise
    severity: critical
    claim: "B3 asserts per-application [boost] is implementable on the existing thread and timing. The focus sequencing is right and the decoder path does not exist: there is no channel by which per-dictation terms reach transcribe()."
    evidence: "faster_whisper.py:306 reads self._config.initial_prompt from EngineConfig at decode time; transcribe(audio, sample_rate, *, biased=True) at :264-266 has no terms parameter. Also dictation_controller.py:369 puts the session on the queue before :373 stashes the focus."
    disposition: accepted
    disposition_rationale: "Both halves verified. The decoder half: `TranscriptionEngine.transcribe` gains `boost: Sequence[str] = ()`, proposed as a §6.3 ABC amendment at this gate on the exact precedent of the 2026-08-05 `biased` amendment — a term list is backend-neutral domain vocabulary and each engine says locally what boosting means, where a prompt string would make the caller responsible for a backend's mechanism. The sketch proposed a §6.4 amendment for a registry file and missed the larger §6.3 one; that is the correct criticism. The race half is UNDERSTATED by the objection, which calls it 'benign today'. It is not benign: a worker that dequeues between :369 and :373 reads None, and `deliver` skips the focus check entirely on a None — so the race silently disables §6.3's protection against injecting into the wrong application, which is a shipped safety check, not a Phase 3 concern. Fixed by stashing the focus before the queue put, with a test."
  - id: O3
    category: premise
    severity: high
    claim: "The half of collapse-guard O6 that matters is not the one answered. [boost] supplying bias while initial_prompt is empty silently disables §5.7's unbiased retry, because the refusal is keyed on the wrong config value."
    evidence: "dictation_controller.py:460 — `if not self.config.engine.initial_prompt:` returns 'nothing to drop'. B3 plus O7's resolution makes initial_prompt-empty the recommended configuration."
    disposition: accepted
    disposition_rationale: "Verified at dictation_controller.py:460. This is the coupling the follow-up record's 'revisit when [boost] is specified' was pointing at, and neither the sketch nor the follow-up record found it. `_why_no_retry` is changed to ask whether ANY bias was applied to this dictation — `initial_prompt` or the boost terms resolved for the focused application — rather than whether one config key is non-empty. The retry drops all of it. Without this, the configuration the spec recommends is the configuration in which DictationState.RECOVERED is unreachable and the user gets a withheld transcript where they would previously have got their words."
  - id: O4
    category: risk
    severity: high
    claim: "Section D adds four constraints and no reject condition. The gate has no state in which it fails, and a frozen empty vocabulary.toml satisfies every constraint it does state."
    evidence: "PRD:2409-2412 pre-excuses proper-noun edit rate — the dictionary's own class. PRD:2414 makes G2's 5% movable. D's 909 ms prediction pre-excuses G1. No postprocess_ms budget exists anywhere. D2's SHA-256 freeze is satisfied by an empty file."
    disposition: accepted
    disposition_rationale: "The strongest objection in the record and the one with the most consequence for the PRD. Verified: §9's reject clause pre-excuses proper-noun edit rate on the grounds that it 'points at §5.6's vocabulary mechanisms, not at a phase failure' — a clause written when §5.6 was unbuilt, and Phase 3 is the phase that builds it. Three remedies, all of which can fail. (1) §9's reject clause is AMENDED with a dated revision note: after Phase 3, proper-noun edit rate is no longer excused, because the mechanism it deferred to now ships and the gate is that mechanism's only measurement. (2) A `postprocess_ms` p95 ceiling of 5 ms is stated. Derived rather than invented: the measured rules floor is 0.0505 ms p95 (experiments/results/04-rules-only.md), and 5 ms is 100x above it while sitting BELOW the 12.01 ms p50 that a loop of re.sub costs at 1000 entries — so the ceiling detects the specific regression the dictionary spec's 70x measurement warns about, which a generous ceiling would not. (3) A minimum instrument: the gate runs `chain = [\"rules\", \"vocabulary\"]` with a vocabulary.toml recorded by entry count as well as digest, and at least one [replace] entry must fire across the set. A gate in which the dictionary never fires has measured the rules pass and must say so."
  - id: O5
    category: scope
    severity: high
    claim: "D1 says the >= 60 s corpus is 'what changes' the guard's untested false-positive direction. That corpus structurally cannot exercise it — the named blind spot is short utterances."
    evidence: "phase-2b-followup.md:66-69 — 'short utterances are this product's ordinary case, so the exemption was a blind spot over the most common input'; the 82.8% genuine floor came from a 3.2 s sample. §9's gate mandates >= 60 s."
    disposition: accepted
    disposition_rationale: "Correct, and the sketch's claim was the exact failure shape the follow-up record named: an instrument that runs, produces output, and is credited with answering a question it cannot reach. D1 drops the claim. The gate additionally records a short-utterance set — ten dictations under five seconds — recorded for coverage and retained_seconds only, not for edit rate. The objection's own note that this is cheap is right: the constraint was never the speaking, it was the recording. The gate record states plainly that ten 60-second dictations sit where coverage is near 100% and margin is largest, and that without the short set the false-positive direction would still be untested after Phase 3."
  - id: O6
    category: risk
    severity: high
    claim: "R2 silently destroys homograph proper nouns — 'Ask Bill about the bill' becomes 'ask bill' — and its only proper-noun shield is [boost], which B3 makes empty by default and scopes per application."
    evidence: "Every conjunct in the sketch's R2 list is satisfied by 'Bill' in that sentence. B3: 'terms = [] # global. Default EMPTY, deliberately.' §7.3's hazard is silent heuristic rewriting; §5.6 exists to protect this exact class of word."
    disposition: accepted
    disposition_rationale: "Accepted, and SUPERSEDED — R2 was withdrawn before this record was read, on evidence the sketch's author found while the sentinel was running, and both routes reached the same verdict. experiments/results/04-rules-only.md §6 already implemented `capitalise_sentences` as raise-only, deliberately: 'a mid-sentence capital is indistinguishable from a proper noun without a model, and destroying proper nouns is a worse failure than leaving a stray capital.' Its 'known limit I did not paper over' section rejects exactly the rule R2 proposed, naming Josh Edwards / Talon / July / Moonshine as the corpus this would corrupt. docs/gates/phase5-disfluency.md quantifies it independently: 15 capitals flagged, ~10 real, the balance being CDE, Renee and other proper nouns — a naive flagger is wrong about a third of what it touches, in the corpus region with the worst WER. The objection's homograph analysis is a better argument than either record made and is recorded here because it generalises: the conjunct the sketch called load-bearing is the definition of a homograph. The spurious mid-sentence capital is documented as an unfixed known cost, per §7.3's own standard, rather than fixed badly."
  - id: O7
    category: risk
    severity: high
    claim: "R1, not R2, is the larger hazard. It has a measured 70% firing rate, no opt-out, no app scoping, and fires into every target surface a dictation product reaches."
    evidence: "PRD:1839 — '7 of 10 transcripts ended with no sentence-final punctuation'. §7.3:1680 — 'a tool that resolves your self-corrections and then rewrites your punctuation has moved the problem rather than solved it.' The sketch has an app-scoping mechanism (B3) and does not apply it to R1."
    disposition: accepted
    disposition_rationale: "Verified, including the §7.3 quote at PRD:1680-1681, and the asymmetry of scrutiny is real: the rule with the measured 70% firing rate got one sentence. Accepted in part, and the part rejected is named. ACCEPTED: `[postprocess] terminal_punctuation` becomes a config key, because CLAUDE.md's binding rule is that a decision which could reasonably go either way is a key, and appending a full stop into a URL bar is the clearest such decision in this phase. It defaults to TRUE, on measurement rather than preference — exp4 records it as the only rule that produced any real movement (strict WER 24.66 -> 24.32), it adds one character, it never adds a content word, and undoing it costs one keystroke against the 70% of dictations that otherwise need one added. REJECTED FOR v1: per-application scoping of R1. It is a second consumer of the [boost.apps] machinery in the phase that introduces it, and the config key discharges the objection's actual complaint. Recorded as a Phase 4 candidate WITH this objection's evidence attached, so the next reader inherits the reasoning rather than the conclusion."
  - id: O8
    category: implementation
    severity: high
    claim: "B2's pick rests on a precedent that does not say what it is quoted as saying. _focus_by_session is safe because it is keyed per session, not because the worker is serial, and `fired` is a single unkeyed slot."
    evidence: "dictation_controller.py:243-249 — 'Written on the event-tap thread and read on the worker's; the two touch different keys'. Also :522-525: an early return leaves `fired` stale from the previous session, readable as this one's."
    disposition: accepted
    disposition_rationale: "The objection is right that the sketch's precedent says the opposite of what it was quoted as saying — the safety of _focus_by_session is key disjointness across two threads that are explicitly NOT serialised, which is the property a single unkeyed slot lacks. Resolution 2 is withdrawn. Resolution 3 is also NOT adopted, for a reason the objection did not have: tests/test_contracts.py:54 asserts TextPostProcessor declares exactly {process, name}, so amending the ABC breaks a deliberate guard. A fourth resolution is adopted instead. `postprocess/base.py` gains a runtime_checkable Protocol, `TracedPostProcessor`, declaring `process_traced(text, session) -> tuple[str, tuple[str, ...]]`. The ABC is untouched and the contracts test still passes; `process` stays pure; the trace is a RETURN VALUE rather than instance state, so there is no slot to go stale on an early return and no cross-thread invariant to state; and the CONTROLLER writes it to the session, which is where session writes already live. experiments/scripts/exp4_rules_only.py:363 already prototyped `process_traced` with this exact signature shape, so this is the codebase's own precedent rather than a new idea."
  - id: O9
    category: premise
    severity: medium
    claim: "B1 calls the default-chain change 'a change to a §5.3 default'. It is a change to the configuration in which G1 is defined, and §2 is not in the sketch's Folds-into list."
    evidence: "PRD:60 — G1 is specified 'with the default post-processing chain (`[\"rules\"]`)'. Restated at :2294 and :2314; revision log 2026-07-30 records it as objection O11's disposition."
    disposition: accepted
    disposition_rationale: "Verified at PRD:60. Resolved by DECIDING the question section E left open, in the direction the objection makes unavoidable: the §5.3 default `chain` STAYS `[\"rules\"]`. G1's reference configuration is defined against it, Phase 1's and Phase 2b's figures were measured under it, and re-opening §7.5's O11 disposition to save a user one config line is a bad trade. The dictionary is opt-in like every other user-supplied artefact, and §5.3's rule is satisfied by the key existing rather than by its default. The gate runs `[\"rules\", \"vocabulary\"]` explicitly and the gate record states which basis each figure was taken on. §2 is added to Folds-into. The objection's flagged inference is also verified and true: config.py:289 accepts \"vocabulary\" while PRD:360's comment still reads `# ordered: rules | llm` — the PRD and the validator had already diverged, and the comment is corrected."
  - id: O10
    category: implementation
    severity: medium
    claim: "B3 and B4 disagree about when vocabulary.toml is read, and B4 puts an unmeasured regex compile inside the G1 window."
    evidence: "B4: 'Checked once per dictation, before the chain runs.' The chain runs at dictation_controller.py:511; transcribe() runs at :488. B1's 70x figure (0.35 ms) is match time, not alternation-compile time."
    disposition: accepted
    disposition_rationale: "Both halves correct. One read point, at the top of _process, before trim and transcribe — [boost] needs the terms before the decode and [replace] does not care, so the earlier point serves both and there is no second schedule. The compile consequence is followed further than the objection took it: a reload at the top of _process is time spent inside G1's window with no field to record it, which is the condition §6.3's standing rule exists for and which this project has now hit four times. `LatencyBreakdown` gains `vocab_ms`, inside `g1_ms`, with a column in history.db — and the compile cost is measured and reported at the gate rather than asserted to be small."
  - id: O11
    category: risk
    severity: medium
    claim: "manu history and --purge are a second process writing history.db with no IPC, and a purge concurrent with write_pending costs the transcript §8 exists to save."
    evidence: "history.py:487 uses default rollback journal and default 5 s busy timeout; a raised OperationalError propagates through write_pending and deliver into dictation_controller.py:522, which returns without persisting or injecting."
    disposition: accepted
    disposition_rationale: "Accepted on both the lock race and the internal inconsistency it found, which is the sharper half: C1 specifies a daemon-start sweep while B4 justifies mtime polling on the daemon being long-lived, and one of the two is wrong about the deployment. Three changes. (1) WAL journal mode and an explicit busy timeout on every connection — WAL lets a reader run against a writer, which is exactly the manu-history-during-dictation case. (2) `--purge` deletes in batches rather than one exclusive statement. (3) The retention sweep runs at daemon start AND when the worker finishes a session more than 24 hours after the last sweep — a clock comparison on a thread that already exists, not a new timer thread. The audio directory race the objection notes at the end has the same shape with no SQLite to arbitrate it, and is handled by unlinking with missing_ok and counting failures, which sweep_pending already does."
  - id: O12
    category: specification quality
    severity: medium
    claim: "Five decisions an implementer must invent, each of which changes output or breaks a write: intra-rules ordering, the V0 column's three other touch points, C1's 'same clock', tokenisation, and R2's [replace] conjunct."
    evidence: "B0 names _MIGRATIONS and not _COLUMNS (history.py:134) or _SCHEMA (:154); C1 says 'Same clock' but sweep_pending uses st_mtime (:388) and rows carry started_at ISO strings (session.py:189)."
    disposition: accepted
    disposition_rationale: "All five verified; items 2 and 3 are silent-failure shapes and item 3 is the sharpest thing in the objection. (1) Rule order is no longer invented: the revised spec adopts the seven-step order already documented and measured in experiments/scripts/exp4_rules_only.py:320-355, with its stated argument that deletion rules precede orthography rules. (2) All four touch points are named — _SCHEMA, _COLUMNS, _MIGRATIONS, to_history_row — because naming one of four in a repository that has recorded this exact failure three times invites the fourth. (3) The clock: `started_at` is an ISO-8601 string and `sweep_pending` compares st_mtime floats. `DELETE ... WHERE started_at < <float>` does not error — SQLite applies the TEXT column's affinity to the operand and the comparison silently matches nothing, which is a retention sweep that appears to work and never deletes a row. The cutoff is formatted as an ISO-8601 string for the row path. (4) Tokenisation is defined explicitly for [replace] matching. (5) Moot with R2 withdrawn, and the objection's underlying point is kept: a conjunct whose stated purpose does not match its position makes a list look more considered than it is."
---

# Objection record — Phase 3, post-processing and history retention

**Target:** `docs/superpowers/specs/phase-3-postprocessing.md` (DESIGN SKETCH, draft 1)
**Mode:** spec. Twelve objections — two critical, six high, four medium.
**All twelve accepted.** Two in part, with the rejected part named (O7), and one
superseded by evidence found independently while the sentinel ran (O6).

## Provenance

**A sentinel produced this, dispatched without `name:`, against the design
sketch rather than a finished spec.** Second delivering sentinel in this
repository, after the collapse guard's on 2026-08-07. The dispatch named the
five source files it should check and asked it to verify rather than accept the
sketch's claims about existing code — which is what produced O1, O2 and O3, all
three of which are defects in shipped code rather than defects in the sketch.

**Every claim was verified against the source before it was dispositioned**,
per the standing rule that roughly one sentinel claim in four is wrong. On this
record the failure rate was **zero**: all twelve held, including the two the
sentinel itself flagged as inferences.

That is a departure from the record and is worth stating rather than
assuming it repeats. Two things about the dispatch differed from the ones that
produced wrong claims: it was pointed at specific files with line-level
questions, and it was given a sketch whose own open-questions section told it
where the author was least confident.

**One objection was understated rather than wrong.** O2's second half calls the
`end_session` ordering race "benign today". It is not — a worker that dequeues
between the queue put and the focus stash reads `None`, and `deliver` skips the
focus check entirely on a `None`. The race silently disables §6.3's protection
against injecting a transcript into an application the user has since switched
away from. That is a shipped safety check, and it is disabled by timing rather
than by configuration, which is the failure mode nobody notices.

## What the sketch got wrong, in one line each

| | |
|---|---|
| O1 | Claimed the chain loop needed no change. The loop loses the transcript. |
| O2 | Claimed `[boost]` rides on existing machinery. The decoder has no channel for it. |
| O3 | Claimed collapse-guard O6 was answered. Answered the harmless half. |
| O4 | Added four gate constraints and no way for the gate to fail. |
| O5 | Credited a 60-second corpus with settling a short-utterance question. |
| O6 | Proposed a rule two existing records had already rejected with measurements. |
| O7 | Scrutinised the rule that needs a homograph, not the one that fires 70% of the time. |
| O8 | Cited a precedent that says the opposite of what it was quoted as saying. |
| O9 | Called a change to G1's reference configuration a change to a default. |
| O10 | Specified one file read at two different times. |
| O11 | Introduced a second writer to the database §8 depends on. |
| O12 | Left five decisions to the implementer, two of them silent-failure shapes. |

## What the sentinel explicitly declined to object to

Recorded because a reviewer that objects to everything has not read anything:
`postprocess/registry.py` as a §6.4 amendment; V0's `raw_transcript` column and
its scoping as a precondition rather than V2's business; literal replacement and
the rejection of B4's casing heuristic; the one-compiled-alternation constraint;
`manu vocab check` as the only verb; `store_audio = true` before the gate, which
it called the single strongest constraint in section D; the rejection of a prose
detector over user-authored `initial_prompt`; `strip_fillers` staying off and
staying present; and setting §9's stale deliverable list aside.

## Consequences beyond this spec

Four of the twelve change files this phase was not otherwise going to touch, and
three of those are defects in shipped code:

- **`dictation_controller.py`** — the unguarded chain loop (O1), the
  `end_session` ordering race (O2), and `_why_no_retry` keyed on the wrong
  config value (O3).
- **`postprocess/base.py` and PRD §6.3** — both state that §8's write has
  already run when a processor raises. It has not (O1).
- **PRD §9's Phase 3 reject clause** — pre-excuses the error class this phase
  ships the fix for (O4). Amended with a dated revision note.
- **PRD §5.3** — the `chain` comment has already diverged from the validator
  (O9).
