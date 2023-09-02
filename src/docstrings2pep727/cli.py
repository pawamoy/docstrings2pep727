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
def get_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        An argparse parser.
    """
    parser = argparse.ArgumentParser(prog="docstrings2pep727")
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
    return 0
