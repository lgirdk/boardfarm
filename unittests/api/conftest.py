"""Shared fixtures for boardfarm API unit tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session
from boardfarm3.lib import device_manager as device_manager_module

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIGS = Path(__file__).parents[2] / "boardfarm3" / "configs"


@pytest.fixture(autouse=True)
def _reset_device_manager_singleton() -> Any:
    """Clear the DeviceManager process global around every test.

    ``pytest-randomly`` shuffles test order, so a leaked singleton would make
    failures depend on ordering.

    :yield: None
    :rtype: Any
    """
    device_manager_module._DEVICE_MANAGER_INSTANCE = None
    yield
    device_manager_module._DEVICE_MANAGER_INSTANCE = None


@pytest.fixture(name="native_payload")
def native_payload_fixture() -> dict[str, Any]:
    """Load the shipped example inventory and env config as a native payload.

    :return: native session payload
    :rtype: dict[str, Any]
    """
    return {
        "inventory": json.loads(
            (CONFIGS / "boardfarm_config_example.json").read_text(encoding="utf-8"),
        ),
        "env": json.loads(
            (CONFIGS / "boardfarm_env_example.json").read_text(encoding="utf-8"),
        ),
    }


class FakeRuntime:
    """RuntimeContext stand-in that records calls instead of touching devices."""

    def __init__(
        self,
        *,
        resolve_error: Exception | None = None,
        boot_error: Exception | None = None,
    ) -> None:
        """Initialise the fake.

        :param resolve_error: raise this from resolve()
        :type resolve_error: Exception | None
        :param boot_error: raise this from boot_blocking()
        :type boot_error: Exception | None
        """
        self.resolve_error = resolve_error
        self.boot_error = boot_error
        self.calls: list[str] = []
        self.config: object | None = None
        self.device_manager: object | None = None

    def refresh_cmdline_args(self) -> None:
        """Record that options were re-materialised."""
        self.calls.append("refresh_cmdline_args")

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Record the call and optionally fail.

        The configured error is an exception instance, so darglint2 cannot
        infer its type from ``raise self.resolve_error``.

        # noqa: DAR401
        # noqa: DAR402

        :param payload: opaque payload
        :type payload: dict[str, Any]
        :raises Exception: when configured to fail
        :return: a placeholder config
        :rtype: object
        """
        self.calls.append("resolve")
        if self.resolve_error:
            raise self.resolve_error
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Record the call.

        :return: a placeholder device manager
        :rtype: object
        """
        self.calls.append("register_devices")
        self.device_manager = object()
        return self.device_manager

    def boot_blocking(self) -> None:
        """Record the call and optionally fail.

        The configured error is an exception instance, so darglint2 cannot
        infer its type from ``raise self.boot_error``.

        # noqa: DAR401
        # noqa: DAR402

        :raises Exception: when configured to fail
        """
        self.calls.append("boot")
        if self.boot_error:
            raise self.boot_error

    def release(self, deployment_status: dict[str, Any]) -> None:
        """Record the call.

        :param deployment_status: deployment outcome
        :type deployment_status: dict[str, Any]
        """
        self.calls.append(f"release:{deployment_status['status']}")


@pytest.fixture(name="make_session")
def make_session_fixture() -> Callable[..., Session]:
    """Return a factory building a Session with a device-free runtime.

    Every session built through this factory is tracked and torn down here:
    ``ConsoleCapture`` is uninstalled and the execution queue is shut down.
    Skipping this teardown leaks a handler onto the global ``pexpect`` and
    ``boardfarm3`` loggers -- whichever session installs its capture second
    snapshots the already-modified ``propagate`` value, so its own later
    ``uninstall()`` restores the wrong value, corrupting an unrelated test
    (e.g. ``test_console.py::test_uninstall_restores_logger_state``)
    depending on collection order.

    :yield: factory taking an optional ``runtime`` override and
        ``RuntimeOptions`` keyword overrides
    :rtype: Callable[..., Session]
    """
    created: list[Session] = []

    def _make(runtime: object | None = None, **overrides: Any) -> Session:
        options = RuntimeOptions(board_name="board", **overrides)
        built = Session(
            "s-test",
            options,
            runtime=runtime if runtime is not None else FakeRuntime(),
        )
        created.append(built)
        return built

    yield _make
    for built in created:
        built.queue.shutdown()
        built.capture.uninstall()
