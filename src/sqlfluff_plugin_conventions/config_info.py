"""Validation and documentation for the plugin's rule configuration.

Kept in its own module, importable without importing any rule, because
SQLFluff must be able to run ``get_configs_info()`` before any rule class is
loaded -- rule docstrings are enriched from it at class-creation time.

Config names are global across SQLFluff and all installed plugins, so every
one here is prefixed distinctively. A bare ``patterns`` or ``columns`` would
silently collide with, or be shadowed by, another plugin's key.
"""

from sqlfluff.core.rules import ConfigInfo

CONFIGS_INFO: dict[str, ConfigInfo] = {
    "type_patterns": {
        "definition": (
            "A mapping from canonical datatype to the regex a column name "
            "must match, e.g. `BOOLEAN=_ind$, DATE=_date$`, or a JSON object. "
            "Types are canonical, so INT and INTEGER are the same, as are "
            "TIMESTAMP_NTZ and TIMESTAMP. Regexes are matched with `search`, "
            "so anchor with `$` or `^` as needed. Columns whose type the file "
            "does not state are always skipped."
        )
    },
    "type_origins": {
        "definition": (
            "Where a column's type may come from: any of `declaration` "
            "(CREATE TABLE columns and view column lists), `cast` (an explicit "
            "CAST(x AS T) AS name), or `alias` (a select alias, which never "
            "has a type and so matches no pattern). Default: declaration, cast."
        )
    },
    "case_convention": {
        "definition": "The casing convention identifiers must follow.",
        "validation": ["snake", "upper_snake", "camel", "pascal"],
    },
    "case_columns": {
        "definition": "Whether column names are checked for case.",
        "validation": [True, False],
    },
    "case_tables": {
        "definition": "Whether table and view names are checked for case.",
        "validation": [True, False],
    },
    "max_identifier_length": {
        "definition": (
            "Maximum column-name length. Zero (the default) disables the rule."
        )
    },
    "forbidden_patterns": {
        "definition": (
            "A mapping from regex to the reason shown when a name matches, "
            "e.g. `_tmp$=use _scratch instead`, or a JSON object. Matching "
            "uses `search`."
        )
    },
    "forbidden_columns": {
        "definition": "Whether column names are checked against forbidden patterns.",
        "validation": [True, False],
    },
    "forbidden_tables": {
        "definition": "Whether table names are checked against forbidden patterns.",
        "validation": [True, False],
    },
    "object_patterns": {
        "definition": (
            "A mapping from object kind to the regex its name must match. "
            "Valid kinds: `table`, `view`, `streaming_table`, "
            "`materialized_view`, e.g. `view=^vw_, table=^tbl_`. Matching "
            "uses `search`."
        )
    },
    "qualified_name_min_parts": {
        "definition": (
            "How many dotted parts a created object's name must have, e.g. "
            "`3` for `catalog.schema.object`. Zero (the default) disables "
            "the rule."
        )
    },
    "require_cluster_by": {
        "definition": "Whether created tables must declare CLUSTER BY.",
        "validation": [True, False],
    },
    "require_partition_by": {
        "definition": "Whether created tables must declare PARTITIONED BY.",
        "validation": [True, False],
    },
    "allow_cluster_by_auto": {
        "definition": ("Whether `CLUSTER BY AUTO` counts as a clustering design."),
        "validation": [True, False],
    },
    "require_primary_key": {
        "definition": (
            "Whether created tables with declared columns must carry a "
            "PRIMARY KEY, column-level or table-level."
        ),
        "validation": [True, False],
    },
    "require_not_null": {
        "definition": ("Whether every declared column must carry NOT NULL."),
        "validation": [True, False],
    },
    "forbidden_types": {
        "definition": (
            "A mapping from canonical datatype to the reason it is banned, "
            "e.g. `FLOAT=use DECIMAL for money, DOUBLE=use DECIMAL`, or a "
            "JSON object."
        )
    },
    "types_requiring_parameters": {
        "definition": (
            "Canonical datatypes that must be written with explicit "
            "parameters, e.g. `DECIMAL` to reject bare `DECIMAL`. A "
            "comma-separated list or a JSON array."
        )
    },
    "require_table_comments": {
        "definition": "Whether every created table and view must carry a COMMENT.",
        "validation": [True, False],
    },
    "require_column_comments": {
        "definition": "Whether every declared column must carry a COMMENT.",
        "validation": [True, False],
    },
    "comment_min_length": {
        "definition": (
            "Minimum number of characters a comment must have to count, after "
            "stripping whitespace. Default 1, so an empty string is caught."
        )
    },
    "comment_forbidden_patterns": {
        "definition": (
            "A list of regexes that a comment must not match, for comments "
            "that are technically present but useless (for example "
            "`^(todo|tbd|n/?a)$`). Matching is case-insensitive. A "
            "comma-separated list or a JSON array."
        )
    },
    "required_property_keys": {
        "definition": (
            "TBLPROPERTIES keys every created table must set, whatever the "
            "value. A comma-separated list or a JSON array."
        )
    },
    "required_property_values": {
        "definition": (
            "TBLPROPERTIES keys that must have an exact value, e.g. "
            "`quality=gold`, or a JSON object."
        )
    },
    "allowed_providers": {
        "definition": (
            "The data sources a CREATE TABLE may use in its USING clause, "
            "e.g. `delta`. An empty list (the default) disables the rule."
        )
    },
    "require_explicit_provider": {
        "definition": (
            "Whether a CREATE TABLE with no USING clause at all is a "
            "violation, even though the platform may default one."
        ),
        "validation": [True, False],
    },
    "allow_qualified_star": {
        "definition": (
            "Whether `t.*` is allowed. A bare `*` is never allowed when this "
            "rule is enabled."
        ),
        "validation": [True, False],
    },
    "comment_score_function": {
        "definition": (
            "The scorer used by comment_quality: an installed scorer name "
            "from the `sqlfluff_conventions.comment_scorers` entry-point "
            "group, `module:function`, or `path/to/scorers.py:function`. The "
            "callable takes the comment string -- or a `CommentContext` if "
            "annotated as such -- and returns a number between 0 and 1. No "
            "scorers are built in; unset means the rule does nothing."
        )
    },
    "comment_score_threshold": {
        "definition": (
            "Comments scoring below this number (0 to 1) are violations. "
            "Unset means the rule does nothing."
        )
    },
    "comment_score_columns": {
        "definition": "Whether column comments are scored.",
        "validation": [True, False],
    },
    "comment_score_tables": {
        "definition": "Whether table and view comments are scored.",
        "validation": [True, False],
    },
}
