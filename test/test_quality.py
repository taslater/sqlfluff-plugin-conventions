"""Quality, robustness and safety tests that are not rule behaviour.

These guard the properties that make the package safe to ship: every rule's
configuration is documented and defaulted, rules never autofix, unparsable
input cannot crash the semantic model, a broken scorer fails the CLI, and the
scorer loading surface respects its lockdown switch.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap

from sqlfluff.api import fix
from sqlfluff.core import FluffConfig, Linter
from sqlfluff.core.plugin.host import get_plugin_manager
from sqlfluff.core.rules.config_info import get_config_info

from sqlfluff_plugin_conventions.config_info import CONFIGS_INFO
from sqlfluff_plugin_conventions.semantics import analyse


def plugin_rules():
    bundles = get_plugin_manager().hook.get_rules()
    return [
        rule
        for bundle in bundles
        for rule in bundle
        if rule.code.startswith("Conventions_")
    ]


# --- configuration completeness ---------------------------------------------


def test_every_config_keyword_is_documented_and_defaulted():
    """A missing default or doc entry breaks at import or release time."""
    config = FluffConfig(overrides={"dialect": "databricks"})
    info = get_config_info()
    for rule in plugin_rules():
        section = config.get_section(("rules", rule.name))
        for keyword in rule.config_keywords:
            assert keyword in section, f"{rule.code} has no default for {keyword}"
            assert keyword in info, f"{rule.code} config {keyword} is undocumented"


def test_documented_config_entries_are_used_by_a_rule():
    used = {keyword for rule in plugin_rules() for keyword in rule.config_keywords}
    for key in CONFIGS_INFO:
        assert key in used, f"CONFIGS_INFO entry {key!r} belongs to no rule"


# --- metadata and docs ------------------------------------------------------


def test_rule_metadata_and_docstrings():
    rules = plugin_rules()
    codes = [rule.code for rule in rules]
    assert len(codes) == len(set(codes))
    for rule in rules:
        doc = rule.__doc__ or ""
        assert "**Anti-pattern**" in doc, rule.code
        assert "**Best practice**" in doc, rule.code
        assert doc.count(".. code-block::") >= 2, rule.code
        assert "all" in rule.groups, rule.code
        assert re.match(r"[a-z][a-z.\_]+", rule.name), rule.code
        assert rule.description, rule.code


# --- robustness against bad input -------------------------------------------


def test_unparsable_input_does_not_crash_the_model():
    parsed = Linter(dialect="databricks").parse_string(
        "SELECT FROM WHERE; CREATE TABLE ("
    )
    assert parsed.tree is not None
    model = analyse(parsed.tree)
    assert model.tables == []


def test_unparsable_input_does_not_crash_any_rule():
    codes = ",".join(rule.code for rule in plugin_rules())
    config = FluffConfig(overrides={"dialect": "databricks", "rules": codes})
    result = Linter(config=config).lint_string("SELECT FROM WHERE")
    assert result.violations is not None


def test_fix_never_rewrites_sql():
    """No rule is fix-compatible, so fix must be a strict no-op."""
    configs = {
        "core": {
            "dialect": "databricks",
            "rules": ",".join(rule.code for rule in plugin_rules()),
        },
        "rules": {
            "conventions.type_naming": {"type_patterns": "BOOLEAN=_ind$"},
            "conventions.identifier_case": {
                "case_columns": True,
                "case_tables": True,
            },
            "conventions.identifier_length": {"max_identifier_length": 5},
            "conventions.forbidden_name": {"forbidden_patterns": "^x=no"},
            "conventions.object_name": {"object_patterns": "view=^vw_"},
            "conventions.require_qualified_names": {"qualified_name_min_parts": 2},
            "conventions.require_comment": {
                "require_table_comments": True,
                "require_column_comments": True,
            },
            "conventions.require_table_properties": {
                "required_property_keys": "quality"
            },
            "conventions.require_table_provider": {
                "allowed_providers": "delta",
                "require_explicit_provider": True,
            },
            "conventions.comment_quality": {
                "comment_score_function": (
                    "sqlfluff_plugin_conventions.example_scorers:word_count"
                ),
                "comment_score_threshold": "0.9",
            },
            "conventions.require_table_design": {"require_cluster_by": True},
            "conventions.require_constraints": {
                "require_primary_key": True,
                "require_not_null": True,
            },
            "conventions.type_policy": {
                "forbidden_types": "FLOAT=no",
                "types_requiring_parameters": "DECIMAL",
            },
            "conventions.no_select_star": {"force_enable": True},
            "conventions.drop_requires_if_exists": {"force_enable": True},
            "conventions.insert_requires_column_list": {"force_enable": True},
            "conventions.delete_without_where": {"force_enable": True},
            "conventions.update_without_where": {"force_enable": True},
        },
    }
    sql = (
        "CREATE TABLE Orders (active BOOLEAN COMMENT 'x', x FLOAT) "
        "USING parquet;\n"
        "SELECT * FROM Orders;\n"
        "DROP TABLE Orders;\n"
        "DELETE FROM Orders;\n"
        "UPDATE Orders SET x = 1;\n"
        "INSERT INTO Orders SELECT 1;\n"
    )
    config = FluffConfig(configs=configs, overrides={"dialect": "databricks"})
    assert fix(sql, config=config) == sql


# --- scorer failures are loud ------------------------------------------------


def test_cli_fails_loudly_on_a_broken_scorer(tmp_path):
    (tmp_path / "scorers.py").write_text(
        "def broken(comment):\n    raise ValueError('boom')\n"
    )
    (tmp_path / ".sqlfluff").write_text(
        textwrap.dedent(
            """
            [sqlfluff]
            dialect = databricks
            rules = Conventions_M004

            [sqlfluff:rules:conventions.comment_quality]
            comment_score_function = scorers.py:broken
            comment_score_threshold = 0.5
            """
        )
    )
    (tmp_path / "test.sql").write_text(
        "CREATE TABLE t (id INT COMMENT 'some words here');\n"
    )
    process = subprocess.run(
        [sys.executable, "-m", "sqlfluff", "lint", "test.sql"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert process.returncode != 0
    output = process.stdout + process.stderr
    assert "Comment scorer" in output
    assert "broken" in output


MALFORMED_SQL = [
    "SELECT FROM WHERE",
    "CREATE TABLE",
    "CREATE TABLE t (",
    "CREATE TABLE t (a INT COMMENT)",
    "CREATE VIEW",
    "DROP",
    "INSERT INTO",
    "DELETE FROM",
    "UPDATE SET",
    "ALTER TABLE t ALTER COLUMN",
    "COMMENT ON",
    "CREATE TABLE t (a INT) TBLPROPERTIES",
    "CREATE TABLE t (a INT) TBLPROPERTIES ('k')",
    "GRANT SELECT ON",
    "WITH x AS (SELECT",
    "CREATE TABLE t (a INT) USING",
    "CREATE MATERIALIZED VIEW (",
]


def test_malformed_sql_never_crashes_a_rule():
    """Parse-recovery trees are where grammar invariants meet reality."""
    codes = ",".join(rule.code for rule in plugin_rules())
    config = FluffConfig(overrides={"dialect": "databricks", "rules": codes})
    linter = Linter(config=config)
    # Sanity: the battery is genuinely malformed.
    assert linter.lint_string("CREATE TABLE (").violations
    for sql in MALFORMED_SQL:
        result = linter.lint_string(sql)
        assert result.violations is not None
