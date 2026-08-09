"""Config string to processor class. The composition boundary's dispatch.

Three dispatch sites already exist in this tree — `engines/registry.py`
(config string), `injection/factory.py` and `hotkey/factory.py` (platform) — and
HARNESS.md states the split: `registry.py` for a config string, `factory.py` for
platform detection. `[postprocess] chain` is a list of config strings, so this
is a registry.

**PRD §6.4 did not list this file** and gains it at the Phase 3 gate rather than
quietly. The rejected alternative was dispatching inline in `cli.py`, which
already imports everything and would have become the home of a fourth dispatch
table for no reason other than that it was already open.

**A name the validator accepts but nothing implements names its phase.**
`config.py` accepts `rules`, `vocabulary` and `llm`, because a chain entry is
validated at load and built at start-up, and the two happen in different
processes' worth of code. A user whose config is *valid* and whose daemon
refuses to start is owed the reason, not a lookup error — the same contract
`engines/registry.py` already keeps for `moonshine` and `parakeet`.
"""

from __future__ import annotations

from typing import Final

from amanuensis.config import PostprocessConfig
from amanuensis.postprocess.base import TextPostProcessor
from amanuensis.postprocess.rules import RuleBasedPostProcessor

__all__ = ["build_chain", "create_processor"]

#: Processor name -> the phase that makes it do something. Entries here are
#: accepted by the config validator and not yet built; removing a name from this
#: table and adding it below is what "shipping it" means.
_UNBUILT: Final[dict[str, str]] = {
    # Being built in this phase, in the slice after this one. Listed rather than
    # left to fail on an ImportError, so the branch is never shipped broken and
    # a user who set the key early gets a sentence instead of a traceback.
    "vocabulary": "Phase 3, in the slice after this one",
    "llm": "Phase 5",
}


def create_processor(name: str, config: PostprocessConfig) -> TextPostProcessor:
    """Build one processor by its `chain` name.

    Raises `ValueError` with the known names on an unknown one, and with the
    phase on a known-but-unbuilt one. Both messages are for a user looking at
    their own `config.toml`, which is why neither is a `KeyError`.
    """
    if name == "rules":
        return RuleBasedPostProcessor(config)
    if name in _UNBUILT:
        raise ValueError(
            f"postprocess.chain: {name!r} is not built yet — it is built in "
            f"{_UNBUILT[name]}. Remove it from the chain to continue."
        )
    known = ", ".join(("rules", *_UNBUILT))
    raise ValueError(f"postprocess.chain: unknown processor {name!r}; known: {known}")


def build_chain(config: PostprocessConfig) -> tuple[TextPostProcessor, ...]:
    """The whole chain, in `chain` order.

    Order is significant and this function is the only thing that preserves it:
    each processor transforms the same value, so reordering changes the output
    (§6.3's composition contract). Built eagerly at start-up so a bad name is a
    daemon that will not start rather than a dictation that silently skips a
    stage.
    """
    return tuple(create_processor(name, config) for name in config.chain)
