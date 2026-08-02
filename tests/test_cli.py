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

from datetime import UTC, datetime

import pytest

from amanuensis.cli import _clipboard_warning, _deliver, build_parser, main
from amanuensis.config import InjectionConfig
from amanuensis.models.results import (
    ClipboardExposure,
    InjectionResult,
    PermissionStatus,
)
from amanuensis.models.session import DictationSession


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


@pytest.mark.parametrize(
    ("verb", "phase"),
    [
        ("daemon", "Phase 2b"),
        ("toggle", "Phase 2b"),
        ("status", "Phase 2b"),
        ("history", "Phase 3"),
    ],
)
def test_each_verb_names_the_phase_that_builds_it(
    verb: str, phase: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([verb])

    assert exit_code != 0
    assert phase in capsys.readouterr().err


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
# Phase 2a — `--inject`, and the §8 ordering it exists to honour
# --------------------------------------------------------------------------


class _SpyHistory:
    """Records the order in which the store was called, and by whom."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.written: list[str] = []

    def write_pending(self, session: object) -> bool:
        transcript = getattr(session, "final_text", None) or getattr(
            session, "raw_transcript", ""
        )
        if not transcript or not transcript.strip():
            return False
        self.calls.append("persist")
        self.written.append(transcript)
        return True

    def mark_injected(self, session: object) -> None:
        self.calls.append("mark")


class _SpyInjector:
    def __init__(
        self,
        calls: list[str],
        *,
        succeeded: bool = True,
        raises: Exception | None = None,
    ) -> None:
        self.calls = calls
        self._succeeded = succeeded
        self._raises = raises
        self.injected: list[str] = []

    def inject(self, text: str) -> InjectionResult:
        self.calls.append("inject")
        if self._raises is not None:
            raise self._raises
        self.injected.append(text)
        return InjectionResult(
            succeeded=self._succeeded,
            strategy="clipboard",
            error=None if self._succeeded else "no permission",
        )

    def check_permissions(self) -> PermissionStatus:
        return PermissionStatus(granted=True)


def _session(text: str = "the small conference room") -> DictationSession:
    return DictationSession(
        id="01J0000000000000000000",
        started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        audio=None,
        sample_rate=16000,
        raw_transcript=text,
    )


def test_the_transcript_is_persisted_before_it_is_injected() -> None:
    """§8, stated as an ordering: *write to history before injection*. This is
    the one invariant in the product that cannot be repaired later — a crash
    between the two costs the user their words, and no amount of correct
    behaviour afterwards gets them back.
    """
    calls: list[str] = []

    _deliver(_session(), _SpyHistory(calls), _SpyInjector(calls))

    assert calls == ["persist", "inject", "mark"]


def test_a_failed_injection_leaves_the_transcript_persisted() -> None:
    """The Phase 2a gate's third reject condition. `mark_injected` is not
    called, so the `retain = false` file is not unlinked and the row is not
    flagged — both paths keep the words."""
    calls: list[str] = []
    history = _SpyHistory(calls)

    result = _deliver(_session(), history, _SpyInjector(calls, succeeded=False))

    assert result.succeeded is False
    assert history.written == ["the small conference room"]
    assert "mark" not in calls


def test_an_injector_that_raises_does_not_cost_the_transcript() -> None:
    """The ABC says `inject` reports rather than raises, and a pyobjc bridge
    is exactly the kind of thing that violates a contract like that. The write
    has already happened, so the words are safe; what this guarantees is that
    the process reports it instead of dying with a traceback."""
    calls: list[str] = []
    history = _SpyHistory(calls)
    injector = _SpyInjector(calls, raises=RuntimeError("NSInternalInconsistency"))

    result = _deliver(_session(), history, injector)

    assert result.succeeded is False
    assert result.error is not None
    assert "NSInternalInconsistency" in result.error
    assert history.written == ["the small conference room"]
    assert "mark" not in calls


def test_the_write_and_the_injection_are_both_timed() -> None:
    """Both are inside G1's clock (§2) — it starts at hotkey release and these
    happen after it. A stage that cannot be measured cannot be defended when
    G1 is missed."""
    session = _session()

    _deliver(session, _SpyHistory([]), _SpyInjector([]))

    assert session.timings.persist_ms > 0.0
    assert session.timings.inject_ms > 0.0


def test_nothing_is_injected_when_there_was_nothing_to_persist() -> None:
    """choice-story #7: a session that never reaches injection leaves nothing
    behind. Pasting an empty string would still clobber the clipboard."""
    calls: list[str] = []

    result = _deliver(_session(text="   "), _SpyHistory(calls), _SpyInjector(calls))

    assert result.succeeded is False
    assert calls == []


# --------------------------------------------------------------------------
# The flag and the exposure warning
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
