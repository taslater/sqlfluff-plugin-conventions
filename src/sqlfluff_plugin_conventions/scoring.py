"""Scorer functions for comment quality: load them, call them, trust nothing.

This is the extension surface for teams who want to judge comments. A scorer
is any callable that takes the comment text (or a richer ``CommentContext``)
and returns a number between 0 and 1::

    def brief(comment: str) -> float:
        return min(1.0, len(comment.split()) / 5)

    def names_the_thing(ctx: CommentContext) -> float:
        tokens = set(ctx.name.lower().split("_"))
        return 0.0 if tokens & set(ctx.comment.lower().split()) else 1.0

There are no built-in scorers and no defaults. Score functions are loaded
from one of three places, named by ``comment_score_function``:

* an entry point name from the group ``sqlfluff_conventions.comment_scorers``
  (for packaged scorers)
* ``package.module:function`` (for installed modules)
* ``path/to/scorers.py:function`` (for a plain script in the repo)

A scorer that cannot be loaded, returns a non-numeric or out-of-range value,
or raises, fails the lint run with its own name in the message. A scorer that
silently does nothing is worse than a broken one, because the corpus comes
back clean.

Setting ``SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS`` to a truthy value refuses
the file-path spelling entirely, so a shared CI can allow only installed
modules and entry points.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import math
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlfluff.core.errors import SQLFluffUserError

__all__ = [
    "NO_FILE_SCORERS_ENV",
    "CommentContext",
    "CommentScore",
    "LoadedScorer",
    "load_scorer",
    "score_comment",
]

SCORER_ENTRY_POINT_GROUP = "sqlfluff_conventions.comment_scorers"

#: Set to a truthy value to refuse file-path scorers, so shared CI can allow
#: only installed modules and entry points.
NO_FILE_SCORERS_ENV = "SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS"


def _file_scorers_disabled() -> bool:
    value = os.environ.get(NO_FILE_SCORERS_ENV, "").strip().lower()
    return value in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class CommentContext:
    """Everything a scorer may know about the comment it is judging.

    ``kind`` is ``"column"`` or ``"table"``. ``duplicates`` counts other
    columns in the same table carrying the same normalised comment, so a
    scorer can penalise copy-paste without doing its own bookkeeping.
    """

    comment: str
    name: str = ""
    kind: str = "column"
    data_type: str | None = None
    table_name: str = ""
    duplicates: int = 0


@dataclass(frozen=True)
class CommentScore:
    """A score and, optionally, the scorer's own explanation."""

    value: float
    notes: str = ""


@dataclass(frozen=True)
class LoadedScorer:
    """A validated scorer function and how to call it."""

    name: str
    function: Callable[..., Any]
    uses_context: bool


def _entry_points() -> dict[str, str]:
    """Installed scorer entry points, mapped name -> ``module:attr`` value."""
    discovered: dict[str, str] = {}
    for point in importlib.metadata.entry_points(group=SCORER_ENTRY_POINT_GROUP):
        discovered[point.name] = point.value
    return discovered


def _uses_context(function: Callable[..., Any], name: str) -> bool:
    """Validate the scorer's signature and report which protocol it uses.

    One required positional argument. Annotate it as ``CommentContext`` to
    receive the context; anything else (including no annotation) receives the
    plain comment string.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError) as exc:
        raise SQLFluffUserError(
            f"Comment scorer {name!r} has no inspectable signature: {exc}"
        ) from exc

    parameters = list(signature.parameters.values())
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters):
        raise SQLFluffUserError(
            f"Comment scorer {name!r} must take exactly one argument "
            f"(the comment or a CommentContext), not *args"
        )
    positional = [
        p
        for p in parameters
        if p.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) != 1:
        raise SQLFluffUserError(
            f"Comment scorer {name!r} must take exactly one argument "
            f"(the comment or a CommentContext); found {len(positional)}"
        )

    annotation = positional[0].annotation
    if annotation is inspect.Parameter.empty:
        return False
    if isinstance(annotation, str):
        annotation_name = annotation.split(".")[-1]
    else:
        annotation_name = getattr(annotation, "__name__", "")
    return annotation_name == "CommentContext"


def _resolve_attr(module: Any, attr: str, source: str) -> Callable[..., Any]:
    function = getattr(module, attr, None)
    if function is None:
        raise SQLFluffUserError(f"Comment scorer {source!r} has no attribute {attr!r}")
    if not callable(function):
        raise SQLFluffUserError(
            f"Comment scorer {source!r} resolves to {attr!r}, which is not callable"
        )
    return function


def _load_from_module(module_name: str, attr: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_name)
    # TypeError/ValueError cover relative-import shapes ("..") and empty
    # names, which are config typos, not crashes.
    except (ImportError, TypeError, ValueError) as exc:
        raise SQLFluffUserError(
            f"Comment scorer module {module_name!r} could not be imported: {exc}"
        ) from exc
    return _resolve_attr(module, attr, f"{module_name}:{attr}")


def _load_from_file(path_text: str, attr: str) -> Callable[..., Any]:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise SQLFluffUserError(f"Comment scorer file {str(path)!r} does not exist")
    module_name = (
        "_sqlfluff_conventions_scorer_"
        + hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:12]
    )
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SQLFluffUserError(f"Comment scorer file {str(path)!r} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise SQLFluffUserError(
            f"Comment scorer file {str(path)!r} raised while importing: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return _resolve_attr(module, attr, f"{path_text}:{attr}")


def load_scorer(spec: str) -> LoadedScorer:
    """Load and validate the scorer named by ``spec``.

    Resolution order: an installed entry point name first, then anything with
    a colon is a module or file path plus attribute, then an error.
    """
    text = (spec or "").strip()
    if not text:
        raise SQLFluffUserError("comment_score_function is empty")

    entry_points = _entry_points()
    if text in entry_points:
        module_name, _, attr = entry_points[text].partition(":")
        if not module_name or not attr:
            raise SQLFluffUserError(
                f"Comment scorer entry point {text!r} has an unexpected value "
                f"{entry_points[text]!r}; expected 'module:function'"
            )
        function = _load_from_module(module_name, attr)
        name = text
    elif ":" in text:
        target, _, attr = text.rpartition(":")
        if not target or not attr:
            raise SQLFluffUserError(
                f"Comment scorer {text!r} must be 'module:function' or "
                f"'path/to/scorers.py:function'"
            )
        if target.endswith(".py") or "/" in target or "\\" in target:
            if _file_scorers_disabled():
                raise SQLFluffUserError(
                    f"Comment scorer {text!r} is a file path, but "
                    f"{NO_FILE_SCORERS_ENV} is set; use an installed module "
                    f"or an entry point instead"
                )
            function = _load_from_file(target, attr)
        else:
            function = _load_from_module(target, attr)
        name = text
    else:
        raise SQLFluffUserError(
            f"Comment scorer {text!r} is neither an installed scorer name nor "
            f"a 'module:function' or 'path/to/scorers.py:function' reference"
        )

    return LoadedScorer(
        name=name, function=function, uses_context=_uses_context(function, name)
    )


def score_comment(context: CommentContext, scorer: LoadedScorer) -> CommentScore:
    """Run one scorer, validating what it returns.

    Returns a validated score in [0, 1]; raises ``SQLFluffUserError`` if the
    scorer raises or returns anything else. Errors name the scorer, because a
    scorer that fails silently makes a clean lint run a lie.
    """
    try:
        if scorer.uses_context:
            raw: CommentScore | float = scorer.function(context)
        else:
            raw = scorer.function(context.comment)
    except Exception as exc:
        raise SQLFluffUserError(
            f"Comment scorer {scorer.name!r} raised {type(exc).__name__}: {exc}"
        ) from exc

    if isinstance(raw, CommentScore):
        result = raw
    elif isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SQLFluffUserError(
            f"Comment scorer {scorer.name!r} returned {raw!r}; expected a "
            f"number between 0 and 1"
        )
    else:
        result = CommentScore(float(raw))

    if not math.isfinite(result.value) or not 0.0 <= result.value <= 1.0:
        raise SQLFluffUserError(
            f"Comment scorer {scorer.name!r} returned {result.value!r}; "
            f"scores must be between 0 and 1"
        )
    return result
