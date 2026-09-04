"""Microphone capture.

The daemon holds the microphone permanently (§6.1), which is a privacy claim
before it is a performance one — §5.4 makes "the user must always know whether
the mic is live" non-negotiable *regardless of where the audio goes*. This
module is deliberately the dumb end of that: it opens a stream, accumulates
float32 samples, and hands back an array. It does not decide when to record,
does not know what a hotkey is, and does not transcribe.

Three decisions are worth stating.

**PortAudio is imported lazily.** `import sounddevice` loads the PortAudio
shared library, which enumerates Core Audio devices and can write to stderr
before any Python code runs. `manu --help` must not pay that, and neither
should a config error. Same argument `engines/registry.py` makes about
CTranslate2, and the accessor `_sounddevice()` is what the tests fake.

**The duration cap truncates; it does not raise.** `[audio]
max_duration_seconds` exists because a hotkey can be held by accident — a user
who walked away mid-sentence should get five minutes of their words, not an
exception and nothing. PRD §5.3 makes the cap configurable; it does not make
exceeding it an error.

**An unmatched device name lists the devices that exist.** A user whose
Bluetooth headset dropped off gets a list they can copy a name out of, not
`PortAudioError -9996`. This costs one `query_devices` call on a path that has
already failed.

What this module does *not* do: resample, convert channels, or apply gain. It
opens the stream at the one rate the rest of the pipeline accepts (`config.py`
pins `[audio] sample_rate` to 16000 — Whisper and Silero agree on nothing else)
and lets Core Audio do the conversion in the driver, where it is done properly.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import AudioConfig

__all__ = ["AudioCapture", "DeviceNotFoundError"]

#: Frames per PortAudio callback. 1024 at 16 kHz is 64 ms — small enough that
#: the tail of an utterance is not lost to a partially-filled block, large
#: enough that the callback is not the thing costing CPU during recording.
_BLOCKSIZE = 1024


class DeviceNotFoundError(Exception):
    """`[audio] device` names a microphone this machine does not have."""


def _sounddevice() -> Any:
    """Import PortAudio at the point of use, never at module import."""
    import sounddevice

    return sounddevice


class AudioCapture:
    """Records from one input device into a float32 mono buffer.

    Not thread-safe by accident — the callback runs on PortAudio's own thread
    and appends to `_blocks` under a lock, because `stop()` reads that list
    from the caller's thread. The lock is held for a list append and nothing
    else; a callback that blocks is a callback that drops audio.
    """

    def __init__(self, config: AudioConfig) -> None:
        self._observer: Callable[[NDArray[np.float32]], None] | None = None
        self._config = config
        self._stream: Any | None = None
        self._blocks: list[NDArray[np.float32]] = []
        self._lock = threading.Lock()
        self._max_samples = config.max_duration_seconds * config.sample_rate

    def set_observer(
        self, observer: Callable[[NDArray[np.float32]], None] | None
    ) -> None:
        """Watch blocks as they arrive. Used by `hotkey.mode = "vad_auto"`.

        The observer runs on the PortAudio callback thread and must be short
        for the same reason `_on_block` is: this thread has a deadline, and
        missing it costs audio.
        """
        with self._lock:
            self._observer = observer

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def resolve_device(self) -> int | None:
        """Turn `[audio] device` into a PortAudio index, or None for the default.

        `None` means "whatever the user chose in Sound preferences", which is
        both what most users want and one fewer thing to keep in sync with the
        system. Anything else is a case-insensitive substring match on the
        device name (§5.3), restricted to devices that actually have inputs —
        "MacBook Pro Speakers" contains "MacBook Pro", and matching it would
        open a stream that records nothing, forever, with no error.
        """
        wanted = self._config.device
        if wanted == "default":
            return None

        devices = _sounddevice().query_devices()
        needle = wanted.casefold()
        inputs = [
            (index, device)
            for index, device in enumerate(devices)
            if device["max_input_channels"] > 0
        ]
        for index, device in inputs:
            if needle in str(device["name"]).casefold():
                return index

        available = "\n".join(f"  - {device['name']}" for _, device in inputs)
        raise DeviceNotFoundError(
            f"audio.device: no input device matching {wanted!r}.\n"
            f"Input devices on this machine:\n{available}"
        )

    def start(self) -> None:
        """Open the stream and begin accumulating. Non-blocking."""
        if self._stream is not None:
            raise RuntimeError("capture is already running; call stop() first")

        with self._lock:
            self._blocks = []

        stream = _sounddevice().InputStream(
            samplerate=self._config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=_BLOCKSIZE,
            device=self.resolve_device(),
            callback=self._on_block,
        )
        stream.start()
        self._stream = stream

    def stop(self) -> NDArray[np.float32]:
        """Close the stream and return everything captured, truncated to the cap.

        Returns an empty array rather than `None` when nothing was captured —
        a tapped-and-released hotkey is an ordinary user action, and what to do
        about an empty utterance is the caller's decision, not one this method
        makes by returning a different type.
        """
        stream = self._stream
        if stream is None:
            raise RuntimeError("capture is not running; call start() first")

        stream.stop()
        stream.close()
        self._stream = None

        with self._lock:
            blocks, self._blocks = self._blocks, []

        if not blocks:
            return np.zeros(0, dtype=np.float32)

        audio = np.concatenate(blocks).astype(np.float32, copy=False)
        return audio[: self._max_samples]

    def record(self, seconds: float) -> NDArray[np.float32]:
        """Capture for a fixed duration. For `manu transcribe --seconds`.

        The one-shot CLI has no hotkey to release, so it needs a bounded record
        rather than start/stop. Kept as a thin wrapper so that the buffer
        contract has exactly one implementation.
        """
        self.start()
        try:
            time.sleep(seconds)
        finally:
            audio = self.stop()
        return audio

    def _on_block(
        self, indata: NDArray[np.float32], _frames: int, _time: Any, status: Any
    ) -> None:
        """PortAudio callback. Runs on PortAudio's thread — keep it short.

        Overruns are not raised from here. A dropped block on an overloaded
        machine costs 64 ms of audio; raising out of a callback into PortAudio's
        C stack costs the stream. The status is left visible to a future tray
        indicator (§5.4) rather than acted on.
        """
        del status
        block = np.asarray(indata, dtype=np.float32).reshape(-1)
        with self._lock:
            self._blocks.append(block.copy())
            observer = self._observer
        if observer is not None:
            # `vad_auto` needs to see the audio while it is still arriving
            # (§5.2). Anything raised here would unwind into PortAudio's C
            # stack and cost the stream, which is the same argument the status
            # field above is left unacted on for — so a broken observer costs
            # its own feature and nothing else.
            try:
                observer(block)
            except Exception:
                pass
