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

---

## 2. Goals

| # | Goal | Measurement |
|---|---|---|
| G1 | Text appears fast enough to feel like typing | p50 ≤ 400 ms, p95 ≤ 800 ms from hotkey release to first character injected, for a 10-second utterance |
| G2 | Transcription is accurate enough to not require editing | ≤ 5% WER on clean desk-mic English |
| G3 | Zero network traffic at runtime | Verified by packet capture with the app under load |
| G4 | Works in any focused application | Native fields, Electron apps, terminals, browsers |
| G5 | A developer can read the codebase in an afternoon | Enforced by the structure in §6 |

## 3. Non-goals (v1)

- Real-time streaming transcription with partial results on screen
- Speaker diarization or multi-speaker meeting transcription
- Mobile
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
2. User presses and holds the configured hotkey (default: `Right Option` on macOS,
   `Right Alt` on Windows).
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
│     ├── MacOSInjector
│     ├── WindowsInjector
│     └── LinuxInjector
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
    """Per-stage timings. Required for G1 — every stage records into this."""
    capture_ms: float = 0.0
    transcribe_ms: float = 0.0
    postprocess_ms: float = 0.0
    inject_ms: float = 0.0

    @property
    def total_ms(self) -> float: ...
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
│   │   ├── windows.py
│   │   ├── linux.py
│   │   └── factory.py            # platform detection → injector
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

**Platform assumption:** Phase 2 targets **macOS first**, because its permissions model
(Accessibility + Input Monitoring) is the most restrictive and will surface the hardest
problems earliest. If your daily driver is Windows, swap the order at the Phase 2 gate —
the ABC makes this a scheduling decision, not an architectural one.

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

### Phase 2 — Hotkey and injection (the product becomes real)
`HotkeyListener`, `MacOSInjector` (or Windows, per §7.3), permission checks with actionable
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

### Phase 5 — Optional LLM post-processing
`LocalLLMPostProcessor` with the latency ceiling from §7.5.

**Gate:** A/B against Phase 3 output on the same audio. If quality gain does not justify
measured latency cost, ship it disabled and say so in the README.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| G1 unachievable on CPU-only hardware | High | Phase 1 gate is explicitly a go/no-go. CPU tier may ship with a smaller model and a documented latency expectation rather than a broken promise. |
| macOS permissions are opaque and users get stuck | High | Permission check at startup with copy-pasteable remediation, not a generic failure. |
| Clipboard restore races with clipboard managers | Medium | Document it. Offer `keystroke` strategy. Do not claim it is solved. |
| Electron and Java apps reject synthetic paste | Medium | Enumerate failures at the Phase 2 gate; per-app strategy override if needed. |
| Model download size (~1.5 GB) surprises users | Low | Show size and prompt before download. |
| Scope creep into a meeting-transcription product | Medium | §3 is binding. |

---

## 11. Open decisions

Resolve before or at the stated gate. Do not guess.

1. **Primary OS target** — macOS assumed (§7.3). Confirm at Phase 2 gate.
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
Phase 0 started. Each produced a structured record. **Every disposition in all
three adjudicable records is `pending`** — the sentinels cannot fill them, by
design, and nothing in this PRD has been amended in response to them. Resolving
a disposition is a human act, and the read-only tool boundary on those agents is
what enforces that.

| Record | Path | Entries |
|---|---|---|
| Slicing | `docs/superpowers/slices/amanuensis-prd.md` | 7 slices, 7 pending |
| Objections | `docs/superpowers/objections/amanuensis-prd.md` | 12 objections, 12 pending |
| Choice stories | `docs/superpowers/stories/amanuensis-prd.md` | 10 stories, 10 pending |
| Cost estimate | `cost-estimates/2026-07-30-amanuensis-prd-estimate.md` | not adjudicable |

Two objections are rated **critical** and both bear on §2 and §7.3 — read
`O8` (G1 is not operationally defined against the instrument that measures it)
and `O12` (the default clipboard strategy is an egress path G3's verification
method structurally cannot see) before Phase 0 begins, since both change what
Phase 0 should freeze.

The cost estimate omits a dollar figure: no snapshot exists in
`observability/costs/`, and there is no list-price fallback. Its token figures
are generation-side only and its stated failure direction is `likely-underrun`.

Per §7's own discipline, any of these records that changes a decision here
should produce a dated revision-log entry below — not a silent edit.

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-30 | Initial draft |
| 2026-07-30 | Added §14 indexing the four sentinel records. Navigational only — no decision in §1–§13 was amended, and all 29 dispositions remain pending. |
