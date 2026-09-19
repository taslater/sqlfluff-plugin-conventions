"""Property-based tests for the contracts contributors are most likely to break.

Example-based tests encode the cases we thought of. These encode the
invariants: whatever a contributor adds, the parser surface must never drop
input silently or raise anything other than a config error, scores must pass
through or be rejected, and arbitrary token soup must never crash a rule.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlfluff.core import FluffConfig, Linter
from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.parser import BaseSegment
from sqlfluff.core.plugin.host import get_plugin_manager

from sqlfluff_plugin_conventions.config import parse_list, parse_mapping
from sqlfluff_plugin_conventions.scoring import (
    CommentContext,
    LoadedScorer,
    load_scorer,
    score_comment,
)
from sqlfluff_plugin_conventions.semantics import (
    Table,
    _match_table,
    _unquote,
    canonical_type,
    normalise_type,
)

SAFE_TEXT = st.text(
    min_size=1, alphabet=st.characters(blacklist_characters="=,{}[]\n\r")
).filter(lambda value: value == value.strip() and value != "")

SETTINGS = settings(max_examples=100, deadline=None)


def _scorer_returning(value):
    return LoadedScorer(
        name="property", function=lambda comment: value, uses_context=False
    )


# --- type handling -----------------------------------------------------------


@given(st.text())
@SETTINGS
def test_canonical_type_is_total_idempotent_and_upper(value):
    result = canonical_type(value)
    if result is None:
        assert normalise_type(value) is None
        return
    assert result == result.upper()
    assert canonical_type(result) == result


@given(st.text())
@SETTINGS
def test_unquote_is_idempotent(value):
    once = _unquote(value)
    assert _unquote(once) == once


# --- config parsers ----------------------------------------------------------


@given(st.lists(SAFE_TEXT))
@SETTINGS
def test_parse_list_round_trips(token_list):
    assert parse_list(", ".join(token_list)) == token_list


@given(st.dictionaries(SAFE_TEXT, SAFE_TEXT))
@SETTINGS
def test_parse_mapping_readable_round_trips(mapping):
    text = ", ".join(f"{key}={value}" for key, value in mapping.items())
    assert parse_mapping(text) == mapping


@given(st.dictionaries(SAFE_TEXT, SAFE_TEXT))
@SETTINGS
def test_parse_mapping_json_round_trips(mapping):
    assert parse_mapping(json.dumps(mapping)) == mapping


@given(st.text())
@SETTINGS
def test_config_parsers_raise_only_config_errors(value):
    for parser in (parse_list, parse_mapping):
        try:
            parser(value)
        except SQLFluffUserError:
            pass


@given(st.text(max_size=40))
@SETTINGS
def test_load_scorer_raises_only_config_errors(spec):
    try:
        load_scorer(spec)
    except SQLFluffUserError:
        pass


# --- scorer contract ---------------------------------------------------------


@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
@SETTINGS
def test_valid_scores_pass_through_unchanged(value):
    result = score_comment(CommentContext(comment="whatever"), _scorer_returning(value))
    assert result.value == value


@given(st.floats(allow_nan=False).filter(lambda value: value < 0 or value > 1))
@SETTINGS
def test_out_of_range_scores_are_always_rejected(value):
    with pytest.raises(SQLFluffUserError):
        score_comment(CommentContext(comment="whatever"), _scorer_returning(value))


# --- table matching ----------------------------------------------------------

_DUMMY_SEGMENT = cast(BaseSegment, object())


def _table(name: str) -> Table:
    return Table(name=name, segment=_DUMMY_SEGMENT)


@given(st.lists(SAFE_TEXT, min_size=1, max_size=4), st.text(max_size=20))
@SETTINGS
def test_match_table_never_returns_a_mismatched_or_ambiguous_table(names, target):
    tables = [_table(name) for name in names]
    result = _match_table(tables, target)
    if result is None:
        return
    wanted = target.strip().casefold()
    assert result.name.casefold() == wanted or (
        result.name.casefold().rsplit(".", 1)[-1] == wanted.rsplit(".", 1)[-1]
    )
    if any(table.name.casefold() == wanted for table in tables):
        return  # an exact match is always a valid choice
    suffix_matches = [
        table
        for table in tables
        if table.name.casefold().rsplit(".", 1)[-1] == wanted.rsplit(".", 1)[-1]
    ]
    assert len(suffix_matches) == 1


# --- an arbitrary token soup must never crash a rule -------------------------

_TOKENS = [
    "CREATE",
    "TABLE",
    "t",
    "a",
    "INT",
    "COMMENT",
    ",",
    "(",
    ")",
    "SELECT",
    "*",
    "FROM",
    ";",
    "'x'",
    "ALTER",
    "COLUMN",
    "DROP",
    "VIEW",
    "IF",
    "EXISTS",
    "USING",
    "delta",
    "TBLPROPERTIES",
    "ON",
    "ADD",
    "=",
]

_RULES = ",".join(
    rule.code
    for bundle in get_plugin_manager().hook.get_rules()
    for rule in bundle
    if rule.code.startswith("Conventions_")
)
_SOUP_CONFIG = FluffConfig(overrides={"dialect": "databricks", "rules": _RULES})
_SOUP_LINTER = Linter(config=_SOUP_CONFIG)


@given(st.lists(st.sampled_from(_TOKENS), min_size=1, max_size=12))
@settings(max_examples=60, deadline=None)
def test_arbitrary_token_soup_never_crashes_a_rule(tokens):
    _SOUP_LINTER.lint_string(" ".join(tokens))
