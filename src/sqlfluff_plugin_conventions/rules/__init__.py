"""All plugin rules, imported lazily by the root module's ``get_rules`` hook."""

from sqlfluff_plugin_conventions.rules.antipatterns import (
    Rule_Conventions_A001,
    Rule_Conventions_A002,
    Rule_Conventions_A003,
    Rule_Conventions_A004,
    Rule_Conventions_A005,
)
from sqlfluff_plugin_conventions.rules.metadata import (
    Rule_Conventions_M001,
    Rule_Conventions_M002,
    Rule_Conventions_M003,
    Rule_Conventions_M004,
    Rule_Conventions_M005,
    Rule_Conventions_M006,
)
from sqlfluff_plugin_conventions.rules.naming import (
    Rule_Conventions_N001,
    Rule_Conventions_N002,
    Rule_Conventions_N003,
    Rule_Conventions_N004,
    Rule_Conventions_N005,
    Rule_Conventions_N006,
)
from sqlfluff_plugin_conventions.rules.types import Rule_Conventions_T001

RULES = [
    Rule_Conventions_N001,
    Rule_Conventions_N002,
    Rule_Conventions_N003,
    Rule_Conventions_N004,
    Rule_Conventions_N005,
    Rule_Conventions_N006,
    Rule_Conventions_M001,
    Rule_Conventions_M002,
    Rule_Conventions_M003,
    Rule_Conventions_M004,
    Rule_Conventions_M005,
    Rule_Conventions_M006,
    Rule_Conventions_T001,
    Rule_Conventions_A001,
    Rule_Conventions_A002,
    Rule_Conventions_A003,
    Rule_Conventions_A004,
    Rule_Conventions_A005,
]

__all__ = ["RULES"]
