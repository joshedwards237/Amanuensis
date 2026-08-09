"""Load, validate, and freeze the user's configuration. Once, at startup.

PRD §5.3 makes a strong commitment: every behavioural decision that could
reasonably go either way is a config key with a sane default, and nothing a
user might want to change is hardcoded. That policy ratchets — the key surface
only grows — and this module is where the cost lands. Three decisions shape it.

**One load, passed explicitly.** `load_config()` returns a frozen `AppConfig`
and that is the only way to get one. There is no `AppConfig.get()` and no
module-level instance. An earlier draft of the PRD specified a singleton *and*
constructor injection one sentence apart — Service Locator beside Dependency
Injection, which is the pattern DI was formulated against — and a reader at
any call site could not tell which instance was in play. Components receive
the narrowest slice they need (`MacOSInjector(cfg.injection)`), so a
post-processor structurally cannot read `[injection]`. That is a boundary, not
a convention (PRD §6.3, choice-story #3).

**Rejection is the interesting path.** The Phase 0 gate says config must
reject a malformed file "with a useful error", and useful is doing real work
in that sentence. A `KeyError` tells a user nothing. Every failure below names
the fully-qualified key, what was expected, and what was found — and unknown
keys are errors rather than being silently ignored, because a typo that is
quietly discarded presents as the feature not working.

**Paths resolve through `platformdirs`, never literals.** Portability floor
item 2 (PRD §7.3): changing a path after users have files on disk is a
migration, not an edit. The two `AMANUENSIS_*_DIR` environment variables exist
so tests and packagers can redirect without a config file — which is the one
setting that cannot live in the config file it locates.

Deliberately *not* here: any defaulting that depends on hardware. `"auto"` is
preserved as the literal string through load and validation, and
`resolve_cpu_threads` is a separate call. A config object that quietly held
`10` on one machine and `4` on another would make a bug report unreadable.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Final

import platformdirs

__all__ = [
    "AppConfig",
    "AudioConfig",
    "ConfigError",
    "EngineConfig",
    "GuardConfig",
    "HistoryConfig",
    "HotkeyConfig",
    "InjectionConfig",
    "LLMConfig",
    "PostprocessConfig",
    "VadConfig",
    "default_config_path",
    "default_data_dir",
    "default_history_path",
    "load_config",
    "resolve_cpu_threads",
]

_APP_NAME: Final = "amanuensis"


class ConfigError(Exception):
    """A configuration file exists but cannot be used as written.

    Carries a message meant to be printed verbatim to a user who is looking at
    their TOML file, not a message meant for a stack trace.
    """


# ---------------------------------------------------------------------------
# The shape — one frozen dataclass per table in PRD §5.3
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    mode: str = "push_to_talk"
    binding: str = "right_option"


@dataclass(frozen=True, slots=True)
class AudioConfig:
    device: str = "default"
    #: 16000 is the only accepted value, despite §5.3 presenting the key as
    #: free. Whisper consumes 16 kHz mono and Silero accepts 8 or 16 kHz; the
    #: intersection is one number. See `_sample_rate` for the rejection.
    sample_rate: int = 16000
    max_duration_seconds: int = 300


@dataclass(frozen=True, slots=True)
class VadConfig:
    """Silence trimming (§7.4). Added in Phase 1; §5.3 had no table for it.

    Note what is absent: there is no `enabled`. §5.3's bounded exception —
    behaviour a stated guarantee depends on is not user-settable — applies,
    because G1 is unreachable without trimming (§7.2: without it no candidate
    model passes p95 at all). A switch for turning it off would be a supported
    way to break a published guarantee.

    The defaults are Silero's, unchanged, because they are the configuration
    the 328/420 ms figures in §7.2 were measured under. Changing one here would
    silently invalidate the number the tier check compares against.
    """

    threshold: float = 0.5
    min_silence_duration_ms: int = 2000
    speech_pad_ms: int = 400


@dataclass(frozen=True, slots=True)
class EngineConfig:
    backend: str = "faster_whisper"
    model: str = "auto"
    device: str = "auto"
    #: "auto" resolves to the performance-core count. NOT the CTranslate2
    #: default of 4, which measured 1.8x slower on a 14-core machine (§7.2).
    cpu_threads: int | str = "auto"
    language: str = "en"
    initial_prompt: str = ""


@dataclass(frozen=True, slots=True)
class GuardConfig:
    """§5.7. Two gates, because one number was doing two jobs.

    Spending a decode and withholding the user's words have costs that differ
    by orders of magnitude, so a single threshold tuned to be safe for the
    second is blind to everything short of total collapse (objection O4).
    """

    #: Refuse to inject below this fraction of retained speech. 0 disables the
    #: guard entirely — permitted here, unlike `[vad] enabled`, because no
    #: stated guarantee depends on it yet and a provisional threshold that can
    #: be wrong about a user must be adjustable by that user.
    min_decoded_coverage: float = 0.5
    #: Re-decode with the vocabulary bias dropped below this. Must be at least
    #: `min_decoded_coverage`, or the guard refuses transcripts it never tried
    #: to recover. 0 never retries.
    #:
    #: Lowered from 0.8 on 2026-08-07 by measurement. The corpus's shortest
    #: genuine sample reads 82.8% even after the padding correction, which left
    #: 2.8 points of headroom — short dictation would have paid a second decode
    #: routinely, and short dictation is the ordinary case here. **Calibrated
    #: against one short sample**, which is thinner evidence than this number
    #: deserves and is why it starts permissive.
    retry_below_coverage: float = 0.7
    #: Predicted from §2's `transcribe_ms ≈ 48.8 + 13.69 × seconds`, not
    #: measured after the fact — the point is to decline the cost, not to
    #: notice it afterwards. The default allows a retry on roughly 140 seconds
    #: of speech and declines on a five-minute dictation.
    retry_max_latency_ms: int = 2000
    #: The fallback floor, used only when an engine cannot report a decoded
    #: span. Inert under faster-whisper. See §5.7's blind spot: under the
    #: fallback, short dictation is unguarded, because word count is an integer
    #: and at two seconds the rate quantises to 0.5 w/s per word.
    min_words_per_second: float = 0.5
    min_audio_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class LLMConfig:
    enabled: bool = False
    model_path: str = ""
    #: Exceeded, the pass is skipped — never queued. Consistently 350 ms and
    #: slightly rougher beats occasionally 900 ms (§5.3, §7.5).
    max_latency_ms: int = 300


@dataclass(frozen=True, slots=True)
class PostprocessConfig:
    #: Ordered. Each processor transforms the same value, so reordering
    #: changes the output (§6.3, composition contract).
    chain: tuple[str, ...] = ("rules",)
    #: Off by default because it is lossy. Also measured to fire **zero times**
    #: on Whisper output — the decoder removes filled pauses during decoding —
    #: so on this engine the key operates on nothing. Kept because a future
    #: engine may be verbatim (§7.5).
    strip_fillers: bool = False
    #: Append "." when the transcript ends on a word character. Fires on 7 of 10
    #: real transcripts, which is why it needs a key rather than being assumed:
    #: it also appends into a URL bar, a shell prompt and a filename field.
    #: Default `true` on measurement — it is the only rule that produced any
    #: movement (strict WER 24.66 -> 24.32), it adds one character, it never
    #: adds a content word, and undoing it costs one keystroke against the 70%
    #: of dictations that otherwise need one added.
    terminal_punctuation: bool = True
    #: "new paragraph" -> a blank line. Off by default because the rule
    #: **deletes content words** and nothing measures it — no take in either
    #: corpus contains one. The processor counts what it *would* have done even
    #: while disabled, so the Phase 3 gate reports a real firing rate rather
    #: than the structural zero a disabled rule would otherwise produce.
    spoken_commands: bool = False
    llm: LLMConfig = LLMConfig()


@dataclass(frozen=True, slots=True)
class InjectionConfig:
    strategy: str = "clipboard"
    restore_clipboard: bool = True
    restore_delay_ms: int = 150
    #: Tray indicator when a known clipboard manager is detected. The
    #: detection list is incomplete by nature and absence of a warning means
    #: "no known manager detected", never "no manager present" (§7.3, O12).
    warn_on_clipboard_manager: bool = True


@dataclass(frozen=True, slots=True)
class HistoryConfig:
    #: Retention, *not* the write. §8's pre-injection write happens
    #: unconditionally; `retain = false` means the transcript never enters
    #: history.db at all and is unlinked once injection succeeds (§5.5).
    retain: bool = True
    retain_days: int = 30
    #: Audio is the sensitive artefact. Off by default.
    store_audio: bool = False


@dataclass(frozen=True, slots=True)
class AppConfig:
    hotkey: HotkeyConfig = HotkeyConfig()
    audio: AudioConfig = AudioConfig()
    vad: VadConfig = VadConfig()
    engine: EngineConfig = EngineConfig()
    guard: GuardConfig = GuardConfig()
    postprocess: PostprocessConfig = PostprocessConfig()
    injection: InjectionConfig = InjectionConfig()
    history: HistoryConfig = HistoryConfig()


# ---------------------------------------------------------------------------
# The schema — declared rather than reflected
# ---------------------------------------------------------------------------
#
# `from __future__ import annotations` makes field annotations strings, so
# reflecting types off the dataclasses would mean parsing them back. Declaring
# the expected types explicitly is duller and produces better messages: the
# error can say "expected int, got str" because it knows both.


@dataclass(frozen=True, slots=True)
class _Rule:
    types: tuple[type, ...]
    #: Returns an explanation when the value is unusable, otherwise None.
    check: Callable[[Any], str | None] | None = None


def _positive(value: Any) -> str | None:
    return None if value >= 1 else "must be 1 or greater"


def _non_negative(value: Any) -> str | None:
    return None if value >= 0 else "must be 0 or greater"


def _one_of(*allowed: str) -> Callable[[Any], str | None]:
    def check(value: Any) -> str | None:
        if value in allowed:
            return None
        return f"must be one of: {', '.join(allowed)}"

    return check


def _cpu_threads(value: Any) -> str | None:
    if isinstance(value, str):
        return None if value == "auto" else 'must be "auto" or a positive integer'
    return None if value >= 1 else 'must be "auto" or a positive integer'


#: The one rate Whisper and Silero both accept. Not a preference — Whisper's
#: feature extractor is built for 16 kHz mono, and Silero ships 8 kHz and
#: 16 kHz heads only. Accepting 44100 would resample somewhere unspecified and
#: quietly change every timing in §7.2.
SUPPORTED_SAMPLE_RATE: Final = 16000


def _sample_rate(value: Any) -> str | None:
    if value == SUPPORTED_SAMPLE_RATE:
        return None
    return (
        f"must be {SUPPORTED_SAMPLE_RATE} — Whisper consumes 16 kHz mono and "
        "Silero VAD accepts 8 or 16 kHz, so this is the only value the pipeline "
        "supports end to end (§7.2, §7.4)"
    )


def _probability(value: Any) -> str | None:
    return None if 0.0 <= value <= 1.0 else "must be between 0.0 and 1.0"


def _non_negative_number(value: Any) -> str | None:
    return None if value >= 0 else "must be 0 or greater"


_PROCESSORS: Final = ("rules", "vocabulary", "llm")


def _chain(value: Any) -> str | None:
    """Membership, uniqueness, and **order**.

    Order was unchecked, and `postprocess/vocabulary.py` states its position as
    a contract: the map must run *after* the rules, because the rules pass
    changes capitalisation and punctuation and would otherwise rewrite the
    replacement. `chain = ["vocabulary", "rules"]` validated, built and ran, and
    turned `csp is the format` into `Csv is the format` — the casing heuristic
    dictionary objection O4 rejected, reached by configuration (objection C10).

    Preserving the user's order is not the same as validating it, and a user who
    lists their processors alphabetically cannot trace the symptom back to this
    line.
    """
    seen: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return f"entries must be strings; found {type(item).__name__}"
        if item not in _PROCESSORS:
            return f"unknown processor {item!r}; known: {', '.join(_PROCESSORS)}"
        if item in seen:
            return f"{item!r} appears twice; each processor runs once"
        seen.append(item)
    ordered = [name for name in _PROCESSORS if name in seen]
    if seen != ordered:
        return (
            f"must be in this order: {', '.join(ordered)}. Post-processing is "
            "ordered and the stages are not interchangeable — the rules pass "
            "rewrites capitalisation and punctuation, so running it after the "
            "vocabulary would rewrite the replacement the dictionary guarantees"
        )
    return None


_SCHEMA: Final[dict[str, dict[str, _Rule]]] = {
    "hotkey": {
        "mode": _Rule((str,), _one_of("push_to_talk", "toggle", "vad_auto")),
        "binding": _Rule((str,)),
    },
    "audio": {
        "device": _Rule((str,)),
        "sample_rate": _Rule((int,), _sample_rate),
        "max_duration_seconds": _Rule((int,), _positive),
    },
    "vad": {
        "threshold": _Rule((float,), _probability),
        "min_silence_duration_ms": _Rule((int,), _non_negative),
        "speech_pad_ms": _Rule((int,), _non_negative),
    },
    "engine": {
        "backend": _Rule((str,), _one_of("faster_whisper", "moonshine", "parakeet")),
        "model": _Rule((str,)),
        "device": _Rule((str,), _one_of("auto", "cpu", "cuda")),
        "cpu_threads": _Rule((int, str), _cpu_threads),
        "language": _Rule((str,)),
        "initial_prompt": _Rule((str,)),
    },
    "guard": {
        "min_decoded_coverage": _Rule((float, int), _probability),
        "retry_below_coverage": _Rule((float, int), _probability),
        "retry_max_latency_ms": _Rule((int,), _non_negative),
        "min_words_per_second": _Rule((float, int), _non_negative_number),
        "min_audio_seconds": _Rule((float, int), _non_negative_number),
    },
    "postprocess": {
        "chain": _Rule((list,), _chain),
        "strip_fillers": _Rule((bool,)),
        "terminal_punctuation": _Rule((bool,)),
        "spoken_commands": _Rule((bool,)),
    },
    "postprocess.llm": {
        "enabled": _Rule((bool,)),
        "model_path": _Rule((str,)),
        "max_latency_ms": _Rule((int,), _positive),
    },
    "injection": {
        "strategy": _Rule((str,), _one_of("clipboard", "keystroke")),
        "restore_clipboard": _Rule((bool,)),
        "restore_delay_ms": _Rule((int,), _non_negative),
        "warn_on_clipboard_manager": _Rule((bool,)),
    },
    "history": {
        "retain": _Rule((bool,)),
        "retain_days": _Rule((int,), _non_negative),
        "store_audio": _Rule((bool,)),
    },
}

_TOP_LEVEL_TABLES: Final = (
    "hotkey",
    "audio",
    "vad",
    "engine",
    "guard",
    "postprocess",
    "injection",
    "history",
)


# ---------------------------------------------------------------------------
# Paths — portability floor item 2
# ---------------------------------------------------------------------------


def default_config_path() -> Path:
    """Where `config.toml` lives on this platform.

    `$AMANUENSIS_CONFIG_DIR` wins when set. It is the one setting that cannot
    be a config key, because it is what finds the config file.
    """
    override = os.environ.get("AMANUENSIS_CONFIG_DIR")
    base = Path(override) if override else Path(platformdirs.user_config_dir(_APP_NAME))
    return base / "config.toml"


def default_data_dir() -> Path:
    """Where per-machine state lives — `history.db`, the recorded tier.

    Split out from `default_history_path` in Phase 1, when the tier check
    became the second thing that needs this directory. Resolving it twice by
    copy-paste is how a `$AMANUENSIS_DATA_DIR` override ends up honoured by one
    caller and not the other.
    """
    override = os.environ.get("AMANUENSIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP_NAME))


def default_history_path() -> Path:
    """Where `history.db` lives on this platform. See `default_config_path`."""
    return default_data_dir() / "history.db"


def resolve_cpu_threads(value: int | str) -> int:
    """Turn `cpu_threads` into a thread count for the engine.

    `"auto"` means the *performance*-core count, not the total core count and
    emphatically not CTranslate2's default of 4 — that default measured 1.8x
    slower on a 14-core machine (§7.2). Handing the decoder efficiency cores
    tends to cost more in scheduling than the cores return.

    Kept out of `load_config` on purpose: the same config file must produce
    the same `AppConfig` on every machine, or a pasted config in a bug report
    stops meaning anything.
    """
    if isinstance(value, int):
        return value

    total = os.cpu_count() or 1
    performance_cores = _macos_performance_cores() if sys.platform == "darwin" else None
    if performance_cores is not None:
        return max(1, min(performance_cores, total))
    return max(1, total)


def _macos_performance_cores() -> int | None:
    """Performance-core count on Apple Silicon, or None if it cannot be read.

    Returns None on Intel Macs, which have no `perflevel` keys, and in any
    sandbox that refuses the call. Neither is worth failing a daemon start
    over — the caller falls back to the total core count.
    """
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.perflevel0.physicalcpu"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return int(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _type_names(types: tuple[type, ...]) -> str:
    return " or ".join(t.__name__ for t in types)


def _validate_scalar(qualified: str, value: Any, rule: _Rule) -> Any:
    # bool is a subclass of int in Python, so `sample_rate = true` would sail
    # through an isinstance check against int and become 1.
    is_bool_mismatch = isinstance(value, bool) and bool not in rule.types
    if is_bool_mismatch or not isinstance(value, rule.types):
        raise ConfigError(
            f"{qualified}: expected {_type_names(rule.types)}, "
            f"got {type(value).__name__} ({value!r})"
        )
    if rule.check is not None:
        problem = rule.check(value)
        if problem is not None:
            raise ConfigError(f"{qualified}: {problem} (got {value!r})")
    return tuple(value) if isinstance(value, list) else value


def _collect(table: str, raw: dict[str, Any], cls: type) -> dict[str, Any]:
    """Validate one table's scalar keys and return them as constructor kwargs.

    Returns kwargs rather than an instance so that a table owning a sub-table
    (`[postprocess.llm]`) can be constructed exactly once, with its child
    already built.
    """
    rules = _SCHEMA[table]
    nested = {f.name for f in fields(cls)} - set(rules)

    values: dict[str, Any] = {}
    for key, value in raw.items():
        if key in nested:
            continue  # a sub-table, built by the caller
        if key not in rules:
            known = ", ".join(sorted(rules))
            raise ConfigError(
                f"{table}.{key}: unknown key. Known keys in [{table}]: {known}"
            )
        values[key] = _validate_scalar(f"{table}.{key}", value, rules[key])

    return values


def _check_coherence(config: AppConfig) -> None:
    """Cross-key rules that no single key can express.

    Caught here rather than at first use: a user who enables the LLM pass and
    forgets the model path should learn that at daemon start, not on the
    utterance where the pass silently does not happen.
    """
    if config.postprocess.llm.enabled and not config.postprocess.llm.model_path:
        raise ConfigError(
            "postprocess.llm.model_path: required when "
            "postprocess.llm.enabled is true"
        )
    if "llm" in config.postprocess.chain and not config.postprocess.llm.enabled:
        raise ConfigError(
            'postprocess.chain: contains "llm" but postprocess.llm.enabled '
            "is false — enable it or remove it from the chain"
        )
    guard = config.guard
    if 0.0 < guard.retry_below_coverage < guard.min_decoded_coverage:
        # The one configuration in which §5.7's flow has no reachable recovery
        # path: the guard would refuse transcripts it never attempted to
        # recover. Zero is exempt because it means "never retry", which is a
        # coherent choice rather than an unreachable one.
        raise ConfigError(
            f"guard.retry_below_coverage ({guard.retry_below_coverage}) is below "
            f"guard.min_decoded_coverage ({guard.min_decoded_coverage}) — the "
            "guard would refuse transcripts it never tried to recover. Set it "
            "to 0 to disable the retry deliberately."
        )


def load_config(path: Path | None = None) -> AppConfig:
    """Read, validate, and freeze the configuration. Call once, at startup.

    A missing file is not an error: every key in §5.3 has a default, so an
    absent `config.toml` is a user who has not needed to change anything.
    A file that exists and is wrong *is* an error, and says why.
    """
    config_path = path if path is not None else default_config_path()

    if not config_path.exists():
        return AppConfig()

    try:
        with config_path.open("rb") as handle:
            raw: dict[str, Any] = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: not valid TOML — {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{config_path}: could not be read — {exc}") from exc

    unknown = set(raw) - set(_TOP_LEVEL_TABLES)
    if unknown:
        known = ", ".join(_TOP_LEVEL_TABLES)
        raise ConfigError(
            f"unknown table(s): {', '.join(sorted(unknown))}. " f"Known tables: {known}"
        )

    for table, value in raw.items():
        if not isinstance(value, dict):
            raise ConfigError(
                f"{table}: expected a table (a [{table}] section), "
                f"got {type(value).__name__}"
            )

    postprocess_raw = dict(raw.get("postprocess", {}))
    llm_raw = postprocess_raw.get("llm", {})
    if not isinstance(llm_raw, dict):
        raise ConfigError(
            "postprocess.llm: expected a table (a [postprocess.llm] section), "
            f"got {type(llm_raw).__name__}"
        )

    config = AppConfig(
        hotkey=HotkeyConfig(**_collect("hotkey", raw.get("hotkey", {}), HotkeyConfig)),
        audio=AudioConfig(**_collect("audio", raw.get("audio", {}), AudioConfig)),
        vad=VadConfig(**_collect("vad", raw.get("vad", {}), VadConfig)),
        engine=EngineConfig(**_collect("engine", raw.get("engine", {}), EngineConfig)),
        guard=GuardConfig(**_collect("guard", raw.get("guard", {}), GuardConfig)),
        postprocess=PostprocessConfig(
            **_collect("postprocess", postprocess_raw, PostprocessConfig),
            llm=LLMConfig(**_collect("postprocess.llm", llm_raw, LLMConfig)),
        ),
        injection=InjectionConfig(
            **_collect("injection", raw.get("injection", {}), InjectionConfig)
        ),
        history=HistoryConfig(
            **_collect("history", raw.get("history", {}), HistoryConfig)
        ),
    )

    _check_coherence(config)
    return config
