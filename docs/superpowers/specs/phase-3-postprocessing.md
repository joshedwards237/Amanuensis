# Phase 3 — post-processing and the retention half of history

**Status:** revision 3, post-review. 2026-08-08. Ready to build.
**Supersedes:** draft 1, wrong in five places recorded in §0; and revision 2,
which the choice-story record changed in four places (§A5, §B5/§C2, §E1's two
ceilings, §E1's §9 amendment) after it had been called ready.
**Review:** `docs/superpowers/objections/phase-3-postprocessing.md` — 12
objections, 2 critical, all accepted.
`docs/superpowers/stories/phase-3-postprocessing.md` — 10 choice stories, nine
accepted and one deferred. **Six of the ten map decisions the objection
dispositions themselves introduced**, which is the argument for running the
cartographer rather than treating the objection record as the end of review.
**Folds into:** PRD **§2**, §5.3, §5.5, §5.6, §6.3, §6.4, §7.5, §9.
**Inherits:** `docs/superpowers/specs/dictionary.md` rev 2 (V0/V2/V3/V4),
`docs/gates/phase-2b-followup.md` (the guard, and its O6, answered in §B3).

This is the phase where `postprocess_ms` stops being structurally zero and
`g1_ms` stops being a floor.

---

## 0. What the review changed

Draft 1 was attacked and did not survive in five places. Three of them are
**defects in shipped code** that the sketch asserted were already correct, which
is the more useful outcome than a spec correction.

| Draft 1 said | Actually | Effect |
|---|---|---|
| "Nothing about the chain loop changes" | **A raising processor loses the transcript.** `_process` has no per-processor guard and returns before `deliver`, so nothing is persisted and nothing is injected — while `base.py` and PRD §6.3 both state the §8 write has already run | O1. Fixes the loop *and* both documents |
| `[boost]` rides on machinery that already exists | **The decoder has no channel for per-dictation terms.** `transcribe()` takes `biased: bool` and reads `initial_prompt` from `EngineConfig` | O2. Needs a §6.3 ABC amendment the sketch never proposed |
| Collapse-guard O6 is answered | **Answered the harmless half.** `_why_no_retry` refuses the §5.7 retry when `initial_prompt` is empty — the configuration `[boost]` recommends | O3. The retry is unreachable exactly where the new bias lives |
| The gate needs four more constraints | **The gate had no state in which it fails**, and §9's reject clause pre-excuses the error class this phase ships the fix for | O4. Amends §9 |
| R2 lowercases spurious mid-sentence capitals | **Two existing records already rejected that rule with measurements** | O6. Withdrawn |

**One further thing the review understated.** O2 calls the `end_session`
ordering race "benign today". It is not: a worker that dequeues between the
queue put and the focus stash reads `None`, and `deliver` skips the focus check
on a `None`. The race silently disables §6.3's protection against injecting into
an application the user switched away from — a shipped safety check, disabled by
timing rather than by configuration.

---

## 1. Scope

§9's Phase 3 deliverable list names `HistoryStore` (landed Phase 2a) and VAD
trimming (landed Phase 1). The Phase 2b gate said so. The real remaining work:

| | | why now |
|---|---|---|
| **A** | `RuleBasedPostProcessor` + chain dispatch | the only thing that fills `postprocess_ms` |
| **B** | dictionary V0, V2, V3, V4 | V0 is a precondition for V2 *and* Phase 5 |
| **C** | retention — `retain_days` on `history.db`, purge, `manu history` | §5.5 gap 3, open since Phase 2a |
| **D** | three shipped-code defects the review found | O1, O2, O3 |
| **E** | the gate harness | the gate must be able to fail (O4) |

**Not in scope:** `manu toggle` / `manu status` and the IPC transport (Phase 4).
Auto-learning and sync (§3 non-goals; auto-learning needs reading other
applications' text, which §7.6 keeps out of the product).

---

## A. `RuleBasedPostProcessor`

### A1 — It is ported, not invented

`experiments/results/04-rules-only.md` measured a complete rules-only pass on
2026-07-31 and `experiments/scripts/exp4_rules_only.py` implements it. Phase 3
ports that implementation and its rule order. What the experiment already
established, and what this spec therefore does not re-decide:

| | measured |
|---|---|
| Latency | **p50 0.0445 ms, p95 0.0505 ms** over six samples |
| WER movement | **+0.00** — and strict WER 24.66 → **24.32**, entirely from one restored terminal period |
| Safety | **0/6 INVENT, 0/6 SHRINK** in the shipping configuration |
| Disfluency in the corpus | **0.0%** — `strip_fillers` operates on nothing on this engine |

The seven rules, in the order the experiment fixed and argued — deletion rules
before orthography rules, because deleting a token can create a ` ,` join or
expose a new sentence-initial word:

| # | rule | on by default | note |
|---|---|---|---|
| 1 | `collapse_whitespace` | yes | leading whitespace appears on **10/10** takes (`phase5-disfluency.md`) |
| 2 | `strip_fillers` | **no** | §5.3 key. Fires 0/6; kept because a future engine may be verbatim |
| 3 | `collapse_immediate_repeats` | yes | guarded by `LEGITIMATE_DOUBLES` (`had had`, `that that`) |
| 4 | `spoken_to_written_numbers` | **NOT SHIPPED** | see A3 |
| 5 | `normalise_punctuation_spacing` | yes | blind to `file.py` and `3.5` by construction |
| 6 | `capitalise_sentences` | yes | **only ever raises case** — see A2 |
| 7 | `ensure_terminal_punctuation` | yes, **behind a new key** | see A4 |

### A2 — The rule that is not written, and why (O6)

Draft 1 proposed lowercasing spurious mid-sentence capitals. Withdrawn. Three
independent lines of evidence say the same thing:

- **`04-rules-only.md` §6 already rejected it**: "a mid-sentence capital is
  indistinguishable from a proper noun without a model, and destroying proper
  nouns is a worse failure than leaving a stray capital." Its *known limit I did
  not paper over* section names `Josh Edwards`, `Talon`, `July`, `Moonshine` as
  the corpus the rule would corrupt.
- **`phase5-disfluency.md` quantifies it**: 15 capitals flagged, **~10 real** —
  the balance being `CDE`, `Renee` and other proper nouns. A naive flagger is
  wrong about a third of what it touches, in the corpus region with the worst
  WER.
- **The review found the general case** (O6): the draft's "load-bearing"
  conjunct — the same token appears lowercase elsewhere in the transcript — is
  *the definition of a homograph*. `I met Mark, and he asked me to mark the
  invoice` satisfies every conjunct and lowercases a person's name. So do Bill,
  Rose, Grace, Robin, Will, Hope, Art, Dawn, Ray, Jack, Pat, Drew — and Word,
  Slack, Terminal, Amazon.

**Documented as an unfixed known cost**, per §7.3's own standard, rather than
fixed badly. The alternative is silent heuristic rewriting of the user's words
from inside the product, where §7.3's excuse — "nothing in Amanuensis can reach
into another application's substitution settings" — does not apply.

### A3 — `spoken_to_written_numbers` does not ship

Measured: `one thought ends and the next one starts` → `1 thought ends and the
next 1 starts`. Two INVENT violations across 2 of 6 samples, +0.97 mean WER.
`one` is a pronoun and a determiner as often as it is a numeral, and no
token-level rule can tell which. The experiment's own recommendation is to ship
it only behind a part-of-speech guard; there is no part-of-speech tagger in this
product and adding one is not this phase.

### A4 — `[postprocess] terminal_punctuation` (O7)

R1 fires on **7 of 10** transcripts, has no opt-out in the experiment, and
appends a full stop into whatever has focus — a URL bar, a shell prompt, a
filename field, a commit subject. §7.3's own sentence is the standard: *"a tool
that resolves your self-corrections and then rewrites your punctuation has moved
the problem rather than solved it."*

**A config key, defaulting to `true`.** CLAUDE.md's binding rule is that a
decision which could reasonably go either way is a key, and this is the clearest
such decision in the phase. The default is `true` on measurement rather than
preference: it is the only rule that produced any real movement (strict WER
24.66 → 24.32), it adds one character, it never adds a content word, and undoing
it costs one keystroke against the 70% of dictations that otherwise need one
added.

**Per-application scoping of R1 is rejected for v1** and recorded as a Phase 4
candidate with the review's evidence attached. It would be a second consumer of
the `[boost.apps]` machinery in the phase that introduces it, and the key
discharges the objection's actual complaint.

**Two costs of that deferral, both found by the choice-story record** (story #3):

- **There is no cheap third option.** Conditioning on the *transcript* instead of
  the target — do not append when the text looks like a path or a URL — is
  foreclosed by §A2's own argument: that is a silent heuristic rewriting the
  user's words, which is the hazard A2 refuses for R2. So the choice is between a
  global boolean and per-application configuration, with nothing in between.
- **Deferring makes it a migration.** By the time Phase 4 wants a second
  consumer, `[boost.apps]` is a shipped config format users have written files
  against, so generalising it into an `[apps]` table stops being a design and
  starts being a migration. That cost is created here and paid there.

### A5 — Spoken commands

§7.5 names spoken commands as one of the three surviving gaps. **Nothing
measures them** — no take in either corpus contains one. `new paragraph` → `\n\n`
and `new line` → `\n` ship behind `[postprocess] spoken_commands`, **default
`false`**, matching only when the phrase stands alone as a complete sentence or
is bounded by sentence punctuation. Off by default because the rule *deletes
content words* and this project's standing rule is that anything unmeasured and
lossy ships off.

**The rule counts its candidate matches even when it is disabled** (story #2).
This is not a refinement; without it the gate is rigged. `04-rules-only.md`
§7.3 asks for a fifth safety constraint — *measure the firing rate; if a
post-processor changes nothing on real input, ship the no-op and delete the
code* — and revision 2 pointed at the gate to supply it. But
`spoken_commands = false` produces a firing rate of **structurally zero** on any
gate run at default config, and zero reads as "it did no harm" to the author and
as "delete the code" to the constraint. A gate line item disarmed by the same
default that admitted the code is not a counterweight.

So the rule detects and counts always, and transforms only when enabled. The
count rides in the trace (§B2), the gate reports it, and the transformation
stays off. Zero lossiness, no tri-state config key, and the first real
measurement of a rule that currently has none.

This is also the answer to what "off by default" *means* in this project, which
had never been written down (story #2): it is **quarantine pending measurement,
and quarantine carries an obligation to measure.** Recorded in §5.3, because
`strip_fillers` and the LLM pass were both admitted the same way and neither
carried the obligation.

Literal string mapping. Never `eval`/`exec` on anything derived from a
transcript (§7.6, binding).

### A6 — Dispatch

`postprocess/registry.py` — config string → class, matching
`engines/registry.py`. A §6.4 amendment, proposed at this gate. Rejected
alternative: dispatching inline in `cli.py`, which would put a fourth dispatch
table in the one module that already imports everything.

---

## B. The dictionary

### B0 (V0) — `raw_transcript` gets a column

`to_history_row()` emits `final_text or raw_transcript` into one column, so the
engine's own words are lost the moment any processor runs (dictionary O1).

**Four touch points, all named** (O12). Naming one of four, in a repository that
has recorded this exact failure three times, invites the fourth:

| | |
|---|---|
| `_SCHEMA` (`history.py:154`) | or a new install lacks the column |
| `_COLUMNS` (`:134`) | or `_insert` silently drops the value |
| `_MIGRATIONS` (`:192`) | or an existing user's table is never widened |
| `to_history_row` (`session.py:187`) | or nothing produces the value |

`raw_transcript TEXT` — nullable, no default. A row written before this existed
has no raw text and `NULL` says so, where `''` would claim the decoder produced
nothing. §7.5's Phase 5 constraints open with "raw transcript persisted"; this
unblocks that identically, which is why it is neither V2's business nor Phase
5's.

### B1 (V2) — `[replace]`

`vocabulary.toml`, beside `config.toml` in the `platformdirs` config directory.

```toml
[replace]
"breadshoe"    = "spreadsheet"
"spread sheet" = "spreadsheet"   # phrase — the likelier error
"CSP"          = "CSV"
```

Unchanged from the reviewed dictionary spec: case-insensitive (B3),
phrase-aware, **literal replacement** — B4's casing heuristic rejected as §7.3's
hazard re-committed (dictionary O4); longest key wins with no re-fire inside the
match (B5); one replacement per key (B6); no cascading (B7); a malformed file is
an error at load naming the key, a missing file is not an error (B8).

**Tokenisation, defined rather than assumed** (O12 item 4). A key boundary is a
zero-width assertion applied only where the key's own edge character is a word
character: `(?<!\w)` before, `(?!\w)` after. A key ending in punctuation gets no
trailing assertion. Word characters are Python's `\w` under `re.UNICODE`, so
`café` and `naïve` match as single tokens; `don't`, `re-order` and `O'Brien`
split at the apostrophe and hyphen, which is why a phrase key is the documented
way to match them.

**One compiled alternation, keys sorted longest-first** — the sort is what
implements B5. Measured **70× at 1000 entries** (0.35 ms vs 12.01 ms p50) for
match time; the compile is measured separately at the gate (O10).

**Where it runs:** after `RuleBasedPostProcessor`, because the rules pass changes
capitalisation and punctuation and would otherwise rewrite the map's output.

**The §5.3 default `chain` stays `["rules"]`** (O9). G1 is defined at PRD §2
*with the default post-processing chain* (`["rules"]`), and Phase 1's and Phase
2b's figures were measured under it. Changing the default to include
`vocabulary` would re-open §7.5's O11 disposition to save a user one config
line. The gate runs `["rules", "vocabulary"]` explicitly and states the basis.

### B2 (V2) — recording which entries fired, without breaking purity (O8)

Dictionary O5: a rule firing wrongly presents as an ASR error, which is the one
explanation that sends the user to the wrong fix. The disposition was that the
session records which entries fired — and `TextPostProcessor.process` is
documented pure with respect to the session.

Draft 1 proposed a `fired` attribute read after the call, justified by the
serial worker. **Withdrawn.** `_focus_by_session`'s safety is *key disjointness
across two threads that are explicitly not serialised* — the opposite of what it
was cited for — and a single unkeyed slot goes stale across `_process`'s two
early returns, so session N+1 could read N's entries as its own.

Amending the ABC is also out: `tests/test_contracts.py:54` asserts
`TextPostProcessor` declares exactly `{process, name}`, a deliberate guard.

**Adopted:** a `runtime_checkable` Protocol beside the ABC.

```python
@runtime_checkable
class TracedPostProcessor(Protocol):
    def process_traced(
        self, text: str, session: DictationSession
    ) -> tuple[str, tuple[str, ...]]: ...
```

The ABC is untouched and the contracts test still passes. `process` stays pure.
The trace is a **return value**, so there is no slot to go stale and no
cross-thread invariant to state. The chain runner prefers `process_traced` when
a processor satisfies the Protocol, and **the controller** writes the trace to
the session — where session writes already live.
`exp4_rules_only.py:363` already prototyped this signature.

**The Protocol needs its own guard test** (story #1). `runtime_checkable` checks
**method presence only**, so a processor declaring `process_traced(self, text)`
satisfies `isinstance` and then fails at the call. The ABC has
`test_abc_declares_exactly_its_contract` and
`test_postprocessor_process_takes_the_session_it_must_not_mutate` protecting it;
the second contract would have shipped with neither. `tests/test_contracts.py`
gains a signature check.

The pattern has a name the spec should use rather than re-derive: **Extension
Interface** (POSA vol. 2), structurally identical to Go's optional-interface
upgrade idiom (`http.Flusher` beside `http.ResponseWriter`). Its cost is
accepted and stated: `chain` names processors, not capabilities, so a user
reading their config cannot tell whether `fired_entries` will be populated.
Surfacing capabilities in config would be a worse trade than a documented
asymmetry.

Persisted as `fired_entries TEXT` — the same four touch points as B0.

### B3 (V3) — `[boost]`, scoped per application

Boosting improves macro WER by **1.1 points** while making **two of six samples
worse** (+3.2, +5.2). A global always-on prompt is a trade, not a win
(dictionary O2). Operator decision 2026-08-04: scope it per application.

```toml
[boost]
terms = []                          # global. Default EMPTY — see below.

[boost.apps]
"com.microsoft.VSCode" = ["Firestore", "OAuth", "XLSX"]
"com.apple.Terminal"   = ["ripgrep", "kubectl"]
```

- A per-app list **replaces** the global list. Union makes the measured
  degradation unavoidable and the scoping pointless.
- `terms = []` by default, because the global list is the configuration the
  measurement calls a trade. The README states what it costs.
- ≤ 100 terms, truncated with a warning.

**The decoder needs a channel, and this is a §6.3 ABC amendment** (O2).
`TranscriptionEngine.transcribe` gains `boost: Sequence[str] = ()`, on the exact
precedent of the 2026-08-05 `biased` amendment: a term list is backend-neutral
domain vocabulary and each engine says locally what boosting means, where
passing a prompt string would make the caller responsible for a mechanism it is
not supposed to know about. Under faster-whisper the terms are joined and
appended to `initial_prompt`, prose first.

**O7 of the dictionary record, resolved as proposed:** `[boost]` is
authoritative; `[engine] initial_prompt` is documented as prose framing only.

**O6 of the collapse-guard record, answered — and the half that matters is not
the one draft 1 answered** (O3).

- **Rejected:** a prose detector over user-authored `initial_prompt`. It is a
  heuristic with a false-positive population, and the guard catches the failure
  directly.
- **Accepted:** a shape constraint on the segment *this feature generates*,
  which is not a heuristic because we author it. Boost terms are joined as a
  comma-separated term list with no sentence-final punctuation, so the generated
  segment structurally cannot be the "complete short utterance" shape that
  finding 4 identified as the collapse trigger.
- **The live coupling, which neither record had found.** `_why_no_retry`
  refuses §5.7's recovery retry when `[engine] initial_prompt` is empty, with
  the reason "nothing to drop". `[boost]` supplies bias while `initial_prompt`
  is empty — the configuration this spec recommends — so the guard could fire,
  the reason would be false, `DictationState.RECOVERED` would be unreachable,
  and the user would get a withheld transcript where they would previously have
  got their words back. **`_why_no_retry` asks whether any bias was applied to
  *this dictation*** — `initial_prompt` or the boost terms resolved for the
  focused application — and the retry drops all of it.

### B4 (V3) — `vocabulary.toml` is re-read on mtime change

Operator decision 2026-08-04. The daemon is long-lived; adding an entry must not
require a restart.

**One read point, at the top of `_process`, before `trim` and `transcribe`**
(O10). `[boost]` needs its terms before the decode and `[replace]` does not
care, so the earlier point serves both and there is no second schedule. Draft 1
said "before the chain runs", which is *after* the decode.

`(st_mtime_ns, st_size)`. One `stat()` per dictation.

**`LatencyBreakdown` gains `vocab_ms`, inside `g1_ms`**, with a `history.db`
column. A reload at the top of `_process` is time inside G1's window, and §6.3's
standing rule is that a stage inside that window needs a field — this project
has now hit that rule four times. The alternation compile is measured at the
gate rather than asserted to be cheap; the dictation immediately after a user
edits their vocabulary is the one that pays it, and is also the one they are
testing their new entry on.

**A reload that fails keeps the last good map** and records the error on the
session. B8's "malformed is an error at load" is the *startup* contract; at
reload the daemon is holding a transcript, and §5.3's degrade-rather-than-stall
rule applies.

**But a silent keep is C3's original complaint one layer down** (story #5). A
user who edits `vocabulary.toml` *while the daemon is running* never meets B8's
load error at all, so the validation surface they get depends on whether the
daemon happened to be running when they saved — and what they experience is "my
entry did not work", which is exactly the complaint hot-reloading was adopted to
fix. Three surfacings, all cheap:

1. The daemon prints the parse error to stderr, **once per distinct failure**
   rather than once per dictation.
2. The session records it, so it is in `history.db` beside the dictation it
   affected.
3. **`manu vocab check` re-reads the file directly and raises the real
   `ConfigError`, with the key named.** That makes the debugging verb the place
   the error is legible, which is a large part of why V4 survives at all.

### B5 (V4) — `manu vocab check`

One verb. `manu vocab check "<text>"` prints which entries fire, in order, and
the resulting text. No file writes. `add`/`list`/`boost` are rejected: §6.1
treats the verb set as the process model's public contract, and they are a
second way to do what a text editor already does.

**`manu vocab check --app` prints the frontmost application's bundle identifier
and the boost terms currently resolved for it** (story #7). `[boost.apps]` is
keyed on an identifier **the product never displays**, so without this the
feature serves a user who edits TOML *and* can name their applications the way
macOS does — obtainable only through an `osascript` incantation they have to
find first. §6.1's argument against new verbs is that they duplicate a text
editor; printing a bundle identifier duplicates nothing the user can otherwise
do, and this is a flag on a verb that already exists rather than a new verb.

Dictionary story **C6** — *"the user is assumed to be someone who edits TOML by
hand"*, still `pending` — was raised against a flat list of words. Per-application
keying raises that bar rather than lowering it, so C6 should be dispositioned
against this version and not the one it was written about.

---

## C. History retention

### C1 — `retain_days` reaches `history.db`

**The cutoff is an ISO-8601 string, not a float** (O12 item 3). `sweep_pending`
compares `st_mtime` floats; `history.db` rows carry `started_at` as ISO-8601
text. `DELETE ... WHERE started_at < <float>` does **not** error — SQLite applies
the TEXT column's affinity to the operand and the comparison silently matches
nothing. That is a retention sweep that appears to work and never deletes a row,
which is the third silent-failure shape this repository has recorded.

`retain_days = 0` keeps nothing, consistent with the pending path.

**The sweep runs at daemon start AND when the worker finishes a session more
than 24 hours after the last one** (O11). C1 and B4 disagreed about the
deployment: one specified a start-only sweep while the other justified mtime
polling on the daemon being long-lived. A daemon running for a fortnight would
never have expired a row. The periodic half is a clock comparison on a thread
that already exists, not a new timer thread.

### C2 — `manu history`

| | |
|---|---|
| `manu history` | the most recent N (default 20): timestamp, injected/not, first line |
| `manu history --last` | the most recent transcript — **and the raw text too, when it differs** |
| `manu history --last --raw` | the raw text alone |
| `manu history --pending` | the `pending/` orphans of §5.5 gap 3, by path |
| `manu history --purge` | delete everything on every path |

**`--last` shows both when they differ** (story #10). B0 makes "did the
processors change my words?" answerable for the first time, and revision 2 was
about to ship the only viewer of that data with no way to ask it: a user who
suspected a `[replace]` entry had misfired could read `fired_entries`, could
re-run `manu vocab check`, and could not see the raw text without opening SQLite
by hand. That is dictionary objection O5's complaint surviving its own fix.

**Which column is §8's artefact is left open, deliberately.** Naming `raw`
canonical would make the crash guarantee independent of the processor chain —
which is what §7.5's Phase 5 constraint assumes — and would also make
`manu history --last` show text the user never received. That trade needs Phase
5's evidence. What this phase changes is that the question is now *answerable*,
which it was not before B0.

Pending orphans are surfaced as a footer line in default `manu history` output
whenever any exist, not only behind the flag — §5.5 gap 3's complaint is that
they were a file the user was never told about.

**`--purge` confirms.** It removes `history.db` rows, `pending/*.json` and
`audio/*.wav`. `--yes` skips the prompt for scripted use. §5.5 says "`manu
history --purge` wipes it" and does not say it asks; asking is proposed here
because the artefact it wipes is the one §8 exists to preserve.

### C3 — A second process on `history.db` (O11)

`manu history` opens the database the daemon is holding, and IPC is Phase 4. A
`--purge` taking an exclusive lock while the daemon calls `write_pending` raises
`OperationalError`, which propagates into `_process`'s outer handler — nothing
persisted, nothing injected. The user ran a *history* command and lost a
transcript.

1. **WAL journal mode and an explicit busy timeout** on every connection. WAL
   lets a reader run against a writer, which is the `manu history`-during-
   dictation case exactly.
2. **`--purge` deletes in batches** rather than one exclusive statement.
3. The `audio/` race has the same shape with no SQLite to arbitrate it, and is
   handled by `unlink(missing_ok=True)` and counted failures, as `sweep_pending`
   already does.
4. **WAL adds `history.db-wal` and `history.db-shm` beside the database, and
   `--purge`'s inventory has to grow to cover them** (story #9) — in the code
   and in the README's list of what purge removes. §5.5 already declines to
   claim secure erasure and explicitly moved the non-retaining path out of
   SQLite to avoid reasoning about "`secure_delete`, `VACUUM` and WAL checkpoint
   behaviour", so what is owed here is the inventory, not a new privacy claim.

**The cost of shipping this before IPC, recorded rather than designed away**
(story #9): after this phase, history works without the transport, so §7.3's
floor item 3 arrives in Phase 4 with `toggle`/`status` as its only real consumer
and history with no incentive to migrate. The temporary shape becomes the shape.
Accepted because §5.5 gap 3 has been open since Phase 2a and the orphans are
plaintext transcripts the user was never told about.

---

## D. Three defects in shipped code

Found by the review, none of them Phase 3 features, all of them reachable the
moment Phase 3 ships.

**D1 — the chain loop loses the transcript** (O1, critical).
`_process` has no per-processor guard; the outer handler returns before
`deliver`, which is the only caller of `write_pending` on that path. A raising
processor therefore persists nothing, injects nothing, and leaves the words in a
local variable. `postprocess/base.py:20-25` and PRD §6.3:989-990 both state the
opposite — that §8's write has already run. It has not: the chain precedes the
write.

Fixed by guarding each processor — abandon the chain, keep the last good text,
record the error, and let `deliver` run. **Both documents are amended too**,
because guarding the loop while leaving a false statement in place is how the
next reader inherits it.

**D2 — the `end_session` ordering race** (O2). The session is queued *before*
the focus is stashed. A worker that dequeues in between reads `None`, and
`deliver` skips the focus check on a `None` — silently disabling §6.3's
protection against injecting into an application the user switched away from.
Fixed by stashing before the put.

**D3 — `_why_no_retry` keyed on the wrong value** (O3). See §B3.

---

## E. The gate

§9's Phase 3 gate: ten real dictations of ≥ 60 seconds, report edit rate and
what kind. Phase 2b additionally deferred **the real G1 number — every stage
populated, nothing labelled a floor** — to this gate.

### E1 — The gate must be able to fail (O4)

Draft 1 added four constraints and no reject condition. Enumerating the
outcomes: high edit rate from punctuation was the only live reject; high edit
rate from proper nouns was pre-excused by §9; a G1 miss was pre-excused by the
909 ms prediction; `postprocess_ms` had no ceiling anywhere. The PRD has
recorded this species once already, about Phase 5: *"the gate also cannot fail
the budget by construction."*

Three remedies, each of which can fail:

1. **§9's reject clause is amended — and narrowed** (story #8). It excuses
   proper-noun edit rate on the grounds that it "points at §5.6's vocabulary
   mechanisms, not at a phase failure", written when §5.6 was unbuilt. **Phase 3
   builds it.** But un-excusing the class *wholesale* would make the gate fail on
   **the corpus's scope** rather than on **the dictionary's misses** — a
   proper-noun failure would have two possible causes, a weak mechanism or a thin
   vocabulary, and entry count is not coverage.

   So the amended clause counts proper-noun errors **for terms present in the
   frozen `vocabulary.toml`**. Proper nouns the vocabulary does not cover stay
   excused, because for those §9's original reasoning is still correct.

   This also matters two phases out. `04-rules-only.md` §5 measured **87.2% of
   corpus errors as ASR mistranscription** that no downstream pass can recover.
   A wholesale un-excusing would hand Phase 5 a reject clause counting a class it
   *structurally cannot address*, and §7.5 has already recorded one Phase 5
   criterion that could not do its job.

2. **`postprocess_ms` p95 ≤ 5 ms.** Derived, not invented: the measured rules
   floor is 0.0505 ms p95, and 5 ms is 100× above it while sitting *below* the
   12.01 ms p50 that a loop of `re.sub` costs at 1000 entries — so the ceiling
   detects the specific regression the 70× measurement warns about, which a
   generous ceiling would not.

3. **`vocab_ms` p95 ≤ 10 ms** (story #6). Revision 2 gave the reload a field, a
   column and a gate measurement, and **no bar** — so the phase's one stage whose
   cost scales with an artefact *the user authors* was the one stage with no
   budget. The dictionary spec measured 18.4 ms at 5000 entries for match time
   alone; a large enough `vocabulary.toml` would move a published guarantee with
   no code change. The compile is paid only on the dictation after an edit, and
   10 ms is where the user testing their new entry would start to feel it.

   Rejected alternative: excluding `vocab_ms` from `g1_ms` as "the user's cost".
   §2's two exclusions — `capture_ms` and `restore_ms` — are both justified by
   falling *outside* the hotkey-release-to-text window, never by whose fault the
   cost is, and admitting that second justification would let any future stage
   escape the same way.

4. **A minimum instrument.** The gate runs `chain = ["rules", "vocabulary"]`
   with `vocabulary.toml` recorded by **entry count** as well as digest, and at
   least one `[replace]` entry must fire across the set. A gate in which the
   dictionary never fires has measured the rules pass, and must say so.

### E2 — What every dictation records

`coverage` and `retained_seconds`, **fired or not** (`phase-2b-followup.md` O8),
plus `postprocess_ms`, `vocab_ms`, `g1_ms`, `fired_entries`, the firing rate of
every rule — **including `spoken_commands`, which counts while disabled**
(§A5) — and **both transcripts where they differ** (story #10), since this is
where raw and final would first be compared and revision 2's list omitted the
pair the column was added to make comparable.

**One trade, stated in one place.** The dictionary's *cost* lands in G1
(`vocab_ms`, `postprocess_ms`) and its *benefit* lands in G2 (edit rate), and
those are reported against different criteria at the same gate — so the trade the
whole feature rests on would otherwise never appear anywhere as a trade. The gate
record states it as one: what the dictionary bought in edit rate, and what it
cost in milliseconds, on the same page.

**The ≥ 60 s corpus cannot settle the guard's false-positive direction** (O5).
That blind spot is at the short end: the 82.8% genuine floor came from a
**3.2-second** sample, and `retry_below_coverage = 0.7` is calibrated against
one short clip. Ten 60-second dictations sit where coverage is near 100% and
margin is largest. So the gate records **a second set of ten dictations under
five seconds**, for coverage and `retained_seconds` only — not for edit rate.
Without it, the false-positive direction is still untested after Phase 3, and
the gate record says which.

### E3 — Freezing the instrument (dictionary O6)

`vocabulary.toml` is frozen before the first gate dictation. The record states
when it was last edited, its SHA-256, **and its entry count**. Edit rate is what
the dictionary moves by construction; entries written against the test set
measure nothing.

`store_audio = true` before the gate dictations, so a collapse in the wild is
reproducible. The last one was not.

### E4 — A prediction recorded before the measurement

§2's model is `transcribe_ms ≈ 48.8 + 13.69 × seconds`, so a 60-second dictation
lands near **909 ms** — over G1's 800 ms p95. §2 binds G1 at ten seconds and
already records this. It is utterance length, not post-processing. Recorded in
advance so it cannot be read as a regression this phase caused — and **not**
usable as a reject exemption, per E1.

### E5 — The harness needs a positive control that can fail

Fourth instance in this repository of a check that could not fail. The
edit-rate script exits **non-zero** when its control input produces no edits,
and separately when the recorded `vocabulary.toml` has zero entries — E1's
minimum instrument, enforced by the script rather than by the person writing
the record.

Every latency figure carries p50 **and** p95, nearest-rank via
`amanuensis.tier.percentile`, never interpolated.

---

## F. What this spec does not settle

- **The short-utterance set is ten recordings by one speaker.** It removes the
  structural blind spot; it does not produce a speaker the guard is wrong about.
- **`spoken_commands` ships off with no measurement behind it.** The gate
  produces its first firing rate, and `04-rules-only.md` §7.3's fifth constraint
  applies: if it changes nothing on real input, delete the code.
- **Per-application scoping of `terminal_punctuation`** is deferred to Phase 4
  with O7's evidence attached.
- **`[boost]`'s trade is still one speaker, six samples.** The gate is the first
  data from a second context, not a second speaker.
