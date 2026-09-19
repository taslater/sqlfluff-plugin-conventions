"""Rules about the metadata a table is expected to carry.

These are the conventions most likely to be agreed across a whole
organisation, regardless of naming taste: documentation requirements, storage
format, and table properties.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.rules import BaseRule, LintResult, RuleContext

from sqlfluff_plugin_conventions.config import parse_list, parse_mapping
from sqlfluff_plugin_conventions.rules.base import ConventionsRule
from sqlfluff_plugin_conventions.scoring import (
    CommentContext,
    load_scorer,
    score_comment,
)


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


class Rule_Conventions_M004(ConventionsRule, BaseRule):
    """Comments must score at least a threshold from your own scorer.

    **Anti-pattern**

    With a scorer that penalises comments merely restating the column name:

    .. code-block:: sql

        CREATE TABLE users (
            id BIGINT COMMENT 'the id'
        );

    **Best practice**

    .. code-block:: sql

        CREATE TABLE users (
            id BIGINT COMMENT 'Surrogate key from the identity pool'
        );

    There are no built-in scorers. ``comment_score_function`` names one
    callable -- an installed scorer name, ``module:function``, or
    ``path/to/scorers.py:function`` -- which takes the comment (or a
    ``CommentContext``) and returns a number between 0 and 1. Existing
    comments are scored; requiring a comment at all is ``require_comment``.
    A scorer that cannot load, raises, or returns nonsense fails the run.
    """

    name = "conventions.comment_quality"
    groups = ("all", "conventions", "metadata")
    config_keywords = [
        "comment_score_function",
        "comment_score_threshold",
        "comment_score_columns",
        "comment_score_tables",
    ]
    comment_score_function: str
    comment_score_threshold: str
    comment_score_columns: bool
    comment_score_tables: bool

    def __init__(self, *args, **kwargs):
        """Load the scorer and parse the threshold, once per lint run."""
        super().__init__(*args, **kwargs)
        spec = str(self.comment_score_function or "").strip()
        self._scorer = load_scorer(spec) if spec else None
        self._threshold = self._parse_threshold(self.comment_score_threshold)

    @staticmethod
    def _parse_threshold(value: object) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            threshold = float(text)
        except ValueError as exc:
            raise SQLFluffUserError(
                f"comment_score_threshold must be a number between 0 and 1, "
                f"got {value!r}"
            ) from exc
        if not 0.0 <= threshold <= 1.0:
            raise SQLFluffUserError(
                f"comment_score_threshold must be between 0 and 1, got {threshold!r}"
            )
        return threshold

    @staticmethod
    def _normalise(comment: str) -> str:
        return " ".join(comment.split()).casefold()

    def _check(self, anchor, context: CommentContext) -> LintResult | None:
        assert self._scorer is not None and self._threshold is not None
        score = score_comment(context, self._scorer)
        if score.value >= self._threshold:
            return None
        description = (
            f"comment on {context.kind} {context.name!r} scores "
            f"{score.value:.2f}, below {self._threshold:.2f} "
            f"[{self._scorer.name}]"
        )
        if score.notes:
            description += f": {score.notes}"
        return LintResult(anchor=anchor, description=description)

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if self._scorer is None or self._threshold is None:
            return None
        if not (self.comment_score_columns or self.comment_score_tables):
            return None
        results = []
        for table in self._analysis(context).tables:
            comment_counts = Counter(
                self._normalise(column.comment)
                for column in table.columns
                if column.comment is not None
            )
            if self.comment_score_columns:
                for column in table.columns:
                    if column.comment is None:
                        continue
                    duplicates = comment_counts[self._normalise(column.comment)] - 1
                    result = self._check(
                        column.segment,
                        CommentContext(
                            comment=column.comment,
                            name=column.name,
                            kind="column",
                            data_type=column.data_type,
                            table_name=table.name,
                            duplicates=duplicates,
                        ),
                    )
                    if result is not None:
                        results.append(result)
            if self.comment_score_tables and table.comment is not None:
                result = self._check(
                    table.segment,
                    CommentContext(
                        comment=table.comment,
                        name=table.name,
                        kind="table",
                        table_name=table.name,
                    ),
                )
                if result is not None:
                    results.append(result)
        return results or None


class Rule_Conventions_M005(ConventionsRule, BaseRule):
    """Tables must declare a clustering or partitioning design.

    **Anti-pattern**

    With ``require_cluster_by`` set:

    .. code-block:: sql

        CREATE TABLE events (id BIGINT, occurred_at TIMESTAMP);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE events (id BIGINT, occurred_at TIMESTAMP)
        CLUSTER BY (occurred_at);

    Applied to tables and streaming tables; views and materialized views
    have no storage layout. ``CLUSTER BY AUTO`` can be allowed or rejected
    with ``allow_cluster_by_auto``.
    """

    name = "conventions.require_table_design"
    groups = ("all", "conventions", "metadata")
    config_keywords = [
        "require_cluster_by",
        "require_partition_by",
        "allow_cluster_by_auto",
    ]
    require_cluster_by: bool
    require_partition_by: bool
    allow_cluster_by_auto: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not (self.require_cluster_by or self.require_partition_by):
            return None
        results = []
        for table in self._analysis(context).tables:
            if table.kind not in ("table", "streaming_table"):
                continue
            if self.require_cluster_by:
                if not table.cluster_by:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} has no CLUSTER BY clause"
                            ),
                        )
                    )
                elif table.cluster_by_auto and not self.allow_cluster_by_auto:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} uses CLUSTER BY AUTO; "
                                f"an explicit key list is required"
                            ),
                        )
                    )
            if self.require_partition_by and not table.partitioned_by:
                results.append(
                    LintResult(
                        anchor=table.segment,
                        description=(
                            f"table {table.name!r} has no PARTITIONED BY clause"
                        ),
                    )
                )
        return results or None


class Rule_Conventions_M006(ConventionsRule, BaseRule):
    """Declared tables must carry PRIMARY KEY and/or NOT NULL constraints.

    **Anti-pattern**

    With ``require_primary_key`` and ``require_not_null`` set:

    .. code-block:: sql

        CREATE TABLE users (id BIGINT, email STRING);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE users (
            id BIGINT NOT NULL PRIMARY KEY,
            email STRING NOT NULL
        );

    Databricks primary keys are informational rather than enforced, but
    declaring them still documents the grain. Applied to tables and streaming
    tables with declared columns, never to views.
    """

    name = "conventions.require_constraints"
    groups = ("all", "conventions", "metadata")
    config_keywords = ["require_primary_key", "require_not_null"]
    require_primary_key: bool
    require_not_null: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not (self.require_primary_key or self.require_not_null):
            return None
        results = []
        for table in self._analysis(context).tables:
            if table.kind not in ("table", "streaming_table"):
                continue
            if not table.columns:
                continue
            if self.require_primary_key:
                has_key = table.primary_key or any(
                    column.primary_key for column in table.columns
                )
                if not has_key:
                    results.append(
                        LintResult(
                            anchor=table.segment,
                            description=(
                                f"table {table.name!r} declares no PRIMARY KEY"
                            ),
                        )
                    )
            if self.require_not_null:
                for column in table.columns:
                    if not column.not_null:
                        results.append(
                            LintResult(
                                anchor=column.segment,
                                description=(
                                    f"column {column.name!r} of table "
                                    f"{table.name!r} is nullable; add NOT NULL"
                                ),
                            )
                        )
        return results or None
