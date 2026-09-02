# G1 at ten seconds, with the shipped chain

**Measured 2026-09-02. p50 312.4 ms, p95 344.5 ms, against 400 / 800.**

§9 assigned "the real G1 number" to the Phase 3 gate and Phase 3's own ≥ 60 s
corpus rule forbade the corpus containing one — the two requirements are not
jointly satisfiable, which the Phase 3 gate recorded as finding 4 and deferred
here. This is that measurement.

## What was measured

| | |
|---|---|
| takes | 10 |
| speech | **7.5 – 10.0 s** |
| G1 p50 | **312.4 ms** (budget 400) |
| G1 p95 | **344.5 ms** (budget 800) |
| range | 292.4 – 344.5 ms |

Percentiles are nearest-rank, never interpolated. `g1_ms` is
`LatencyBreakdown.g1_ms` — the product's own property, not arithmetic
reimplemented in a harness — read from `history.db` rows the daemon wrote,
which is the same method the Phase 2b gate used.

**The configuration that produced it**, because this project has quoted a
corpus decoded under a dead `initial_prompt` and not noticed for two weeks:

| | |
|---|---|
| `config.toml` sha256 | `58c6525b5d8722779c8e128837fbc236c365a90821331431e41b44e1fac6425e` |
| `[postprocess] chain` | `["rules", "vocabulary"]` — the full shipped chain |
| `[engine] initial_prompt` | `""` |
| `[engine] model` | `auto` → `tiny.en`, 10 threads |
| code | `cf6aed2` |

The digest was captured before recording and again after, and matched. Phase
2b's 223.0 / 270.0 was taken with `chain` **empty**; this is the first G1 at its
own definition with post-processing in the path.

## The first attempt was contaminated, and by me

Nine takes recorded at 22:31–22:33 produced p50 327.5 / **p95 4014.1** — three
takes at 1558, 1806 and 4014 ms against six at 278–436, on input of essentially
identical length. A 14× spread where the Phase 3 gate's own p95/p50 was 1.2×.

That was not the product. The assistant was running the test suite, `mypy` and
`ruff` during the recording, having just warned the operator that a benchmark
would corrupt exactly this measurement.

**Established rather than asserted.** The same stored audio was re-decoded on an
idle machine:

| take | live | idle re-decode | ratio |
|---|---|---|---|
| 9.2 s | 1780 ms | 199 ms | **8.9×** |
| 9.1 s | 1529 ms | 206 ms | **7.4×** |
| 9.8 s | 3946 ms | 201 ms | **19.6×** |
| the other six | 259–388 ms | 180–230 ms | 1.2–1.9× |

The audio is identical and decode cost is deterministic in it, so the only
variable was machine load. **All nine takes were discarded, not just the three
outliers** — publishing "the fastest six" would have been outcome selection,
choosing the rows that flatter, which is the failure this project already has on
record from the site's headline band.

## The control on the accepted run

The same test, applied to the ten takes above:

| | |
|---|---|
| live / idle ratio | **1.29× – 1.76×**, mean 1.48× |
| contaminated run | 1.2× – 19.6× |

**Consistency is the evidence, not the absolute value.** The 1.48× is the
daemon's own concurrency cost — the worker decodes while the process also runs
an AppKit loop, an event tap, a PortAudio callback and the IPC acceptor — and
that cost is inside G1 by §2's definition. The idle replay is a decode-only
lower bound and is not a target.

## What this number does not cover

- **One machine, one speaker, one session.** Tier A hardware (this machine
  measures inside the budget at install). No Tier B figure exists — see the
  Phase 4 gate record.
- **7.5–10.0 s of speech.** G1 is defined at ten seconds and this is that band.
  It says nothing about the 67–97 s dictation the Phase 3 corpus contains, where
  §2's own model predicts ≈ 909 ms.
- **`transcribe_ms` is 83–93% of every row.** G1 is the decoder's number; the
  chain contributes under a millisecond.
