"""Lint and test boardfarm on multiple python environments."""

import nox

_PYTHON_VERSIONS = ["3.11"]

# Fail nox session when run a program which
# is not installed in its virtualenv
nox.options.error_on_external_run = True


@nox.session(python=_PYTHON_VERSIONS)
def lint(session: nox.Session) -> None:
    """Lint boardfarm.

    # noqa: DAR101
    """
    session.install("--upgrade", ".[dev]")
    session.run("ruff", "format", "--check", ".")
    session.run("ruff", "check", ".")
    session.run("flake8", ".")
    session.run("mypy", "boardfarm3")


@nox.session(python=_PYTHON_VERSIONS)
def pylint(session: nox.Session) -> None:
    """Lint boardfarm using pylint without dev dependencies.

    # noqa: DAR101
    """
    session.install("--upgrade", ".", "pylint", "pylint-per-file-ignores")
    session.run("pylint", "boardfarm3")


@nox.session(python=_PYTHON_VERSIONS)
def test(session: nox.Session) -> None:
    """Test boardfarm.

    # noqa: DAR101
    """
    session.install("--upgrade", ".[test]")
    session.run("pytest", "unittests")
