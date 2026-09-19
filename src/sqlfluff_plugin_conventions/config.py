"""Parsing helpers for values that must live in a ``.sqlfluff`` INI file.

SQLFluff reads INI values as strings (or int/float/bool when they look like
one), so a mapping such as "type -> regex" cannot be a dict the way it was in
this engine's previous TOML life. Two spellings are accepted everywhere a
mapping or list is wanted:

* readable: ``BOOLEAN=_ind$, DATE=_date$`` (commas separate entries)
* JSON:     ``{"BOOLEAN": "_ind$", "DATE": "_date$"}``

The JSON spelling is the escape hatch for values containing ``,`` or ``=``,
which regexes sometimes do. Badly shaped values raise ``SQLFluffUserError``
with the offending text, rather than being silently dropped.
"""

from __future__ import annotations

import json
from typing import Any

from sqlfluff.core.errors import SQLFluffUserError

__all__ = ["parse_list", "parse_mapping"]


def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_list(value: Any) -> list[str]:
    """Parse a comma-separated list, or a JSON array."""
    text = _as_text(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SQLFluffUserError(
                f"Expected a JSON array or a comma-separated list, got {text!r} ({exc})"
            ) from exc
        if not isinstance(loaded, list):
            raise SQLFluffUserError(f"Expected a JSON array, got {text!r}")
        return [str(item) for item in loaded]
    if text.startswith("{"):
        raise SQLFluffUserError(
            f"Expected a JSON array or a comma-separated list, got a JSON "
            f"object: {text!r}"
        )
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_mapping(value: Any, *, regex_keys: bool = False) -> dict[str, str]:
    """Parse a mapping, either as JSON or as ``KEY=value`` entries.

    ``regex_keys`` splits on the *last* ``=`` rather than the first, so a
    regex key containing ``=`` (a lookahead, say) survives the readable
    spelling. Use the JSON spelling when both sides can contain ``=``.
    """
    text = _as_text(value)
    if not text:
        return {}
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SQLFluffUserError(
                f"Expected a JSON object or 'KEY=value, KEY=value' entries, "
                f"got {text!r} ({exc})"
            ) from exc
        if not isinstance(loaded, dict):
            raise SQLFluffUserError(f"Expected a JSON object, got {text!r}")
        return {str(key): str(val) for key, val in loaded.items()}
    if text.startswith("["):
        raise SQLFluffUserError(
            f"Expected a JSON object or 'KEY=value, KEY=value' entries, got a "
            f"JSON array: {text!r}"
        )

    parsed: dict[str, str] = {}
    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, separator, val = (
            entry.rpartition("=") if regex_keys else entry.partition("=")
        )
        if not separator or not key.strip() or not val.strip():
            raise SQLFluffUserError(
                f"Expected entries of the form 'KEY=value' separated by commas, "
                f"got {entry!r}. If a value contains '=' or ',', use the JSON "
                f"spelling instead."
            )
        parsed[key.strip()] = val.strip()
    return parsed
