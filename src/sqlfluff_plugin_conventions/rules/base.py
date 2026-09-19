"""Shared plumbing for the convention rules.

A plain mixin rather than a ``BaseRule`` subclass: SQLFluff's rule metaclass
rejects any class whose name does not look like ``Rule_<Plugin>_<CODE>``, so
the shared behaviour cannot live on an intermediate rule base. Each rule
inherits ``(ConventionsRule, BaseRule)``.
"""

from __future__ import annotations

import re

from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.rules import RuleContext
from sqlfluff.core.rules.crawlers import BaseCrawler, RootOnlyCrawler

from sqlfluff_plugin_conventions.semantics import Analysis, analyse


class ConventionsRule:
    """Base behaviour for rules that analyse the whole file once.

    Every rule in this plugin is a whole-file rule: the semantic model is
    built once per file and each rule walks it. That keeps the segment-tree
    knowledge confined to ``semantics.py`` instead of spread across rules.
    """

    # Annotated with the same type as BaseRule's attribute because multiple
    # inheritance requires the definitions to agree; the narrower inferred
    # type would otherwise conflict.
    crawl_behaviour: BaseCrawler = RootOnlyCrawler()
    is_fix_compatible = False

    def _analysis(self, context: RuleContext) -> Analysis:
        return analyse(context.segment)

    @staticmethod
    def _compile(pattern: str, owner: str, flags: int = 0) -> re.Pattern[str]:
        """Compile a configured regex, attributing failures to the config."""
        try:
            return re.compile(pattern, flags)
        except re.error as exc:
            raise SQLFluffUserError(
                f"Invalid regex for {owner!r}: {pattern!r} ({exc})"
            ) from exc
