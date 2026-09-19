"""Naming rules: type-aware patterns, identifier style, object conventions.

None of these rules carries an opinion of its own. ``type_naming`` and
``object_name`` do nothing until a config supplies patterns; the others are
off until switched on. What a column or a view should be called is a decision
for the team adopting the plugin, not for the plugin.
"""

from __future__ import annotations

import re

from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.rules import BaseRule, LintResult, RuleContext

from sqlfluff_plugin_conventions.config import parse_list, parse_mapping
from sqlfluff_plugin_conventions.rules.base import ConventionsRule
from sqlfluff_plugin_conventions.semantics import canonical_type

CASE_PATTERNS = {
    "snake": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "upper_snake": re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"),
    "camel": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "pascal": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}

OBJECT_KINDS = ("table", "view", "streaming_table", "materialized_view")


class Rule_Conventions_N001(ConventionsRule, BaseRule):
    """Column names must match a pattern chosen by their declared type.

    **Anti-pattern**

    With ``BOOLEAN=_ind$`` configured, a boolean column without the suffix:

    .. code-block:: sql

        CREATE TABLE users (active BOOLEAN);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE users (active_ind BOOLEAN);

    Types are read only where the file states them: a ``CREATE TABLE``
    column declaration, a view column list, or an explicit
    ``CAST(x AS T) AS name``. A column like ``total AS revenue`` has no
    locally knowable type and is skipped -- the rule never guesses.
    """

    name = "conventions.type_naming"
    groups = ("all", "conventions", "naming")
    config_keywords = ["type_patterns", "type_origins"]
    type_patterns: str
    type_origins: str

    def __init__(self, *args, **kwargs):
        """Compile configured type patterns once, at rule construction."""
        super().__init__(*args, **kwargs)
        self._patterns = {
            canonical_type(key) or key.upper(): self._compile(pattern, key)
            for key, pattern in parse_mapping(self.type_patterns).items()
        }
        self._origins = set(parse_list(self.type_origins))
        unknown = self._origins - {"declaration", "cast", "alias"}
        if unknown:
            raise SQLFluffUserError(
                f"Unknown type_origins value(s) {sorted(unknown)}; valid "
                f"values are declaration, cast, alias"
            )

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._patterns:
            return None
        results = []
        for column in self._analysis(context).columns:
            if column.origin not in self._origins or not column.has_type:
                continue
            pattern = self._patterns.get(column.data_type)
            if pattern is None:
                continue
            if not pattern.search(column.name):
                results.append(
                    LintResult(
                        anchor=column.segment,
                        description=(
                            f"{column.data_type} column {column.name!r} does "
                            f"not match the required pattern "
                            f"/{pattern.pattern}/"
                        ),
                    )
                )
        return results or None


class Rule_Conventions_N002(ConventionsRule, BaseRule):
    """Identifiers must follow one casing convention.

    **Anti-pattern**

    With ``case_convention = snake``:

    .. code-block:: sql

        SELECT orderId FROM SalesOrders;

    **Best practice**

    .. code-block:: sql

        SELECT order_id FROM sales_orders;
    """

    name = "conventions.identifier_case"
    groups = ("all", "conventions", "naming")
    config_keywords = ["case_convention", "case_columns", "case_tables"]
    case_convention: str
    case_columns: bool
    case_tables: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not (self.case_columns or self.case_tables):
            return None
        pattern = CASE_PATTERNS[self.case_convention]
        style = self.case_convention
        analysis = self._analysis(context)
        results = []

        if self.case_columns:
            for column in analysis.columns:
                if not pattern.match(column.name):
                    results.append(
                        LintResult(
                            anchor=column.segment,
                            description=(f"column {column.name!r} is not {style} case"),
                        )
                    )

        if self.case_tables:
            for table in analysis.tables:
                for part in table.name.split("."):
                    if part and not pattern.match(part):
                        results.append(
                            LintResult(
                                anchor=table.segment,
                                description=(
                                    f"table name part {part!r} is not {style} case"
                                ),
                            )
                        )
                        break

        return results or None


class Rule_Conventions_N003(ConventionsRule, BaseRule):
    """Column names must not exceed a maximum length.

    **Anti-pattern**

    With ``max_identifier_length = 16``:

    .. code-block:: sql

        CREATE TABLE t (a_column_name_far_too_long INT);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE t (short_name INT);
    """

    name = "conventions.identifier_length"
    groups = ("all", "conventions", "naming")
    config_keywords = ["max_identifier_length"]
    max_identifier_length: int

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        limit = self.max_identifier_length
        if not isinstance(limit, int) or limit <= 0:
            return None
        results = []
        for column in self._analysis(context).columns:
            if len(column.name) > limit:
                results.append(
                    LintResult(
                        anchor=column.segment,
                        description=(
                            f"column {column.name!r} is {len(column.name)} "
                            f"characters, over the limit of {limit}"
                        ),
                    )
                )
        return results or None


class Rule_Conventions_N004(ConventionsRule, BaseRule):
    """Identifiers must not match any forbidden pattern.

    **Anti-pattern**

    With ``_tmp$=use _scratch instead`` configured:

    .. code-block:: sql

        CREATE TABLE orders_tmp (id INT);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE orders_scratch (id INT);
    """

    name = "conventions.forbidden_name"
    groups = ("all", "conventions", "naming")
    config_keywords = [
        "forbidden_patterns",
        "forbidden_columns",
        "forbidden_tables",
    ]
    forbidden_patterns: str
    forbidden_columns: bool
    forbidden_tables: bool

    def __init__(self, *args, **kwargs):
        """Compile configured patterns once, at rule construction."""
        super().__init__(*args, **kwargs)
        self._forbidden = [
            (self._compile(pattern, pattern), reason)
            for pattern, reason in parse_mapping(
                self.forbidden_patterns, regex_keys=True
            ).items()
        ]

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._forbidden:
            return None
        analysis = self._analysis(context)
        targets = []
        if self.forbidden_columns:
            targets += [
                (column.name, column.segment, "column") for column in analysis.columns
            ]
        if self.forbidden_tables:
            targets += [
                (table.name, table.segment, "table") for table in analysis.tables
            ]

        results = []
        for name, anchor, kind in targets:
            for pattern, reason in self._forbidden:
                if pattern.search(name):
                    description = (
                        f"{kind} {name!r} matches forbidden pattern /{pattern.pattern}/"
                    )
                    if reason:
                        description += f" ({reason})"
                    results.append(LintResult(anchor=anchor, description=description))
                    break
        return results or None


class Rule_Conventions_N005(ConventionsRule, BaseRule):
    """Tables and views must be named according to their kind.

    **Anti-pattern**

    With ``view=^vw_`` configured:

    .. code-block:: sql

        CREATE VIEW active_users AS SELECT 1;

    **Best practice**

    .. code-block:: sql

        CREATE VIEW vw_active_users AS SELECT 1;

    Patterns are matched against the object's own name -- the last part of a
    qualified name -- because the catalog and schema are governed separately.
    """

    name = "conventions.object_name"
    groups = ("all", "conventions", "naming")
    config_keywords = ["object_patterns"]
    object_patterns: str

    def __init__(self, *args, **kwargs):
        """Compile configured patterns once, at rule construction."""
        super().__init__(*args, **kwargs)
        patterns = parse_mapping(self.object_patterns)
        unknown = set(patterns) - set(OBJECT_KINDS)
        if unknown:
            raise SQLFluffUserError(
                f"Unknown object kind(s) {sorted(unknown)}; valid kinds are "
                f"{', '.join(OBJECT_KINDS)}"
            )
        self._patterns = {
            kind: self._compile(pattern, kind) for kind, pattern in patterns.items()
        }

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._patterns:
            return None
        results = []
        for table in self._analysis(context).tables:
            pattern = self._patterns.get(table.kind)
            if pattern is None:
                continue
            name = table.name.rsplit(".", 1)[-1]
            if not name or pattern.search(name):
                continue
            results.append(
                LintResult(
                    anchor=table.segment,
                    description=(
                        f"{table.kind.replace('_', ' ')} {table.name!r} does "
                        f"not match the required pattern /{pattern.pattern}/"
                    ),
                )
            )
        return results or None


class Rule_Conventions_N006(ConventionsRule, BaseRule):
    """Created objects must be qualified with their schema.

    **Anti-pattern**

    .. code-block:: sql

        CREATE TABLE orders (id BIGINT);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE sales.orders (id BIGINT);

    An unqualified name lands in whatever the session's default schema
    happens to be, which differs between a notebook, a job and a migration.
    ``qualified_name_min_parts`` is the number of dotted parts required, so
    ``3`` demands ``catalog.schema.object`` where the platform supports it.
    """

    name = "conventions.require_qualified_names"
    groups = ("all", "conventions", "naming")
    config_keywords = ["qualified_name_min_parts"]
    qualified_name_min_parts: int

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        minimum = self.qualified_name_min_parts
        if not isinstance(minimum, int) or minimum <= 0:
            return None
        results = []
        for table in self._analysis(context).tables:
            if not table.name:
                continue
            parts = table.name.split(".")
            if len(parts) < minimum:
                results.append(
                    LintResult(
                        anchor=table.segment,
                        description=(
                            f"{table.kind.replace('_', ' ')} {table.name!r} "
                            f"has {len(parts)} qualified part(s); "
                            f"{minimum} required"
                        ),
                    )
                )
        return results or None
