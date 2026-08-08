# Amanuensis — Product Requirements Document

**Version:** 0.1 (pre-implementation)
**Owner:** Josh Edwards
**Status:** Specification complete, measured. Phase 0 not started — see `HANDOFF.md`
**License target:** Apache-2.0 (patent grant; safer than MIT for a project bundling third-party model weights)

---

## How to use this document

This PRD is the standing specification. It is **not** an operating contract — it does not
define agent loop behavior, approval mechanics, or forbidden actions. Those belong in
`HARNESS.md`. This document answers *what* and *why*; `HARNESS.md` answers *how you are
allowed to work*.

**Execution is phase-gated.** Each phase in §9 ends at an approval gate. Do not begin
phase N+1 until phase N is explicitly approved. At each gate, stop and report:
what was built, what was verified, what was deferred, and what the phase revealed that
this PRD got wrong.

**Amend this document.** If implementation contradicts a decision recorded here, do not
silently diverge. Open the disagreement at the gate with evidence, and if accepted, update
§7 with a dated revision note.

---

## 1. Summary

Amanuensis is a fully local, open-source dictation tool. Press a hotkey, speak, release,
and your words appear as text at the cursor in whatever application currently has focus.
No account, no network, no audio leaving the machine.

The product it is measured against is Wispr Flow. The differentiator is not features —
it is that the audio never leaves the device and the user owns the stack.

**Why build rather than adopt** (resolved 2026-07-30, objection O2). §7's discipline
is that every decision records the alternative it rejected; the decision to build at
all deserves the same treatment, and §13 lists two shipping local tools whose
existence would otherwise go unaddressed:

- **nerd-dictation** does the injection layer well — §13 says so — and is Linux-only.
  The platform this product targets first (§7.3) is the one it does not serve.
- **Talon Voice** has the mature hotkey and injection layer this product needs, but
  it is a voice-*control* system: a command grammar for driving the OS, which §3
  explicitly lists as a non-goal. Its interaction model and licensing posture are
  both different from a press-hold-speak dictation tool the user owns outright.

The gap is therefore narrow but real: general-purpose push-to-talk dictation, model
resident in memory, macOS-first, open source, no account. If Phase 1's required
reading (§13) shows either tool closes that gap after all, that is a finding for the
Phase 1 gate and this paragraph is where the correction lands.

---

## 2. Goals

| # | Goal | Measurement |
|---|---|---|
| G1 | Text appears fast enough to feel like typing | p50 ≤ 400 ms, p95 ≤ 800 ms from hotkey release to **text fully present** in the focused application, for a 10-second utterance, **on a Tier A machine** (§7.2 — measured, not named after silicon), with the **default post-processing chain** (`["rules"]`). Measured as `LatencyBreakdown.g1_ms` (§6.3) — `capture_ms` is excluded. See the G1 measurement note below. |
| G2 | Transcription is accurate enough to not require editing | **Edit rate ≤ 5%** — the fraction of words requiring manual correction across the Phase 3 dictation set. WER is *not* the product goal; see the accuracy-measurement note below. |
| G3 | Zero network traffic at runtime | Verified by packet capture with the app under load. **Scope:** this verifies Amanuensis's own sockets only. Transcript egress through a third-party clipboard manager happens in another process and is invisible to this method — see §7.3. |
| G4 | Works in any focused application | Native fields, Electron apps, terminals, browsers |
| G5 | A developer can read the codebase in an afternoon | Enforced by the structure in §6 |

### G1 measurement note

Three points that were previously ambiguous, resolved 2026-07-30 (objection O8):

1. **The window excludes capture.** G1 starts at hotkey release, so the time
   spent recording is not in it. `LatencyBreakdown.total_ms` includes
   `capture_ms` and is therefore a diagnostic figure, **not** the gated number.
   The gated number is `g1_ms`.
2. **The utterance length is 10 seconds, and §7.1's 15–30 s is a different
   thing.** G1 binds at 10 s; §7.1's "realistic 15–30 second utterances" is a
   *revisit trigger* for the batch-vs-streaming decision, not a second budget.
   A build that passes at 10 s and degrades at 30 s is a G1 pass **and** a §7.1
   trigger. Neither overrides the other; they are separate signals.
3. **"Fully present" rather than "first character."** The earlier wording could
   not be applied to the default clipboard strategy, where paste is atomic and
   there is no first character distinct from the last — and under
   `strategy = "keystroke"` it would have reported a fast number for a slow
   experience, measuring to the first character of a paragraph §7.3 rejects
   keystroke for being too slow to deliver. "Fully present" is what the §4 user
   experiences and is comparable across both strategies.

   **"Fully present" also sets the *end* of the window, not only its unit**
   (clarified 2026-08-02, Phase 2a finding 1). Work that happens after the text
   is present is outside G1 even though the process is still busy. The clipboard
   restore is the first instance: it costs ~155 ms, it runs while the user is
   already reading their words, and counting it reported a 272 ms delivery as a
   422 ms miss on the first real dictation. It is recorded as `restore_ms`,
   inside `total_ms` and outside `g1_ms` (§6.3).

   **The gated figure is the best case of a linear relationship** (added
   2026-08-03, Phase 2b finding 3). Measured over fourteen real dictations
   spanning 0.7 s to 43.4 s:

   ```
   transcribe_ms ~= 48.8 + 13.69 * seconds_of_audio
     10 s  ->  186 ms  ->  g1 ~= 225 ms      <- what G1 gates
     30 s  ->  460 ms  ->  g1 ~= 499 ms
     60 s  ->  870 ms  ->  g1 ~= 909 ms      <- over G1's 800 ms p95
   ```

   Point 2 above already says G1 binds at 10 s and that longer utterances are a
   §7.1 revisit trigger rather than a second budget. That stands. What has to be
   said alongside it is the consequence: **a user dictating a paragraph is the
   ordinary case, not an edge case, and G1 says nothing about what they wait.**
   Publishing 225 ms while a 60-second dictation costs 909 ms is not false, but
   a reader who has not read this paragraph will draw the wrong conclusion from
   it, so the README carries the scaling alongside the figure.

   This binds on **Phase 3 immediately**, and is recorded here rather than left
   to be found there: that phase's gate is ten real dictations of >= 60 seconds,
   which is exactly where the model predicts ~909 ms. Without this note the
   result reads as a regression introduced by post-processing. It is the
   utterance length, and it was already true at the Phase 2b gate.

Two further scoping decisions, resolved the same day:

4. **G1 is tier-conditional, and tiers are measured** (objection O1, revised
   2026-07-31 from probe evidence). It binds on **Tier A** — machines where the
   selected model transcribes a 10-second utterance inside the budget, decided
   once at install (§7.2). On **Tier B** machines it is *not* a pass/fail
   criterion: that tier ships with a **measured, published latency expectation**
   instead, per §10. §9's "if G1 is missed here, stop" therefore means *stop for
   Tier A*. It does not halt the project over a Tier B miss.

   **What changed and why.** O1 originally split on *accelerated versus
   CPU-only*, naming CUDA and Apple Silicon as the gated tiers. The probe showed
   that boundary does not exist: CTranslate2 has no Metal backend, so Apple
   Silicon is a CPU path, and macOS — the only v1 platform — has no CUDA. The
   old split would have left **no gated tier at all in v1**, which is the
   opposite of what O1 was accepted to achieve. O1's reasoning is unchanged; only
   the axis moved, from what chip a machine has to what it measured.

   Why: §1's differentiator is locality, and the §4 user who is
   offline-constrained or privacy-motivated frequently has no fast alternative
   at all. Shipping them a slower tool with an honest number serves them;
   shipping them nothing does not. Previously §2 and §9 demanded parity
   unconditionally while §10 quietly permitted the slow tier to ship anyway —
   which meant the gate could not fail, because any miss was redescribable as
   "a documented latency expectation." The escape hatch is now a stated scope
   boundary rather than an unstated one.

   **Tier B still needs a published number, and a bar to clear.**
   "Not gated by G1" is not "unmeasured" — the Phase 1 gate reports the Tier B
   figure alongside the Tier A one, and the README states both.
   §10's escape clause is that a tier "unusable rather than merely slow" should
   be dropped in §3, and *unusable* was undefined in exactly the way objection
   O9 rejected for gates. So:

   > **G1-CPU (provisional): p50 ≤ 2 000 ms, p95 ≤ 4 000 ms**, same measurement
   > basis as G1. A Tier B machine class that misses either is dropped in §3
   > rather than shipped.

   **This is a judgement, not a derivation** (relabelled 2026-07-31, objection
   A5). The paragraph here previously opened "the derivation, since the number
   should not be a guess" and then reasoned: a 10-second utterance is roughly
   25 words, at 40 wpm that is ~37 seconds to type, and two seconds is
   comfortably inside that. The arithmetic is correct and it does not produce
   2 000 ms. The user has already spent the ten seconds speaking, so a strict
   throughput reading compares 10 s + latency against ~37 s and licenses
   anything under about 27 seconds — which nobody would ship. The clause
   actually carrying the decision was "while still reading as a tool rather than
   a batch job," and that is a judgement about felt responsiveness.

   So it is stated as one. The typing comparison establishes that two seconds is
   **not slow**; it does not establish two seconds. Like G2's 5%, this is
   **provisional** — Phase 1 confirms or moves it with a stated reason in
   `docs/gates/phase-1.md`. It is a floor for shipping the tier at all, not a
   claim that 2 000 ms feels good.

   §2's own G2 note two paragraphs above says a number presented as derived when
   it was inherited is worse than one labelled a guess. This was the newer of the
   two and was making that exact mistake.

   **The p95 is added because a p50-only bar cannot fail on this project's
   documented failure mode.** Tier B runs a smaller model on slower hardware,
   which is where a decoder repetition-looping excursion is most likely and most
   costly — the same class of event that took a 541 ms case to 6,039 ms on
   identical input. A threshold that decides whether a whole machine class ships,
   stated only at the median, is the shape of the finding that a p50 from one
   clean sample said GO while the p95 said the opposite. 4 000 ms is 2× the p50
   bar, matching G1's own p50:p95 ratio; it is provisional on the same terms.

5. **G1 assumes post-processing is off** (objection O11). The budgets above are
   measured with `chain = ["rules"]`, the default. The optional LLM pass adds
   200–500 ms against a 300 ms ceiling (§5.3, §7.5), so a base pipeline landing
   exactly at the 400 ms p50 target reaches ~700 ms with the pass enabled —
   G1 as written was unsatisfiable whenever the feature it gates was turned on.
   Phase 5 carries its **own** stated budget; see §7.5.

### G2 accuracy-measurement note

Resolved 2026-07-30 (objection O7). G2 previously read "≤ 5% WER on clean
desk-mic English" — a numeric threshold against a corpus that did not exist and
was not described well enough to construct, while no phase in §9 measured WER at
all. Two instruments now do two different jobs:

- **Edit rate is the product goal.** It measures what the §4 user experiences —
  how much correcting they had to do — and it is what the Phase 3 gate already
  collects. WER punishes a model for transcribing "gonna" when the speaker said
  "gonna"; a dictation tool optimised for WER against read-aloud corpora can lose
  to one optimised for post-edit effort.
- **A fixed corpus serves the Phase 1 engine benchmark.** The Phase 1 ADR
  (`0001-engine-selection.md`) trades accuracy against latency, and edit rate does
  not exist until Phase 3 — two phases after the decision that needs it. So Phase 1
  commits a small self-recorded desk-mic corpus with reference transcripts under
  `tests/fixtures/asr/`, and reports WER on it for each candidate engine.

  **That WER figure is for relative comparison only.** A corpus of this size
  cannot validate an absolute 5% claim, and it is not a G2 measurement. It answers
  "is Moonshine competitive with `small.en` here", which is the only question the
  ADR needs.

**The 5% edit-rate threshold is provisional.** It is carried over from the old WER
number, and the two metrics have different denominators, so it is not a converted
figure — it is a placeholder with a plausible magnitude. Phase 3 is where it gets
confirmed or moved, with real data and a stated reason. Recording it as provisional
is deliberate: a goal with no number cannot fail, and a number presented as
derived when it was inherited is worse than one labelled as a guess.

## 3. Non-goals (v1)

- Real-time streaming transcription with partial results on screen
- Speaker diarization or multi-speaker meeting transcription
- Mobile
- **Windows and Linux in v1** — v1 is macOS-only (resolved 2026-07-30,
  objection O6; amended 2026-07-31). No phase in §9 builds a second platform,
  §6.4 stubs no files for one, and `injection/factory.py` raises an actionable
  error naming the unsupported platform rather than failing obscurely.

  **Windows is post-v1 intent, not a rejected platform.** It ships no code in
  v1 and gates nothing, but §7.3's *portability floor* keeps the port from
  becoming a redesign. Linux remains a straightforward non-goal — no stated
  intent either way.

  The distinction matters because "not now" and "not ever" imply different
  work today. The floor is the entire difference, and it is four items long.
- Cloud sync of history or settings
- Voice commands that control the OS ("open Chrome")
- Text-to-speech (see §12 for where Kokoro actually belongs)

---

## 4. Users

**Primary:** Developers and writers who already know what dictation is, are privacy-motivated
or offline-constrained, and are comfortable with a config file. They will not tolerate a
tool that is slower than typing.

**Hardware splits this group, and the split is a positioning fact rather than an
implementation detail** (2026-07-31, choice-story #8; tier vocabulary corrected
2026-07-31, objection A9). G1's budgets bind on Tier A
machines (Tier A, §7.2) and Tier B ships against the separate, looser G1-CPU bar in §2. Note the tension that creates: privacy motivation and offline
constraint correlate with older and cheaper machines, so the users the product exists
*for* are disproportionately the ones who get the slower tier. The README states both
numbers and which hardware each applies to, in the same place it makes the speed claim
— not only in §2 where implementers read it. A tool marketed on locality whose speed
promise holds only with an accelerator needs that caveat where users are, not where
tests are.

**Secondary:** Users with RSI or motor impairment for whom dictation is not a convenience.
This group raises the bar on reliability — a dropped transcription is not a minor annoyance.

---

## 5. Functional requirements

### 5.1 Core loop

1. Daemon runs in the background with the ASR model resident in memory.
2. User presses and holds the configured hotkey (default: `Right Option`; macOS is the
   only v1 platform per §3).
3. Audio capture begins immediately. A visual indicator appears (§5.4).
4. User speaks and releases the hotkey.
5. Audio buffer is transcribed.
6. Transcript passes through the post-processor chain.
7. Text is injected at the cursor position in the focused application.
8. Session is written to local history.

### 5.2 Capture modes

Config-selectable, one active at a time:

- **`push_to_talk`** (default) — record while held. Predictable, no false starts.
- **`toggle`** — press to start, press to stop. For long-form dictation.
- **`vad_auto`** — press to start, silence detection ends the session.
  Requires VAD (§7.4). Ship behind a flag; it is the mode most likely to misfire.

### 5.3 Configuration

Single TOML file at the platform config directory, resolved through `platformdirs`
(`~/Library/Application Support/amanuensis/config.toml` on macOS — see §7.3's
portability floor). `$AMANUENSIS_CONFIG_DIR` overrides it; that is the one setting
that cannot live in the config file, because it is what finds the config file. Every behavioral decision in this PRD that could
reasonably go either way is a config key with a sane default. No behavior is hardcoded that
a user might want to change.

**One bounded exception** (added 2026-07-31, choice-story #6): **behaviour that a stated
guarantee depends on is not user-settable.** §8's persist-before-inject is the first
instance — the write happens regardless, and `retain` governs only whether the row is
kept (§5.5).

The exception exists because the rule met that collision and resolved it by *redefining
a key* rather than admitting a limit, which set a precedent that the next collision
would inherit. A rule with no stated exception does not stop generating keys whose plain
meaning contradicts a guarantee stated elsewhere; it just makes each one a naming
problem. Prefer this exception to another rename.

The rule remains otherwise absolute, and it does ratchet: any future decision that
"could reasonably go either way" becomes a key, and the surface only grows. That cost is
accepted knowingly — §4's primary user is comfortable with a config file, and
configurability is how this PRD discharges tradeoffs it cannot resolve.

```toml
[hotkey]
mode = "push_to_talk"       # push_to_talk | toggle | vad_auto
binding = "right_option"

[audio]
device = "default"          # or a substring match on device name
sample_rate = 16000         # 16000 ONLY — see the note below the block
max_duration_seconds = 300

[vad]                       # added 2026-08-01, Phase 1. §7.4 specified Silero
                            # trimming and §5.3 had no table for it.
threshold = 0.5             # speech probability above which a frame is speech
min_silence_duration_ms = 2000
speech_pad_ms = 400         # defaults are the ones §7.2's figures were
                            # measured under; changing one invalidates them

[engine]
backend = "faster_whisper"  # faster_whisper | moonshine | parakeet
model = "auto"              # "auto" resolves per §7.2
device = "auto"             # auto | cpu | cuda
cpu_threads = "auto"        # "auto" = performance-core count. NOT the library
                            # default of 4 — see §7.2. Worth ~1.8x.
language = "en"
initial_prompt = ""         # biases vocabulary; see §5.6

[guard]                       # added 2026-08-05, Phase 2b follow-up. See §5.7.
min_decoded_coverage = 0.5    # refuse below this fraction of retained speech.
                              # 0 disables the guard entirely.
retry_below_coverage = 0.7    # re-decode with the bias dropped below this.
                              # Must be >= min_decoded_coverage. 0 never retries.
                              # 0.8 left the shortest genuine sample 2.8 points
                              # of headroom; calibrated against ONE such sample.
retry_max_latency_ms = 2000   # skip the retry rather than pay it. Predicted
                              # from §2's model, not measured after the fact.

# The fallback floor, for engines that cannot report a decoded span. Both keys
# are inert under faster-whisper. See §5.7's blind spot.
min_words_per_second = 0.5
min_audio_seconds = 5.0

[postprocess]
chain = ["rules"]           # ordered: rules | vocabulary | llm. Comment corrected
                            # 2026-08-08 — the validator has accepted
                            # "vocabulary" since Phase 2b and this line had
                            # already diverged from it (objection O9).
                            # The default stays ["rules"]: §2 defines G1 against
                            # it, so changing it moves the configuration every
                            # recorded G1 figure was measured under.
strip_fillers = false       # "um", "uh" — off by default, it is lossy
terminal_punctuation = true # added 2026-08-08, Phase 3. Appends "." when the
                            # transcript ends on a word character. Fires on
                            # 7 of 10 real transcripts, so it needs a key: it
                            # also appends into a URL bar, a shell prompt and a
                            # filename field. §7.3's own standard — "a tool that
                            # rewrites your punctuation has moved the problem" —
                            # is the argument for the key, not against the rule.
spoken_commands = false     # added 2026-08-08, Phase 3. "new paragraph" -> \n\n.
                            # Off by default because it DELETES content words and
                            # nothing measures it: no take in either corpus
                            # contains one. The Phase 3 gate reports its firing
                            # rate; if it changes nothing, the code goes.

[postprocess.llm]
enabled = false
model_path = ""
max_latency_ms = 300        # exceed this and the pass is skipped, not queued

[injection]
strategy = "clipboard"      # clipboard | keystroke
restore_clipboard = true
restore_delay_ms = 150
warn_on_clipboard_manager = true   # tray indicator when a manager is detected; see §7.3

[history]
retain = true               # false: the transcript is still written before
                            # injection (§8, unconditional) and deleted once
                            # injection succeeds. Renamed from `enabled`
                            # 2026-07-31 — see §5.5.
retain_days = 30
store_audio = false         # off by default; audio is the sensitive artifact
```

**Two keys above are not the free choices they look like** (added 2026-08-01,
Phase 1 findings 2 and 3).

`[audio] sample_rate` accepts **16000 and nothing else**. Whisper's feature
extractor consumes 16 kHz mono, and faster-whisper's Silero wrapper hardcodes a
512-sample window — the 16 kHz frame size. The intersection of the two
constraints is one value. It is rejected at load with both reasons named,
rather than resampled somewhere unspecified.

`[vad]` has **no `enabled` key**, and that absence is deliberate. §7.2 records
that without trimming no candidate model passes G1's p95 at all, so an off
switch would be a supported way to break a published guarantee — which is
exactly what the bounded exception above refuses.

That makes three instances of the exception across two phases, on a rule
described as "otherwise absolute": persist-before-inject, `[vad] enabled`, and
`[audio] sample_rate`. Phase 0's finding 5 predicted the accumulation. The rule
is therefore restated as a shape rather than a list: **a key exists for every
decision that could reasonably go either way, and a decision that a stated
guarantee or an external library has already removed is not one of those.**
Enumerating a fourth exception would be the wrong response to the next
collision.

### 5.4 Feedback

The user must always know whether the mic is live. Non-negotiable — a dictation tool that
is ambiguous about recording state is a privacy problem regardless of where the audio goes.

- Tray/menubar icon state: idle / recording / transcribing / error
- Optional audio cue on start and stop (`[feedback] sounds = true`)
- Recording state must be visible without the tray menu open
- **A recording affordance with more presence than a menu-bar glyph** (added
  2026-08-03, Phase 2b finding 4). The minimum indicator built in Phase 2b
  satisfies the line above — the glyph fills on press and empties on release,
  confirmed against a running daemon — and the operator's first reaction to
  using it was that a glyph is not enough to be confident the microphone is
  live. This is a Phase 4 deliverable, not a Phase 2b one: it means an
  `NSPanel` overlay or a real `.app` bundle, both of which are work §9 already
  puts there.

  Recorded because of where it came from. Every other requirement in this
  document was written before anything existed; this one came from someone
  using the product and finding the specified behaviour insufficient. A
  requirement met to the letter and reported as inadequate by its user is worth
  more than one argued into the spec, and it should not be lost because the
  gate it arrived at had already passed.

  Note also what met the requirement *without* being built: macOS's own
  microphone-in-use indicator, which the operator saw alongside the glyph. It
  is the one recording signal this product cannot suppress and cannot get
  wrong, and §5.4's purpose is served by it regardless of what Amanuensis
  draws. That is a reason to build the richer affordance for *confidence*
  rather than for *correctness*.
- **Clipboard exposure state** — when `strategy = "clipboard"` and a known
  clipboard manager is detected, the tray carries a persistent indicator that
  transcripts transit the system clipboard (§7.3, objection O12). Same
  reasoning as recording state: a privacy-relevant condition the user cannot
  see is a privacy problem regardless of whether it is ever exercised.
- **A recovered transcript is signalled distinctly from a clean one** (added
  2026-08-05, §5.7, objection O3). When the collapse guard's retry succeeds,
  what reaches the cursor was decoded *without* the vocabulary bias the user
  configured, and is therefore systematically worse at exactly the proper nouns
  `initial_prompt` exists for. Folding that into the idle state would leave the
  user reading substituted text with no signal that anything but the model
  produced it — which is dictionary objection O5, that a rewriting pass
  presents as an ASR error and sends the user to the wrong fix. Distinct from
  `error`, which is what a *refused* transcript raises.

### 5.5 History

Local SQLite at the platform data directory, resolved through `platformdirs`
(`~/Library/Application Support/amanuensis/history.db` on macOS), overridable with
`$AMANUENSIS_DATA_DIR`. Stores timestamp, transcript,
duration, engine, and latency breakdown. Audio is **not** stored unless explicitly enabled.
`manu history --purge` wipes it.

Latency breakdown is a product requirement, not a debugging nicety — G1 cannot be defended
without per-stage timings.

**`store_audio` validated and did nothing for three phases** (found 2026-08-03,
implemented 2026-08-05). It was a config key with a documented meaning, a
validation rule, a test asserting its default, and no code that read it. Setting
it to `true` had no effect of any kind.

That is not a missing feature, it is §5.3's rule broken at the surface the rule
is about: a key that exists is a promise that the behaviour behind it is
reachable. The cost came due when the live collapse in §5.7 turned out to be
unreproducible — the one setting that would have preserved the evidence was the
one that did nothing, and nobody could have known without reading the source.

Implemented now, minimally and with its own retention:

- Audio is written to `audio/<session-id>.wav` under the data directory, on the
  same `platformdirs` path as everything else this product writes.
- **It is swept by `retain_days` at daemon start**, through the existing
  `sweep_pending` mechanism. Audio is the sensitive artefact (§7.6), and adding
  a writer without a reaper would create a directory that grows without bound
  and that no command reaches — `manu history --purge` is Phase 3.
- `retain = false` writes no audio at all, on either path. The pending-file
  mechanism above exists to keep a transcript recoverable across a crash; audio
  is not needed for that and §5.3's privacy default is `store_audio = false`
  precisely because this is the artefact that matters.

**Third instance of "an amendment must reach the tooling."** The first was
`bench_engines.py` regenerating a withdrawn WER figure, the second was
`restore_ms` having no column. A key that parses is not a key that works, and
nothing in the test suite could tell the difference — `test_config.py` asserted
the default and passed.

**`retain` controls retention, not the write** (resolved 2026-07-30, objection
O10; key renamed 2026-07-31, choice-story #10). The pre-injection write in §8 happens
**unconditionally**. `retain = false` means the row is deleted immediately after
injection succeeds — so nothing persists, and the crash guarantee still holds on the
path where it matters.

The key was originally `enabled`, which required this section to instruct readers to
read it as *retain* rather than *use* — a gloss that would have had to survive into the
README, the tray, any settings UI (§11.2) and every validation message, each a fresh
opportunity for the plain reading to win. The name is the interface; renaming it while
Phase 0 has not started and no user has a config file cost nothing.

The alternative reading — that `enabled = false` disables the write — would have
made §8's "never lose a transcript" silently conditional on a setting the user was
never told it depended on. That trade lands worst on the two §4 users at once: the
privacy-motivated primary user is the one most likely to disable history, and the
secondary user with motor impairment, for whom "a dropped transcription is not a
minor annoyance," is the one who most needs the recovery path. Neither would have
been told the trade existed.

**The non-retaining path does not touch the database** (resolved 2026-07-31,
choice-story #5). When `retain = false`, the pre-injection transcript is written to a
`0600` temp file and unlinked once injection succeeds — it never enters
`history.db` at all.

The earlier reading was write-then-`DELETE` in SQLite, which makes "nothing persists" a
privacy claim resting on a statement that marks pages free for reuse rather than
erasing bytes. `secure_delete`, `VACUUM` and WAL checkpoint behaviour all bear on
whether the transcript is actually gone, and specifying all three correctly is more
work — and easier to get subtly wrong — than not writing it to the shared file in the
first place. A component chosen silently for retention convenience should not become
load-bearing for a privacy promise.

**What this does and does not buy** (2026-07-31, objection A7). `unlink()` drops a
directory entry and releases blocks for reuse. On a journalling copy-on-write
filesystem that is the *same* property as `DELETE`, one layer down — so the honest
statement is not "the bytes are gone":

> **Amanuensis does not claim secure erasure of the pre-injection transcript.**
> `retain = false` means no transcript is retained in any file Amanuensis keeps
> open or reads back. It does not mean the bytes have been overwritten on disk.
> Full-disk encryption is the mechanism that makes residue unreadable, and it is
> the operating system's job, not this application's.

What the temp file genuinely buys is narrower and still worth having: a long-lived
shared database stops being load-bearing for a privacy promise. That was the
correct half of the original change. Presenting it as though the erasure claim had
been *repaired* — rather than moved down a layer and left standing — was not.

Three gaps follow from the mechanism and are closed here:

1. **The path is resolved through `platformdirs`**, in a dedicated
   `pending/` directory under the data dir — not an unnamed system temp location.
   §7.3's portability floor item 2 applies to every path this product writes, and
   a file nothing can name is a file nothing can purge.
2. **Orphans are swept at daemon start.** The file is unlinked once injection
   *succeeds*; injection failing is the case the whole ordering exists for, and
   §7.3 documents it failing in Electron and Java apps. Every failed injection and
   every crash between write and unlink leaves a plaintext transcript behind, and
   the user who set `retain = false` is the one accumulating them.
3. **`manu history` surfaces pending transcripts and `--purge` covers them.**
   §8 promises the user can recover their words when injection fails. With
   `retain = true` that promise is discharged by `manu history`. Without this, the
   `retain = false` artefact was a file the user was never told about and no
   command surfaced — the guarantee mechanically preserved and practically
   unreachable, landing hardest on §4's secondary user, for whom "a dropped
   transcription is not a minor annoyance."

**The write is scoped to sessions that reach injection** (choice-story #7). §8's
guarantee protects words the user has committed to. A session aborted before injection
— `abort_session()`, an empty transcript, a mic disconnect mid-capture — has no such
claim and leaves nothing behind on either path. This closes the half of objection O10
that was explicitly deferred: previously every misfired session was written to disk
before the user had seen it, and retained for thirty days by default when `retain` was
on.

### 5.6 Custom vocabulary

Users have proper nouns the model will never get right. Two mechanisms:

1. `initial_prompt` passed to the ASR engine — cheap, works today, limited length.
2. A post-processing replacement map (`vocabulary.toml`, beside `config.toml` in the
   `platformdirs` config directory) applying
   case-insensitive whole-word substitutions.

Both. They fail in different places.

**Specified and built in Phase 3** (2026-08-08). Full specification in
`docs/superpowers/specs/dictionary.md` rev 2 and
`docs/superpowers/specs/phase-3-postprocessing.md` rev 3. Five things above are
now measured rather than asserted, and four of them change what this section
said:

- **"Whole-word substitutions" is wrong and was the likelier error all along.**
  `spread sheet → spreadsheet` is two tokens becoming one, and it is what the
  model produces when it half-hears the word. A whole-word map catches
  `breadshoe` and misses the common case. **The map matches phrases.**
- **"They fail in different places" is now answered** (dictionary O9), and the
  answer is not flattering to the two-table design. `[boost]` fails by
  *degrading unrelated speech* — measured at +3.2 and +5.2 WER on two of six
  samples, for a net macro gain of 1.1 — and by collapsing a transcript entirely
  on one (§5.7). `[replace]` fails by firing on a homonym, invisibly.
- **`[boost]` is scoped per application** (operator decision 2026-08-04), keyed
  on the bundle identifier `TextInjector.focus_identity()` already returns on
  every dictation. A global always-on prompt is a trade, not a win, so
  `[boost] terms` defaults to empty and `[boost.apps]` is the intended surface.
  `[boost]` is authoritative and `initial_prompt` is **prose framing only**
  (dictionary O7).
- **There is no model-size fix inside G1**, which this section asserted in one
  line and is now measured: `base.en` doubles the parameters, buys one proper
  noun in five, and misses G1's p95 by 248 ms. `beam_size = 5` costs 2.5× the
  latency for 1.6 WER points. A dictionary is not a patch over a fixable
  deficiency — it is the only mechanism that addresses this class of word at all.
- **`vocabulary.toml` is re-read when its mtime changes**, not only at startup
  (operator decision 2026-08-04) — and it therefore has a *different lifecycle
  contract from `config.toml`*: strict at startup, permissive at reload, because
  at reload the daemon is holding a transcript and losing it to a half-saved file
  is the wrong failure. §5.3 states the split.

### 5.7 The collapse guard

**Added 2026-08-05, as a Phase 2b follow-up defect fix.** Mechanism 1 above can
silently destroy a transcript, and it shipped in Phase 1 with nothing watching it.

The failure is not theoretical and it is not the dictionary's. On 2026-08-05 a
**30.5-second dictation on the operator's machine returned two words** —
`" For Tenants."` — with `initial_prompt` set, no error raised, the audio buffer
full, and the text injected at the cursor as though it were what had been said.

| | words per second of retained speech |
|---|---|
| Phase 1 corpus, slowest genuine sample | 2.18 |
| Phase 1 corpus, fastest | 3.33 |
| Measured collapse, prose prompt on `03-proper-nouns` | 0.20 |
| **The live failure** | **0.066** |

**The guard measures the decoder, not the speaker.** This is the second design
and the first one was wrong; the reasoning is worth keeping because the wrong
version is the intuitive one.

**The denominator is speech, and making that true took a correction.** §5.7
first divided by `TrimResult.retained_seconds` and called it speech by
construction. It is not: `[vad] speech_pad_ms` adds 400 ms of deliberate
non-speech to each side of every retained segment, and the decoder correctly
emits nothing over it. That under-reports coverage **in proportion to how short
the clip is** — noise in a 30-second dictation, a quarter of a 3.2-second one.
Measured: the corpus's shortest genuine sample read **62.2%** against a 50%
refusal gate before the correction and **82.8%** after. The bias was systematic,
pointed at refusing genuine transcripts, and concentrated on the input this
product's first user produces most often. `TrimResult` now reports
`padding_seconds` and the guard subtracts it.

The obvious instrument is words per second — the transcript is too short for the
speech, so divide one by the other. It was drafted that way, and objection O1
killed it. Words per second is a property of *how the user talks* divided by
*how long they talked*. The failure is a property of *where the decoder
stopped*. The proxy carries a confound the product has no evidence about, and
a direct measurement was available the whole time.

`faster_whisper` returns segments carrying `start` and `end`; `_decode` was
discarding them. **Decoded coverage** is the last segment's `end` over retained
seconds — did the decoder traverse the audio it was given.

**Measured on the Phase 1 corpus, 2026-08-07** (`scripts/verify_guard.py`),
not estimated:

| | coverage |
|---|---|
| Reproduced collapse — `03-proper-nouns` under a prompt the decoder echoes | **8.3%** |
| Genuine speech, lowest of six samples (`06-short`, 3.2 s) | **82.8%** |
| Genuine speech, highest | 100.0% |

The collapse and the genuine floor differ by a factor of ten, and the 50%
refusal gate sits between them with 33 points of margin below and 42 above.

Three properties follow, and each one is a defect in the rate floor:

1. **Coverage is duration-independent.** It reads the same at two seconds and at
   sixty. The rate floor could not: word count is an integer, so at two seconds
   the rate is quantised to 0.5 w/s *per word* — a genuine one-word "Yes." and a
   transcript collapsed to one word are **the same measurement**. `min_audio_seconds`
   was never a policy choice; it was the floor conceding it cannot work on short
   audio. And short utterances are the ordinary case for this product's first
   user, so the exemption was a blind spot over the most common input.
2. **Coverage has no false-positive population.** A slow or quiet speaker still
   produces segments spanning their audio. The rate floor's worst outcome —
   refusing a *genuine* transcript from someone who talks slowly — was a hazard
   this project had no evidence about, aimed squarely at §4's secondary user.
3. **Coverage explains rather than detects.** Dictionary objection O3 asked
   whether the collapse is early termination or domain drift, and said a floor
   answers only the first. Coverage distinguishes them on every firing.

**The threshold does two jobs and therefore is two numbers.** Spending a decode
and withholding the user's words have costs that differ by orders of magnitude,
and one number tuned for the second is blind to everything short of total
collapse (objection O4).

| coverage | what happens |
|---|---|
| ≥ `retry_below_coverage` (0.7) | nothing; the transcript is used |
| between the two | decoded again with the bias dropped, then re-judged |
| < `min_decoded_coverage` (0.5) after recovery | **not injected**; the error state reports it |

The middle band is also where the evidence comes from. A retry produces biased
and unbiased output over the same audio, both recorded, which is the comparison
§5.7 otherwise has no way to generate.

**On a fired verdict the transcript is retried, not discarded** (choice-story
C4). Two consequences are recorded here rather than discovered later:

1. **The retry must drop `initial_prompt` or it is worthless.** §7.2 fixes
   `beam_size = 1`; greedy decoding of the same audio with the same prompt
   returns the same words. The prompt is the only lever available, which makes
   the retry a test of the hypothesis as well as a recovery.
2. **Where no `initial_prompt` is configured there is nothing to retry**, and
   the guard goes straight to the loud failure. Reporting a recovery attempt
   that was mechanically identical to the first would be an instrument
   describing work it did not do.

3. **The retry itself has a ceiling**, and skipping it is a recorded outcome
   rather than a silent one. §2's model gives `transcribe_ms ≈ 48.8 + 13.69 ×
   seconds`, so a retry is *predicted* before it is attempted and skipped when
   the prediction exceeds `retry_max_latency_ms`. §6.3's standing rule is that a
   stage inside G1's window needs a field; this one has `guard_ms`. The default
   of 2000 ms allows a retry on anything up to about 140 seconds of speech and
   declines on a five-minute dictation, where doubling the decode helps nobody.

**When the retry also fails, the text is not injected**, and the words are
reachable. §8's write is unconditional and precedes this decision, but *written*
is not *recoverable*: `manu history` refuses and names Phase 3, so before this
change a refused transcript went somewhere no shipped command could show it
(objection O2). **`manu history --last` ships with the refusal**, for that
reason and no other. A guarantee that is mechanically preserved and practically
unreachable is the failure §5.5 already documented once.

**This overrides choice-story C4, which specified failing open.** C4 is titled
*"The guard fails open"* and slice V1 says the same. Recorded as an override
rather than cited as support: human decision, 2026-08-04, reaffirmed 2026-08-05.
The argument is that a destroyed transcript at the cursor costs the user a
noticing and an undo, and the refusal is only defensible because the words are
retrievable — which is why the retrieval verb is in scope and not deferred.

**Three cases where the guard does not run**, each recorded on the session
rather than inferred from a missing value:

| | why |
|---|---|
| `min_decoded_coverage = 0` | Explicitly disabled |
| `TrimResult.fell_back` | No speech was detected, so the denominator is the whole clip rather than speech |
| The engine reports no decoded span | The fallback floor applies instead — see below |

**The fallback floor, and its blind spot.** An engine that cannot report where
decoding stopped falls back to words per second of retained speech, with
`min_audio_seconds` exempting audio too short for the quantisation to mean
anything. Both keys are inert under faster-whisper. **Stated as a blind spot
rather than a setting:** under the fallback, short dictation is unguarded, and
that is a limitation of the fallback, not a decision about short dictation.

**Why an off switch is permitted here and was refused for `[vad] enabled`.**
§5.3's bounded exception withholds a key when a stated guarantee depends on the
behaviour. No guarantee depends on this one yet, the thresholds are provisional,
and a threshold that can be wrong about a user must be adjustable by that user.
Coverage removes the *known* false-positive population; it does not prove there
is none. If it holds across the Phase 3 dictation set, this reasoning is what
has to be revisited to remove the switch.

**What the guard cannot see.** Coverage catches a decoder that stopped early.
The opposite failure — a hallucinated *expansion*, plausible and wrong — passes
it untouched, as does a decode that traverses the audio and gets the words
wrong. §7.5 carries a no-invent check for the first and it is a Phase 5
concern; recording the gap is the honest alternative to implying the guard
covers more than one failure.

**A recovered transcript is not silently substituted.** When the retry succeeds,
what reaches the cursor was decoded *without* the vocabulary bias the user
configured, and is therefore systematically worse at the proper nouns
`initial_prompt` exists for. §5.4's indicator distinguishes recovery from
success, because a transcript the product quietly swapped is dictionary
objection O5 re-committed: the user sees different text and has no signal that
anything but the model produced it.

**The mechanism, which was unexplained until the guard was built.** Dictionary
objection O3 posed it as a fork: *"if the cause is early-termination, a floor is
right; if it is domain drift, a floor is half a guard."* Reproduced 2026-08-07,
it is neither of the things the record guessed. **The decoder echoes the prompt
and terminates.** `initial_prompt = "And how much is this?"` produces exactly
that string as the transcript of a 25-second clip, deterministically.

That retires the "prose prompt" description in the 2026-08-03 record, which
described the *output* and attributed it to the prompt's register. The register
is not the variable — five other prompts of comparable shape, including a
600-character one, collapsed nothing. What the collapsing prompt has is the form
of a complete short utterance the model can plausibly emit as a whole
transcript.

Coverage measures early termination directly, so the instrument and the failure
now match rather than the instrument being aimed at a symptom. **Not answered:**
why this clip and not the other five. The guard does not need that answer, which
is the point of building it against the failure rather than against the cause.

---

## 6. Architecture

### 6.1 Process model

One long-lived Python daemon. The model stays resident — this is the entire reason the
product can hit G1. A per-invocation CLI that loads a model would take 3–8 seconds and
there is no version of that which is acceptable.

```
manu daemon    # long-running background process
manu toggle    # IPC to the daemon — for external hotkey managers.
               # Transport is platform-resolved (unix socket on macOS,
               # named pipe on Windows); see §7.3 portability floor.
manu status
manu history
```

### 6.2 Component boundaries

```
DictationController  (orchestrator — owns the loop, owns nothing else)
├── HotkeyListener          → emits press/release events
├── AudioCapture            → ring buffer, sounddevice/PortAudio
├── VoiceActivityDetector   → optional, Silero VAD via ONNX
├── TranscriptionEngine     ← ABC
│     ├── FasterWhisperEngine
│     ├── MoonshineEngine
│     └── ParakeetEngine
├── TextPostProcessor       ← ABC, composed into an ordered chain
│     ├── RuleBasedPostProcessor
│     ├── VocabularyPostProcessor
│     └── LocalLLMPostProcessor
├── TextInjector            ← ABC
│     └── MacOSInjector           (v1; other platforms are §3 non-goals)
├── HistoryStore            → SQLite
└── TrayApp                 → status surface only, no business logic
```

### 6.3 Class contracts

**Models** know what a thing *is*. They do not know about the UI and do not drive flow.

```python
@dataclass
class DictationSession:
    """A single press-speak-release cycle and everything that happened to it."""
    id: str
    started_at: datetime
    audio: np.ndarray | None
    sample_rate: int
    raw_transcript: str | None = None
    final_text: str | None = None
    timings: LatencyBreakdown = field(default_factory=LatencyBreakdown)
    #: §5.7. Always set once the worker reaches the check, including when the
    #: check does not run — `None` here means the worker never got that far.
    guard: GuardVerdict | None = None
    error: str | None = None
    #: Set by the worker, last, after every field above is written. See the
    #: concurrency model below — this is the only synchronisation point.
    completed: threading.Event = field(default_factory=threading.Event)

    def duration_seconds(self) -> float: ...
    def to_history_row(self) -> dict: ...
    def wait(self, timeout: float | None = None) -> bool: ...
```

```python
@dataclass
class LatencyBreakdown:
    """Per-stage timings. Required for G1 — every stage records into this.

    Two summary properties, deliberately distinct (see §2, G1 measurement note):
    `g1_ms` is the gated number; `total_ms` is for diagnostics only. Asserting
    G1 against `total_ms` would compare a ~10,400 ms figure to a 400 ms budget
    and fail unconditionally.
    """
    capture_ms: float = 0.0        # excluded from G1 — G1's clock starts at release
    vad_ms: float = 0.0            # inside G1 — trimming happens after release
    transcribe_ms: float = 0.0
    postprocess_ms: float = 0.0
    guard_ms: float = 0.0          # inside G1 — §5.7's check and any retry
    persist_ms: float = 0.0        # inside G1 — §8's write precedes injection
    inject_ms: float = 0.0
    restore_ms: float = 0.0        # OUTSIDE G1 — runs after the text is present

    @property
    def asr_ms(self) -> float:
        """vad + transcribe. The quantity §7.2's tier check bounds at 350/700."""

    @property
    def g1_ms(self) -> float:
        """asr + postprocess + persist + inject. The number G1 is gated on."""

    @property
    def total_ms(self) -> float:
        """Every stage including capture. Diagnostics only — never assert G1 on this."""
```

```python
@dataclass(frozen=True, slots=True)
class Transcription:
    """What one decode produced, and how much of the audio it got through.

    `decoded_seconds` is where the decoder stopped, in the timebase of the
    audio handed in — which is trimmed audio, so it is directly comparable to
    `TrimResult.retained_seconds`. `None` from an engine that cannot report it.

    This follows the `InjectionResult.restore_ms` precedent exactly: a caller
    needs a quantity only the implementation can compute, and timing it from
    outside is impossible because the call returns once. Phase 2a made that
    argument for the injector; §5.7 is the same argument at the engine.
    """
    text: str
    decoded_seconds: float | None
```

```python
@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """§5.7's answer about one transcript, and the evidence behind it.

    Every quantity is carried even when the guard did not run, because
    objection O10's failure is a guard that *silently* never fires: an
    over-trimming VAD shrinks the denominator and nothing about that is
    visible from the verdict alone.
    """
    outcome: GuardOutcome            # passed | recovered | failed | skipped
    retained_seconds: float
    coverage: float | None           # decoded / retained; None on the fallback
    words_per_second: float | None   # the fallback instrument only
    reason: str | None               # why it was skipped, or what failed
    retried: bool                    # was an unbiased second decode attempted
```

**`transcribe` returns `Transcription` and gains a `biased` keyword**
(2026-08-05, §5.7). Two changes for two reasons.

`biased=False` asks for a decode with vocabulary bias suppressed, which the
retry needs and the contract could not express. An alternative was weighed and
rejected: passing `initial_prompt=""` through as a parameter. That makes the
*caller* responsible for knowing what biasing means on a given backend, which is
the knowledge `TranscriptionEngine` exists to hold — Moonshine and Parakeet
(§7.2) do not necessarily have the same mechanism, and a caller passing an empty
prompt string to an engine with no prompt concept is asking a question that does
not parse. The flag asks for the *behaviour*.

The return type changed because `str` could not carry `decoded_seconds`, and
**the information was already crossing the boundary and being discarded** —
`_decode` joined the segment texts and dropped `start`, `end`, `avg_logprob`,
`no_speech_prob` and `compression_ratio` on the floor. Four production call
sites, all of which want `.text`.

**`guard_ms` joins `LatencyBreakdown`, inside `g1_ms`.** §5.7's retry is a
second decode on the path between hotkey release and text at the cursor, so it
is inside the window by the rule stated above — which this revision broke in the
same document that restates it, making four phases in a row. The field covers
the check and any retry it triggers; a passed guard costs microseconds and a
recovered one costs a full decode, and one figure that mixed them would hide the
only case worth looking at.

**`vad_ms` and `asr_ms` added 2026-08-01** (Phase 1 finding 1). §7.4 calls
trimming "the dominant latency lever, not a free bonus" and moves it into
Phase 1 because it changes what that gate measures — and this breakdown had
nowhere to record it. G1's clock starts at hotkey release and trimming happens
after release, so the cost is inside the gated number either way; the only
question was whether it got its own field.

Folding it into `transcribe_ms` would have buried the dominant lever inside the
stage it exists to shrink, in the very structure G1 is defended with. `asr_ms`
exists because §7.2's tier check runs "VAD on, matching runtime" and therefore
bounds trim-plus-decode, a quantity no property expressed.

**`persist_ms` and `restore_ms` added 2026-08-02** (Phase 2a findings 1 and 5),
and the rule they establish matters more than either field.

`persist_ms` is §8's pre-injection write. G1's clock is already running when it
happens, so it is inside the gated number, and it is separate from `inject_ms`
because the two have different remedies — a slow write is a storage problem, a
slow injection is a target-application problem, and one combined figure sends a
reader to the wrong one.

`restore_ms` is the clipboard restore, and it is **outside `g1_ms` and inside
`total_ms`**. G1 ends when the text is *fully present in the focused
application*; the restore runs strictly after that, while the user is already
reading their words. This was not a theoretical distinction: the first real
end-to-end dictation reported `g1_ms` **421.9 ms** against a 400 ms budget, of
which **180.3 ms** was `inject_ms` and roughly 150 of those was
`restore_delay_ms` sleeping. Split correctly the same path measures **231.6 ms**.
`InjectionResult` carries `restore_ms` because only the injector can separate
them — `inject()` returns once, after both.

**The pattern, stated so a fourth phase does not rediscover it.** Three phases
have now found a stage this structure could not express: `vad_ms` at Phase 1,
`persist_ms` and `restore_ms` at Phase 2a. `LatencyBreakdown` was specified
before anyone knew what the stages were. The standing rule for any stage added
later:

> A stage inside G1's window with no field is a stage that cannot be defended
> when G1 is missed. A stage **outside** the window recorded inside it is a miss
> that never happened. Decide which side of "text fully present in the focused
> application" a new stage falls on, give it a field, and say which summary
> property it belongs to.

**Abstract bases** define the swap points. The original rule — "every one of these
exists because there is a real chance we replace the implementation, not for symmetry" —
was one test covering three structurally different jobs, plus a fourth ABC it was never
applied to (choice-story #4). Restated 2026-07-31 as three rules, each carrying the
contract its own job requires:

| Kind | Dispatch | Instances live | ABCs |
|---|---|---|---|
| **Replacement** | `registry.py`, config string → class | one at a time | `TranscriptionEngine` |
| **Platform selection** | `factory.py`, platform detection | one per process | `TextInjector`, `HotkeyListener` |
| **Composition** | ordered chain from `chain = [...]` | **several at once** | `TextPostProcessor` |

The test to apply before adding an ABC is now *which of these three is it* — and if it
is none, it is symmetry and does not get one.

**Composition needs a contract the other two do not**, and `TextPostProcessor` was
given two members on the assumption it was the same kind of thing as the others.
It is not:

- **Order is significant.** `chain` is ordered (§5.3) and each processor transforms the
  same value. Reordering changes output.
- **`process` must be pure with respect to the session.** It returns transformed text
  and does not mutate `DictationSession`, so a chain is replayable against a stored
  transcript and a processor cannot reach the audio.
- **A raising processor must not cost the transcript.** If `process` raises mid-chain,
  the chain is abandoned and the **last good text** proceeds to the §8 write and then
  to injection; the error is surfaced in the tray (§5.4) and recorded, not swallowed
  silently.

  **Corrected 2026-08-08** (Phase 3, objection O1). This previously read "§8's
  persist-before-inject ordering already ran, so the words survive regardless."
  The chain runs **before** the write, and `_process` had no per-processor guard,
  so a raising processor persisted nothing and injected nothing. Unreachable for
  three phases because `cli.py` passed `processors=[]` — a sentence asserting a
  guarantee above code that could not honour it, and the fourth instance of that
  shape in this project.

`TranscriptionEngine` got `load` / `warm_up` / `is_loaded` because someone thought about
its lifecycle. This is that thinking for the boundary that will actually grow — rules,
vocabulary, and whatever the Phase 3 edit-rate report demands.

```python
class TranscriptionEngine(ABC):
    @abstractmethod
    def load(self) -> None:
        """Called once at daemon start. Blocking. Must be idempotent."""

    @abstractmethod
    def transcribe(
        self, audio: np.ndarray, sample_rate: int, *, biased: bool = True
    ) -> Transcription:
        """`biased=False` suppresses every vocabulary bias this engine applies.

        For faster-whisper that is `initial_prompt`. An engine with no biasing
        mechanism ignores the flag — it is already unbiased.

        `Transcription.decoded_seconds` is `None` from an engine that cannot
        say where decoding stopped; §5.7 falls back to a rate floor there
        rather than treating silence as a pass. See §5.7.
        """

    @abstractmethod
    def warm_up(self) -> None:
        """Run one throwaway inference. First real call must not pay compile cost."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...
```

```python
class TextInjector(ABC):
    @abstractmethod
    def inject(self, text: str) -> InjectionResult: ...

    @abstractmethod
    def check_permissions(self) -> PermissionStatus:
        """Non-destructive check. Called at startup, surfaced in the tray."""

    def warm_up(self) -> None:
        """Pay the one-time cost now. Idempotent, and invisible to the user."""

    def focus_identity(self) -> str | None:
        """Who would receive text right now? None when it cannot be told."""
```

**`focus_identity` added 2026-08-03** (Phase 2b), for the hazard the concurrency
model below creates rather than for anything injection needs. `end_session()`
does not block, so session N's text can land in whatever window has focus when
the worker reaches it; the controller compares this value across that gap and
declines to type when it changed. It is on the injector because the injector is
the component that knows where text goes — the controller must not learn what a
bundle identifier is (§6.2). The value is opaque and comparable; nothing may
parse it.

Concrete and `None` by default, on `warm_up`'s argument. **`None` means *cannot
tell*, which is deliberately not *changed*:** an implementation with no way to
answer must still inject, because the check exists to catch a change and unknown
is not one.

**`warm_up` added 2026-08-02** (Phase 2a finding 2), from measurement rather
than symmetry. The first `inject()` on macOS cost **165.8 ms** and every
subsequent one under 2 ms, because the pyobjc bridges load on first use — 165 ms
against a 400 ms budget, landing on the user's *first* dictation. That is the
identical problem `TranscriptionEngine.warm_up` exists for ("first real call
must not pay compile cost"), at a boundary that had no method for it. Phase 2a
escaped it only by accident: the CLI checks permissions and detects clipboard
managers, which happen to load both bridges before the microphone opens.

Concrete with a default no-op rather than abstract — an injector with nothing to
warm should not be made to write an empty method, and forgetting it is slow once
rather than silently wrong. **One constraint is tighter than the engine's:** the
engine can afford a throwaway inference because it has no effect outside the
process; an injector must never type a throwaway character into whatever window
happens to have focus.

**`HotkeyListener` is contracted here from 2026-08-03** (Phase 2b). §6.4 declared
`hotkey/base.py` from the start and §6.2 listed the component, but this section
never wrote the contract down — which portability floor item 4 (§7.3) called out
and Phase 0 closed by declaring the ABC without §6.3 ever catching up.

```python
class HotkeyListener(ABC):
    @abstractmethod
    def start(self, on_press: Callable[[], None],
              on_release: Callable[[], None]) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @property
    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def check_permissions(self) -> PermissionStatus:
        """Non-destructive check. Called at startup, surfaced in the tray."""
```

**`check_permissions` added on `TextInjector`'s argument, not for symmetry.**
Every plausible platform has some version of "this app may not watch your
keyboard", and the user's first dictation is the worst time to discover it. The
ABC's own text already said `start` raises when the OS refuses the tap and that
this "is a startup-time condition the tray must surface" — a condition the tray
must surface needs a method that answers it without raising.

On macOS the two grants are **separate and confusable**:
`CGPreflightPostEventAccess` is Accessibility, for injection;
`CGPreflightListenEventAccess` is Input Monitoring, for the hotkey. Different
Settings panes, granted independently, and a user who granted one for Phase 2a
will reasonably believe they granted both. Each remediation therefore names its
own permission *and* says the other one is not it. Both are the non-prompting
halves of documented pairs; the `CGRequest*` twins raise a system dialog, which
a daemon that starts at login must never do at startup.

The callbacks return nothing, and that is load-bearing rather than incidental:
there is nothing useful a callback could hand back to a thread that must not
wait for it.

```python
class TextPostProcessor(ABC):
    @abstractmethod
    def process(self, text: str, session: DictationSession) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
```

**Controller** owns orchestration and nothing else. It does not know how injection works
on macOS, does not know what model is loaded, and does not format text.

```python
class DictationController:
    def __init__(
        self,
        config: AppConfig,
        engine: TranscriptionEngine,
        injector: TextInjector,
        processors: list[TextPostProcessor],
        history: HistoryStore,
        capture: AudioCapture,                                   # 2026-08-03
        detector: VoiceActivityDetector,                         # 2026-08-03
        on_state_change: Callable[[DictationState], None] | None = None,
    ) -> None: ...

    def start(self) -> None: ...          # load, warm, start the worker
    def shutdown(self) -> None: ...       # release the mic, stop the worker

    def start_session(self) -> None: ...
    def end_session(self) -> DictationSession: ...
    def abort_session(self) -> None: ...
```

**Four additions, made when the class was first built** (2026-08-03, Phase 2b).
`capture` and `detector` were in §6.2's component tree and absent from this
constructor, which would have meant the controller constructing them itself —
the one component that must not know what a sample rate is reaching for
PortAudio. `start`/`shutdown` exist because the worker thread and the resident
model have a lifetime and the three session methods do not describe it.

`on_state_change` is how §5.4's state leaves the controller without the
controller knowing what draws it. It takes a `DictationState` — exactly §5.4's
four values, no more — and a callback that raises must not stop dictation:
§6.2 makes the tray a status surface with no business logic, and that has to
hold in the failure direction too.

**Configuration is loaded once and passed explicitly** (resolved 2026-07-31,
choice-story #3). `load_config() -> AppConfig` returns a **frozen** dataclass at
startup. There is no `AppConfig.get()` and no module-level instance.

```python
cfg = load_config()                      # frozen, validated, once
ctrl = DictationController(config=cfg, engine=..., injector=..., ...)
injector = MacOSInjector(cfg.injection)  # narrow slice, not the whole config
```

The PRD previously specified a singleton exposed via `AppConfig.get()` *and*
constructor injection into `DictationController`, one sentence apart, without saying
which was authoritative — Service Locator beside Dependency Injection, which is the
pattern DI was formulated against. Both would have been used, and a reader at any call
site could not tell which instance was in play.

Components receive the narrowest slice they need. `RuleBasedPostProcessor` cannot read
`[injection]` because it is never handed it — a structural boundary rather than a
convention. The cost is real and accepted: `restore_delay_ms` reaches
`injection/macos.py` through a parameter rather than an ambient lookup, and §5.3's
config policy is now slightly more expensive to extend. That expense is the point;
choice-story #6 notes the policy ratchets precisely because adding a key currently
costs nothing.

#### Concurrency model

Named 2026-07-31 (choice-story #2, §7.3 portability floor item 1). The PRD previously
specified none, which meant the daemon's most architecturally consequential property
would have been settled by whoever wrote Phase 2b first.

The daemon is **Half-Sync/Half-Async** (POSA vol. 2, Schmidt et al. 2000): a
synchronous service layer, an asynchronous I/O layer, and a queue between them. §6.2's
`AudioCapture` ring buffer is already that queue.

| Concern | Thread |
|---|---|
| `TrayApp` run loop | main — a macOS status item requires it |
| `HotkeyListener` | OS event tap; posts press/release into the controller |
| `AudioCapture` | PortAudio callback thread, writing the ring buffer |
| Transcription, post-processing, injection | one worker thread, draining sessions |

**Two queues, not one** (corrected 2026-07-31, objection A6). An earlier revision
said "§6.2's `AudioCapture` ring buffer is already that queue." It is not the same
queue. There are two, with different producers, different element types and
different backpressure behaviour:

| Queue | Producer | Consumer | Holds |
|---|---|---|---|
| Audio ring buffer | PortAudio callback thread | `AudioCapture` | float32 frames |
| Session queue | event-tap thread, via `end_session()` | the worker | `DictationSession` |

Consequences that follow, and are therefore requirements rather than choices:

- `DictationController`'s methods are called from the event-tap thread and **must not
  block it**. `end_session()` hands the buffer to the worker and returns; it does not
  wait for transcription. The `-> DictationSession` return in the contract above is the
  session object, populated asynchronously.

- **Completion is signalled, not polled** (2026-07-31, objection A6). "Callers observe
  completion through the session" previously described an interface that did not
  exist: `DictationSession` had no flag, no event, and no lock, so the only available
  reading was polling a mutable dataclass across a thread boundary — the thing
  Half-Sync/Half-Async is chosen to avoid. The session carries a `threading.Event`:

  ```python
  session.completed: threading.Event   # set by the worker, last
  session.wait(timeout: float | None = None) -> bool
  ```

  The worker populates every field *before* setting the event, so any thread that
  observes it set sees a fully written session. That ordering is the synchronisation
  rule; nothing else guards the fields, and nothing else needs to.

- **Injection targets the focus at inject time, and that is a hazard the async
  handoff creates** (2026-07-31, objection A6). Because `end_session()` no longer
  blocks, sessions can overlap: a user who dictates twice quickly — or is in
  `vad_auto`, which §5.2 calls the mode most likely to misfire — can have session N's
  text land in whatever window has focus when the worker gets to it. §8's
  persist-before-inject guarantee saves the words; it does not stop them landing in
  the wrong application.

  **v1 resolution: the worker is serial and a session whose focused application
  changed between capture and injection is not injected.** It is written to history,
  and the tray reports it. Re-targeting the original window is the alternative and is
  rejected for v1 — it requires raising and focusing another app on the user's behalf,
  which is a larger intrusion than declining to type.
- `TranscriptionEngine.load()` is documented "Blocking" and runs on the worker at
  startup. `is_loaded` exists so the tray can show *transcribing* versus *not ready*.
- Nothing touching the UI is called off the main thread.
- Nothing in this table is macOS-specific except which thread the tray needs. That is
  the point: Windows changes one row.

### 6.4 Repository layout

```
amanuensis/
├── src/amanuensis/
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py                 # load_config() -> frozen AppConfig, TOML + validation
│   ├── models/
│   │   ├── session.py            # DictationSession, LatencyBreakdown
│   │   └── results.py            # InjectionResult, PermissionStatus
│   ├── controllers/
│   │   └── dictation_controller.py
│   ├── audio/
│   │   ├── capture.py            # AudioCapture
│   │   └── vad.py                # VoiceActivityDetector
│   ├── engines/
│   │   ├── base.py               # TranscriptionEngine ABC
│   │   ├── faster_whisper.py
│   │   ├── moonshine.py
│   │   └── registry.py           # backend string → class, per config
│   ├── postprocess/
│   │   ├── base.py
│   │   ├── rules.py
│   │   ├── vocabulary.py
│   │   └── llm.py
│   ├── injection/
│   │   ├── base.py
│   │   ├── macos.py
│   │   └── factory.py            # platform detection → injector;
│   │                             # raises an actionable error off macOS
│   ├── hotkey/
│   │   ├── base.py
│   │   ├── factory.py            # platform detection → listener (§7.3 floor)
│   │   └── macos.py              # renamed from listener.py, 2026-08-03
│   ├── storage/
│   │   └── history.py            # HistoryStore
│   └── ui/
│       ├── indicator.py          # the minimum §5.4 surface (Phase 2b)
│       └── tray.py               # TrayApp (Phase 4)
├── tests/
│   └── fixtures/asr/             # desk-mic corpus + reference transcripts (§2, Phase 1)
├── docs/
│   ├── PRD.md                    # this file
│   ├── HARNESS.md
│   ├── adr/                      # architecture decision records
│   └── gates/                    # phase-<n>.md — one record per gate (§9)
├── pyproject.toml
└── README.md
```

**`hotkey/listener.py` became `hotkey/macos.py`** (2026-08-03, Phase 2b), on
this section's own precedent rather than by preference. `injection/` names its
implementation after the platform because `factory.py` dispatches on platform,
and `hotkey/factory.py` was specified to mirror it "down to the error wording".
A Windows port adds `hotkey/windows.py` beside `hotkey/macos.py`; it cannot add
a second `listener.py`. The name was written before the factory existed and was
not revisited when it did.

---

## 7. Technical decisions

Each decision records the alternative rejected. If implementation shows a decision was
wrong, bring evidence to the gate and amend this section with a dated note.

### Where a decision goes

Added 2026-07-31 (choice-story #13). This project accumulated six places a decision can
land, each justified on its own and none compared to the others: §7 amended in place,
`docs/adr/`, `docs/gates/`, and the three sentinel records. The failure mode of six
unrouted surfaces is not confusion — it is *silence*: a contributor unsure where a
decision belongs writes it in none, which is the intent debt all six exist to prevent.

| Surface | Receives | Mutable? |
|---|---|---|
| **PRD §7** | Product-level decisions — anything that changes what the product *is* or what a user experiences | Yes, via dated revision-log rows |
| **`docs/adr/`** | Implementation-level decisions below PRD granularity — which quantization, which ONNX opset, which clipboard API | No; superseded by a later ADR |
| **`docs/gates/`** | Measurements and the pass/reject call at each gate, plus what the phase revealed the PRD got wrong | No; one file per gate, append-only |
| **`docs/superpowers/*`** | Review artefacts produced by sentinels, and the human dispositions on them | Dispositions written once |

The rule when they collide: **a gate record reports, an ADR decides, and §7 governs.**
Phase 1 is the first live collision — §7.2 already holds the engine decision,
`0001-engine-selection.md` is a required deliverable, and `docs/gates/phase-1.md` must
carry the measurements. So: the gate record carries the numbers, the ADR carries the
engine choice and its reasoning, and §7.2 is amended only if the outcome changes the
product-level decision rather than merely confirming it. An ADR that contradicts §7 is a
finding for the gate, not a silent override.

Note the standing tension, since it is not resolved by the table: §7's amend-in-place
convention and the ADR discipline of immutable-and-superseded (Nygard, 2011) cannot both
govern the same decision. The split above is by *granularity*, which keeps them from
meeting — but a decision that migrates from implementation-level to product-level will
sit awkwardly across both, and there is no rule for that yet.

### 7.0 Python, and what it costs

**The floor is 3.12, raised from 3.11 at the Phase 0 gate (2026-07-31).** Not a
preference: the installed numpy's type stubs use PEP 695 `type` statements, which mypy
only parses under a 3.12+ target. Under `python_version = "3.11"` the Phase 0 gate
condition `mypy --strict src/` fails on numpy's own stubs before reaching a line of this
project's code — a *named gate condition* rendered unsatisfiable for reasons unrelated
to the code being gated. 3.11 also buys nothing here: `tomllib` is 3.11+, and 3.12 is
the oldest release still receiving security fixes for the lifetime of a v1.

Recorded 2026-07-31 (choice-story #1). §8 states "Python 3.11+" as a table row between
two performance targets, and until now it was the only technical decision in this
document with no argument attached — while §7 recorded rejected alternatives for
streaming, engines, injection, VAD, post-processing, platform scope and two latency
budgets. The implementation language of a latency-critical, always-resident daemon
deserves the same treatment, especially as it is the **least reversible** commitment
here: every other §7 decision sits behind an ABC, and the runtime sits under all of them.

**The argument for.** The ASR ecosystem is Python-first — faster-whisper/CTranslate2,
ONNX Runtime for Silero, sounddevice over PortAudio, llama.cpp bindings. Choosing
Python minimises integration cost and is precisely what keeps §7.2's engine swap a
scheduling decision rather than a rewrite. A Moonshine or Parakeet evaluation is a
dependency change here and a porting project elsewhere.

**The argument against, stated honestly.** A daemon holding a real-time audio callback,
a global hotkey listener, a tray run loop and a several-hundred-millisecond inference
call is a concurrency problem, and Python is the language in which concurrency costs
the most reasoning per line. §6.3's concurrency model exists partly because of this.

**Rejected:** (a) a Rust or Go core with Python confined to inference behind FFI or a
subprocess — the line whisper.cpp and nerd-dictation sit on the other side of, both on
§13's required-reading list; (b) a Swift-native macOS app on Core ML or whisper.cpp
directly, which O6's move to macOS-only makes *more* attractive than it was, since the
portability cost has just been written off as a non-goal, and which would also dissolve
§11.3's ~1.5 GB Python distribution problem; (c) Python orchestration with the hot path
as a compiled extension.

**Note what ratifies this if nobody decides.** The pre-Phase-0 probe (§9) runs on this
runtime, and a "go" from it commits the project to Python without anyone having chosen.
That is the decision being made here rather than there.

### 7.1 Batch transcription, not streaming (v1)

Transcribe the complete buffer on hotkey release. Streaming with partial hypotheses is
what makes competitors feel instant, but it triples complexity — chunk boundary handling,
hypothesis revision, partial-text injection and retraction — and Whisper-family models are
not natively streaming.

**Rejected:** chunked streaming with rolling context. Revisit only if §9 Phase 1 shows
p95 latency missing G1 on realistic 15–30 second utterances.

**Also weighed, and deliberately not built for v1: pre-release inference**
(recorded 2026-07-30, objection O3). Run inference on buffered audio *while the
hotkey is still held*, surfacing nothing. By the time the user releases, most of
the audio is already transcribed and only the tail remains.

This matters because it attacks G1's clock directly — G1 starts at *release*
(§2), so work completed before release is free against the budget. Of the three
costs the rejection above cites, two — hypothesis revision, and partial-text
injection and retraction — arise **only because partial results are displayed**,
and nothing is displayed here. §5.1 puts injection at step 7 and release at
step 4; there is no user-visible surface in between. Only chunk boundary handling
survives, and it is real: Whisper-family models are not natively streaming, and
splitting mid-word costs accuracy.

**Why it is recorded rather than built:** batch is simpler, v1 does not need it,
and it adds a concurrency burden to a daemon whose threading model is already
unstated. **Why it is recorded at all:** §9's Phase 1 instruction on a G1 miss is
"renegotiate §7.1," and until now the only alternative §7.1 documented was full
streaming with retraction — the most expensive possible response. A project that
halts on latency should have the cheap option on the table before it reaches for
the dear one.

### 7.2 Engine: faster-whisper default, abstracted

`faster_whisper` (CTranslate2) is the default because it is fast, mature, quantizes well,
and supports CPU and CUDA from one API.

#### Tiers are measured, not named after silicon

Revised 2026-07-31 from probe evidence (`docs/gates/probe.md`). The table below
previously had four rows keyed on hardware — two CUDA, one "Apple Silicon", one
"CPU only" — and that classification was wrong in a way that mattered:

**CTranslate2 has no Metal backend.** "Apple Silicon" and "CPU only" are the same
execution path with different core counts and memory bandwidth, not two paths.
And macOS, the only v1 platform (§3), has no CUDA at all. So the old table's four
rows described two real paths, one of which has **zero v1 users**.

A tier is therefore defined by **what a machine measures**, not by what chip it
contains:

> **Tier A** — the install check measures **p50 ≤ 350 ms and p95 ≤ 700 ms** for
> transcription alone. **G1 binds and is published as a guarantee.**
>
> **Tier B** — it does not. **G1-CPU applies** (§2): the number is measured,
> published, and told to the user at install; it does not halt the project.

**The thresholds are absolute, not a restatement of G1** (revised 2026-07-31,
objection A1). The previous wording defined Tier A as "transcribes inside G1's
budget on this machine", which made §9's Phase 1 gate — *rejects if G1 is missed
on a Tier A machine* — unreachable: a machine cannot be both inside the budget by
definition and miss it, and a Tier B miss explicitly does not reject. §10's top
risk had a mitigation with no failing state, and the project's real go/no-go had
silently migrated to Phase 2b, which measures the full path and therefore *can*
fail.

The 350/700 figures are the transcribe **share** of G1's 400/800, leaving ~50 ms
p50 for post-processing and injection. That residual is thin and known to be
thin — it is what the probe measured (`docs/gates/probe.md`) — and Phase 1
confirms or moves it against real capture. A tier check compared against the full
`g1_ms` budget would classify a machine measuring 380 ms as Tier A and then ship
it a gated promise it misses in normal operation; the bias would run consistently
toward the tier that carries the guarantee.

**The install check is specified, not referred to** (2026-07-31, objection A4).
It previously said only "the same measurement the pre-Phase-0 probe ran" — a
deleted throwaway script, warmed, median of five, one clip, no VAD, transcription
only. Six things were undetermined and each moved the tier boundary. It runs:

| | |
|---|---|
| Audio | A bundled 10-second reference clip, shipped with the app. Not the user's voice — the check must be reproducible and must not require a microphone permission before first use. |
| VAD | **On**, matching runtime. Without it no candidate model passes p95 at all (§7.4). A check run in a configuration the product does not use measures nothing. |
| Warm-up | One throwaway inference first, discarded. The check measures steady state, not compile cost. |
| Runs | **Nine**, reporting p50 and p95. A single warmed median cannot see a repetition-looping excursion, and that excursion — 541 ms → 6,039 ms on the same model and sample — is this product's documented failure mode. |
| Model | The `model = "auto"` selection below, already resolved. |
| Compared against | The transcribe-share thresholds above, **not** `g1_ms`. |

Model download is **not** part of the timed check. It is a one-time install cost
(185 s measured on this machine's connection) and timing it would measure the
network.

The tier is decided **once, at install**, and recorded. It is not re-derived per
session — a machine that is momentarily busy must not flip tiers, and a machine
near the boundary must not oscillate. `manu status` reports the recorded tier;
re-running the install check is how it changes.

The tier is a **recorded fact about a machine**, not a gate condition. Nothing in
§9 rejects on it.

This supersedes the accelerated-versus-CPU-only split from objection O1. **O1's
reasoning survives unchanged** — a slow machine gets an honest published number
rather than a halt, and shipping the offline-constrained §4 user a slower tool
beats shipping them nothing. What changes is the boundary: it moves from *what
chip* to *what it measured*, because the probe showed the chip does not determine
the answer.

#### `model = "auto"`

Starting guesses, **verified at install** by the tier check above. Where a row is
marked *measured*, that number is real; the rest are still model-card estimates
and are labelled so.

| Hardware | Model | 10 s transcribe | Basis |
|---|---|---|---|
| CUDA, ≥8 GB VRAM | `large-v3-turbo`, float16 | — | estimate, **unmeasured**, and **unimplementable as written** — see below |
| CUDA, <8 GB VRAM | `distil-large-v3`, int8_float16 | — | estimate, **unmeasured**, and **unimplementable as written** |
| macOS (all Macs) | **`tiny.en`, int8, VAD on** | **328 ms p50 / 420 ms p95** | *measured*, M3 Max, 6-sample corpus |

**The two CUDA rows split on a quantity nothing here can measure** (added
2026-08-01, Phase 1 finding 7). They key on VRAM, and neither CTranslate2 nor
faster-whisper exposes it; the PRD names no other source. Both rows are already
labelled unmeasured estimates and §3 makes macOS the only v1 platform, so this
is a specification for zero users — but it cannot be implemented as written,
and `engines/faster_whisper.py` collapses it to a single CUDA entry rather than
inventing a VRAM probe. Resolve the split, or delete one row, before any phase
claims CUDA support.

**`tiny.en` replaced `base.en` on 2026-07-31 (objection A3), and VAD is part of
the selection, not a separate setting.** The `base.en` row carried a measured
352 ms — but measured *without VAD*, on one clip. Re-measured over the six-sample
corpus with VAD, `base.en` is 541 ms p50, and without VAD it reaches 6,039 ms.
`tiny.en` + VAD is the only candidate meeting both halves of G1. The row was
also self-contradictory with §8, whose cold-start figure already assumed
`tiny.en`.

The two macOS rows are collapsed into one. §7.2 established above that "Apple
Silicon" and "CPU only" are the same execution path, which left "Apple Silicon /
CPU" versus "Slower CPU" as an undefined boundary the install check would have
had to resolve before it could pick a model to time. The install check decides
the *tier*; the table decides the *model*, and on macOS there is one.

`distil-large-v3` — the original Apple Silicon selection — measured **2,412 ms**,
six times over budget. That row was a model-card guess and it was wrong by
roughly 7×.

**This table still selects on latency alone, and `tiny.en` has the worst accuracy
of the candidates.** All five candidates are statistically indistinguishable on a
six-sample corpus — every Wilson interval overlaps — so there is no evidence-based
model selection yet, only an evidence-based *elimination* of everything that
misses G1. **Do not finalise the model choice until the Phase 1 corpus exists**
(objection O7). Doing so would repeat, on the accuracy axis, exactly the mistake
this revision is correcting on the latency axis — twice over now.

**WER in this document is macro-average** — the unweighted mean of per-sample
rates (2026-07-31, objection A3). The frozen fixture's mean is **19.62%**. A
micro-average figure of 14.8% was also in circulation; the two differ by a third
relative, and the open question of whether cleanup compensates for weaker ASR is
answered differently depending on which is used. **The 14.8% figure is
withdrawn.** Macro is chosen because each sample is one dictation event and the
product's user experiences them one at a time; a word-weighted mean lets one long
sample dominate six.

#### `cpu_threads` is load-bearing and was never specified

Added 2026-07-31. CTranslate2 defaults to **4 threads**. On a 14-core M3 Max that
default measured 4,413 ms; setting `cpu_threads` to the performance-core count
took the identical model to 2,412 ms. **A 1.8× factor**, from a parameter this
PRD did not mention.

The first run of the pre-Phase-0 probe returned **NO-GO on that default**. The
project's top risk (§10) would have fired on a library default rather than on
physics.

**The 1.8× does not transfer to the model this table selects** (revised
2026-08-01, Phase 1 finding 4). Those figures are `distil-large-v3` — the model
this same revision *rejected*, by a factor of roughly 7×. Swept on `tiny.en`
over the Phase 1 corpus, 54 observations per point:

| `cpu_threads` | ASR p50 | vs `auto` (10) |
|---|---|---|
| 2 | 365.9 ms | 1.36× |
| 4 | 273.4 ms | **1.02×** |
| 6 | 261.1 ms | 0.97× |
| 8 | **235.9 ms** | **0.88×** |
| 10 (`auto`) | 289.1 ms | 1.00× |
| 14 | 559.1 ms | 2.08× |

Confirmed on an independent run at 15 runs per sample: 8 threads at 0.83× of 10.

Two things follow, and they point opposite ways.

**The efficiency-core exclusion is confirmed, and is worth more than was
claimed for it.** Handing the decoder all 14 cores costs **2.08×** — a larger
penalty than the library default ever was. That half of the rule is right.

**The library-default penalty is not real for `tiny.en`.** At 4 threads the
model is within noise of the performance-core count, and the measured optimum
is around 6–8 — *below* it. A model this small does not parallelise across ten
threads well enough to pay the coordination.

`cpu_threads = "auto"` is **unchanged** and still resolves to the
performance-core count. Tuning it to 8 would be tuning to n=1 hardware, which
is exactly what the exclusion-rule caveat below warns against, and 10 clears
Tier A with 100 ms of G1 headroom. What changes is the argument: the rule is
retained for the E-core exclusion it encodes, **not** for the library-default
penalty it was originally argued from. Anyone re-deriving it from the 4,413 ms
figure is re-deriving it from a rejected model.

`cpu_threads = "auto"` resolves to the **performance-core count**, not the total
core count and emphatically not the library default. Efficiency cores are
deliberately excluded — scheduling inference across heterogeneous cores typically
costs more than it returns.

**Resolution branches on whether the facility exists, not on which OS is running**
(2026-07-31, objection A8):

1. Query `hw.perflevel0.physicalcpu`. If it resolves, use it, clamped to the total
   core count.
2. If it does not — an Intel Mac has no `perflevel` keys, and a sandbox may refuse
   the call — fall back to **the total core count**.

The earlier wording branched on platform ("on macOS that is `sysctl ...`;
elsewhere, physical cores"), and §3 makes macOS the only v1 platform, so
"elsewhere" covered no shipping configuration. A homogeneous Mac has no
`perflevel0` to query and therefore fell into the branch that did not apply — with
the most likely implementation outcome being CTranslate2's default of **4**, the
exact value whose first probe run returned NO-GO. A defaulting rule whose
undefined case lands on the known-bad value is worth the sentence that closes it.

**The exclusion rule is generalised from n=1 and is labelled so.** It was measured
once, on a 10P/4E machine where discarding the efficiency cores costs 29% of the
core count. On a 4P/4E machine it discards half, and per §4 that machine is
disproportionately a Tier B user's. The value was not tuned beyond "match the
performance cores" and is not claimed optimal; **Phase 1 sweeps it**, and the sweep
covers at least one non-10P topology or the rule stays n=1 with a wider blast
radius.

Note `device = "mps"` was removed from §5.3's options. CTranslate2 has no Metal
backend, so it was never a reachable value.

**Moonshine** is a real alternative on CPU for short utterances and is the reason
`TranscriptionEngine` is an ABC rather than a module of functions. Benchmark it in
Phase 1 against `base.en` — not `small.en`, which the probe showed is 2.2× over
budget — and record the result in an ADR.

**Benchmarked and declined, 2026-08-01** (`docs/adr/0001-engine-selection.md`).
`moonshine/tiny` is the fastest candidate measured — 163 ms p50 against
`tiny.en`'s 278 ms — and every WER pair involving `tiny.en` is statistically
indistinguishable on the Phase 1 corpus, so the rate could not decide it. The
**error breakdown** did: Moonshine deletes 12–14 words where the faster-whisper
models delete 2–7. A substituted word is wrong on screen and gets corrected; a
deleted word is silent data loss in text the user has not read yet, which is
the failure §8 exists to refuse. That is a claim about failure mode rather than
rate, so the interval overlap does not touch it. Reconsider if G1 headroom
becomes binding once §7.5 and §7.3 land — it buys 115 ms p50, more than the
~50 ms this section budgeted for both.

### 7.3 Injection: clipboard paste, with a keystroke fallback

Synthesizing keystrokes character-by-character is too slow for a 300-character paragraph
and breaks in applications with input debouncing. Clipboard write + synthetic paste is
near-instant and format-safe.

**The cost, stated plainly:** it clobbers the user's clipboard. Mitigate by saving and
restoring, but restoration races with clipboard manager apps — the manager may capture the
transcript before restore lands. This is a known, unavoidable leak of the strategy, and it
must be documented in the README rather than papered over.

`strategy = "keystroke"` exists for users who cannot accept that.

**`keystroke` has a third cost, and it is silent** (measured 2026-08-02, Phase
2a finding 3). The two costs stated above are speed and fragility. The one that
matters more is that **synthetic keystrokes are subject to the target
application's text substitution**, exactly as real ones are. Injected into
TextEdit:

```
sent    : don't use --dashes... "quoted" and i said so
landed  : don’t use —dashes… “quoted” and I said so
```

Five substitutions in one sentence — smart quotes twice, an em dash, an
ellipsis, and an autocapitalised "i". **The identical string pasted arrives
byte-identical.**

Two consequences. It lands on §4's privacy-motivated primary user, who is
precisely the person this strategy is offered to. And it cuts against §1: a
tool that resolves your self-corrections and then rewrites your punctuation has
moved the problem rather than solved it.

Nothing in Amanuensis can reach into another application's substitution
settings, so this cannot be fixed here — only said. It is surfaced when
`strategy = "keystroke"` is in use, symmetrically with the clipboard-manager
warning below, and belongs in the README beside the clipboard cost.

This also disqualifies `keystroke` as a silent *automatic* fallback when
clipboard injection fails: falling back would trade a visible failure for an
invisible corruption. Any per-app override (§10) must be a stated choice.

**Transcript egress is a privacy surface, not a hygiene annoyance** (resolved
2026-07-30, objection O12). The framing above — and §10's — describes the
clipboard-manager capture as a *race*, which understates it in three ways:

- Capturing the clipboard is the **normal operation** of a clipboard manager,
  not a timing artefact. A manager that missed the transcript would be broken.
  `restore_delay_ms` governs only whether the user's *previous* contents come
  back; it has no bearing on whether the transcript was recorded in transit.
- Several widely used managers on the target platform offer **cross-device
  sync**. For those users a transcript leaves the machine as a direct
  consequence of the default configuration.
- §1's promise is scoped to *audio* ("no audio leaving the machine") and is
  technically preserved. No reader parses it that way, and the transcript is
  the artefact the user cares about keeping private.

Clipboard remains the default — the latency argument above still holds, and
`keystroke` is slower and more failure-prone precisely for the §4 secondary
user who can least afford either. The exposure is handled by **making it
visible rather than silent**:

1. At daemon start, detect known clipboard managers on the platform.
2. When one is present, surface the exposure in the tray as a persistent
   state, following the §5.4 precedent that a privacy-relevant condition must
   be visible without opening a menu.
3. Config key `[injection] warn_on_clipboard_manager = true` (§5.3) to silence
   it for users who have read the README and accepted the trade.

The detection list will be incomplete and must not be presented as
comprehensive — absence of a warning means "no known manager detected", never
"no manager present". Say that in the README.

**Measured 2026-08-02, and the argument above is confirmed** (Phase 2a gate).
Against Maccy 2.7.0, with a positive control proving the instrument could see an
ordinary copy:

| | captured by the manager |
|---|---|
| An ordinary copy (control) | yes |
| **Transcript, default config — restore on, `restore_delay_ms = 150`** | **yes** |
| Transcript, `restore_clipboard = false` | yes |

A 150 ms window is not a mitigation. The transcript of every dictation is
recorded by a clipboard manager running on default settings, which is what this
section already said and now no longer has to assert.

Worth recording how nearly this went the other way: the first run of that
measurement reported *not captured*, because it read the manager's store before
the manager had flushed. It was caught only because the positive control was
added afterwards and came back captured too. Without the control, this gate
would have published a false all-clear on the most-argued privacy surface in
the document.

**The tray indicator is Phase 4; the obligation is not** (Phase 2a finding 4).
§9's Phase 2a gate asks that the indicator "fire correctly" while `TrayApp` is
built two phases later. Phase 2b already carries the resolution — "a visible
indicator, not the full `TrayApp`" — and Phase 2a takes the same shape: the
exposure is surfaced before the microphone opens, so the user learns of it while
they can still decline. Phase 4 renders the same state in the tray. Nothing is
printed when no known manager is found, and **never an all-clear**, for the
reason stated above.

**This is also a G3 verification gap, not only a risk.** G3's method is packet
capture on this app; the egress occurs in another process, so the headline
privacy claim would verify green while the leak is live. §2's G3 row now scopes
the claim accordingly.

**The obligation to say so is assigned to the Phase 4 gate** (2026-07-31,
choice-story #11) — it previously belonged to no gate at all. Phase 4's G3
verification must state explicitly, in the gate record and in the README's privacy
section, that packet capture covers this process only, and that transcripts transit
the system clipboard by default where another process may capture them. An
unqualified "G3 verified" in a gate record is itself the failure this objection
describes.

**Platform: macOS only for v1** (resolved 2026-07-30, objection O6; §3, §11.1). The
original reasoning stands — macOS's permissions model (Accessibility + Input
Monitoring) is the most restrictive and surfaces the hardest problems earliest — but
"first" implied a second platform that no phase in §9 ever scheduled. Windows is
**post-v1 intent** and Linux a plain non-goal (§3, amended 2026-07-31); neither ships
code in v1.

`TextInjector` remains an ABC, so a later port stays a scheduling decision rather
than an architectural one. That claim covers **injection only**. `HotkeyListener`, the
tray, the IPC transport and the config paths are each platform-shaped, and the ABC does
nothing for them.

**Portability floor** (added 2026-07-31). Windows is post-v1 intent (§3), so v1 builds
no Windows code — but four things must not become macOS-specific *by accident*, because
each is cheap now and expensive after Phase 2b:

1. **The threading model is named, not implied** (§6.3). A macOS status item
   conventionally owns the process main thread; Windows has no equivalent constraint.
   A model that is never written down gets re-derived rather than ported, and it would
   be re-derived for the one class §6.3 says owns the loop. This is the item that would
   actually corner the project.
2. **No hardcoded XDG paths.** §5.3 and §5.5 originally named `~/.config/amanuensis/`
   and `~/.local/share/amanuensis/` as the *macOS* locations, which is where `platformdirs`
   puts them on Unix and not on macOS — this section stated the rule and then wrote down
   the paths the rule forbids. Corrected 2026-07-31 at the Phase 0 gate. Resolve them
   through
   `platformdirs` from Phase 0. Changing this after users have config files on disk is
   a migration, not an edit.
3. **The IPC transport is abstracted** (§6.1). `manu toggle` uses a unix socket on
   macOS; that is a POSIX assumption and must not appear in the CLI contract as though
   it were the interface.
4. **`HotkeyListener` gets a `factory.py`**, mirroring `injection/factory.py`. §6.4
   declares `hotkey/base.py` while §6.2 and §6.3 never contract it — the one ABC the
   §6.3 "real chance we replace the implementation" test was never applied to.

None of the four builds Windows support. All four are the difference between a port
and a rewrite.

### 7.4 VAD: Silero, optional

Silero VAD via ONNX runtime. Small, fast, no GPU. Used for `vad_auto` mode and to trim
leading/trailing silence before transcription.

**Trimming is the dominant latency lever, not a free bonus** (revised 2026-07-31 from
probe evidence; slicing record S5). The original wording called it "a free latency win",
which understated it. Whisper's encoder always processes a **padded 30-second window**;
only the decoder scales with output length. Measured: `base.en` takes 352 ms for a
10-second utterance and 517 ms for a 26-second one — 1.5×, not 2.6×.

The consequence is that **a 2-second utterance costs nearly what a 25-second one does**.
Most real dictation is short, so without trimming the common case pays close to the
worst case on every single utterance.

**Therefore trimming moves to Phase 1**, from Phase 3. It has to land before the phase
that measures latency, because it changes what that measurement means — Phase 1 without
trimming measures a padded window rather than the product.

### 7.5 Post-processing: rules first, LLM behind a flag

The genuine gap between raw Whisper output and a polished dictation product is
post-processing: punctuation, capitalization, spoken commands ("new paragraph"), filler
removal.

**Filler removal is already done upstream, measured 2026-08-02**
(`docs/gates/phase5-disfluency.md`). Whisper emits no filled pauses at all —
zero in 403 words of spontaneous speech, across three model sizes, with three
verified by ear in the audio of one take. One of this list's four items is
therefore not a gap on this engine. `[postprocess] strip_fillers` is kept
because a future engine may be verbatim, but on Whisper output it operates on
nothing and its "off by default, it is lossy" comment describes a risk that does
not arise.

The other three survive, and two now have a frequency rather than an assumption:
over the same ten takes, **7 of 10** transcripts ended with no sentence-final
punctuation and roughly ten spurious mid-sentence capitals appeared. Both are
rule-shaped — which is the argument the next paragraph was already making.

Start with deterministic rules. They are debuggable, instant, and cover most of the value.

A local LLM pass (Qwen3-0.6B or similar via llama.cpp) can do what rules cannot — reflowing
rambling speech into clean prose. It also adds 200–500 ms, which directly threatens G1.
Therefore: **off by default, hard latency ceiling, and it is skipped rather than queued
when it exceeds budget.** A dictation tool that sometimes takes 900 ms is worse than one
that is consistently 350 ms and slightly rougher.

**The budget, stated honestly** (resolved 2026-07-30, objection O11). The instinct
above is right; the numbers as originally written did not implement it.

- **G1 does not apply when this pass is enabled.** §2's budgets assume
  `chain = ["rules"]`. A base pipeline at the 400 ms p50 target plus a 300 ms
  ceiling is ~700 ms. Pretending otherwise made G1 unsatisfiable exactly when the
  feature was on.
- **Phase 5 carries its own budget:** **p50 ≤ 700 ms, p95 ≤ 1100 ms** with the pass
  enabled, on the same Tier A and measurement basis as G1. The
  README states both numbers; the user choosing to enable this is choosing the
  second one.
- **`max_latency_ms` is a cancellation deadline, not a predictive check.** You
  cannot know a pass's cost before paying it, so "skip" means *abandon in flight
  at the deadline and inject the pre-LLM text*. There is no predictor and none is
  specified.
- **The skip path costs the full ceiling and produces nothing.** A cancelled pass
  has already spent 300 ms. That is the price of the mechanism, and it is worth
  naming rather than discovering: the worst case is strictly worse than either not
  running the pass or letting it finish. It is still the right trade — a bounded
  overrun beats an unbounded one — but the bound is on the overrun, not a saving.

**Unresolved, and left that way deliberately** (choice-story #9, 2026-07-31). The
700/1100 ms budget above is *arithmetic* — G1 plus `max_latency_ms`, twice. It states
what the mechanism costs, not what a user will tolerate, and those coincide only by
luck. This section's own argument names the tolerance directly ("a dictation tool that
sometimes takes 900 ms is worse than one that is consistently 350 ms and slightly
rougher") and the p95 budget of 1100 ms **permits a latency this section rejects**.

Both statements are in this section and they contradict. The gate also cannot fail the
budget by construction: base-plus-ceiling *is* the worst case, so any run respecting the
deadline is inside it.

This is not resolved now because the evidence to decide — a real Phase 3 edit rate
showing what rules could not fix — does not exist yet. **Whoever revives Phase 5 sets
the budget from tolerance first and derives `max_latency_ms` from it, not the reverse.**
If §7.5's own 900 ms line is taken as binding, the implied ceiling is nearer 100–200 ms,
and the honest conclusion may be that the pass does not fit. That is worth knowing
before building it rather than after.

**Amended 2026-07-31 (objection A2).** This paragraph previously read "This is not
resolved now because Phase 5 is deferred (§9) and nobody is building against it." Both
clauses were false when written: §9 had un-deferred the phase the same day, and four
experiments were being run against exactly this budget. Phase 5's real state is
**unresolved and corpus-blocked** (§9), and the 700 ms figure the experiments measured
against was already missed by 3× — which makes deriving it from tolerance urgent rather
than deferrable. A section that justifies leaving a number unresolved on the grounds
that nobody depends on it must be re-checked whenever the phase moves, or the
justification outlives the fact.

### 7.6 Security posture

Standard Firebase/cloud rules mostly do not apply — there is no backend, no secrets, no
auth. What does apply:

- No telemetry, no crash reporting, no update check that phones home. If an update check
  is ever added it is opt-in and documented.
- Model weights are downloaded once at install over HTTPS with checksum verification, from
  a pinned revision. Never at runtime.
- History DB is created `0600`. Audio storage defaults off.
- **Both artefacts of an utterance, stated together** (choice-story #7). They are
  handled asymmetrically and the asymmetry is deliberate, so it belongs in one place
  rather than split across §5.3 and §8:
  - **Audio** is never written unless `store_audio` is explicitly enabled. It is the
    higher-sensitivity artefact and nothing in the product requires retaining it.
  - **The transcript** is written before injection, unconditionally, for every session
    that reaches injection — that is §8's crash guarantee and it is not user-disableable.
    `retain = false` makes the write transient (temp file, unlinked after success,
    §5.5); it does not make it optional.
  - Sessions that never reach injection leave neither artefact.

  The honest note, from objection O10: a transcript of what someone dictated into a
  password manager is not obviously less sensitive than a recording of it. The
  asymmetry is justified by durability, not by the transcript being safe.
- The daemon holds microphone access permanently. Recording state must be unambiguous in
  the UI at all times (§5.4).
- No `eval`/`exec` of anything derived from transcripts. Transcripts are injected as text
  and never interpreted as commands in v1.

**Surfacing versus preventing — the stated doctrine** (added 2026-07-31,
choice-story #11). Two decisions in this PRD resolved a privacy exposure by making it
visible rather than by removing it: §5.4's recording indicator, and §7.3's
clipboard-manager warning. §7.3 reasons from §5.4 as precedent, which is how a doctrine
forms without anyone deciding to adopt one. Stating it means the third case is judged
against a policy rather than inheriting a shape:

> **Privacy-relevant conditions are surfaced rather than prevented, unless prevention is
> free or the user has no viable action.**

The second clause is the part that matters, and it is where the two existing cases
differ. At §5.4 the user's action is free — stop talking. At §7.3 the only remedy is
`keystroke`, which §7.3 itself argues the §4 secondary user should not take. Notice
without a viable alternative shifts responsibility rather than reducing risk, so §7.3
sits at the edge of this doctrine rather than comfortably inside it. If a transient or
concealed clipboard type proves workable on macOS, prevention becomes cheap and this
doctrine says to prefer it.

---

## 8. Non-functional requirements

| Requirement | Target |
|---|---|
| Idle CPU | < 1% |
| Idle RSS | < 1.5 GB with model resident (GPU). **Revisit**: Phase 5 adds a second resident model (~1.8 GB on disk for the 4-bit 3B), so this figure predates the design it now has to cover. |
| Cold daemon start to ready | < 15 s — **measured 3.43 s** with `tiny.en` + `Llama-3.2-3B-4bit` both loaded and warmed (2026-07-31, `docs/gates/phase5-feasibility.md`) |
| Recovery from mic disconnect | Automatic, no restart |
| Crash behavior | Never lose a transcript — write to history before injection. Unconditional; not affected by `[history] retain` (§5.5) |
| Python | **3.12+** (raised from 3.11 at the Phase 0 gate — see §7.0) |

Note the crash-order requirement: persist first, inject second. If injection fails the user
can still recover their words.

This guarantee is **not** conditional on the `[history] retain` config key. That key
governs *retention* — when it is false the row is written before injection and deleted
after injection succeeds (§5.5, objection O10). A guarantee whose mechanism a user can
switch off without being told is not a guarantee.

---

## 9. Phases

Each phase ends at an approval gate. **Stop at the gate.**

**Every gate states what rejects it, and every gate leaves a record**
(resolved 2026-07-30, objection O9 and choice-story #9). Previously three of six
gates named an activity — "report where it fails", "report edit rate" — with no
condition attached, so they could not fail on their own terms and reduced to
discretionary approval by the person whose work was being gated. Each gate below
now carries a **Rejects if** line.

Each gate also writes `docs/gates/phase-<n>.md`: the date, the measurements, the
pass/reject decision, and §9's standing question — what this phase revealed that
the PRD got wrong. Without it, Phase 1's measured latencies exist only in a
conversation, and every later phase implicitly regresses against a baseline that
was never written down.

**And a closed gate is recorded here, in a blockquote under its phase** (convention
established 2026-07-31 at the Phase 0 gate). The `docs/gates/` record stays
authoritative and holds the full evidence; the blockquote carries the verdict, the
date, and the answer to the standing question. The reason for duplicating that much
and no more: §9 is the section a reader consults to know what is built, and a phase
plan that reads identically before and after the phase ran makes them open four
files to find out. Two gates had already closed before anyone noticed this document
could not say so.

### Probe — Is G1 reachable at all? (before Phase 0)

Added 2026-07-30 (objection O4). A throwaway script — no package, no ABCs, no
config, deliberately not to §6.4 — that loads the `model = "auto"` resolution for
this hardware (§7.2), transcribes a pre-recorded 10-second WAV, and prints the
elapsed transcribe time. Delete it afterwards; it is not a deliverable.

**Gate:** Does transcription complete in a few hundred milliseconds, or in several
seconds? An order of magnitude is all this needs to answer.

**Rejects if:** transcription of a 10-second utterance takes longer than the
**G1-CPU p50 bar in §2** on the machine the probe runs on. A machine that cannot beat
the floor set for the *slowest* tier this product ships is not a slow result — it is a
broken setup, and no amount of Phase 0 scaffolding fixes it.

Reworded 2026-07-31 (objection A9). It previously conditioned on "*accelerated*
hardware", a category §7.2 retired the same day: CTranslate2 has no Metal backend and
macOS has no CUDA, so on the only v1 platform the class had no members and the reject
line was unevaluable. The probe had already run, so the cost here is retrospective —
but a reject condition that silently stops being checkable when a definition moves is
the failure worth naming, not the one instance of it.

**Writes `docs/gates/probe.md` before the script is deleted** (choice-story #12): the
date, the hardware, the model `auto` resolved to, the input file, the measured
transcribe time, and the verdict — plus the standing caveat that this number skips
capture, model residency, post-processing and injection and is therefore a **floor**.
Delete the code, keep the answer. This produces the earliest kill decision in the
project; O9 required every other gate to leave a record precisely because a number that
lives only in a conversation cannot be compared against later, and this is the number
with the least surrounding context to reconstruct it from.

The reasoning: §10 rates G1-unachievability as the top risk and offers the Phase 1
gate as the mitigation, but that gate sits *after* the entire Phase 0 scaffold and
most of Phase 1. A gate is a mitigation only when it can change the decision before
the cost is incurred. This probe costs about an hour and makes the price of a "no"
an hour rather than a scaffold.

It does **not** replace the Phase 1 gate. This number is optimistic by
construction — it skips real capture, model residency, post-processing and
injection. It is a floor, and a floor is enough to kill the project early. If the
probe is ambiguous, treat it as a pass and let Phase 1 decide.

> **CLOSED 2026-07-31 — GO.** Record: `docs/gates/probe.md`. Script deleted, as
> instructed.
>
> **The first run returned NO-GO at 4,413 ms, and it was wrong.** CTranslate2 was
> defaulting to 4 threads on a 14-core machine; setting `cpu_threads` to the
> performance-core count took the identical model to 2,412 ms. The project's top
> risk would have fired on an unchecked library default rather than on physics.
> Checking defaults before accepting a verdict is what saved it, and §7.2's
> `cpu_threads` block exists because of this.
>
> It also found §7.2's model table wrong by roughly 7×: `distil-large-v3`, then the
> Apple Silicon selection, measured 2,412 ms against a 400 ms budget, because
> **CTranslate2 has no Metal backend** and "Apple Silicon" was a CPU tier named
> after an accelerator. Both the table and the tier scheme were rebuilt from
> measurement on the same day.
>
> The verdict recorded here is a **floor**, as this section says it must be — and
> Phase 1's corpus later showed how much of one. A p50 of 352 ms from one clean
> clip became a p95 of 5,810 ms over six real samples, 14× worse and the opposite
> decision, because the decoder repetition-loops on silence. Enabling VAD took the
> same model from 6,039 ms to 541 ms. Any latency figure entering this document
> now carries p50 **and** p95, or is labelled a floor.

### Phase 0 — Scaffolding
Repo structure per §6.4, `pyproject.toml`, ruff + black + mypy strict, `AppConfig` with TOML
load and validation, CLI skeleton, all ABCs defined with no implementations.

Also here, from §7.3's portability floor: config and history paths resolved through
`platformdirs` rather than hardcoded, and `hotkey/factory.py` alongside
`injection/factory.py`. The concurrency model in §6.3 is now specified, so the ABC
signatures are written against it rather than against an assumption.

**Gate:** `manu --help` runs, `mypy --strict src/` is clean, config loads and rejects a
malformed file with a useful error.

**Rejects if:** any of the three fails, a config/history path is hardcoded rather
than resolved through `platformdirs`, or `config.py` exposes a module-level instance or
a `.get()` accessor (§6.3). All are mechanical; there is no judgment here.

> **CLOSED 2026-07-31 — PASS.** Record: `docs/gates/phase-0.md`.
>
> All six conditions met: `manu --help` exits 0, `mypy --strict src/` is clean across
> 18 files, config loads and rejects a malformed file by naming the key and its valid
> alternatives, no path is hardcoded, and `config.py` exposes neither a module-level
> instance nor a `.get()`. 57 tests; ruff and black clean.
>
> **What it revealed the PRD got wrong**, per this section's standing question:
> §5.3, §5.5 and §5.6 named `~/.config/amanuensis/` and `~/.local/share/amanuensis/`
> as the *macOS* locations while §7.3's floor instructed the implementation to use
> `platformdirs`, which returns neither there — the floor stated the rule and three
> sections wrote down the paths it forbids. And the Python floor is **3.12**, not
> 3.11: numpy's stubs use PEP 695 `type` statements that mypy cannot parse under a
> 3.11 target, which made the gate condition `mypy --strict src/` unsatisfiable for
> reasons unrelated to the code being gated. Both applied; see the revision log.
>
> Four further findings are recorded but not amended, because each is a decision
> rather than a defect: `[postprocess] chain` lists two processors in §5.3 and three
> in §6.2; `chain` and `llm.enabled` are two switches for one thing, with the two
> incoherent combinations now rejected at load time rather than silently resolved;
> `$AMANUENSIS_CONFIG_DIR` and `$AMANUENSIS_DATA_DIR` are surface no section
> authorises — a second case §5.3's key-per-decision rule structurally cannot reach,
> after the bounded exception added the same day; and `cpu_threads = "auto"` is
> resolved at *use*, not at load, so one config file cannot produce two different
> `AppConfig` values on two machines.
>
> **Adversarial review ran against this phase and found a defect in it.** Objection
> A6: `DictationSession` implemented §6.3's "callers observe completion through the
> session" faithfully, and that contract described an interface that did not exist —
> no flag, no event, no lock. Fixed here for one field, one method and four tests,
> because nothing had been built on it yet. This is the argument for reviewing before
> the scaffold hardens, made concrete: after Phase 2b it would have been a change to
> the threading model of a running daemon.
>
> **Not built, deliberately:** `controllers/`, `audio/`, `storage/`, `ui/` and every
> concrete implementation. §6.4 is the finished layout, not the Phase 0 deliverable.

### Phase 1 — Prove the ASR path
`AudioCapture`, `FasterWhisperEngine`, warm-up, `LatencyBreakdown`, VAD silence trimming
(§7.4), the install-time tier check (§7.2). No hotkey, no injection.
`manu transcribe --seconds 10` records from the mic and prints the transcript plus timings.

`manu install` too (added 2026-08-01, Phase 1 finding 6). §7.2 specifies the
install-time check in six-parameter detail and says "re-running the install check
is how it changes" — presuming a command that appeared nowhere in this document.
It downloads the weights once and runs the timed check. Both verbs break Phase 0's
claim that §6.1 fixes the verb set at four, and that claim survives for the reason
it was made: neither talks to a daemon. `transcribe` is a one-shot diagnostic;
`install` runs before a daemon exists.

**Gate:** Report measured latency on your actual hardware against G1. Benchmark
faster-whisper vs. Moonshine and write `docs/adr/0001-engine-selection.md`. **If G1 is
missed here, stop and renegotiate §7.1 before continuing** — no later phase makes this faster.

Scope of that stop (objection O1, revised 2026-07-31): G1 binds on **Tier A only** —
machines that measure inside the budget at the install-time check (§7.2). A miss there
stops the project. Also measure and report **Tier B** — it is not gated, but it ships
with a published number (§2, §10), and "not gated" is not "unmeasured." When renegotiating §7.1, weigh **pre-release inference** before full
streaming; §7.1 now records both (objection O3).

Benchmark methodology (objection O7): record a small desk-mic corpus with reference
transcripts, and report WER per candidate engine. That figure is for **relative**
comparison only — the corpus is too small to validate an absolute threshold, and it is
not a G2 measurement (§2).

**The corpus is built BEFORE the engine is chosen** (2026-07-31). The pre-Phase-0 probe
selected `base.en` on latency alone, from one clip by one speaker in one room. That is
sufficient to prove G1 is reachable and **insufficient to pick a model** — accuracy is
still unmeasured, which is the whole of objection O7. Choosing on the probe's evidence
would repeat, on the accuracy axis, the mistake §7.2 just corrected on the latency axis.

Corpus shape: five to ten samples on the microphone actually used for dictation, varied
deliberately — a code-heavy sentence, one dense with proper nouns, one at a natural
rambling pace, one deliberately fast, one with background noise. Reference transcripts
(`.txt`) are committed; the audio is **not** (see `.gitignore` — a voice recording in a
public repository cannot be unpublished).

Phase 1 also carries, from the probe's findings: **VAD silence trimming** (§7.4, moved
here from Phase 3 — it changes what this gate measures), the **`cpu_threads` default**
(§7.2), and the **install-time tier check** that decides Tier A versus Tier B (§7.2).
Report the tier this machine lands in.

**Rejects if:** G1 is missed **on the machine this phase is built on**, whatever tier
that machine recorded at install.

Revised 2026-07-31 (objection A1). The line previously read "G1 is missed on a Tier A
machine", which could not fire: §7.2 defined Tier A by the same predicate this gate
tests. It now gates unconditionally on a real machine and reports the tier separately —
so a developer working on a Tier B machine still faces a stop, where before the build
would have proceeded with **no gated tier at all**, which is verbatim the outcome the
tier redefinition was made to prevent. Tier A/B is measured and published here; it is
not a condition of this gate.

**Also at this gate — first G3 verification** (added 2026-07-30, objection O5).
Run the daemon under packet capture through a full transcribe cycle and report
whether any network traffic occurred. This is the earliest point a model loads, and
therefore the earliest point a Hugging Face cache-miss fetch would fire. G3 is the
goal that carries the product premise (§1) and until now no gate verified it.
Confirm the model resolves from a local path, not a repository ID.

> **CLOSED 2026-08-01 — PASS.** Record: `docs/gates/phase-1.md`. Decision:
> `docs/adr/0001-engine-selection.md`.
>
> G1 met on the machine this phase was built on, measured through the product's
> own classes rather than a throwaway script: ASR **p50 299.7 ms / p95 373.3 ms**
> over 54 observations, against a 400/800 ms budget — 100 ms of p50 headroom for
> post-processing and injection, twice what §7.2 budgeted. The corpus averages
> 18.6 s per sample against a goal defined at 10 s, which biases the figure
> against the product.
>
> **Tier A**, recorded: p50 258.4 ms / p95 385.6 ms on the install check.
> "Tier B's number" was not fabricated — this machine does not miss 350/700, so
> what is reported instead is the same measurement under a pinned
> `cpu_threads = 4` (277.8 / 344.6 ms), labelled a simulated constraint rather
> than a measured machine. A real Tier B number needs a real Tier B machine.
>
> **G3 verified for the first time.** Zero sockets and zero bytes for a full
> transcribe cycle, against a positive control that opened one socket and moved
> 866 bytes — the control is what makes the null result mean anything. The model
> resolves to a local absolute directory, and with a cold cache `manu transcribe`
> refuses and names `manu install` rather than downloading.
>
> **ADR 0001**: faster-whisper `tiny.en`. Moonshine benchmarked as required and
> declined on its error breakdown, not its rate.
>
> Ten findings; four amended this document (§5.3 twice, §6.3, §7.2 twice, §9).
> The largest: §7.2's 1.8× `cpu_threads` penalty was measured on a model §7.2
> rejected and does not hold for the model it selects.

### Phase 2a — Text at the cursor, no hotkey yet

Split from the original Phase 2 on 2026-07-31 (slicing record S2/S3). On macOS these
are **two distinct permissions** — Accessibility for injection, Input Monitoring for
global key capture — with two failure modes and two remediation messages. Adjudicating
them together means a failure in either is diagnosed as a failure of "Phase 2".

`MacOSInjector` (clipboard strategy with save/restore, `keystroke` fallback),
non-destructive permission check with copy-pasteable remediation, clipboard-manager
detection and the §5.4 tray exposure indicator. Triggered from the CLI —
`manu transcribe --inject` — not from a hotkey.

**Also here: the §8 persist-before-inject write** (slicing record S4, merged). A
minimum `HistoryStore` write lands with the injector, not two phases later. Phase 2a is
the first point at which there is a transcript to lose, and shipping an injection path
that structurally cannot honour §8 — because the thing it must persist to does not
exist yet — is not a scheduling detail. Retention, purge, and `manu history` stay in
Phase 3.

**Gate:** Dictate into TextEdit, VS Code, Chrome, and a terminal. Report where it fails.
Confirm clipboard save/restore behavior with a clipboard manager running, and that the
detection and tray indicator from §7.3 fire correctly. Confirm the transcript survives
a deliberately failed injection.

**Rejects if:** injection fails in **two or more** of the four named applications, or
fails in a *native* text field. G4 claims "works in any focused application"; two of
four is not that, and a native-field failure means the injector is broken rather than
the target being hostile. A single Electron or Java failure is a known-hazard finding
(§10) and does not reject — enumerate it and carry a per-app strategy override. Also
rejects if a transcript is lost when injection fails.

> **CLOSED 2026-08-02 — PASS.** Record: `docs/gates/phase-2a.md`.
>
> **Injection: zero failures.** TextEdit, Terminal, VS Code and Chrome, on
> *both* strategies, verified by reading the text back through the
> Accessibility API rather than by eye (`scripts/gate_2a_inject.py`). Neither
> reject condition is approached.
>
> **§8 holds under fault injection.** With the Accessibility grant forced off,
> the transcript survives on both retention paths — a row with `injected = 0`
> under `retain = true`, a `0600` file under `pending/` when false.
>
> **The clipboard exposure is now measured, not argued.** A real manager
> captured the transcript inside the default 150 ms restore window (§7.3). The
> first attempt at that measurement said "not captured" and was wrong; only the
> positive control caught it.
>
> **Latency:** Phase 2a adds p50 **3.32 ms** / p95 **6.89 ms** to `g1_ms`
> (n=25). A real end-to-end dictation measured `g1_ms` **231.6 ms**. G3 re-run
> with pyobjc in the tree: 0 sockets, 0 bytes, against a control that saw 865.
>
> Five findings; four amended this document (§2, §6.3 twice, §7.3 twice, §9).
> The two that changed the product: the clipboard restore was being charged to
> G1 and is not in it, and `TextInjector` needed the `warm_up` that §6.3's own
> argument for `TranscriptionEngine` had always implied — the first injection
> cost 165.8 ms and every later one under 2 ms.
>
> The tray-indicator wording in the gate above names a Phase 4 component;
> resolved as §7.3 records, the same way Phase 2b resolves the recording
> indicator.

### Phase 2b — Close the loop with the hotkey

> **CLOSED 2026-08-03 — PASS.** `docs/gates/phase-2b.md`. First end-to-end G1
> measurement as §2 defines it: **p50 223.0 ms / p95 270.0 ms** against 400 /
> 800, over ten real dictations in the 7–16 s band, read from the daemon's own
> `history.db` rows. Recording indicator confirmed visible by the operator
> against a running daemon. Still a floor — `postprocess_ms` is the one stage
> left, and Phase 3 fills it.
>
> Six findings, four amending this document. Two defects came from running the
> daemon rather than reading it: **it could not be stopped** (Ctrl-C and SIGTERM
> both did nothing — a Python signal handler cannot run while the main thread is
> inside `NSApplication.run()`, and `stop_` needs an event to be noticed), and
> **`restore_ms` had no column in `history.db`**, so Phase 2a's headline finding
> was emitted and silently dropped on every row since. The p95 figures are the
> maximum observation at n=14 and n=10 — extremes, not estimates.

`HotkeyListener` (Input Monitoring), `push_to_talk` only, `DictationController` wiring
press → capture → transcribe → inject.

**Also here: the minimum recording indicator** (slicing record S4, merged). §5.4 calls
unambiguous recording state non-negotiable and grounds it in privacy "regardless of
where the audio goes." Phase 2b is where a daemon first holds the microphone on a
global hotkey, and Phase 3's gate is ten real dictations of ≥ 60 seconds — dogfooding,
not a dry run. A visible indicator, not the full `TrayApp`, which stays in Phase 4.

**Gate:** **First end-to-end G1 measurement** as §2 actually defines it — hotkey release
to text fully present, via `g1_ms`, on a Tier A machine, with `chain = ["rules"]`.
Confirm the recording indicator is visible without opening a menu.

**Rejects if:** G1 is missed on a Tier A machine, or recording state is ambiguous at
any point while the mic is live.

Note what this gate means for Phase 1 (slicing record S1/S3): Phase 1 populates at most
two of `LatencyBreakdown`'s four stages, so its G1 check is a **lower bound**. This is
the first full-path number. Decide *before* Phase 1 what happens if it passes at 360 ms
and Phase 2b lands at 520 ms — whether the go/no-go is re-run or was already spent —
and record that decision in `docs/gates/phase-1.md`.

> **Decided 2026-08-02: the go/no-go is re-armed, not spent.** A Phase 2b G1 miss on a
> Tier A machine rejects the phase *and* re-triggers Phase 1's "stop and renegotiate
> §7.1". A floor clearing a budget shows the budget is reachable; it does not measure
> the thing the budget is about, and Phase 1's record labels every one of its numbers a
> floor. Recorded in `docs/gates/phase-1.md` — **backfilled**, because Phase 1 closed
> without making this decision at all. Deciding it after seeing Phase 2b's number would
> have let the number choose the rule.

**`chain = ["rules"]` in this gate names a Phase 3 component** (recorded 2026-08-02).
`RuleBasedPostProcessor` is built in Phase 3; Phase 2b cannot run the condition as
written. Same shape as Phase 2a's gate requiring a Phase 4 tray, and resolved the same
way rather than by moving the clause: **Phase 2b measures end to end with an empty
chain and labels `g1_ms` a floor once more**, naming `postprocess_ms` as the one stage
still missing. The reject condition binds on what is measured. The real G1 number —
every stage populated, nothing labelled — is taken at the **Phase 3** gate.

This is the **second** gate whose conditions reference a component from a later phase,
after Phase 2a's tray indicator. The remaining gates were checked rather than assumed:
Phases 0, 1, 3 and 4 name nothing they do not build. So the pattern is confined to the
two phases the 2026-07-31 split created, which is where it would be — the split moved
work across a boundary and the gate text either side of it was not re-read.

The same check found staleness pointing the other way, recorded here rather than left
for whoever opens Phase 3: **that phase's deliverable list names two things already
built.** `HistoryStore` landed in Phase 2a with the §8 write, and "silence trimming via
VAD" landed in Phase 1 when §7.4 moved it. Phase 3's remaining scope is
`RuleBasedPostProcessor`, `VocabularyPostProcessor`, and history's *retention* half —
`retain_days`, purge, `manu history`, and surfacing the `pending/` orphans §5.5 gap 3
describes.

#### Phase 2b follow-up — the collapse guard (2026-08-05)

**Not a reopening of the gate, and not the start of Phase 3.** Phase 2b closed
PASS on 2026-08-03 and stays closed. This is defect work against what that phase
shipped, taken before Phase 3 begins because the defect is live.

**Why it is Phase 2b's and not Phase 3's.** The dictionary's slicing record put
the guard first among its slices and said so in terms that turned out to decide
the question: *"first, and not because of the dictionary — `initial_prompt` is a
config key any user can set, is wired today, and is set on the operator's machine
now."* A slice that is not about the feature is not a slice of the feature. It
was scheduled inside a Phase 3 feature only because that is where it was noticed.

**What settled it was evidence, not the argument.** On 2026-08-05 a 30.5-second
dictation returned two words at 0.066 w/s — see §5.7. The record predicted the
hazard was already in production; it was, and it had been for two phases.

**Scope:** §5.7's guard, the `[guard]` config block, `GuardVerdict` and
`Transcription` in §6.3, `guard_ms` in `LatencyBreakdown`, the verdict in
`history.db`, `store_audio` implemented (§5.5), and **`manu history --last`**,
which is Phase 3 surface pulled forward because §5.7's refusal is only
defensible if the refused words are reachable.

**Not in scope:** the dictionary itself. `[replace]`, `[boost]`, `vocabulary.toml`
and `manu vocab check` remain Phase 3, unstarted and ungated. `manu history`
without `--last` — search, purge, retention against `history.db` — stays there
too.

**How it is verified, and what the verification cannot do.**
`scripts/verify_guard.py` runs both directions over the corpus: the guard fires
on a reproduced collapse (8.3% coverage) and on none of the six genuine samples
(floor 82.8%).

**The first run of that verification was worthless and reported a pass.** Its
positive control used a prompt reconstructed from the 2026-08-03 record's
description rather than the prompt itself, which was never written down. It
collapsed nothing, so the script measured the negative control twice and called
it a verification. The real prompt was found by sweeping nine candidates. The
script now exits non-zero when the positive control catches nothing, because a
control that cannot fail is not a control — the fourth instance of that failure
in this repository.

That is not sufficient and the record says so rather than implying otherwise
(objection O8). Two named limits:

1. **The negative control is one speaker.** Six samples from one voice cannot
   produce a speaker the guard is wrong about, so it passes by construction.
   Coverage is duration- and rate-independent by design, which is the argument
   that it *should* generalise — an argument, not a measurement.
2. **The positive control is not the failure that motivated the fix.** §5.5
   records the live 30.5-second collapse as unreproducible, because
   `store_audio` did nothing. The guard is validated against the corpus
   collapse, which is n=1 of six with no explanation of why that sample.

The Phase 3 gate records `coverage` and `retained_seconds` for **every**
dictation, fired or not, so the live distribution can be compared against the
six samples these thresholds came from. Until then the false-positive direction
is **untested**, which is different from tested and clean.

### Phase 3 — Post-processing and history
`RuleBasedPostProcessor`, `VocabularyPostProcessor`, `HistoryStore`, silence trimming via VAD.

> **This deliverable list is stale and the Phase 2b gate said so** (see above).
> `HistoryStore` landed in Phase 2a and VAD trimming landed in Phase 1. The real
> remaining scope is `RuleBasedPostProcessor`, `VocabularyPostProcessor`, and
> history's *retention* half — `retain_days` against `history.db`, purge,
> `manu history`, and surfacing the `pending/` orphans of §5.5 gap 3. Left in
> place above rather than rewritten, because the phase has not been opened and
> its scope is the operator's to approve, not this document's to quietly revise.

**Scope opened 2026-08-08**, in the terms the blockquote left for the operator:
`RuleBasedPostProcessor`, the dictionary (`vocabulary.toml` — §5.6), history's
retention half, and three defects in shipped code that the phase's own review
found (`docs/superpowers/objections/phase-3-postprocessing.md`, O1/O2/O3). Full
specification in `docs/superpowers/specs/phase-3-postprocessing.md`.

**Gate:** Ten real dictations of ≥ 60 seconds. Report edit rate — what fraction of output
needed manual correction, and what kind. This is also the phase that takes **the
real G1 number** — every stage populated, nothing labelled a floor — which Phase
2b explicitly deferred here.

**Rejects if:** edit rate exceeds the G2 threshold **and** the corrections are
dominated by classes the rules chain should have caught (punctuation, capitalisation,
spoken commands) **or by proper nouns for terms present in the frozen
`vocabulary.toml`**; or `postprocess_ms` p95 exceeds 5 ms; or `vocab_ms` p95
exceeds 10 ms.

**The proper-noun clause was amended 2026-08-08** (objection O4, choice-story
#8). It previously read: *"an edit rate driven by proper nouns points at §5.6's
vocabulary mechanisms, not at a phase failure."* That was written when §5.6 was
unbuilt. **Phase 3 builds §5.6**, so the clause pre-excused the exact error class
this phase ships the fix for, and — with G2's threshold movable and §2's 909 ms
prediction covering G1 — left a gate with no reachable failing state. The PRD had
already recorded this species once, about Phase 5: *"the gate also cannot fail
the budget by construction."*

The amendment is **narrowed to terms the frozen vocabulary covers**, and the
narrowing is the load-bearing part. Un-excusing proper nouns wholesale would make
the gate fail on the *corpus's scope* rather than the *dictionary's misses* —
entry count is not coverage, and a failure would have two causes the instruments
cannot separate. For proper nouns the vocabulary does not cover, §9's original
reasoning still holds and they stay excused. This also matters two phases out:
`04-rules-only.md` §5 measured **87.2% of corpus errors as ASR mistranscription**
that no downstream pass can recover, and a wholesale un-excusing would hand Phase
5 a reject clause counting a class it structurally cannot address.

**Two latency ceilings, both derived rather than picked.** `postprocess_ms` p95
≤ 5 ms: the measured rules floor is 0.0505 ms p95 and 5 ms sits *below* the
12.01 ms p50 that a loop of `re.sub` costs at 1000 entries, so the ceiling
catches the specific regression §5.6's 70× measurement warns about. `vocab_ms`
p95 ≤ 10 ms: this is the one stage whose cost scales with an artefact the *user*
authors, and without a bar a large enough `vocabulary.toml` moves a published
guarantee with no code change.

**The gate must be able to measure something.** It runs `chain = ["rules",
"vocabulary"]` with `vocabulary.toml` **frozen before the first dictation** and
recorded by SHA-256 *and entry count*, and at least one `[replace]` entry must
fire across the set — a frozen empty file satisfies a digest and measures
nothing. `store_audio = true`, so a collapse in the wild is reproducible; the
last one was not. Every dictation records `coverage` and `retained_seconds`
whether the guard fired or not, plus a **second set of ten dictations under five
seconds**: §5.7's untested false-positive direction is a *short*-utterance blind
spot, and ten sixty-second dictations sit where coverage is near 100% and margin
is largest, so the long corpus cannot reach it.

This is also where G2's provisional 5% threshold is confirmed or moved (§2). Moving it
is a legitimate outcome; moving it without stating the reason in the gate record is
not. **Note the pairing** (choice-story #8): the amendment above closes the
qualitative escape and leaves the numeric one, and both are exercised by the same
person at the same sitting.

### Phase 4 — Tray, modes, polish
`TrayApp`, `toggle` and `vad_auto` modes, error surfacing, README with the clipboard caveat
documented, install path with checksummed model download.

**Three additions from the Phase 2b gate** (2026-08-03):

1. **`manu toggle` and `manu status`, and the IPC transport underneath them.**
   Both were marked Phase 2b in `cli.py` and named nowhere in Phase 2b's own
   text, which lists the listener, the controller and the indicator. They need
   §7.3's portability floor item 3 — the platform-resolved transport — which no
   phase had ever scheduled. A floor item with no phase is a floor item that
   does not exist. They land here because this is the phase that owns `toggle`
   mode and the tray.
2. **A recording affordance with more presence than a menu-bar glyph** (§5.4,
   Phase 2b finding 4). The minimum indicator meets §5.4's letter and its first
   user said a glyph is not enough to be confident the microphone is live. This
   means an `NSPanel` overlay or a real `.app` bundle, both already this phase's
   territory.
3. **Revisit the asynchronous clipboard restore.** 155 ms of worker thread
   spent holding the transcript on the clipboard, outside G1 and real. Phase 2b
   declined it because it races the next dictation, and the serial worker is
   what makes §6.3's focus check meaningful. The tray is what a restore
   outliving its session would need in order to report failure anywhere.

The README also carries the **per-tier latency table** — the Tier A G1 figures and the
Tier B G1-CPU figures, each labelled with **what the machine measured** rather than what
silicon it has (§2, §4, §7.2; choice-story #8, objection A9) — and the privacy section
from §9's Phase 4 G3 verification. "Accelerated" is not a user-facing distinction: this
product has one execution path and tiers are measured, so a README that published an
"accelerated" figure would be advertising a difference it does not make.

**Gate:** A second person installs it from the README without your help.

**Rejects if:** they cannot reach a first successful dictation from the README alone,
or they have to ask a question the README should have answered. Record what they asked
— that list is the README's real defect report.

Define the conduct in advance so the gate measures the README rather than the tester:
observe silently, no hints, stop at 30 minutes, and note their starting environment.
This gate is n=1 and unrepeatable; those constraints are what keep it honest rather
than flattering.

**Also at this gate — second G3 verification** (objection O5). Re-run packet capture
against the assembled product: tray running, install path exercised, checksummed
model download performed. Phase 1 verified a narrower system; this is the last point
before an audience sees it, and the tray toolkit and install path are both new
dependency surface introduced since. Report the result in the README's privacy
section rather than only at the gate.

**Qualify the claim explicitly** (choice-story #11): state in both the gate record and
the README that packet capture covers Amanuensis's own sockets only, and that
transcripts transit the system clipboard by default where another process may capture
them (§7.3). An unqualified "G3 verified" is the failure O12 described.

### Phase 5 — LLM second pass — **UNRESOLVED, no longer corpus-blocked** (2026-08-02)

Deferred, then un-deferred, then measured and found not shippable — all on
2026-07-31. This section records the state that survived the day, and it is
neither "scheduled" nor "dead".

**Why it is not dropped.** The second pass is not polish. It is a **core feature
of the product §1 measures against**: a verbatim transcriber and a tool that
resolves your self-corrections are different products, and a user comparing them
will not grade on the distinction.

**Why it is not scheduled.** The design that motivated un-deferring it was
measured against real ASR output and failed — WER 19.6% → 110%, latency
373–2,201 ms against a 700 ms budget (`docs/gates/phase5-feasibility.md`). Four
alternatives were then tested against a frozen corpus
(`docs/gates/phase5-experiments.md`):

| Approach | mean WER 19.33% → | p50 | Verdict |
|---|---|---|---|
| Rules-only (control) | **19.33%** — unchanged | 0.044 ms | no effect |
| Token keep/delete classification | 20.35% | 13.6 ms | no improvement |
| Fine-tuned seq2seq | 21.27% | 300 ms | no improvement |
| Constrained decoding | 34.58% | 908 ms | worse, budget missed |

**Not one approach improved WER on a single sample**, and the control — which
changes nothing and costs 44 microseconds — leads the table.

**That result is inconclusive, not negative, and the distinction is the whole
section.** The corpus contains no disfluencies: every sample was read from a
prepared script, which `05-noisy`'s own reference states outright ("while I read
this sentence"). Three of the four approaches are deletion mechanisms aimed at
tokens that are not in the input. The corpus was built to measure ASR accuracy
against a known reference, which requires a script — it is structurally
incapable of testing a disfluency remover, and reusing it here was the error.

**The blocking unknown, stated as a question nobody has answered: do
disfluencies survive the decoder?** It is untested. The claim that they do not
appears in one experiment record and is an assertion, not a measurement.

**Measured 2026-08-02** (`docs/gates/phase5-disfluency.md`). The corpus exists —
10 takes of genuinely spontaneous speech — and the answer splits in two.

**Filled pauses do not survive. Answered.** Zero "um"/"uh"/"er" in 403 words,
identically across `tiny.en`, `base.en` and `small.en`. Verified by ear rather
than inferred: the speaker counted **three audible "um"s** in `06-undecided`,
which transcribed 56 words with none. Three model sizes across a 4× parameter
range deleting them identically points at Whisper's training data, not at any
parameter this project sets.

**Self-corrections are still untested, and they are the half this section rests
on.** "Disfluency" covers filled pauses *and* repairs — "let's meet Tuesday, no,
Wednesday" — and the paragraph above about resolving self-corrections is about
the second. The prompts elicited thinking under load, which produces filled
pauses reliably and repairs barely: one repair marker in 403 words is not a
sample. Nothing here says what the decoder does with them.

**So three of the four approaches below were aimed at tokens the decoder had
already removed**, and would have found nothing to do on a spontaneous corpus
either. The earlier verdict — inconclusive because the corpus was scripted — was
half wrong: the corpus was not the only reason those deletion mechanisms had
nothing to delete. They sat downstream of a stage that had already done their
job.

**Closing it costs one targeted take**, roughly two minutes: deliberately
self-correct a counted number of times, then check how many survive. The count
has to be known in advance, because a repair — unlike "um" — is grammatical
English and cannot be found in a transcript by pattern. "Let's meet Tuesday, no,
Wednesday" and "let's meet Wednesday" are both fluent sentences, and only the
speaker knows which was said.

**Unblocked by:** 6–10 samples of genuinely spontaneous speech — thinking aloud,
no script — transcribed with the selected model and VAD. No reference
transcripts needed; this measures *presence of disfluency*, not WER. Roughly a
20-minute recording session.

- If disfluencies survive, re-run all four approaches against that corpus before
  choosing. Token classification is the standing candidate on latency and safety.
- If they do not, Phase 5 has no subject matter. Move it to §3, and say plainly
  in the README that Amanuensis transcribes what you said rather than rewriting
  it.

**No gate until there is something to gate.** The previous A/B gate measured
against a p50 ≤ 700 ms budget already missed by 3× on the fastest hardware this
product will run on, which made it pre-failed rather than undecided.

**What was learned and holds regardless**, because none of it is a WER claim:

- **Deletion-only is a checkable property**, and that is what made the original
  failure catchable at all. The four constraints below were written *before* the
  test and caught 100% of the catastrophic failures.
- **Both safety checks are individually insufficient, in opposite directions.**
  `INVENT` is blind to function-word substitution — one checkpoint rewrote
  "faster whisper" → "the whisper" and it did not fire. The 25% `SHRINK` floor
  would discard the best output any experiment produced: the one genuine
  self-correction resolution shrinks content words by 44.4%. For a
  deletion-only mechanism, large shrink is the feature.
- **A fifth constraint is missing: measure the firing rate.** All four existing
  checks are *shape* checks. Nothing asks whether the pass had a job to do. A
  pass that correctly no-ops on every input satisfies all four perfectly and
  delivers nothing.
- **MPS is slower than CPU at this model size** — 804 ms versus 300 ms on the
  same checkpoint. Second accelerator assumption this project has found
  backwards.

If and when the feature revives, these four constraints ship *with* it, not
after it:

1. **The pre-injection write stores the RAW transcript** (§8), never the cleaned one.
2. **No-invent check**: if cleaned output contains content words absent from the raw
   transcript, discard it and inject raw. Deletion is intended; insertion is a
   hallucination.
3. **Length floor**: if cleaning removes more than ~25% of content words, treat it as
   over-editing and fall back to raw.
4. **One-keystroke undo to the raw text**, because the user cannot know what was removed.

Constraints 2 and 3 are cheap deterministic checks wrapped around a probabilistic step.
They convert the failure mode from silent corruption into a visible no-op — measured, not
argued. Constraint 3's threshold is **provisional and probably wrong**: see the SHRINK
finding above. The `[postprocess.llm]` config block stays reserved.

**Rejects if** (should the phase revive): the spontaneous-speech corpus shows no
disfluencies surviving the decoder — in which case the phase does not start — or the
selected approach fails to improve edit rate against the Phase 3 baseline on that
corpus. The budget is re-derived from tolerance at that point, not inherited: §7.5's
arithmetic-not-tolerance objection stands, and the old 700 ms figure was already missed
by 3×.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| G1 unachievable on any hardware class | High | The pre-Phase-0 probe (§9) answers this to an order of magnitude in about an hour, before the scaffold is built; the Phase 1 gate remains the real go/no-go. A miss here does stop the project (§9). |
| Tier B machines are slow enough to be unusable | Medium | G1 does not bind on Tier B (§2, §7.2). It ships with a smaller model and a **measured, published** latency expectation rather than a broken promise. The Phase 1 gate reports the Tier B number even though it does not gate on it; if that number is unusable rather than merely slow, the honest response is to drop the class in §3, not to ship it silently. |
| Silent network egress from a transitive dependency | High | Packet capture is now a gate criterion at Phase 1 and again at Phase 4 (§9). Model weights resolve from a pinned local path, never a repository ID at runtime (§7.6). |
| Transcript captured and cloud-synced by a third-party clipboard manager | High | Clipboard-manager detection at startup with a persistent tray indicator (§5.4, §7.3). Not covered by G3's packet capture — the egress is in another process. |
| macOS permissions are opaque and users get stuck | High | Permission check at startup with copy-pasteable remediation, not a generic failure. |
| Clipboard restore races with clipboard managers | Medium | Document it. Offer `keystroke` strategy. Do not claim it is solved. |
| Electron and Java apps reject synthetic paste | Medium | Enumerate failures at the Phase 2 gate; per-app strategy override if needed. |
| Model download size (~1.5 GB) surprises users | Low | Show size and prompt before download. |
| Scope creep into a meeting-transcription product | Medium | §3 is binding. |

---

## 11. Open decisions

Resolve before or at the stated gate. Do not guess.

1. ~~**Primary OS target**~~ — **RESOLVED 2026-07-30 (objection O6): macOS-only v1.**
   Windows and Linux are §3 non-goals. `TextInjector` stays an ABC so a later port is
   a scheduling decision (§7.3), but nothing in §9 builds one and §6.4 no longer stubs
   the files. Note what this closes: §7.3's "swap the order freely" claim was never
   tested, and is now not relied upon for v1.
2. **Settings UI** — tray menu is sufficient for v1. A React/Tauri settings panel is a
   post-v1 question and is not in §9.
3. **Model distribution** — Hugging Face at first run vs. bundled installer. Phase 4.
4. **Public repo timing** — before or after Phase 4.

---

## 12. Where Kokoro actually goes

Kokoro is text-to-speech. Amanuensis is speech-to-text. It does no work in the core loop
and must not be pulled into v1 on the strength of the original idea.

There is a real feature it enables — **read-back**: select text anywhere, press a second
hotkey, hear it spoken. That pairs naturally with dictation for proofreading and is genuinely
useful for the accessibility user in §4. It is a separate module (`amanuensis.speech`) with
its own hotkey, its own ABC (`SpeechSynthesizer`), and its own PRD.

Do not build it in v1. Do not import `kokoro` anywhere in the Phase 0–5 tree.

---

## 13. Prior art to read before Phase 1

Read these before writing code; several problems in §10 are already solved in public.

- **whisper.cpp** — quantization approaches, Core ML backend
- **faster-whisper** — the API you are building against
- **nerd-dictation** (Linux) — the injection layer, done well
- **Talon Voice** — the accessibility bar, and what a mature hotkey/injection layer handles
- **Moonshine** — the short-utterance latency argument

---

## 14. Sentinel records for this document

Four read-only sentinel agents were run against this PRD on 2026-07-30, before
Phase 0 started, and `advocatus-diaboli` was run a **second time on 2026-07-31**,
scoped to that day's amendments alone. Each produced a structured record. The
sentinels cannot fill a disposition — resolving one is a human act, and their
read-only tool boundary is what enforces that. Every amendment made in response
appears in the revision log below; none was made silently.

**Why the second pass happened.** The 2026-07-31 amendments were applied
recommendation → approval → document, with no review step, on a day when
measurement falsified four of five confident recommendations within hours. That
is precisely the condition the sentinel exists for, and skipping it would have
hardened Phase 0 against unreviewed decisions. It found nine objections, seven
of them high or critical, including one — A6 — that landed on code committed the
same day.

<!-- BEGIN sentinel-index (generated) -->
| Record | Path | State |
|---|---|---|
| Slicing — `amanuensis-prd` | `docs/superpowers/slices/amanuensis-prd.md` | 7 slices — 3 accepted, 4 merged |
| Slicing — `dictionary` | `docs/superpowers/slices/dictionary.md` | 5 slices — 1 merged, 4 pending |
| Objections — `amanuensis-prd-2026-07-31-amendments` | `docs/superpowers/objections/amanuensis-prd-2026-07-31-amendments.md` | 9 objections — **all accepted** |
| Objections — `amanuensis-prd` | `docs/superpowers/objections/amanuensis-prd.md` | 12 objections — **all accepted** |
| Objections — `collapse-guard` | `docs/superpowers/objections/collapse-guard.md` | 8 objections — 7 accepted, 1 deferred |
| Objections — `dictionary` | `docs/superpowers/objections/dictionary.md` | 11 objections — 2 accepted, 9 pending |
| Objections — `phase-3-postprocessing` | `docs/superpowers/objections/phase-3-postprocessing.md` | 12 objections — **all accepted** |
| Choice stories — `amanuensis-prd` | `docs/superpowers/stories/amanuensis-prd.md` | 13 stories — **all accepted** |
| Choice stories — `dictionary` | `docs/superpowers/stories/dictionary.md` | 8 stories — 3 accepted, 5 pending |
| Choice stories — `phase-3-postprocessing` | `docs/superpowers/stories/phase-3-postprocessing.md` | 10 stories — 9 accepted, 1 revisit |
| Cost estimate | `cost-estimates/2026-07-30-amanuensis-prd-estimate.md` | not adjudicable |
<!-- END sentinel-index (generated) -->

<!-- Regenerate with: python3 scripts/regenerate-sentinel-index.py
     Counts are parsed from each record's YAML frontmatter, never from prose.
     Do not hand-edit the rows above; they are overwritten. -->

**Both critical objections are resolved.** `O8` (G1 was not operationally defined
against the instrument built to measure it) and `O12` (the default clipboard
strategy is a transcript-egress path G3's verification structurally cannot see)
are accepted and applied — see the revision log.

**All twelve of the 2026-07-30 objections are disposed as accepted**, and every
amendment is in the revision log. The 2026-07-31 amendment round adds nine more
(A1–A9), **all nine accepted** — see the table above for the generated count.
Their IDs are lettered because O1–O12 are still referenced by name throughout
this document. The through-line across them: this document was better at defining
what to build than at defining what would count as having built it badly. G1 was not
computable, G2 was stated in a unit nothing measured, G3 had a verification method no
gate ran, and half the gates could not fail. Those are fixed.

The choice-story record has been **re-run** against this amended PRD, in the
intended order this time. Of its first-pass ten: one stands, six changed, two were
resolved outright (by O6 and O9), and one was superseded. Seven of the thirteen are
new — decisions the amendments themselves introduced. Read `#8`, `#9` and `#12`
first; each maps a choice made *inside* an objection resolution without being
posed as a choice.

The cost estimate omits a dollar figure: no snapshot exists in
`observability/costs/`, and there is no list-price fallback. Its token figures
are generation-side only and its stated failure direction is `likely-underrun`.

---

## Revision log

| Date | Change |
|---|---|
| 2026-08-08 | **Phase 3's gate could not fail, and the clause that made it so was written before the thing it excused existed** (§9, objection O4, choice-story #8). The reject clause excused an edit rate driven by proper nouns because it "points at §5.6's vocabulary mechanisms, not at a phase failure" — and Phase 3 *builds* §5.6. With G2's 5% movable and §2's 909 ms prediction covering G1, every failure mode was pre-authorised. Amended, and **narrowed to terms present in the frozen `vocabulary.toml`**: un-excusing the class wholesale would fail the gate on the *corpus's scope* rather than the *dictionary's misses*, and would hand Phase 5 a reject clause counting the **87.2% of errors measured as unrecoverable ASR mistranscription**. Two derived latency ceilings added (`postprocess_ms` p95 ≤ 5 ms, `vocab_ms` p95 ≤ 10 ms), plus a minimum instrument — a frozen *empty* dictionary satisfies a SHA-256 and measures nothing, so entry count is recorded and one entry must fire. Second instance in this PRD of a gate that could not fail by construction; the first is §7.5's, about Phase 5. |
| 2026-08-08 | **A raising post-processor loses the transcript, and two documents say it cannot** (§6.3, objection O1). `postprocess/base.py` and §6.3 both state that when `process` raises, "§8's persist-before-inject ordering already ran, so the words survive regardless." In `DictationController._process` the chain runs **before** the write, and the only handler returns before `deliver` — so nothing is persisted, nothing is injected, and the words exist in a local variable. Invisible for three phases because `cli.py` passed `processors=[]`; reachable the day Phase 3 ships one. The loop gets a per-processor guard **and both documents are corrected**, because guarding the loop while leaving a false statement in place is how the next reader inherits it. Fourth instance of the PRD stating a constraint the code cannot honour, after `restore_ms`, `store_audio`, and the missing `raw_transcript` column. |
| 2026-08-08 | **§6.3's `TranscriptionEngine.transcribe` gains `boost: Sequence[str] = ()`** (objection O2). §5.6's per-application boosting needs terms chosen per dictation, and the contract had no channel: `initial_prompt` is read from a frozen `EngineConfig` at decode time and `biased` is all-or-nothing. Exactly the 2026-08-05 `biased` precedent — a term list is backend-neutral domain vocabulary and each engine says locally what boosting means, where passing a prompt string would make the caller responsible for a mechanism it is not supposed to know about. Also **`vocab_ms` joins `LatencyBreakdown`**, inside `g1_ms`: the vocabulary reload runs before the decode, and a stage inside G1's window needs a field. **Fifth phase in a row.** |
| 2026-08-08 | **`[boost]` would have disabled §5.7's recovery in the configuration it recommends** (§5.7, objection O3). `_why_no_retry` refuses the unbiased retry when `[engine] initial_prompt` is empty, reporting "nothing to drop" — and `[boost]` supplies bias *while `initial_prompt` is empty*, which is what §5.6's O7 resolution recommends. The guard could fire, the reason would be false, `DictationState.RECOVERED` would be unreachable, and the user would get a withheld transcript where they previously got their words back. The refusal now asks whether **any** bias was applied to *this dictation*. This is the half of the collapse guard's deferred objection O6 that mattered; the half about the prompt's prose register is rejected, because a prose detector is a heuristic with a false-positive population and the guard catches the failure directly. |
| 2026-08-08 | **§5.3 gains two policies it had been applying without writing down** (choice-stories #2 and #4). (1) **"Off by default" means quarantine pending measurement, and quarantine carries an obligation to measure.** Three mechanisms have now been admitted that way — `strip_fillers`, the LLM pass, `spoken_commands` — and none carried the obligation; `spoken_commands = false` would have produced a gate firing rate of *structurally zero*, which reads as "harmless" to an author and "delete the code" to `04-rules-only.md`'s fifth constraint. Resolved by having the rule count candidate matches while disabled. (2) **A guarantee measured against a reference configuration is qualified by it, not protected by withholding the key.** G1 is defined against `chain = ["rules"]`, so enabling the dictionary leaves the configuration every recorded G1 figure was measured under. §5.3's bounded exception would say remove the key, which is absurd here. §5.3 warned that a fourth *exception* would be the wrong answer to the next collision; what arrived was a fourth *technique*, and the warning did not cover it. G2 is next in line — the gate's freeze-and-digest is the same move. |
| 2026-08-05 | **`initial_prompt` can silently destroy a transcript, and it shipped in Phase 1 with nothing watching it. New §5.7, the collapse guard**, plus a `[guard]` block in §5.3 and `GuardVerdict` in §6.3. A 30.5-second dictation on the operator's machine returned two words — `" For Tenants."` — with no error raised and the text injected as though it were what was said. On a fired verdict the audio is decoded once more with the bias dropped; **the retry must be unbiased or it is worthless**, because `beam_size = 1` is greedy and re-running identical inputs returns identical words — and where no `initial_prompt` is configured there is nothing to retry, so the guard reports the loud failure rather than a recovery attempt it never made. When recovery also fails the text is **not injected**, which overrides choice-story C4's fail-open decision and is recorded as an override rather than cited as support. Built as a **Phase 2b follow-up defect fix**, not as dictionary slice V1: the slicing record's own case for it — *"first, and not because of the dictionary"* — is a case for it not being part of the dictionary at all. |
| 2026-08-05 | **The guard measures the decoder, not the speaker — the first design was wrong and the wrong one is the intuitive one** (§5.7, objection O1). Words per second divides *how the user talks* by *how long they talked*; the failure is *where the decoder stopped*. `faster_whisper` returns segments carrying `start`, `end`, `avg_logprob`, `no_speech_prob` and `compression_ratio`, and `_decode` was discarding every one of them — the signal was already crossing the boundary. **Decoded coverage** — last segment `end` over retained seconds — reads 6.5% on the live failure and ~95% on a genuine two-second utterance. It is duration-independent, which the rate floor could not be: word count is an integer, so at two seconds the rate quantises to 0.5 w/s *per word* and a genuine one-word "Yes." is **the same measurement** as a transcript collapsed to one word. `min_audio_seconds` was therefore never a policy choice — it was the floor conceding it cannot work on short audio, over the input the product's first user produces most often. Coverage also has **no false-positive population**: a slow or quiet speaker still produces segments spanning their audio, which retires the hazard aimed at §4's secondary user rather than mitigating it with a config key. The rate floor survives as a fallback for engines that cannot report a span, with its blind spot labelled. |
| 2026-08-05 | **One threshold was doing two jobs with costs differing by orders of magnitude** (§5.7, objection O4). Spending a decode and withholding the user's words are split: `retry_below_coverage = 0.8` triggers an unbiased re-decode, `min_decoded_coverage = 0.5` gates the refusal. The middle band is where the evidence comes from — biased and unbiased output over the same audio, both recorded, which the guard otherwise had no way to generate. **`manu history --last` ships with the refusal** (objection O2), pulled forward from Phase 3: §8's write is unconditional, but *written* is not *recoverable*, and before this a refused transcript went somewhere no shipped command could show it. The refusal is defensible only because the words are reachable. |
| 2026-08-05 | **`guard_ms` joins `LatencyBreakdown`** (§6.3, objection O5). §5.7's retry is a second full decode inside G1's window, and the standing rule — *a stage inside G1's window with no field is a stage that cannot be defended when G1 is missed* — was broken **in the same revision that restates it**. Four phases in a row now. The retry is also bounded: §2's `transcribe_ms ≈ 48.8 + 13.69 × seconds` predicts its cost before it is attempted, and `retry_max_latency_ms` skips it rather than paying it, with the skip recorded on the verdict. |
| 2026-08-07 | **The guard verified on real audio, and three things it found.** `scripts/verify_guard.py`, both directions over the Phase 1 corpus: fires on a reproduced collapse at **8.3%** coverage, silent on all six genuine samples, floor **82.8%**. (1) **The first verification was worthless and reported a pass** — its positive control used a prompt reconstructed from the 2026-08-03 record's *description*, since the prompt itself was never written down. It collapsed nothing, so the script measured the negative control twice. The real one was found by sweeping nine candidates; the script now exits non-zero when the positive control catches nothing. Fourth instance of a check that could not fail. (2) **The denominator was not speech.** `[vad] speech_pad_ms` adds 400 ms of deliberate non-speech per side, and the decoder emits nothing over it — which under-reports coverage in proportion to how *short* the clip is. The shortest genuine sample read 62.2% against a 50% refusal gate; corrected, 82.8%. Systematic, pointed at refusing genuine transcripts, worst on this product's most common input. `TrimResult` now reports `padding_seconds`. (3) **`retry_below_coverage` lowered 0.8 → 0.7**, because 82.8% left 2.8 points of headroom and short dictation would have paid a second decode routinely. Calibrated against one short sample, which is thinner than the number deserves. |
| 2026-08-07 | **The collapse mechanism is prompt echo, and dictionary objection O3's fork was a false one.** O3 asked whether the cause is early termination or domain drift, and said a floor answers only the first. It is early termination: `initial_prompt = "And how much is this?"` makes the decoder emit exactly that string as the transcript of a 25-second clip, deterministically. This retires the 2026-08-03 record's "prose prompt" description, which named the *output* and attributed the failure to the prompt's register — the register is not the variable, since five other prompts of comparable shape including a 600-character one collapsed nothing. What the collapsing prompt has is the form of a complete short utterance the model can plausibly emit as a whole transcript. Coverage measures early termination directly, so instrument and failure now match. Still unanswered: why this clip and not the other five — which the guard does not need, because it is built against the failure rather than the cause. |
| 2026-08-05 | **§9's verification for this fix could not fail, and now says so** (objection O8). The negative control is six samples from one speaker, which cannot produce a speaker the guard is wrong about; the positive control is the corpus collapse rather than the live failure, because §5.5's `store_audio` did nothing and that audio is gone. Both limits are named in §9, the false-positive direction is labelled **untested**, and the Phase 3 gate is required to record `coverage` and `retained_seconds` for every dictation so the live distribution can be compared against the six samples the thresholds came from. Also: this is the **first sentinel record in this repository a sentinel actually produced** (`docs/superpowers/objections/collapse-guard.md`, eight objections, one critical) — dispatched without `name:`, per the cause found on 2026-08-04. Two of its claims were checked against the source before being acted on; one held and one did not. |
| 2026-08-05 | **`store_audio` validated and did nothing for three phases** (§5.5). A documented key with a validation rule and a test asserting its default, and no code anywhere that read it. The cost came due when the collapse above turned out to be unreproducible: the one setting that would have preserved the evidence was the one that did nothing. Implemented with its own retention — audio is swept by `retain_days` at daemon start through the existing `sweep_pending` mechanism, because adding a writer for the sensitive artefact (§7.6) without a reaper would create a directory that grows without bound and that no command reaches until Phase 3 ships `--purge`. **Third instance of "an amendment must reach the tooling"**, after `bench_engines.py` and `restore_ms`, and the first where the test suite passed *because* it only checked that the key parsed. |
| 2026-08-05 | **§6.3's `TranscriptionEngine.transcribe` gains `biased: bool = True`.** §5.7's retry needs a decode with vocabulary bias suppressed and the contract had no way to ask for one. Rejected alternative: passing `initial_prompt=""` through as a parameter, which makes the caller responsible for knowing what biasing means on a backend it is not supposed to know about — §7.2's Moonshine and Parakeet do not necessarily share the mechanism, and an empty prompt string is a question that does not parse for an engine with no prompt concept. The flag asks for the behaviour; each engine says locally what it means. Default preserves every existing call site. |
| 2026-08-03 | **Phase 2b closed — PASS. First end-to-end G1 measurement as §2 defines it: p50 223.0 ms / p95 270.0 ms** against 400 / 800 (`docs/gates/phase-2b.md`). Ten real dictations in the 7–16 s band, read from the daemon's own `history.db` rows rather than a harness, because `LatencyBreakdown` already persists. Passes on all fourteen too, at p50 215.3 / p95 795.0 — by 5 ms, and that margin is the utterance-length finding below. **The p95 at n=14 is the maximum observation, not an estimate of a 95th percentile.** Still a floor: `postprocess_ms` is the one unfilled stage. |
| 2026-08-03 | **G1's gated figure is the best case of a linear relationship** (§2). Measured across 0.7–43.4 s of speech: `transcribe_ms ≈ 48.8 + 13.69 × seconds`. At 10 s that is `g1 ≈ 225 ms`; at 60 s it is **≈ 909 ms, over G1's 800 ms p95**. §2 already bound G1 at 10 s and that stands — what was missing is the consequence, which is that a user dictating a paragraph is the ordinary case and G1 says nothing about what they wait. **This lands on Phase 3 immediately:** its gate is ten dictations of ≥ 60 s, exactly where the model predicts 909 ms, and without this note the result reads as a regression caused by post-processing rather than by utterance length. |
| 2026-08-03 | **§5.4 gains a recording affordance beyond the menu-bar glyph; Phase 4 builds it.** The minimum indicator meets §5.4's letter — confirmed against a running daemon, the glyph fills on press and empties on release — and its first user said a glyph is not enough to be confident the microphone is live. Recorded because of where it came from: every other requirement here was written before anything existed, and this one came from someone using the product and finding the specified behaviour insufficient. Also noted: macOS's own microphone indicator meets §5.4 independently and cannot be suppressed by this process, which makes the richer affordance a *confidence* requirement rather than a correctness one. |
| 2026-08-03 | **The daemon could not be stopped, and that is §5.4's problem with the escape hatch removed.** Ctrl-C and SIGTERM both did nothing; only `kill -9` worked. Two independent causes: CPython cannot run a signal handler while the main thread is blocked inside `NSApplication.run()`, and `NSApplication.stop_` sets a flag checked only when an event is dequeued — which an idle dictation daemon never has. Fixed with a 250 ms `NSTimer` that yields to the interpreter and a posted application-defined event. The indicator was correct the entire time; the failure was that knowing did not help. |
| 2026-08-03 | **`restore_ms` had no column in `history.db`.** Phase 2a added the field as its headline finding, argued it across §2 and §6.3, and never added the column — so `to_history_row()` emitted the value and `_insert` dropped it, silently, on every row since. Found by reading a real row at this gate. Second instance of AGENTS.md's *an amendment must reach the tooling that can regenerate it*. The regression test iterates `dataclasses.fields(LatencyBreakdown)` rather than naming the field, because the defect was a hand-maintained list that stopped being checked against the dataclass. |
| 2026-08-03 | **§6.3 contracts `HotkeyListener` and adds `check_permissions`; `TextInjector` gains `focus_identity`; `DictationController`'s constructor gains `capture`, `detector`, `on_state_change`, and a `start`/`shutdown` lifetime.** The listener was declared in §6.4 and listed in §6.2 and never contracted here, which floor item 4 had already flagged. `focus_identity` exists for the hazard the async handoff creates, not for injection: `None` means *cannot tell*, deliberately not *changed*. `capture` and `detector` were in §6.2's tree and absent from the constructor, which would have had the controller reach for PortAudio itself. |
| 2026-08-03 | **`manu toggle` and `manu status` move to Phase 4, with the IPC transport they need.** `cli.py` said Phase 2b; §9's Phase 2b text names the listener, the controller and the indicator and names neither. Both need §7.3's portability floor item 3, which **no phase had ever scheduled** — a floor item with no phase is a floor item that does not exist. Phase 4 also inherits the asynchronous-restore question Phase 2b declined, because the serial worker is what makes the focus check meaningful. |
| 2026-08-03 | **`hotkey/listener.py` renamed to `hotkey/macos.py`** (§6.4), on this section's own precedent. `injection/` names its implementation after the platform because `factory.py` dispatches on platform, and `hotkey/factory.py` was specified to mirror it down to the error wording. A Windows port adds `hotkey/windows.py`; it cannot add a second `listener.py`. |
| 2026-08-02 | **Two §9 gate conditions name components from later phases, and one Phase 1 decision was never made.** Phase 2b's gate asks for `chain = ["rules"]`, which Phase 3 builds — resolved the way Phase 2a's tray indicator was: Phase 2b measures end to end with an empty chain and labels `g1_ms` a floor, and the real G1 number is taken at the Phase 3 gate. Phases 0, 1, 3 and 4 were checked and name nothing they do not build, so the pattern is confined to the two phases the 2026-07-31 split created. Separately: §9 required Phase 1 to decide whether a Phase 2b G1 miss re-runs the project-level go/no-go, and Phase 1 closed without deciding. **Backfilled: re-armed.** A floor clearing a budget shows the budget is reachable and does not measure the thing the budget is about. Also recorded: Phase 3's deliverable list names `HistoryStore` (built in 2a) and VAD trimming (built in Phase 1). |
| 2026-08-02 | **Phase 2a gate findings applied** (`docs/gates/phase-2a.md`). §6.3's `LatencyBreakdown` gains **`persist_ms`** (inside `g1_ms` — §8's write precedes injection) and **`restore_ms`** (**outside** it — the clipboard restore runs after the text is present). §2's G1 note now says "fully present" fixes the *end* of the window and not only its unit. §6.3's `TextInjector` gains **`warm_up`**, concrete and defaulting to a no-op. §7.3 records that **synthetic keystrokes are rewritten by the target application's text substitution** and that clipboard-manager capture is now measured against a real manager. §9's Phase 2a tray-indicator wording resolved the way Phase 2b resolves the recording indicator. §5.5's engine field reaches `to_history_row`. |
| 2026-08-02 | **The clipboard restore was being charged to G1, and is not in it.** The first real end-to-end dictation reported `g1_ms` **421.9 ms** against a 400 ms budget, with `inject_ms` **180.3 ms** — roughly 150 of which was `restore_delay_ms` sleeping, after the user already had their words. Split correctly, the same path measures **231.6 ms**. `InjectionResult` carries `restore_ms` because `inject()` returns after both and no caller can separate them from outside. Third phase running in which a stage had nowhere to be recorded, so §6.3 now states the rule rather than patching a fourth time. |
| 2026-08-02 | **`TextInjector.warm_up` added, from measurement.** The first `inject()` cost **165.8 ms** and every later one under 2 ms — the pyobjc bridges load on first use, 165 ms against a 400 ms budget, on the user's first dictation. §6.3 gave `TranscriptionEngine` a `warm_up` on that exact argument and left this boundary without one; Phase 2a escaped the cost only because the permission check and the manager detection happen to load both bridges first. Tighter than the engine's contract in one respect: an injector must not type a throwaway character into whatever window has focus. |
| 2026-08-02 | **`strategy = "keystroke"` silently rewrites the transcript** (§7.3). `don't use --dashes... "quoted" and i said so` arrives in TextEdit as `don’t use —dashes… “quoted” and I said so` — five substitutions, from macOS text substitution applying to synthetic keystrokes as it does to real ones. Pasting the same string is byte-identical. The cost lands on §4's privacy-motivated user, who is the person the strategy exists for, and it disqualifies `keystroke` as a *silent* automatic fallback: falling back would trade a visible failure for an invisible corruption. |
| 2026-08-01 | **Phase 1 gate findings applied.** §6.3's `LatencyBreakdown` gains **`vad_ms`** (inside `g1_ms` — G1's clock starts at hotkey release and trimming happens after it) and **`asr_ms`** (the quantity §7.2's tier check actually bounds). §5.3 gains a **`[vad]` table** and states that `[audio] sample_rate` accepts 16000 alone; with `[vad] enabled` deliberately absent, the bounded exception now has three instances in two phases and is restated as a shape rather than a list. §9's Phase 1 gains **`manu install`** — §7.2 specified an install check in six-parameter detail and named no way to run it. §7.2 records that its two CUDA rows split on VRAM with no stated way to measure it, and that Moonshine was benchmarked and declined on its error breakdown (ADR 0001). |
| 2026-08-01 | **§7.2's 1.8× `cpu_threads` penalty corrected.** The 4,413 ms → 2,412 ms figures were measured on `distil-large-v3`, the model the same revision rejected by ~7×. Swept on `tiny.en` over the Phase 1 corpus, 4 threads is **1.02×** of the performance-core count and the optimum is around 6–8 — *below* it. The E-core exclusion is confirmed and is worth more than was claimed: 14 threads costs **2.08×**. `auto` is unchanged, because tuning to 8 would be tuning to n=1 hardware; what changed is the argument the rule rests on. |
| 2026-07-31 | **A1 + A4 accepted.** Tier A is now an absolute measured bar — p50 ≤ 350 ms, p95 ≤ 700 ms on the transcription share, VAD on — rather than a restatement of G1, and §9's Phase 1 gate rejects on G1 missed on the machine the phase is built on, whatever tier it recorded. The previous wording defined Tier A by the same predicate its own gate tested, so §10's top risk had a mitigation with no reachable failing state and the real go/no-go had silently moved to Phase 2b. §7.2 also specifies the install check itself — audio, VAD state, warm-up, nine runs with p95, and the comparison basis — where it previously pointed at a deleted throwaway script. |
| 2026-07-31 | **A2 accepted.** §9's Phase 5 is recorded as **unresolved and corpus-blocked**, not scheduled and not dead. Four approaches were measured against the frozen corpus and none improved WER on any sample; that result is inconclusive rather than negative, because every sample was read from a script and contains no disfluencies. The blocking unknown is stated as a question — do disfluencies survive the decoder — and the pre-failed 700 ms A/B gate is removed until there is something to gate. §7.5's claim that Phase 5 was deferred and nobody was building against it is corrected in place; both clauses were false when written. |
| 2026-07-31 | **A3 accepted.** `model = "auto"` selects **`tiny.en`, int8, VAD on** at 328 ms p50 / 420 ms p95, in one collapsed macOS row. The `base.en` row carried a no-VAD figure from a single clip and contradicted §8, which already assumed `tiny.en`. The undefined "Apple Silicon / CPU" versus "Slower CPU" boundary is gone. WER is declared **macro-average** throughout and the 14.8% micro-weighted figure is withdrawn — the two differ by a third relative and were being used interchangeably across model-selection records. |
| 2026-07-31 | **A6 accepted.** §6.3 gains an explicit completion contract: `DictationSession` carries a `threading.Event`, the worker writes every field before setting it, and that ordering is the only synchronisation rule. The previous text said callers observe completion through the session while the session had no flag, event or lock. The two queues — audio frames and sessions — are now named separately rather than asserted to be one. The overlapping-session hazard the async handoff creates is resolved for v1: a session whose focused application changed between capture and injection is written to history and not injected. |
| 2026-07-31 | **A5 accepted.** G1-CPU is relabelled a **judgement, not a derivation**, and gains a **p95 ≤ 4 000 ms**. The typing comparison establishes that two seconds is not slow; it does not produce two seconds — read strictly it licenses ~27 s, and the clause carrying the decision was "still reading as a tool rather than a batch job". §2's own G2 note two paragraphs above warns against exactly this. The p95 exists because a median-only bar cannot fail on the repetition-looping excursion that is this project's documented failure mode, and G1-CPU decides whether a whole machine class ships. |
| 2026-07-31 | **A7 accepted with revision.** §5.5 now states plainly that **Amanuensis does not claim secure erasure** of the pre-injection transcript — `unlink()` releases blocks exactly as `DELETE` marks pages free, so the original change moved the claim down a layer rather than repairing it. What it genuinely bought (a shared database no longer load-bearing for a privacy promise) is kept. Three gaps closed: the path resolves through `platformdirs` into a named `pending/` directory, orphans from failed injections are swept at daemon start, and `manu history` surfaces them so §8's recovery promise is reachable. |
| 2026-07-31 | **A8 accepted.** `cpu_threads = "auto"` branches on **whether `hw.perflevel0.physicalcpu` resolves**, not on which OS is running, falling back to the total core count. §3 makes macOS the only v1 platform, so the old "elsewhere" branch covered nothing and a homogeneous Mac fell through to CTranslate2's default of 4 — the value whose first probe run returned NO-GO. The efficiency-core exclusion is labelled as generalised from n=1 on a 10P/4E machine, and Phase 1's sweep must cover a second topology. |
| 2026-07-31 | **A9 accepted.** The tier vocabulary is propagated to the four sites still keyed on "accelerated hardware": §4's positioning paragraph, §7.5's Phase 5 budget basis, §9's probe **Rejects if** line, and §9's Phase 4 README instruction. §7.2 retired that category the same day — CTranslate2 has no Metal backend and macOS has no CUDA — which had left the probe's reject condition conditioning on a hardware class with no members, and would have had Phase 4 publish a user-facing distinction the product does not make. |
| 2026-07-31 | **Phase 0 gate findings applied.** §5.3, §5.5 and §5.6 named `~/.config/amanuensis/` and `~/.local/share/amanuensis/` as the *macOS* paths while instructing the implementation to use `platformdirs`, which returns neither on macOS — §7.3's portability floor stated the rule and the same sections wrote down the paths it forbids. All now resolve through `platformdirs`, with `$AMANUENSIS_CONFIG_DIR` / `$AMANUENSIS_DATA_DIR` overrides named, since the location of the config file cannot itself be a config key. |
| 2026-07-31 | **Python floor raised to 3.12** (Phase 0 gate). numpy's type stubs use PEP 695 `type` statements that mypy cannot parse under a 3.11 target, which made the named gate condition `mypy --strict src/` fail on numpy's own stubs before reaching this project's code. §7.0 and §8 updated. |
| 2026-07-31 | **Gate closures are recorded in §9.** Convention established at the Phase 0 gate: a closed gate gets a blockquote under its phase carrying the verdict, the date, and the answer to §9's standing question, while `docs/gates/` stays authoritative for the evidence. §9 is where a reader looks to know what is built, and a phase plan that reads identically before and after the phase ran forces them elsewhere to find out. Applied retroactively to the **probe (GO)** and **Phase 0 (PASS)**, both of which had already closed with no trace in this document. |
| 2026-07-30 | Initial draft |
| 2026-07-30 | Added §14 indexing the four sentinel records. Navigational only — no decision in §1–§13 was amended, and all 29 dispositions remain pending. |
| 2026-07-30 | **O8 accepted.** G1 redefined as hotkey release to *text fully present*, measured by the new `LatencyBreakdown.g1_ms` (§6.3); `total_ms` is diagnostics only. Added the G1 measurement note to §2, including an explicit precedence statement that §2's 10 s budget and §7.1's 15–30 s revisit trigger are separate signals. HARNESS.md corrected to assert against `g1_ms`. |
| 2026-07-30 | **O12 accepted.** Clipboard remains the default injection strategy; the transcript-egress exposure is made visible instead. §7.3 reframes clipboard-manager capture as a privacy surface rather than a restore race, and adds startup detection plus a tray indicator. §5.4 gains the clipboard exposure state; §5.3 gains `[injection] warn_on_clipboard_manager`. §2's G3 row now scopes packet-capture verification to this process only. |
| 2026-07-30 | **O2 accepted.** §1 gains a build-vs-adopt paragraph recording why nerd-dictation (Linux-only) and Talon (voice control, a §3 non-goal) do not close the gap — applying §7's record-the-rejected-alternative discipline to the decision at the top of the tree. |
| 2026-07-30 | **O4 accepted.** A throwaway latency probe is inserted before Phase 0 in §9, answering G1 to an order of magnitude in about an hour. It does not replace the Phase 1 gate and is optimistic by construction. §10's top-risk mitigation updated: a gate positioned after the cost is incurred is a deferral, not a mitigation. |
| 2026-07-30 | **O5 accepted.** Packet capture becomes a gate criterion at Phase 1 (earliest model load, where a cache-miss fetch would fire) and again at Phase 4 (assembled product, new tray and install-path dependency surface). §10 gains a corresponding risk row. G3 previously had a stated verification method and no gate that ran it. |
| 2026-07-30 | **O6 accepted.** v1 is macOS-only. Windows and Linux move to §3 non-goals; §6.2 and §6.4 drop the two injectors and their files; §5.1 loses the Right Alt default; §7.3 changes from "macOS first" to "macOS only"; §11.1 resolved. §6.4 no longer mandates two stub files that made the layout describe a product that does not exist. |
| 2026-07-30 | **O1 accepted.** G1 is tier-conditional: it binds on accelerated hardware (CUDA / Apple Silicon) and does not gate the CPU-only tier, which ships with a measured, published number instead. §9's "stop" scoped accordingly; §10's risk row split in two. Previously §2 and §9 demanded parity while §10 quietly permitted the CPU tier to ship anyway, which meant the gate could not fail. |
| 2026-07-30 | **O11 accepted.** G1 is defined with post-processing off (`chain = ["rules"]`). Phase 5 carries its own budget: p50 ≤ 700 ms, p95 ≤ 1100 ms. §7.5 now states that `max_latency_ms` is a cancellation deadline rather than a predictive check, and that the skip path costs the full ceiling and returns nothing. |
| 2026-07-30 | **O10 accepted.** `[history] enabled` governs retention, not the write. The pre-injection write is unconditional; `false` deletes the row after injection succeeds. §8's guarantee is no longer silently contingent on a config key. Deliberately **not** addressed: `retain_days` and aborted-session retention, which the objection also raised. |
| 2026-07-30 | **O3 accepted.** §7.1 now records pre-release inference — inference during the hold, nothing displayed — as a weighed alternative, deliberately not built for v1. Phase 1's "renegotiate §7.1" instruction previously pointed only at full streaming with retraction, the most expensive available response. |
| 2026-07-30 | **O7 accepted.** G2 is restated as **edit rate ≤ 5%**, matching the Phase 3 gate; WER is no longer the product goal. A small committed desk-mic corpus (`tests/fixtures/asr/`) serves the Phase 1 engine benchmark for *relative* comparison only. The 5% threshold is recorded as **provisional** — inherited from the old WER number, not converted from it — and is confirmed or moved at Phase 3. |
| 2026-07-30 | **O9 accepted.** Every gate in §9 gains a **Rejects if** line, and every gate writes `docs/gates/phase-<n>.md` carrying its measurements, decision, and what the phase revealed that this PRD got wrong. Phase 4's gate also fixes observer conduct in advance so it measures the README rather than the tester. |
| 2026-07-31 | **O6 amended; portability floor added.** Windows moves from a flat §3 non-goal to **post-v1 intent** — it still ships no code in v1 and gates nothing, but §7.3 now carries a four-item portability floor: name the threading model, resolve paths via `platformdirs`, abstract the `manu toggle` IPC transport, and give `HotkeyListener` a factory. Linux remains a plain non-goal. None of the four builds Windows support; all four are the difference between a port and a rewrite. |
| 2026-07-31 | **Concurrency model named** (§6.3), closing choice-story #2 and floor item 1. The daemon is Half-Sync/Half-Async: tray on main, hotkey on the OS event tap, capture on the PortAudio callback, and one worker draining transcribe → post-process → inject. `end_session()` must not block the event-tap thread. Previously unspecified, which meant Phase 2b would have settled it by default. |
| 2026-07-31 | **Choice-story #10 accepted.** `[history] enabled` renamed to **`retain`**. The key now states its own semantics, and §5.5's instruction to read it as retain-rather-than-use is deleted. Free to do before Phase 0; the gloss would otherwise have had to survive into the README, the tray, a settings UI and every validation message. |
| 2026-07-31 | **Choice-story #12 accepted.** The pre-Phase-0 probe now writes `docs/gates/probe.md` — hardware, resolved model, measured time, verdict, and the floor caveat — before its code is deleted. It also gains the *Rejects if* line it was the only gate in §9 to lack. |
| 2026-07-31 | **Choice-story #13 accepted.** §7 gains a **"Where a decision goes"** routing table splitting the six decision surfaces by granularity, with the collision rule *a gate record reports, an ADR decides, §7 governs*. §14's counts are now generated by `scripts/regenerate-sentinel-index.py` and checked in CI. The §7-versus-ADR mutability tension is recorded as standing, not claimed as resolved. |
| 2026-07-31 | **Choice-story #8 accepted.** The hardware tier split is stated as **positioning** in §4 and required in the Phase 4 README, not left in §2's measurement note — §4's privacy-motivated and offline-constrained user correlates with unaccelerated hardware. The CPU tier gains **G1-CPU (provisional): p50 ≤ 2 000 ms**, derived from §4's own not-slower-than-typing bar, and a tier missing it is dropped rather than shipped. |
| 2026-07-31 | **Choice-story #3 accepted.** `AppConfig` becomes a **frozen dataclass from `load_config()`**, passed explicitly — no singleton, no `.get()`. Components receive the narrowest slice they need, so a post-processor structurally cannot read `[injection]`. Phase 0's *Rejects if* now fails on a module-level instance or an ambient accessor. |
| 2026-07-31 | **Choice-story #4 accepted.** The single ABC rationale is restated as **three rules** — replacement, platform selection, composition — each carrying its own contract. `TextPostProcessor` finally gets one: order is significant, `process` is pure with respect to the session, and a mid-chain raise abandons the chain and injects the last good text. |
| 2026-07-31 | **Choice-story #5 accepted.** When `retain = false` the transient transcript goes to a `0600` temp file and never enters `history.db`, rather than relying on SQLite `DELETE` — which marks pages free rather than erasing bytes, making "nothing persists" a claim the mechanism did not support. |
| 2026-07-31 | **Choice-story #7 accepted.** The pre-injection write is **scoped to sessions that reach injection**, so aborted and misfired sessions leave nothing — closing the half of O10 that was deferred. §7.6 now states both artefacts' handling together, including that the asymmetry is justified by durability rather than by transcripts being safe. |
| 2026-07-31 | **Choice-story #1 accepted.** New **§7.0** records the Python decision with its rejected alternatives — the one irreversible commitment in the document, previously the only unargued one. Notes that macOS-only made the Swift-native option *more* attractive without it being reopened, and that the pre-Phase-0 probe ratifies the runtime by default if nobody decides. |
| 2026-07-31 | **Choice-story #6 accepted.** §5.3 gains **one bounded exception**: behaviour a stated guarantee depends on is not user-settable, with §8's persist-before-inject as the first instance. Prefer the exception to another rename — O10 resolved the first collision by redefining a key, which would otherwise have become the precedent. The `[experimental]` tier is *not* adopted; §5.2's flag mechanism gap stays open. |
| 2026-07-31 | **Choice-story #9 accepted.** §7.5 now records that Phase 5's budget is arithmetic rather than chosen, that its own 900 ms tolerance line contradicts the 1100 ms p95, and that the gate cannot fail it by construction. Deliberately unresolved while Phase 5 is deferred — whoever revives it sets the budget from tolerance first and derives `max_latency_ms` from that. |
| 2026-07-31 | **Choice-story #11 accepted.** §7.6 names the **surfacing-versus-preventing doctrine**, including the clause that matters — unless prevention is free *or the user has no viable action* — and records that §7.3 sits at its edge. §7.3's orphaned G3 obligation is assigned to the **Phase 4 gate**: an unqualified "G3 verified" is itself the failure O12 described. |
| 2026-07-31 | **Phase 5 un-deferred, and scoped from measurement.** Reverses slicing record S7, decided earlier the same day. S7 treated the LLM second pass as polish; it is a **core feature of the product §1 measures against**, which S7 could not weigh because §1 names Wispr Flow as the comparison without saying which of its features constitute it. Feasibility measured in `docs/gates/phase5-feasibility.md`: MLX + `Llama-3.2-3B-Instruct-4bit` resolves self-corrections at **278–390 ms**, since MLX has a Metal backend and CTranslate2 does not. **The blocker is fidelity, not latency** — the pass silently rewrites and drops content, so four constraints ship with it: raw transcript persisted, no-invent check, 25% length floor, one-keystroke undo. |
| 2026-07-31 | **VAD filtering is not an optimisation, it prevents catastrophic tails.** Measured: `base.en` on a 25 s sample takes **6,039 ms** without VAD and **541 ms** with it; `small.en` goes 23,886 → 1,438 ms. The cause is decoder repetition looping on silence — `condition_on_previous_text=False` alone recovers most of it. Without VAD **no candidate model passes G1's p95**; with it, `tiny.en` passes both p50 (328 ms) and p95 (420 ms). |
| 2026-07-31 | **Probe amendments 1–5 accepted** (`docs/gates/probe.md`). **§7.2's `model = "auto"` table re-derived from measurement** — the Apple Silicon row selected `distil-large-v3` at 2,412 ms, six times over budget; `base.en` measures 352 ms. Table is marked provisional and selects on latency alone; the model choice is **not** final until the Phase 1 corpus exists. |
| 2026-07-31 | **`cpu_threads` added to §5.3**, defaulting to performance-core count rather than CTranslate2's default of 4 — worth **1.8×**, and the probe's first run returned NO-GO on that default. `device = "mps"` removed; CTranslate2 has no Metal backend, so it was never reachable. |
| 2026-07-31 | **Tiers are now measured, not named after silicon** (§2, §7.2) — revising objection O1. "Apple Silicon" and "CPU only" were the same execution path, and macOS has no CUDA, so the old split would have left **no gated tier at all in v1**. Tier A = measures inside the budget at install; Tier B = does not. O1's reasoning is unchanged; only the axis moved. |
| 2026-07-31 | **VAD silence trimming moved from Phase 3 to Phase 1** (§7.4, §9; slicing record S5's open finding). Whisper's encoder always processes a padded 30-second window, so a 2-second utterance costs nearly what a 25-second one does — trimming is the dominant latency lever, not "a free win", and it changes what Phase 1 measures. |
| 2026-07-31 | **The Phase 1 corpus is built before the engine is chosen** (§9; objection O7). The probe picked `base.en` on latency from one clip by one speaker — enough to prove G1 reachable, not enough to pick a model. |
| 2026-07-31 | **Slicing record disposed; §9 governs the build order.** Phase 2 splits into **2a** (injector, CLI-triggered — Accessibility) and **2b** (hotkey, controller, first full-path G1 — Input Monitoring); the two macOS permission surfaces were previously adjudicated as one. The §8 persist-before-inject write moves into 2a and the minimum recording indicator into 2b, rather than lagging the phases that make them binding. **Phase 5 is deferred indefinitely** — not cut. Slices: 4 merged, 2 accepted, 1 deferred. |
