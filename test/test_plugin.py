"""Plugin-level tests: registration, default configuration, validation."""

from __future__ import annotations

import pytest
from sqlfluff.core.config import FluffConfig
from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.plugin.host import get_plugin_manager
from sqlfluff.core.rules import get_ruleset

EXPECTED_CODES = {
    "Conventions_N001",
    "Conventions_N002",
    "Conventions_N003",
    "Conventions_N004",
    "Conventions_N005",
    "Conventions_M001",
    "Conventions_M002",
    "Conventions_M003",
    "Conventions_A001",
    "Conventions_A002",
    "Conventions_A003",
}


def plugin_rules():
    bundles = get_plugin_manager().hook.get_rules()
    return [rule for bundle in bundles for rule in bundle]


def test_all_rules_are_registered():
    codes = {rule.code for rule in plugin_rules()}
    assert EXPECTED_CODES <= codes


def test_every_rule_has_a_namespaced_name_and_all_group():
    for rule in plugin_rules():
        if rule.code in EXPECTED_CODES:
            assert rule.name.startswith("conventions.")
            assert "all" in rule.groups


def test_rule_codes_match_their_class_names():
    for rule in plugin_rules():
        if rule.code in EXPECTED_CODES:
            assert rule.code.startswith("Conventions_")


def test_default_config_keeps_every_rule_inert():
    """The plugin ships no opinions: defaults alone must not flag anything."""
    config = FluffConfig(overrides={"dialect": "databricks"})
    assert config.get_section(("rules", "conventions.type_naming")) == {
        "type_patterns": "",
        "type_origins": "declaration, cast",
    }
    assert config.get_section(("rules", "conventions.no_select_star")) == {
        "force_enable": False,
        "allow_qualified_star": False,
    }
    assert (
        config.get_section(("rules", "conventions.require_comment"))[
            "require_table_comments"
        ]
        is False
    )


def _build_rulepack(rule_configs: dict):
    configs = {
        "core": {"dialect": "databricks"},
        "rules": {"conventions.type_naming": rule_configs},
    }
    return get_ruleset().get_rulepack(
        FluffConfig(configs=configs, overrides={"dialect": "databricks"})
    )


def test_invalid_regex_is_a_config_error():
    with pytest.raises(SQLFluffUserError, match="Invalid regex"):
        _build_rulepack({"type_patterns": "BOOLEAN=("})


def test_unknown_type_origin_is_a_config_error():
    with pytest.raises(SQLFluffUserError, match="type_origins"):
        _build_rulepack({"type_patterns": "BOOLEAN=_ind$", "type_origins": "guess"})


def test_unknown_object_kind_is_a_config_error():
    configs = {
        "core": {"dialect": "databricks"},
        "rules": {
            "conventions.object_name": {"object_patterns": "materialised_view=^mv_"}
        },
    }
    with pytest.raises(SQLFluffUserError, match="object kind"):
        get_ruleset().get_rulepack(
            FluffConfig(configs=configs, overrides={"dialect": "databricks"})
        )


def test_invalid_case_convention_is_a_config_error():
    configs = {
        "core": {"dialect": "databricks"},
        "rules": {"conventions.identifier_case": {"case_convention": "kebab"}},
    }
    with pytest.raises(SQLFluffUserError):
        get_ruleset().get_rulepack(
            FluffConfig(configs=configs, overrides={"dialect": "databricks"})
        )


def test_negative_comment_min_length_is_a_config_error():
    configs = {
        "core": {"dialect": "databricks"},
        "rules": {
            "conventions.require_comment": {
                "require_column_comments": True,
                "comment_min_length": -1,
            }
        },
    }
    with pytest.raises(SQLFluffUserError, match="comment_min_length"):
        get_ruleset().get_rulepack(
            FluffConfig(configs=configs, overrides={"dialect": "databricks"})
        )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("BOOLEAN=_ind$, DATE=_date$", {"BOOLEAN": "_ind$", "DATE": "_date$"}),
        ('{"BOOLEAN": "_ind$"}', {"BOOLEAN": "_ind$"}),
        ("", {}),
        (None, {}),
    ],
)
def test_parse_mapping_spellings(value, expected):
    from sqlfluff_plugin_conventions.config import parse_mapping

    assert parse_mapping(value) == expected


def test_parse_mapping_rejects_bad_entries():
    from sqlfluff_plugin_conventions.config import parse_mapping

    with pytest.raises(SQLFluffUserError):
        parse_mapping("BOOLEAN")


def test_parse_list_spellings():
    from sqlfluff_plugin_conventions.config import parse_list

    assert parse_list("declaration, cast") == ["declaration", "cast"]
    assert parse_list('["declaration"]') == ["declaration"]
    assert parse_list("") == []
