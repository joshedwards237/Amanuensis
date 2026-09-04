"""Configuration loading, validation, and path resolution.

These tests encode the Phase 0 gate conditions from PRD §9 that concern
config: it loads, it rejects a malformed file with a *useful* error, no path
is hardcoded, and `config.py` exposes neither a module-level instance nor an
ambient accessor.

The "useful error" condition is the one worth stating carefully. A gate that
only checked "raises something" would pass on a bare `KeyError`, which tells a
user nothing about which key in which table of their TOML file is wrong. Every
rejection test below asserts on the *content* of the message, because that is
the property the gate actually cares about.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from amanuensis import config as config_module
from amanuensis.config import (
    AppConfig,
    ConfigError,
    VadConfig,
    default_config_path,
    default_history_path,
    load_config,
    resolve_cpu_threads,
    write_hotkey_binding,
)

# --------------------------------------------------------------------------
# Defaults — every key in PRD §5.3 has one, and a missing file is not an error
# --------------------------------------------------------------------------


def test_missing_file_yields_the_documented_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")

    assert cfg.hotkey.mode == "push_to_talk"
    assert cfg.hotkey.binding == "right_option"
    assert cfg.audio.sample_rate == 16000
    assert cfg.audio.max_duration_seconds == 300
    assert cfg.engine.backend == "faster_whisper"
    assert cfg.engine.model == "auto"
    assert cfg.engine.cpu_threads == "auto"
    assert cfg.postprocess.chain == ("rules",)
    assert cfg.postprocess.strip_fillers is False
    assert cfg.postprocess.llm.enabled is False
    assert cfg.injection.strategy == "clipboard"
    assert cfg.injection.warn_on_clipboard_manager is True
    assert cfg.history.retain is True
    assert cfg.history.store_audio is False


def test_partial_file_overrides_only_what_it_names(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[engine]\nmodel = "small.en"\n')

    cfg = load_config(path)

    assert cfg.engine.model == "small.en"
    assert cfg.engine.backend == "faster_whisper"  # untouched
    assert cfg.audio.sample_rate == 16000  # untouched table entirely


# --------------------------------------------------------------------------
# §6.3 — frozen, passed explicitly, no singleton, no ambient accessor
# --------------------------------------------------------------------------


def test_config_is_frozen_all_the_way_down(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")

    for obj in (
        cfg,
        cfg.hotkey,
        cfg.audio,
        cfg.engine,
        cfg.postprocess,
        cfg.postprocess.llm,
        cfg.injection,
        cfg.history,
    ):
        assert dataclasses.is_dataclass(obj)
        with pytest.raises(dataclasses.FrozenInstanceError):
            # Nested config objects have no attribute in common, so mutate
            # whichever field the dataclass declares first.
            field_name = dataclasses.fields(obj)[0].name
            setattr(obj, field_name, "mutated")


def test_config_module_exposes_no_instance_and_no_ambient_accessor() -> None:
    """PRD §9 rejects Phase 0 outright if either of these exists."""
    assert not hasattr(AppConfig, "get")

    instances = [
        name
        for name, value in vars(config_module).items()
        if isinstance(value, AppConfig)
    ]
    assert instances == [], f"module-level AppConfig instance(s): {instances}"


# --------------------------------------------------------------------------
# §7.3 portability floor item 2 — paths resolve through platformdirs
# --------------------------------------------------------------------------


def test_paths_are_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AMANUENSIS_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path / "data"))

    assert default_config_path() == tmp_path / "cfg" / "config.toml"
    assert default_history_path() == tmp_path / "data" / "history.db"


def test_paths_fall_back_to_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMANUENSIS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AMANUENSIS_DATA_DIR", raising=False)

    cfg_path = default_config_path()
    db_path = default_history_path()

    assert cfg_path.name == "config.toml"
    assert db_path.name == "history.db"
    # The whole point of the floor: no literal ~/.config or ~/.local in there.
    assert ".local/share" not in str(db_path) or "Application Support" in str(db_path)


# --------------------------------------------------------------------------
# Rejection — a malformed file fails with an error that names the problem
# --------------------------------------------------------------------------


def test_malformed_toml_names_the_file_and_the_parse_failure(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[engine\nmodel = broken")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert str(path) in message
    assert "line" in message.lower()


def test_unknown_table_is_rejected_and_listed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[engien]\nmodel = "tiny.en"\n')

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "engien" in message
    assert "engine" in message  # the valid names are shown


def test_unknown_key_is_rejected_with_its_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[engine]\ncpu_thread = 8\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "engine.cpu_thread" in message
    assert "cpu_threads" in message


def test_wrong_type_names_the_key_and_both_types(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[audio]\nsample_rate = "sixteen thousand"\n')

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "audio.sample_rate" in message
    assert "int" in message
    assert "str" in message


def test_invalid_enum_value_lists_the_permitted_ones(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[hotkey]\nmode = "double_tap"\n')

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "hotkey.mode" in message
    assert "push_to_talk" in message
    assert "vad_auto" in message


def test_a_negative_double_tap_window_is_refused_rather_than_read_as_off(
    tmp_path: Path,
) -> None:
    """Two spellings of one behaviour is how a user concludes a key is inert.

    A negative window is arithmetically indistinguishable from `0` everywhere
    `hotkey/macos.py` reads it -- `held >= window` is true for any hold and any
    tap -- so it would silently disable §5.2's latch while reading as a setting
    that was chosen. §5.3 gives `0` that meaning explicitly and this refuses
    the other route to it.
    """
    path = tmp_path / "config.toml"
    path.write_text("[hotkey]\ndouble_tap_ms = -1\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "hotkey.double_tap_ms" in message
    assert "0 to disable" in message, "the refusal must name the way to turn it off"


def test_zero_double_tap_window_is_accepted_as_the_documented_way_off(
    tmp_path: Path,
) -> None:
    """The negative control on the check above. A refusal that also rejected
    the documented value would be a check nobody could satisfy."""
    path = tmp_path / "config.toml"
    path.write_text("[hotkey]\ndouble_tap_ms = 0\n")

    assert load_config(path).hotkey.double_tap_ms == 0


def test_out_of_range_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[audio]\nsample_rate = 0\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    assert "audio.sample_rate" in str(exc.value)


def test_cpu_threads_accepts_auto_or_a_positive_int(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    path.write_text("[engine]\ncpu_threads = 10\n")
    assert load_config(path).engine.cpu_threads == 10

    path.write_text('[engine]\ncpu_threads = "auto"\n')
    assert load_config(path).engine.cpu_threads == "auto"

    path.write_text("[engine]\ncpu_threads = 0\n")
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "engine.cpu_threads" in str(exc.value)


def test_unknown_postprocessor_in_the_chain_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[postprocess]\nchain = ["rules", "magic"]\n')

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "postprocess.chain" in message
    assert "magic" in message


def test_llm_enabled_without_a_model_path_is_incoherent(tmp_path: Path) -> None:
    """Catching this at load time beats discovering it on the first utterance."""
    path = tmp_path / "config.toml"
    path.write_text("[postprocess.llm]\nenabled = true\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    assert "model_path" in str(exc.value)


# --------------------------------------------------------------------------
# `cpu_threads = "auto"` — PRD §7.2, worth ~1.8x over the library default of 4
# --------------------------------------------------------------------------


def test_resolve_cpu_threads_passes_an_explicit_count_through() -> None:
    assert resolve_cpu_threads(6) == 6


def test_resolve_auto_returns_a_positive_count_below_the_core_count() -> None:
    import os

    resolved = resolve_cpu_threads("auto")

    assert resolved >= 1
    assert resolved <= (os.cpu_count() or 1)


# --------------------------------------------------------------------------
# [vad] — added in Phase 1
# --------------------------------------------------------------------------
#
# PRD §7.4 specifies Silero trimming and §5.3 has no table for it, which is the
# gap Phase 1 closed. The interesting part is what is *not* a key.


def test_vad_defaults_match_the_configuration_the_probe_measured(
    tmp_path: Path,
) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")

    assert cfg.vad.threshold == 0.5
    assert cfg.vad.min_silence_duration_ms == 2000
    assert cfg.vad.speech_pad_ms == 400


def test_there_is_no_switch_for_turning_trimming_off() -> None:
    """§5.3's bounded exception: behaviour a stated guarantee depends on is not
    user-settable.

    G1 is unreachable without trimming — every candidate model misses p95
    outright (§7.2, §7.4). A `vad.enabled = false` key would therefore be a
    supported way to break a published guarantee, which is precisely the shape
    of key the exception exists to refuse. Persist-before-inject was the first
    instance; this is the second.
    """
    assert not hasattr(VadConfig(), "enabled")


def test_a_threshold_outside_the_probability_range_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[vad]\nthreshold = 1.5\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    assert "vad.threshold" in str(exc.value)


def test_an_unknown_vad_key_names_the_ones_that_exist(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[vad]\nenabled = false\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "vad.enabled" in message
    assert "threshold" in message


# --------------------------------------------------------------------------
# [audio] sample_rate is not the free choice §5.3 presents it as
# --------------------------------------------------------------------------


def test_a_sample_rate_other_than_16k_is_rejected_with_both_reasons(
    tmp_path: Path,
) -> None:
    """Phase 1 finding. Whisper consumes 16 kHz mono and Silero accepts 8 or
    16 kHz; 16000 is the only value both allow. §5.3 offers the key as though
    any positive integer worked, and a user who set 44100 would previously have
    got a resampled, mistimed pipeline rather than an error.
    """
    path = tmp_path / "config.toml"
    path.write_text("[audio]\nsample_rate = 44100\n")

    with pytest.raises(ConfigError) as exc:
        load_config(path)

    message = str(exc.value)
    assert "audio.sample_rate" in message
    assert "16000" in message


# ---------------------------------------------------------------------------
# §5.7 — the [guard] block
# ---------------------------------------------------------------------------


def test_guard_defaults() -> None:
    cfg = AppConfig()
    assert cfg.guard.min_decoded_coverage == 0.5
    assert cfg.guard.retry_below_coverage == 0.7
    assert cfg.guard.retry_max_latency_ms == 2000
    # The fallback floor, inert under faster-whisper.
    assert cfg.guard.min_words_per_second == 0.5
    assert cfg.guard.min_audio_seconds == 5.0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("min_decoded_coverage", -0.1),
        ("min_decoded_coverage", 1.5),
        ("retry_below_coverage", -0.1),
        ("retry_below_coverage", 1.5),
        ("min_words_per_second", -1.0),
        ("min_audio_seconds", -0.5),
        ("retry_max_latency_ms", -1),
    ],
)
def test_out_of_range_guard_values_are_rejected(
    tmp_path: Path, key: str, value: float
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[guard]\n{key} = {value}\n")
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert key in str(caught.value)


def test_a_retry_gate_below_the_refusal_gate_is_rejected(tmp_path: Path) -> None:
    """A retry threshold under the refusal threshold means the guard refuses
    transcripts it never tried to recover — the one configuration in which the
    §5.7 flow has no reachable recovery path."""
    path = tmp_path / "config.toml"
    path.write_text("[guard]\nmin_decoded_coverage = 0.6\nretry_below_coverage = 0.3\n")
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert "retry_below_coverage" in str(caught.value)


def test_a_zero_gate_is_accepted_because_it_is_the_off_switch(tmp_path: Path) -> None:
    """§5.7: the thresholds are provisional and coverage removes the *known*
    false-positive population without proving there is none. A threshold that
    can be wrong about a user must be adjustable by that user — which is why
    §5.3's bounded exception does not withhold this key."""
    path = tmp_path / "config.toml"
    path.write_text("[guard]\nmin_decoded_coverage = 0.0\n")
    assert load_config(path).guard.min_decoded_coverage == 0.0


def test_retry_below_zero_is_accepted_as_never_retry(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[guard]\nretry_below_coverage = 0.0\n")
    assert load_config(path).guard.retry_below_coverage == 0.0


# ---------------------------------------------------------------------------
# [feedback] — §5.4's keys, specified 2026-07-30 and built 2026-09-02
# ---------------------------------------------------------------------------


def test_feedback_defaults() -> None:
    """§5.4 referenced `[feedback] sounds` for three phases with no such block.

    `overlay` is on because it is the affordance the operator asked for after
    finding the glyph insufficient, and a privacy affordance that ships off is
    one nobody sees. `sounds` is off and quarantined under §5.3's rule: nothing
    has measured how a cue on every dictation reads over a working day.
    """
    feedback = AppConfig().feedback
    assert feedback.overlay is True
    assert feedback.overlay_position == "bottom"
    assert feedback.sounds is False


def test_feedback_parses_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[feedback]\noverlay = false\noverlay_position = "top"\nsounds = true\n'
    )
    feedback = load_config(path).feedback
    assert feedback.overlay is False
    assert feedback.overlay_position == "top"
    assert feedback.sounds is True


def test_feedback_rejects_an_unknown_position(tmp_path: Path) -> None:
    """The overlay must not cover the caret, and "middle" has no meaning."""
    path = tmp_path / "config.toml"
    path.write_text('[feedback]\noverlay_position = "middle"\n')
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "overlay_position" in str(exc.value)


def test_feedback_rejects_a_wrong_type(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[feedback]\noverlay = "yes"\n')
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "overlay" in str(exc.value)


def test_feedback_rejects_an_unknown_key(tmp_path: Path) -> None:
    """A typo that silently does nothing is how `store_audio` did nothing."""
    path = tmp_path / "config.toml"
    path.write_text("[feedback]\noverlays = true\n")
    with pytest.raises(ConfigError):
        load_config(path)


# ---------------------------------------------------------------------------
# Writing one key back — the tray's hotkey picker (2026-09-03)
# ---------------------------------------------------------------------------


def test_writing_the_binding_preserves_everything_else(tmp_path: Path) -> None:
    """The operator's `config.toml` is hand-written and full of comments that
    explain why each value is what it is. A round-trip through a TOML library
    would drop every one of them, so this edits the line and nothing else."""
    path = tmp_path / "config.toml"
    original = (
        "# my notes\n"
        "[hotkey]\n"
        'mode = "push_to_talk"\n'
        'binding = "right_option"   # because it is under my thumb\n'
        "\n"
        "[engine]\n"
        'model = "auto"\n'
    )
    path.write_text(original)

    write_hotkey_binding(path, "right_shift")

    after = path.read_text()
    assert 'binding = "right_shift"' in after
    assert "# my notes" in after
    assert "# because it is under my thumb" in after, "the comment was lost"
    assert 'mode = "push_to_talk"' in after
    assert 'model = "auto"' in after
    assert load_config(path).hotkey.binding == "right_shift"


def test_writing_the_binding_adds_the_key_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[hotkey]\nmode = "toggle"\n')
    write_hotkey_binding(path, "fn")
    assert load_config(path).hotkey.binding == "fn"
    assert load_config(path).hotkey.mode == "toggle"


def test_writing_the_binding_adds_the_table_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[engine]\nmodel = "auto"\n')
    write_hotkey_binding(path, "left_option")
    assert load_config(path).hotkey.binding == "left_option"
    assert load_config(path).engine.model == "auto"


def test_writing_the_binding_creates_the_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.toml"
    write_hotkey_binding(path, "right_command")
    assert load_config(path).hotkey.binding == "right_command"


def test_an_unknown_binding_is_refused_before_the_file_is_touched(
    tmp_path: Path,
) -> None:
    """Writing a value the listener will reject leaves a daemon that cannot
    start, and the user's only clue is a config file they did not hand-edit."""
    path = tmp_path / "config.toml"
    path.write_text('[hotkey]\nbinding = "right_option"\n')
    with pytest.raises(ConfigError):
        write_hotkey_binding(path, "the_spacebar")
    assert 'binding = "right_option"' in path.read_text(), "the file was modified"


def test_a_binding_in_a_later_table_is_not_mistaken_for_the_hotkey(
    tmp_path: Path,
) -> None:
    """`binding` is a plausible key name elsewhere. A naive line match would
    rewrite the wrong table's value and leave the hotkey untouched."""
    path = tmp_path / "config.toml"
    path.write_text(
        "[engine]\n"
        'model = "auto"\n'
        "\n"
        "[hotkey]\n"
        'binding = "right_option"\n'
    )
    write_hotkey_binding(path, "fn")
    text = path.read_text()
    assert text.index("[hotkey]") < text.index('binding = "fn"')
    assert load_config(path).hotkey.binding == "fn"
