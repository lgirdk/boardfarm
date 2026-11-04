"""ptpython REPL settings shared by the CLI interact and the API Python shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

import jedi

if TYPE_CHECKING:
    from ptpython.python_input import PythonInput


def configure_repl(repl: PythonInput) -> None:
    """Configure a few useful defaults.

    :param repl: python input
    """
    repl.show_signature = True
    repl.show_docstring = True
    repl.show_line_numbers = True
    repl.highlight_matching_parenthesis = True


def disable_jedi_descriptor_getattr() -> None:
    """Stop autocompletion from running object properties.

    Jedi otherwise calls ``__getattr__`` on the live objects (which may talk
    to a device) to complete their attributes.
    """
    interpreter = jedi.Interpreter
    # pylint: disable-next=protected-access,line-too-long
    interpreter._allow_descriptor_getattr_default = False  # type: ignore[attr-defined]  # noqa: SLF001
