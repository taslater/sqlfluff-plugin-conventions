# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-19

### Added

- `conventions.comment_quality` (M004): scores comments with a function the
  team supplies, loaded by entry-point name, `module:function`, or
  `path/to/scorers.py:function`, returning 0–1. No scorers are built in.
  `SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS` refuses file-path scorers for
  hardened CI.
- Tier 1 rules: `delete_without_where` (A004), `update_without_where` (A005),
  `require_qualified_names` (N006). `COMMENT ON ...` and
  `ALTER TABLE ... ALTER COLUMN ... COMMENT` now satisfy comment
  requirements.
- Tier 2 rules: `require_table_design` (M005), `require_constraints` (M006),
  `type_policy` (T001).
- `py.typed`, so the semantic-model and scoring APIs are typed for consumers.

### Changed

- Requires SQLFluff 4.3.0 or newer; the test suite runs against that floor
  and the latest release.
- Mypy runs in CI; the codebase is type-clean under SQLFluff's own option set.
- Line and branch coverage are held at 100% with no pragmas; unreachable
  code was deleted rather than excluded.
- Mutation testing (mutmut) runs weekly and on `src/` PRs with a ratcheting
  floor; survivors are printed for triage.
- CI adds SHA-pinned actions, a hash-pinned dev lockfile, a dependency audit,
  CodeQL, OpenSSF Scorecard, and an SBOM on release; releases are published
  with PEP 740 provenance attestations.
- Property-based, integration, security-veto and golden-description tests
  were added, including a malformed-SQL battery for every rule.
