# sqlfluff-plugin-conventions

[![CI](https://github.com/taslater/sqlfluff-plugin-conventions/actions/workflows/ci.yml/badge.svg)](https://github.com/taslater/sqlfluff-plugin-conventions/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Config-driven team conventions for [SQLFluff](https://sqlfluff.com): enforce
the rules your team actually agreed on — column comments and comment quality,
type-aware column naming, object naming, `SELECT *` bans, and re-runnability
anti-patterns — in the same lint pass as everything else.

The plugin ships **no opinions of its own**. Every rule is inert until your
`.sqlfluff` config switches it on and supplies the patterns. What a column
should be called is a decision for your team, not for a linter.

## Install

Requires Python 3.10+ and SQLFluff 4.3.0 or newer.

```bash
pip install sqlfluff-plugin-conventions
```

Until the first PyPI release lands, install from git:

```bash
pip install git+https://github.com/taslater/sqlfluff-plugin-conventions
```

For development, see "Working on the plugin" below.

## Quickstart

Copy an example config to your project root and lint:

```bash
cp examples/snake-case-team.sqlfluff .sqlfluff
sqlfluff lint models/
```

Or point at a config without renaming it:

```bash
sqlfluff lint models/ --config examples/comments-quality.sqlfluff
```

`examples/demo.sql` is a deliberately non-compliant file to see the output:

```bash
sqlfluff lint examples/demo.sql --config examples/snake-case-team.sqlfluff
```

The examples are starting points, not recommendations:
`snake-case-team.sqlfluff` and `hungarian-team.sqlfluff` express **opposite**
naming conventions with the same rules, and there is a test asserting they
disagree.

On an existing codebase, expect a backlog the first time you enable a rule:
measured over 867 published Databricks SQL files, `no_select_star` and
`require_comment` each fire on roughly a third of files, while type-aware
naming fires on about 5% (it only sees declared types). The governance rules
are broader still: `require_qualified_names` fires on 273 files and
`require_constraints` on 94, while the predicate-free DML guards
(`delete_without_where`, `update_without_where`) fire on fewer than five
files each — worth enabling everywhere. Roll out rule by rule with
`sqlfluff lint --rules`, or start by enforcing them on new files only.
Run `scripts/corpus_check.py` against your own code to see what a config will
find before you commit to it.

## Rules

| Code | Name | What it checks | Key config |
| --- | --- | --- | --- |
| `Conventions_N001` | `conventions.type_naming` | Column name matches a regex chosen by its **declared type** | `type_patterns`, `type_origins` |
| `Conventions_N002` | `conventions.identifier_case` | snake / upper_snake / camel / pascal | `case_convention`, `case_columns`, `case_tables` |
| `Conventions_N003` | `conventions.identifier_length` | Maximum column-name length | `max_identifier_length` |
| `Conventions_N004` | `conventions.forbidden_name` | Names matching banned patterns, with a reason | `forbidden_patterns` |
| `Conventions_N005` | `conventions.object_name` | Per-kind naming for tables, views, streaming tables, materialized views | `object_patterns` |
| `Conventions_N006` | `conventions.require_qualified_names` | Created objects must be schema-qualified | `qualified_name_min_parts` |
| `Conventions_M001` | `conventions.require_comment` | Comments exist and are meaningful | `require_table_comments`, `require_column_comments`, `comment_min_length`, `comment_forbidden_patterns` |
| `Conventions_M002` | `conventions.require_table_properties` | Required `TBLPROPERTIES` keys and values | `required_property_keys`, `required_property_values` |
| `Conventions_M003` | `conventions.require_table_provider` | `USING` allowlist | `allowed_providers`, `require_explicit_provider` |
| `Conventions_M004` | `conventions.comment_quality` | Comment score from **your own function** clears a threshold | `comment_score_function`, `comment_score_threshold` |
| `Conventions_M005` | `conventions.require_table_design` | `CLUSTER BY` / `PARTITIONED BY` declared | `require_cluster_by`, `require_partition_by`, `allow_cluster_by_auto` |
| `Conventions_M006` | `conventions.require_constraints` | `PRIMARY KEY` / `NOT NULL` present | `require_primary_key`, `require_not_null` |
| `Conventions_T001` | `conventions.type_policy` | Forbidden types; explicit parameters | `forbidden_types`, `types_requiring_parameters` |
| `Conventions_A001` | `conventions.no_select_star` | `SELECT *` (optionally allowing `t.*`) | `force_enable`, `allow_qualified_star` |
| `Conventions_A002` | `conventions.drop_requires_if_exists` | `DROP … IF EXISTS` | `force_enable` |
| `Conventions_A003` | `conventions.insert_requires_column_list` | Named `INSERT` columns or `BY NAME` | `force_enable` |
| `Conventions_A004` | `conventions.delete_without_where` | Predicate-free `DELETE` | `force_enable` |
| `Conventions_A005` | `conventions.update_without_where` | Predicate-free `UPDATE` | `force_enable` |

Rules with no patterns of their own are off until `force_enable = True` in
their config section. The rest are inert until their patterns or booleans are
set. `sqlfluff rules` lists them all; run `sqlfluff rules --verbose` for full
configuration docs.

## sqruff compatibility

None, by design. sqruff has no plugin system and a fixed Rust rule set; its
configuration files are `.sqruff` / `sqruff.toml` / `pyproject.toml`, and it
does not read `.sqlfluff`. These rules cannot run there, and porting them into
sqruff would duplicate work its SQLFluff replay already does.

If you want sqruff's speed and these conventions, run both in the same CI:
sqruff for formatting and core style, SQLFluff for the convention rules.

```bash
sqruff lint .
sqlfluff lint . --rules Conventions_N001,Conventions_M001
```

### Type-aware naming, the unusual one

`conventions.type_naming` maps a canonical datatype to a regex the column name
must match:

```ini
[sqlfluff:rules:conventions.type_naming]
type_patterns = BOOLEAN=_ind$, DATE=_date$, TIMESTAMP=_timestamp$
type_origins = declaration, cast
```

Types are canonical, so one entry covers every spelling: `INT` and `INTEGER`
are the same, as are `TIMESTAMP_NTZ`/`TIMESTAMP`, `VARCHAR`/`CHAR`/`STRING`,
`DECIMAL`/`NUMERIC`/`DEC`/parameters. Patterns are matched with `search`, so
anchor with `^` and `$` as needed.

The rule resolves a type only where the file itself states one: a
`CREATE TABLE` column declaration, a view column list (which carries no type),
or an explicit `CAST(x AS T) AS name` / `x::T AS name`. A column like
`total AS revenue` has no locally knowable type and is **skipped** — the rule
never guesses, because a guess is invisible in the diagnostic and a wrong
report looks like a real finding.

### Two ways to write structured config

INI values are strings, so mappings and lists accept either a readable spelling
or JSON. The JSON spelling is the escape hatch when a regex contains `,` or
`=`:

```ini
[sqlfluff:rules:conventions.type_naming]
type_patterns = BOOLEAN=_ind$, DATE=_date$

[sqlfluff:rules:conventions.require_table_properties]
required_property_values = {"quality": "gold", "owner": "data"}

[sqlfluff:rules:conventions.require_comment]
comment_forbidden_patterns = ["^(todo|tbd|n/?a)$", "the .*"]
```

Malformed values raise a config error naming the offending text; nothing is
silently dropped.

## Comment scoring: bring your own function

`conventions.comment_quality` has no scorer of its own. You write a function
that takes a comment and returns a number between 0 and 1; the rule reports
every existing comment that scores below your threshold. Requiring a comment
at all is still `require_comment` — the two rules coexist, and enabling both
means a bad comment is reported by both.

```python
# tools/scorers.py
from sqlfluff_plugin_conventions.scoring import CommentContext, CommentScore


def decent(comment: str) -> float:
    """One-liner scorers just take the text."""
    return min(1.0, len(comment.split()) / 4)


def not_just_the_name(ctx: CommentContext) -> CommentScore:
    """Annotate the argument as CommentContext for name, datatype and more."""
    if ctx.name.lower() in ctx.comment.lower():
        return CommentScore(0.0, "comment only restates the column name")
    return CommentScore(1.0)
```

```ini
[sqlfluff]
rules = Conventions_M004

[sqlfluff:rules:conventions.comment_quality]
comment_score_function = tools/scorers.py:not_just_the_name
comment_score_threshold = 0.6
comment_score_columns = True
comment_score_tables = False
```

`comment_score_function` accepts three spellings:

* `path/to/scorers.py:function` — a plain script in your repo
* `package.module:function` — any installed module
* an entry-point name from the group `sqlfluff_conventions.comment_scorers`,
  for scorers shipped as packages

Exactly one scorer runs per rule instance. Compose your own: a function can
call other functions and return `CommentScore(value, notes)` to attach its
reasoning to the finding.

A scorer that cannot be loaded, raises, returns a non-number, or returns a
value outside 0–1 fails the lint run with the scorer's name in the message.
That is deliberate: a comment scorer that silently does nothing makes a clean
report a lie.

Scorers are code you install or name in config, which is the same trust model
as SQLFluff plugins themselves — running SQLFluff already executes arbitrary
code from installed packages. The file-path spelling means a `.sqlfluff` from
an untrusted source can name a script to import, so treat config as code. For
shared or hardened CI, set `SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS=1` to refuse
file-path scorers entirely. Nothing is fetched or `eval`'d from a string.

## Writing your own rules

`semantics.py` is a public API. It turns any SQLFluff parse tree into a small
model — `Table`, `Column`, `SelectStar` — so you can write team rules without
learning each dialect's segment names:

```python
from sqlfluff.core.rules import BaseRule
from sqlfluff.core.rules.crawlers import RootOnlyCrawler
from sqlfluff_plugin_conventions.semantics import analyse


class Rule_MyTeam_X001(BaseRule):
    """Every table must have at least one column."""

    name = "myteam.at_least_one_column"
    groups = ("all",)

    crawl_behaviour = RootOnlyCrawler()

    def _eval(self, context):
        results = []
        for table in analyse(context.segment).tables:
            if not table.columns:
                results.append(self._result(anchor=table.segment))  # your wording
        return results or None
```

Columns carry `name`, `canonical_type`, `raw_type`, `comment`, `origin`
(`declaration` / `cast` / `alias`), `primary_key`, `not_null` and the
`segment` to anchor a violation on. Tables carry `kind`, `provider`,
`properties`, `comment`, `primary_key`, `cluster_by`, `cluster_by_auto` and
`partitioned_by`. Comments declared later with `COMMENT ON` or `ALTER
TABLE … COMMENT` are folded in before rules run. The API is versioned with
the package: it changes only with a minor release.

## Working on the plugin

```bash
python -m venv .venv
.venv/bin/pip install -e ../sqlfluff -e ".[dev]"   # fork checkout, or any sqlfluff
.venv/bin/python -m pytest --cov=sqlfluff_plugin_conventions --cov-fail-under=96
.venv/bin/ruff check src/ test/ scripts/
.venv/bin/mypy
.venv/bin/sqlfluff rules | grep Conventions
```

CI runs the same checks plus a pinned `sqlfluff==4.3.0` floor job, a
`pip-audit` dependency audit, and SHA-pinned actions kept current by
Dependabot. Releases are published with PEP 740 provenance attestations.

The rule tests are YAML cases under `test/rules/test_cases/`, one file per
rule, using SQLFluff's own `sqlfluff.utils.testing` harness.

### Measuring against a corpus

`scripts/corpus_check.py` lints a directory of real SQL with one of the
example configs and counts findings per rule. It exists to answer "how noisy
is this rule on published SQL?", and it always lints a deliberately broken
control first so a harness that loads nothing cannot report success:

```bash
.venv/bin/python scripts/corpus_check.py --config examples/snake-case-team.sqlfluff
```

## Licence

MIT.
