"""Tests for the semantic model the rules are written against.

The behaviour pinned hardest is what the model does NOT do: it never guesses
a column's type, and it keeps declarations, casts and plain aliases distinct.
"""

from __future__ import annotations

import pytest
from sqlfluff.core import Linter

from sqlfluff_plugin_conventions.semantics import (
    analyse,
    canonical_type,
    normalise_type,
)


def model(sql: str):
    """Parse ``sql`` as Databricks and return the semantic model."""
    parsed = Linter(dialect="databricks").parse_string(sql)
    assert not parsed.violations, parsed.violations
    result = analyse(parsed.tree)
    assert result is not None
    return result


# --- type canonicalisation --------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("BOOLEAN", "BOOLEAN"),
        ("boolean", "BOOLEAN"),
        ("INT", "INTEGER"),
        ("INTEGER", "INTEGER"),
        ("DECIMAL(10,2)", "DECIMAL"),
        ("NUMERIC(5,1)", "DECIMAL"),
        ("VARCHAR(20)", "STRING"),
        ("TIMESTAMP_NTZ", "TIMESTAMP"),
        ("BIGINT", "BIGINT"),
        ("ARRAY<INT>", "ARRAY"),
        ("STRUCT<a: INT>", "STRUCT"),
        (None, None),
        ("", None),
    ],
)
def test_canonical_type(raw, expected):
    assert canonical_type(raw) == expected


def test_normalise_type_keeps_parameters_separate():
    assert normalise_type("DECIMAL(10,2)") == "DECIMAL"


# --- declarations -----------------------------------------------------------


def test_declaration_column_is_typed_and_commented():
    analysis = model(
        "CREATE TABLE t (active BOOLEAN COMMENT 'whether active', dt DATE)"
    )
    assert len(analysis.tables) == 1
    table = analysis.tables[0]
    assert table.name == "t"
    assert table.kind == "table"
    assert [c.name for c in table.columns] == ["active", "dt"]
    active, dt = table.columns
    assert active.data_type == "BOOLEAN"
    assert active.raw_type == "BOOLEAN"
    assert active.comment == "whether active"
    assert active.origin == "declaration"
    assert dt.data_type == "DATE"
    assert dt.comment is None


def test_quoted_identifiers_are_unquoted_for_naming_rules():
    analysis = model("CREATE TABLE `t` (`Active Ind` BOOLEAN)")
    assert analysis.tables[0].name == "t"
    assert analysis.columns[0].name == "Active Ind"


def test_type_parameters_do_not_leak_into_canonical_type():
    analysis = model("CREATE TABLE t (price DECIMAL(10,2))")
    assert analysis.columns[0].data_type == "DECIMAL"
    assert analysis.columns[0].raw_type == "DECIMAL(10,2)"


# --- casts vs aliases -------------------------------------------------------


def test_cast_alias_has_a_type_and_cast_origin():
    analysis = model("SELECT CAST(x AS BOOLEAN) AS active FROM t")
    typed = [c for c in analysis.columns if c.name == "active"]
    assert len(typed) == 1
    assert typed[0].origin == "cast"
    assert typed[0].data_type == "BOOLEAN"


def test_shorthand_cast_is_recognised():
    analysis = model("SELECT x::INT AS num FROM t")
    assert analysis.columns[0].origin == "cast"
    assert analysis.columns[0].data_type == "INTEGER"


def test_plain_alias_has_no_type():
    """The model must never guess. `total AS revenue` is unknowable."""
    analysis = model("SELECT total AS revenue FROM t")
    assert analysis.columns[0].origin == "alias"
    assert analysis.columns[0].data_type is None
    assert not analysis.columns[0].has_type


def test_cast_in_a_larger_expression_is_not_a_cast():
    analysis = model("SELECT CAST(a AS INT) + 1 AS total FROM t")
    assert analysis.columns[0].origin == "alias"
    assert analysis.columns[0].data_type is None


# --- tables -----------------------------------------------------------------


def test_streaming_and_live_tables_are_one_kind():
    analysis = model(
        "CREATE STREAMING TABLE st AS SELECT 1;"
        "CREATE OR REFRESH STREAMING LIVE TABLE slt AS SELECT 1"
    )
    assert [t.kind for t in analysis.tables] == [
        "streaming_table",
        "streaming_table",
    ]


def test_materialized_view_kind():
    analysis = model("CREATE MATERIALIZED VIEW mv AS SELECT 1")
    assert analysis.tables[0].kind == "materialized_view"
    assert analysis.tables[0].name == "mv"


def test_view_columns_and_comments():
    analysis = model(
        "CREATE VIEW v (a COMMENT 'column a', b) COMMENT 'view doc' AS SELECT 1"
    )
    table = analysis.tables[0]
    assert table.kind == "view"
    assert table.comment == "view doc"
    assert [(c.name, c.comment) for c in table.columns] == [
        ("a", "column a"),
        ("b", None),
    ]
    assert table.columns[0].origin == "declaration"
    assert not table.columns[0].has_type


def test_table_metadata_and_properties():
    analysis = model(
        "CREATE TABLE t (id INT) USING delta "
        "COMMENT 'orders' TBLPROPERTIES ('quality' = 'gold', 'owner' = 'data')"
    )
    table = analysis.tables[0]
    assert table.provider == "delta"
    assert table.comment == "orders"
    assert table.properties == {"quality": "gold", "owner": "data"}


def test_view_comment_does_not_leak_from_column_list():
    analysis = model(
        "CREATE VIEW v (a COMMENT 'column a') COMMENT 'view doc' AS SELECT 1"
    )
    assert analysis.tables[0].comment == "view doc"


def test_nested_type_comments_are_not_column_comments():
    analysis = model(
        "CREATE TABLE t (s STRUCT<field: INT COMMENT 'inner'> COMMENT 'outer')"
    )
    table = analysis.tables[0]
    assert table.columns[0].comment == "outer"
    assert table.comment is None


# --- anti-pattern detection -------------------------------------------------


def test_select_stars_qualified_and_bare():
    analysis = model("SELECT *, t.* FROM t")
    assert [(s.qualified) for s in analysis.select_stars] == [False, True]


def test_drops_without_if_exists():
    # NOTE: DROP MATERIALIZED VIEW is currently unparsable in SQLFluff's
    # databricks dialect, so it cannot appear here yet.
    analysis = model("DROP TABLE t; DROP TABLE IF EXISTS u; DROP VIEW v;")
    assert [kind for kind, _ in analysis.drops_without_if_exists] == [
        "table",
        "view",
    ]


def test_inserts_without_column_list():
    analysis = model(
        "INSERT INTO t SELECT 1;"
        "INSERT INTO t (a) SELECT 1;"
        "INSERT INTO t BY NAME SELECT 1;"
        "INSERT INTO t VALUES (1)"
    )
    assert len(analysis.inserts_without_column_list) == 2
