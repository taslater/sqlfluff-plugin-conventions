"""Config-driven team conventions, delivered as SQLFluff rules.

The plugin ships no opinions of its own: every rule is inert until a
project's ``.sqlfluff`` config turns it on. See the README for the rule list
and the config for each.

Hooks live here and nowhere else. Rules are imported inside ``get_rules``
because SQLFluff must be able to run ``get_configs_info()`` before any
``BaseRule`` subclass is imported; importing them at module level would
break the configuration documentation attached to each rule.
"""

from typing import Any

from sqlfluff.core.config import load_config_resource
from sqlfluff.core.plugin import hookimpl
from sqlfluff.core.rules import BaseRule, ConfigInfo


@hookimpl
def get_rules() -> list[type[BaseRule]]:
    """Return the plugin's rule classes."""
    from sqlfluff_plugin_conventions.rules import RULES

    return RULES


@hookimpl
def load_default_config() -> dict[str, Any]:
    """Load the plugin's default configuration: every rule inert."""
    return load_config_resource(
        package="sqlfluff_plugin_conventions",
        file_name="plugin_default_config.cfg",
    )


@hookimpl
def get_configs_info() -> dict[str, dict[str, ConfigInfo]]:
    """Return validation and documentation for the plugin's config keys."""
    from sqlfluff_plugin_conventions.config_info import CONFIGS_INFO

    return CONFIGS_INFO
