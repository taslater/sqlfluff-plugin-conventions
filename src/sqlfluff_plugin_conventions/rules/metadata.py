"""Rules about the metadata a table is expected to carry.

These are the conventions most likely to be agreed across a whole
organisation, regardless of naming taste: documentation requirements, storage
format, and table properties.
"""

from __future__ import annotations

import re

from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.rules import BaseRule, LintResult, RuleContext

from sqlfluff_plugin_conventions.config import parse_list, parse_mapping
from sqlfluff_plugin_conventions.rules.base import ConventionsRule


class Rule_Conventions_M001(ConventionsRule, BaseRule):
    """Tables and columns must carry a meaningful COMMENT.

    **Anti-pattern**

    A declared column with no comment, or a placeholder comment:

    .. code-block:: sql

        CREATE TABLE users (id BIGINT, email STRING COMMENT 'TODO');

    **Best practice**

    .. code-block:: sql

        CREATE TABLE users (
            id BIGINT COMMENT 'Surrogate key from the identity pool',
            email STRING COMMENT 'Primary contact address'
        );

    A comment counts when it is present, strips to at least
    ``comment_min_length`` characters, and matches none of
    ``comment_forbidden_patterns``.
    """

    name = "conventions.require_comment"
    groups = ("all", "conventions", "metadata")
    config_keywords = [
        "require_table_comments",
        "require_column_comments",
        "comment_min_length",
        "comment_forbidden_patterns",
    ]
    require_table_comments: bool
    require_column_comments: bool
    comment_min_length: int
    comment_forbidden_patterns: str

    def __init__(self, *args, **kwargs):
        """Compile quality patterns once, at rule construction."""
        super().__init__(*args, **kwargs)
        if not isinstance(self.comment_min_length, int) or self.comment_min_length < 0:
            raise SQLFluffUserError(
                "comment_min_length must be a non-negative integer, got "
                f"{self.comment_min_length!r}"
            )
        self._forbidden = [
            self._compile(pattern, pattern, re.IGNORECASE)
            for pattern in parse_list(self.comment_forbidden_patterns)
        ]

    def _problem(self, comment: str | None) -> str | None:
        if comment is None:
            return "has no COMMENT"
        stripped = comment.strip()
        if len(stripped) < self.comment_min_length:
            return f"has a COMMENT shorter than {self.comment_min_length} characters"
        for pattern in self._forbidden:
            if pattern.search(stripped):
                return f"has a placeholder COMMENT matching /{pattern.pattern}/"
        return None

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not (self.require_table_comments or self.require_column_comments):
            return None
        results = []
        for table in self._analysis(context).tables:
            if self.require_table_comments:
                problem = self._problem(table.comment)
                if problem:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=f"table {table.name!r} {problem}",
                        )
                    )
            if self.require_column_comments:
                for column in table.columns:
                    problem = self._problem(column.comment)
                    if problem:
                        results.append(
                            LintResult(
                                anchor=column.segment,
                                description=(
                                    f"column {column.name!r} of table "
                                    f"{table.name!r} {problem}"
                                ),
                            )
                        )
        return results or None


class Rule_Conventions_M002(ConventionsRule, BaseRule):
    """Tables must set particular TBLPROPERTIES.

    **Anti-pattern**

    With ``quality=gold`` required:

    .. code-block:: sql

        CREATE TABLE orders (id BIGINT) TBLPROPERTIES ('owner' = 'data');

    **Best practice**

    .. code-block:: sql

        CREATE TABLE orders (id BIGINT)
        TBLPROPERTIES ('owner' = 'data', 'quality' = 'gold');
    """

    name = "conventions.require_table_properties"
    groups = ("all", "conventions", "metadata")
    config_keywords = ["required_property_keys", "required_property_values"]
    required_property_keys: str
    required_property_values: str

    def __init__(self, *args, **kwargs):
        """Parse the required keys and values once, at rule construction."""
        super().__init__(*args, **kwargs)
        self._keys = parse_list(self.required_property_keys)
        self._values = parse_mapping(self.required_property_values)

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._keys and not self._values:
            return None
        results = []
        for table in self._analysis(context).tables:
            for key in self._keys:
                if key not in table.properties:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} is missing required "
                                f"property {key!r}"
                            ),
                        )
                    )
            for key, expected in self._values.items():
                actual = table.properties.get(key)
                if actual is None:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} is missing required "
                                f"property {key!r}; expected {expected!r}"
                            ),
                        )
                    )
                elif actual != expected:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} has {key!r} = "
                                f"{actual!r}; expected {expected!r}"
                            ),
                        )
                    )
        return results or None


class Rule_Conventions_M003(ConventionsRule, BaseRule):
    """Tables must be created with an allowed USING provider.

    **Anti-pattern**

    With ``allowed_providers = delta``:

    .. code-block:: sql

        CREATE TABLE orders (id BIGINT) USING parquet;

    **Best practice**

    .. code-block:: sql

        CREATE TABLE orders (id BIGINT) USING delta;
    """

    name = "conventions.require_table_provider"
    groups = ("all", "conventions", "metadata")
    config_keywords = ["allowed_providers", "require_explicit_provider"]
    allowed_providers: str
    require_explicit_provider: bool

    def __init__(self, *args, **kwargs):
        """Parse the allowlist once, at rule construction."""
        super().__init__(*args, **kwargs)
        self._allowed = {
            provider.lower() for provider in parse_list(self.allowed_providers)
        }

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._allowed:
            return None
        results = []
        for table in self._analysis(context).tables:
            if table.kind in ("view", "materialized_view"):
                continue
            if table.provider is None:
                if self.require_explicit_provider:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} has no USING clause; "
                                f"expected one of: "
                                f"{', '.join(sorted(self._allowed))}"
                            ),
                        )
                    )
                continue
            if table.provider not in self._allowed:
                results.append(
                    LintResult(
                        anchor=table.segment,
                        description=(
                            f"table {table.name!r} uses provider "
                            f"{table.provider!r}; allowed: "
                            f"{', '.join(sorted(self._allowed))}"
                        ),
                    )
                )
        return results or None
