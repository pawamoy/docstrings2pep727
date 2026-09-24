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

"""Tests for moving function documentation into annotations."""

from __future__ import annotations

import griffe
import libcst as cst

from docstrings2pep727._internal.transformer import _PEP727Transformer


def test_generator_components_keep_all_documentation() -> None:
    """Document each component of a generator return annotation."""
    source = "def stream() -> Generator[int, str, bool]:\n    pass\n"
    docstring = griffe.Docstring(
        "Summary.\n\nYields:\n    value (int): A value.\n\nReceives:\n    incoming (str): A message.\n\nReturns:\n    result (bool): A result.",
        parser=griffe.Parser.google,
    )
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.stream": docstring}))

    assert transformed.code == (
        "def stream() -> Generator[Annotated[int, Name('value'), Doc('A value.')], "
        "Annotated[str, Name('incoming'), Doc('A message.')], "
        "Annotated[bool, Name('result'), Doc('A result.')]]:\n    pass\n"
    )


def test_unannotated_return_is_left_alone() -> None:
    """A return section cannot modify a function without a return type."""
    source = "def calculate():\n    pass\n"
    docstring = griffe.Docstring("Summary.\n\nReturns:\n    answer (int): The answer.", parser=griffe.Parser.google)
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.calculate": docstring}))

    assert transformed.code == source


def test_tuple_return_documents_each_value() -> None:
    """Keep descriptions attached to the matching tuple values."""
    source = "def pair() -> tuple[int, str]:\n    pass\n"
    docstring = griffe.Docstring(
        "Summary.\n\nReturns:\n    number (int): The count.\n    label (str): The name.",
        parser=griffe.Parser.google,
    )
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.pair": docstring}))

    assert transformed.code == (
        "def pair() -> tuple[Annotated[int, Name('number'), Doc('The count.')], "
        "Annotated[str, Name('label'), Doc('The name.')]]:\n    pass\n"
    )


def test_return_and_raised_exception_share_annotation() -> None:
    """Keep both return and exception descriptions on the return type."""
    source = "def calculate() -> int:\n    pass\n"
    docstring = griffe.Docstring(
        "Summary.\n\nReturns:\n    answer (int): The answer.\n\nRaises:\n    ValueError: Bad input.",
        parser=griffe.Parser.google,
    )
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.calculate": docstring}))

    assert transformed.code == (
        "def calculate() -> Annotated[int, Name('answer'), Doc('The answer.'), "
        "Raises(ValueError, 'Bad input.')]:\n    pass\n"
    )


def test_only_simple_annotated_assignment_uses_its_name() -> None:
    """An attribute target cannot be used as a module variable path."""
    source = "value: int = 1\nobj.value: int = 2\n"
    docstring = griffe.Docstring("The module value.", parser=griffe.Parser.google)
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.value": docstring}))

    assert transformed.code == "value: Annotated[int, Doc('The module value.')] = 1\nobj.value: int = 2\n"
