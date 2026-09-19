"""Rules against patterns that are legal SQL but usually a mistake.

These carry no naming opinion at all, so they are the rules most likely to be
useful to a team that shares none of the plugin's other conventions. Each is
off until switched on with ``force_enable = True``.
"""

from __future__ import annotations

from sqlfluff.core.rules import BaseRule, LintResult, RuleContext

from sqlfluff_plugin_conventions.rules.base import ConventionsRule


class Rule_Conventions_A001(ConventionsRule, BaseRule):
    """SELECT * is forbidden.

    **Anti-pattern**

    .. code-block:: sql

        SELECT * FROM users;

    **Best practice**

    .. code-block:: sql

        SELECT id, email FROM users;

    A star binds to whatever columns the source has at run time, so adding a
    column upstream silently changes what a downstream table contains.
    ``t.*`` can be allowed separately with ``allow_qualified_star``.
    """

    name = "conventions.no_select_star"
    groups = ("all", "conventions", "antipatterns")
    config_keywords = ["force_enable", "allow_qualified_star"]
    force_enable: bool
    allow_qualified_star: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self.force_enable:
            return None
        results = []
        for star in self._analysis(context).select_stars:
            if star.qualified and self.allow_qualified_star:
                continue
            what = "t.*" if star.qualified else "SELECT *"
            results.append(
                LintResult(
                    anchor=star.segment,
                    description=(
                        f"{what} binds to whatever columns exist at run time; "
                        f"list the columns explicitly"
                    ),
                )
            )
        return results or None


class Rule_Conventions_A002(ConventionsRule, BaseRule):
    """DROP statements must use IF EXISTS to stay re-runnable.

    **Anti-pattern**

    .. code-block:: sql

        DROP TABLE users;

    **Best practice**

    .. code-block:: sql

        DROP TABLE IF EXISTS users;

    Without ``IF EXISTS`` a re-run fails on the first already-dropped object,
    which in a pipeline means a partial deploy.
    """

    name = "conventions.drop_requires_if_exists"
    groups = ("all", "conventions", "antipatterns")
    config_keywords = ["force_enable"]
    force_enable: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self.force_enable:
            return None
        results = []
        for kind, anchor in self._analysis(context).drops_without_if_exists:
            results.append(
                LintResult(
                    anchor=anchor,
                    description=(
                        f"DROP {kind.upper()} without IF EXISTS is not "
                        f"re-runnable; use DROP {kind.upper()} IF EXISTS"
                    ),
                )
            )
        return results or None


class Rule_Conventions_A003(ConventionsRule, BaseRule):
    """INSERT must name its target columns or use BY NAME.

    **Anti-pattern**

    .. code-block:: sql

        INSERT INTO users SELECT id, email FROM staging;

    **Best practice**

    .. code-block:: sql

        INSERT INTO users (id, email) SELECT id, email FROM staging;

    A bare ``INSERT INTO t SELECT ...`` binds by position. Add a column to
    either side and the data lands in the wrong column with no error, provided
    the types happen to line up.
    """

    name = "conventions.insert_requires_column_list"
    groups = ("all", "conventions", "antipatterns")
    config_keywords = ["force_enable"]
    force_enable: bool

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self.force_enable:
            return None
        results = []
        for anchor in self._analysis(context).inserts_without_column_list:
            results.append(
                LintResult(
                    anchor=anchor,
                    description=(
                        "INSERT binds columns by position; name the target "
                        "columns, or use INSERT INTO ... BY NAME"
                    ),
                )
            )
        return results or None
