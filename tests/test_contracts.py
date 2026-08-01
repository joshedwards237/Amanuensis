"""The swap points: ABCs, the registry, and the two factories.

Phase 0 defines contracts and dispatches to them. It implements none of them.
That is not a gap to be apologised for — it is the deliverable, and these
tests pin the shape so Phase 1 and Phase 2a fill it in rather than redesign it.

PRD §6.3 classifies every ABC as exactly one of three kinds, and the kind
determines the dispatch mechanism:

    Replacement        registry.py, config string -> class    TranscriptionEngine
    Platform selection factory.py, platform detection         TextInjector,
                                                              HotkeyListener
    Composition        ordered chain from `chain = [...]`      TextPostProcessor

An ABC that is none of the three is symmetry and does not get one. The tests
below check both halves: that the abstract methods exist, and that dispatch
fails *informatively* while the implementations are still absent.
"""

from __future__ import annotations

import inspect
from abc import ABC

import pytest

from amanuensis.engines.base import TranscriptionEngine
from amanuensis.engines.registry import UnknownBackendError, resolve_engine
from amanuensis.hotkey.base import HotkeyListener
from amanuensis.hotkey.factory import create_hotkey_listener
from amanuensis.injection.base import TextInjector
from amanuensis.injection.factory import (
    UnsupportedPlatformError,
    create_injector,
)
from amanuensis.postprocess.base import TextPostProcessor


def _abstract_methods(cls: type) -> set[str]:
    return set(getattr(cls, "__abstractmethods__", frozenset()))


# --------------------------------------------------------------------------
# The four ABCs and their required members
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("abc_cls", "expected"),
    [
        (TranscriptionEngine, {"load", "transcribe", "warm_up", "is_loaded"}),
        (TextInjector, {"inject", "check_permissions"}),
        (TextPostProcessor, {"process", "name"}),
        (HotkeyListener, {"start", "stop", "is_running"}),
    ],
)
def test_abc_declares_exactly_its_contract(abc_cls: type, expected: set[str]) -> None:
    assert issubclass(abc_cls, ABC)
    assert _abstract_methods(abc_cls) == expected


@pytest.mark.parametrize(
    "abc_cls",
    [TranscriptionEngine, TextInjector, TextPostProcessor, HotkeyListener],
)
def test_abc_cannot_be_instantiated(abc_cls: type) -> None:
    with pytest.raises(TypeError):
        abc_cls()


def test_postprocessor_process_takes_the_session_it_must_not_mutate() -> None:
    """§6.3: `process` is pure with respect to the session.

    The signature is what makes the chain replayable against a stored
    transcript, and it is the reason a processor cannot reach the audio.
    Every Track 2 candidate satisfies this same signature, which is why the
    contract was safe to freeze before the experiments returned.
    """
    params = list(inspect.signature(TextPostProcessor.process).parameters)

    assert params == ["self", "text", "session"]


# --------------------------------------------------------------------------
# Replacement dispatch — registry.py, config string -> class
# --------------------------------------------------------------------------


def test_unknown_backend_lists_the_ones_that_exist() -> None:
    with pytest.raises(UnknownBackendError) as exc:
        resolve_engine("whisper_cpp")

    message = str(exc.value)
    assert "whisper_cpp" in message
    assert "faster_whisper" in message


def test_a_known_but_unbuilt_backend_says_which_phase_builds_it() -> None:
    """Honest beats convenient: nothing here pretends to be implemented."""
    with pytest.raises(NotImplementedError) as exc:
        resolve_engine("faster_whisper")

    assert "Phase 1" in str(exc.value)


# --------------------------------------------------------------------------
# Platform-selection dispatch — factory.py, one instance per process
# --------------------------------------------------------------------------


def test_injector_factory_rejects_an_unsupported_platform_actionably() -> None:
    with pytest.raises(UnsupportedPlatformError) as exc:
        create_injector(platform="linux")

    message = str(exc.value)
    assert "linux" in message
    assert "macOS" in message


def test_injector_factory_on_macos_says_which_phase_builds_it() -> None:
    with pytest.raises(NotImplementedError) as exc:
        create_injector(platform="darwin")

    assert "Phase 2a" in str(exc.value)


def test_hotkey_factory_mirrors_the_injector_factory() -> None:
    """§7.3 floor item 4 — the ABC the 'real chance we replace it' test was
    never applied to. It gets a factory now, when that costs nothing."""
    with pytest.raises(UnsupportedPlatformError):
        create_hotkey_listener(platform="linux")

    with pytest.raises(NotImplementedError) as exc:
        create_hotkey_listener(platform="darwin")

    assert "Phase 2b" in str(exc.value)


def test_factories_default_to_detecting_the_running_platform() -> None:
    """No caller should have to pass a platform string in production."""
    for factory in (create_injector, create_hotkey_listener):
        default = inspect.signature(factory).parameters["platform"].default
        assert default is None
