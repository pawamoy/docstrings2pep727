"""Tests for the `cli` module."""

from __future__ import annotations

import pytest

from docstrings2pep727 import cli


def test_main() -> None:
    """Basic CLI test."""
    assert cli.main([]) == 0


def test_show_help(capsys: pytest.CaptureFixture) -> None:
    """Show help.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        cli.main(["-h"])
    captured = capsys.readouterr()
    assert "docstrings2pep727" in captured.out
