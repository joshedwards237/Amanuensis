"""The install-time tier check (PRD §7.2).

A tier is a recorded fact about a machine, not a gate condition. Tier A means
the ASR stage measured **p50 ≤ 350 ms and p95 ≤ 700 ms** on a bundled reference
clip, and G1 is published as a guarantee on that machine; Tier B means it did
not, and G1-CPU applies — the number is measured, published, and told to the
user, and nothing halts.

Three properties get tests, because each one has already gone wrong somewhere
in this project's history:

**Both halves bind.** A p50 inside budget with a p95 outside it is Tier B. The
project has been burned twice by a bare median — a p50 from one clean sample
said GO and the p95 over six real samples was fourteen times worse.

**The thresholds are 350/700, not G1's 400/800.** §7.2 spells out why: the
350/700 figures are the transcribe *share*, leaving ~50 ms for post-processing
and injection. Checking against the full budget would classify a machine
measuring 380 ms as Tier A and then ship it a promise it misses in normal use.

**The tier is decided once and read back.** Re-deriving it per session would let
a momentarily busy machine flip tiers, and a machine near the boundary
oscillate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amanuensis.tier import (
    TIER_A_P50_MS,
    TIER_A_P95_MS,
    TierResult,
    classify,
    read_tier,
    record_tier,
    tier_path,
)


def _result(**overrides: object) -> TierResult:
    defaults: dict[str, object] = {
        "tier": "A",
        "p50_ms": 328.0,
        "p95_ms": 420.0,
        "model": "tiny.en",
        "cpu_threads": 10,
        "runs": 9,
        "clip_seconds": 10.0,
        "measured_at": "2026-07-31T12:00:00+00:00",
        "machine": "Darwin 27.0.0 arm64",
    }
    defaults.update(overrides)
    return TierResult(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def test_the_thresholds_are_the_transcribe_share_not_g1s_full_budget() -> None:
    """§7.2, objection A1. G1 is 400/800; the ASR stage gets 350/700 and the
    ~50 ms residual is what post-processing and injection have to fit in."""
    assert TIER_A_P50_MS == 350.0
    assert TIER_A_P95_MS == 700.0


def test_inside_both_thresholds_is_tier_a() -> None:
    assert classify(p50_ms=328.0, p95_ms=420.0) == "A"


def test_a_p95_miss_is_tier_b_even_with_a_healthy_median() -> None:
    """The lesson that cost this project a false GO. A median cannot see a
    repetition-looping excursion, and that excursion is the documented failure
    mode — 541 ms to 6,039 ms on the same model and sample."""
    assert classify(p50_ms=300.0, p95_ms=6_039.0) == "B"


def test_a_p50_miss_is_tier_b_even_with_a_healthy_tail() -> None:
    assert classify(p50_ms=800.0, p95_ms=690.0) == "B"


def test_the_boundary_is_inclusive() -> None:
    """A machine measuring exactly the threshold passes. Stated because the
    alternative is a silent one-millisecond cliff nobody would ever find."""
    assert classify(p50_ms=TIER_A_P50_MS, p95_ms=TIER_A_P95_MS) == "A"


# --------------------------------------------------------------------------
# Recording — once, at install
# --------------------------------------------------------------------------


def test_the_tier_lands_beside_the_other_per_machine_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same data directory as `history.db`, resolved through `platformdirs`
    and overridable with `$AMANUENSIS_DATA_DIR` — portability floor item 2."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))

    assert tier_path().parent == tmp_path


def test_a_recorded_tier_reads_back_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))
    result = _result()

    record_tier(result)

    assert read_tier() == result


def test_reading_a_tier_that_was_never_recorded_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A machine that has not run `manu install` has no tier. That is a
    distinct state from Tier B and must not be reported as one."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))

    assert read_tier() is None


def test_a_corrupt_tier_record_reads_as_absent_rather_than_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing a recorded tier costs one re-run of the install check. Refusing
    to start the daemon over it costs the user their dictation."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))
    (tmp_path / "tier.json").write_text("{ not json")

    assert read_tier() is None


def test_the_record_carries_what_makes_it_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tier with no model, thread count or date is a number with no claim
    attached. §7.2 specifies six parameters for this check and all six move the
    boundary."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))

    record_tier(_result())

    stored = json.loads((tmp_path / "tier.json").read_text())
    required = ("model", "cpu_threads", "runs", "clip_seconds", "measured_at", "p95_ms")
    for key in required:
        assert key in stored


def test_re_recording_replaces_rather_than_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the install check is how a tier changes (§7.2)."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path))

    record_tier(_result(tier="B", p50_ms=900.0))
    record_tier(_result(tier="A", p50_ms=328.0))

    stored = read_tier()
    assert stored is not None
    assert stored.tier == "A"
