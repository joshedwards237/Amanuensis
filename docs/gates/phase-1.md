# Phase 1 gate — Prove the ASR path

**Date:** 2026-08-01
**Branch:** `phase-1-asr-path`
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), 36 GB, macOS 27.0
**Interpreter:** CPython 3.14.5
**Tier measured on this machine: A** (p50 258 ms / p95 386 ms on the install check)

**Verdict: PASS.**

G1 is met on the machine this phase was built on, through the product's own
classes rather than a throwaway script. G3 is verified for the first time, with
a positive control proving the instrument works. ADR 0001 is written from a
measurement that includes Moonshine, which had never been benchmarked.

---

## What the gate asked

PRD §9, Phase 1:

> **Gate:** Report measured latency on your actual hardware against G1.
> Benchmark faster-whisper vs. Moonshine and write
> `docs/adr/0001-engine-selection.md`. **If G1 is missed here, stop and
> renegotiate §7.1 before continuing.**
>
> **Rejects if:** G1 is missed **on the machine this phase is built on**,
> whatever tier that machine recorded at install.

Plus: report the tier and Tier B's number; first G3 verification under packet
capture, confirming the model resolves from a local path.

## What was measured

### G1, through the product path

`scripts/measure_g1.py` constructs `VoiceActivityDetector` and
`FasterWhisperEngine` from an `AppConfig` and records into `LatencyBreakdown`.
Six corpus samples × 9 runs = 54 observations, nearest-rank percentiles.

| Stage | p50 | p95 | min | max |
|---|---|---|---|---|
| `vad_ms` | 30.4 ms | 52.2 ms | 6.8 ms | 52.5 ms |
| `transcribe_ms` | 247.9 ms | 325.7 ms | 94.4 ms | 475.4 ms |
| **`asr_ms`** | **299.7 ms** | **373.3 ms** | 101.2 ms | 524.0 ms |

- **vs Tier A thresholds (350 / 700 ms): PASS.**
- **vs G1 (400 / 800 ms), as a floor: PASS**, with 100 ms of p50 headroom left
  for post-processing and injection — twice the ~50 ms §7.2 budgeted.

The mean sample is 18.6 s, not the 10 s G1 is defined against. That biases the
figure **against** the product: more audio is more decoder output. A corpus
centred on 10 s would report lower.

### The whole path including capture

`manu transcribe` is the only place capture runs. Five 10-second invocations:

| | asr_ms | trim |
|---|---|---|
| 1 | 114.3 ms | 10.0 s → 10.0 s, **no speech detected** |
| 2 | 155.3 ms | 9.9 s → 7.1 s |
| 3 | 162.3 ms | 10.0 s → 8.1 s |
| 4 | 140.0 ms | 9.9 s → **2.0 s** |
| 5 | 161.5 ms | 9.9 s → 9.9 s, **no speech detected** |

`capture_ms` ran 10,194–10,239 ms — the length of the utterance, as expected,
and excluded from G1 by §2.

**Guard 1 fired twice, unprompted, in ordinary use.** Two of the five captures
were ambient room noise the detector found no speech in, and the buffer passed
through whole rather than coming back empty. That guard was written from the
step's invariant before any of this was measured; it is the difference between
"the transcript was poor" and "the words are gone".

### Tier

**Tier A**, recorded to `~/Library/Application Support/amanuensis/tier.json`.
`manu install` measures p50 **258.4 ms** / p95 **385.6 ms** against the 350/700
thresholds, on the bundled reference clip, `tiny.en`, 10 threads, 9 runs.

### Tier B's number

§9 asks for this and "not gated" is not "unmeasured". It is also not
fabricable: Tier B is a machine that misses 350/700, and this machine does not
miss it. What was measured instead is the **same measurement under a pinned
`cpu_threads = 4`** — CTranslate2's default, the value whose penalty returned
NO-GO on the probe's first run:

| | asr p50 | asr p95 |
|---|---|---|
| `cpu_threads = auto` (10) | 299.7 ms | 373.3 ms |
| `cpu_threads = 4` | 277.8 ms | 344.6 ms |

**That is a simulated constraint, not a measured machine** — core count, memory
bandwidth and thermal envelope are still this machine's. It is labelled that
way in the tool's output. **A real Tier B number requires a real Tier B
machine, and this gate does not have one.**

It also produced finding 4 below, which is the most consequential thing this
phase found.

### G3 — first verification

`scripts/verify_g3.py`, four checks:

| Check | Result |
|---|---|
| Model resolves to a local absolute directory, not a repo ID | **PASS** — `~/.cache/huggingface/hub/models--Systran--faster-whisper-tiny.en/snapshots/0d3d19a3…` |
| Sockets opened during a full transcribe cycle | **0** |
| Bytes in/out attributed to the process | **0 / 0** |
| Positive control | **1 socket, 866 bytes** |

Confirmed separately: with `HF_HOME` pointed at an empty directory, `manu
transcribe` **refuses and names `manu install`** rather than downloading —
`local_files_only=True` means there is no fetching code path, not merely no
fetch observed.

`tcpdump` was not used. It needs root, and per-process attribution from
`nettop` and `lsof` is better evidence for this question than an
interface-wide capture that has to be filtered down to this process anyway —
the filtering is where a mistake hides. `--tcpdump` prints the commands for
anyone who wants the interface-wide version.

**The positive control is the part worth keeping.** Its first version fetched a
URL and exited, which validated the byte meter and left the socket poller
unproven: it reported **zero sockets on a run that had certainly opened one**,
because `lsof` samples every 250 ms and an HTTP round trip closes faster. A
clean socket count from the subject would have been unearned. The control now
holds the connection open, and each instrument is validated separately. This
repo has already shipped one gate that passed by measuring nothing
(`sentinel-integrity-check.sh`, AGENTS.md GOTCHAS); that is twice the same
shape of bug now.

### ADR 0001

`docs/adr/0001-engine-selection.md`. **faster-whisper `tiny.en`.** Seven
candidates, 54 observations each, all on identical trimmed input.

Moonshine is faster — `moonshine/tiny` at 163 ms p50 against 278 ms — and every
WER pair involving `tiny.en` is statistically indistinguishable on this corpus.
So the decision could not rest on the rate, and rests on the **error breakdown**
instead: Moonshine deletes 12–14 words where the faster-whisper models delete
2–7. A substituted word is wrong on screen and gets fixed; a deleted word is
silent data loss in text the user has not read yet, which is the failure PRD §8
exists to refuse. That argument is about failure mode, not rate, so the
confidence-interval overlap does not touch it.

`base.en` misses G1's **p95** at 867 ms with nothing built downstream — §7.2
eliminated it on a p50, and this confirms it on the half that matters more.

## What was built

```
src/amanuensis/
├── audio/
│   ├── capture.py        AudioCapture — 16 kHz mono float32, PortAudio lazily
│   └── vad.py            VoiceActivityDetector, TrimResult, two guards
├── engines/
│   └── faster_whisper.py FasterWhisperEngine, local-path resolution, pinned revisions
├── tier.py               §7.2's install check, classify/record/read
├── assets/               the tier-check reference clip (generated, not committed)
├── cli.py                + `manu transcribe`, + `manu install`
├── config.py             + [vad], + default_data_dir, sample_rate constrained
└── models/session.py     + vad_ms, + asr_ms

scripts/
├── measure_g1.py         NEW — G1 through the product classes
├── verify_g3.py          NEW — sockets, bytes, positive control
├── make_tier_clip.sh     NEW — generates the reference clip
└── bench_engines.py      + Moonshine, + --trim, macro-average WER
```

124 tests (57 at the Phase 0 gate), `mypy --strict src/` clean across 23 files,
`ruff check src/ tests/` clean, `black` clean.

## Deferred, by design

- **`AudioCapture` is not covered by an end-to-end automated test.** Opening an
  input stream triggers a TCC prompt and records the room. The PortAudio
  boundary is faked and the logic on this side of it is tested; the real path
  is exercised by `manu transcribe` and reported above.
- **`beam_size` is not swept.** Still the open item the probe named. Every
  figure in this project is `beam_size = 1`.
- **No `MoonshineEngine` class.** `engines/registry.py` still lists `moonshine`
  as "Phase 1", which is now wrong — see finding 8.
- **Post-processing and injection.** Phases 2a and 3. Every `g1_ms` here is a
  floor and will grow.

## What this phase revealed that the PRD got wrong

Ten findings. Four need a PRD amendment and are marked.

### 1. `LatencyBreakdown` had nowhere to put the dominant latency lever — **amend §6.3**

§7.4 calls trimming "the dominant latency lever, not a free bonus" and moves it
into Phase 1 precisely because it changes what this gate measures. §6.3's
`LatencyBreakdown` has `capture_ms`, `transcribe_ms`, `postprocess_ms`,
`inject_ms` — and no field for it.

G1's clock starts at hotkey release, and trimming happens after release, so it
is inside the gated number. The only two options were to fold it into
`transcribe_ms` or to add a field. Folding it in would have buried the
dominant lever inside the stage it exists to shrink, in the very breakdown G1
is defended with. **`vad_ms` added, inside `g1_ms`.**

`asr_ms` (= `vad_ms + transcribe_ms`) added alongside it, because §7.2's
350/700 thresholds bound trim-plus-decode — the check runs with "VAD on,
matching runtime" — and there was no property for that quantity either.

### 2. §5.3 has no `[vad]` table — **amend §5.3**

§7.4 specifies Silero with a threshold and padding behaviour; §5.3's config
block has no table for any of it, while §5.3's own rule says every decision
that could reasonably go either way is a key. Added `threshold`,
`min_silence_duration_ms`, `speech_pad_ms`, defaulted to the values the 328/420
figures were measured under.

**There is deliberately no `vad.enabled`.** §5.3's bounded exception —
behaviour a stated guarantee depends on is not user-settable — applies: §7.2
records that without trimming *no candidate model passes p95 at all*, so an
off switch would be a supported way to break a published guarantee. This is
the **second** instance of that exception after persist-before-inject.

### 3. `[audio] sample_rate` is presented as free and is not — **amend §5.3**

Whisper's feature extractor consumes 16 kHz mono; faster-whisper's Silero
wrapper hardcodes a 512-sample window, which is the 16 kHz frame size. The
intersection is one value. §5.3 offers the key as though any positive integer
worked, and a user who set 44100 would previously have got a resampled,
mistimed pipeline rather than an error. Now rejected at load with both reasons
named.

That makes **three** instances of the bounded exception in two phases, on a
rule stated as "otherwise absolute". Phase 0's finding 5 predicted the pattern;
this is it. §5.3 should stop enumerating exceptions and state the shape:
*a key exists for every decision that could go either way, and a decision that
a stated guarantee or an external library removes is not one of those.*

### 4. §7.2's 1.8× `cpu_threads` penalty does not hold for the model §7.2 selects — **amend §7.2**

This is the most consequential finding, and it is a measurement contradicting a
number the PRD leans on hard.

§7.2: "CTranslate2 defaults to **4 threads**. On a 14-core M3 Max that default
measured 4,413 ms; setting `cpu_threads` to the performance-core count took the
identical model to 2,412 ms. **A 1.8× factor.**"

Those figures are `distil-large-v3` — the model §7.2 **rejected** in the same
revision. Swept on `tiny.en`, the model §7.2 **selects**, over the full corpus:

| `cpu_threads` | asr p50 | vs auto (10) |
|---|---|---|
| 2 | 365.9 ms | 1.36× |
| 4 | 273.4 ms | **1.02×** |
| 6 | 261.1 ms | 0.97× |
| 8 | **235.9 ms** | **0.88×** |
| 10 (`auto`) | 289.1 ms | 1.00× |
| 14 | 559.1 ms | 2.08× |

Confirmed on a second independent run at 15 runs per sample: 8 threads 243.4 ms
against 10 threads 292.1 ms, **0.83×**.

Two conclusions, and they point opposite ways:

- **The efficiency-core exclusion is confirmed and is worth more than claimed.**
  14 threads is 2.08× worse. §7.2's rule to discard the E-cores is right.
- **The 1.8× penalty from the library default is not real for this model.**
  On `tiny.en`, 4 threads is within noise of 10, and the actual optimum is
  around 6–8 — *below* the performance-core count. A small model does not
  parallelise across 10 threads well enough to pay the coordination.

**The default is not changed.** Tuning to 8 would be tuning to n=1 hardware,
which is exactly what §7.2 warns against two paragraphs later, and 10 passes
Tier A with 100 ms of headroom. What changes is the **claim**: §7.2 should say
the 1.8× was measured on a rejected model and does not transfer, and that the
performance-core rule is retained for the E-core exclusion it also encodes, not
for the library-default penalty it was originally argued from.

### 5. §7.2's reference clip cannot be shipped yet — **open, blocks Phase 4**

§7.2 specifies "a bundled 10-second reference clip, shipped with the app". The
repository ships none, and the reason is not laziness:

- It has to be **speech**. Whisper's decode time scales with emitted tokens and
  it repetition-loops on silence, so a synthetic tone would time the failure
  mode rather than the product.
- A **recording of a person** cannot be unpublished once it is in a public
  repo — the reasoning that gitignores the corpus.
- **macOS `say` output** — what `scripts/make_tier_clip.sh` generates, and what
  every number in this gate's tier check was measured on — has no clear
  redistribution grant for a system TTS voice.

Generated locally, gitignored, and `manu install --clip PATH` accepts any
recording. **This must be settled before Phase 4 packages anything**, or
`manu install` fails out of the box for every user.

### 6. §9's Phase 1 names one verb and needs two — **amend §9**

§9 names `manu transcribe --seconds 10`. §7.2 specifies an install-time check
in six-parameter detail and says "re-running the install check is how it
changes" — presuming a command that appears nowhere in the PRD. Added `manu
install` (download once, measure, record).

Both break Phase 0's claim that §6.1 fixes the verb set at four. That claim
survives for the reason it was made: neither new verb talks to a daemon.
`transcribe` is a one-shot diagnostic; `install` runs before a daemon exists.

### 7. §7.2's CUDA rows key on VRAM with no way to measure it — **amend §7.2**

The `model = "auto"` table splits CUDA into "≥8 GB VRAM" and "<8 GB VRAM".
Nothing in the PRD says how a machine determines which it is, and neither
CTranslate2 nor faster-whisper exposes it. Both rows are labelled "estimate,
**unmeasured**" and §3 makes macOS the only v1 platform, so this is a
specification for zero users — but it is unimplementable as written. The
implementation collapses them to one CUDA entry and says so in a comment.

### 8. `engines/registry.py` says Moonshine is built in Phase 1, and it is not

The registry maps `moonshine` → "Phase 1". Phase 1 benchmarked Moonshine and
ADR 0001 declined it, so no `MoonshineEngine` exists. A user who sets
`backend = "moonshine"` gets a `NotImplementedError` naming a phase that has
closed. Registry entry corrected to point at ADR 0001.

### 9. §7.4's "dominant latency lever" is not observable on this corpus

Trimming removed **9%** of the corpus (10.4 s of 111.6 s) and cost 30 ms p50.
On this corpus it is close to net-negative.

That is not a contradiction of §7.4 — it is a property of the corpus. The
samples were recorded with `ffmpeg -t`, tightly cropped, with no dead air to
remove. §7.4's argument is about **real dictation**, where a user presses,
pauses, speaks, pauses, releases; `manu transcribe` shows exactly that,
trimming one 9.9 s capture to 2.0 s.

The consequence is a **measurement-validity limit, not a design one**: this
corpus cannot be used to evaluate trimming, and any future claim about the
trim's benefit needs samples recorded with the silence left in. Worth recording
because the corpus looks like it should be able to answer the question.

### 10. `bench_engines.py` was reporting the WER figure §7.2 withdrew

§7.2, amended 2026-07-31 under objection A3: "WER in this document is
macro-average... A micro-average figure of 14.8% was also in circulation...
**The 14.8% figure is withdrawn.**"

`bench_engines.py` computes WER by pooling edit counts across samples and
dividing — the micro-average. It printed **14.77%** for `tiny.en`. The
amendment landed in the PRD and never reached the tooling, so the withdrawn
figure was still being generated on demand, into the file destined to become
ADR 0001. The macro figure is **19.33%**.

Fixed: macro is the headline, micro is labelled and kept only because the
Wilson interval is a binomial over pooled errors and cannot be computed from a
mean of rates.

**The general lesson is about where an amendment has to land.** A PRD
correction that withdraws a number has to reach every instrument that can
regenerate it, or the number comes back. Nothing in this project's process
checks tooling against PRD amendments.

## Also worth recording

- **WER is not bit-reproducible.** Two runs of the same script over identical
  input gave 7.20% and 6.82% micro for `small.en`. Greedy decoding is not
  deterministic across threaded CTranslate2 runs. Smaller than any gap ADR 0001
  relies on, but a future comparison inside 0.4 points needs repeats.
- **Macro-average is dominated by the short sample.** `06-short` has 7
  reference words, so three errors is 42.9% and it weighs the same as a 60-word
  sample. `tiny.en`'s 19.33% macro is substantially that one sample. Macro is
  still right for §7.2's stated reason; the corpus should grow a second short
  sample.
- **§7.2's demand for a non-10P topology is unmet.** "The sweep covers at least
  one non-10P topology or the rule stays n=1 with a wider blast radius." It
  stays n=1. Every thread number in this gate is from one machine.

## Gate decision

**PASS.**

`Rejects if: G1 is missed on the machine this phase is built on` — G1 is met,
with 100 ms of p50 headroom, on a corpus averaging 18.6 s against a goal
defined at 10 s. Tier A recorded. Moonshine benchmarked, ADR written. G3
verified with a validated instrument.

Phase 2a is released. It inherits three open items: the reference clip's
provenance (finding 5, blocks Phase 4), `beam_size` unswept, and Phase 5 still
`UNRESOLVED, corpus-blocked` on spontaneous unscripted speech.

### The go/no-go is re-armed, not spent (backfilled 2026-08-02)

§9's Phase 2b note assigned this decision to Phase 1 and required it to be
recorded here:

> Decide *before* Phase 1 what happens if it passes at 360 ms and Phase 2b
> lands at 520 ms — whether the go/no-go is re-run or was already spent — and
> record that decision in `docs/gates/phase-1.md`.

**It was not recorded.** This gate closed without it, and it is backfilled here
rather than at the Phase 2b gate deliberately: deciding it *after* seeing
Phase 2b's number would let the number choose the rule.

**Decision: re-armed.** A Phase 2b G1 miss on a Tier A machine rejects the
phase **and** re-triggers §9 Phase 1's "stop and renegotiate §7.1", exactly as
a Phase 1 miss would have.

The reasoning is this record's own words. Every `g1_ms` above is labelled a
floor, because Phase 1 populates at most two of `LatencyBreakdown`'s stages. A
floor clearing a budget is evidence that the budget is *reachable*; it is not a
measurement of the thing the budget is about. Treating it as having discharged
a project-level go/no-go would mean the decision was spent on a number that was
declared incomplete in the same breath.

The cost of being wrong is asymmetric, which settles it. If the go/no-go is
re-armed and never needed, nothing happens. If it is spent and Phase 2b misses,
§7.1's batch-vs-streaming decision stands on a number that never measured the
full path — and §9 says no later phase makes this faster.

Backfilled after the Phase 2a gate, where the end-to-end path first ran and
measured `g1_ms` **231.6 ms** against the 400 ms budget with injection included.
That makes a Phase 2b miss unlikely, which is the reason to fix the rule now:
the decision costs nothing while it is cheap and everything while it is not.

## Rollback

Everything is additive on a branch. `git checkout main` restores the tree as of
the Phase 0 merge; nothing outside `src/`, `tests/`, `scripts/`, `docs/`,
`pyproject.toml` and `.gitignore` was touched.
