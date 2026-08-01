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

import pytest

from amanuensis.cli import build_parser, main


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
        build_parser().parse_args(["transcribe"])

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
