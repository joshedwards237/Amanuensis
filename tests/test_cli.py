"""The `manu` command surface.

`manu --help` running cleanly is a named Phase 0 gate condition (PRD §9), so
it gets a test rather than a manual check. The subcommands exist and are
wired to argparse; each one refuses to run and names the phase that builds it.

The alternative — omitting the subcommands until their phase — was rejected
because §6.1 treats the four-verb surface as the process model's public
contract. A CLI that grows verbs one phase at a time is a CLI whose shape is
decided by implementation order.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from amanuensis.cli import (
    _clipboard_warning,
    _keystroke_warning,
    build_parser,
    main,
)
from amanuensis.config import InjectionConfig, default_data_dir
from amanuensis.models.results import ClipboardExposure


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0


def test_version_exits_zero_and_prints_a_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


@pytest.mark.parametrize("verb", ["daemon", "toggle", "status", "history"])
def test_the_four_verbs_from_the_process_model_all_parse(verb: str) -> None:
    """§6.1 fixes the verb set. Asserted through the public parse path rather
    than by reaching into argparse internals, which change between releases."""
    assert build_parser().parse_args([verb]).verb == verb


def test_an_invented_verb_is_rejected() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["dictate"])

    assert exc.value.code != 0


def test_no_subcommand_prints_usage_and_fails() -> None:
    assert main([]) != 0


@pytest.fixture
def short_data_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """A data directory short enough for `sun_path`.

    `conftest` isolates `$AMANUENSIS_DATA_DIR` into pytest's tmp tree, which is
    129 bytes deep — past the kernel's 104-byte limit for a unix socket. The
    transport refuses that with a sentence rather than a bare `OSError`, which
    is correct behaviour and not what these tests are about.
    """
    import shutil
    import tempfile

    made = Path(tempfile.mkdtemp(prefix="amn", dir="/tmp"))
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(made))
    yield made
    shutil.rmtree(made, ignore_errors=True)


@pytest.mark.parametrize("verb", ["toggle", "status"])
def test_a_verb_with_no_daemon_says_so_and_says_how(
    verb: str, capsys: pytest.CaptureFixture[str], short_data_dir: Path
) -> None:
    """Both verbs shipped in Phase 4, and this test replaces the one asserting
    they were unbuilt.

    §7.6's third requirement is the content: "nothing is listening" and "the
    daemon says it is idle" are different facts, and reporting the first as the
    second is a claim about the microphone nobody checked. So a missing daemon
    is an error with a non-zero exit and a next step, not a shrug.

    It runs against `$AMANUENSIS_DATA_DIR` in a temp directory — `conftest`
    already redirects it — so it can never reach a daemon the operator has
    running, and never starts one.
    """
    exit_code = main([verb])

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "not running" in err.lower()
    assert "manu daemon" in err, "the error must name the next step"


def test_toggle_and_status_name_the_transport_they_are_waiting_on(
    short_data_dir: Path,
) -> None:
    """Recorded at the Phase 2b gate: §9's Phase 2b names the listener, the
    controller and the indicator, and does not name these two. Both need the
    IPC transport §7.3 lists as portability floor item 3, which no phase ever
    scheduled — so they move to Phase 4, which owns `toggle` mode and the tray.

    Asserted here rather than left as prose, because the previous value said
    Phase 2b and this phase is the one that would have shipped the lie. The
    assertion moved from a phase label to the transport itself once Phase 4
    built them.
    """
    from amanuensis.ipc.factory import create_transport

    # The socket is not in the CLI contract — §7.3 floor item 3 — so the thing
    # asserted is that a transport resolves at all, not what kind it is.
    transport = create_transport()
    assert transport.path.name == "daemon.sock"
    assert transport.path.parent == default_data_dir(), (
        "the socket lives beside history.db so one $AMANUENSIS_DATA_DIR "
        "override moves both; see choice-story #2"
    )


def test_a_bad_config_is_reported_as_an_error_not_a_traceback(
    tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """A user with a typo in their TOML gets a sentence, not a stack trace."""
    path = tmp_path / "config.toml"  # type: ignore[operator]
    path.write_text('[hotkey]\nmode = "double_tap"\n')

    exit_code = main(["--config", str(path), "status"])

    assert exit_code != 0
    assert "hotkey.mode" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Phase 1's two new verbs
# --------------------------------------------------------------------------
#
# The module preamble above says §6.1 fixes the verb set at four, and Phase 1
# proves that wrong twice over: PRD §9 names `manu transcribe --seconds 10` as
# a Phase 1 deliverable, and §7.2 specifies an install-time tier check without
# naming any way to invoke it. Both are recorded in docs/gates/phase-1.md. The
# §6.1 claim was about the *daemon's* process model, and neither of these verbs
# talks to a daemon — `transcribe` is a one-shot diagnostic and `install` is a
# setup step that runs before a daemon exists.


@pytest.mark.parametrize("verb", ["transcribe", "install"])
def test_the_phase_1_verbs_parse(verb: str) -> None:
    assert build_parser().parse_args([verb]).verb == verb


def test_transcribe_defaults_to_the_utterance_length_g1_is_defined_against() -> None:
    """PRD §2 binds G1 to a ten-second utterance, so that is the default and
    `--seconds` is how you depart from it."""
    assert build_parser().parse_args(["transcribe"]).seconds == 10.0


def test_transcribe_rejects_a_non_positive_duration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["transcribe", "--seconds", "0"]) != 0
    assert "seconds" in capsys.readouterr().err


def test_install_can_skip_the_download_it_already_did() -> None:
    """§7.2: model download is not part of the timed check. Re-running the
    check to re-measure a tier should not re-fetch 75 MB of weights."""
    assert build_parser().parse_args(["install", "--skip-download"]).skip_download


def test_transcribe_reports_a_bad_config_as_a_sentence(
    tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "config.toml"  # type: ignore[operator]
    path.write_text("[vad]\nthreshold = 2.0\n")

    exit_code = main(["--config", str(path), "transcribe"])

    assert exit_code != 0
    assert "vad.threshold" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Phase 2a — `--inject`, and the flag and warnings around it
#
# The §8 ordering tests moved to `test_controller.py` in Phase 2b, with the
# function. `deliver` was written here because `DictationController` did not
# exist; it does now, and a guarantee tested only where it used to live is a
# guarantee with a phase-shaped hole in it.
# --------------------------------------------------------------------------


def test_transcribe_does_not_inject_unless_asked() -> None:
    """Phase 1's diagnostic behaviour is the default. `--inject` is opt-in
    because typing into whatever window happens to be focused is not something
    to do by surprise."""
    args = build_parser().parse_args(["transcribe"])

    assert args.inject is False


def test_the_inject_flag_parses() -> None:
    args = build_parser().parse_args(["transcribe", "--inject"])

    assert args.inject is True


def test_a_detected_clipboard_manager_is_named_in_the_warning() -> None:
    """§5.4 requires the exposure be visible, and §7.3 requires it name the
    application — "a clipboard manager is running" is not actionable."""
    warning = _clipboard_warning(
        InjectionConfig(), ClipboardExposure(detected=True, manager="Maccy")
    )

    assert warning is not None
    assert "Maccy" in warning


def test_the_warning_is_silenced_by_the_config_key_that_exists_for_it() -> None:
    """§7.3 adds `warn_on_clipboard_manager` for users who have read the README
    and accepted the trade."""
    warning = _clipboard_warning(
        InjectionConfig(warn_on_clipboard_manager=False),
        ClipboardExposure(detected=True, manager="Maccy"),
    )

    assert warning is None


def test_no_known_manager_produces_no_warning_and_no_all_clear() -> None:
    """The absence of a warning must not read as "no manager present" (§7.3,
    objection O12). Printing an all-clear would state exactly the thing the
    detection cannot know."""
    warning = _clipboard_warning(InjectionConfig(), ClipboardExposure(detected=False))

    assert warning is None


def test_the_keystroke_strategy_has_no_clipboard_exposure_to_warn_about() -> None:
    """§5.4 scopes the indicator to `strategy = "clipboard"`. Warning a user
    who already chose the slower strategy to avoid this exact exposure would
    be telling them their mitigation did not work."""
    warning = _clipboard_warning(
        InjectionConfig(strategy="keystroke"),
        ClipboardExposure(detected=True, manager="Maccy"),
    )

    assert warning is None


def test_the_keystroke_strategy_warns_that_the_target_may_rewrite_the_text() -> None:
    """Measured at the Phase 2a gate: synthetic keystrokes are subject to the
    *target application's* text substitution. Into TextEdit,

        don't use --dashes... "quoted" and i said so

    arrives as

        don't use —dashes… "quoted" and I said so

    — smart quotes, em dash, ellipsis and autocapitalisation, five changes in
    one sentence. Clipboard paste of the same string is byte-identical.

    §7.3 offers `keystroke` to users who cannot accept the clipboard exposure,
    and describes its cost as being slower and more failure-prone. Silent
    rewriting is a different and larger cost, and it lands on the
    privacy-motivated primary user of §4 — the one who chose this strategy.
    Nothing in Amanuensis can suppress another application's substitution
    settings, so the only honest response is to say so.
    """
    warning = _keystroke_warning(InjectionConfig(strategy="keystroke"))

    assert warning is not None
    assert "substitution" in warning.lower()


def test_the_clipboard_strategy_has_nothing_to_warn_about_here() -> None:
    """Paste is byte-identical — measured, not assumed."""
    assert _keystroke_warning(InjectionConfig(strategy="clipboard")) is None


# --------------------------------------------------------------------------
# Phase 2b — `manu daemon`
#
# Only the paths that return *before* anything is opened are tested here. The
# happy path takes the microphone, installs a machine-wide event tap and blocks
# in an AppKit run loop; a test that exercised it would be a test that recorded
# the developer. It is measured by dogfooding at the gate instead, which is
# what §9 asks for anyway.
# --------------------------------------------------------------------------


def test_the_daemon_refuses_an_unsupported_binding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before the model loads, before the tap, before the microphone. §5.3
    leaves `binding` a free string, so this is where a typo is caught."""
    monkeypatch.setenv("AMANUENSIS_CONFIG_DIR", "/nonexistent")
    from amanuensis.cli import _daemon
    from amanuensis.config import AppConfig, HotkeyConfig

    exit_code = _daemon(AppConfig(hotkey=HotkeyConfig(binding="f13")))

    assert exit_code != 0
    assert "f13" in capsys.readouterr().err


def test_the_daemon_refuses_a_mode_it_does_not_implement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Accepting an unknown mode and behaving as push-to-talk would be a
    configured mode silently doing something else.

    **Rewritten 2026-09-02, and the reason is worth keeping.** This test used
    to pass `mode="toggle"` and assert the daemon refused it as unbuilt. Phase 4
    built `toggle`, so the refusal it depended on went away — and the test did
    not fail. It *hung*: `_daemon` ran on, loaded the model, opened the
    microphone and blocked in the AppKit run loop, in a pytest process, on the
    operator's machine.

    A test written against a refusal becomes a test that exercises the thing
    the moment the refusal is lifted, and it does not announce itself when it
    does. The mode named here is one nothing will ever implement.
    """
    from amanuensis.cli import _daemon
    from amanuensis.config import AppConfig, HotkeyConfig

    exit_code = _daemon(AppConfig(hotkey=HotkeyConfig(mode="telepathy")))

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "telepathy" in err
    assert "push_to_talk" in err, "the error must name a mode that works"


def test_the_daemon_reports_both_missing_permissions_at_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accessibility and Input Monitoring are separate grants in separate
    panes. A user who fixes one, restarts, and is then told about the other has
    been sent to System Settings twice for a condition fully known the first
    time."""
    from amanuensis.cli import _daemon
    from amanuensis.config import AppConfig
    from amanuensis.hotkey import macos as macos_hotkey
    from amanuensis.injection import macos as macos_injection

    class _Denied:
        def CGPreflightPostEventAccess(self) -> bool:
            return False

        def CGPreflightListenEventAccess(self) -> bool:
            return False

    monkeypatch.setattr(macos_injection, "_quartz", _Denied)
    monkeypatch.setattr(macos_hotkey, "_quartz", _Denied)

    exit_code = _daemon(AppConfig())

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "Accessibility" in err
    assert "Input Monitoring" in err


def test_a_second_daemon_is_refused_before_it_takes_the_microphone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """§9's single-instance guard, asserted at the position that makes it one.

    The transport has refused a second bind since it was written; what was
    wrong was *when* `_daemon` reached it. The bind lived at `control.serve`,
    below `create_hotkey_listener`, `AudioCapture`, `TrayApp` and
    `controller.start` — so the second daemon installed an event tap, opened
    the microphone and added a second status item, and only then discovered it
    should not exist. §5.4 calls that intermediate state a privacy problem on
    its own: the indicator on one daemon reads *idle* while the other records.

    So this asserts an ordering, not a return code. The autouse
    `_no_real_microphone` guard raises if `AudioCapture` is ever constructed
    for real, and `TrayApp` is monkeypatched to raise — either one firing means
    the refusal came too late. A test that only checked the exit code would
    have passed against the broken order, because the broken order also exits
    non-zero, just after taking three things it should not have.
    """
    from amanuensis.cli import _daemon
    from amanuensis.config import AppConfig
    from amanuensis.hotkey import macos as macos_hotkey
    from amanuensis.injection import macos as macos_injection
    from amanuensis.ipc import factory as ipc_factory
    from amanuensis.ipc.macos import UnixSocketTransport
    from amanuensis.ui import tray as tray_module

    class _Granted:
        def CGPreflightPostEventAccess(self) -> bool:
            return True

        def CGPreflightListenEventAccess(self) -> bool:
            return True

    monkeypatch.setattr(macos_injection, "_quartz", _Granted)
    monkeypatch.setattr(macos_hotkey, "_quartz", _Granted)

    def _too_late(*args: object, **kwargs: object) -> None:
        raise AssertionError("the tray was built before the guard refused")

    monkeypatch.setattr(tray_module, "TrayApp", _too_late)

    # A short path: sun_path is 104 bytes and pytest's tmp tree is 129.
    holder_dir = Path(tempfile.mkdtemp(prefix="amn", dir="/tmp"))
    incumbent = UnixSocketTransport(holder_dir / "d.sock")
    incumbent.claim()
    monkeypatch.setattr(
        ipc_factory, "create_transport", lambda: UnixSocketTransport(incumbent.path)
    )
    try:
        exit_code = _daemon(AppConfig())
    finally:
        incumbent.stop()
        shutil.rmtree(holder_dir, ignore_errors=True)

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "already listening" in err
    assert "manu status" in err, "the refusal must name a next step"


# ---------------------------------------------------------------------------
# §5.7 / objection O2 — `manu history --last`
# ---------------------------------------------------------------------------


def test_bare_history_lists_rather_than_refusing(capsys: Any) -> None:
    """Phase 3 built the rest of the verb, so the refusal is gone.

    Rewritten 2026-08-08. It previously asserted `main(["history"]) == 1` and
    "Phase 3" on stderr, which was correct while only `--last` had been pulled
    forward by objection O2. Left as it was, it would have been a test asserting
    a feature does not work.
    """
    assert main(["history"]) == 0

    assert "no transcripts yet" in capsys.readouterr().out


def test_history_last_prints_the_transcript(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    from datetime import UTC, datetime

    from amanuensis.config import HistoryConfig
    from amanuensis.models.session import DictationSession
    from amanuensis.storage.history import HistoryStore

    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))
    HistoryStore(HistoryConfig(), data_dir=tmp_path).write_pending(
        DictationSession(
            id="01J",
            started_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            audio=None,
            sample_rate=16000,
            raw_transcript="the words the guard would not inject",
        )
    )

    assert main(["history", "--last"]) == 0

    assert "the words the guard would not inject" in capsys.readouterr().out


def test_history_last_says_when_the_guard_refused(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Handing back the words without saying why they were withheld leaves the
    user with no way to act on it."""
    from datetime import UTC, datetime

    from amanuensis.config import HistoryConfig
    from amanuensis.models.results import GuardOutcome, GuardVerdict
    from amanuensis.models.session import DictationSession
    from amanuensis.storage.history import HistoryStore

    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))
    HistoryStore(HistoryConfig(), data_dir=tmp_path).write_pending(
        DictationSession(
            id="01J",
            started_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            audio=None,
            sample_rate=16000,
            raw_transcript=" For Tenants.",
            guard=GuardVerdict(
                outcome=GuardOutcome.FAILED,
                retained_seconds=30.5,
                coverage=0.0656,
                reason="the decoder covered 7% of 30.5s of speech",
            ),
        )
    )

    assert main(["history", "--last"]) == 0

    out = capsys.readouterr().out
    assert "not injected" in out
    assert "For Tenants." in out


def test_history_last_says_so_when_there_is_nothing(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))

    assert main(["history", "--last"]) == 0

    assert "no transcripts" in capsys.readouterr().out.lower()


def test_a_data_dir_too_deep_for_a_socket_is_a_sentence_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`sun_path` is 104 bytes on macOS and the kernel's own error names
    nothing. `$AMANUENSIS_DATA_DIR` is user-set and can easily exceed it —
    pytest's own tmp tree does, which is how this was found.
    """
    exit_code = main(["status"])  # conftest's isolated data dir is 129 bytes

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "AMANUENSIS_DATA_DIR" in err
    assert "Traceback" not in err
