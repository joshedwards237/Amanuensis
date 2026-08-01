# Phase 0 gate — Scaffolding

**Date:** 2026-07-31
**Branch:** `phase-0-scaffolding`
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), macOS 27.0
**Interpreter:** CPython 3.14.5 (package targets ≥ 3.12 — see finding 2)

**Verdict: PASS — gate closed 2026-07-31.**

All six gate conditions met. Both findings requiring a PRD amendment are **applied**
(§5.3, §5.5, §5.6, §7.0, §7.3, §8 — see the revision log). The adversarial review that
was outstanding when this record was first written **ran and was adjudicated**: nine
objections, all nine accepted, one of which (A6) landed on code committed inside this
phase and was fixed before the gate closed. Phase 1 may begin.

---

## What the gate asked

PRD §9, Phase 0:

> **Gate:** `manu --help` runs, `mypy --strict src/` is clean, config loads and
> rejects a malformed file with a useful error.
>
> **Rejects if:** any of the three fails, a config/history path is hardcoded rather
> than resolved through `platformdirs`, or `config.py` exposes a module-level
> instance or a `.get()` accessor (§6.3). All are mechanical; there is no judgment
> here.

## What was measured

| Gate condition | Result | Evidence |
|---|---|---|
| `manu --help` runs | **PASS**, exit 0 | Console script installed from `[project.scripts]`; help lists all four verbs |
| `mypy --strict src/` clean | **PASS** | `Success: no issues found in 18 source files`. Also clean across `src/ tests/` — 22 files |
| Config loads | **PASS** | Missing file yields §5.3's documented defaults; a partial file overrides only what it names |
| Malformed config rejected usefully | **PASS** | `manu: engine.cpu_thred: unknown key. Known keys in [engine]: backend, cpu_threads, device, initial_prompt, language, model` |
| No hardcoded config/history path | **PASS** | `grep -rn '\.config/\|\.local/share\|Application Support\|expanduser\|Path.home()' src/` → no matches |
| No module-level instance, no `.get()` | **PASS** | Asserted in `tests/test_config.py`, by scanning `vars(config)` for an `AppConfig` instance and `hasattr(AppConfig, "get")` |

Supporting: `ruff check src/ tests/` clean, `black --check` clean, **53 tests pass**.

"Rejects with a useful error" was the one condition worth writing carefully. A gate
that only checked *that* it raised would pass on a bare `KeyError`. Every rejection
test asserts on the message *content* — the fully-qualified key, the expected type,
and the permitted values — because that is the property the condition is about.

## What was built

```
src/amanuensis/
├── __init__.py           version only; importing the package imports nothing heavy
├── __main__.py           python -m amanuensis
├── cli.py                four verbs, all refusing with the phase that builds them
├── config.py             load_config() -> frozen AppConfig, schema-driven validation
├── models/
│   ├── session.py        DictationSession, LatencyBreakdown (g1_ms vs total_ms)
│   └── results.py        InjectionResult, PermissionStatus
├── engines/
│   ├── base.py           TranscriptionEngine ABC        [replacement]
│   └── registry.py       backend string -> class, lazy
├── injection/
│   ├── base.py           TextInjector ABC               [platform selection]
│   └── factory.py        sys.platform -> injector
├── hotkey/
│   ├── base.py           HotkeyListener ABC             [platform selection]
│   └── factory.py        sys.platform -> listener       (§7.3 floor item 4)
└── postprocess/
    └── base.py           TextPostProcessor ABC          [composition]
```

Every ABC carries its §6.3 classification in its module preamble, because the kind
is what determines the dispatch mechanism and a later reader will otherwise have to
re-derive it.

Both dispatch paths keep two failure modes distinct, deliberately: an **unknown**
name is the user's typo and lists the valid names; a **known but unbuilt** name is
our gap and names the phase that closes it. Collapsing them into "not found" would
tell a user their config was wrong when it was right.

## Deferred, by design

Not built, and their absence is not an omission:

- `controllers/`, `audio/`, `storage/`, `ui/`, and every concrete implementation.
  §6.4 is the **finished** layout, not the Phase 0 deliverable. Phase 0 is "all ABCs
  defined with no implementations" — creating empty modules to match a diagram would
  be scaffolding for the scaffolding.
- `DictationController`. Contracted in §6.3 but not an ABC; it arrives in Phase 2b
  with something to orchestrate.
- Runtime dependencies. `pyproject.toml` pins only `numpy` and `platformdirs`;
  faster-whisper, sounddevice, onnxruntime and the tray toolkit arrive with the
  phase that first needs them, so a broken ASR wheel cannot block work on the CLI.

## What this phase revealed that the PRD got wrong

§9's standing question. Six findings, the first two needing an amendment.

### 1. §5.3's macOS config path contradicted its own instruction — **applied**

§5.3 says, in one sentence:

> Single TOML file at the platform config directory (`platformdirs`;
> `~/.config/amanuensis/config.toml` on macOS — see §7.3's portability floor).

Those are two different paths. `platformdirs.user_config_dir("amanuensis")` returns
`~/Library/Application Support/amanuensis` on macOS; it returns `~/.config/...` only
on Unix. §5.5 has the same problem for `~/.local/share/amanuensis/history.db`.

The gate resolves it — a hardcoded path is an explicit reject — so the
implementation follows `platformdirs` and the PRD's stated macOS paths are now
wrong. **Applied 2026-07-31**: §5.3, §5.5 and §5.6 now resolve through `platformdirs` and
name the macOS location correctly, with the `$AMANUENSIS_*_DIR` overrides stated.
§7.3's floor item 2 records that it stated the rule and then wrote down the paths the
rule forbids.

This is worth more than a typo correction: portability floor item 2 exists because
"changing this after users have config files on disk is a migration, not an edit."
The PRD stated the correct rule and then wrote down the path the rule forbids.

### 2. The floor is Python 3.12, not 3.11 — **applied**

`requires-python = ">=3.12"`, not `>=3.11`. Not a preference: the installed numpy's
type stubs use PEP 695 `type` statements, which mypy only parses under a 3.12+
target. Under `python_version = "3.11"` the gate condition `mypy --strict src/`
fails on numpy's own stubs before checking a line of this project's code —

```
numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater
```

— which would have made a named gate condition unsatisfiable for reasons unrelated
to the code being gated. 3.11 also buys nothing here: `tomllib` is 3.11+, and 3.12
is the oldest release still receiving security fixes for the lifetime of a v1.

### 3. `[postprocess] chain` disagrees with itself across sections

§5.3's inline comment reads `chain = ["rules"] # ordered: rules | llm`, but §6.2's
component tree lists three post-processors: `RuleBasedPostProcessor`,
`VocabularyPostProcessor`, `LocalLLMPostProcessor`. Validation accepts all three —
`vocabulary` is a real processor with a real config section (§5.6) and rejecting it
would make the custom-vocabulary feature unreachable. §5.3's comment should list it.

### 4. `chain` and `llm.enabled` are two switches for one thing

§5.3 gives the LLM pass an `enabled` flag *and* a position in `chain`, with nothing
saying which wins. Four combinations exist and only two are meaningful. Phase 0
rejects the two incoherent ones at load time rather than picking a winner silently:

- `llm.enabled = true` with an empty `model_path` → rejected
- `"llm"` in `chain` with `llm.enabled = false` → rejected

That is a stopgap. The real fix is to decide whether membership in `chain` *is* the
enable switch and delete the other, which is a §5.3 decision, not an implementation
one. Flagged rather than taken, because the §5.3 rule about not renaming keys
without amending the PRD applies to deleting them too.

### 5. Two environment variables exist that no PRD section authorises

`AMANUENSIS_CONFIG_DIR` and `AMANUENSIS_DATA_DIR` override path resolution. §5.3's
rule — every decision that could reasonably go either way becomes a config key —
structurally cannot cover the location of the config file, because that setting is
what *finds* the config file.

This is the same shape as §5.3's bounded exception added on 2026-07-31 (behaviour a
stated guarantee depends on is not user-settable): a second case the absolute rule
does not reach. Two cases is a pattern. §5.3 should either name environment
overrides explicitly or state that path resolution is outside the key-per-decision
rule.

### 6. `cpu_threads = "auto"` must not be resolved at load time

Not a PRD error — a decision the PRD leaves open that the implementation had to
close. `"auto"` is preserved verbatim through load and validation, and
`resolve_cpu_threads()` is a separate call. Resolving it during load would produce
an `AppConfig` holding `10` on this machine and `4` on another *from the same file*,
which makes a config pasted into a bug report stop meaning anything. Measured here:
`resolve_cpu_threads("auto")` → **10** (`hw.perflevel0.physicalcpu`), matching the
probe's measured optimum and 2.5× CTranslate2's default of 4.

---

## The adversarial review — resolved, and it did land here

When this record was first written the 2026-07-31 amendments had no independent
review, and this section said that if objections landed against §6.3 or §7.3, the
scaffold was where they would land. **One did.**

`advocatus-diaboli` returned nine objections against the amendment set
(`docs/superpowers/objections/amanuensis-prd-2026-07-31-amendments.md`), seven high
or critical. All nine were adjudicated and accepted. Three bear on Phase 0:

**A6 — accepted, and it was a defect in code committed by this phase.** §6.3 said
"callers observe completion through the session" while `DictationSession` had no
flag, no event and no lock — leaving polling a mutable dataclass across a thread
boundary as the only available reading, which is the thing Half-Sync/Half-Async is
chosen to avoid. `models/session.py` had implemented that contract faithfully,
docstring and all. The session now carries a `threading.Event` with an explicit
write-then-signal ordering rule and a `wait()` method, covered by four tests
including one that asserts the ordering against a real thread. The spec was wrong
and the code was faithful to it; only review caught that.

**A1 — accepted.** §7.2 defined Tier A by the same predicate §9's Phase 1 gate
tested, so the project's top risk had a mitigation with no reachable failing state.
Phase 0 did not encode this — it is a spec defect — but Phase 1 would have started
against it, which is the phase this gate releases.

**A8 — accepted, and the code was already right.** §7.2 said `cpu_threads = "auto"`
branches on OS; `config.py` branches on whether the sysctl resolves and falls back
to the total core count, never to CTranslate2's default of 4. The spec was amended
to match the implementation rather than the reverse. The spec also said
`hw.perflevel0.logicalcpu` where the code queries `physicalcpu`; on Apple Silicon
both return 10, and physical is the more defensible of the two.

**This is the argument for running the sentinel before the scaffold hardens, made
concrete.** A6's fix cost one field, one method and four tests because nothing had
been built on the old contract yet. After Phase 2b it would have been a change to
the threading model of a running daemon.

## Gate decision

**PASS, closed 2026-07-31.** Conditions met, findings applied, review adjudicated.

Phase 1 is released. It inherits one known-open item that is not a Phase 0 defect:
Phase 5 is `UNRESOLVED, corpus-blocked` (§9), pending 6–10 samples of spontaneous
unscripted speech. Nothing in Phase 1 depends on it — every candidate approach
satisfies the `TextPostProcessor.process(text, session) -> str` contract frozen
here, which is why it was safe to freeze before the experiments returned.

## Rollback

Everything is additive on a branch. `git checkout main` restores the pre-Phase-0
tree; nothing outside `src/`, `tests/`, `pyproject.toml` and this file was touched.
