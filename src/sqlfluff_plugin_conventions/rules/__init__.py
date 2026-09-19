"""All plugin rules, imported lazily by the root module's ``get_rules`` hook."""

from sqlfluff_plugin_conventions.rules.antipatterns import (
    Rule_Conventions_A001,
    Rule_Conventions_A002,
    Rule_Conventions_A003,
)
from sqlfluff_plugin_conventions.rules.metadata import (
    Rule_Conventions_M001,
    Rule_Conventions_M002,
    Rule_Conventions_M003,
)
from sqlfluff_plugin_conventions.rules.naming import (
    Rule_Conventions_N001,
    Rule_Conventions_N002,
    Rule_Conventions_N003,
    Rule_Conventions_N004,
    Rule_Conventions_N005,
)

RULES = [
    Rule_Conventions_N001,
    Rule_Conventions_N002,
    Rule_Conventions_N003,
    Rule_Conventions_N004,
    Rule_Conventions_N005,
    Rule_Conventions_M001,
    Rule_Conventions_M002,
    Rule_Conventions_M003,
    Rule_Conventions_A001,
    Rule_Conventions_A002,
    Rule_Conventions_A003,
]

__all__ = ["RULES"]
