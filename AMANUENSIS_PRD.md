# Amanuensis — Product Requirements Document

**Version:** 0.1 (pre-implementation)
**Owner:** Josh Edwards
**Status:** Draft — Phase 0 not started
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
| G1 | Text appears fast enough to feel like typing | p50 ≤ 400 ms, p95 ≤ 800 ms from hotkey release to **text fully present** in the focused application, for a 10-second utterance. Measured as `LatencyBreakdown.g1_ms` (§6.3) — `capture_ms` is excluded. See the G1 measurement note below. |
| G2 | Transcription is accurate enough to not require editing | ≤ 5% WER on clean desk-mic English |
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

## 3. Non-goals (v1)

- Real-time streaming transcription with partial results on screen
- Speaker diarization or multi-speaker meeting transcription
- Mobile
- **Windows and Linux** — v1 is macOS-only (resolved 2026-07-30, objection O6).
  `TextInjector` remains an ABC so the port stays a scheduling decision (§7.3),
  but no phase in §9 builds a second platform and §6.4 no longer stubs the files.
  `injection/factory.py` raises an actionable error naming the unsupported
  platform rather than failing obscurely.
- Cloud sync of history or settings
- Voice commands that control the OS ("open Chrome")
- Text-to-speech (see §12 for where Kokoro actually belongs)

---

## 4. Users

**Primary:** Developers and writers who already know what dictation is, are privacy-motivated
or offline-constrained, and are comfortable with a config file. They will not tolerate a
tool that is slower than typing.

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

Single TOML file at `~/.config/amanuensis/config.toml`. Every behavioral decision in this
PRD that could reasonably go either way is a config key with a sane default. No behavior is
hardcoded that a user might want to change.

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
device = "auto"             # auto | cpu | cuda | mps
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
enabled = true
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
manu toggle    # IPC to the daemon (unix socket) — for external hotkey managers
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

**Abstract bases** define the swap points. Every one of these exists because there is a
real chance we replace the implementation, not for symmetry.

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

`AppConfig` is a singleton loaded once at startup, exposed via `AppConfig.get()`.

### 6.4 Repository layout

```
amanuensis/
├── src/amanuensis/
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py                 # AppConfig singleton, TOML load + validation
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
│   │   └── listener.py
│   ├── storage/
│   │   └── history.py            # HistoryStore
│   └── ui/
│       └── tray.py
├── tests/
├── docs/
│   ├── PRD.md                    # this file
│   ├── HARNESS.md
│   └── adr/                      # architecture decision records
├── pyproject.toml
└── README.md
```

---

## 7. Technical decisions

Each decision records the alternative rejected. If implementation shows a decision was
wrong, bring evidence to the gate and amend this section with a dated note.

### 7.1 Batch transcription, not streaming (v1)

Transcribe the complete buffer on hotkey release. Streaming with partial hypotheses is
what makes competitors feel instant, but it triples complexity — chunk boundary handling,
hypothesis revision, partial-text injection and retraction — and Whisper-family models are
not natively streaming.

**Rejected:** chunked streaming with rolling context. Revisit only if §9 Phase 1 shows
p95 latency missing G1 on realistic 15–30 second utterances.

### 7.2 Engine: faster-whisper default, abstracted

`faster_whisper` (CTranslate2) is the default because it is fast, mature, quantizes well,
and supports CPU and CUDA from one API.

`model = "auto"` resolves as:

| Hardware | Model |
|---|---|
| CUDA, ≥8 GB VRAM | `large-v3-turbo`, float16 |
| CUDA, <8 GB VRAM | `distil-large-v3`, int8_float16 |
| Apple Silicon | `distil-large-v3`, int8 |
| CPU only | `small.en`, int8 |

**Moonshine** is a real alternative on CPU for short utterances and is the reason
`TranscriptionEngine` is an ABC rather than a module of functions. Benchmark it against
`small.en` in Phase 1 and record the result in an ADR.

**Note:** these are pre-implementation estimates from the model cards, not measured on
target hardware. Phase 1 exists to replace them with numbers.

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
the claim accordingly. Whatever gate ends up verifying G3 must cover the
cross-process path or explicitly state that it does not.

**Platform: macOS only for v1** (resolved 2026-07-30, objection O6; §3, §11.1). The
original reasoning stands — macOS's permissions model (Accessibility + Input
Monitoring) is the most restrictive and surfaces the hardest problems earliest — but
"first" implied a second platform that no phase in §9 ever scheduled. Windows and
Linux are now explicit non-goals.

`TextInjector` remains an ABC, so a later port stays a scheduling decision rather
than an architectural one. Two caveats on that claim, since it is no longer load-bearing
for v1 and should not be trusted without evidence: the ABC covers injection only, and
`HotkeyListener`, the tray, and the `manu toggle` unix socket (§6.1) are each
platform-shaped with no equivalent factory. Whoever ports first will find out how
much of the claim was true.

### 7.4 VAD: Silero, optional

Silero VAD via ONNX runtime. Small, fast, no GPU. Used for `vad_auto` mode and to trim
leading/trailing silence before transcription — the latter is a free latency win on every
mode, since Whisper pads to 30-second windows.

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

### 7.6 Security posture

Standard Firebase/cloud rules mostly do not apply — there is no backend, no secrets, no
auth. What does apply:

- No telemetry, no crash reporting, no update check that phones home. If an update check
  is ever added it is opt-in and documented.
- Model weights are downloaded once at install over HTTPS with checksum verification, from
  a pinned revision. Never at runtime.
- History DB is created `0600`. Audio storage defaults off.
- The daemon holds microphone access permanently. Recording state must be unambiguous in
  the UI at all times (§5.4).
- No `eval`/`exec` of anything derived from transcripts. Transcripts are injected as text
  and never interpreted as commands in v1.

---

## 8. Non-functional requirements

| Requirement | Target |
|---|---|
| Idle CPU | < 1% |
| Idle RSS | < 1.5 GB with model resident (GPU) |
| Cold daemon start to ready | < 15 s |
| Recovery from mic disconnect | Automatic, no restart |
| Crash behavior | Never lose a transcript — write to history before injection |
| Python | 3.11+ |

Note the crash-order requirement: persist first, inject second. If injection fails the user
can still recover their words.

---

## 9. Phases

Each phase ends at an approval gate. **Stop at the gate.**

### Probe — Is G1 reachable at all? (before Phase 0)

Added 2026-07-30 (objection O4). A throwaway script — no package, no ABCs, no
config, deliberately not to §6.4 — that loads the `model = "auto"` resolution for
this hardware (§7.2), transcribes a pre-recorded 10-second WAV, and prints the
elapsed transcribe time. Delete it afterwards; it is not a deliverable.

**Gate:** Does transcription complete in a few hundred milliseconds, or in several
seconds? An order of magnitude is all this needs to answer.

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

**Gate:** `manu --help` runs, `mypy --strict src/` is clean, config loads and rejects a
malformed file with a useful error.

### Phase 1 — Prove the ASR path
`AudioCapture`, `FasterWhisperEngine`, warm-up, `LatencyBreakdown`. No hotkey, no injection.
`manu transcribe --seconds 10` records from the mic and prints the transcript plus timings.

**Gate:** Report measured latency on your actual hardware against G1. Benchmark
faster-whisper vs. Moonshine and write `docs/adr/0001-engine-selection.md`. **If G1 is
missed here, stop and renegotiate §7.1 before continuing** — no later phase makes this faster.

**Also at this gate — first G3 verification** (added 2026-07-30, objection O5).
Run the daemon under packet capture through a full transcribe cycle and report
whether any network traffic occurred. This is the earliest point a model loads, and
therefore the earliest point a Hugging Face cache-miss fetch would fire. G3 is the
goal that carries the product premise (§1) and until now no gate verified it.
Confirm the model resolves from a local path, not a repository ID.

### Phase 2 — Hotkey and injection (the product becomes real)
`HotkeyListener`, `MacOSInjector`, permission checks with actionable
error messages, `DictationController` wiring the loop.

**Gate:** Dictate into TextEdit, VS Code, Chrome, and a terminal. Report where it fails.
Confirm clipboard save/restore behavior with a clipboard manager running.

### Phase 3 — Post-processing and history
`RuleBasedPostProcessor`, `VocabularyPostProcessor`, `HistoryStore`, silence trimming via VAD.

**Gate:** Ten real dictations of ≥ 60 seconds. Report edit rate — what fraction of output
needed manual correction, and what kind.

### Phase 4 — Tray, modes, polish
`TrayApp`, `toggle` and `vad_auto` modes, error surfacing, README with the clipboard caveat
documented, install path with checksummed model download.

**Gate:** A second person installs it from the README without your help.

**Also at this gate — second G3 verification** (objection O5). Re-run packet capture
against the assembled product: tray running, install path exercised, checksummed
model download performed. Phase 1 verified a narrower system; this is the last point
before an audience sees it, and the tray toolkit and install path are both new
dependency surface introduced since. Report the result in the README's privacy
section rather than only at the gate.

### Phase 5 — Optional LLM post-processing
`LocalLLMPostProcessor` with the latency ceiling from §7.5.

**Gate:** A/B against Phase 3 output on the same audio. If quality gain does not justify
measured latency cost, ship it disabled and say so in the README.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| G1 unachievable on CPU-only hardware | High | The pre-Phase-0 probe (§9) answers this to an order of magnitude in about an hour, before the scaffold is built; the Phase 1 gate remains the real go/no-go. CPU tier may ship with a smaller model and a documented latency expectation rather than a broken promise. |
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

| Record | Path | State |
|---|---|---|
| Slicing | `docs/superpowers/slices/amanuensis-prd.md` | 7 slices — 7 pending |
| Objections | `docs/superpowers/objections/amanuensis-prd.md` | 12 objections — 6 accepted, 6 pending |
| Choice stories | `docs/superpowers/stories/amanuensis-prd.md` | 10 stories — 10 pending |
| Cost estimate | `cost-estimates/2026-07-30-amanuensis-prd-estimate.md` | not adjudicable |

**Both critical objections are resolved.** `O8` (G1 was not operationally defined
against the instrument built to measure it) and `O12` (the default clipboard
strategy is a transcript-egress path G3's verification structurally cannot see)
are accepted and applied — see the revision log.

**Still open, and worth reading before Phase 0** — `O1` (is G1 tier-conditional,
or does a CPU-tier miss stop the project?), `O3` (§7.1 rejected streaming without
weighing pre-release inference, so the Phase 1 "renegotiate §7.1" instruction
points at only the most expensive option), `O7` (G2's WER corpus is undefined and
no phase measures WER), `O9` (three gates state an activity rather than a pass
condition), `O10` (`[history] enabled = false` silently voids §8's crash
guarantee), `O11` (the LLM latency ceiling is 75% of the p50 budget on its own).

Two further caveats on the records themselves:

- The **choice-story record was drawn concurrently with the objection record**,
  not after it as the pipeline intends, so no story cites an objection ID. It
  should be re-run now that dispositions exist.
- Its Story #9 cites HARNESS.md's "1 of 3 constraints enforced" as evidence;
  that figure has not been re-audited since and may be stale.

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
