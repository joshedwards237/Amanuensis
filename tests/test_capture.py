"""Microphone capture.

`AudioCapture` is the one component in Phase 1 that cannot be tested against
the real thing in CI: opening an input stream on macOS triggers a TCC prompt
and, once granted, records whatever is in the room. So the PortAudio boundary
is faked and what is asserted is the logic on this side of it — device
resolution, the duration cap, and the buffer contract.

The seam is `capture._sounddevice()`, a lazy accessor rather than a top-level
import. That is not a test affordance: importing `sounddevice` loads PortAudio,
which enumerates Core Audio devices and prints to stderr, and `manu --help` has
no business paying for that (the same argument `engines/registry.py` makes about
CTranslate2).

The two behaviours worth stating outright:

- **A device name that matches nothing lists what is available.** A user whose
  Bluetooth headset disconnected gets the device list, not `PortAudioError -9996`.
- **`max_duration_seconds` truncates rather than raising.** A user who walked
  away with the hotkey held gets five minutes of their words, not an exception
  and nothing. PRD §5.3 makes the cap configurable; it does not make exceeding
  it an error.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from amanuensis.audio.capture import AudioCapture, DeviceNotFoundError
from amanuensis.config import AudioConfig

_DEVICES = [
    {"name": "Josh's iPhone Microphone", "max_input_channels": 1},
    {"name": "MacBook Pro Microphone", "max_input_channels": 1},
    {"name": "MacBook Pro Speakers", "max_input_channels": 0},
    {"name": "BoomAudio", "max_input_channels": 6},
]


class _FakeStream:
    """Feeds a fixed block on every read, the way PortAudio's callback would."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.active = False
        self._callback = kwargs["callback"]
        self._blocksize = kwargs.get("blocksize") or 1024

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.active = False

    def __enter__(self) -> _FakeStream:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def feed(self, blocks: int = 1) -> None:
        for _ in range(blocks):
            block = np.full((self._blocksize, 1), 0.25, dtype=np.float32)
            self._callback(block, self._blocksize, None, 0)


class _FakeSoundDevice:
    def __init__(self) -> None:
        self.streams: list[_FakeStream] = []

    def query_devices(self) -> list[dict[str, Any]]:
        return _DEVICES

    def InputStream(self, **kwargs: Any) -> _FakeStream:  # mirrors the sounddevice API
        stream = _FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


@pytest.fixture
def fake_sd(monkeypatch: pytest.MonkeyPatch) -> _FakeSoundDevice:
    fake = _FakeSoundDevice()
    monkeypatch.setattr("amanuensis.audio.capture._sounddevice", lambda: fake)
    return fake


def _capture(**overrides: object) -> AudioCapture:
    return AudioCapture(AudioConfig(**overrides))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Device resolution
# --------------------------------------------------------------------------


def test_the_default_device_defers_to_the_system(fake_sd: _FakeSoundDevice) -> None:
    """`None` means "whatever the user chose in Sound preferences", which is
    almost always what they want and is one fewer thing to keep in sync."""
    assert _capture(device="default").resolve_device() is None


def test_a_device_is_matched_on_a_substring_of_its_name(
    fake_sd: _FakeSoundDevice,
) -> None:
    """PRD §5.3: "or a substring match on device name". Full names are long,
    contain smart quotes, and change between macOS releases."""
    assert _capture(device="MacBook Pro Mic").resolve_device() == 1


def test_matching_ignores_case(fake_sd: _FakeSoundDevice) -> None:
    assert _capture(device="macbook pro mic").resolve_device() == 1


def test_an_output_only_device_is_never_matched(fake_sd: _FakeSoundDevice) -> None:
    """ "MacBook Pro Speakers" contains "MacBook Pro". Matching it would open a
    stream on a device with zero input channels and record nothing, forever."""
    assert _capture(device="MacBook Pro").resolve_device() == 1


def test_an_unmatched_device_lists_what_is_available(
    fake_sd: _FakeSoundDevice,
) -> None:
    with pytest.raises(DeviceNotFoundError) as exc:
        _capture(device="Blue Yeti").resolve_device()

    message = str(exc.value)
    assert "Blue Yeti" in message
    assert "MacBook Pro Microphone" in message


# --------------------------------------------------------------------------
# The buffer contract
# --------------------------------------------------------------------------


def test_a_fresh_capture_is_not_recording(fake_sd: _FakeSoundDevice) -> None:
    assert _capture().is_recording is False


def test_start_then_stop_returns_the_captured_samples(
    fake_sd: _FakeSoundDevice,
) -> None:
    capture = _capture()

    capture.start()
    fake_sd.streams[0].feed(blocks=4)
    audio = capture.stop()

    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert len(audio) == 4 * fake_sd.streams[0]._blocksize
    assert capture.is_recording is False


def test_stopping_without_starting_is_an_error(fake_sd: _FakeSoundDevice) -> None:
    with pytest.raises(RuntimeError):
        _capture().stop()


def test_starting_twice_is_an_error(fake_sd: _FakeSoundDevice) -> None:
    capture = _capture()
    capture.start()

    with pytest.raises(RuntimeError):
        capture.start()


def test_capturing_nothing_yields_an_empty_array_not_none(
    fake_sd: _FakeSoundDevice,
) -> None:
    """A tapped-and-released hotkey. Downstream decides what to do with an
    empty utterance; capture does not decide it by returning `None`."""
    capture = _capture()
    capture.start()

    audio = capture.stop()

    assert isinstance(audio, np.ndarray)
    assert len(audio) == 0


def test_the_duration_cap_truncates_rather_than_raising(
    fake_sd: _FakeSoundDevice,
) -> None:
    """A user who walked away with the hotkey held keeps their words."""
    capture = _capture(sample_rate=16_000, max_duration_seconds=1)

    capture.start()
    fake_sd.streams[0].feed(blocks=40)  # ~2.5 s at 1024 samples per block
    audio = capture.stop()

    assert len(audio) == 16_000


def test_the_stream_is_opened_at_the_configured_rate_in_mono(
    fake_sd: _FakeSoundDevice,
) -> None:
    """16 kHz mono float32 is what Whisper and Silero both require; §5.3
    presents `sample_rate` as free and it is not (see test_config)."""
    capture = _capture()

    capture.start()

    kwargs = fake_sd.streams[0].kwargs
    assert kwargs["samplerate"] == 16_000
    assert kwargs["channels"] == 1
    assert kwargs["dtype"] == "float32"


def test_record_captures_for_a_fixed_duration(
    fake_sd: _FakeSoundDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`manu transcribe --seconds 10` (PRD §9, Phase 1) has no hotkey to
    release, so it needs a bounded record rather than start/stop."""
    capture = _capture()

    def fake_sleep(_seconds: float) -> None:
        fake_sd.streams[0].feed(blocks=3)

    monkeypatch.setattr("amanuensis.audio.capture.time.sleep", fake_sleep)

    audio = capture.record(seconds=0.2)

    assert len(audio) == 3 * fake_sd.streams[0]._blocksize
    assert capture.is_recording is False
