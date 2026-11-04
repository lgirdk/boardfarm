"""Unit tests for device holds and job tagging on the execution queue."""

from __future__ import annotations

import asyncio
import threading
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.execution import JOB_ID_ATTR, ExecutionQueue, JobState
from boardfarm3.api.holds import ALL, ConsoleHeld, Holds
from boardfarm3.api.session import Session, SessionState
from boardfarm3.templates.cpe import CPE  # noqa: TC001  # resolved at runtime

from .conftest import FakeRuntime
from .test_routers_lan import _FakeRuntimeWithLAN

if TYPE_CHECKING:
    from boardfarm3.api.runtime import RuntimeOptions

LAN_REASON = "device lan held by terminal (user bob)"


def _queue() -> tuple[ExecutionQueue, Holds]:
    holds = Holds()
    return ExecutionQueue(holds=holds), holds


def test_job_on_held_device_refused_at_submit() -> None:
    """A job tagged with a held device is refused and never runs."""
    queue, holds = _queue()
    holds.hold("lan", LAN_REASON)
    called: list[int] = []

    async def go() -> None:
        with pytest.raises(ConsoleHeld, match="held by terminal"):
            await queue.submit(lambda: called.append(1), devices=frozenset({"lan"}))

    asyncio.run(go())
    queue.shutdown()
    assert not called


def test_job_on_other_device_runs() -> None:
    """A hold on one device does not affect a job on another."""
    queue, holds = _queue()
    holds.hold("lan", LAN_REASON)

    async def go() -> Any:
        return await queue.submit(lambda: 1, devices=frozenset({"wan"}))

    job = asyncio.run(go())
    queue.shutdown()
    assert job.state is JobState.DONE


def test_job_queued_before_hold_refused_when_it_starts() -> None:
    """A hold placed while a job waits refuses that job when it would start."""
    queue, holds = _queue()
    release = threading.Event()
    called: list[int] = []

    async def go() -> Any:
        blocker = asyncio.ensure_future(
            queue.submit(release.wait, devices=frozenset({"wan"})),
        )
        await asyncio.sleep(0.1)
        job = await queue.submit(
            lambda: called.append(1),
            mode="async",
            devices=frozenset({"lan"}),
        )
        holds.hold("lan", LAN_REASON)
        release.set()
        await blocker
        await asyncio.sleep(0.2)
        return job

    job = asyncio.run(go())
    queue.shutdown()
    assert not called
    assert job.state is JobState.ERROR
    assert isinstance(job.error, ConsoleHeld)


def test_all_tag_refused_when_any_device_held() -> None:
    """The default ALL tag touches every device, so any hold refuses it."""
    queue, holds = _queue()
    holds.hold("lan", LAN_REASON)

    async def go() -> None:
        with pytest.raises(ConsoleHeld):
            await queue.submit(lambda: 1)

    asyncio.run(go())
    queue.shutdown()


def test_all_hold_refuses_every_device() -> None:
    """Holding ALL refuses a job on any single device."""
    queue, holds = _queue()
    reason = "session held by Python shell (user bob)"
    holds.hold(ALL, reason)

    async def go() -> None:
        with pytest.raises(ConsoleHeld, match="Python shell"):
            await queue.submit(lambda: 1, devices=frozenset({"wan"}))

    asyncio.run(go())
    queue.shutdown()


def test_wait_idle_waits_for_running_job_on_device() -> None:
    """wait_idle stays pending while a job on the device runs."""
    queue, _ = _queue()
    release = threading.Event()

    async def go() -> None:
        running = asyncio.ensure_future(
            queue.submit(release.wait, devices=frozenset({"lan"})),
        )
        await asyncio.sleep(0.1)
        idle = asyncio.ensure_future(queue.wait_idle(frozenset({"lan"})))
        await asyncio.sleep(0.2)
        assert not idle.done()
        release.set()
        await asyncio.wait_for(idle, timeout=1)
        await running

    asyncio.run(go())
    queue.shutdown()


def test_is_held_is_exact_key_check() -> None:
    """is_held(ALL) is True only when ALL itself is held."""
    holds = Holds()
    holds.hold("lan", LAN_REASON)
    assert holds.is_held("lan")
    assert not holds.is_held(ALL)
    holds.hold(ALL, "all")
    assert holds.is_held(ALL)
    assert not holds.is_held("wan")


def test_reason_returns_exact_key_reason() -> None:
    """reason() returns the stored text for that key only."""
    holds = Holds()
    holds.hold("lan", LAN_REASON)
    assert holds.reason("lan") == LAN_REASON
    assert holds.reason("wan") is None
    assert holds.reason(ALL) is None


def test_try_hold_all_succeeds_only_when_nothing_is_held() -> None:
    """try_hold(ALL) takes the hold on an empty registry, else names the conflict."""
    holds = Holds()
    assert holds.try_hold(ALL, "shell") is None
    assert holds.reason(ALL) == "shell"
    assert holds.try_hold(ALL, "second shell") == "shell"
    assert holds.reason(ALL) == "shell"


def test_try_hold_all_refused_while_a_device_is_held() -> None:
    """A device hold makes try_hold(ALL) fail with that device's reason."""
    holds = Holds()
    holds.hold("lan", LAN_REASON)
    assert holds.try_hold(ALL, "shell") == LAN_REASON
    assert not holds.is_held(ALL)


def test_try_hold_device_refused_while_all_is_held() -> None:
    """try_hold(device) fails with the ALL reason and stores nothing."""
    holds = Holds()
    holds.hold(ALL, "shell")
    assert holds.try_hold("lan", LAN_REASON) == "shell"
    assert not holds.is_held("lan")


def test_try_hold_device_allows_re_holding_the_same_device() -> None:
    """Re-holding a device (hand-over) succeeds and re-labels it."""
    holds = Holds()
    assert holds.try_hold("lan", "alice") is None
    assert holds.try_hold("lan", "bob") is None
    assert holds.reason("lan") == "bob"
    assert holds.try_hold("wan", "carol") is None


def test_try_hold_is_atomic_under_contention() -> None:
    """Racing try_hold(ALL) and try_hold(device): never both succeed."""
    for _ in range(200):
        holds = Holds()
        barrier = threading.Barrier(2)
        results: dict[str, str | None] = {}

        def take(
            key: str,
            holds: Holds = holds,
            barrier: Any = barrier,
            results: dict[str, str | None] = results,
        ) -> None:
            barrier.wait()
            results[key] = holds.try_hold(key, key)

        threads = [threading.Thread(target=take, args=(key,)) for key in (ALL, "lan")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert [results[ALL], results["lan"]].count(None) == 1


class _FakeConsole:
    def execute_command(self, command: str) -> str:
        return command


class _FakeDevice:
    def get_interactive_consoles(self) -> dict[str, object]:
        return {"console": _FakeConsole()}


class _NamedDeviceManager:
    def get_device_by_name(self, name: str) -> _FakeDevice:
        del name
        return _FakeDevice()


def test_exec_on_held_device_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /devices/<name>/exec on a held device answers 409."""

    def build(session_id: str, options: RuntimeOptions) -> Session:
        runtime = FakeRuntime()
        runtime.device_manager = _NamedDeviceManager()
        return Session(session_id, options, runtime=runtime)

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        session = application.state.session
        session.runtime.device_manager = _NamedDeviceManager()
        session.state = SessionState.READY
        session.holds.hold("lan", LAN_REASON)
        resp = client.post("/devices/lan/exec", json={"command": "ls"})
    assert resp.status_code == HTTPStatus.CONFLICT
    assert "held by terminal" in resp.json()["detail"]


def test_release_makes_device_runnable_again() -> None:
    """After release() a job on the device runs."""
    queue, holds = _queue()
    holds.hold("lan", LAN_REASON)
    holds.release("lan")

    async def go() -> Any:
        return await queue.submit(lambda: 1, devices=frozenset({"lan"}))

    job = asyncio.run(go())
    queue.shutdown()
    assert job.state is JobState.DONE


def test_wait_idle_returns_at_once_for_other_device() -> None:
    """wait_idle does not wait for a running job on a different device."""
    queue, _ = _queue()
    release = threading.Event()

    async def go() -> None:
        running = asyncio.ensure_future(
            queue.submit(release.wait, devices=frozenset({"wan"})),
        )
        await asyncio.sleep(0.1)
        await asyncio.wait_for(queue.wait_idle(frozenset({"lan"})), timeout=0.2)
        release.set()
        await running

    asyncio.run(go())
    queue.shutdown()


def test_hold_refusal_at_start_names_the_job() -> None:
    """A job refused when it starts carries its job id on the exception."""
    queue, holds = _queue()
    release = threading.Event()

    async def go() -> Any:
        blocker = asyncio.ensure_future(
            queue.submit(release.wait, devices=frozenset({"wan"})),
        )
        await asyncio.sleep(0.1)
        job = await queue.submit(
            lambda: 1,
            mode="async",
            devices=frozenset({"lan"}),
        )
        holds.hold("lan", LAN_REASON)
        release.set()
        await blocker
        await asyncio.sleep(0.2)
        return job

    job = asyncio.run(go())
    queue.shutdown()
    assert getattr(job.error, JOB_ID_ATTR) == job.id


def test_release_runs_while_device_held(make_session: Any) -> None:
    """Session.release() still reaches the runtime while a device is held."""
    runtime = FakeRuntime()
    session = make_session(runtime=runtime)
    session.holds.hold("lan", LAN_REASON)
    asyncio.run(session.release())
    assert any(call.startswith("release:") for call in runtime.calls)


def test_template_route_on_held_device_returns_409_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generated template route answers a held device with 409 and detail."""

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=_FakeRuntimeWithLAN())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}, "options": {}},
        )
        client.post("/session/boot")
        application.state.session.holds.hold("lan", LAN_REASON)
        resp = client.post("/core/templates/lan/ping", json={"ping_ip": "8.8.8.8"})
    assert resp.status_code == HTTPStatus.CONFLICT
    assert resp.json() == {"detail": LAN_REASON}


def test_usecase_route_refused_while_any_device_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A use-case route (tagged ALL) is refused while any device is held."""
    from boardfarm3.use_cases import cpe as uc_cpe

    from .test_routers_usecase import _FakeRuntime

    def _stub_get_cpu_usage(board: CPE) -> float:  # noqa: ARG001
        return 1.0

    _stub_get_cpu_usage.__module__ = uc_cpe.__name__
    monkeypatch.setattr(uc_cpe, "get_cpu_usage", _stub_get_cpu_usage)

    def build(session_id: str, options: RuntimeOptions) -> Session:
        return Session(session_id, options, runtime=_FakeRuntime())

    monkeypatch.setattr(app_module, "build_session", build)
    application = app_module.create_app("s-test", "board-1")
    with TestClient(application) as client:
        client.post(
            "/session/config",
            json={"payload": {"inventory": {}, "env": {}}, "options": {}},
        )
        client.post("/session/boot")
        application.state.session.holds.hold("lan", LAN_REASON)
        resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "board"})
    assert resp.status_code == HTTPStatus.CONFLICT
    assert resp.json() == {"detail": LAN_REASON}
