# ASR benchmark corpus

Reference transcripts for the Phase 1 engine-selection benchmark (PRD §2's
accuracy-measurement note, §9 Phase 1, objection O7).

**The `.txt` files are committed. The `.wav` files are not**, and never will be —
see the note in `.gitignore`. A voice recording in a public repository cannot be
unpublished once it is cloned, cached and indexed. The corpus exists so *your*
engine comparison is reproducible by you, not so strangers can replay your voice.

## What this corpus is for, and what it is not

It answers **one** question: *of these candidate engines, which is more accurate
on this kind of speech?* That is a relative comparison and it is all the Phase 1
ADR needs.

It does **not** validate G2's `≤ 5%` edit-rate threshold. Six samples from one
speaker in one room on one microphone cannot support an absolute accuracy claim —
n is too small, and the speaker and acoustic diversity are zero. The benchmark
harness is built to say so in its own output. Do not quote a WER from this corpus
as a product claim.

## Recording

One sample per `.txt`. Read the text as written. **Read it the way you talk, not
the way you would read to a microphone** — the flattering-number trap is
enunciating, and a transcript that a model handles perfectly because you
over-articulated tells you nothing about a Tuesday afternoon.

If you stumble or misread a word, keep going, then **fix the `.txt` to match what
you actually said**. The reference must be ground truth for the audio, not an
aspiration. A reference that disagrees with the recording inflates every engine's
WER equally and hides the differences you are trying to measure.

Use the microphone you actually dictate with. Not AirPods or another Bluetooth
headset: those use a voice-optimised codec with heavy noise suppression and a
different acoustic profile from a desk mic, so a corpus recorded on one benchmarks
that headset rather than your setup. PRD §2 specifies desk-mic English.

**Address the microphone by name, not by index.** Device indexes renumber
whenever something connects — an iPhone on Continuity, AirPods pairing, a virtual
audio device. On this machine index `0` is *Josh's iPhone 15 Pro Microphone* and
the built-in mic is `1`, so a hardcoded `:0` silently records the corpus through a
phone. `avfoundation` accepts the device name and that is stable.

```bash
# 1. List devices and pick yours by NAME.
#    The "Error opening input" at the end is expected — -list_devices always
#    exits that way after printing the list. The listing is what you want.
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A6 "audio devices"

MIC="MacBook Pro Microphone"    # <- set to your device's exact name

# 2. Record each sample. Read the matching .txt, then Ctrl-C when finished.
for n in 01-natural 02-code 03-proper-nouns 04-fast 05-noisy 06-short; do
  printf '\n=== %s ===\n' "$n"; cat "tests/fixtures/asr/$n.txt"; echo
  read -r -p "press enter, read it aloud, then Ctrl-C..." _
  ffmpeg -hide_banner -loglevel error -f avfoundation -i ":$MIC" \
         -ar 16000 -ac 1 -c:a pcm_s16le "tests/fixtures/asr/$n.wav"
done

# 3. Verify: every file should read 1 ch, 16000 Hz, Int16, and a plausible length
for f in tests/fixtures/asr/*.wav; do
  printf '%-42s %s\n' "$f" "$(afinfo "$f" | grep -E 'Data format|estimated duration' | tr -s ' ' | tr '\n' ' ')"
done
```

macOS prompts once for microphone access for your terminal. That is the same
Accessibility/Input-Monitoring permission wall Phase 2a exists to front-load, so
treat it as a preview of the real thing.

16 kHz mono 16-bit PCM matches what `AudioCapture` will feed the engine
(`[audio] sample_rate = 16000`, PRD §5.3). Recording at a different rate measures
a resample step that will not exist in the product.

## The samples, and why each is here

| File | Tests |
|---|---|
| `01-natural` | Baseline. Ordinary dictation at a normal pace. |
| `02-code` | Identifiers, paths, symbols spoken aloud, version numbers. The case general ASR is worst at and §5.6's vocabulary map exists for. |
| `03-proper-nouns` | Dense product and person names. Every model missed "Amanuensis" in the probe; this measures how much worse that gets in bulk, and gives `initial_prompt` something to improve. |
| `04-fast` | Rapid speech with no sentence boundaries. Tests punctuation inference, which is most of what the rules post-processor has to fix. |
| `05-noisy` | Deliberate background noise. Play music, run a fan, have a conversation nearby. A tool that only works in a silent room does not work. |
| `06-short` | Seven words. The probe found Whisper's encoder always processes a padded 30-second window, so a short utterance costs nearly what a long one does — this is the sample that shows what VAD trimming (§7.4) is worth. |

## Adding samples

Add a `.txt`, record the matching `.wav`, extend the table above. The benchmark
harness discovers pairs automatically and fails with a named file if one half is
missing. More speakers would be worth more than more samples from one speaker —
if anyone else is willing to record these six, that is the single biggest
improvement available to this corpus.
