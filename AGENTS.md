# AGENTS

Guidance for AI coding agents working in `sqlfluff-plugin-conventions/`.

## What this is

A SQLFluff plugin of config-driven team conventions. It is the home for the
rule engine that used to live in the corpus repo (local dir
`databricks_sql_parser/` at the time, since renamed `databricks-sql-corpus/`;
package `dbsqlparse`) and was removed when that project's parser was retired.
That history is the spec: `git show 66e915f^:src/dbsqlparse/rules/` and
`tests/test_rules.py` in `taslater/databricks-sql-corpus`. Do not revive the
parser; this plugin is what carries that work forward.

Org-specific rules belong in a plugin, not SQLFluff core — their CONTRIBUTING
says so. Nothing here is proposed upstream.

## Commands

```bash
.venv/bin/python -m pytest                       # tests, seconds
.venv/bin/python -m pytest --cov=sqlfluff_plugin_conventions --cov-fail-under=100
.venv/bin/ruff check src/ test/ scripts/
.venv/bin/ruff format src/ test/ scripts/
.venv/bin/mypy                                   # config in pyproject
.venv/bin/mutmut run                             # then scripts/mutation_score.py
.venv/bin/sqlfluff rules | grep Conventions     # discovery smoke test
.venv/bin/python scripts/corpus_check.py --config examples/snake-case-team.sqlfluff
```

Setup: `python -m venv .venv && .venv/bin/pip install -e ../sqlfluff -e ".[dev]"`
(the editable SQLFluff fork, or any installed sqlfluff). The claimed floor is
**SQLFluff 4.3.0**, verified by a pinned CI job; earlier 4.x parse several
databricks constructs differently, so do not lower it without running the
whole suite against the candidate.

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

**Rule codes are `Conventions_<N|M|T|A><NN>`** (naming / metadata / types /
antipatterns). `N001` is the one this project actually exists for; the rest
are ports. Codes and config section names are compatibility surface.

**Comment scoring takes exactly one team function and ships none.** M004
loads a scorer named in config from three surfaces (entry-point name,
`module:function`, `path.py:function`), calls it per comment, and fails the
run loudly if it cannot load, raises, or returns anything outside 0–1. Do
not add built-in scorers or presets — the point is that the team's judgment
lives in the team's code. `example_scorers.py` is unregistered and exists
only for docs and tests. The file-path spelling means config names code to
import; the trust model is the same as plugins themselves, and the README
says so.

**Comment assignment is resolved before rules run.** `semantics.py` applies
`COMMENT ON ...` and `ALTER TABLE ... ALTER COLUMN ... COMMENT` statements to
the tables created in the same file, last one wins. Cross-file correlation is
deliberately not attempted; a target not created in the file is ignored.

## Testing

- YAML cases under `test/rules/test_cases/` via SQLFluff's own harness
  (`sqlfluff.utils.testing.rules`); one file per rule, run whole.
- `test/test_semantics.py` pins the model, especially its negatives:
  unknown types skipped, expression casts not treated as casts, comments not
  leaking out of nested types or view column lists.
- `test/test_scoring.py` pins the scorer contract: every loader surface,
  both protocols, and every way a scorer can fail (missing, non-callable,
  wrong arity, raising, non-numeric, NaN, out of range), plus the
  `SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS` lockdown.
- `test/test_plugin.py` covers registration, defaults, and config errors.
- `test/test_quality.py` guards shipping properties: every config keyword is
  documented and defaulted, docstrings conform, unparsable input cannot crash
  the model, `fix` is a no-op, and the CLI exits non-zero on a broken scorer.
  It also runs a malformed-SQL battery against every rule.
- `test/test_integration.py` drives the CLI: exact violation positions and
  descriptions, determinism across hash seeds, parent-directory config
  discovery, `--rules`, `noqa`, JSON output, and a two-process parallel run.
- `test/test_golden.py` is deliberately brittle: all 18 rules fire on one
  file and every diagnostic word is pinned. When it fails, the question is
  "did the wording change on purpose?", then update it.
- `test/test_properties.py` encodes invariants with Hypothesis: parsers never
  drop input or raise anything but `SQLFluffUserError`, scores pass through
  or are rejected, table matching never guesses, token soup never crashes.
- `test/test_security.py` vetoes sockets and subprocesses around scorer
  loading, evaluation, and a full lint.
- `scripts/corpus_check.py` measures noise on real SQL and **always lints a
  deliberately broken control first**. A harness bug that loads no rules
  would otherwise report a clean sweep. Learn from the three times that
  happened in the sibling corpus project.

**Coverage is 100% line and branch with zero pragmas.** Unreachable branches
get deleted, not covered; where a branch exists only because the parse tree
guarantees a shape, use an `assert` with the guarantee named, and prove the
no-crash property with the malformed-SQL battery and the Hypothesis soup
test. Never add a pragma to hit the gate.

**Mypy, ruff and mutation are gates.** The package ships `py.typed`; keep
`mypy` clean under the config in `pyproject.toml`. Mutation testing runs
weekly and on `src/` PRs with a floor of 75 that only ratchets upward — if
it fails, kill the survivors with tests or document them as equivalent,
never lower the floor. Scores fluctuate a few points between runs because
the Hypothesis property tests explore different examples (observed band
roughly 78–83% in September 2026); the floor sits below the band on purpose.
Target: 90%.

**Actions are SHA-pinned** with version comments, Dependabot updates them,
and releases carry PEP 740 attestations and an SPDX SBOM. The dev toolchain
is hash-pinned in `requirements-dev.txt`; regenerate with
`pip-compile --allow-unsafe --generate-hashes --extra dev --output-file requirements-dev.txt pyproject.toml`.

## Releasing

1. Bump `version` in `pyproject.toml` and date the section in `CHANGELOG.md`
   (move `[Unreleased]` items under it).
2. Commit and push; wait for CI, CodeQL and the floor job to pass.
3. Tag and push the tag: `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
   The `publish.yml` workflow builds, generates an SPDX SBOM and publishes to
   PyPI via OIDC trusted publishing (no tokens) with PEP 740 attestations.
4. Verify: `pip install sqlfluff-plugin-conventions` in a clean venv, check
   the PyPI page shows provenance, then `gh release create vX.Y.Z
   --generate-notes` for the tag page.

The PyPI trusted publisher is a one-time account setting (project name,
owner, repo, workflow `publish.yml`, environment `pypi`); nothing in the
repo needs a secret.

## Known gaps found here

`DROP MATERIALIZED VIEW` is unparsable in SQLFluff's `databricks` dialect as
of 4.3.0 (found 2026-09-18 by `test_semantics.py`). That is dialect work, not
plugin work — it belongs in the `databricks-sql-corpus` gap queue
(`docs/gaps.md`) and an upstream PR, not a workaround here.

## Standing constraints

No employer SQL, ever — not as a test case, not as an example. Every example
in `examples/` is invented. The corpus repo stays private pending the
employment conversation; this plugin contains none of it.
