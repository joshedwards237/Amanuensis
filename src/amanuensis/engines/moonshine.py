"""Moonshine (ONNX) — the alternative §7.2 has named since 2026-07-30.

§6.4 has listed this file since Phase 0 and it did not exist until 2026-09-02.
The engine ABC exists because Moonshine is "a genuine alternative to
faster-whisper on CPU" (§7.2), and an ABC with one implementation is a claim
nobody has tested.

**What ADR 0001 already decided, and what it did not.** Moonshine is the
fastest candidate this project has measured — 163 ms p50 against `tiny.en`'s
278 — and it was declined anyway, on an axis latency cannot see: it *deletes*
12–14 words where the faster-whisper models delete 2–7. A deleted word is
silent data loss, which §8 exists to refuse, and every WER pair involving
`tiny.en` was statistically indistinguishable, so the rate could not decide it.
That decision stands and this file does not reopen it.

What was never measured is **punctuation**, which is the Phase 3 gate's
dominant error class — 58 missing sentence marks and 41 stray capitals out of
171 edits — and the reason §7.2 marked the engine question open and carried it
here. §7.2 also freezes the Phase 4 default *before* any of this runs, so the
result cannot select its own consequence.

Three differences from faster-whisper that the contract has to absorb:

* **No prompt, so no bias to suppress.** `biased=False` is honoured by being
  already true — §6.3 chose a boolean over a prompt string for exactly this
  case, "an engine with no prompt concept cannot be told to use an empty
  prompt, but it can be told it is already unbiased and ignore the flag."
* **No `boost`.** The term list is accepted and dropped, and `Transcription`
  says so rather than implying the terms were applied. §5.6's dictionary still
  runs in the post-processing chain, which is where the other half of boosting
  lives for every engine.
* **No segment timings, so `decoded_seconds` is `None`.** Not zero: §5.7's
  coverage guard routes a `None` to its fallback instrument, and a zero would
  read as "the decoder stopped immediately" and refuse every transcript.

The weights ship inside `useful-moonshine-onnx`'s own model cache. That is a
G3 matter and is why the import is at point of use: `manu --help` must not pay
an ONNX runtime it will not use.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from numpy.typing import NDArray

from amanuensis.engines.base import TranscriptionEngine
from amanuensis.models.results import Transcription

if TYPE_CHECKING:
    from amanuensis.config import EngineConfig

__all__ = ["MODELS", "MoonshineEngine"]

#: The two sizes ADR 0001 measured. Prefixed as the upstream package names
#: them, so a row in a report and a value in `config.toml` are the same string.
MODELS: Final[tuple[str, ...]] = ("moonshine/tiny", "moonshine/base")

#: §7.4's rate, and the only one this engine is given. Moonshine's feature
#: extraction assumes 16 kHz exactly as Whisper's does, and there is no
#: resampling here — a mismatched rate would silently transcribe audio played
#: at the wrong speed rather than fail.
EXPECTED_SAMPLE_RATE: Final = 16_000


class MoonshineEngine(TranscriptionEngine):
    """ONNX encoder/decoder. One knob, which is the point."""

    def __init__(self, config: EngineConfig) -> None:
        model = config.model
        if not model.startswith("moonshine/"):
            # `[engine] model` is shared with faster-whisper, whose names are
            # bare (`tiny.en`). Reaching here with one of those means the
            # backend and the model disagree, and guessing which the user meant
            # is how a benchmark ends up measuring the wrong engine.
            raise ValueError(
                f"[engine] model is {model!r}, which is not a Moonshine model. "
                f"Known: {', '.join(MODELS)}."
            )
        self._model_name = model
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        if self._model is not None:
            return
        from moonshine_onnx import MoonshineOnnxModel, load_tokenizer

        self._model = MoonshineOnnxModel(model_name=self._model_name)
        self._tokenizer = load_tokenizer()

    def warm_up(self) -> None:
        """One throwaway inference, on the same seeded noise faster-whisper
        uses — silence is the wrong warm-up for a decoder that can loop on it.
        """
        if self._model is None:
            self.load()
        rng = np.random.default_rng(0)
        noise = rng.normal(0.0, 0.001, EXPECTED_SAMPLE_RATE).astype(np.float32)
        self.transcribe(noise, EXPECTED_SAMPLE_RATE)

    def transcribe(
        self,
        audio: NDArray[np.float32],
        sample_rate: int,
        *,
        biased: bool = True,
        boost: Sequence[str] = (),
    ) -> Transcription:
        """One utterance in, raw transcript out.

        `biased` and `boost` are accepted and have no effect — see the module
        preamble. They are not rejected, because §5.7's guard and §5.6's
        per-application boosting both call every engine the same way, and an
        engine that raised on a flag it cannot honour would make the caller
        responsible for knowing which engine it was talking to.
        """
        del biased, boost

        if sample_rate != EXPECTED_SAMPLE_RATE:
            raise ValueError(
                f"Moonshine expects {EXPECTED_SAMPLE_RATE} Hz and got "
                f"{sample_rate}. There is no resampling here, so a mismatch "
                "would transcribe audio played at the wrong speed."
            )
        if self._model is None or self._tokenizer is None:
            self.load()
        assert self._model is not None and self._tokenizer is not None

        batched = np.asarray(audio, dtype=np.float32)[None, ...]
        tokens = self._model.generate(batched)
        # Tokenisation is inside this call rather than left to the caller
        # because it is inside faster-whisper's equivalent: what a caller needs
        # is text, and an engine that stopped at token IDs would have its
        # tokeniser timed as somebody else's `postprocess_ms`.
        text = str(self._tokenizer.decode_batch(tokens)[0])

        return Transcription(
            text=text.strip(),
            # None, not zero. §5.7 routes a `None` to its fallback instrument;
            # a zero reads as "decoding stopped immediately" and would refuse
            # every transcript this engine produced.
            decoded_seconds=None,
        )
