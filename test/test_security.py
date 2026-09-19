"""Security tests: prove the documented trust boundaries hold.

The plugin is allowed to import code a team names; it is not allowed to reach
the network, spawn processes, or fail in any way other than a clear config
error. These tests veto those capabilities and assert nothing changes.
"""

from __future__ import annotations

import os
import socket
import subprocess

from sqlfluff.core import FluffConfig, Linter

from sqlfluff_plugin_conventions.scoring import (
    CommentContext,
    load_scorer,
    score_comment,
)

EXAMPLE_SCORER = "sqlfluff_plugin_conventions.example_scorers:word_count"


def _explode(*args, **kwargs):
    raise AssertionError("this capability must not be used")


def test_scoring_does_not_touch_the_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    scorer = load_scorer(EXAMPLE_SCORER)
    result = score_comment(CommentContext(comment="a decent comment indeed"), scorer)
    assert result.value == 1.0


def test_scoring_does_not_spawn_processes(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", _explode)
    monkeypatch.setattr(subprocess, "run", _explode)
    monkeypatch.setattr(os, "system", _explode)
    scorer = load_scorer(EXAMPLE_SCORER)
    result = score_comment(CommentContext(comment="a decent comment indeed"), scorer)
    assert result.value == 1.0


def test_a_full_lint_with_a_scorer_makes_no_network_calls(monkeypatch):
    monkeypatch.setattr(socket, "socket", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    configs = {
        "core": {"dialect": "databricks", "rules": "Conventions_M004"},
        "rules": {
            "conventions.comment_quality": {
                "comment_score_function": EXAMPLE_SCORER,
                "comment_score_threshold": "0.6",
            }
        },
    }
    config = FluffConfig(configs=configs, overrides={"dialect": "databricks"})
    result = Linter(config=config).lint_string(
        "CREATE TABLE t (id INT COMMENT 'short');\n"
    )
    assert result.violations
