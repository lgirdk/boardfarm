"""Lint and test boardfarm on multiple python environments."""
import nox

_PYTHON_VERSIONS = ["3.9"]
# Fail nox session when run a program which
# is not installed in its virtualenv
nox.options.error_on_external_run = True


@nox.session(python=_PYTHON_VERSIONS)
def lint(session: nox.Session) -> None:
    """Lint boardfarm."""
    session.install("--upgrade", "pip")
    session.install("--upgrade", "pip", "wheel")
    session.install("--upgrade", "pip", "wheel", ".[dev]")
    session.run("black", ".", "--check")
    session.run("isort", ".", "--check-only")
    session.run("flake8", "boardfarm")


@nox.session(python=_PYTHON_VERSIONS)
def pylint(session: nox.Session) -> None:
    """Lint boardfarm using pylint without dev dependencies."""
    session.install("--upgrade", "pip")
    session.install("--upgrade", "pip", "wheel")
    session.install("--upgrade", "pip", "wheel", ".", "pylint")
    # FIXME: boardfarm-lgi-shared is needed because boardfarm imports,
    # but it should not be a dependency, as it creates a cycle.
    session.install("--upgrade", "pip", "wheel", ".", "pylint", "boardfarm-lgi-shared")
    session.run("pylint", "boardfarm")


@nox.session(python=_PYTHON_VERSIONS)
def test(session: nox.Session) -> None:
    """Test boardfarm."""
    session.install("--upgrade", "pip")
    session.install("--upgrade", "pip", "wheel")
    # FIXME: boardfarm-lgi-shared is needed because boardfarm imports,
    # but it should not be a dependency, as it creates a cycle.
    session.install("--upgrade", "pip", "wheel", ".[test]", "boardfarm-lgi-shared")
    session.run("pytest", "unittests")
