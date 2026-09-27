# SPDX-License-Identifier: ISC
#
# ISC License
#
# Copyright (c) 2023, Timothée Mazzucotelli and contributors
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""Tests for the CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from docstrings2pep727 import main
from docstrings2pep727._internal import debug

if TYPE_CHECKING:
    from pathlib import Path


def test_main() -> None:
    """Require a subcommand when no arguments are given."""
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2


def test_show_help(capsys: pytest.CaptureFixture) -> None:
    """Show help.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit) as error:
        main(["-h"])

    captured = capsys.readouterr()
    assert error.value.code == 0
    assert "docstrings2pep727" in captured.out
    assert "check" in captured.out
    assert "diff" in captured.out
    assert "format" in captured.out


@pytest.mark.parametrize("command", ["check", "diff", "format"])
def test_show_subcommand_help(command: str, capsys: pytest.CaptureFixture) -> None:
    """Show each subcommand's paths and style option."""
    with pytest.raises(SystemExit) as error:
        main([command, "--help"])

    captured = capsys.readouterr()
    assert error.value.code == 0
    assert f"docstrings2pep727 {command}" in captured.out
    assert "PATH" in captured.out
    assert "--style" in captured.out


@pytest.mark.parametrize("command", ["check", "diff", "format"])
def test_subcommands_require_paths(command: str, capsys: pytest.CaptureFixture) -> None:
    """Require at least one path for every subcommand."""
    with pytest.raises(SystemExit) as error:
        main([command])

    assert error.value.code == 2
    assert "PATH" in capsys.readouterr().err


@pytest.mark.parametrize("flags", [[], ["--check"], ["--diff"]])
def test_subcommand_is_required(flags: list[str], tmp_path: Path) -> None:
    """Reject paths and the former flags without a subcommand."""
    file = tmp_path / "sample.py"
    source = "value = 1\n"
    file.write_text(source)

    with pytest.raises(SystemExit) as error:
        main([*flags, str(file)])

    assert error.value.code == 2
    assert file.read_text() == source


def test_show_version(capsys: pytest.CaptureFixture) -> None:
    """Show version.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        main(["-V"])
    captured = capsys.readouterr()
    assert debug._get_version() in captured.out


def test_show_debug_info(capsys: pytest.CaptureFixture) -> None:
    """Show debug information.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        main(["--debug-info"])
    captured = capsys.readouterr().out.lower()
    assert "python" in captured
    assert "system" in captured
    assert "environment" in captured
    assert "packages" in captured


def test_format_directory_and_leave_hidden_environment_alone(tmp_path: Path) -> None:
    """Rewrite Python files below a directory and skip hidden environments."""
    package = tmp_path / "package"
    package.mkdir()
    source = '''def greet(name: str) -> str:
    """Greet a user.

    Args:
        name: The user's name.

    Returns:
        The greeting.
    """
    return "Hello " + name
'''
    file = package / "greeting.py"
    file.write_text(source)

    hidden = tmp_path / ".venv"
    hidden.mkdir()
    hidden_file = hidden / "other.py"
    hidden_file.write_text(source)

    # Rewrite the directory and check the result through the public CLI.
    assert main(["format", str(tmp_path)]) == 0
    transformed = file.read_text()

    assert 'name: Annotated[str, Doc("The user\'s name.")]' in transformed
    assert "-> Annotated[str, Doc('The greeting.')]" in transformed
    assert "Args:" not in transformed
    assert "Returns:" not in transformed
    assert hidden_file.read_text() == source

    # Running the command again must not add another import or annotation.
    assert main(["format", str(tmp_path)]) == 0
    assert file.read_text() == transformed


def test_check_and_diff_do_not_write(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Preview a rewrite without changing the source file."""
    file = tmp_path / "sample.py"
    source = '''def run(value: int) -> None:
    """Args:
        value: The input.
    """
    print(value)
'''
    file.write_text(source)

    # The check command reports pending changes with a nonzero exit status.
    assert main(["check", str(file)]) == 1
    assert "Would transform" in capsys.readouterr().out
    assert file.read_text() == source

    # The diff command shows the exact edit and also leaves the file alone.
    assert main(["diff", str(file)]) == 0
    diff = capsys.readouterr().out
    assert "+from typing import Annotated" in diff
    assert '-    """Args:' in diff
    assert file.read_text() == source

    # After formatting, both preview commands succeed without reporting changes.
    assert main(["format", str(file)]) == 0
    transformed = file.read_text()
    capsys.readouterr()

    assert transformed != source
    assert main(["check", str(file)]) == 0
    assert main(["diff", str(file)]) == 0
    assert capsys.readouterr().out == ""
    assert file.read_text() == transformed


@pytest.mark.parametrize("command", ["check", "diff", "format"])
def test_subcommand_style_override(command: str, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Use the requested docstring style for every subcommand."""
    file = tmp_path / "sample.py"
    source = '''def run(value: int) -> None:
    """Args:
        value: The input.
    """
    print(value)
'''
    file.write_text(source)

    # Sphinx parsing leaves Google sections alone instead of detecting their style.
    assert main([command, "--style", "sphinx", str(file)]) == 0

    assert capsys.readouterr().out == ""
    assert file.read_text() == source


@pytest.mark.parametrize("command", ["check", "diff", "format"])
def test_invalid_path_is_reported(command: str, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A missing input path returns a useful error status."""
    missing = tmp_path / "missing.py"

    assert main([command, str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err
