"""Module docstring."""

import warnings
from typing import Annotated, doc, name, raises, warns

attr: Annotated[int, doc("Module attribute docstring.")] = 0


class Class:
    """Class docstring."""

    attr: Annotated[float, doc("Class attribute docstring.")] = 1.0

    def method(
        self, parameter: Annotated[str, doc("Parameter docstring.")] = "Tim"
    ) -> Annotated[
        str,
        name("retval"),
        doc("Returns docstring."),
        raises(ValueError, "Exception docstring."),
        warns(FutureWarning, "Warning docstring"),
    ]:
        """Method docstring."""
        warnings.warn("Hello users.", FutureWarning)
        if not parameter:
            raise ValueError("parameter cannot be empty")
        return parameter * 2
