# Amanuensis

Fully local, open-source dictation for macOS. Press a hotkey, speak, release —
your words appear as text at the cursor in whatever application has focus.

No account. No network at runtime. No audio leaving the machine.

**There is no packaged app and no signed binary.** You run it from a source
checkout — there is a script that does the whole setup for you, and the manual
path is seven steps.
[nerd-dictation](https://github.com/ideasman42/nerd-dictation) (Linux) and
[Talon](https://talonvoice.com/) are the mature alternatives; PRD §1 records why
this exists alongside them.

---

## Install

**Requirements:** macOS (PRD §3) and Python **3.12 or later**.

### The short way

One command, and it handles everything below:

```sh
curl -fsSL https://raw.githubusercontent.com/joshedwards237/Amanuensis/main/scripts/bootstrap.sh | bash
```

It checks what your Mac is missing, tells you what each system dialog is
**before** it appears, installs what is needed, downloads the model, and raises
the two permission prompts. It asks before changing anything, never uses `sudo`,
is safe to run twice, and **refuses to report success if the result does not
work** — including checking that the speech model is actually resolvable, which
is the one failure that otherwise looks like a clean install until your first
dictation.

It cannot grant permissions. Nothing can; macOS reserves that for you. It raises
the prompts and opens the right pane, and you click.

The rest of this section is the same install by hand.

---

### Before step 1 — what a new Mac does not have

Three things, and a Mac that has never been used for development has none of
them. This list exists because the first person to try this README got as far as
`git clone` and no further.

- **Permission for your terminal to read the folder you are working in.** macOS
  guards `~/Documents`, `~/Desktop` and `~/Downloads`. The first command you run
  in one of them raises a permission dialog. Working in your **home folder**
  avoids it entirely, which is where the script above clones to.
- **The Xcode Command Line Tools.** There is no `git` without them, so `git
  clone` does not clone — it opens Apple's installer, downloads about a
  gigabyte, and takes several minutes. Trigger it deliberately with
  `xcode-select --install` rather than being surprised by it.
- **Python 3.12.** The Requirements line above is not advice. The command line
  tools ship an older Python, so `python3.12` will not exist until you install
  it — from [python.org](https://www.python.org/downloads/macos/), whose
  installer is a normal Mac `.pkg` and asks for your password itself.

Check all three before starting:

```sh
sw_vers -productVersion     # macOS version
xcode-select -p             # a path means the tools are installed
python3.12 --version        # "command not found" means install it
```

### 1. Get the source and install it

```sh
git clone https://github.com/joshedwards237/Amanuensis.git
cd Amanuensis
python3.12 -m venv .venv && source .venv/bin/activate
pip install .
```

This installs two commands that do the same thing: **`manu`** and
**`amanuensis`**. Every example below uses `manu` because it is shorter; use
whichever you remember.

**They live in the virtualenv, so a new terminal will not find them.** A second
terminal answers `zsh: command not found: manu` until you
`source .venv/bin/activate` again. To have them always available, link them into
a directory already on your `PATH`:

```sh
ln -s "$PWD/.venv/bin/manu" ~/.local/bin/manu                    # or /usr/local/bin
ln -s "$PWD/.venv/bin/amanuensis" ~/.local/bin/amanuensis
```

Check with `echo $PATH` in a **new** terminal that the directory you chose is
actually on it.

### 2. Generate the reference clip

```sh
scripts/make_tier_clip.sh
```

The install measures your machine against a ten-second speech clip, and **the
repository does not ship one.** PRD §7.2 requires a clip that is not your voice
and needs no microphone permission before first use, which leaves synthesised
speech — and the redistribution grant for a macOS system voice is not clear
enough to commit one. So you generate it locally with `say`. No microphone, no
network.

Not on macOS-with-`say`, or you would rather use your own recording:
`manu install --clip /path/to/ten-seconds.wav`.

### 3. Download the model and measure this machine

```sh
manu install
```

**This is the only network access Amanuensis ever makes**, and it happens once.
It fetches the ASR weights from Hugging Face over HTTPS at a pinned revision,
then re-hashes every downloaded file against a SHA-256 this project recorded
itself — a mismatch is refused, not warned about (§7.6). Then it runs nine timed
decodes on the clip from step 2 to find your machine's speed tier.

Expect a few minutes; the download was measured at 185 s on the author's
connection and yours will differ. It prints `checksums verified`, then your tier
and the p50 and p95 it measured. Those are your numbers, not ours.

It also writes **`~/Desktop/Start Amanuensis.command`**, a double-clickable
launcher. `manu install --no-desktop-launcher` skips it.

### 4. Grant two macOS permissions

The daemon needs **Accessibility** (to type into other applications) and **Input
Monitoring** (to see the hotkey). They are separate panes in System Settings →
Privacy & Security, and granting one does not grant the other.

**Run `manu daemon` first and let it ask.** It checks both grants, raises the
macOS dialog for each one it does not have, and prints the pane to open. Answer
the dialogs however you like — asking is what puts your terminal into those
lists in the first place. **A pane you open before anything has asked is empty**,
with no row to switch on.

**The entry you are looking for carries your terminal's name, not
"Amanuensis".** macOS attaches these grants to whatever launched the process, so
look for Terminal, iTerm, Ghostty or VS Code — whichever you ran `manu` from.
This is a real wart and it does not currently go away; an `.app` bundle would
fix it and none is scheduled (PRD §5.4 holds it in reserve as the fallback if
the recording panel fails its confidence test).

If your terminal still is not listed, add it with the `+` button. Terminal lives
at `/System/Applications/Utilities/Terminal.app`, which the file picker hides
until you press **Cmd-Shift-G** and paste that path.

**On macOS 26.6 you may have to do this for Input Monitoring.** Measured there
2026-09-14: the Accessibility dialog appeared, and the Input Monitoring one did
not — so that pane stayed empty until you added your terminal by hand.

That was `CGRequestListenEventAccess`, and on 2026-09-17 it was replaced with
`IOHIDRequestAccess`, which is the call that registers the process with TCC.
**This is not yet confirmed on 26.x.** Both machines this project is developed
on run macOS 27.0 holding both grants, so neither can reproduce the failure, and
a fix is unverified until it runs where it can fail. If the dialog appears, the
`+` route below is unnecessary. If it does not, the `+` route is the whole
procedure and nothing has regressed.

Run `python scripts/diagnose_permissions.py` either way — it asks every
candidate API on your machine and prints what each one answered, which is the
only way this gets settled.

### Escape cancels a hands-free dictation

Double-tap the hotkey and it latches — your hand comes off the key and the
dictation keeps running. **Press Escape to throw that dictation away**, or tap
the hotkey again to finish and process it normally.

A known cost, stated rather than hidden: **while a latched dictation is running,
Escape belongs to Amanuensis and no other application sees it.** It is taken
when the latch closes and given back the moment the microphone closes, so it is
yours again between dictations. Amanuensis does not watch your keyboard to do
this — it asks macOS for that one key, and is sent no other.

Escape **discards the recording and nothing is saved**. There is no
confirmation and no undo: the audio was never transcribed, so there is nothing
in `manu history` to recover.

The grant is read once at launch, so **restart `manu daemon`** after granting —
a running process does not notice.

### 5. Dictate

Double-click **`Start Amanuensis`** on your Desktop. A Terminal window opens and
stays open while Amanuensis runs; closing that window stops it. Step 4 wrote
that file — see [The Desktop launcher](#the-desktop-launcher) if it is not
there.

Or, from a terminal:

```sh
manu daemon
```

Hold **right-option**, speak, release. The text appears at your cursor in
whatever application has focus.

**A small pill sits near the edge of your screen the whole time the daemon
runs** — a short outlined pill while idle, growing into a live waveform while
the microphone is open. Those are deliberately two different sizes rather than
two shades of one: a panel that has frozen looks exactly like a resting one, and
telling "idle" from "stopped" is the whole reason the idle form exists. Turn it
off with `[feedback] overlay_idle = false` and nothing appears until you
dictate.

The growth is animated. `[feedback] overlay_animate = false` turns that off, and
so does macOS's own **Reduce Motion** — you do not have to set both.

There is also a glyph in your
menu bar — `○` idle, `●` recording, `◐` transcribing — and a panel near the edge
of the screen whenever the microphone is open. Stop with Ctrl-C, or from the
tray menu.

Two more menu-bar states worth knowing: `◍` means the collapse guard recovered a
transcript, so what landed was decoded without your `initial_prompt` and is less
reliable at proper nouns. `⚠` after a dictation means the words were withheld —
`manu history --last` has them.

### 6. Update

```sh
cd Amanuensis
git pull
pip install .          # required — the pull alone changes nothing
```

**`pip install .` in step 1 is not an editable install.** It copies the package
into your virtualenv, so `git pull` updates your checkout and leaves the `manu`
you actually run exactly as it was. This is the ordinary way to get a fix,
conclude it did not work, and report a bug against code you are not running.

Check which you have at any time:

```sh
manu --version
```

It prints the version, the directory the running code is in, and whether that
directory is a checkout git tracks (**follows `git pull`**) or a copy (**re-run
`pip install .`**). Restart the daemon afterwards; a running process keeps the
code it started with.

If you would rather have `git pull` be enough, install editable instead —
`pip install -e .` — at which point the checkout *is* the installed code.

### 7. Uninstall

```sh
manu history --purge                # transcripts, stored audio, and the database
pip uninstall amanuensis
rm -rf ~/Library/Application\ Support/amanuensis    # config, weights cache aside
```

The model weights live in the Hugging Face cache (`~/.cache/huggingface`) and are
shared with anything else that uses them; delete that separately if you want the
disk back. Revoke the two permissions in System Settings — uninstalling does not.

---

## Everyday use

```sh
manu install                        # download the model once, measure this machine's tier
manu daemon                         # hold right-option, speak, release
manu status                         # is it up, and on which model, mode and microphone
manu toggle                         # start or stop a dictation without the hotkey
manu history --last                 # the last transcript, even if injection failed
manu history --purge                # delete transcripts, stored audio and the database
manu vocab check                    # validate your replacement dictionary
manu transcribe --seconds 10        # one-shot diagnostic: record and print, inject nothing
manu transcribe --inject            # one-shot: record, persist, paste at the cursor
```

`manu status` and `manu toggle` talk to a running daemon over a unix socket at
mode `0600`. Any process running as you can send those; nothing on the network
can, and no transcript text ever crosses that socket. Only one daemon runs at a
time; a second refuses and names the first.

### Capture modes and the hotkey

**If right-option is taken on your machine, change it from the tray menu** — it
lists every supported binding and writes your choice to the config file. The
same menu switches capture mode, so you can try one rather than decide from a
description:

- **Hold to talk** (default, `push_to_talk`) — record while held. Nothing starts
  by accident.
- **Press to start, press to stop** (`toggle`) — for long-form dictation.
- **Press to start, silence ends it** (`vad_auto`) — needs VAD, and it is the
  mode most likely to misfire. It has its own `[vad_auto]` silence window and a
  `max_seconds` hard stop, because a detector that misses the end would
  otherwise leave the microphone open.

**Double-tap right-option to dictate hands-free**, then single-tap to finish.
This works inside hold-to-talk without giving it up, so both gestures live on one
key; a hold during a hands-free session is ignored on purpose. The window is
`double_tap_ms` and defaults to 350 ms, which is **a guess about your hand, not a
measurement** — set it to `0` for the hold gesture and nothing else.

### Picking your microphone

**The same menu picks your microphone.** `Device:` lists every input on the
machine, plus `System default`, which is what a fresh install follows. Two
reasons to change it. Dictating on Bluetooth headphones **interrupts whatever is
playing** — opening an input drops the headset out of A2DP into the mono headset
profile, which is macOS doing its job, not this product misbehaving — and pinning
the built-in microphone leaves the headset in A2DP and the music alone. And a
pinned microphone stays pinned when you plug something else in.

**The cost is not measured and you should assume there is one:** the built-in
microphone at arm's length is a worse recording than a headset at your mouth, and
no figure in this project describes how much worse. A microphone that is pinned
and then unplugged shows as `⚠ not connected` in the menu, and the next dictation
fails naming the devices you do have.

### The Desktop launcher

Step 3 wrote **`~/Desktop/Start Amanuensis.command`**. Double-click it and the
daemon starts in a Terminal window. Skip it next time with
`manu install --no-desktop-launcher`; delete the file whenever you like, and
re-run `manu install` to get it back.

There is **no application icon and no login item.** `manu daemon` in a terminal
is the whole product, and the launcher is a shell script that runs it for you —
not an `.app`. The daemon does not start at login and does not survive a reboot.

**The permission consequence is real.** macOS attaches Accessibility and Input
Monitoring to **whatever launches the process**. Double-clicking makes that
**Terminal.app** — not the terminal you normally type in. Grant them to whichever
you actually use, or to both.

`manu install` writes the launcher with the path of the `manu` that wrote it,
because a Finder launch inherits no shell profile: `manu` is not on `PATH` and
cannot be found by looking. If you later move or delete that environment the
launcher says so and names `manu install` as the repair, rather than failing with
`cannot find`. It never overwrites a file it did not write, and it leaves a
symlink alone.

```sh
~/Desktop/Start\ Amanuensis.command --check   # what it resolved; starts nothing
```

**From a source checkout**, `scripts/start-amanuensis.command --link` makes the
Desktop entry a **symlink into the checkout** instead, so it follows the tree as
you work rather than snapshotting it. `manu install` will not replace a symlink.
That matters because the first version of this file was hand-copied, the checkout
it named was later deleted, and the Desktop entry spent four days answering
`cannot find`.

### Spoken commands

Say "new paragraph" as a complete sentence and you get a blank line. **It
frequently will not fire**, and the reason is documented in PRD §7.5: the rule
needs sentence marks on both sides of the phrase, and the decoder often supplies
neither.

---

## Troubleshooting

- **`git clone` opened an Apple installer instead of cloning.** Expected on a
  Mac that has never built software — there is no `git` until the Command Line
  Tools are installed. Let it finish, then run the command again. See "Before
  step 1".
- **`zsh: command not found: python3.12`.** The command line tools ship an older
  Python. Install 3.12 from python.org; see "Before step 1".
- **A dialog asked whether Terminal may access my Documents folder.** macOS
  guards Documents, Desktop and Downloads. Say yes, or work in your home folder
  instead, which is what the install script does.
- **I pulled a fix and nothing changed.** `git pull` does not update a
  non-editable install. Run `pip install .` again and restart the daemon;
  `manu --version` says which kind of install you have. See step 6.
- **The Accessibility or Input Monitoring list is empty — there is nothing to
  toggle.** Nothing has asked for the grant yet, and macOS lists a process only
  once it has asked. Run `manu daemon`; it requests both and the rows appear.
  Failing that, add your terminal with `+` (Cmd-Shift-G, then
  `/System/Applications/Utilities/Terminal.app`).
- **Nothing happens when I hold right-option.** Input Monitoring is not granted
  to the terminal you launched from. `manu daemon` says so on startup.
- **The glyph goes `●` then nothing appears.** Accessibility is missing —
  transcription worked, injection did not. `manu history --last` has your words.
- **`⚠` after a dictation.** The collapse guard withheld the text because the
  decoder stopped early. `manu history --last` has what it got.
- **`manu install` says the reference clip is missing.** Step 2 — the clip is
  generated locally and is not in the repository.
- **Starting a dictation pauses my music / my AirPods sound worse.** macOS moves
  a Bluetooth headset out of playback mode when anything opens its microphone.
  Pin a different input and the headset is never touched: `[audio] device` takes
  any substring of a device name, so `device = "MacBook Pro Microphone"` in
  `config.toml` keeps dictation on the built-in mic. **The trade is unmeasured**
  — every accuracy figure here was recorded on a desk mic. `manu daemon` lists
  the devices it can see if the name does not match.
- **My double-tap does not latch.** 350 ms is a default, not a measurement of
  your hand. Raise `double_tap_ms` in the config file; set it to `0` to turn the
  latch off entirely and keep hold-to-talk.
- **A short deliberate tap feels slow to appear.** Expected, and it is the price
  of the latch: a release inside `double_tap_ms` waits out the rest of the window
  in case a second press is coming. Anything you hold for longer than that window
  — which is every real dictation — is unaffected. `0` removes both.
- **`zsh: command not found: manu` in a new terminal.** The commands live in the
  virtualenv and a new shell has not activated it. `source .venv/bin/activate`
  from the checkout, or link them onto your `PATH` as step 1 describes. The
  Desktop launcher is unaffected — it resolves the command itself and never
  relies on your `PATH`.
- **The Desktop launcher cannot find `manu`.** The environment it was installed
  into moved or was deleted. It names the path it was looking for; re-run
  `manu install` from the environment you want it to use. From a source checkout,
  `scripts/start-amanuensis.command --link` instead. Either way, `--check` on the
  launcher shows what it resolved without starting anything.
- **`manu daemon` refuses and names another daemon.** One at a time, on purpose.
  Two would both hold the microphone, both inject and both persist, and the
  menu-bar glyph on one would read idle while the other recorded.
- **I said "new paragraph" and got the words instead of a break.** Known; see
  Spoken commands above and PRD §7.5.

---

## Known costs, stated up front

The PRD's rule is that a cost gets documented rather than papered over. The first
two are **measured**, not argued.

- **Your transcripts go into your clipboard manager.** Not "may" — measured
  against a real one (Maccy) on default settings: every transcript was captured,
  including with clipboard restore on and its 150 ms window. That window is not a
  mitigation. This is the manager working correctly, and several managers sync
  across devices, so for those users a transcript leaves the machine as a direct
  consequence of the defaults.

  Amanuensis detects known managers and warns before recording starts, but
  detection is **incomplete by nature** — absence of a warning means "no known
  manager detected", never "no manager present". (§7.3)

- **`strategy = "keystroke"` avoids the clipboard and silently rewrites your
  text.** macOS text substitution applies to synthetic keystrokes exactly as it
  does to real ones. Typed into TextEdit:

  ```
  you said : don't use --dashes... "quoted" and i said so
  you get  : don’t use —dashes… “quoted” and I said so
  ```

  Five changes in one sentence — smart quotes, em dash, ellipsis,
  autocapitalisation. Pasting the same text is byte-identical. Nothing Amanuensis
  can do reaches another application's substitution settings, so this is a
  warning rather than a fix; turn substitution off in the applications you
  dictate into. The trade is real and unpleasant: the strategy that protects your
  privacy is the one that alters your words.

- **Zero-network verification covers this process only.** Packet capture on
  Amanuensis cannot see egress that happens inside a different process, which is
  exactly where the clipboard path goes. The Maccy result above *is* that blind
  spot, measured. (§2 G3)

### The collapse guard has two blind spots, and neither is fixed

§5.7's guard exists because `initial_prompt` can silently destroy a transcript: a
30.5-second dictation returned two words, no error, injected at the cursor. The
guard measures **decoded coverage** — how far into your audio the decoder got
before it stopped — and below half the audio is decoded again with the vocabulary
bias dropped; if that fails too the text is **not** injected. Verified on real
audio: fires at 8.3% coverage on a reproduced collapse, silent on all six corpus
samples with a floor of 82.8%
([`docs/gates/phase-2b-followup.md`](docs/gates/phase-2b-followup.md)).

Two things it cannot do, both established with controls at the Phase 3 gate and
both still true:

- **It cannot see a hole in the middle.** Coverage is the *end point* of
  decoding, not how much came back. One take lost 56 words spanning 27.7 s to
  49.4 s of a single dictation, and the guard reported **coverage 100.0%,
  passed**. Invisible by construction, not by oversight.
- **It cannot fire below about two seconds of speech.** The refusal threshold is
  unreachable under 2.00 s — measured on 11 of 11 short takes — because the
  numerator quantises to whole seconds at that length. Short dictation is the
  ordinary case for most people, and there the guard is decorative.

Both fail **open**: a bad short transcript is injected rather than withheld, so
you see it at your own cursor and can undo it. That is the safe direction, and it
is why this is documented rather than treated as a release blocker.

The false-positive direction — refusing something you actually said — is
**untested**, because six corpus samples from one speaker cannot produce a
speaker it is wrong about.

---

## What is measured

| Goal | Target | Status |
|---|---|---|
| Latency, Tier A | p50 ≤ 400 ms, p95 ≤ 800 ms — hotkey release → text present, 10 s utterance | **Met: p50 312.4 ms / p95 344.5 ms**, over ten dictations of 7.5–10.0 s recorded 2026-09-02 for this purpose, with the full shipped chain. [`docs/gates/g1-at-ten-seconds.md`](docs/gates/g1-at-ten-seconds.md) carries the conditions. **Read the scaling note below before quoting this figure** |
| Latency, Tier B | p50 ≤ 2 000 ms — published, not gated; a class missing it is dropped rather than shipped | **unmeasured.** No Tier B machine has run this. A simulated thread constraint is not a slower computer |
| Accuracy | edit rate ≤ 5% | **missed, at 8.59%**, over ten real dictations of 67–97 s at the Phase 3 gate. The threshold was deliberately **not moved**; the gap is carried as debt. 163 of 171 edits are the decoder's, 8 are the rules chain's ([`docs/gates/phase-3.md`](docs/gates/phase-3.md)) |
| Network traffic at runtime | zero | **verified twice**, most recently with pyobjc added: 0 sockets and 0 bytes against a control that saw 865 bytes. Scope caveat above |

Tiers are **measured, not named after silicon** (§7.2). CTranslate2 has no Metal
backend, so "Apple Silicon" was never a distinct execution path — a machine's tier
is decided by what it measures at install.

**The latency figure is for a ten-second utterance and it does not generalise
across lengths.**

| you spoke for | text appears after | n |
|---|---|---|
| **7.5–10.0 s** | **p50 312.4 ms / p95 344.5 ms** — the band G1 gates, measured deliberately | **10** |
| 10–60 s | **no band is published** — too few observations under known conditions | — |
| 67–97 s | p50 ≈ 0.9 s, and over 800 ms throughout — the Phase 3 corpus | 10 |

That is not a bug and not a missed goal: PRD §2 binds G1 at ten seconds and says
so. But dictating a paragraph is the ordinary case, and the headline number says
nothing about it, so both are here.

**The headline row is a dedicated recording, not a query over `history.db`.** A
band scraped from stored rows mixes configurations, machine load and product
versions. A first attempt at it on 2026-09-02 produced a p95 of **4014 ms**
because a test suite was running on the same machine; all nine takes were
discarded rather than the three outliers, because keeping the fastest six would
have been choosing the rows that flatter. Those rows were removed from the
database on 2026-09-03, after a backup — the `≤ 10 s` band read p95 **1558.2 ms**
with them and **344.5 ms** without. Until a `config_sha256` provenance column
exists, any band published from stored rows depends on nobody having run anything
heavy at the time, which is not a property a database can attest to.

> **Correction, 2026-08-31.** An earlier revision of this file published a fitted
> model, `transcribe_ms ≈ 49 + 13.7 × seconds`, and a 10/30/60 s table derived
> from it. **Those numbers were wrong and are withdrawn** — the model was fitted
> over n = 14 spanning 0.7–43.4 s and then used to predict at 60 s, outside the
> range it ever saw. No figure here is extrapolated to a duration that was not
> measured.

Every latency figure here is from **one machine and one speaker in one room**,
and **the latency claim is hardware-conditional.** Privacy motivation and offline
constraint correlate with older machines, so the users this exists for are
disproportionately the ones on the slower tier. PRD §4 says so in the same place
it makes the speed claim.

Injection is verified in TextEdit, Terminal, VS Code and Chrome, on both
strategies, by reading the text back out of each application rather than by eye.
Zero failures ([`docs/gates/phase-2a.md`](docs/gates/phase-2a.md),
[`docs/gates/phase-2b.md`](docs/gates/phase-2b.md)).

---

## Scope

**macOS only for v1.** Windows is post-v1 intent — it ships no code and gates
nothing, but the architecture carries a portability floor so the port stays a
port (§7.3). Linux is a non-goal.

Also out of scope for v1: streaming partials on screen, speaker diarization,
mobile, cloud sync, OS voice commands, and text-to-speech.

Design choices behind the current build:

- **Batch transcription**, not streaming, for v1 (PRD §7.1)
- **faster-whisper** by default, behind an abstraction so the engine can be
  swapped (§7.2)
- **Clipboard paste** by default with a keystroke fallback (§7.3)
- **Deterministic post-processing** first — a rules pass cleans whitespace,
  sentence capitalisation and punctuation spacing before injection, and
  `manu history --raw` shows what the model emitted before it ran. Two rules are
  deliberately absent: lowercasing a spurious mid-sentence capital
  (indistinguishable from a proper noun without a model) and folding spoken
  numbers into digits (measured harmful — *one thought ends* became *1 thought
  ends*). An optional local LLM cleanup pass is specified but **does not work
  yet**: tested 2026-07-31, it made transcription 5–28× worse on real output
  ([`docs/gates/phase5-feasibility.md`](docs/gates/phase5-feasibility.md))

---

## How this repository is built

Development is phase-gated. Each phase ends at an approval gate that states what
would **reject** it, and writes its measurements to `docs/gates/`. The
specification is reviewed adversarially before implementation: 12 objections, 13
choice stories and 7 slicing decisions in the first round, 9 more objections in
the second, all adjudicated, and every amendment carries a dated revision-log row.

That process is why this README can be specific about what is unmeasured, and the
gate records are why it can be specific about what is measured. Three of them
record a number that contradicted the specification.

| | |
|---|---|
| [`AMANUENSIS_PRD.md`](AMANUENSIS_PRD.md) | The standing specification — what and why |
| [`HARNESS.md`](HARNESS.md) | The operating contract — how work is allowed to proceed |
| [`CLAUDE.md`](CLAUDE.md) | Project conventions for AI-assisted development |
| [`docs/superpowers/`](docs/superpowers/) | Adversarial review records — 41 dispositions across two rounds, all resolved |
| [`docs/gates/`](docs/gates/) | One measurement record per phase gate, plus the probe and the Phase 5 experiments |
| [`docs/adr/`](docs/adr/) | Architecture decisions — 0001 selects the ASR engine |

## Licence

Apache-2.0 (intended). See PRD header for the reasoning.
