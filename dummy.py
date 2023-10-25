"""Module docstring."""

import warnings
from typing import Generator


attr: int = 0
"""Module attribute docstring."""

class Class:
    """Class docstring."""

    attr: float = 1.0
    """Class attribute docstring."""

    def method(self, parameter: str = "Tim") -> str:
        """Method docstring.
        
        Parameters:
            parameter: Parameter docstring.

        Raises:
            ValueError: Exception docstring.

        Warns:
            FutureWarning: Warning docstring.

        Returns:
            retval: Returns docstring.
        """
        warnings.warn("Hello users.", FutureWarning)
        if not parameter:
            raise ValueError("parameter cannot be empty")
        return parameter * 2


def single_yields_receives_returns() -> Generator[int, str, bytes]:
    """Summary.

    Yields:
        one: `1`.

    Receives:
        one: `"1"`.

    Returns:
        one: `b"1"`.
    """


def multiple_returns() -> tuple[int, int]:
    """Summary.
    
    Returns:
        one: `1`.
        two: `2`.
    """
    return 1, 2


def multiple_yields_receives_returns() -> Generator[tuple[int, int], tuple[str, str], tuple[bytes, bytes]]:
    """Summary.

    Yields:
        one: `1`.
        two: `2`.

    Receives:
        one: `"1"`.
        two: `"2"`.

    Returns:
        one: `b"1"`.
        two: `b"2"`.
    """