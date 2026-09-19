# AGENTS

Guidance for AI coding agents working in `sqlfluff-plugin-conventions/`.

## What this is

A SQLFluff plugin of config-driven team conventions. It is the home for the
rule engine that used to live in `databricks_sql_parser` (then `dbsqlparse`)
and was removed when that project's parser was retired. That history is the
spec: `git show 66e915f^:src/dbsqlparse/rules/` and `tests/test_rules.py` in
the `databricks_sql_parser` repo. Do not revive the parser; this plugin is
what carries that work forward.

Org-specific rules belong in a plugin, not SQLFluff core — their CONTRIBUTING
says so. Nothing here is proposed upstream.

## Commands

```bash
.venv/bin/python -m pytest                       # 100+ tests, seconds
.venv/bin/ruff check src/ test/ scripts/
.venv/bin/ruff format src/ test/ scripts/
.venv/bin/sqlfluff rules | grep Conventions     # discovery smoke test
.venv/bin/python scripts/corpus_check.py --config examples/snake-case-team.sqlfluff
```

Setup: `python -m venv .venv && .venv/bin/pip install -e ../sqlfluff -e ".[dev]"`
(the editable SQLFluff fork, or any installed sqlfluff).

## The non-obvious constraints

**Every rule is inert by default.** SQLFluff runs all registered rules unless
deselected, so "off by default" is implemented as empty patterns and `False`
booleans in `plugin_default_config.cfg`, plus `force_enable = False` for the
rules that have no patterns. A plugin that invents naming opinions on first
run gets uninstalled. Two tests pin this: `test_default_config_keeps_every_rule_inert`
and the `inert_*` YAML cases.

**Type resolution never guesses.** `type_naming` fires only where the file
states a type: a `CREATE TABLE` column, a view column list (no type), or an
exact `CAST(x AS T) AS name` / `x::T AS name`. `CAST(a AS INT) + 1 AS x` is an
addition, not a cast, and is skipped. A guess is invisible in the diagnostic,
so a wrong report looks real. Do not widen this.

**Every rule is a whole-file rule.** Segment-tree knowledge lives only in
`semantics.py`; rules walk `analyse(context.segment)` once. When a dialect
moves a segment, exactly one file changes. `semantics.py` is also public API
for teams writing their own rules.

**The shared base is a plain mixin, not a `BaseRule` subclass.** SQLFluff's
rule metaclass rejects any class name that is not `Rule_<Plugin>_<CODE>`, so
`ConventionsRule` cannot derive from `BaseRule`. Rules inherit
`(ConventionsRule, BaseRule)`.

**Rules are imported lazily inside `get_rules()`.** SQLFluff must run
`get_configs_info()` before any rule class imports, or rule docstrings lose
their auto-generated configuration sections. `config_info.py` must stay
importable without importing rules.

**Config keys are globally namespaced.** `get_configs_info()` merges every
plugin's keys into one dict and duplicates lose silently. Never add a bare
`patterns` or `columns`; prefix distinctively (`type_patterns`,
`comment_min_length`, …). The names are part of users' configs.

**Structured values accept two spellings.** INI values are strings, so
mappings and lists take `KEY=value, KEY=value` or JSON. JSON is the escape
hatch for regexes containing `,` or `=`. Malformed input raises
`SQLFluffUserError` naming the offending entry — never parse silently.
`comment_forbidden_patterns` is matched case-insensitively so `TODO` is
caught; that is deliberate.

**Rule codes are `Conventions_<N|M|A><NN>`** (naming / metadata /
antipatterns). `N001` is the one this project actually exists for; the rest
are ports. Codes and config section names are compatibility surface.

## Testing

- YAML cases under `test/rules/test_cases/` via SQLFluff's own harness
  (`sqlfluff.utils.testing.rules`); one file per rule, run whole.
- `test/test_semantics.py` pins the model, especially its negatives:
  unknown types skipped, expression casts not treated as casts, comments not
  leaking out of nested types or view column lists.
- `test/test_plugin.py` covers registration, defaults, and config errors.
- `scripts/corpus_check.py` measures noise on real SQL and **always lints a
  deliberately broken control first**. A harness bug that loads no rules
  would otherwise report a clean sweep. Learn from the three times that
  happened in the sibling corpus project.

## Known gaps found here

`DROP MATERIALIZED VIEW` is unparsable in SQLFluff's `databricks` dialect as
of 4.3.0 (found 2026-09-18 by `test_semantics.py`). That is dialect work, not
plugin work — it belongs in the `databricks_sql_parser` gap queue and an
upstream PR, not a workaround here.

## Standing constraints

No employer SQL, ever — not as a test case, not as an example. Every example
in `examples/` is invented. The corpus repo stays private pending the
employment conversation; this plugin contains none of it.
