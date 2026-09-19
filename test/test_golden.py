"""Golden descriptions: every rule, exactly as users see it.

Deliberately brittle: all 18 rules fire on one file and every diagnostic
word is pinned, so a refactor cannot quietly change what users read.
"""

from __future__ import annotations

from sqlfluff.core import FluffConfig, Linter

GOLDEN_CONFIG = """
[sqlfluff]
dialect = databricks
rules = Conventions_N001,Conventions_N002,Conventions_N003,Conventions_N004,Conventions_N005,Conventions_N006,Conventions_M001,Conventions_M002,Conventions_M003,Conventions_M004,Conventions_M005,Conventions_M006,Conventions_T001,Conventions_A001,Conventions_A002,Conventions_A003,Conventions_A004,Conventions_A005

[sqlfluff:rules:conventions.type_naming]
type_patterns = BOOLEAN=_ind$

[sqlfluff:rules:conventions.identifier_case]
case_columns = True
case_tables = True

[sqlfluff:rules:conventions.identifier_length]
max_identifier_length = 3

[sqlfluff:rules:conventions.forbidden_name]
forbidden_patterns = _tmp$=use _scratch instead

[sqlfluff:rules:conventions.object_name]
object_patterns = view=^vw_

[sqlfluff:rules:conventions.require_qualified_names]
qualified_name_min_parts = 2

[sqlfluff:rules:conventions.require_comment]
require_table_comments = True
require_column_comments = True

[sqlfluff:rules:conventions.require_table_properties]
required_property_keys = quality

[sqlfluff:rules:conventions.require_table_provider]
allowed_providers = delta

[sqlfluff:rules:conventions.comment_quality]
comment_score_function = sqlfluff_plugin_conventions.example_scorers:word_count
comment_score_threshold = 0.9

[sqlfluff:rules:conventions.require_table_design]
require_cluster_by = True

[sqlfluff:rules:conventions.require_constraints]
require_primary_key = True
require_not_null = True

[sqlfluff:rules:conventions.type_policy]
forbidden_types = FLOAT=use DECIMAL for money
types_requiring_parameters = DECIMAL

[sqlfluff:rules:conventions.no_select_star]
force_enable = True

[sqlfluff:rules:conventions.drop_requires_if_exists]
force_enable = True

[sqlfluff:rules:conventions.insert_requires_column_list]
force_enable = True

[sqlfluff:rules:conventions.delete_without_where]
force_enable = True

[sqlfluff:rules:conventions.update_without_where]
force_enable = True
"""

GOLDEN_SQL = """
CREATE TABLE orders (
    active BOOLEAN,
    id_tmp INT,
    amount FLOAT,
    note DECIMAL COMMENT 'short'
) USING parquet;

CREATE VIEW active_view AS SELECT * FROM orders;

INSERT INTO orders SELECT 1;
DELETE FROM orders;
UPDATE orders SET active = TRUE;
DROP TABLE orders;
SELECT CAST(x AS INT) AS camelCase FROM orders;
CREATE VIEW BadView AS SELECT 1;
"""


def test_every_rule_description_is_exactly_as_documented():
    config = FluffConfig.from_string(GOLDEN_CONFIG)
    result = Linter(config=config).lint_string(GOLDEN_SQL)
    observed = {
        (violation.rule_code(), violation.description)
        for violation in result.violations
    }
    expected = {
        (
            "Conventions_A001",
            "SELECT * binds to whatever columns exist at run time; list the columns explicitly",
        ),
        (
            "Conventions_A002",
            "DROP TABLE without IF EXISTS is not re-runnable; use DROP TABLE IF EXISTS",
        ),
        (
            "Conventions_A003",
            "INSERT binds columns by position; name the target columns, or use INSERT INTO ... BY NAME",
        ),
        (
            "Conventions_A004",
            "DELETE without a WHERE clause removes every row; add a predicate or use TRUNCATE deliberately",
        ),
        (
            "Conventions_A005",
            "UPDATE without a WHERE clause rewrites every row; add a predicate",
        ),
        ("Conventions_M001", "column 'active' of table 'orders' has no COMMENT"),
        ("Conventions_M001", "column 'amount' of table 'orders' has no COMMENT"),
        ("Conventions_M001", "column 'id_tmp' of table 'orders' has no COMMENT"),
        ("Conventions_M001", "table 'BadView' has no COMMENT"),
        ("Conventions_M001", "table 'active_view' has no COMMENT"),
        ("Conventions_M001", "table 'orders' has no COMMENT"),
        ("Conventions_M002", "table 'BadView' is missing required property 'quality'"),
        (
            "Conventions_M002",
            "table 'active_view' is missing required property 'quality'",
        ),
        ("Conventions_M002", "table 'orders' is missing required property 'quality'"),
        ("Conventions_M003", "table 'orders' uses provider 'parquet'; allowed: delta"),
        (
            "Conventions_M004",
            "comment on column 'note' scores 0.20, below 0.90 [sqlfluff_plugin_conventions.example_scorers:word_count]",
        ),
        ("Conventions_M005", "table 'orders' has no CLUSTER BY clause"),
        (
            "Conventions_M006",
            "column 'active' of table 'orders' is nullable; add NOT NULL",
        ),
        (
            "Conventions_M006",
            "column 'amount' of table 'orders' is nullable; add NOT NULL",
        ),
        (
            "Conventions_M006",
            "column 'id_tmp' of table 'orders' is nullable; add NOT NULL",
        ),
        (
            "Conventions_M006",
            "column 'note' of table 'orders' is nullable; add NOT NULL",
        ),
        ("Conventions_M006", "table 'orders' declares no PRIMARY KEY"),
        (
            "Conventions_N001",
            "BOOLEAN column 'active' does not match the required pattern /_ind$/",
        ),
        ("Conventions_N002", "column 'camelCase' is not snake case"),
        ("Conventions_N002", "table name part 'BadView' is not snake case"),
        ("Conventions_N003", "column 'active' is 6 characters, over the limit of 3"),
        ("Conventions_N003", "column 'amount' is 6 characters, over the limit of 3"),
        ("Conventions_N003", "column 'camelCase' is 9 characters, over the limit of 3"),
        ("Conventions_N003", "column 'id_tmp' is 6 characters, over the limit of 3"),
        ("Conventions_N003", "column 'note' is 4 characters, over the limit of 3"),
        (
            "Conventions_N004",
            "column 'id_tmp' matches forbidden pattern /_tmp$/ (use _scratch instead)",
        ),
        (
            "Conventions_N005",
            "view 'BadView' does not match the required pattern /^vw_/",
        ),
        (
            "Conventions_N005",
            "view 'active_view' does not match the required pattern /^vw_/",
        ),
        ("Conventions_N006", "table 'orders' has 1 qualified part(s); 2 required"),
        ("Conventions_N006", "view 'BadView' has 1 qualified part(s); 2 required"),
        ("Conventions_N006", "view 'active_view' has 1 qualified part(s); 2 required"),
        (
            "Conventions_T001",
            "'amount' uses forbidden type FLOAT (use DECIMAL for money)",
        ),
        (
            "Conventions_T001",
            "'note' uses bare DECIMAL; explicit parameters are required, e.g. DECIMAL(p, s)",
        ),
    }
    assert observed == expected
