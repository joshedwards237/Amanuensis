# Feasibility record — LLM second pass (Phase 5)

Measured 2026-07-31 on Apple M3 Max / 36 GB, in response to the question: *can
Amanuensis do the Wispr-Flow-style cleanup pass locally, and what would it cost?*

**Answer: yes, technically. The blocker is not latency or hardware — it is
fidelity.**

## Why this was measured at all

Phase 5 was deferred indefinitely on 2026-07-31 (slicing record S7). That
disposition assumed the LLM pass was a polish feature. It is not: the second pass
is a **core** feature of the product Amanuensis is measured against (§1). A
verbatim transcriber and a dictation tool that resolves your self-corrections are
different products, and users comparing the two will not grade on the distinction.

## The technology

**MLX** (Apple's array framework) with 4-bit quantised instruct models.

The decisive fact: **MLX and llama.cpp both have Metal backends. CTranslate2 does
not.** So the LLM pass runs on the GPU on Apple Silicon while transcription is
stuck on CPU cores. The second pass is *cheaper per token* than the transcription
that precedes it, which is the opposite of the intuition §7.5 was written on.

| Package | Role |
|---|---|
| `mlx`, `mlx-lm` | inference, Metal-backed |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | ~1.8 GB on disk |

## Measured latency

Median of 3, warmed, greedy decoding (`temp=0.0`), `max_tokens=120`, on
representative dictation-length inputs:

| Model | Cleanup latency | Quality |
|---|---|---|
| Qwen2.5-0.5B-Instruct-4bit | **103–184 ms** | Unusable. Mangled self-corrections, left fillers in. |
| Qwen2.5-1.5B-Instruct-4bit | **154–301 ms** | Removes fillers and stutters. Fails self-corrections. |
| **Llama-3.2-3B-Instruct-4bit** | **278–390 ms** | Resolves self-corrections correctly with a directive prompt. Over-edits. |

**Cold start is not a problem, contrary to the first reading here.** The 48 s
figure originally recorded was the one-time weight *download*, not the load.
Measured warm, with weights cached:

| | import + load | first inference |
|---|---|---|
| `tiny.en` (int8, 10 threads) | 0.77 s | 0.22 s |
| `Llama-3.2-3B-Instruct-4bit` (MLX) | 2.11 s | 0.33 s |
| **daemon cold start to ready** | **3.43 s** | NFR §8: **< 15 s** |

Roughly 11 s of headroom with **both** models resident. The NFR that looked
threatened is comfortably met. This correction matters because "two resident
models blows the cold-start budget" was briefly treated as an argument against
the feature; it is not one.

### Against the budget

`tiny.en` with VAD is the only ASR candidate inside G1 (328 ms p50 / 420 ms p95,
`docs/gates/probe.md` and the Phase 1 benchmark). Adding the 3B pass:

```
tiny.en  328 ms  +  Llama-3.2-3B  390 ms  =  ~718 ms
```

Against Phase 5's own budget of p50 ≤ 700 ms (§7.5) that is **marginally over**,
on a machine at the fast end of what this product will run on. It fits the shape
of the budget and not the number.

## The finding that matters: it rewrites, it does not just clean

Model capability was never the blocker. Prompting was — a directive prompt with
explicit self-correction rules took the 3B model from *wrong* to *correct* on the
case that motivates the whole feature:

> in: "I want the button to be, um, red, no, blue, and it should be like, on the
> right side of the page, or actually the left."
> out: "The button should be **blue**, and it should be on the **left** side of the page."

Both corrections resolved. But the same prompt produced:

> in: "send that to uh Josh and and copy me on it"
> out: "Send to Josh, copy me." — *dropped "on it", reworded "send that to"*

> in: "let's meet on Monday, sorry, Tuesday at like three, no, four o'clock"
> out: "on Tuesday at 4 o'clock" — *dropped "let's meet" entirely*

**The failure mode is not "cleans too little". It is "silently changes what you
said."** In a dictation tool that is strictly worse than leaving the fillers in:
a user can see and delete an "um". They cannot see a clause the model removed
before the text ever reached the screen.

This is the same class of hazard as §7.3's clipboard exposure — an invisible
transformation the user has no way to audit — and it deserves the same treatment
under §7.6's surfacing-versus-preventing doctrine.

## What a shippable design has to include

Not implementation detail; these are the constraints that make the feature safe:

1. **The raw transcript is preserved.** The pre-injection write (§8) stores the
   **raw** text, not the cleaned text. If the pass drops a clause, the words still
   exist and are recoverable.
2. **A hard no-invent rule, verified.** Compare cleaned output against raw before
   injecting: if the cleaned text contains content words absent from the raw
   transcript, discard the cleaned version and inject raw. Deletion is the
   intended operation; insertion is a hallucination.
3. **A length floor.** If cleaning removes more than ~25% of content words,
   treat it as over-editing and fall back to raw. Case 3 above lost 40%.
4. **Undo affordance.** The user needs one keystroke to get the raw version back,
   because they cannot know what was removed.
5. **Off by default** — unchanged from §7.5.

Constraints 2 and 3 are cheap deterministic checks around a probabilistic step,
and they turn the failure mode from *silent corruption* into *visible no-op*.

## What is still unknown

- **n=3 prompts, one author.** These are three hand-written cases, not a corpus.
  The Phase 3 edit-rate data is the real evidence and does not exist.
- **No accuracy measurement of the pass itself.** "Over-edits" is a judgement made
  by reading three outputs. There is no metric here.
- **The 700 ms budget is arithmetic, not tolerance** — choice-story #9 flagged
  this before any of it was measured, and the flag stands.
- **Untested on the ASR output that will actually feed it.** Every case above was
  hand-written to be disfluent. Real `tiny.en` output has *transcription* errors
  as well as disfluencies, and the pass may amplify them.
