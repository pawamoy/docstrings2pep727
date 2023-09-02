"""Module docstring."""

import warnings

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