---
spec: docs/superpowers/specs/phase-3-postprocessing.md
target: "three Phase 3 gate recommendations — disable initial_prompt, add a guard continuity term, store float32 audio — plus re-recording the ten-dictation corpus"
task_slug: phase-3-gate-recommendations
date: 2026-08-18
mode: code
diaboli_model: claude-opus-5
spec_objections: docs/superpowers/objections/phase-3-postprocessing.md
authored_by: "advocatus-diaboli sentinel, code mode, dispatched without `name:`. Read-only boundary — it ran no interpreter. Every file:line in it is a hand trace of the source, and the two critical objections were confirmed by measurement afterwards. Written to this path rather than the derived `phase-3-postprocessing-code.md`, which already holds the C1-C12 implementation review and would have been destroyed."
objections:
  - id: O1
    category: premise
    severity: critical
    claim: "FINDING B's own numbers contradict FINDING A's production claim: take 12e727b3's live stored transcript is 260 words, which matches the offline prompt-OFF arm (262), not the prompt-ON arm (159). The 103-word loss is a property of the offline re-decode, not of the shipped decode."
    disposition: accepted
    disposition_rationale: "CONFIRMED by measurement. Live word counts against both arms across all ten: 12e727b3 live 260 vs ON 159 / OFF 262 — the live decode matches the unbiased arm, and the largest number in the case never happened in production. The generalisation 'four of ten, 164 words' is withdrawn. What survives is smaller and differently distributed: live output is short of the prompt-off arm on 8 of 10 takes, 109 words total, and a605e8a3 alone accounts for 52. The 2x2 run later put a605e8a3's lossy cell at exactly 197 words, which is its live stored value — so that take did lose content in production, and O1's correction applies to the incidence and not to the existence. Also correct on the sub-point: 'deterministic across five runs' with BEAM_SIZE=1 measures the product's determinism, not the effect's stability."
  - id: O2
    category: risk
    severity: critical
    claim: "The gate's store_audio check cannot fail for the corpus it protects — it asserts that at least one .wav exists anywhere in audio_dir, so stale audio from the abandoned corpus satisfies it while the new ten have none."
    disposition: accepted
    disposition_rationale: "Correct as written, at scripts/gate_phase3.py:401. Now joins each gate row to `audio_dir / f'{id}.wav'` and names the missing ids. Verified by sabotage: clean before, `REJECT [reproducibility] 1 of 10 gate dictations have no stored audio (a605e8a3a7e1)` with one file hidden, clean after restoring. The reviewer's framing is the part worth keeping — `_sweep_audio` expires audio on retain_days while rows persist, so rows-without-audio is the daemon's normal steady state rather than an edge case. Ninth instance of a check that could not fail in this repository, and the second in this file on the same day: the pass that fixed the dictionary instrument check read the block above it and not the block below."
  - id: O3
    category: implementation
    severity: high
    claim: "REC 1 does not close the channel it blames: [boost] terms are concatenated into the same initial_prompt= argument, so with initial_prompt = \"\" and a non-empty [boost] the decoder still receives a prompt."
    disposition: accepted
    disposition_rationale: "Correct, at engines/faster_whisper.py:355. The channel is empty in practice — vocabulary.toml sets `terms = []` and there is no [boost.apps] — but the shipped hazard stands, and config.py:130 shows `\"\"` is already the shipped default, so the config edit only ever fixed this machine. Recorded in config.toml as consequence 1 rather than left to be rediscovered. The O4 result supersedes the remedy: condition_on_previous_text=False closes the channel for any user's long prompt, which is what this objection asked for and what the config edit could not deliver."
  - id: O4
    category: implementation
    severity: high
    claim: "The causal claim is not isolated: five decode-shaping faster-whisper parameters are left at library defaults, and condition_on_previous_text is a better-fitting explanation for a hole of exactly one 30-second window."
    disposition: accepted
    disposition_rationale: "The sharpest objection in the record, and the answer is neither hypothesis alone — it is the conjunction. 2x2 over three takes, prompt SET/none against condition_on_previous_text True/False: loss occurs in exactly one cell of four, every time. 12e727b3 198/255/262/262, a605e8a3 197/249/249/251, eeced9b1 221/242/242/241. The prompt is the source; condition_on_previous_text is what propagates it into subsequent windows. So the reviewer is right that the parameter is a mediator and wrong that it displaces the prompt. Consequence: there are two independent fixes and the one shipped is the weaker. Pinning condition_on_previous_text=False is a decode-behaviour change affecting every transcript and is NOT made here — it needs measurement first, and it is the strongest candidate for the first Phase 4 change."
  - id: O5
    category: risk
    severity: high
    claim: "REC 1 makes §5.7's recovery path unreachable: with no prompt and no boost terms, biased is False, the retry is refused by construction, and DictationState.RECOVERED becomes dead code."
    disposition: accepted
    disposition_rationale: "Correct, at controllers/dictation_controller.py:498 and :534-538. Not a defect — it is a designed consequence, correctly reasoned (a greedy re-decode of identical input is identical output) — but it is user-visible and was being triggered globally by a config edit with no note. Recorded in config.toml as consequence 2: §5.7 is now detect-and-refuse, and a fired verdict means the words reach history.db and nothing reaches the cursor. Accepted as the right trade; refusing beats injecting a destroyed transcript."
  - id: O6
    category: risk
    severity: high
    claim: "REC 1 collides with the gate's instrument check: half the dictionary exists to clean up prompt artefacts, the gate rejects unless a [replace] entry fires, and the freeze rule bars the only remedy."
    disposition: accepted-and-closed
    disposition_rationale: "The reasoning is right and the outcome is benign, which is only knowable by measuring — so the objection earned its place. Re-decoding the ten with the prompt off and running the frozen chain: `replace:text stack` fires twice, so the instrument clause passes. With the prompt on it was four firings — `text stack` x2, `cloud session`, `cde into` — and the two lost are exactly the prompt-induced ones. The shrinkage the recommendation predicted is real and measured; the incompatibility it might have caused is not. The deeper point stands for the gate record: the dictionary's measured benefit was inflated by a setting that was manufacturing its own work."
  - id: O7
    category: implementation
    severity: high
    claim: "REC 3 breaks every WAV reader in this repository, including the collapse guard's own verification harness: Python's wave module cannot read WAVE_FORMAT_IEEE_FLOAT, and all three readers use it with a hardcoded int16 dtype."
    disposition: accepted
    disposition_rationale: "Correct, and decisive against REC 3. tests/conftest.py:41-45, scripts/verify_guard.py:55-59, scripts/measure_long_audio.py:63-67 all combine `wave.open` with `np.frombuffer(..., dtype=np.int16)`. The recommendation cited wave's inability to WRITE format 3 and did not notice it is the same module on the read side. Breaking verify_guard.py is the unacceptable part — it is §5.7's verification harness, and the PRD already records that its first version was worthless and printed PASS. REC 3 withdrawn."
  - id: O8
    category: implementation
    severity: high
    claim: "REC 3 cannot deliver §E3's reproducibility because the stored WAV is the untrimmed capture, not the array the decoder saw — reproduction must re-run VAD, and a 0.05 s trim shift moved a decode by 40 words."
    disposition: accepted
    disposition_rationale: "Correct, at storage/history.py:749 against dictation_controller.py:571-577. The reviewer's quantitative point is the one that mattered: the 32767/32768 mismatch is a 3.05e-5 relative gain error, not a credible cause of a 100-word difference, and the real variable is VAD picking different boundaries on requantised input. Its alternative was taken — the three readers now divide by 32767 to match every writer. Its second alternative, storing the trim boundaries, is the actual fix for §E3 and is NOT done here; it is a schema change and belongs to Phase 4. NOTE, found after this record was written: changing the read constant by half a least-significant bit moved 12e727b3's prompt-on decode from 159 words to 198. The knife-edge sensitivity is larger than either of us credited, and it means every offline figure quoted at this gate is fragile at that precision. §E3's reproducibility claim needs weakening rather than defending."
  - id: O9
    category: alternatives
    severity: high
    claim: "A single metric — voiced-sum over the padding-corrected speech denominator — subsumes both coverage and continuity, reuses the existing thresholds as a strict tightening, and requires re-validating one number rather than calibrating a second."
    disposition: accepted-not-implemented
    disposition_rationale: "The design argument is better than the one it replaces and the reasoning at guard.py:170-175 supports it: substituting sum(end-start) for max(end) yields a value <= current coverage for every decode, so min_decoded_coverage and retry_below_coverage stay valid as bounds. Not implemented, because the 2x2 in O4 showed the failure mode is not always a gap — in the corrected-constant runs the lossy cell has NO inter-segment gap over 2 s and loses words by truncation INSIDE segments, while segment count collapses from 14 to 3. A voiced-sum metric would have missed all three of those. The guard gap is recorded in the PRD as open rather than closed with a metric that fails the same way. Segment count is the signal that discriminates in every run so far, and it is engine-specific in a way coverage deliberately is not — which is the unresolved part."
  - id: O10
    category: implementation
    severity: high
    claim: "REC 2's formula is wrong in two specific ways: span = max(end) - min(start) is blind to a dropped opening — the same failure class — and voiced / span reintroduces the padding confound that the Phase 2b follow-up's headline correction removed."
    disposition: accepted
    disposition_rationale: "Both halves correct, and together they withdrew the recommendation. The head-drop case is exact: if the decoder drops the opening, min(start) moves to the drop's end, span equals voiced, continuity reads 1.000 — and coverage reads 1.000 too, so both instruments are clean on a transcript missing its beginning. The padding point is the 2026-08-07 correction being re-imported: padding is 2 x speech_pad_ms x segment count inserted INSIDE the concatenated audio (vad.py:191-192, 212-216), and guard.py:161-168 records that dividing without correcting read 62.2% where the corrected value was 82.8%, biased toward refusing genuine transcripts. A metric whose bias scales with segment count is speaker-dependent, which is the exact objection guard.py:14-18 records against the words-per-second draft. Proposing it was that rejected design with a different numerator."
  - id: O11
    category: risk
    severity: high
    claim: "Nothing in history.db or the gate report records which decode configuration produced a row, and the failing prompt string is not written down anywhere — so a re-recorded corpus is untraceable to the config change that motivated it, repeating the verify_guard.py failure exactly."
    disposition: accepted
    disposition_rationale: "Correct: dictation_controller.py:579 records only backend:model, and gate_phase3.py's report carried no engine settings while freezing the dictionary by SHA-256 and mtime. The gate report now carries backend, model, language, and the initial_prompt's SHA-256 and character count. Hashed rather than verbatim: it is user-authored text that can name people and clients, the gate record is committed, and length is the variable this phase measured as load-bearing. `initial_prompt 0 chars` is the disabling, self-evidencing in the record. Per-row recording in history.db is NOT done — that is a schema change, and the gate-report digest is what protects the re-record. The reviewer's parallel to §9's documented failure is exact and is why this was fixed before recording rather than after."
  - id: O12
    category: specification quality
    severity: medium
    claim: "'Record only' as stated has no sample-size target, no false-positive population, no threshold-setting procedure, no named history.db column and no gate at which the decision is forced — the shape under which store_audio and restore_ms each sat inert for a phase."
    disposition: accepted
    disposition_rationale: "Correct, and it applies to a recommendation that has since been withdrawn on O9 and O10, so the remedy is not a column but an honest open item. The PRD revision row for 2026-08-18 records §5.7's blindness as unresolved and names why the drafted metric was withdrawn, rather than shipping a column with no decision procedure attached. The reviewer's sharpest observation survives the withdrawal and belongs in the Phase 4 brief: the Phase 3 corpus probably CANNOT license a threshold — the ten long dictations are one speaker, and the ten short ones are single-window and structurally cannot exhibit a window skip at all. A phase that recorded continuity might have produced zero positive instances and deferred again with no new evidence."
---

## Provenance

Dispatched at the Phase 3 gate, 2026-08-18, against three recommendations that had
not yet been implemented. This is the second sentinel in this repository to be
dispatched *before* the change rather than after it, and the first whose objections
changed the change: six of twelve (O1, O3, O4, O5, O6, O9/O10) altered what shipped,
and one recommendation was withdrawn entirely.

**What the sentinel got right that the author did not.** O1 read the author's own two
findings against each other and noticed they contradicted — FINDING A's headline
number was refuted by a line inside FINDING B, in the same brief, and the author had
written both. O4 named a library default the author had not considered and turned out
to be half of a conjunction neither party had proposed. O2 found a check of a shape
the author had spent that morning fixing elsewhere in the same file.

**Where the sentinel was wrong.** O1's generalisation ("no live instance behind it at
all") does not survive: a605e8a3's lossy cell reproduces its live word count exactly,
so one take did lose content in production. O4's framing treated the prompt and
`condition_on_previous_text` as competing explanations; they are conjunctive.

**Standing consequence.** The strongest available fix — pinning
`condition_on_previous_text=False`, which closes the failure for any user's long
prompt rather than for this machine's config — is deliberately NOT taken here. It
changes decode behaviour for every transcript and needs measuring at a gate, not
adopting in the middle of one.
