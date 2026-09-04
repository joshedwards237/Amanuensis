---
spec: docs/superpowers/specs/phase-3-postprocessing.md
target: "branch phase-3-postprocessing, implementation as of 2026-08-08"
task_slug: phase-3-postprocessing
date: 2026-08-08
mode: code
diaboli_model: claude-opus-5
spec_objections: docs/superpowers/objections/phase-3-postprocessing.md
authored_by: "advocatus-diaboli sentinel, code mode, dispatched without `name:`. Read-only boundary — it ran no tests and no interpreter, and every input/output pair in it is a hand trace of the source. Ten of twelve were verified at a REPL before dispositioning."
objections:
  - id: C1
    category: implementation
    severity: critical
    claim: "collapse_immediate_repeats deletes a content word on ordinary English reduplication and on repeated digits. LEGITIMATE_DOUBLES is a seven-word closed list standing against an open class, and the SHRINK safety check that would catch it is given five inputs, none of which contains a repeated content word."
    disposition: accepted
    disposition_rationale: "VERIFIED at a REPL: 'it was really really good' -> 'It was really good.', 'that is so so wrong' -> 'That is so wrong.', 'ok bye bye' -> 'Ok bye.', 'extension 4 4' -> 'Extension 4.' Four content words deleted across four ordinary inputs. The reviewer's sharper point is that the premise was wrong rather than the list too short — an adjacent exact duplicate is not a stutter, because English reduplication is productive and every repeated numeral is a duplicate. Fixed by INVERTING the guard: `COLLAPSIBLE_REPEATS` is an allowlist of closed-class function words, minus the ones that legitimately double (`had had`, `that that` — which the old blocklist named exactly, and which my first attempt at the allowlist broke until a pre-existing test caught it). The no-SHRINK property is now structural: a rule that can only delete a function word cannot delete a content word, so it no longer depends on a test remembering to probe the right input. Third defect found in this one function; the first two were fixed by adding conjuncts about punctuation and case without revisiting the premise, and this is the first fix that revisits it."
  - id: C2
    category: risk
    severity: critical
    claim: "O1's disposition guarded the chain loop but left the ordering that made the chain loop dangerous. Any exception raised between the decode and deliver() still returns from _process with nothing persisted — and session.raw_transcript is not even assigned until after _judge returns, so a raising retry discards a transcript the decoder had already produced."
    disposition: accepted
    disposition_rationale: "VERIFIED by reproduction: a fake engine that decodes once and raises on §5.7's retry produced `session.error` set, `raw_transcript` None, and ZERO calls to `write_pending`. The decoder had produced 'the words the user actually said' and the product discarded them. This is §8, the constraint CLAUDE.md lists first, and it is the most serious defect found in the phase. The reviewer is right about the general shape and right that O1's fix addressed the instance: I guarded the chain loop and wrote a commit message claiming the guarantee was restored, when the window between 'words exist' and 'words are safe' still spanned a second decode and a guard evaluation. Fixed in two places — `session.raw_transcript` is assigned immediately after the first decode, and the outer handler writes the transcript when one exists before returning. Two tests, one for a raising retry and one for a raising guard, both of which fail against the old code."
  - id: C3
    category: implementation
    severity: high
    claim: "capitalise_sentences uppercases the first alphabetic character of the transcript wherever it occurs, not the first word. Any dictation opening with a number capitalises a mid-sentence word."
    disposition: accepted
    disposition_rationale: "VERIFIED: '20 minutes left' -> '20 Minutes left.' The flag was cleared only by uppercasing a letter, so a leading digit kept the boundary open across the whole first word. The reviewer's framing is the part worth keeping: this module argues at length about a lowercasing rule it declines to write, on the grounds that a spurious mid-sentence capital is a cost worth documenting rather than fixing badly — and this rule was CREATING them, deterministically, on a common input class. Fixed by closing the boundary on the first non-space character rather than the first letter, with opening punctuation skipped so `\"hello` still yields `\"Hello` — the behaviour the buggy version got right and which is why it was written that way."
  - id: C4
    category: implementation
    severity: high
    claim: "normalise_punctuation_spacing splits acronyms and initials. It is the same defect the port already found in capitalise_sentences ('file.Py'), with the case flipped, and the test written for that defect covers only the lowercase half so it cannot fail on this one."
    disposition: accepted
    disposition_rationale: "VERIFIED, and worse than reported. 'the U.S. economy is fine' produced 'The U.S. Economy is fine.' — the rule split the acronym, and the space it inserted created a boundary `capitalise_sentences` then acted on. Two rules, one input, three corruptions. The reviewer's diagnosis is exact: the inverse of 'lowercase implies an identifier' is not 'uppercase implies a boundary', and uppercase after a dot inside a token is an acronym. Fixed in both rules, because each reached the wrong conclusion independently — the split now requires the capital to begin an ordinary word (`[A-Z][a-z]`), and `capitalise_sentences` does not open a boundary after an abbreviation dot (a single letter preceded by a dot or whitespace). The residual case is a sentence ending in a single letter, which loses a capital rather than gaining a wrong one; that is the direction this module argues for everywhere else."
  - id: C5
    category: risk
    severity: high
    claim: "purge() unlinks history.db-wal and history.db-shm unconditionally. The daemon may hold an open connection at that instant, and deleting a live WAL discards committed frames — which is precisely the §8 pre-injection write that O11's WAL disposition was introduced to protect."
    disposition: accepted
    disposition_rationale: "NOT REPRODUCED, and fixed anyway — the distinction matters and the record states it rather than implying a confirmation. `_transaction` opens and closes a connection per call, so SQLite checkpoints and removes the WAL on the last close and a single-process purge has no sidecar to delete: the unlink is dead code in the common case. The cross-process window the reviewer describes is narrow and I could not construct it. But the reviewer found a real second defect inside the same code that does NOT depend on the race: the checkpoint ran only `if rows_removed`, so a purge against an already-empty table skipped it and unlinked anyway. Both fixed — the checkpoint is unconditional, and a sidecar is unlinked only when it is zero-length after it, since a non-empty WAL after a TRUNCATE means another connection is holding frames. Cheap, strictly safer, and it makes the failure impossible rather than unlikely."
  - id: C6
    category: implementation
    severity: high
    claim: "O3's accepted disposition has no test that can fail. The test named for it passes biased=True as a literal, so reverting _why_no_retry's caller to the old initial_prompt-only check leaves the assertion green."
    disposition: accepted
    disposition_rationale: "VERIFIED BY SABOTAGE, and this is the finding I should sit with. I reverted `biased = ... or bool(boost)` to the old check and ran the full suite: 458 tests green. The test wrote a vocabulary file, built a loader, set `initial_prompt = ''` — and then called `_why_no_retry(10.0, biased=True)`, supplying the value under test as a literal, so none of the setup reached the line the disposition changed. The file's own docstring states the standard it violates: 'asserting on bias_flags rather than on the text is the difference between testing the retry and testing the fake.' Rewritten to run a full dictation and assert the engine was called twice with `bias_flags == [True, False]`. Re-ran the same sabotage: it now fails. I have written about checks that cannot fail in three gate records this session and then shipped two more, in the tests written to prevent the regressions I had just found."
  - id: C7
    category: implementation
    severity: medium
    claim: "O10's vocab_ms test cannot fail either. The session assertion is `>= 0.0` on a value that is a perf_counter delta, and the only arithmetic assertion is against a hand-constructed LatencyBreakdown that never touched the controller."
    disposition: accepted
    disposition_rationale: "VERIFIED BY THE SAME SABOTAGE: deleting the `vocab_ms` assignment in `_process` left the suite green. `>= 0.0` on a field defaulting to `0.0` is a tautology, and the arithmetic assertion tested `g1_ms`'s formula rather than whether anything populated the field. The reviewer's comparison is the useful part — `test_the_guard_is_timed` asserts `> 0.0` correctly, one screen earlier, on the field added for the same reason one phase before, so the right form was already in the file. Rewritten to `> 0.0` after a real dictation plus `g1_ms >= vocab_ms`; the sabotage now fails."
  - id: C8
    category: implementation
    severity: medium
    claim: "_maybe_sweep's stated schedule is not the one it runs. Nothing outside the method ever assigns _last_sweep_at, so the daemon-start sweep does not seed it and the first dictation of every daemon runs a second full sweep on the worker thread."
    disposition: accepted
    disposition_rationale: "VERIFIED by grep: four references to `_last_sweep_at`, all inside `dictation_controller.py`, and `cli.py` calls `history.sweep()` without touching the controller's clock. The field's own comment claimed the daemon-start sweep seeded it. Seeded in `start()` now. The cost was small — a write lock and two globs on the worker after the first dictation, with the serial worker making a second dictation wait behind it — and the reason to fix it is the reviewer's: the comment stated the opposite of the behaviour, which is how the next reader reasons about it wrongly."
  - id: C9
    category: risk
    severity: medium
    claim: "Vocabulary.apply's callback does an unguarded dict lookup on a key it reconstructs from the matched text. Any input where the match's lowercase form is not the stored key raises KeyError out of the processor."
    disposition: accepted
    disposition_rationale: "VERIFIED, and the reviewer flagged its own example as inferred while being right about it. `re.IGNORECASE` uses simple case folding and `str.lower()` uses full folding: a pattern for `i` matches `İ`, whose `.lower()` is TWO code points, and matches dotless `ı`, whose `.lower()` is itself. Both reconstruct a key that is not in the map, and both raised `KeyError` under `[]`. Changed to `.get`, returning the matched text unchanged on a miss — which is what a user reading their own file would predict. The blast radius was bounded by C2's chain guard, so the user would have got an error naming 'vocabulary' rather than losing the transcript; what made it worth fixing is that the failure it produced is dictionary objection O5's complaint (a replacement failure presenting as an ASR error) arriving through the module written to answer it."
  - id: C10
    category: risk
    severity: medium
    claim: "The ordering invariant the vocabulary module states as a contract is not enforced anywhere. chain = ['vocabulary', 'rules'] loads, validates and runs, and lets the rules pass rewrite the literal replacement the dictionary exists to guarantee."
    disposition: accepted
    disposition_rationale: "VERIFIED: with `\"csp\" = \"csv\"`, the reversed chain turned 'csp is the format' into 'Csv is the format' — the casing heuristic dictionary objection O4 rejected as §7.3's hazard re-committed, reached by configuration rather than by code. `chain = ['rules','rules']` was also accepted. `_chain` now validates order and uniqueness against `_PROCESSORS`, with a message that says why the stages are not interchangeable. The reviewer's framing is the one worth keeping: preserving the user's order is not the same as validating it, and the symptom — a dictionary entry that mostly works but capitalises oddly at sentence starts — is not one a user could trace back to their `chain` line."
  - id: C11
    category: implementation
    severity: medium
    claim: "The spoken-commands guard protects the wrong position. It excludes the phrase mid-sentence but fires on a genuine sentence that begins with those words — and because the rule counts candidates while disabled, it also inflates the firing rate the gate will use to decide whether to enable it."
    disposition: accepted
    disposition_rationale: "VERIFIED: 'Add a note. New line items are on order.' became 'Add a note.\\nItems are on order.' — three words deleted. The guard excluded the phrase mid-sentence, where it is harmless, and admitted it sentence-initial, which is where a command lives AND where 'New line items are on order' lives. Fixed by requiring a complete sentence: the trailing terminator is no longer optional, so the phrase must be followed by `.!?` or the end of the transcript. The second half of the objection is the one that mattered more and I had not seen it — the candidate counter feeds the gate's firing rate, and choice-story #2 built that counter specifically so the rate would be honest. A counter with the same false-positive population as the rule reports a rate for a rule more dangerous than the number suggests, which would have been read as evidence to enable it."
  - id: C12
    category: risk
    severity: low
    claim: "Two §7.6 leaks outside the file-mode discipline the rest of the module keeps: the one command whose purpose is to run your own dictated text through the dictionary takes that text as argv, and the data directory itself is created without a mode."
    disposition: accepted
    disposition_rationale: "PARTIALLY VERIFIED and accepted in full. The directory mode is confirmed: 0755 on the data directory while the database inside it is 0600 and `pending/` and `audio/` are 0700 — so session identifiers and the existence of stored audio were listable by other local users. Fixed with `mode=` on creation plus a chmod, since `mode=` applies only when the directory does not already exist and every existing install has one. The argv half is accepted on inspection rather than measured: `manu vocab check \"...\"` writes the user's own dictated text to shell history, and it is the one command whose stated purpose is to run a transcript through the dictionary. Left as-is for now with the cost recorded rather than papered over — a `--stdin` alternative is one branch and belongs with the README work Phase 4 owns, and the argument for doing it there rather than here is that §7.6's discipline should be stated once for every verb rather than patched onto the one a reviewer looked at."
---

# Objection record — Phase 3, post-processing and history retention (CODE)

**Target:** the implementation on branch `phase-3-postprocessing`
**Mode:** code. Twelve objections — two critical, four high, five medium, one low.
**All twelve accepted.** Ten verified empirically before dispositioning; one
(C5) not reproduced and fixed anyway; one (C12) half-measured.

## Provenance, and what the reviewer could not do

**A sentinel produced this**, dispatched without `name:` against the finished
implementation. Fourth delivering sentinel in this repository and the third in a
row.

It was offered the test suite and a Python interpreter and **had neither** — its
dispatch boundary was Read/Glob/Grep. It said so in its first line rather than
presenting hand traces as observations, marked C5 and C9 as inferred inside
their own text, and closed by naming the three things I should check before
accepting anything. That disclosure is why this record can be confident: a
reviewer that had quietly guessed would have been indistinguishable until
something shipped.

**Ten of twelve were reproduced at a REPL before being acted on.** The standing
rule in this project is that roughly one sentinel claim in four is wrong. On
this record the hand traces were exact — every predicted input produced the
predicted output, and two produced worse output than predicted (C4 compounded
into a second rule; C2 discarded a transcript the decoder had already produced).

## The finding that is about me rather than the code

**C6 and C7 are checks that could not fail, in the tests written to prevent the
regressions this phase had just found.**

I reverted the O3 fix and deleted the `vocab_ms` assignment, ran the suite, and
got 492 green. One test supplied the value under test as a literal argument; the
other asserted `>= 0.0` on a field whose default is `0.0`.

This project has counted this pattern five times in its gate records —
`sentinel-integrity-check.sh` passing on zero agents, a generated index that
could not see new records, that index reporting zero entries inside records it
could see, `verify_guard.py` running its negative control twice and printing
PASS, and Phase 3's own gate clause pre-excusing its only failure mode. I wrote
about three of those this session. Then I shipped two more.

The verification that catches it — break the line, run the suite, confirm red —
took ninety seconds, and I ran it only after a reviewer told me the tests were
hollow. **A test written immediately after fixing a bug feels verified because
the bug was just observed failing.** It is not the same event.

Both are rewritten to run a full dictation, and the same sabotage now fails
against both.

## What was checked and cleared

The reviewer's own list, kept because a reviewer that objects to everything has
read nothing: `deliver()`'s ordering; the chain guard from O1 (the objection is
about what was left outside it); the focus-stash ordering and its structural
test; `TracedPostProcessor` and its signature guard, which it called the
strongest verification artefact in the phase; `_escape_key`'s asymmetric
boundaries; `re.sub` with a callback rather than a replacement string, which is
what makes a `[replace]` value containing `\1` land literally; the longest-key
sort; the ISO-8601 cutoff and its positive control; all four `raw_transcript`
touch points; the absence of any `eval`/`exec` on transcript-derived text; the
autouse isolation fixture; and `registry.py` naming the phase for an unbuilt
processor.

## Where the accepted spec dispositions actually landed

The reviewer checked each of the twelve spec-time dispositions against the code
rather than against the spec. Nine were honoured as written. Three were not, and
each failure is a different shape:

| | |
|---|---|
| **O1** | honoured for the chain, and the same hazard survived one stage earlier (C2) |
| **O3** | honoured in the code, with a test that could not detect its reversal (C6) |
| **O10** | honoured in the code, same (C7) |

That O1 is the one that recurred is the useful part. Its disposition rationale
called the defect "the fourth instance in this repository of the specification
stating a constraint the code cannot honour" — and the fix closed one third of
the window between the words existing and the words being safe.
