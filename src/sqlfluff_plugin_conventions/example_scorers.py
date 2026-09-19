"""Example comment scorers. Illustrations, not defaults.

Nothing here is registered or enabled by anything in the plugin. They exist
so the README has real code to show and the tests have real functions to
load; a team writes its own, or copies these and edits them.

The first two take the comment string; the third takes a ``CommentContext``
for the cases where the column name matters.
"""

from __future__ import annotations

import re

from sqlfluff_plugin_conventions.scoring import CommentContext, CommentScore

_PLACEHOLDERS = re.compile(r"^(todo|tbd|n/?a|none|\.\.\.)$", re.IGNORECASE)
_GENERIC = {
    "data",
    "value",
    "field",
    "flag",
    "info",
    "information",
    "thing",
    "column",
    "table",
    "record",
    "row",
}
_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "this",
    "that",
    "is",
    "are",
    "in",
    "on",
    "to",
    "with",
    "and",
    "or",
}


def word_count(comment: str) -> float:
    """Score purely on how many words the comment has."""
    words = comment.split()
    if len(words) >= 4:
        return 1.0
    if len(words) == 3:
        return 0.75
    if len(words) == 2:
        return 0.5
    if len(words) == 1:
        return 0.2
    return 0.0


def no_placeholder(comment: str) -> float:
    """Zero for TODO/TBD/N/A/none/ellipsis, one otherwise."""
    return 0.0 if _PLACEHOLDERS.match(comment.strip()) else 1.0


def specificity(ctx: CommentContext) -> CommentScore:
    """Reward content words that are not the name, stopwords or filler.

    A comment that only restates its column ("the id" on ``id``) scores zero;
    copy-paste comments are capped so the duplicates count is visible.
    """
    name_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", ctx.name.lower())
        if token and not token.isdigit()
    }
    tokens = {token for token in re.split(r"[^a-z0-9]+", ctx.comment.lower()) if token}
    content = tokens - _STOPWORDS
    if not content:
        return CommentScore(0.0, "no content words")
    informative = content - name_tokens - _GENERIC
    score = min(1.0, len(informative) / 3)
    if ctx.duplicates:
        score = min(score, 0.2)
    return CommentScore(
        score,
        f"{len(informative)} informative word(s), {ctx.duplicates} duplicate(s)",
    )
