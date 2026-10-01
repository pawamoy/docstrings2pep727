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

# Why does this file exist, and why not put this in `__main__`?
#
# You might be tempted to import things from `__main__` later,
# but that will cause problems: the code will get executed twice:
#
# - When you run `python -m docstrings2pep727` python will execute
#   `__main__.py` as a script. That means there won't be any
#   `docstrings2pep727.__main__` in `sys.modules`.
# - When you import `__main__` it will get executed again (as a module) because
#   there's no `docstrings2pep727.__main__` in `sys.modules`.

from __future__ import annotations

import argparse
import difflib
import io
import os
import sys
import tokenize
from pathlib import Path
from typing import Any

import libcst as cst

from docstrings2pep727._internal import debug
from docstrings2pep727._internal.transformer import _transform_source


class _DebugInfo(argparse.Action):
    def __init__(self, nargs: int | str | None = 0, **kwargs: Any) -> None:
        super().__init__(nargs=nargs, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        debug._print_debug_info()
        sys.exit(0)


def get_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        An argparse parser.
    """
    parser = argparse.ArgumentParser(
        prog="docstrings2pep727",
        description="Move docstring sections into Annotated type metadata.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {debug._get_version()}")
    parser.add_argument("--debug-info", action=_DebugInfo, help="Print debug information.")
    subparsers = parser.add_subparsers(dest="command", required=True, title="subcommands")
    for command, description in (
        ("check", "Report files that would change without writing them. Exit with status 1 if changes are needed."),
        ("diff", "Print a unified diff without writing files."),
        ("format", "Transform Python files in place."),
    ):
        subparser = subparsers.add_parser(command, help=description, description=description)
        subparser.add_argument(
            "paths",
            nargs="+",
            type=Path,
            metavar="PATH",
            help="Python files or directories to process.",
        )
        subparser.add_argument(
            "--style",
            choices=("auto", "google", "numpy", "sphinx"),
            default="auto",
            help="Docstring style (default: auto).",
        )
    return parser


def _python_files(paths: list[Path]) -> list[Path]:
    files: dict[Path, Path] = {}
    excluded = {"__pycache__", "build", "dist", "node_modules", "site-packages", "venv"}

    def raise_walk_error(error: OSError) -> None:
        raise error

    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files[path.resolve()] = path
        elif path.is_dir():
            for root, directories, names in os.walk(path, onerror=raise_walk_error):
                directories[:] = sorted(
                    name for name in directories if not name.startswith(".") and name not in excluded
                )
                for name in sorted(names):
                    if name.endswith(".py"):
                        file = Path(root) / name
                        if not file.is_symlink():
                            files[file.resolve()] = file
        else:
            raise ValueError(f"{path}: expected a Python file or directory")
    return sorted(files.values(), key=str)


def _read_source(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def main(args: list[str] | None = None) -> int:
    """Run the main program.

    This function is executed when you type `docstrings2pep727` or `python -m docstrings2pep727`.

    Parameters:
        args: Arguments passed from the command line.

    Returns:
        An exit code.
    """
    parser = get_parser()
    opts = parser.parse_args(args=args)
    try:
        files = _python_files(opts.paths)
    except (OSError, ValueError) as error:
        print(f"docstrings2pep727: {error}", file=sys.stderr)
        return 2

    changed = False
    failed = False
    for path in files:
        try:
            source, encoding = _read_source(path)
            transformed = _transform_source(source, style=opts.style)
            if transformed == source:
                continue
            changed = True
            if opts.command == "diff":
                print(
                    "".join(
                        difflib.unified_diff(
                            source.splitlines(keepends=True),
                            transformed.splitlines(keepends=True),
                            fromfile=str(path),
                            tofile=str(path),
                        ),
                    ),
                    end="",
                )
            elif opts.command == "check":
                print(f"Would transform {path}")
            else:
                path.write_bytes(transformed.encode(encoding))
                print(f"Transformed {path}")
        except (OSError, UnicodeError, SyntaxError, ValueError, cst.ParserSyntaxError) as error:
            print(f"docstrings2pep727: {path}: {error}", file=sys.stderr)
            failed = True
    if failed:
        return 2
    return 1 if changed and opts.command == "check" else 0
