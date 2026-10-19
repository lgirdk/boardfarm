"""Teardown of sessions that carry a run."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from boardfarm3_control import teardown
from boardfarm3_control.errors import StopPending
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import teardown_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from boardfarm3_control.models import AgentInfo


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.setattr(teardown, "_RUN_POLL_INTERVAL", 0.01)


async def _session(
    mode: str,
) -> tuple[FakeLauncher, AgentInfo, SessionRegistry, BoardLease]:
    launcher = FakeLauncher()
    info = await launcher.start("s-1", "b1", "img", "prplos", mode=mode)
    registry = SessionRegistry()
    registry.add(info)
    lease = BoardLease()
    await lease.acquire("b1", "s-1")
    return launcher, info, registry, lease


def _mock_bundle_and_release(info: AgentInfo) -> None:
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"bundle")
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={"status": "released"})
    )


async def _teardown(
    launcher: FakeLauncher,
    info: AgentInfo,
    registry: SessionRegistry,
    lease: BoardLease,
    *,
    retain: bool,
) -> str:
    async with httpx.AsyncClient() as http:
        return await teardown_session(
            session_id="s-1",
            info=info,
            launcher=launcher,
            registry=registry,
            lease=lease,
            store=DiagnosticsStore(),
            http=http,
            retain=retain,
        )


def _meta() -> dict[str, object]:
    path = DiagnosticsStore().session_dir("s-1") / "meta.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _answers(
    *steps: dict[str, object] | int | Exception,
) -> Callable[[httpx.Request], httpx.Response]:
    """Return a respx side effect that plays one step per call.

    A dict is a 200 JSON reply, an int is a bare status, an exception is raised.
    """
    queue = iter(steps)

    def _answer(_request: httpx.Request) -> httpx.Response:
        step = next(queue)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, int):
            return httpx.Response(step)
        return httpx.Response(200, json=step)

    return _answer


@respx.mock
async def test_a_running_run_is_cancelled_before_the_bundle_is_taken() -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    replies = iter(
        [{"state": "running"}, {"state": "finished", "outcome": "cancelled"}]
    )
    respx.get(f"{info.agent_url}/run").mock(
        side_effect=lambda _request: httpx.Response(200, json=next(replies))
    )
    cancel = respx.post(f"{info.agent_url}/run/cancel").mock(
        return_value=httpx.Response(202, json={"status": "cancelling"})
    )
    assert await _teardown(launcher, info, registry, lease, retain=True) == "retained"
    assert cancel.called
    urls = [str(call.request.url) for call in respx.calls]
    assert urls.index(f"{info.agent_url}/run/cancel") < urls.index(
        f"{info.agent_url}/diagnostics/bundle"
    )
    corpse = registry.get("s-1")
    assert corpse is not None
    assert corpse.run == {"state": "finished", "outcome": "cancelled"}


@respx.mock
async def test_the_final_run_is_kept_in_the_store_after_release() -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    respx.get(f"{info.agent_url}/run").mock(
        return_value=httpx.Response(
            200, json={"state": "finished", "outcome": "passed"}
        )
    )
    assert await _teardown(launcher, info, registry, lease, retain=False) == "released"
    assert registry.get("s-1") is None
    meta = _meta()
    assert meta["mode"] == "pytest"
    assert meta["run"] == {"state": "finished", "outcome": "passed"}


@respx.mock
async def test_an_interact_session_is_never_asked_for_a_run() -> None:
    launcher, info, registry, lease = await _session("interact")
    _mock_bundle_and_release(info)
    run = respx.get(f"{info.agent_url}/run").mock(return_value=httpx.Response(404))
    await _teardown(launcher, info, registry, lease, retain=False)
    assert not run.called
    assert _meta()["run"] is None


@respx.mock
async def test_an_unreachable_agent_does_not_block_teardown() -> None:
    launcher, info, registry, lease = await _session("pytest")
    respx.get(f"{info.agent_url}/run").mock(side_effect=httpx.ConnectError("down"))
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down")
    )
    respx.delete(f"{info.agent_url}/session").mock(
        side_effect=httpx.ConnectError("down")
    )
    assert await _teardown(launcher, info, registry, lease, retain=False) == "released"
    assert _meta()["run"] is None
    assert lease.held_by("b1") is None


@respx.mock
async def test_a_second_pass_keeps_the_run_already_on_the_record() -> None:
    launcher, info, registry, lease = await _session("pytest")
    held = {"state": "finished", "outcome": "passed"}
    info = info.model_copy(update={"run": held})
    registry.add(info)
    respx.get(f"{info.agent_url}/run").mock(side_effect=httpx.ConnectError("down"))
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down")
    )
    respx.delete(f"{info.agent_url}/session").mock(
        side_effect=httpx.ConnectError("down")
    )
    assert await _teardown(launcher, info, registry, lease, retain=True) == "retained"
    assert _meta()["run"] == held
    corpse = registry.get("s-1")
    assert corpse is not None
    assert corpse.run == held


@respx.mock
async def test_a_run_lookup_that_fails_in_any_way_still_releases_the_board(
    caplog: pytest.LogCaptureFixture,
) -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    respx.get(f"{info.agent_url}/run").mock(side_effect=RuntimeError("boom"))
    with caplog.at_level(logging.WARNING):
        status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    assert lease.held_by("b1") is None
    assert _meta()["run"] is None
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert "final run status unavailable for s-1: RuntimeError" in warnings
    assert "boom" not in caplog.text


@respx.mock
async def test_a_run_that_outlives_the_release_timeout_does_not_hold_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_AGENT_RELEASE_TIMEOUT", "1")
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    polls = respx.get(f"{info.agent_url}/run").mock(
        return_value=httpx.Response(200, json={"state": "running"})
    )
    cancel = respx.post(f"{info.agent_url}/run/cancel").mock(
        return_value=httpx.Response(202, json={"status": "cancelling"})
    )
    status = await asyncio.wait_for(
        _teardown(launcher, info, registry, lease, retain=False), timeout=5
    )
    assert status == "released"
    assert cancel.call_count == 1
    assert polls.call_count > 1
    assert _meta()["run"] == {"state": "running"}
    assert lease.held_by("b1") is None


@pytest.mark.parametrize(
    ("raw", "expected"), [("30", 30.0), ("0.5", 0.5), (None, 120.0)]
)
def test_the_release_timeout_is_read_from_the_environment(
    raw: str | None, expected: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    if raw is None:
        monkeypatch.delenv("BOARDFARM_AGENT_RELEASE_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("BOARDFARM_AGENT_RELEASE_TIMEOUT", raw)
    assert teardown._release_seconds() == expected


@pytest.mark.parametrize("raw", ["120s", "", "nan", "inf", "-5", "0"])
@respx.mock
async def test_a_malformed_release_timeout_does_not_strand_the_board(
    raw: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("BOARDFARM_AGENT_RELEASE_TIMEOUT", raw)
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    final = {"state": "finished", "outcome": "passed"}
    respx.get(f"{info.agent_url}/run").mock(
        return_value=httpx.Response(200, json=final)
    )
    with caplog.at_level(logging.WARNING):
        status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    assert lease.held_by("b1") is None
    assert _meta()["run"] == final
    assert "BOARDFARM_AGENT_RELEASE_TIMEOUT" in caplog.text


@respx.mock
async def test_a_pending_stop_keeps_the_corpse_with_its_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    final = {"state": "finished", "outcome": "passed"}
    respx.get(f"{info.agent_url}/run").mock(
        return_value=httpx.Response(200, json=final)
    )

    async def _pending(session_id: str, **_kwargs: object) -> None:
        raise StopPending(session_id, "lab-1")

    monkeypatch.setattr(launcher, "stop", _pending)
    status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "stop_pending"
    corpse = registry.get("s-1")
    assert corpse is not None
    assert corpse.state == "dead"
    assert corpse.stop_pending is True
    assert corpse.run == final
    assert _meta()["run"] == final
    assert lease.held_by("b1") is None


@respx.mock
async def test_a_failed_stop_keeps_the_corpse_with_its_run_and_frees_the_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    final = {"state": "finished", "outcome": "passed"}
    respx.get(f"{info.agent_url}/run").mock(
        return_value=httpx.Response(200, json=final)
    )

    async def _boom(_session_id: str, **_kwargs: object) -> None:
        msg = "docker daemon unreachable"
        raise RuntimeError(msg)

    monkeypatch.setattr(launcher, "stop", _boom)
    status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    corpse = registry.get("s-1")
    assert corpse is not None
    assert corpse.state == "dead"
    assert corpse.stop_pending is False
    assert corpse.run == final
    assert _meta()["run"] == final
    assert lease.held_by("b1") is None


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("down"), 503],
    ids=["an exception", "a non-200 reply"],
)
@respx.mock
async def test_a_failed_poll_does_not_end_the_wait(
    failure: Exception | int,
) -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    final = {"state": "finished", "outcome": "cancelled"}
    polls = respx.get(f"{info.agent_url}/run").mock(
        side_effect=_answers({"state": "running"}, failure, final)
    )
    respx.post(f"{info.agent_url}/run/cancel").mock(
        return_value=httpx.Response(202, json={"status": "cancelling"})
    )
    status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    assert polls.call_count == 3
    assert _meta()["run"] == final


@respx.mock
async def test_three_failed_polls_in_a_row_end_the_wait() -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    last_good = {"state": "running", "current_test": "test_a"}
    polls = respx.get(f"{info.agent_url}/run").mock(
        side_effect=_answers(
            last_good,
            503,
            httpx.ConnectError("down"),
            500,
            {"state": "finished", "outcome": "cancelled"},
        )
    )
    respx.post(f"{info.agent_url}/run/cancel").mock(
        return_value=httpx.Response(202, json={"status": "cancelling"})
    )
    status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    assert polls.call_count == 4  # the first lookup, then the three failed polls
    assert _meta()["run"] == last_good
    assert lease.held_by("b1") is None


@respx.mock
async def test_failed_polls_are_counted_in_a_row_not_in_total() -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    running = {"state": "running"}
    final = {"state": "finished", "outcome": "cancelled"}
    polls = respx.get(f"{info.agent_url}/run").mock(
        side_effect=_answers(running, 503, running, 503, 503, final)
    )
    respx.post(f"{info.agent_url}/run/cancel").mock(
        return_value=httpx.Response(202, json={"status": "cancelling"})
    )
    await _teardown(launcher, info, registry, lease, retain=False)
    assert polls.call_count == 6
    assert _meta()["run"] == final


@respx.mock
async def test_a_run_reply_that_is_not_200_is_logged_with_its_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    launcher, info, registry, lease = await _session("pytest")
    _mock_bundle_and_release(info)
    respx.get(f"{info.agent_url}/run").mock(return_value=httpx.Response(503))
    with caplog.at_level(logging.INFO):
        status = await _teardown(launcher, info, registry, lease, retain=False)
    assert status == "released"
    assert _meta()["run"] is None
    infos = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.INFO and record.name == teardown.__name__
    ]
    assert any("s-1" in message and "503" in message for message in infos)
