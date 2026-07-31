# Phase 0 gate — Scaffolding

**Date:** 2026-07-31
**Branch:** `phase-0-scaffolding`
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), macOS 27.0
**Interpreter:** CPython 3.14.5 (package targets ≥ 3.12 — see finding 2)

**Verdict: PASS.**

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

### 1. §5.3's macOS config path contradicts its own instruction — **amendment needed**

§5.3 says, in one sentence:

> Single TOML file at the platform config directory (`platformdirs`;
> `~/.config/amanuensis/config.toml` on macOS — see §7.3's portability floor).

Those are two different paths. `platformdirs.user_config_dir("amanuensis")` returns
`~/Library/Application Support/amanuensis` on macOS; it returns `~/.config/...` only
on Unix. §5.5 has the same problem for `~/.local/share/amanuensis/history.db`.

The gate resolves it — a hardcoded path is an explicit reject — so the
implementation follows `platformdirs` and the PRD's stated macOS paths are now
wrong. **§5.3 and §5.5 should be amended to drop the literal paths**, or to name
`~/Library/Application Support/amanuensis/` if the intent was to document where
files actually land.

This is worth more than a typo correction: portability floor item 2 exists because
"changing this after users have config files on disk is a migration, not an edit."
The PRD stated the correct rule and then wrote down the path the rule forbids.

### 2. The floor is Python 3.12, not 3.11 — **amendment needed if §7.0 names a version**

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

## Outstanding at this gate

**The 2026-07-31 PRD amendments still have no independent adversarial review.**
Phase 0 hardens against §6.3's ABC classification, §6.3's config decision, and
§7.3's portability floor — all amended on 2026-07-31, all applied
recommendation → approval → document with no review step. An `advocatus-diaboli`
pass was dispatched alongside this phase; its record is not in hand at the time of
writing. **If it lands objections against §6.3 or §7.3, this scaffold is where they
land**, and the cost of changing it is at its lowest right now.

## Rollback

Everything is additive on a branch. `git checkout main` restores the pre-Phase-0
tree; nothing outside `src/`, `tests/`, `pyproject.toml` and this file was touched.
