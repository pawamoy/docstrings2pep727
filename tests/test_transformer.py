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

from docstrings2pep727._internal.transformer import (
    _PEP727Transformer,
    _transform_source,
)


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
        "def stream() -> Generator[Annotated[int, Doc('A value.')], "
        "Annotated[str, Doc('A message.')], "
        "Annotated[bool, Doc('A result.')]]:\n    pass\n"
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
        "def pair() -> tuple[Annotated[int, Doc('The count.')], Annotated[str, Doc('The name.')]]:\n    pass\n"
    )


def test_return_does_not_turn_raise_into_unsupported_metadata() -> None:
    """Only return descriptions belong in Doc metadata."""
    source = "def calculate() -> int:\n    pass\n"
    docstring = griffe.Docstring(
        "Summary.\n\nReturns:\n    answer (int): The answer.\n\nRaises:\n    ValueError: Bad input.",
        parser=griffe.Parser.google,
    )
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.calculate": docstring}))

    assert transformed.code == "def calculate() -> Annotated[int, Doc('The answer.')]:\n    pass\n"


def test_only_simple_annotated_assignment_uses_its_name() -> None:
    """An attribute target cannot be used as a module variable path."""
    source = "value: int = 1\nobj.value: int = 2\n"
    docstring = griffe.Docstring("The module value.", parser=griffe.Parser.google)
    module = cst.parse_module(source)

    transformed = module.visit(_PEP727Transformer(module, "sample", {"sample.value": docstring}))

    assert transformed.code == "value: Annotated[int, Doc('The module value.')] = 1\nobj.value: int = 2\n"


def test_google_sections_move_and_keep_unsupported_sections() -> None:
    """Keep prose and exception documentation while moving typed descriptions."""
    source = '''"""Module summary."""

def calculate(number: int) -> int:
    """Calculate a result.

    Args:
        number: The input.

    Returns:
        The result.

    Raises:
        ValueError: The input is invalid.
    """
    return number * 2
'''

    transformed = _transform_source(source)

    assert "from typing import Annotated" in transformed
    assert "from typing_extensions import Doc" in transformed
    assert "number: Annotated[int, Doc('The input.')]" in transformed
    assert "-> Annotated[int, Doc('The result.')]" in transformed
    assert "Args:" not in transformed
    assert "Returns:" not in transformed
    assert "Raises:\n        ValueError: The input is invalid." in transformed
    assert _transform_source(transformed) == transformed


def test_google_section_at_start_is_removed() -> None:
    """A docstring with no summary can disappear after its section moves."""
    source = '''def run(value: int) -> None:
    """Args:
        value: The input.
    """
    print(value)
'''

    transformed = _transform_source(source)

    assert "def run(value: Annotated[int, Doc('The input.')]) -> None:" in transformed
    assert '"""' not in transformed
    assert "print(value)" in transformed


def test_google_prose_after_section_is_preserved() -> None:
    """A section can end before the next free-form paragraph."""
    source = '''def run(value: int) -> int:
    """Summary.

    Args:
        value: The input.

    Extra context about the result.
    """
    return value
'''

    transformed = _transform_source(source)

    assert "value: Annotated[int, Doc('The input.')]" in transformed
    assert "Args:" not in transformed
    assert "Extra context about the result." in transformed


def test_docstring_only_function_gets_pass() -> None:
    """Removing the only statement still leaves a valid function body."""
    source = '''def run(value: int):
    """Args:
        value: The input.
    """
'''

    transformed = _transform_source(source)

    assert "value: Annotated[int, Doc('The input.')]" in transformed
    assert "    pass\n" in transformed
    assert '"""' not in transformed


def test_unannotated_parameter_section_stays_intact() -> None:
    """A section stays in place if one parameter has no type annotation."""
    source = '''def run(first: int, second):
    """Args:
        first: The first value.
        second: The second value.
    """
    return first, second
'''

    transformed = _transform_source(source)

    assert transformed == source


def test_numpy_sections_move_and_notes_remain() -> None:
    """Move NumPy descriptions without deleting an unrelated Notes section."""
    source = '''def run(value: int) -> int:
    """Summary.

    Parameters
    ----------
    value : int
        The input.

    Returns
    -------
    int
        The output.

    Notes
    -----
    Additional detail.
    """
    return value
'''

    transformed = _transform_source(source)

    assert "value: Annotated[int, Doc('The input.')]" in transformed
    assert "-> Annotated[int, Doc('The output.')]" in transformed
    assert "Parameters\n" not in transformed
    assert "Returns\n" not in transformed
    assert "Notes\n" in transformed
    assert "Additional detail." in transformed


def test_sphinx_fields_move_and_raise_remains() -> None:
    """Move Sphinx parameter and return fields without dropping raises."""
    source = '''def run(value: int) -> int:
    """Summary.

    :param value: The input.
    :type value: int
    :returns: The output.
    :rtype: int
    :raises ValueError: Invalid input.
    """
    return value
'''

    transformed = _transform_source(source)

    assert "value: Annotated[int, Doc('The input.')]" in transformed
    assert "-> Annotated[int, Doc('The output.')]" in transformed
    assert ":param" not in transformed
    assert ":type" not in transformed
    assert ":returns" not in transformed
    assert ":rtype" not in transformed
    assert ":raises ValueError: Invalid input." in transformed


def test_nested_function_and_attribute_docstrings_move() -> None:
    """Convert nested functions and documented attributes without a Griffe path lookup."""
    source = '''item: int = 1
"""The item."""

class Container:
    value: str
    """The value."""

    def outer(self) -> None:
        def inner(number: int) -> int:
            """Args:
                number: The number.
            """
            return number
'''

    transformed = _transform_source(source)

    assert "item: Annotated[int, Doc('The item.')]" in transformed
    assert "value: Annotated[str, Doc('The value.')]" in transformed
    assert "number: Annotated[int, Doc('The number.')]" in transformed
    assert 'The item."""' not in transformed
    assert 'The value."""' not in transformed
