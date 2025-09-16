"""Lint and test boardfarm on multiple python environments."""

from __future__ import annotations

import nox

_PYTHON_VERSIONS = ["3.11"]

# Fail nox session when run a program which
# is not installed in its virtualenv
nox.options.error_on_external_run = True
nox.options.default_venv_backend = "uv"


def _install_deps(session: nox.Session, group: str | None = None) -> None:
    cmd = [
        "uv",
        "sync",
        "--no-dev",
        f"--python={session.virtualenv.location}",
    ]
    if group:
        cmd.remove("--no-dev")
        cmd.insert(
            2,
            f"--group={group}",
        )

    session.run_install(
        *cmd,
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )


@nox.session(python=_PYTHON_VERSIONS)
def lint(session: nox.Session) -> None:
    """Lint boardfarm.

    # noqa: DAR101
    """
    _install_deps(session=session, group="dev")
    session.run("ruff", "format", "--check", ".")
    session.run("ruff", "check", ".")
    session.run("flake8", ".")
    session.run("mypy", "boardfarm3")


@nox.session(python=_PYTHON_VERSIONS)
def pylint(session: nox.Session) -> None:
    """Lint boardfarm using pylint without dev dependencies.

    # noqa: DAR101
    """
    session.install("--upgrade", ".", "pylint==3.2.6", "pylint-per-file-ignores")
    session.run("pylint", "boardfarm3")


@nox.session(python=_PYTHON_VERSIONS)
def test(session: nox.Session) -> None:
    """Test boardfarm.

    # noqa: DAR101
    """
    _install_deps(session=session, group="test")
    session.run("pytest", "unittests")


@nox.session(python=_PYTHON_VERSIONS)
def boardfarm_help(session: nox.Session) -> None:
    """Execute boardfarm --help.

    This helps identifying integration issues with the plugins/devices.

    # noqa: DAR101
    """
    _install_deps(session=session)
    session.run("boardfarm", "--help")
