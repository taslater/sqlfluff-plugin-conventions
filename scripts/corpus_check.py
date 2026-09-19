#!/usr/bin/env python3
"""Lint the Databricks SQL corpus with this plugin and summarise the findings.

This is a false-positive check, not a gate. The corpus is published SQL,
written without any of these conventions, so findings are expected. What
matters is the shape: a rule that fires on half the corpus needs a narrower
default or a louder warning in its docs, and a rule that fires on nothing is
either perfectly targeted or not wired up at all.

A deliberately violating control is linted alongside the corpus. If the
control does not produce its expected rules, the run fails: a harness or a
plugin that has quietly stopped loading would otherwise report a clean sweep.

Usage:
    python scripts/corpus_check.py --config examples/snake-case-team.sqlfluff
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

from sqlfluff.core import FluffConfig, Linter
from sqlfluff.core.errors import SQLLintError

CONTROL_SQL = "CREATE TABLE t (active BOOLEAN); SELECT * FROM t;"
CONTROL_EXPECTED = {"Conventions_N001", "Conventions_A001"}

DEFAULT_CORPUS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "databricks-sql-corpus"
    / "corpus"
    / "cache"
)


def control_config() -> FluffConfig:
    """A minimal config with two rules guaranteed to fire on CONTROL_SQL."""
    return FluffConfig(
        configs={
            "core": {
                "dialect": "databricks",
                "rules": "Conventions_N001, Conventions_A001",
            },
            "rules": {
                "conventions.type_naming": {"type_patterns": "BOOLEAN=_ind$"},
                "conventions.no_select_star": {"force_enable": True},
            },
        }
    )


def run_control() -> bool:
    result = Linter(config=control_config()).lint_string(CONTROL_SQL)
    codes = {
        violation.rule_code()
        for violation in result.violations
        if isinstance(violation, SQLLintError)
    }
    missing = CONTROL_EXPECTED - codes
    if missing:
        print(
            f"CONTROL FAILED: expected {sorted(CONTROL_EXPECTED)}, "
            f"got {sorted(codes)} -- the harness or plugin is not loading",
            file=sys.stderr,
        )
        return False
    print(f"control: deliberately broken SQL flagged by {', '.join(sorted(codes))}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=pathlib.Path,
        default=DEFAULT_CORPUS,
        help="directory of .sql files to lint (default: the corpus cache)",
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        required=True,
        help="a .sqlfluff file to lint with, e.g. one of the examples",
    )
    parser.add_argument("--dialect", default="databricks")
    parser.add_argument(
        "--limit", type=int, default=None, help="only lint the first N files"
    )
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"corpus directory not found: {args.corpus}", file=sys.stderr)
        return 2

    if not run_control():
        return 2

    files = sorted(args.corpus.rglob("*.sql"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"no .sql files under {args.corpus}", file=sys.stderr)
        return 2

    config = FluffConfig.from_root(
        extra_config_path=str(args.config),
        overrides={"dialect": args.dialect},
    )
    linter = Linter(config=config)

    findings: collections.Counter[str] = collections.Counter()
    files_by_rule: dict[str, set[str]] = collections.defaultdict(set)
    parse_failures = 0
    files_with_findings = 0

    for index, path in enumerate(files, start=1):
        text = path.read_text(encoding="utf-8", errors="replace")
        result = linter.lint_string(text, fname=str(path))
        lint_errors = [
            violation
            for violation in result.violations
            if isinstance(violation, SQLLintError)
        ]
        if any(
            not isinstance(violation, SQLLintError) for violation in result.violations
        ):
            parse_failures += 1
        if lint_errors:
            files_with_findings += 1
        for violation in lint_errors:
            findings[violation.rule_code()] += 1
            files_by_rule[violation.rule_code()].add(str(path.relative_to(args.corpus)))
        if index % 100 == 0:
            print(f"  ... {index}/{len(files)} files", file=sys.stderr)

    print(
        f"\nlinted {len(files)} files: {files_with_findings} with convention "
        f"findings, {parse_failures} with parse/templater errors"
    )
    print(f"{'rule':<24}{'findings':>9}{'files':>7}")
    for code, count in findings.most_common():
        print(f"{code:<24}{count:>9}{len(files_by_rule[code]):>7}")
    if not findings:
        print("(no findings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
