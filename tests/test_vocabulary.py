"""`vocabulary.toml` — the file, the matcher, and the reload.

PRD §5.6 promised "case-insensitive whole-word substitutions" and the dictionary
spec's §4 established that whole-word is the wrong shape: `spread sheet ->
spreadsheet` is two tokens becoming one, and it is what the model produces when
it half-hears the word. A whole-word map catches `breadshoe` and misses the
commoner error.

The tests that matter most here are the ones about **not** transforming:
replacement is literal (dictionary objection O4 rejected the casing heuristic as
§7.3's hazard re-committed), rules do not cascade, and a key does not fire
inside a longer key's match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amanuensis.config import ConfigError, PostprocessConfig
from amanuensis.models.session import DictationSession
from amanuensis.postprocess.base import TracedPostProcessor
from amanuensis.postprocess.vocabulary import (
    Vocabulary,
    VocabularyLoader,
    VocabularyPostProcessor,
    load_vocabulary,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "vocabulary.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _session() -> DictationSession:
    from datetime import UTC, datetime

    return DictationSession(
        id="v-1",
        started_at=datetime(2026, 8, 8, tzinfo=UTC),
        audio=None,
        sample_rate=16000,
    )


def _processor(path: Path) -> VocabularyPostProcessor:
    return VocabularyPostProcessor(PostprocessConfig(), VocabularyLoader(path))


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    """A user with no dictionary has not made a mistake (B8)."""
    vocabulary = load_vocabulary(tmp_path / "nothing.toml")
    assert vocabulary.replacements == {}
    assert vocabulary.boost_terms == ()


def test_a_malformed_file_names_the_problem(tmp_path: Path) -> None:
    """Same contract as `config.py`: the user is looking at a TOML file they
    just edited, and a `KeyError` tells them nothing."""
    path = _write(tmp_path, '[replace]\n"breadshoe" = \n')
    with pytest.raises(ConfigError) as excinfo:
        load_vocabulary(path)
    assert str(path) in str(excinfo.value)


def test_a_non_string_replacement_names_the_key(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"csp" = 42\n')
    with pytest.raises(ConfigError) as excinfo:
        load_vocabulary(path)
    assert "csp" in str(excinfo.value)


def test_an_unknown_table_is_rejected(tmp_path: Path) -> None:
    """Unknown keys are errors rather than being silently ignored — a typo that
    is quietly discarded presents as the feature not working."""
    path = _write(tmp_path, '[replacements]\n"csp" = "CSV"\n')
    with pytest.raises(ConfigError) as excinfo:
        load_vocabulary(path)
    assert "replacements" in str(excinfo.value)


def test_an_empty_key_is_rejected(tmp_path: Path) -> None:
    """An empty key would match at every position in the alternation."""
    path = _write(tmp_path, '[replace]\n"" = "CSV"\n')
    with pytest.raises(ConfigError):
        load_vocabulary(path)


# ---------------------------------------------------------------------------
# Matching (B3, B5, B6, B7)
# ---------------------------------------------------------------------------


def test_a_single_word_is_replaced(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"breadshoe" = "spreadsheet"\n')
    assert _processor(path).process("open the breadshoe", _session()) == (
        "open the spreadsheet"
    )


def test_matching_is_case_insensitive(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"breadshoe" = "spreadsheet"\n')
    processor = _processor(path)
    for text in ("Breadshoe", "BREADSHOE", "breadshoe"):
        assert processor.process(text, _session()) == "spreadsheet"


def test_a_phrase_is_replaced(tmp_path: Path) -> None:
    """The case PRD §5.6's "whole-word" wording could not express, and the one
    the operator actually hit."""
    path = _write(tmp_path, '[replace]\n"spread sheet" = "spreadsheet"\n')
    assert _processor(path).process("open the spread sheet now", _session()) == (
        "open the spreadsheet now"
    )


def test_a_phrase_matches_across_a_whitespace_run(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"spread sheet" = "spreadsheet"\n')
    assert _processor(path).process("the spread  sheet", _session()) == (
        "the spreadsheet"
    )


def test_a_key_does_not_match_inside_a_longer_word(tmp_path: Path) -> None:
    """B3: `breadshoe` matches `breadshoe.` and not `breadshoes`."""
    path = _write(tmp_path, '[replace]\n"breadshoe" = "spreadsheet"\n')
    processor = _processor(path)
    assert processor.process("breadshoes", _session()) == "breadshoes"
    assert processor.process("abreadshoe", _session()) == "abreadshoe"
    assert processor.process("the breadshoe.", _session()) == "the spreadsheet."


def test_the_longest_key_wins(tmp_path: Path) -> None:
    """B5, and the alternation's key order is what implements it — not a
    post-hoc comparison."""
    path = _write(
        tmp_path,
        '[replace]\n"spread" = "SPREAD"\n"spread sheet" = "spreadsheet"\n',
    )
    assert _processor(path).process("the spread sheet", _session()) == (
        "the spreadsheet"
    )


def test_a_shorter_key_does_not_refire_inside_the_match(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[replace]\n"sheet" = "SHEET"\n"spread sheet" = "spreadsheet"\n',
    )
    assert _processor(path).process("the spread sheet", _session()) == (
        "the spreadsheet"
    )


def test_replacements_do_not_cascade(tmp_path: Path) -> None:
    """B7. Cascading makes order significant, cycles possible, and the result
    unreadable from the file."""
    path = _write(tmp_path, '[replace]\n"a" = "b"\n"b" = "c"\n')
    assert _processor(path).process("a", _session()) == "b"


def test_replacement_is_literal(tmp_path: Path) -> None:
    """Dictionary objection O4 rejected B4's casing heuristic.

    §7.3's Phase 2a finding is that silent heuristic rewriting of the user's
    words is the hazard — and the `[replace]` table's whole selling point over
    `[boost]` is that it is deterministic. What the user writes on the
    right-hand side is what lands, at sentence-start or anywhere else.
    """
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    processor = _processor(path)
    assert processor.process("csp is the format", _session()) == "CSV is the format"
    assert processor.process("CSP is the format", _session()) == "CSV is the format"


def test_a_replacement_is_not_capitalised_at_a_sentence_start(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"widget" = "gizmo"\n')
    assert _processor(path).process("widget first.", _session()) == "gizmo first."


def test_an_empty_map_changes_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path, "[replace]\n")
    assert _processor(path).process("anything at all", _session()) == "anything at all"


def test_a_unicode_key_matches_as_one_token(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"café" = "cafe"\n')
    assert _processor(path).process("the café closed", _session()) == "the cafe closed"


def test_a_regex_metacharacter_in_a_key_is_literal(tmp_path: Path) -> None:
    """No regex (§5.5 non-goals). A user debugging a regex against their own
    speech is worse off than one adding three literal entries."""
    path = _write(tmp_path, '[replace]\n"c++" = "cpp"\n')
    processor = _processor(path)
    assert processor.process("i write c++ daily", _session()) == "i write cpp daily"
    assert processor.process("i write cxx daily", _session()) == "i write cxx daily"


# ---------------------------------------------------------------------------
# The trace (B10, dictionary objection O5)
# ---------------------------------------------------------------------------


def test_the_processor_reports_which_entries_fired(tmp_path: Path) -> None:
    """A rule firing wrongly presents as an ASR error, which is the one
    explanation that sends the user to the wrong fix."""
    path = _write(tmp_path, '[replace]\n"breadshoe" = "spreadsheet"\n"csp" = "CSV"\n')
    processor = _processor(path)
    assert isinstance(processor, TracedPostProcessor)

    _, fired = processor.process_traced("the breadshoe is csp", _session())
    assert set(fired) == {"replace:breadshoe", "replace:csp"}


def test_an_entry_that_did_not_fire_is_not_reported(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"breadshoe" = "spreadsheet"\n"csp" = "CSV"\n')
    _, fired = _processor(path).process_traced("the breadshoe", _session())
    assert fired == ("replace:breadshoe",)


def test_an_entry_firing_twice_is_reported_once(tmp_path: Path) -> None:
    """The trace answers "which entry touched my text", not "how many times"."""
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    _, fired = _processor(path).process_traced("csp and csp", _session())
    assert fired == ("replace:csp",)


def test_process_does_not_mutate_the_session(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    session = _session()
    before = (session.raw_transcript, session.final_text, session.error)
    _processor(path).process("csp", session)
    assert (session.raw_transcript, session.final_text, session.error) == before


# ---------------------------------------------------------------------------
# The reload (operator decision 2026-08-04, choice-story #5)
# ---------------------------------------------------------------------------


def test_an_edited_file_is_picked_up_without_a_restart(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader = VocabularyLoader(path)
    processor = VocabularyPostProcessor(PostprocessConfig(), loader)
    assert processor.process("csp", _session()) == "CSV"

    _write(tmp_path, '[replace]\n"csp" = "CSV"\n"breadshoe" = "spreadsheet"\n')
    loader.refresh()
    assert processor.process("breadshoe", _session()) == "spreadsheet"


def test_an_unchanged_file_is_not_recompiled(tmp_path: Path) -> None:
    """One `stat()` per dictation, not one parse and one `re.compile`. The
    compile is the cost `vocab_ms` exists to bound (objection O10)."""
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader = VocabularyLoader(path)
    first = loader.refresh()
    second = loader.refresh()
    assert first is second


def test_a_broken_reload_keeps_the_last_good_map(tmp_path: Path) -> None:
    """B8's "malformed is an error at load" is the *startup* contract. At reload
    the daemon is holding a transcript, and §5.3's degrade-rather-than-stall
    rule applies — refusing to dictate because a TOML file was half-saved is
    the wrong failure.
    """
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader = VocabularyLoader(path)
    processor = VocabularyPostProcessor(PostprocessConfig(), loader)
    assert processor.process("csp", _session()) == "CSV"

    _write(tmp_path, '[replace]\n"csp" = \n')
    loader.refresh()

    assert (
        processor.process("csp", _session()) == "CSV"
    ), "a half-saved file must not cost the user this dictation"
    assert loader.error is not None, "and it must not be silent either"


def test_a_repaired_file_clears_the_error(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"csp" = \n')
    loader = VocabularyLoader(path)
    loader.refresh()
    assert loader.error is not None

    _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader.refresh()
    assert loader.error is None
    assert loader.current().replacements == {"csp": "CSV"}


def test_a_file_that_appears_later_is_picked_up(tmp_path: Path) -> None:
    """The ordinary first-run case: the daemon starts, then the user writes
    their first entry."""
    path = tmp_path / "vocabulary.toml"
    loader = VocabularyLoader(path)
    processor = VocabularyPostProcessor(PostprocessConfig(), loader)
    assert processor.process("csp", _session()) == "csp"

    _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader.refresh()
    assert processor.process("csp", _session()) == "CSV"


def test_a_deleted_file_empties_the_map(tmp_path: Path) -> None:
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    loader = VocabularyLoader(path)
    processor = VocabularyPostProcessor(PostprocessConfig(), loader)
    assert processor.process("csp", _session()) == "CSV"

    path.unlink()
    loader.refresh()
    assert (
        processor.process("csp", _session()) == "csp"
    ), "a missing file is not an error, so it cannot leave stale rules firing"


# ---------------------------------------------------------------------------
# [boost] — parsed here, applied by the engine
# ---------------------------------------------------------------------------


def test_boost_terms_are_read(tmp_path: Path) -> None:
    path = _write(tmp_path, '[boost]\nterms = ["Airtable", "Firestore"]\n')
    assert load_vocabulary(path).boost_terms == ("Airtable", "Firestore")


def test_a_per_application_list_replaces_the_global_one(tmp_path: Path) -> None:
    """Not a union. Boosting is measured to DEGRADE unrelated speech (+3.2 and
    +5.2 WER on two of six samples), so a union makes the degradation
    unavoidable and the scoping pointless."""
    path = _write(
        tmp_path,
        '[boost]\nterms = ["Airtable"]\n\n'
        '[boost.apps]\n"com.apple.Terminal" = ["ripgrep", "kubectl"]\n',
    )
    vocabulary = load_vocabulary(path)
    assert vocabulary.terms_for("com.apple.Terminal") == ("ripgrep", "kubectl")
    assert vocabulary.terms_for("com.microsoft.VSCode") == ("Airtable",)
    assert vocabulary.terms_for(None) == ("Airtable",)


def test_the_global_list_is_empty_by_default(tmp_path: Path) -> None:
    """§5.6's measured trade: a global always-on prompt is a trade, not a win."""
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    assert load_vocabulary(path).terms_for("com.apple.Terminal") == ()


def test_too_many_boost_terms_are_truncated_with_a_warning(tmp_path: Path) -> None:
    """The prompt window is finite and silently drops overflow, which would make
    a truncated list look like a term that does not work."""
    terms = ", ".join(f'"term{n}"' for n in range(120))
    path = _write(tmp_path, f"[boost]\nterms = [{terms}]\n")
    vocabulary = load_vocabulary(path)
    assert len(vocabulary.boost_terms) == 100
    assert vocabulary.warnings and "100" in vocabulary.warnings[0]


def test_a_non_string_boost_term_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "[boost]\nterms = [1, 2]\n")
    with pytest.raises(ConfigError):
        load_vocabulary(path)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_the_registry_builds_it(tmp_path: Path) -> None:
    from amanuensis.postprocess.registry import build_chain

    chain = build_chain(
        PostprocessConfig(chain=("rules", "vocabulary")),
        vocabulary=VocabularyLoader(tmp_path / "vocabulary.toml"),
    )
    assert [processor.name for processor in chain] == ["rules", "vocabulary"]


def test_the_vocabulary_runs_after_the_rules(tmp_path: Path) -> None:
    """B2: the rules pass changes capitalisation and punctuation, and would
    otherwise rewrite the map's output."""
    from amanuensis.postprocess.registry import build_chain

    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n')
    chain = build_chain(
        PostprocessConfig(chain=("rules", "vocabulary")),
        vocabulary=VocabularyLoader(path),
    )
    session = _session()
    text = "the format is csp"
    for processor in chain:
        text = processor.process(text, session)
    assert text == "The format is CSV."


def test_an_empty_vocabulary_is_reported_as_such(tmp_path: Path) -> None:
    """The Phase 3 gate's minimum instrument (objection O4): a frozen *empty*
    dictionary satisfies a SHA-256 and measures nothing, so entry count is
    recorded rather than inferred from the digest."""
    assert Vocabulary().entry_count == 0
    path = _write(tmp_path, '[replace]\n"csp" = "CSV"\n"breadshoe" = "spreadsheet"\n')
    assert load_vocabulary(path).entry_count == 2
