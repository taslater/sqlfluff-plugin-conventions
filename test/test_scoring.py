"""Tests for the scorer loading and calling contract.

The failure modes matter more than the happy path: a scorer that cannot load,
raises, or returns nonsense must fail the lint run with its name attached. A
scorer that silently does nothing would make a clean report a lie.
"""

from __future__ import annotations

import math
import sys
import textwrap

import pytest
from sqlfluff.core.errors import SQLFluffUserError

from sqlfluff_plugin_conventions.example_scorers import (
    no_placeholder,
    specificity,
    word_count,
)
from sqlfluff_plugin_conventions.scoring import (
    NO_FILE_SCORERS_ENV,
    CommentContext,
    CommentScore,
    load_scorer,
    score_comment,
)

GOOD_SCORER = """
def good(comment):
    return 0.75
"""

CONTEXT_SCORER = """
from sqlfluff_plugin_conventions.scoring import CommentContext

def contextual(ctx: CommentContext):
    return 1.0 if ctx.name in ctx.comment else 0.25
"""

STRING_ANNOTATED_SCORER = """
def annotated(comment: str):
    return 0.5
"""

BAD_RETURN_SCORER = """
def bad(comment):
    return "excellent"
"""

RAISING_SCORER = """
def broken(comment):
    raise RuntimeError("boom")
"""

OUT_OF_RANGE_SCORER = """
def wild(comment):
    return 1.5
"""

NAN_SCORER = """
def nan(comment):
    return float("nan")
"""

WRONG_ARITY_SCORER = """
def two(comment, extra):
    return 1.0
"""


def load_from_source(tmp_path, source, name="good"):
    path = tmp_path / "scorers.py"
    path.write_text(textwrap.dedent(source))
    return load_scorer(f"{path}:{name}")


# --- loading from a file path -----------------------------------------------


def test_load_from_file_and_score(tmp_path):
    scorer = load_from_source(tmp_path, GOOD_SCORER)
    assert scorer.uses_context is False
    result = score_comment(CommentContext(comment="a decent comment"), scorer)
    assert result.value == 0.75


def test_load_from_file_that_does_not_exist(tmp_path):
    with pytest.raises(SQLFluffUserError, match="does not exist"):
        load_scorer(f"{tmp_path}/missing.py:good")


def test_load_from_file_with_bad_import(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("import not_a_real_module\n")
    with pytest.raises(SQLFluffUserError, match="raised while importing"):
        load_scorer(f"{path}:anything")


def test_missing_attribute(tmp_path):
    with pytest.raises(SQLFluffUserError, match="no attribute"):
        load_from_source(tmp_path, GOOD_SCORER, name="nope")


def test_non_callable_attribute(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("value = 3\n")
    with pytest.raises(SQLFluffUserError, match=r"not\s+callable"):
        load_scorer(f"{path}:value")


# --- loading from a module path ---------------------------------------------


def test_load_from_installed_module():
    scorer = load_scorer("sqlfluff_plugin_conventions.example_scorers:word_count")
    assert scorer.uses_context is False
    assert (
        score_comment(CommentContext(comment="a well written comment"), scorer).value
        == 1.0
    )


def test_load_from_module_that_does_not_exist():
    with pytest.raises(SQLFluffUserError, match="could not be imported"):
        load_scorer("definitely_not_a_module:score")


# --- loading from an entry point name ---------------------------------------


def test_load_from_entry_point(monkeypatch, tmp_path):
    module_name = "test_entry_point_scorers"
    (tmp_path / f"{module_name}.py").write_text("def score(comment):\n    return 0.9\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module_name, None)

    import sqlfluff_plugin_conventions.scoring as scoring_module

    monkeypatch.setattr(
        scoring_module,
        "_entry_points",
        lambda: {"team_score": f"{module_name}:score"},
    )
    scorer = load_scorer("team_score")
    assert scorer.name == "team_score"
    assert score_comment(CommentContext(comment="anything"), scorer).value == 0.9


# --- signature protocol ------------------------------------------------------


def test_context_annotation_selects_context_protocol(tmp_path):
    scorer = load_from_source(tmp_path, CONTEXT_SCORER, name="contextual")
    assert scorer.uses_context is True
    assert (
        score_comment(CommentContext(comment="the id", name="id"), scorer).value == 1.0
    )
    assert (
        score_comment(CommentContext(comment="unrelated", name="id"), scorer).value
        == 0.25
    )


def test_string_annotation_keeps_string_protocol(tmp_path):
    scorer = load_from_source(tmp_path, STRING_ANNOTATED_SCORER, name="annotated")
    assert scorer.uses_context is False


def test_wrong_arity_is_rejected(tmp_path):
    with pytest.raises(SQLFluffUserError, match="exactly one argument"):
        load_from_source(tmp_path, WRONG_ARITY_SCORER, name="two")


def test_unspecified_reference_is_rejected():
    with pytest.raises(SQLFluffUserError, match="neither an installed scorer"):
        load_scorer("not_a_reference")


# --- return-value validation -------------------------------------------------


def test_non_numeric_return_is_rejected(tmp_path):
    scorer = load_from_source(tmp_path, BAD_RETURN_SCORER, name="bad")
    with pytest.raises(SQLFluffUserError, match="expected a"):
        score_comment(CommentContext(comment="x"), scorer)


def test_out_of_range_return_is_rejected(tmp_path):
    scorer = load_from_source(tmp_path, OUT_OF_RANGE_SCORER, name="wild")
    with pytest.raises(SQLFluffUserError, match="between 0 and 1"):
        score_comment(CommentContext(comment="x"), scorer)


def test_nan_return_is_rejected(tmp_path):
    scorer = load_from_source(tmp_path, NAN_SCORER, name="nan")
    with pytest.raises(SQLFluffUserError, match="between 0 and 1"):
        score_comment(CommentContext(comment="x"), scorer)


def test_boolean_return_is_rejected(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def flag(comment):\n    return True\n")
    scorer = load_scorer(f"{path}:flag")
    with pytest.raises(SQLFluffUserError, match="expected a"):
        score_comment(CommentContext(comment="x"), scorer)


def test_raising_scorer_fails_with_its_name(tmp_path):
    scorer = load_from_source(tmp_path, RAISING_SCORER, name="broken")
    with pytest.raises(SQLFluffUserError, match=r"broken.*RuntimeError"):
        score_comment(CommentContext(comment="x"), scorer)


def test_integer_return_is_accepted(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def whole(comment):\n    return 1\n")
    scorer = load_scorer(f"{path}:whole")
    result = score_comment(CommentContext(comment="x"), scorer)
    assert result.value == 1.0
    assert isinstance(result.value, float)


def test_comment_score_notes_are_preserved(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text(
        "from sqlfluff_plugin_conventions.scoring import CommentScore\n"
        "def noted(comment):\n"
        "    return CommentScore(0.4, 'because')\n"
    )
    scorer = load_scorer(f"{path}:noted")
    result = score_comment(CommentContext(comment="x"), scorer)
    assert result == CommentScore(0.4, "because")
    assert math.isclose(result.value, 0.4)


# --- example scorers ---------------------------------------------------------


@pytest.mark.parametrize(
    "comment,expected",
    [
        ("", 0.0),
        ("one", 0.2),
        ("one two", 0.5),
        ("one two three", 0.75),
        ("one two three four", 1.0),
    ],
)
def test_example_word_count(comment, expected):
    assert word_count(comment) == expected


@pytest.mark.parametrize("comment", ["TODO", "tbd", "N/A", "none", "..."])
def test_example_no_placeholder_rejects_placeholders(comment):
    assert no_placeholder(comment) == 0.0


def test_example_no_placeholder_accepts_content():
    assert no_placeholder("Primary contact address") == 1.0


def test_example_specificity_restating_the_name_scores_zero():
    result = specificity(CommentContext(comment="the id", name="id"))
    assert result.value == 0.0


def test_example_specificity_duplicates_are_capped():
    result = specificity(
        CommentContext(
            comment="Surrogate key from the identity pool",
            name="id",
            duplicates=1,
        )
    )
    assert result.value <= 0.2


def test_example_specificity_needs_content_words():
    result = specificity(CommentContext(comment="the a", name="x"))
    assert result.value == 0.0
    assert "content" in result.notes


# --- loader robustness -------------------------------------------------------


def test_entry_point_with_malformed_value_is_rejected(monkeypatch):
    import sqlfluff_plugin_conventions.scoring as scoring_module

    monkeypatch.setattr(
        scoring_module, "_entry_points", lambda: {"bad": "no_colon_here"}
    )
    with pytest.raises(SQLFluffUserError, match="unexpected value"):
        load_scorer("bad")


def test_failed_file_import_is_not_left_in_sys_modules(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("raise RuntimeError('nope')\n")
    before = set(sys.modules)
    with pytest.raises(SQLFluffUserError, match="raised while importing"):
        load_scorer(f"{path}:anything")
    added = set(sys.modules) - before
    assert not any(name.startswith("_sqlfluff_conventions_scorer_") for name in added)


def test_repeated_loads_are_stable(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def score(comment):\n    return 0.5\n")
    first = load_scorer(f"{path}:score")
    second = load_scorer(f"{path}:score")
    assert score_comment(CommentContext(comment="x"), first).value == 0.5
    assert score_comment(CommentContext(comment="x"), second).value == 0.5


def test_file_scorers_can_be_refused(monkeypatch, tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def score(comment):\n    return 1.0\n")
    monkeypatch.setenv(NO_FILE_SCORERS_ENV, "1")
    with pytest.raises(SQLFluffUserError, match="is set"):
        load_scorer(f"{path}:score")
    scorer = load_scorer("sqlfluff_plugin_conventions.example_scorers:word_count")
    assert (
        score_comment(CommentContext(comment="a decent comment indeed"), scorer).value
        == 1.0
    )


def test_file_scorer_lockdown_is_off_by_default(monkeypatch, tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def score(comment):\n    return 1.0\n")
    monkeypatch.delenv(NO_FILE_SCORERS_ENV, raising=False)
    assert load_scorer(f"{path}:score").name.endswith(":score")


def test_star_args_scorer_is_rejected(tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def score(*args):\n    return 1.0\n")
    with pytest.raises(SQLFluffUserError, match=r"not \*args"):
        load_scorer(f"{path}:score")


def test_uninspectable_scorer_is_rejected(monkeypatch):
    import sqlfluff_plugin_conventions.scoring as scoring_module

    def broken_signature(function):
        raise ValueError("nope")

    monkeypatch.setattr(scoring_module.inspect, "signature", broken_signature)
    with pytest.raises(SQLFluffUserError, match="no inspectable signature"):
        scoring_module._uses_context(lambda comment: 1.0, "test")


def test_entry_points_are_read_from_metadata(monkeypatch):
    from types import SimpleNamespace

    import sqlfluff_plugin_conventions.scoring as scoring_module

    monkeypatch.setattr(
        scoring_module.importlib.metadata,
        "entry_points",
        lambda group=None: [
            SimpleNamespace(
                name="mine",
                value=("sqlfluff_plugin_conventions.example_scorers:word_count"),
            )
        ],
    )
    assert scoring_module._entry_points() == {
        "mine": "sqlfluff_plugin_conventions.example_scorers:word_count"
    }


def test_relative_file_path_resolves_from_cwd(monkeypatch, tmp_path):
    (tmp_path / "scorers.py").write_text("def score(comment):\n    return 0.5\n")
    monkeypatch.chdir(tmp_path)
    scorer = load_scorer("scorers.py:score")
    assert score_comment(CommentContext(comment="x"), scorer).value == 0.5


def test_empty_spec_is_rejected():
    with pytest.raises(SQLFluffUserError, match="empty"):
        load_scorer("   ")


def test_colon_with_empty_side_is_rejected():
    with pytest.raises(SQLFluffUserError, match="module:function"):
        load_scorer("module:")
    with pytest.raises(SQLFluffUserError, match="module:function"):
        load_scorer(":function")


def test_relative_module_spec_is_a_config_error():
    with pytest.raises(SQLFluffUserError, match="could not be imported"):
        load_scorer("..:score")


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_file_scorer_lockdown_truthy_values(monkeypatch, tmp_path, value):
    path = tmp_path / "scorers.py"
    path.write_text("def score(comment):\n    return 1.0\n")
    monkeypatch.setenv(NO_FILE_SCORERS_ENV, value)
    with pytest.raises(SQLFluffUserError, match="is set"):
        load_scorer(f"{path}:score")


def test_file_scorer_lockdown_falsy_value_is_off(monkeypatch, tmp_path):
    path = tmp_path / "scorers.py"
    path.write_text("def score(comment):\n    return 1.0\n")
    monkeypatch.setenv(NO_FILE_SCORERS_ENV, "0")
    assert load_scorer(f"{path}:score").name.endswith(":score")
