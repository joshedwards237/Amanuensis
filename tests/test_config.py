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
    default_config_path,
    default_history_path,
    load_config,
    resolve_cpu_threads,
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
