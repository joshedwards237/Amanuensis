"""Write the per-take transcripts back from the one editable document.

A one-line wrapper, and it exists because the alternative is telling somebody
who has just spent forty minutes reading their own words to remember a flag.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_punctuation_corpus import main

if __name__ == "__main__":
    raise SystemExit(main(["--split", *sys.argv[1:]]))
