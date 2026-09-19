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

from sqlfluff_plugin_conventions.scoring import (
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
    with pytest.raises(SQLFluffUserError, match="not\\s+callable"):
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
    with pytest.raises(SQLFluffUserError, match="broken.*RuntimeError"):
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
