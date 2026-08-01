"""`python -m amanuensis` — the same entry point as the `manu` script.

Exists so the tool is runnable from a checkout without installing it, which
is how anyone auditing a privacy-focused local tool will first run it.
"""

from __future__ import annotations

import sys

from amanuensis.cli import main

if __name__ == "__main__":
    sys.exit(main())
