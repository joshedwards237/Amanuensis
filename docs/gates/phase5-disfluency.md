# Do disfluencies survive the decoder?

**Measured 2026-08-02.** Apple M3 Max, macOS 27.0, faster-whisper 1.2.1.
Corpus: `tests/fixtures/spontaneous/`, 10 takes, 403 transcribed words,
recorded with `scripts/record_spontaneous.py`. One speaker.

PRD §9's Phase 5 named this as the blocking unknown, in those words:

> **The blocking unknown, stated as a question nobody has answered: do
> disfluencies survive the decoder?** It is untested. The claim that they do not
> appears in one experiment record and is an assertion, not a measurement.

It is now a measurement, and the answer splits in two.

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

## Self-corrections: **not answered, and this is the half that matters**

The distinction was nearly lost, so it is stated plainly. "Disfluency" covers at
least two things:

- **Filled pauses** — "um", "uh", "er". Measured above. Deleted.
- **Self-corrections** — "let's meet Tuesday, no, Wednesday." **Untested.**

PRD §1 and §9 rest the entire product argument on the *second* one:

> a verbatim transcriber and a tool that **resolves your self-corrections** are
> different products, and a user comparing them will not grade on the
> distinction.

Nothing in this corpus establishes what happens to those. The prompts were
built to elicit *thinking under load*, which reliably produces filled pauses,
and they were not built to elicit corrections — the speaker had no reason to
say a wrong thing and take it back. There is one repair marker in 403 words,
which is not a sample.

Two suggestive artefacts, both from `06-undecided`, neither conclusive:
mid-sentence capitals appear where a restart plausibly was (`...for both Like
she's...`, `...character And I've...`), which is what a segment boundary looks
like when the decoder split on a hesitation it then declined to transcribe.
That is a hypothesis, not a result — nobody has the ground truth for those
moments.

**So Phase 5's status changes but does not resolve.** It was blocked on "do
disfluencies survive". Half of that is now answered negatively, and the
answered half is the half Phase 5 was *least* needed for.

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
- **§9's Phase 5 is no longer corpus-blocked.** The corpus exists and answered
  what it could. What remains is a narrower and much cheaper question.

## What would close it

One targeted take, roughly two minutes: the speaker deliberately self-corrects
several times, counts them, and reports the count. Then check how many survive.

That is a different experiment from this one and it needs the count in advance,
because self-corrections — unlike "um" — are grammatical English and cannot be
found in a transcript by pattern. "Let's meet Tuesday, no, Wednesday" and "let's
meet Wednesday" are both fluent sentences. Only the speaker knows which one they
said.

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
