---
spec: docs/superpowers/plans/phase-4-tray-modes.md
date: 2026-09-02
mode: spec
cartographer_model: claude-opus-5[1m]
stories:
  - id: 1
    lens: [defaults, patterns, coherence]
    title: IPC listener has no thread assigned
    disposition: accepted
    disposition_rationale: "S6.3 gains a row for the IPC acceptor and its thread affinity is written down before the socket is built. Floor item 1's whole purpose."
  - id: 2
    lens: [defaults, consequences]
    title: Socket directory inherits platformdirs by analogy
    disposition: accepted
    disposition_rationale: "The platformdirs accessor is named explicitly in S4 rather than inherited by analogy, together with whether a stale socket survives a reboot."
  - id: 3
    lens: [alternatives, consequences]
    title: manu status contents decided by first slice
    disposition: accepted
    disposition_rationale: "manu status ships a contract, not an acceptance criterion. The recorded tier is included - the README publishes a per-tier table and the reader needs to know which row is theirs."
  - id: 4
    lens: [forces, defaults]
    title: vad_auto inherits the trimming VAD parameters
    disposition: accepted
    disposition_rationale: "vad_auto gets its own silence window. Sharing S7.2's measured trimming parameters means either two seconds of dead time per dictation or a user silently invalidating every figure this project has published."
  - id: 5
    lens: [defaults, coherence]
    title: Overlay ships without a config key
    disposition: accepted
    disposition_rationale: "The overlay's config keys and S5.4's unbuilt [feedback] sounds are both booked into S2 rather than lapsing in the phase that owns S5.4."
  - id: 6
    lens: [forces, alternatives]
    title: Overlay confidence test — no criterion, builder judges
    disposition: accepted
    disposition_rationale: "The criterion is written before the overlay exists. Who judges is named at the same time."
  - id: 7
    lens: [patterns, coherence]
    title: Errors routed through tray, not modelled upstream
    disposition: accepted
    disposition_rationale: "Errors are state the tray reads, not traffic routed through it. Whether TrayApp replaces RecordingIndicator is decided in S2 rather than discovered by two glyphs appearing in one menu bar."
  - id: 8
    lens: [consequences, coherence]
    title: Phase 4 gate drops the G2 revisit
    disposition: accepted
    disposition_rationale: "The G2 revisit is restored to the Phase 4 gate, where docs/gates/phase-3.md:330 put it."
  - id: 9
    lens: [consequences, alternatives]
    title: Engine rematch omits ADR 0001's deciding metric
    disposition: accepted
    disposition_rationale: "Deletion counts added to the benchmark deliverable - see objection O1."
  - id: 10
    lens: [consequences, defaults]
    title: Two new engines no pinned revision covers
    disposition: accepted
    disposition_rationale: "D2 resolves it: manu install stays, so the download is not in the daemon and the capture's subject is unchanged. Pinned revisions for the two new engines are required before any of their numbers reach a user-facing surface."
  - id: 11
    lens: [consequences, defaults]
    title: spoken_commands stays off by never deciding
    disposition: accepted
    disposition_rationale: \"Exits 2 and 3 together: the default is flipped ON and the sunset clause is rewritten to a condition that can discriminate - retire it if it does not fire across 20 dictations in which the phrase was actually spoken. Deleting on the Phase 3 zero would have discarded the product's only structure mechanism on a measurement that could not have come out otherwise. Checking this found a third fact neither the clause nor the gate knew: _COMMAND_RE needs a terminator on BOTH sides, and S7.5's dominant defect is Whisper omitting exactly those marks - so the rule's trigger is defeated by the error class it sits next to. Recorded in S7.5 and pinned by a test, not fixed: loosening the anchors is the change that deleted three content words once."
  - id: 12
    lens: [alternatives, forces]
    title: The gate's second person, unnamed and single-use
    disposition: accepted
    disposition_rationale: "The archetype is named in advance and recorded in the gate record, and the 30-minute stop is reconciled with the 185 s download and the nine-run tier check that sit inside it."
---

# Choice stories — Amanuensis Phase 4 plan

Twelve decisions the plan makes without recording that it is making them. Four
operator decisions were taken explicitly and are not relitigated here; these are
the ones made by omission, by ordering, or by inheriting a default nobody
re-examined.

## #1 — IPC listener has no thread assigned

§6.3's table has exactly four rows — `TrayApp` on main, `HotkeyListener` on the
OS event tap, `AudioCapture` on the PortAudio callback, and one worker draining
sessions. A socket listener is a fifth concern and the table has no row for it.

**Forces.** Accepting a connection is blocking I/O; §6.3's rule is that
`DictationController`'s methods must not block the thread that calls them, and
nothing touching the UI runs off main. An IPC command that starts a dictation has
to cross from wherever it is read into the controller, and the plan does not say
where.

**Options not taken.** A dedicated accept/serve thread — the obvious POSIX shape,
adds a fifth row and a third producer into the session queue. A main-thread
runloop source (`CFSocket` / `NSFileHandle`) — keeps the count at four but
couples the IPC surface to AppKit, the opposite of portability floor item 3.
Serving from the existing worker — free until the worker is mid-transcription, at
which point `manu status` blocks behind a decode.

**Choice as written.** The plan chose by asserting coverage: threading is
"already named in §6.3", so no work is booked. §6.3 names four threads and none
serves a socket, so the placement will be settled by whoever writes the slice —
precisely the outcome §7.3's floor item 1 exists to prevent ("a model that is
never written down gets re-derived rather than ported"). Item 1 was raised about
the tray's main thread; the plan reproduced its failure shape one component over.

**Pattern.** Acceptor-Connector (POSA vol. 2) is the missing half of the
Half-Sync/Half-Async structure §6.3 already names — the acceptor's thread
affinity is exactly what that pattern makes explicit and what the table omits.

**Note.** This is the sharpest answer to "was each actually settled by the PRD?"
The transport *is* settled (§6.1 and §7.3 item 3 both name the unix socket and
the abstraction). The threading is *not*.

## #2 — Socket directory inherits platformdirs by analogy

§5.3 resolves the *config* directory through `platformdirs` with
`$AMANUENSIS_CONFIG_DIR`; §5.5 resolves the *data* directory with
`$AMANUENSIS_DATA_DIR`. §7.3's floor item 2 is written against those two by name.
Nothing in the PRD names a runtime or socket directory, and there is no third
override variable.

**Forces.** A socket has a different lifetime from both a config file and a
database. Config and data persist across reboots and are backed up; a rendezvous
point for a running process should not be either.

**Options not taken.** `platformdirs.user_runtime_dir` — right lifetime, longest
path. The data directory alongside `history.db` — most symmetric with §5.5, puts
a socket inside a directory the user may sync. An explicitly specified short path
with a stated reason — what §5.3 did for `$AMANUENSIS_CONFIG_DIR`.

**Choice as written.** "Resolved through `platformdirs`" without saying which
accessor, treated as inherited rather than new. Floor item 2's rule is about not
hardcoding; the plan read it as "platformdirs answers all path questions." It does
not answer this one, because the PRD never asked it.

**Consequences.** Three undecided things follow. Whether a stale socket survives a
reboot (data dir: yes; runtime dir: no) determines what liveness detection
`manu status` needs. The override symmetry breaks: two daemons under two
`$AMANUENSIS_CONFIG_DIR` values get one socket unless a third variable exists.
And whichever directory is picked becomes a migration rather than an edit the
moment a user has one on disk — floor item 2's own closing sentence.

## #3 — manu status contents decided by first slice

Three documents specify what `manu status` reports and they do not agree.
`cli.py:112` registers it as "report daemon, model, and permission state". PRD
§7.2 says it "reports the recorded tier". The plan ends at "prints live daemon
state from a second process."

**Forces.** A status command is the natural sink for every fact the product
knows. Against: the slice's purpose is to prove the transport works, and the tier
is not daemon state at all — §7.2 calls it "a recorded fact about a machine",
decided once at install, readable without a daemon and unanswerable by an IPC
round trip.

**Choice as written.** The narrowest of the three, by writing an acceptance
criterion rather than a contract. Permission state and the recorded tier are
dropped by silence.

**Consequences.** The README publishes a per-tier latency table, and a user
reading it has no way to find out which row applies to them if `manu status` does
not say.

## #4 — vad_auto inherits the trimming VAD parameters

`[vad]` exists with `threshold = 0.5`, `min_silence_duration_ms = 2000`,
`speech_pad_ms = 400`, added at Phase 1 for *trimming silence before
transcription*. §5.3's comment: "defaults are the ones §7.2's figures were
measured under; changing one invalidates them." The plan introduces a second
consumer — deciding when an utterance has *ended* — and names no keys.

**Forces.** The two uses want opposite settings. Trimming wants a long silence
window, because cutting into speech loses words and §7.2's numbers were taken at
2000 ms. End-of-utterance detection wants a short one, because 2000 ms before the
session closes is two seconds of dead time on every dictation in the mode — and
G1 is the product. One parameter set cannot serve both directions.

**Choice as written.** The shared parameter set, by not mentioning parameters.
§5.2 says `vad_auto` should "ship behind a flag; it is the mode most likely to
misfire" — the plan reads the mode selector as that flag, which leaves the
misfire behaviour itself untunable.

**Consequences.** If shared, a user who shortens `min_silence_duration_ms` to make
`vad_auto` responsive silently moves the configuration every G1 and edit-rate
figure in this project was measured under — including the ones the README is about
to publish. If split, §5.3's block grows by three keys and the plan books no such
amendment.

## #5 — Overlay ships without a config key

§5.3: every behavioural decision that could reasonably go either way is a config
key with a sane default, with **one** bounded exception — behaviour a stated
guarantee depends on is not user-settable. §5.3 explicitly says enumerating a
fourth instance would be the wrong response to the next collision. The plan adds
a persistent on-screen panel and names no key.

**Forces.** An always-present overlay is exactly what a user wants to move, dim,
or switch off. But §5.4 says the user must always know whether the mic is live
and calls it non-negotiable, which is the shape of a stated guarantee. Both
readings are available and the plan takes neither.

**Options not taken.** `[feedback]` keys for the overlay, accepting that the
guarantee becomes user-defeatable — noting §5.4 records that macOS's own
microphone indicator serves the *correctness* half regardless, which is a real
argument that the overlay is a confidence feature and therefore ordinary. Invoke
the bounded exception explicitly, against §5.3's advice. Appearance keys but no
off switch — threads the needle, needs arguing rather than assuming.

**Second omission, same shape.** §5.4 promises `[feedback] sounds = true` for an
audio cue on start and stop. That key appears nowhere in §5.3's TOML block and
nowhere in `config.py`, and the plan does not book it — so a §5.4 deliverable
that was already half-specified lapses in the phase that owns §5.4.

**Consequences.** §5.3's rule is described as ratcheting. A phase that adds a
whole UI surface and zero keys is the first phase that stops the ratchet without
saying so.

## #6 — Overlay confidence test: no criterion, builder judges

Operator decision 1 makes the bundle conditional on the overlay "still failing the
confidence test at the gate". §5.4's requirement exists because the Phase 2b
indicator met the specification to the letter and its first user reported that a
glyph is not enough. The confidence test is therefore a subjective report by a
user — and the plan does not say which user, at what moment, against what
description of success.

**Forces.** Writing the criterion in advance risks specifying the wrong thing for
a requirement whose whole provenance is that specification was insufficient.
Against: an unwritten criterion judged after construction, by the person who built
it, is judged by someone who has spent a phase acquiring confidence from sources
other than the overlay.

**Options not taken.** Write it into the amendments — a falsifiable form exists
("with a fullscreen app focused and the menu bar hidden, the operator can answer
*is the mic live* without moving the pointer"). Delegate the judgment to the
gate's second person, the only non-author user the phase contains. Build the
bundle unconditionally and drop the test.

**Choice as written.** Defer the criterion to the gate and leave the judge
unnamed, which resolves both to the operator by default. And make a scheduling
decision depend on that judgment, so the unwritten criterion governs work, not
just documentation.

**Note.** Reading this as "a test that cannot fail" is failure-shaped and belongs
to the diaboli record (O10). The choice recorded here is narrower: who judges, and
when the criterion is fixed.

## #7 — Errors routed through tray, not modelled upstream

The plan restates the boundary — status surface, no business logic — then delivers
"error surfacing through tray + overlay" and reports restore failure "through" it.
Both describe errors as *travelling through* the UI rather than as state the UI
reads.

**Forces.** The existing precedent points the other way and is implemented:
`DictationState` is defined in `dictation_controller.py:101` and imported by
`ui/indicator.py:38`, which maps five states to five glyphs and owns no policy.
Errors resist that shape, because an error has a lifetime a state enum does not
model — what raised it, whether it has been seen, when it clears. Something must
own that, and the plan's phrasing puts it in the surface.

**Options not taken.** Extend the controller's state model so an error is a value
the tray renders exactly as it renders `RECORDING` — cheapest, preserves the
boundary, but a single enum cannot carry a message or a lifetime. An
error/notification model in `models/results.py` owned by the controller, tray as
pure renderer — more code, keeps the boundary literal. Let `TrayApp` own
presentation policy and amend §6.2's "no business logic" line to say what that
excludes — honest, and the plan does not book the amendment.

**Consequences.** By the end there are three renderers of the same state —
`RecordingIndicator` (shipped), `TrayApp`, the overlay — and the plan never says
what becomes of the first. §6.4 lists `ui/indicator.py` and `ui/tray.py` as
separate files, and two live `NSStatusItem`s would put two glyphs in one menu bar.
A fourth tray obligation is unbooked entirely: §5.4 and §7.3 assign the persistent
clipboard-exposure indicator to Phase 4, and the plan's tray criterion is scoped
to `DictationState`, which does not contain it.

## #8 — Phase 4 gate drops the G2 revisit

The plan's gate section lists the n=1 install observation and the second G3
capture, and states the gate is unchanged. The Phase 3 gate record assigned a
third: "**Operator disposition, 2026-09-02: G2 stays at 5%, recorded as missed** …
The number is revisited at the Phase 4 gate, where the model question is settled"
(`docs/gates/phase-3.md:330`). The plan books the engine benchmark that settles
the model question and does not book the revisit it was for.

**Forces.** A gate that carries every deferred question becomes unpassable, and
this one already carries a human-subject test and a packet capture. Against: the
Phase 3 disposition's reasoning was explicitly sequential, and that sequence only
works if the second half is scheduled where the first half lands.

**Choice as written.** Carry G2 unscheduled, by asserting the gate is unchanged
when the previous gate had changed it. The plan does correctly catch the other
Phase 3 carry-forward of the same shape — G1 at ten seconds — which makes the
omission of G2 an inconsistency inside the plan's own method rather than an
oversight of method.

**Consequences.** This project has a documented pattern of gate conditions that
outlive the gate that carried them — `docs/gates/phase-3.md:204` names three
instances. G2 unscheduled at Phase 4 is the fourth, and it lands in the phase that
publishes a user-facing accuracy claim.

## #9 — Engine rematch omits ADR 0001's deciding metric

Moonshine was already benchmarked and declined on 2026-08-01
(`docs/adr/0001-engine-selection.md`): it is the fastest candidate measured, every
WER pair involving `tiny.en` was statistically indistinguishable, "so the rate
could not decide it. The **error breakdown** did: Moonshine deletes 12–14 words
where the faster-whisper models delete 2–7." Deletion counts are not in the plan's
deliverable list.

**Forces.** The Phase 3 corpus is the project's best real-dictation evidence and
edit rate is its native metric. Against: §7.2's reopening clause is specific about
what is unmeasured — "neither has been benchmarked **for punctuation**" — and ADR
0001's closing condition is equally specific — "Reconsider if G1 headroom becomes
binding." Neither condition is "re-measure edit rate".

**Choice as written.** Reopen a closed decision on a different metric set than the
one that closed it, without saying so. And schedule no decision: the slice produces
numbers, no slice changes `[engine] backend` or `model`, so the phase measures four
engines and ships the default it started with unless someone acts between slices.

**Consequences.** If deletions are not counted, a rematch on edit rate can
recommend an engine ADR 0001 refused for a reason edit rate cannot see — §8 exists
to refuse silent data loss, and a deleted word is invisible in text the user has
not read.

## #10 — Two new engines no pinned revision covers

`faster_whisper.py:101` carries `PINNED_REVISIONS` for three models; `manu install`
is registered at `cli.py:189`; `ModelNotAvailableError` is documented "Weights are
not on disk, and this process will not go and get them." The pin list's own
comment: "Only models this project has actually resolved a revision for are
listed; anything else downloads at its default revision and says so."

The plan adds Moonshine and Parakeet, whose weights come from different
repositories with different layouts, and writes the install slice as though one
model family exists.

**Choice as written.** Treat the install path as new work on a single family, and
do not connect it to the two additions. Separately, "Hugging Face download **at
first run**" reverses an implemented refusal without noting it: §7.6 says weights
download "once at install… **Never at runtime**", `manu install` is that install,
and `ModelNotAvailableError` is the code that enforces it. If "first run" means the
daemon's first start, that is a change to §7.6 and to the second G3 capture's
subject; if it means `manu install`, the decision is a restatement.

**Consequences.** Which process performs the download determines what the gate's
packet capture sees. A download bound to the daemon puts an HTTPS fetch inside the
process whose network silence is the headline claim, and the qualification the plan
already writes does not cover it.

## #11 — spoken_commands stays off by never deciding

§5.3's comment on the key carries a sunset clause: "Off by default because it
DELETES content words and nothing measures it… The Phase 3 gate reports its firing
rate; **if it changes nothing, the code goes**." The gate ran it:
`docs/gates/phase-3.md:148` records that it "stays `false`. It reported as a
candidate rather than firing … so its rate is measured at zero lossiness."

**Forces.** The key was written with two exits — turn it on, or delete it — and the
measurement that was supposed to choose returned "never fired", which is evidence
for deletion under the clause as written and evidence for nothing under a fair
reading (no take in either corpus contains a spoken command, so the corpus could
not have made it fire).

**Choice as written.** A fourth option, by describing the flip as available rather
than as a decision: keep the code, keep it off, schedule nothing. That is precisely
the state §5.3's sunset clause was written to prevent, and because Phase 5 is
unscheduled, "meanwhile" has no end.

**Consequences.** The product ships to a second person at this gate with no way to
produce a paragraph break, and with a code path that can delete content words
sitting inert behind a key whose retirement condition has been met and not acted
on.

## #12 — The gate's second person, unnamed and single-use

The plan carries §9's conduct rules forward faithfully and adds nothing about
*who*. §9 says to note their starting environment; §4 defines two user archetypes
and they would fail differently on this artifact.

**Forces.** n=1 is stated and accepted; the honesty comes from the conduct rules,
not the sample. But at n=1 the choice of subject *is* the sampling design. A
technical subject produces a systematically shorter defect list and will route
around a README gap the gate exists to find; a non-technical subject may not clear
macOS's Accessibility and Input Monitoring dialogs inside 30 minutes, and the gate
then measures the permission model rather than the README.

**Options not taken.** Name the archetype in advance and record it. Recruit
against the harder archetype deliberately, on §4's grounds. Give the same person
the overlay confidence test (#6) — they are the only non-author user the phase
contains, and the one judgment the plan leaves unassigned is exactly the kind only
a fresh user can make.

**Choice as written.** "Whoever is available", by silence, used once. And no
reconciliation of the 30-minute stop with what the install now contains: §7.2
records a one-time model download measured at 185 s on this machine's connection,
plus a nine-run tier check with a warm-up — both inside the subject's clock, on
their connection, before a first dictation is possible.
