"""Teardown of sessions that carry a run."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from boardfarm3_control import teardown
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import teardown_session

if TYPE_CHECKING:
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
