"""Integration tests: the plugin as users actually run it.

These exercise the CLI, configuration discovery, rule selection, noqa
suppression, JSON output and parallel runs — and pin exact violation
positions and descriptions, because anchors are the thing most easily broken
by a well-meaning refactor.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

from sqlfluff.core import FluffConfig, Linter

REPRESENTATIVE_SQL = (
    "CREATE TABLE orders (\n"
    "    active BOOLEAN,\n"
    "    dt DATE COMMENT 'the date'\n"
    ");\n"
    "SELECT * FROM orders;\n"
)

REPRESENTATIVE_CONFIG = """
[sqlfluff]
dialect = databricks
rules = Conventions_N001,Conventions_M001,Conventions_A001

[sqlfluff:rules:conventions.type_naming]
type_patterns = BOOLEAN=_ind$

[sqlfluff:rules:conventions.require_comment]
require_column_comments = True

[sqlfluff:rules:conventions.no_select_star]
force_enable = True
"""


def _write_project(tmp_path, sql=REPRESENTATIVE_SQL, config=REPRESENTATIVE_CONFIG):
    (tmp_path / ".sqlfluff").write_text(textwrap.dedent(config))
    (tmp_path / "test.sql").write_text(sql)


def _cli(*args, cwd, env=None):
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if key != "SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS"
    }
    if env:
        clean_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "sqlfluff", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=clean_env,
    )


def test_violations_have_exact_codes_positions_and_descriptions():
    config = FluffConfig.from_string(REPRESENTATIVE_CONFIG)
    result = Linter(config=config).lint_string(REPRESENTATIVE_SQL)
    observed = [
        (
            violation.rule_code(),
            violation.line_no,
            violation.line_pos,
            violation.description,
        )
        for violation in result.violations
    ]
    assert observed == [
        (
            "Conventions_M001",
            2,
            5,
            "column 'active' of table 'orders' has no COMMENT",
        ),
        (
            "Conventions_N001",
            2,
            5,
            "BOOLEAN column 'active' does not match the required pattern /_ind$/",
        ),
        (
            "Conventions_A001",
            5,
            8,
            "SELECT * binds to whatever columns exist at run time; "
            "list the columns explicitly",
        ),
    ]


def _violations(stdout: str):
    """Violation tuples in order, without the timing statistics."""
    return [
        (
            violation["code"],
            violation["start_line_no"],
            violation["start_line_pos"],
            violation["description"],
        )
        for report in json.loads(stdout)
        for violation in report["violations"]
    ]


def test_output_is_deterministic_across_hash_seeds(tmp_path):
    _write_project(tmp_path)
    first = _cli(
        "lint",
        "test.sql",
        "--format",
        "json",
        cwd=tmp_path,
        env={"PYTHONHASHSEED": "0"},
    )
    second = _cli(
        "lint",
        "test.sql",
        "--format",
        "json",
        cwd=tmp_path,
        env={"PYTHONHASHSEED": "12345"},
    )
    assert first.returncode != 0
    assert second.returncode != 0
    assert _violations(first.stdout) == _violations(second.stdout)


def test_config_is_discovered_from_a_parent_directory(tmp_path):
    sub = tmp_path / "models"
    sub.mkdir()
    (tmp_path / ".sqlfluff").write_text(textwrap.dedent(REPRESENTATIVE_CONFIG))
    (sub / "model.sql").write_text("CREATE TABLE orders (active BOOLEAN);\n")
    process = _cli("lint", "models/model.sql", "--format", "json", cwd=tmp_path)
    assert process.returncode != 0
    codes = {
        violation["code"]
        for file_report in json.loads(process.stdout)
        for violation in file_report["violations"]
    }
    assert "Conventions_N001" in codes


def test_rules_flag_selects_a_subset(tmp_path):
    _write_project(tmp_path)
    process = _cli(
        "lint",
        "test.sql",
        "--rules",
        "Conventions_N001",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert process.returncode != 0
    codes = {
        violation["code"]
        for file_report in json.loads(process.stdout)
        for violation in file_report["violations"]
    }
    assert codes == {"Conventions_N001"}


def test_noqa_suppresses_a_plugin_rule(tmp_path):
    sql = "CREATE TABLE orders (active BOOLEAN);  -- noqa: Conventions_N001\n"
    _write_project(tmp_path, sql=sql)
    process = _cli(
        "lint",
        "test.sql",
        "--rules",
        "Conventions_N001",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert process.returncode == 0


def test_json_output_carries_rule_metadata(tmp_path):
    _write_project(tmp_path)
    process = _cli("lint", "test.sql", "--format", "json", cwd=tmp_path)
    violations = json.loads(process.stdout)[0]["violations"]
    violation = next(item for item in violations if item["code"] == "Conventions_N001")
    assert violation["name"] == "conventions.type_naming"
    assert violation["start_line_no"] == 2
    assert violation["start_line_pos"] == 5
    assert "does not match" in violation["description"]


def test_parallel_lint_over_multiple_files(tmp_path):
    _write_project(tmp_path)
    (tmp_path / "second.sql").write_text("CREATE TABLE users (active BOOLEAN);\n")
    process = _cli(
        "lint",
        "test.sql",
        "second.sql",
        "--processes",
        "2",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert process.returncode != 0
    files = {file_report["filepath"] for file_report in json.loads(process.stdout)}
    assert len(files) == 2
    for file_report in json.loads(process.stdout):
        assert any(
            violation["code"] == "Conventions_N001"
            for violation in file_report["violations"]
        )
