"""Amanuensis — fully local dictation. Hotkey, speak, text at the cursor.

The package root deliberately holds almost nothing. Importing `amanuensis`
must not import an ASR engine, an audio backend, or a UI toolkit: the daemon
pays a one-time cost to become ready (measured at 3.43 s against a < 15 s NFR)
and every import pulled in here is charged against that budget whether the
command needs it or not. `manu --help` should not load numpy.

Version lives here rather than in `cli.py` so that packaging metadata and the
`--version` flag cannot drift apart.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
