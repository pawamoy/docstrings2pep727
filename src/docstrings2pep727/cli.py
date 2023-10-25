"""Module that contains the command line application."""

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
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import libcst as cst
from griffe.agents.visitor import visit
from griffe.docstrings import Parser

from docstrings2pep727.transformer import PEP727Transformer

if TYPE_CHECKING:
    from griffe import Docstring, Object


from docstrings2pep727 import debug


class _DebugInfo(argparse.Action):
    def __init__(self, nargs: int | str | None = 0, **kwargs: Any) -> None:
        super().__init__(nargs=nargs, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        debug.print_debug_info()
        sys.exit(0)


def _docstrings(obj: Object, store: dict | None = None) -> dict[str, Docstring]:
    if store is None:
        store = {}
    if obj.docstring:
        store[obj.path] = obj.docstring
    for member in obj.members.values():
        if not member.is_alias:
            _docstrings(member, store)  # type: ignore[arg-type]
    return store


def get_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        An argparse parser.
    """
    parser = argparse.ArgumentParser(prog="docstrings2pep727")
    parser.add_argument("module", help="Module to transform.")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {debug.get_version()}")
    parser.add_argument("--debug-info", action=_DebugInfo, help="Print debug information.")
    return parser


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

    module_path = Path(opts.module)
    module_code = module_path.read_text()
    module_data = visit(module_path.stem, module_path, module_code, docstring_parser=Parser("google"))
    docstrings = _docstrings(module_data)

    source_tree = cst.parse_module(module_code)
    transformer = PEP727Transformer(source_tree, module_path.stem, docstrings)
    modified_tree = source_tree.visit(transformer)
    print(modified_tree.code)
    return 0
