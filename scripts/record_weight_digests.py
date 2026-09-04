"""Regenerate `PINNED_DIGESTS` from snapshots already on this machine.

§7.6 requires that the bytes a user downloads are re-hashed against digests
**this project** recorded. Recording them by hand is how the two hand-maintained
tables — `PINNED_REVISIONS` and `PINNED_DIGESTS` — drift apart, so this prints
the block to paste and refuses to invent one.

It reads only the local Hugging Face cache and never touches the network: a
script that could fetch would be a script that could record the digest of
whatever it was served, which verifies the hub against itself and is the exact
thing §7.6 was amended to stop doing. Run `manu install` first if a model is
missing, then run this, then check the revision it printed is the pinned one.

    python scripts/record_weight_digests.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amanuensis.engines.faster_whisper import (
    PINNED_REVISIONS,
    ModelNotAvailableError,
    resolve_model_path,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    missing: list[str] = []
    print("PINNED_DIGESTS: Final[dict[str, dict[str, str]]] = {")
    for model, revision in PINNED_REVISIONS.items():
        try:
            directory = resolve_model_path(model)
        except ModelNotAvailableError:
            missing.append(model)
            continue
        # The snapshot directory is named for the revision it holds. Printing it
        # is the only way the reader can tell whether these digests belong to
        # the pin above them or to whatever happened to be in the cache.
        print(f'    # from {directory.name}')
        if directory.name != revision:
            print(f'    # WARNING: pinned revision is {revision} — these differ')
        print(f'    "{model}": {{')
        for entry in sorted(p for p in directory.iterdir() if p.is_file()):
            # Wrapped because a 64-character digest does not fit beside its
            # key inside 88 columns. Must match the module's shape exactly:
            # this output is pasted whole, never hand-aligned.
            print(f'        "{entry.name}":')
            print(f'            "{sha256(entry)}",')
        print("    },")
    print("}")

    if missing:
        print(
            f"\n# NOT RECORDED, no local snapshot: {', '.join(missing)}."
            "\n# Run `manu install` for each, then re-run this. Do not hand-write"
            "\n# a digest — a digest nobody hashed is a digest nobody checked.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
