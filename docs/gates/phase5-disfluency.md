# Do disfluencies survive the decoder?

**Measured 2026-08-02.** Apple M3 Max, macOS 27.0, faster-whisper 1.2.1.
Corpus: `tests/fixtures/spontaneous/` — 10 spontaneous takes (403 transcribed
words) plus 2 targeted repair takes carrying a speaker-declared ground-truth
count. Recorded with `scripts/record_spontaneous.py`. One speaker.

PRD §9's Phase 5 named this as the blocking unknown, in those words:

> **The blocking unknown, stated as a question nobody has answered: do
> disfluencies survive the decoder?** It is untested. The claim that they do not
> appears in one experiment record and is an assertion, not a measurement.

It is now a measurement, and the answer splits in two — **in opposite
directions**. The decoder deletes filled pauses and preserves self-corrections
verbatim. Reading one result as though it settled both was one sentence away
from happening, and would have retired Phase 5 on evidence about the wrong
phenomenon.

---

## Filled pauses: **no, they do not survive.** Answered.

| Model | Words | Filled pauses | Per 100 words |
|---|---|---|---|
| `tiny.en` | 403 | **0** | 0.00 |
| `base.en` | 400 | **0** | 0.00 |
| `small.en` | 398 | **0** | 0.00 |

Also zero immediate word repetitions, and one repair marker across the corpus.

**Verified by ear**, which is the part that makes this a finding rather than a
coincidence. Three models agreeing is consistent with two different worlds —
the decoder deletes them, or the speaker never produced any — and a transcript
cannot tell those apart. The speaker listened to `06-undecided` and counted
**three audible "um"s**. That take transcribed 56 words with zero. Three in 56
words is 5.4 per 100, squarely inside the 2–6 the literature reports for
spontaneous speech, which also means the corpus as a whole probably contained
roughly twenty and lost all of them.

This is not a `tiny.en` artefact. Three model sizes, spanning a 4× parameter
range, delete them identically — consistent with Whisper's training data being
cleaned transcripts rather than with any decoding parameter this project sets.

## Self-corrections: **yes, they survive — every one of them.** Answered 2026-08-02.

Two targeted takes, four corrections each, count declared by the speaker before
transcription and stored in `*.corrections.json`. **8 of 8 survive, in all three
models.** The contrast with filled pauses could not be sharper: the decoder
deletes "um" and preserves repairs verbatim.

### Marked repairs — survive with their markers intact

`11-repairs-marked`, `small.en`, corrections in **bold**:

> Hey, it's Josh. I need to move our meeting. Can we do it on Tuesday?
> **Actually no** Wednesday Wednesday at 3 o'clock **wait, no, no,** I'll make
> that 4 o'clock and do it in the big conference room **Actually, no,** I want
> the small conference room and make sure to bring in Sarah **Actually, no, no,**
> we need Rachel Rachel's the one who needs to be there

4 / 4, and the marker word reaches the text every time. That is the whole
question for the deterministic path: a `RuleBasedPostProcessor` can match
*actually no* / *wait no* / *I mean* and discard the candidate before it.

### Bare repairs — survive too, as adjacent pairs with no cue at all

`12-repairs-bare`, `small.en`:

> Hey, it's Josh moving our meeting. Can we do **Tuesday Wednesday** Wednesday
> at **four? Five** o'clock. Let's use the **small Big** conference room and
> bring **Sarah Rachel** with you

4 / 4 again. The decoder transcribes them faithfully and adds nothing — which
is exactly the problem, because there is no lexical signal to key on.

### This is where the work divides, and the division is now measured

**Marked repairs are rule-tractable.** The marker is a token, tokens are
matchable, and the fix is deterministic, instant and debuggable — PRD §7.5's
"start with deterministic rules" applied to a case that has now been shown to
reach the rules. Phase 3.

**Bare repairs are not, and no rule can be written for them.** "the small big
conference room" is a repair; "the big red ball" is two adjectives; "Sarah
Rachel" is a repair, and someone's double-barrelled name. Nothing distinguishes
them but meaning. A pattern that deleted the first of every adjacent pair would
corrupt correct transcripts to fix incorrect ones.

**That is the first measured justification for Phase 5 this project has.** The
LLM pass was un-deferred on an argument about product parity (§1) and then
failed its own latency and WER gates. It now has something a rule provably
cannot do, on the axis §1 actually names. Whether it can do it inside 700 ms and
without the catastrophic behaviour recorded in `phase5-feasibility.md` remains
completely untested — this establishes the need, not the solution.

## A risk this raises for ADR 0001

`tiny.en` mangled one of the four markers: where `base.en` and `small.en` both
render *"wait, no, no, I'll make that 4 o'clock"*, `tiny.en` produced *"wait in
the middle I make that four o'clock"*. 1 of 4 against 0 of 4 and 0 of 4.

That is n=4 and not a finding. But it lands in a bad place: the marker tokens
are precisely what the deterministic path depends on matching, so `tiny.en`'s
accuracy deficit is not evenly spread — it falls on the words the cheap fix
needs. ADR 0001 selected `tiny.en` knowing it had the worst accuracy of the
faster-whisper candidates and betting post-processing would close the gap. This
is a mechanism by which that bet could fail specifically rather than generally.

**Not enough to reopen the ADR.** Enough to measure deliberately in Phase 3:
marker-token recall by model, over more than four instances. If `tiny.en` drops
one marker in four, the rules processor inherits that miss rate directly.

## Superseded: how this gap was stated before takes 11 and 12

Kept because the framing was the useful part, and because it was nearly missed.

"Disfluency" covers at least two phenomena, and this record originally treated
the first as though it answered both:

- **Filled pauses** — "um", "uh", "er". Deleted by the decoder.
- **Self-corrections** — "let's meet Tuesday, no, Wednesday." Preserved verbatim.

They behave in *opposite* directions, and PRD §1 rests the product argument on
the second:

> a verbatim transcriber and a tool that **resolves your self-corrections** are
> different products, and a user comparing them will not grade on the
> distinction.

Takes 1–10 answered only the first, because prompts that elicit thinking under
load produce filled pauses reliably and repairs barely — one repair marker in
403 words. Reading "disfluencies do not survive" off that corpus and concluding
Phase 5 had nothing to do would have been wrong, and it was one sentence away.
Takes 11 and 12 exist because the two words were separated in time.

One hypothesis from that period is now resolved: mid-sentence capitals in
`06-undecided` (`...for both Like she's...`) were guessed to be segment
boundaries where the decoder split on a hesitation it declined to transcribe.
Takes 11 and 12 show the same capitalisation appearing around *preserved*
repairs (`the small Big conference room`), so the capital marks a boundary the
decoder found — not evidence of something it removed.

## What this does to the earlier Phase 5 result

`docs/gates/phase5-experiments.md` measured four approaches against the scripted
corpus and none improved WER on any sample. That was recorded as **inconclusive
rather than negative**, on the grounds that the corpus was read from a script
and therefore contained no disfluencies to remove — "structurally incapable of
testing a disfluency remover, and reusing it here was the error."

**That diagnosis was half wrong, and in an instructive direction.** The corpus
was not the only reason those approaches had nothing to delete. Even with
genuinely disfluent *audio*, the filled pauses never reach the text. Three of
the four approaches were deletion mechanisms aimed at tokens the decoder had
already removed — and they would have found nothing to do on a spontaneous
corpus either. The experiments were not testing the wrong corpus so much as
sitting downstream of a stage that had already done their job.

The rules-only control leading that table now reads differently too. It was not
that the other approaches underperformed; it is that the input was already
clean of the thing they targeted.

## What post-processing does still have to do

Measured over the same 10 takes, so the remaining work is grounded rather than
assumed:

| Defect | Frequency |
|---|---|
| Leading whitespace on the raw transcript | 10 / 10 takes |
| No sentence-final punctuation | 7 / 10 takes |
| Spurious mid-sentence capitals | ~10 real (15 flagged; `CDE`, `Renee` and other proper nouns inflate it) |

Every one of these is **rule-shaped**: deterministic, instant, debuggable, and
exactly what PRD §7.5 means by "start with deterministic rules. They are
debuggable, instant, and cover most of the value." None of them wants a language
model. That is Phase 3's `RuleBasedPostProcessor`, not Phase 5.

## Consequences for the PRD

- **§7.5 lists "filler removal" as one of four things post-processing exists
  for.** On Whisper output that one is already done upstream. The other three —
  punctuation, capitalisation, spoken commands — survive, and the measurements
  above give two of them a frequency.
- **§5.3's `strip_fillers` operates on nothing** for the default engine. It is
  not wrong to keep the key (a future engine may be verbatim, and Moonshine was
  not tested for this), but its default of `false` is currently a no-op either
  way, and the comment "off by default, it is lossy" describes a risk that does
  not arise.
- **§9's Phase 5 is no longer corpus-blocked, and its justification is now
  measured rather than argued.** Bare repairs reach the transcript and no rule
  can resolve them. What remains open is whether anything can, inside 700 ms —
  which is the question `phase5-feasibility.md` answered badly once already.

## What would close what remains

The decoder question is answered in both directions and needs no more takes.
Two things are open and neither is about the decoder:

1. **Can anything resolve a bare repair inside 700 ms?** That is Phase 5's real
   question and it is untouched. This record establishes that a rule cannot,
   which is the part that was previously assumed.
2. **Marker-token recall by model**, over more than four instances — see the
   ADR 0001 risk above.

## Limits

- **One speaker.** Every number here. A second voice could change the filled-pause
  result, though three models agreeing across a 4× parameter range makes a
  speaker-specific explanation unlikely.
- **One file verified by ear.** `06-undecided`. The other nine takes' filled-pause
  counts are inferred from it plus the literature base rate, not counted.
- **`beam_size = 1` throughout.** A beam search might surface different tokens.
  Untested, and it is the same unswept parameter the probe flagged.
- **Moonshine untested for this.** ADR 0001 declined it on other grounds; whether
  it is more verbatim than Whisper is unknown and would matter if verbatim output
  ever became desirable.
- **Transcripts are not committed.** They carry the speaker's words as surely as
  the audio does, and the audio is gitignored for that reason.
