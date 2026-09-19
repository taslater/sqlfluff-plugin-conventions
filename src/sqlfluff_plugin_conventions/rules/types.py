"""Type policy: which datatypes a team permits, and how precisely.

A team that has been burned by floating-point money or by implicit DECIMAL
defaults can say so once, here, and have it checked everywhere a type is
written down.
"""

from __future__ import annotations

from sqlfluff.core.rules import BaseRule, LintResult, RuleContext

from sqlfluff_plugin_conventions.config import parse_list, parse_mapping
from sqlfluff_plugin_conventions.rules.base import ConventionsRule
from sqlfluff_plugin_conventions.semantics import canonical_type


class Rule_Conventions_T001(ConventionsRule, BaseRule):
    """Column types must respect an allow/forbid policy.

    **Anti-pattern**

    With ``forbidden_types = FLOAT=use DECIMAL for money``:

    .. code-block:: sql

        CREATE TABLE payments (amount FLOAT);

    **Best practice**

    .. code-block:: sql

        CREATE TABLE payments (amount DECIMAL(18, 2));

    ``forbidden_types`` maps a canonical datatype to the reason shown when it
    appears; ``types_requiring_parameters`` lists types that must be written
    with explicit parameters, e.g. ``DECIMAL`` so that bare ``DECIMAL`` cannot
    silently mean ``DECIMAL(10, 0)``. Types are canonical, so forbidding
    ``DECIMAL`` also catches ``NUMERIC`` and ``DEC``.
    """

    name = "conventions.type_policy"
    groups = ("all", "conventions", "types")
    config_keywords = ["forbidden_types", "types_requiring_parameters"]
    forbidden_types: str
    types_requiring_parameters: str

    def __init__(self, *args, **kwargs):
        """Parse the policy once, at rule construction."""
        super().__init__(*args, **kwargs)
        self._forbidden = {
            canonical_type(key) or key.upper(): reason
            for key, reason in parse_mapping(self.forbidden_types).items()
        }
        self._requiring = {
            canonical_type(target) or target.upper()
            for target in parse_list(self.types_requiring_parameters)
        }

    def _eval(self, context: RuleContext) -> list[LintResult] | None:
        if not self._forbidden and not self._requiring:
            return None
        results = []
        for column in self._analysis(context).columns:
            if not column.has_type:
                continue
            reason = self._forbidden.get(column.data_type)
            if reason is not None:
                description = f"{column.name!r} uses forbidden type {column.data_type}"
                if reason:
                    description += f" ({reason})"
                results.append(
                    LintResult(anchor=column.segment, description=description)
                )
            elif column.data_type in self._requiring and "(" not in (
                column.raw_type or ""
            ):
                results.append(
                    LintResult(
                        anchor=column.segment,
                        description=(
                            f"{column.name!r} uses bare {column.data_type}; "
                            f"explicit parameters are required, e.g. "
                            f"{column.data_type}(p, s)"
                        ),
                    )
                )
        return results or None
