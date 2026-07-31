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

   > **G1-CPU (provisional): p50 ≤ 2 000 ms**, same measurement basis as G1.
   > A Tier B machine class that misses this is dropped in §3 rather than shipped.

   The derivation, since the number should not be a guess: §4's own bar is that
   the tool must not be "slower than typing." A 10-second utterance is roughly
   25 words; at 40 wpm that is ~37 seconds to type. Two seconds is comfortably
   inside that while still reading as a tool rather than a batch job. Like G2's
   5%, this is **provisional** — Phase 1 confirms or moves it with a stated
   reason in `docs/gates/phase-1.md`. It is a floor for shipping the tier at
   all, not a claim that 2 000 ms feels good.

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
implementation detail** (2026-07-31, choice-story #8). G1's budgets bind on accelerated
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

Single TOML file at the platform config directory (`platformdirs`; `~/.config/amanuensis/config.toml`
on macOS — see §7.3's portability floor). Every behavioral decision in this PRD that could
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
sample_rate = 16000
max_duration_seconds = 300

[engine]
backend = "faster_whisper"  # faster_whisper | moonshine | parakeet
model = "auto"              # "auto" resolves per §7.2
device = "auto"             # auto | cpu | cuda
cpu_threads = "auto"        # "auto" = performance-core count. NOT the library
                            # default of 4 — see §7.2. Worth ~1.8x.
language = "en"
initial_prompt = ""         # biases vocabulary; see §5.6

[postprocess]
chain = ["rules"]           # ordered: rules | llm
strip_fillers = false       # "um", "uh" — off by default, it is lossy

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

### 5.4 Feedback

The user must always know whether the mic is live. Non-negotiable — a dictation tool that
is ambiguous about recording state is a privacy problem regardless of where the audio goes.

- Tray/menubar icon state: idle / recording / transcribing / error
- Optional audio cue on start and stop (`[feedback] sounds = true`)
- Recording state must be visible without the tray menu open
- **Clipboard exposure state** — when `strategy = "clipboard"` and a known
  clipboard manager is detected, the tray carries a persistent indicator that
  transcripts transit the system clipboard (§7.3, objection O12). Same
  reasoning as recording state: a privacy-relevant condition the user cannot
  see is a privacy problem regardless of whether it is ever exercised.

### 5.5 History

Local SQLite at `~/.local/share/amanuensis/history.db`. Stores timestamp, transcript,
duration, engine, and latency breakdown. Audio is **not** stored unless explicitly enabled.
`manu history --purge` wipes it.

Latency breakdown is a product requirement, not a debugging nicety — G1 cannot be defended
without per-stage timings.

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
2. A post-processing replacement map (`~/.config/amanuensis/vocabulary.toml`) applying
   case-insensitive whole-word substitutions.

Both. They fail in different places.

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
    error: str | None = None

    def duration_seconds(self) -> float: ...
    def to_history_row(self) -> dict: ...
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
    transcribe_ms: float = 0.0
    postprocess_ms: float = 0.0
    inject_ms: float = 0.0

    @property
    def g1_ms(self) -> float:
        """transcribe + postprocess + inject. The number G1 is gated on."""

    @property
    def total_ms(self) -> float:
        """Every stage including capture. Diagnostics only — never assert G1 on this."""
```

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
  the chain is abandoned and the **last good text** proceeds to injection. §8's
  persist-before-inject ordering already ran, so the words survive regardless; the
  error is surfaced in the tray (§5.4) and recorded, not swallowed silently.

`TranscriptionEngine` got `load` / `warm_up` / `is_loaded` because someone thought about
its lifecycle. This is that thinking for the boundary that will actually grow — rules,
vocabulary, and whatever the Phase 3 edit-rate report demands.

```python
class TranscriptionEngine(ABC):
    @abstractmethod
    def load(self) -> None:
        """Called once at daemon start. Blocking. Must be idempotent."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...

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
```

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
    ) -> None: ...

    def start_session(self) -> None: ...
    def end_session(self) -> DictationSession: ...
    def abort_session(self) -> None: ...
```

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

Consequences that follow, and are therefore requirements rather than choices:

- `DictationController`'s methods are called from the event-tap thread and **must not
  block it**. `end_session()` hands the buffer to the worker and returns; it does not
  wait for transcription. The `-> DictationSession` return in the contract above is the
  session object, populated asynchronously — callers observe completion through the
  session, not by the call returning.
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
│   │   └── listener.py
│   ├── storage/
│   │   └── history.py            # HistoryStore
│   └── ui/
│       └── tray.py
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

> **Tier A** — the selected model transcribes a 10-second utterance inside G1's
> budget on this machine. **G1 binds and is gated.**
>
> **Tier B** — it does not. **G1-CPU applies** (§2): the number is measured,
> published, and told to the user at install; it does not halt the project.

The tier is decided **once, at install**, by running the same measurement the
pre-Phase-0 probe ran, and recorded. It is not re-derived per session — a machine
that is momentarily busy must not flip tiers, and a machine near the boundary
must not oscillate. `manu status` reports the recorded tier; re-running the
install check is how it changes.

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
| CUDA, ≥8 GB VRAM | `large-v3-turbo`, float16 | — | estimate, **unmeasured** |
| CUDA, <8 GB VRAM | `distil-large-v3`, int8_float16 | — | estimate, **unmeasured** |
| Apple Silicon / CPU | `base.en`, int8 | **352 ms** | *measured*, M3 Max, n=1 |
| Slower CPU | `tiny.en`, int8 | **190 ms** | *measured*, M3 Max, n=1 |

`distil-large-v3` — the previous Apple Silicon selection — measured **2,412 ms**,
six times over budget on an M3 Max. That row was a model-card guess and it was
wrong by roughly 7×.

**This table is provisional and selects on latency alone.** `base.en` was not
detectably worse than `distil-large-v3` on the probe sample, but that is **one
speaker, one room, one microphone, one paragraph**. Accuracy has no measurement
yet (objection O7). **Do not finalise the model choice until the Phase 1 corpus
exists** — doing so would repeat, on the accuracy axis, exactly the mistake this
revision is correcting on the latency axis.

#### `cpu_threads` is load-bearing and was never specified

Added 2026-07-31. CTranslate2 defaults to **4 threads**. On a 14-core M3 Max that
default measured 4,413 ms; setting `cpu_threads` to the performance-core count
took the identical model to 2,412 ms. **A 1.8× factor**, from a parameter this
PRD did not mention.

The first run of the pre-Phase-0 probe returned **NO-GO on that default**. The
project's top risk (§10) would have fired on a library default rather than on
physics.

`cpu_threads = "auto"` resolves to the **performance-core count**, not the total
core count and not the library default. On macOS that is
`sysctl -n hw.perflevel0.logicalcpu`; elsewhere, physical cores. Efficiency cores
are deliberately excluded — scheduling inference across heterogeneous cores
typically costs more than it returns. The value was not tuned beyond "match the
performance cores" and is not claimed optimal; Phase 1 should sweep it.

Note `device = "mps"` was removed from §5.3's options. CTranslate2 has no Metal
backend, so it was never a reachable value.

**Moonshine** is a real alternative on CPU for short utterances and is the reason
`TranscriptionEngine` is an ABC rather than a module of functions. Benchmark it in
Phase 1 against `base.en` — not `small.en`, which the probe showed is 2.2× over
budget — and record the result in an ADR.

### 7.3 Injection: clipboard paste, with a keystroke fallback

Synthesizing keystrokes character-by-character is too slow for a 300-character paragraph
and breaks in applications with input debouncing. Clipboard write + synthetic paste is
near-instant and format-safe.

**The cost, stated plainly:** it clobbers the user's clipboard. Mitigate by saving and
restoring, but restoration races with clipboard manager apps — the manager may capture the
transcript before restore lands. This is a known, unavoidable leak of the strategy, and it
must be documented in the README rather than papered over.

`strategy = "keystroke"` exists for users who cannot accept that.

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
2. **No hardcoded XDG paths.** §5.3 and §5.5 name `~/.config/amanuensis/` and
   `~/.local/share/amanuensis/` as the macOS locations. Resolve them through
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
  enabled, on the same accelerated-hardware and measurement basis as G1. The
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

This is not resolved now because Phase 5 is deferred (§9) and nobody is building against
it, and because the evidence to decide — a real Phase 3 edit rate showing what rules
could not fix — does not exist yet. **Whoever revives Phase 5 sets the budget from
tolerance first and derives `max_latency_ms` from it, not the reverse.** If §7.5's own
900 ms line is taken as binding, the implied ceiling is nearer 100–200 ms, and the
honest conclusion may be that the pass does not fit. That is worth knowing before
building it rather than after.

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
| Python | 3.11+ |

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

### Probe — Is G1 reachable at all? (before Phase 0)

Added 2026-07-30 (objection O4). A throwaway script — no package, no ABCs, no
config, deliberately not to §6.4 — that loads the `model = "auto"` resolution for
this hardware (§7.2), transcribes a pre-recorded 10-second WAV, and prints the
elapsed transcribe time. Delete it afterwards; it is not a deliverable.

**Gate:** Does transcription complete in a few hundred milliseconds, or in several
seconds? An order of magnitude is all this needs to answer.

**Rejects if:** transcription of a 10-second utterance takes longer than the CPU-tier
bar in §2 on *accelerated* hardware. That would mean the accelerated path is slower
than the floor set for the unaccelerated one, which is not a slow result — it is a
broken setup, and no amount of Phase 0 scaffolding fixes it.

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

### Phase 1 — Prove the ASR path
`AudioCapture`, `FasterWhisperEngine`, warm-up, `LatencyBreakdown`, VAD silence trimming
(§7.4), the install-time tier check (§7.2). No hotkey, no injection.
`manu transcribe --seconds 10` records from the mic and prints the transcript plus timings.

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

**Rejects if:** G1 is missed on a Tier A machine. A Tier B miss does not reject; it is
recorded and published.

**Also at this gate — first G3 verification** (added 2026-07-30, objection O5).
Run the daemon under packet capture through a full transcribe cycle and report
whether any network traffic occurred. This is the earliest point a model loads, and
therefore the earliest point a Hugging Face cache-miss fetch would fire. G3 is the
goal that carries the product premise (§1) and until now no gate verified it.
Confirm the model resolves from a local path, not a repository ID.

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

### Phase 2b — Close the loop with the hotkey

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

### Phase 3 — Post-processing and history
`RuleBasedPostProcessor`, `VocabularyPostProcessor`, `HistoryStore`, silence trimming via VAD.

**Gate:** Ten real dictations of ≥ 60 seconds. Report edit rate — what fraction of output
needed manual correction, and what kind.

**Rejects if:** edit rate exceeds the G2 threshold **and** the corrections are
dominated by classes the rules chain should have caught (punctuation, capitalisation,
spoken commands). An edit rate driven by proper nouns points at §5.6's vocabulary
mechanisms, not at a phase failure.

This is also where G2's provisional 5% threshold is confirmed or moved (§2). Moving it
is a legitimate outcome; moving it without stating the reason in the gate record is
not.

### Phase 4 — Tray, modes, polish
`TrayApp`, `toggle` and `vad_auto` modes, error surfacing, README with the clipboard caveat
documented, install path with checksummed model download.

The README also carries the **per-tier latency table** — the accelerated G1 figures and
the CPU-tier G1-CPU figure, each labelled with the hardware it applies to (§2, §4,
choice-story #8) — and the privacy section from §9's Phase 4 G3 verification.

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

### Phase 5 — LLM second pass — **UN-DEFERRED 2026-07-31**

Deferred earlier the same day (slicing record S7) on the reasoning that it blocks
nothing and its budget cannot be failed by construction. **That disposition is
reversed**, for a reason S7 did not weigh: the second pass is not polish, it is a
**core feature of the product §1 measures against**. A verbatim transcriber and a tool
that resolves your self-corrections are different products, and a user comparing them
will not grade on the distinction.

Feasibility is measured, not assumed — `docs/gates/phase5-feasibility.md`. Summary: an
MLX-backed `Llama-3.2-3B-Instruct-4bit` resolves self-corrections correctly at
**278–390 ms** on Apple Silicon, because **MLX has a Metal backend and CTranslate2 does
not** — the second pass runs on the GPU the transcription cannot use.

**The blocker is fidelity, not latency.** The measured failure mode is that the pass
*rewrites* rather than merely cleaning: it dropped "on it" from one input and "let's
meet" from another, silently. In a dictation tool that is strictly worse than leaving
fillers in — a user can see and delete an "um", but cannot see a clause removed before
the text reached the screen. Same hazard class as §7.3's clipboard exposure, and it
falls under §7.6's surfacing-versus-preventing doctrine.

Four constraints therefore ship *with* the feature, not after it:

1. **The pre-injection write stores the RAW transcript** (§8), never the cleaned one.
2. **No-invent check**: if cleaned output contains content words absent from the raw
   transcript, discard it and inject raw. Deletion is intended; insertion is a
   hallucination.
3. **Length floor**: if cleaning removes more than ~25% of content words, treat it as
   over-editing and fall back to raw.
4. **One-keystroke undo to the raw text**, because the user cannot know what was removed.

Constraints 2 and 3 are cheap deterministic checks wrapped around a probabilistic step.
They convert the failure mode from silent corruption into a visible no-op. The `[postprocess.llm]` config block stays reserved.

`LocalLLMPostProcessor` with the latency ceiling from §7.5.

**Gate:** A/B against Phase 3 output on the same audio. If quality gain does not justify
measured latency cost, ship it disabled and say so in the README.

Measure against **Phase 5's own budget** — p50 ≤ 700 ms, p95 ≤ 1100 ms with the pass
enabled (§7.5, objection O11) — not against G1, which is defined with the pass off.
Report how often the cancellation deadline fires and the pass is discarded, since a
cancelled pass costs the full ceiling and returns nothing; a high cancellation rate is
the signal to ship disabled.

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
Phase 0 started. Each produced a structured record. The sentinels cannot fill a
disposition — resolving one is a human act, and their read-only tool boundary is
what enforces that. Every amendment made in response appears in the revision log
below; none was made silently.

<!-- BEGIN sentinel-index (generated) -->
| Record | Path | State |
|---|---|---|
| Slicing | `docs/superpowers/slices/amanuensis-prd.md` | 7 slices — 3 accepted, 4 merged |
| Objections — `amanuensis-prd-2026-07-31-amendments` | `docs/superpowers/objections/amanuensis-prd-2026-07-31-amendments.md` | 9 objections — 9 pending |
| Objections — `amanuensis-prd` | `docs/superpowers/objections/amanuensis-prd.md` | 12 objections — **all accepted** |
| Choice stories | `docs/superpowers/stories/amanuensis-prd.md` | 13 stories — **all accepted** |
| Cost estimate | `cost-estimates/2026-07-30-amanuensis-prd-estimate.md` | not adjudicable |
<!-- END sentinel-index (generated) -->

<!-- Regenerate with: python3 scripts/regenerate-sentinel-index.py
     Counts are parsed from each record's YAML frontmatter, never from prose.
     Do not hand-edit the rows above; they are overwritten. -->

**Both critical objections are resolved.** `O8` (G1 was not operationally defined
against the instrument built to measure it) and `O12` (the default clipboard
strategy is a transcript-egress path G3's verification structurally cannot see)
are accepted and applied — see the revision log.

**All twelve objections are now disposed as accepted**, and every amendment is in
the revision log. The through-line across them: this document was better at defining
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
