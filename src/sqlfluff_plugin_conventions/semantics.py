"""Extract a small semantic model from a SQLFluff parse tree.

Rules in this plugin are written against this model, not against raw segment
trees. That is a deliberate boundary: a team writing its own rules should not
need to know how each dialect nests a ``column_definition``, and when a dialect
moves a segment the breakage is confined to this file.

Type resolution is deliberately local: a column's type is known only when the
file itself says so, via a ``CREATE TABLE`` declaration, a view's column list,
or an explicit ``CAST(x AS T) AS name`` in a select list. Anything else is left
as ``None`` and rules skip it. A linter that guesses types and then reports on
the guess is worse than one that stays quiet: the guess is invisible in the
diagnostic, so a wrong report looks like a real finding.

This module is a public API. Third-party rules can import ``analyse`` and the
dataclasses below and depend on them; they change only with a minor version.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlfluff.core.parser import BaseSegment

__all__ = [
    "Analysis",
    "Column",
    "SelectStar",
    "Table",
    "analyse",
    "canonical_type",
    "normalise_type",
]


# --- data model -------------------------------------------------------------


@dataclass
class Column:
    """A column with a name and, where the file states one, a type.

    ``origin`` records where the column was found: ``declaration`` (a CREATE
    TABLE column or a view column list), ``cast`` (an explicit
    ``CAST(x AS T) AS name``), or ``alias`` (a select-list alias of unknown
    type). ``segment`` is the anchor a rule should report against.
    """

    name: str
    segment: BaseSegment
    data_type: str | None = None  # canonical, e.g. "BOOLEAN", "DECIMAL"
    raw_type: str | None = None  # as written, e.g. "decimal(10,2)"
    comment: str | None = None
    origin: str = "declaration"
    primary_key: bool = False
    not_null: bool = False

    @property
    def has_type(self) -> bool:
        """Whether the file itself states this column's type."""
        return self.data_type is not None


@dataclass
class Table:
    """A table or view being created or replaced."""

    name: str
    segment: BaseSegment
    kind: str = "table"  # table | view | streaming_table | materialized_view
    columns: list[Column] = field(default_factory=list)
    provider: str | None = None  # the USING clause, lowercased
    comment: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    primary_key: bool = False  # a table-level PRIMARY KEY constraint
    cluster_by: bool = False  # a CLUSTER BY clause (including AUTO)
    cluster_by_auto: bool = False  # CLUSTER BY AUTO specifically
    partitioned_by: bool = False


@dataclass
class SelectStar:
    """A ``SELECT *`` or ``SELECT t.*``."""

    segment: BaseSegment
    qualified: bool


@dataclass
class Analysis:
    """Everything the rules can see for one file."""

    tables: list[Table] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    select_stars: list[SelectStar] = field(default_factory=list)
    drops_without_if_exists: list[tuple[str, BaseSegment]] = field(default_factory=list)
    inserts_without_column_list: list[BaseSegment] = field(default_factory=list)
    destructive_statements_without_where: list[tuple[str, BaseSegment]] = field(
        default_factory=list
    )


# --- type handling ----------------------------------------------------------

# Spark spells several types more than one way. Rules should be able to say
# "TIMESTAMP" and match every spelling of it.
TYPE_ALIASES = {
    "INT": "INTEGER",
    "DEC": "DECIMAL",
    "NUMERIC": "DECIMAL",
    "REAL": "FLOAT",
    "BOOL": "BOOLEAN",
    "TIMESTAMP_LTZ": "TIMESTAMP",
    "TIMESTAMP_NTZ": "TIMESTAMP",
    "LONG": "BIGINT",
    "SHORT": "SMALLINT",
    "BYTE": "TINYINT",
    "CHAR": "STRING",
    "VARCHAR": "STRING",
}


def normalise_type(raw: str | None) -> str | None:
    """Reduce a written type to its base name.

    ``decimal(10,2)`` -> ``DECIMAL``; ``array<int>`` -> ``ARRAY``. Parameters
    are kept separately on ``Column.raw_type`` for any rule that wants them.
    """
    if not raw:
        return None
    text = raw.strip()
    for sep in ("(", "<"):
        if sep in text:
            text = text.split(sep, 1)[0]
    return text.strip().upper() or None


def canonical_type(raw: str | None) -> str | None:
    """Normalise a type and fold known aliases into one canonical spelling."""
    base = normalise_type(raw)
    if base is None:
        return None
    return TYPE_ALIASES.get(base, base)


# --- segment helpers --------------------------------------------------------

_META_TYPES = (
    "whitespace",
    "newline",
    "indent",
    "dedent",
    "meta",
    "comment",
    "inline_comment",
)

# Sub-trees that never hold the table's own COMMENT.
_TABLE_COMMENT_SKIP = (
    "bracketed",
    "select_statement",
    "data_type",
    "table_reference",
    "using_clause",
    "statement_terminator",
    "values_clause",
)


def _visible(seg: BaseSegment) -> list[BaseSegment]:
    """Direct children, ignoring whitespace and other meta segments."""
    return [child for child in seg.segments if not child.is_type(*_META_TYPES)]


def _unquote(raw: str) -> str:
    """Strip identifier or literal quoting, collapsing doubled quotes."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"`":
        quote, inner = text[0], text[1:-1]
        return inner.replace(quote * 2, quote)
    return text


def _identifier_in(seg: BaseSegment | None) -> BaseSegment | None:
    """The identifier segment naming a column, unwrapping references."""
    if seg is None:
        return None
    named = list(seg.recursive_crawl("naked_identifier", "quoted_identifier"))
    if named:
        return named[-1]
    return seg


def _name_segment(seg: BaseSegment) -> BaseSegment | None:
    """The first column-name child of a definition or view column list item."""
    for child in seg.segments:
        if child.is_type("column_reference", "naked_identifier", "quoted_identifier"):
            return _identifier_in(child)
    return None


def _next_literal_after(
    parent: BaseSegment, keyword: BaseSegment
) -> BaseSegment | None:
    """The first literal sibling after ``keyword`` within ``parent``."""
    seen = False
    for child in parent.segments:
        if child is keyword:
            seen = True
            continue
        if not seen or child.is_type(*_META_TYPES):
            continue
        if child.is_type("quoted_literal", "literal", "naked_identifier"):
            return child
        return None
    return None


def _find_comment(seg: BaseSegment, skip: tuple[str, ...]) -> str | None:
    """Find a ``COMMENT '...'`` inside ``seg``, without descending into skip.

    Handles all three shapes in the wild: Databricks wraps column comments in
    ``column_properties_segment``, view comments in ``comment_clause``, and
    SparkSQL/Hive leaves a bare ``COMMENT`` keyword followed by a literal.
    """
    for child in seg.segments:
        if child.is_type(*skip):
            continue
        if child.is_type("keyword") and child.raw_upper == "COMMENT":
            literal = _next_literal_after(seg, child)
            if literal is not None:
                return _unquote(literal.raw)
        if child.segments:
            found = _find_comment(child, skip)
            if found is not None:
                return found
    return None


def _comment_in_clause(clause: BaseSegment) -> str | None:
    """The value of a ``comment_clause`` or bare COMMENT keyword sequence."""
    if clause.is_type("keyword"):
        return None
    literal = next(clause.recursive_crawl("quoted_literal"), None)
    return _unquote(literal.raw) if literal is not None else None


def _has_if_exists(seg: BaseSegment) -> bool:
    keywords = [child.raw_upper for child in seg.segments if child.is_type("keyword")]
    return "IF" in keywords and "EXISTS" in keywords


def _keywords(seg: BaseSegment, skip: tuple[str, ...] = ()) -> list[str]:
    """Uppercased keyword children anywhere under ``seg``, minus skip."""
    found: list[str] = []
    for child in seg.segments:
        if child.is_type(*skip):
            continue
        if child.is_type("keyword"):
            found.append(child.raw_upper)
        if child.segments:
            found.extend(_keywords(child, skip))
    return found


def _has_keywords(seg: BaseSegment, *words: str, skip: tuple[str, ...] = ()) -> bool:
    keywords = _keywords(seg, skip)
    return all(word in keywords for word in words)


def _has_partitioned_by(stmt: BaseSegment) -> bool:
    keywords = [child.raw_upper for child in stmt.segments if child.is_type("keyword")]
    return any(
        first == "PARTITIONED" and second == "BY"
        for first, second in zip(keywords, keywords[1:])
    )


def _has_adjacent_keywords(seg: BaseSegment, first: str, second: str) -> bool:
    """Whether ``first`` is immediately followed by ``second`` as keywords."""
    keywords = [child.raw_upper for child in seg.segments if child.is_type("keyword")]
    return any(
        one == first and two == second for one, two in zip(keywords, keywords[1:])
    )


def _column_is_not_null(seg: BaseSegment) -> bool:
    """True when NOT NULL is written as a constraint, not inside an expression.

    Only direct keyword children and the named constraint/properties subtrees
    are inspected, so a DEFAULT expression, a CHECK expression or a string
    literal containing those words cannot falsely satisfy the requirement.
    """
    if _has_adjacent_keywords(seg, "NOT", "NULL"):
        return True
    return any(
        _has_adjacent_keywords(child, "NOT", "NULL")
        for child in seg.segments
        if child.is_type("column_properties_segment", "column_constraint_segment")
    )


def _table_has_primary_key(stmt: BaseSegment) -> bool:
    bracketed = stmt.get_child("bracketed")
    if bracketed is None:
        return False
    return any(
        _has_keywords(constraint, "PRIMARY", "KEY")
        for constraint in bracketed.recursive_crawl("table_constraint")
    )


# --- per-statement extraction ----------------------------------------------


def _table_name(stmt: BaseSegment) -> str:
    ref = stmt.get_child("table_reference")
    if ref is None:
        return ""
    return _unquote(ref.raw)


def _table_kind(stmt: BaseSegment) -> str:
    if stmt.is_type("create_materialized_view_statement"):
        return "materialized_view"
    if stmt.is_type("create_view_statement"):
        return "view"
    keywords = {child.raw_upper for child in stmt.segments if child.is_type("keyword")}
    if "STREAMING" in keywords or "LIVE" in keywords:
        return "streaming_table"
    return "table"


def _table_provider(stmt: BaseSegment) -> str | None:
    clause = stmt.get_child("using_clause")
    if clause is None:
        return None
    fmt = clause.get_child("data_source_format")
    if fmt is not None:
        return fmt.raw.strip().strip("`").lower() or None
    items = _visible(clause)
    if items and items[0].is_type("keyword") and items[0].raw_upper == "USING":
        items = items[1:]
    provider = " ".join(item.raw for item in items).strip().strip("`").lower()
    return provider or None


def _table_properties(stmt: BaseSegment) -> dict[str, str]:
    items = _visible(stmt)
    for index, child in enumerate(items):
        if child.is_type("keyword") and child.raw_upper == "TBLPROPERTIES":
            rest = items[index + 1 :]
            bracketed = rest[0] if rest else None
            if bracketed is not None and bracketed.is_type("bracketed"):
                return _parse_property_bracket(bracketed)
            return {}
    return {}


def _parse_property_bracket(bracketed: BaseSegment) -> dict[str, str]:
    props: dict[str, str] = {}
    items = _visible(bracketed)
    index = 0
    while index < len(items):
        item = items[index]
        if item.is_type("property_name_identifier"):
            key = _unquote(item.raw)
            cursor = index + 1
            if cursor < len(items) and items[cursor].is_type("comparison_operator"):
                cursor += 1
            value = _unquote(items[cursor].raw) if cursor < len(items) else ""
            props[key] = value
            index = cursor
        index += 1
    return props


def _cast_target_type(node: BaseSegment) -> str | None:
    """The target type when ``node`` is exactly a cast, else None.

    ``CAST(x AS BOOLEAN)`` and ``x::BOOLEAN`` both resolve; ``CAST(a AS INT)
    + 1`` does not, because the expression is an addition and inferring the
    result type is analysis we deliberately do not do.
    """
    current = node
    while current.is_type("expression") or (
        len(_visible(current)) == 1
        and not current.is_type("function", "cast_expression")
    ):
        children = _visible(current)
        if len(children) != 1:
            return None
        current = children[0]

    if current.is_type("cast_expression"):
        data_type = current.get_child("data_type")
        return data_type.raw if data_type is not None else None

    if current.is_type("function"):
        name = current.get_child("function_name")
        if name is not None and name.raw.upper() in (
            "CAST",
            "TRY_CAST",
            "SAFE_CAST",
        ):
            data_type = next(current.recursive_crawl("data_type"), None)
            return data_type.raw if data_type is not None else None

    return None


def _view_columns(stmt: BaseSegment, table: Table) -> None:
    """Columns of a view's explicit column list, with any inline comments."""
    for child in stmt.segments:
        if not child.is_type("bracketed"):
            continue
        current: Column | None = None
        for item in _visible(child):
            if item.is_type(
                "column_reference", "naked_identifier", "quoted_identifier"
            ):
                name_seg = _identifier_in(item)
                current = Column(
                    name=_unquote(name_seg.raw) if name_seg else _unquote(item.raw),
                    segment=name_seg or item,
                    origin="declaration",
                )
                table.columns.append(current)
            elif item.is_type("comment_clause") and current is not None:
                current.comment = _comment_in_clause(item)
        break


def _insert_has_column_list(stmt: BaseSegment) -> bool:
    for child in stmt.segments:
        if child.is_type("bracketed") and next(
            child.recursive_crawl("column_reference"), None
        ):
            return True
    keywords = [child.raw_upper for child in stmt.segments if child.is_type("keyword")]
    return "BY" in keywords and "NAME" in keywords


# --- comment assignments ----------------------------------------------------


def _reference_parts(ref: BaseSegment) -> list[str]:
    """The unquoted identifier parts of a reference, outermost first."""
    return [
        _unquote(seg.raw)
        for seg in ref.recursive_crawl("naked_identifier", "quoted_identifier")
    ]


def _match_table(tables: list[Table], name: str) -> Table | None:
    """Find a created table by name, tolerating qualification differences.

    An unambiguous match is required: if two schemas in the same file both
    declare a table with the same final name, a qualifier-free reference
    cannot be attributed to either, so nothing is returned rather than a
    coin-flip.
    """
    target = name.strip().casefold()
    if not target:
        return None
    exact = [table for table in tables if table.name.casefold() == target]
    if exact:
        return exact[0]
    target_last = target.rsplit(".", 1)[-1]
    suffix_matches = [
        table
        for table in tables
        if table.name.casefold().rsplit(".", 1)[-1] == target_last
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None


def _comment_on_target(
    clause: BaseSegment,
) -> tuple[str, BaseSegment, BaseSegment] | None:
    """(kind, reference, literal) for a top-level COMMENT ON clause."""
    kind = None
    reference = None
    literal = None
    for child in clause.segments:
        if child.is_type("keyword"):
            if child.raw_upper == "COLUMN":
                kind = "column"
            elif child.raw_upper == "TABLE":
                kind = "table"
        elif child.is_type("column_reference", "table_reference"):
            reference = child
        elif child.is_type("quoted_literal"):
            literal = child
    if kind is None or reference is None or literal is None:
        return None
    return kind, reference, literal


def _set_column_comment(table: Table, column_name: str, value: str) -> None:
    for column in table.columns:
        if column.name.casefold() == column_name.casefold():
            column.comment = value
            return


def _apply_comment_assignments(tree: BaseSegment, analysis: Analysis) -> None:
    """Let COMMENT ON and ALTER ... COMMENT statements fill in comments.

    A comment declared after the CREATE in the same file is as good as one
    written inline, and the last declaration wins. Targets not created in
    this file are ignored: a linter cannot see across files, and pretending
    otherwise would report every migration as undocumented.
    """
    for clause in tree.recursive_crawl("comment_clause"):
        if not any(
            child.is_type("keyword") and child.raw_upper == "ON"
            for child in clause.segments
        ):
            continue
        target = _comment_on_target(clause)
        if target is None:
            continue
        kind, reference, literal = target
        value = _unquote(literal.raw)
        parts = _reference_parts(reference)
        if not parts:
            continue
        if kind == "column":
            if len(parts) < 2:
                continue
            table = _match_table(analysis.tables, ".".join(parts[:-1]))
            if table is not None:
                _set_column_comment(table, parts[-1], value)
        else:
            table = _match_table(analysis.tables, ".".join(parts))
            if table is not None:
                table.comment = value

    for stmt in tree.recursive_crawl("alter_table_statement"):
        keywords = [
            child.raw_upper for child in stmt.segments if child.is_type("keyword")
        ]
        if "COLUMN" not in keywords or "COMMENT" not in keywords:
            continue
        table_ref = stmt.get_child("table_reference")
        column_ref = next(stmt.recursive_crawl("column_reference"), None)
        comment_literal = next(stmt.recursive_crawl("quoted_literal"), None)
        if table_ref is None or column_ref is None or comment_literal is None:
            continue
        table = _match_table(analysis.tables, _unquote(table_ref.raw))
        parts = _reference_parts(column_ref)
        if table is not None and parts:
            _set_column_comment(table, parts[-1], _unquote(comment_literal.raw))


# --- the walker -------------------------------------------------------------


def _walk(seg: BaseSegment, table: Table | None, analysis: Analysis) -> None:
    if seg.is_type(
        "create_table_statement",
        "create_view_statement",
        "create_materialized_view_statement",
    ):
        cluster_clause = seg.get_child("table_cluster_by_clause")
        table = Table(
            name=_table_name(seg),
            segment=seg,
            kind=_table_kind(seg),
            provider=_table_provider(seg),
            comment=_find_comment(seg, _TABLE_COMMENT_SKIP),
            properties=_table_properties(seg),
            primary_key=_table_has_primary_key(seg),
            cluster_by=cluster_clause is not None,
            cluster_by_auto=(
                cluster_clause is not None and "AUTO" in _keywords(cluster_clause)
            ),
            partitioned_by=_has_partitioned_by(seg),
        )
        analysis.tables.append(table)
        if table.kind == "view":
            _view_columns(seg, table)

    elif seg.is_type("column_definition"):
        name_seg = _name_segment(seg)
        if name_seg is not None:
            data_type = seg.get_child("data_type")
            raw_type = data_type.raw if data_type is not None else None
            constraint = next(seg.recursive_crawl("column_constraint_segment"), None)
            column = Column(
                name=_unquote(name_seg.raw),
                segment=name_seg,
                data_type=canonical_type(raw_type),
                raw_type=raw_type,
                comment=_find_comment(seg, ("data_type",)),
                origin="declaration",
                primary_key=(
                    constraint is not None
                    and _has_keywords(constraint, "PRIMARY", "KEY")
                ),
                not_null=_column_is_not_null(seg),
            )
            analysis.columns.append(column)
            if table is not None:
                table.columns.append(column)

    elif seg.is_type("select_clause_element"):
        alias = seg.get_child("alias_expression")
        alias_seg = (
            alias.get_child("naked_identifier", "quoted_identifier")
            if alias is not None
            else None
        )
        if alias_seg is not None:
            main = [
                child
                for child in _visible(seg)
                if not child.is_type("alias_expression")
            ]
            raw_type = _cast_target_type(main[0]) if len(main) == 1 else None
            analysis.columns.append(
                Column(
                    name=_unquote(alias_seg.raw),
                    segment=alias_seg,
                    data_type=canonical_type(raw_type),
                    raw_type=raw_type,
                    origin="cast" if raw_type else "alias",
                )
            )

    elif seg.is_type("wildcard_expression"):
        analysis.select_stars.append(SelectStar(segment=seg, qualified="." in seg.raw))

    elif seg.is_type("drop_table_statement", "drop_view_statement"):
        if not _has_if_exists(seg):
            kind = (
                "table"
                if "TABLE"
                in {
                    child.raw_upper
                    for child in seg.segments
                    if child.is_type("keyword")
                }
                else "view"
            )
            analysis.drops_without_if_exists.append((kind, seg))

    elif seg.is_type("insert_statement"):
        if not _insert_has_column_list(seg):
            analysis.inserts_without_column_list.append(seg)

    elif seg.is_type("delete_statement", "update_statement"):
        if seg.get_child("where_clause") is None:
            kind = "delete" if seg.is_type("delete_statement") else "update"
            analysis.destructive_statements_without_where.append((kind, seg))

    for child in seg.segments:
        _walk(child, table, analysis)


def analyse(tree: BaseSegment | None) -> Analysis:
    """Build the semantic model for one parsed file."""
    analysis = Analysis()
    if tree is not None:
        _walk(tree, None, analysis)
        _apply_comment_assignments(tree, analysis)
    return analysis
