# Gate record — pre-Phase-0 probe

Produced by `probe.py` and a follow-up sweep, both deleted afterwards (PRD §9,
objection O4; this record required by choice-story #12).

**Verdict: GO** — but §7.2's `model = "auto"` table is wrong for this hardware,
and the first run of this probe returned NO-GO for reasons that turned out to be
configuration rather than physics. Both halves matter.

| | |
|---|---|
| Date | 2026-07-31 |
| Hardware | Apple M3 Max, 36 GB (10 performance cores, 4 efficiency, 14 total) |
| Tier (PRD §7.2) | Apple Silicon — accelerated |
| Runtime | faster-whisper 1.2.1, CTranslate2 4.8.1, Python 3.14.5 |
| Input | 25.8 s of natural dictation, desk mic, 16 kHz mono 16-bit; also trimmed to 10.0 s |
| Model download | 185 s, one-time |

## The number

Median of 5 runs, warmed, `beam_size=1`, `cpu_threads=10`, 10-second utterance:

| Model | 10 s | 26 s | vs G1 p50 (400 ms) |
|---|---|---|---|
| `distil-large-v3` (§7.2's choice) | 2,412 ms | 2,996 ms | **6× over** |
| `small.en` | 889 ms | 1,328 ms | 2.2× over |
| `distil-small.en` | 691 ms | 962 ms | 1.7× over |
| **`base.en`** | **352 ms** | 517 ms | **inside** |
| `tiny.en` | 190 ms | 309 ms | inside |

**This is transcription only.** G1 is `g1_ms` = transcribe + postprocess +
inject (§2, §6.3). `base.en` leaves roughly 50 ms of the p50 budget for the
other two stages. Rules-based post-processing is sub-millisecond; clipboard
paste is tens of milliseconds. It fits, but not comfortably, and Phase 2b
carries the number that actually decides it.

## Three findings that change the PRD

### 1. Thread count is worth 1.8×, and the PRD never mentions it

The first run measured **4,413 ms** and returned NO-GO. That was CTranslate2
defaulting to 4 threads on a 14-core machine. Setting `cpu_threads=10` — the
performance-core count — took the same model to 2,412 ms.

§7.2's table specifies model and quantization and says nothing about threading.
A near-2× factor that determines whether the project's top risk fires does not
belong in an implementation detail. **`cpu_threads` should be a config key with
a sane default, and the default must not be 4.**

Efficiency cores were deliberately excluded — scheduling inference across
heterogeneous cores on Apple Silicon is usually a loss. 10 was not tuned beyond
"match the performance-core count" and is not claimed optimal.

### 2. §7.2's Apple Silicon row is wrong by roughly 7×

The table sends Apple Silicon to `distil-large-v3`. That is 6× over the G1 p50
budget on an M3 Max — one of the faster machines this will ever run on. §7.2
flagged its own numbers as "pre-implementation estimates from the model cards,
not measured on target hardware." This is that flag firing, in the direction it
warned about.

CTranslate2 has **no Metal backend**, so "Apple Silicon" is a CPU tier wearing an
accelerator's name. That is the root cause of the mis-sizing, and it means
objection O1's G1/G1-CPU split is drawn along the wrong axis on macOS: there is
no acceleration here, only more or fewer CPU cores.

### 3. Cost is per 30-second window, not per second of audio

`base.en` takes 352 ms for 10 s and 517 ms for 26 s — 1.5×, not 2.6×. Whisper's
encoder always processes a padded 30-second window; only the decoder scales with
output length.

Consequences the PRD does not account for:

- **A 2-second utterance costs nearly what a 25-second one does.** Most real
  dictation is short, so the common case pays close to the worst case.
- **§7.4's VAD silence trimming is worth far more than "a free latency win."**
  It is the difference between paying for a 30 s window and paying for the
  speech. Slicing record S5 argued trimming belongs in Phase 1 rather than
  Phase 3 and was left open; this is evidence for it.
- **§2's 10-second utterance basis is close to arbitrary**, since anything under
  30 s costs about the same, and §7.1's 15–30 s revisit trigger tests the same
  single window rather than probing a second one.

## Accuracy — read this before choosing a model on latency

All five models produced substantively the same transcript. Differences:

- **Every model got the product name wrong**: Eminesis / Emenezis / Aminesis /
  M&Nesis / M&Nesus. Expected, and exactly what §5.6's `initial_prompt` and
  vocabulary map exist for. Not a differentiator.
- **Every model rendered "four hundred milliseconds" as "400 milliseconds"** and
  dropped the spoken "um". Both desirable.
- **Every model produced "it'll go back to typing" where the script said "I'll".**
  A real error, identical across all five — acoustic, not a capacity limit. A
  larger model does not fix it.
- Minor punctuation and sentence-boundary variation; no clear winner.

**On this sample, `base.en` is not detectably worse than `distil-large-v3` while
being 7× faster.**

The caveat is the whole caveat: **n=1.** One speaker, one accent, one quiet room,
one microphone, one paragraph. This is precisely the gap objection O7 identified
— latency is now measured and accuracy is not. A committed corpus with reference
transcripts is a Phase 1 deliverable, and no model should be selected on the
strength of one clip.

## What this does not measure

Audio capture, cold model residency (185 s here, almost all download; the NFR is
< 15 s — PRD §8), post-processing, and text injection. Warm-up ran before
measurement, which is right for a resident daemon and wrong for judging cold
start. `beam_size=1` throughout; the Phase 1 ADR should sweep it, since it trades
latency against the accuracy nobody has measured yet.

## Recommended amendments

Not applied — these are product-level decisions for the §7 process, not probe
output:

1. Re-derive §7.2's `model = "auto"` table from measurement. The Apple Silicon
   row is wrong by ~7×.
2. Add `cpu_threads` to §5.3 with a default derived from performance-core count.
3. Reconsider whether "Apple Silicon" is an accelerated tier at all while
   CTranslate2 has no Metal backend — bears on objection O1's G1/G1-CPU split.
4. Move VAD silence trimming earlier, per slicing record S5's open finding.
5. Commit the Phase 1 corpus before choosing an engine, per objection O7.
