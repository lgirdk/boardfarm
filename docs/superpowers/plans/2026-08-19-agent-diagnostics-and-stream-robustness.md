# Agent Diagnostics and Stream Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a failed, wedged, or crashed boardfarm agent debuggable, and stop the control plane proxy from severing operations that take longer than five seconds.

**Architecture:** Three layers, in dependency order. The proxy stops imposing a timeout ceiling and the agent's SSE stream emits keepalives (Phase 1). The agent gains always-on console logs, Python tracebacks in every error path, a `/diagnostics/bundle` tar.gz endpoint, thread-stack sampling, and a reversible `quiet` liveness signal that replaces the wall-clock `STUCK` state (Phase 2). The control plane stops removing failed containers, gains `purge`/`capture_logs`/`capture_files` on the `Launcher` protocol, archives bundles to a local store before every teardown, and serves them through a three-tier `/diagnostics` endpoint (Phase 3). An integration test closes the loop (Phase 4).

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, pluggy, pexpect, docker-py, pytest + pytest-asyncio + respx.

**Spec:** `docs/superpowers/specs/2026-08-19-agent-diagnostics-and-stream-robustness-design.md`

## Global Constraints

- **Two packages, two floors.** `boardfarm3/` must stay valid on Python 3.11–3.13. `boardfarm3_control/` requires >=3.11. Never import `boardfarm3_control` from `boardfarm3`.
- **Lint gate is four tools, all must pass:** `nox -s lint` runs ruff format check, `ruff check` (`select = ["ALL"]`), flake8 (max line length 88, max complexity 10), and `mypy --disallow-untyped-defs`. Do not relax `disallow_untyped_defs`. `nox -s pylint` must also pass.
- **Docstrings are enforced.** Sphinx style, checked by darglint2 over `boardfarm3`. Every public function needs `:param:`/`:type:`/`:return:`/`:rtype:`, and `:raises:` where it raises.
- **Conventional Commits**, enforced by commitizen at commit-msg time: `<type>(<scope>): <subject>`.
- **Layer discipline.** Devices contain no business logic. Nothing in this plan may add a method to a Template ABC or to a concrete device class.
- **No auto-termination.** Nothing added by this plan may stop, kill, or tear down a *live* session. The reaper (Task 20) operates only on containers that are already stopped. No code may branch on the `quiet` liveness signal.
- **Redaction is mandatory** on `session.json` and `config.json` in the bundle. Console transcripts are deliberately *not* redacted.
- Tests live in `unittests/` (agent: `unittests/api/`, control: `unittests/control/`). Async tests need an explicit `@pytest.mark.asyncio`. Control plane tests never touch a Docker daemon — use `FakeLauncher` and `respx`.

---

## Scope Note

The spec covers two packages, but they are **not** independent subsystems: the control plane's diagnostics endpoint consumes the agent's `/diagnostics/bundle`. That is a one-way dependency, so this is one project delivered in phases rather than two projects. Phase 1 is deliberately first because it is the highest-value, lowest-risk fix and depends on nothing.

---

## File Structure

**New files:**

| File | Responsibility |
|---|---|
| `boardfarm3/api/diagnostics.py` | Thread-stack snapshot. Pure function + no I/O, so the bundle and the route share one implementation. |
| `boardfarm3/api/redact.py` | Recursive secret redaction for dicts/lists. Standalone so it is trivially testable. |
| `boardfarm3/api/bundle.py` | Assembles the diagnostics tar.gz. Owns member layout and the manifest. |
| `boardfarm3/api/logs.py` | Installs the `agent.log` rotating file handler and resolves the artifact directory. |
| `boardfarm3_control/store.py` | On-disk diagnostics store: `meta.json`, `bundle.tar.gz`, listing, sizing, deletion. |
| `boardfarm3_control/reaper.py` | Background corpse/bundle reaper. Isolated so it can be unit-tested without an app. |
| `boardfarm3_control/teardown.py` | The single teardown sequence used by `DELETE` and by every `POST /sessions` unwind. |
| `unittests/api/test_diagnostics.py` | Thread snapshot, redaction, bundle. |
| `unittests/api/test_liveness.py` | `quiet` signal behaviour. |
| `unittests/control/test_store.py` | Store layout, sizing, eviction. |
| `unittests/control/test_teardown.py` | The teardown matrix. |
| `unittests/control/test_reaper.py` | TTL and size-cap eviction. |
| `unittests/control/test_diagnostics_routes.py` | Three-tier resolution and snapshot. |

**Modified files:** `boardfarm3/api/{app,console,errors,execution,runtime,session,__main__}.py`, `boardfarm3_control/{app,launcher,models,proxy,registry}.py`, and the existing tests that assert removed behaviour.

**Two similarly-named functions, deliberately distinct — do not confuse them:**

| Symbol | Signature | Meaning |
|---|---|---|
| `boardfarm3.api.bundle.write_bundle` | `(session, dest: Path) -> dict` | **Agent side.** Builds the tar.gz from a live session and returns its manifest. |
| `DiagnosticsStore.write_bundle` | `(session_id: str, chunks: Iterable[bytes]) -> int` | **Control side.** Persists already-built bytes to the store and returns the byte count. |

They live in different packages and take different argument shapes, so a mix-up fails immediately at the call site rather than silently.

`teardown.py` and `reaper.py` are split out of `app.py` deliberately — `boardfarm3_control/app.py:create_app()` already carries `# noqa: C901, PLR0915` for complexity, and adding the teardown sequence plus a reaper inline would push it past what flake8's complexity gate allows.

---

# Phase 1 — Stream robustness

### Task 1: Proxy timeouts and connection pooling

**Files:**
- Modify: `boardfarm3_control/proxy.py:41-109`
- Modify: `boardfarm3_control/app.py:34-36` (`_STATE_TIMEOUT`), `boardfarm3_control/app.py:63-71` (lifespan), `boardfarm3_control/app.py:264-276` (proxy route)
- Test: `unittests/control/test_proxy.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `boardfarm3_control.proxy.is_streaming_path(path: str) -> bool`; `proxy_request(request, agent_url, path, body=None, client=None, session_id="")` — `client: httpx.AsyncClient | None`, `session_id: str`. When `client` is provided the caller owns closing it.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/control/test_proxy.py`:

```python
import pytest

from boardfarm3_control.proxy import is_streaming_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("console/stream", True),
        ("/console/stream/", True),
        ("diagnostics", True),
        ("diagnostics/bundle", True),
        ("session", False),
        ("jobs/j-1a2b", False),
        ("use-cases/networking/ping", False),
    ],
)
def test_is_streaming_path(path: str, expected: bool) -> None:
    assert is_streaming_path(path) is expected


@respx.mock
def test_streaming_path_gets_unbounded_read_timeout() -> None:
    captured: dict[str, object] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured["timeout"] = req.extensions.get("timeout")
        return httpx.Response(200, text="data: hi\n\n")

    respx.get("http://fake-agent/console/stream").mock(side_effect=capture)
    _client.get("/proxy-test/console/stream")
    assert captured["timeout"]["read"] is None


@respx.mock
def test_non_streaming_path_gets_long_read_timeout() -> None:
    captured: dict[str, object] = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured["timeout"] = req.extensions.get("timeout")
        return httpx.Response(200, json={})

    respx.get("http://fake-agent/session").mock(side_effect=capture)
    _client.get("/proxy-test/session")
    assert captured["timeout"]["read"] == 1800.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_proxy.py -v -p no:randomly`
Expected: FAIL — `ImportError: cannot import name 'is_streaming_path'`.

- [ ] **Step 3: Implement**

In `boardfarm3_control/proxy.py`, add imports (`import logging`, `import os`) and a module logger `_log = logging.getLogger(__name__)`, then:

```python
def is_streaming_path(path: str) -> bool:
    """Report whether *path* names a long-lived streaming endpoint.

    Streaming endpoints must not carry a read timeout: an SSE console stream
    is legitimately idle for minutes, and a bounded read severs it.

    :param path: sub-path being proxied, e.g. ``"console/stream"``
    :type path: str
    :return: True when the response is expected to stream
    :rtype: bool
    """
    clean = path.split("?", 1)[0].strip("/")
    return (
        clean.endswith("stream")
        or clean == "diagnostics"
        or clean.startswith("diagnostics/")
    )


def _timeout_for(path: str) -> httpx.Timeout:
    """Build the httpx timeout appropriate for *path*.

    :param path: sub-path being proxied
    :type path: str
    :return: timeout configuration
    :rtype: httpx.Timeout
    """
    connect = float(os.environ.get("BOARDFARM_PROXY_CONNECT_TIMEOUT", "10"))
    read = None if is_streaming_path(path) else float(
        os.environ.get("BOARDFARM_PROXY_READ_TIMEOUT", "1800"),
    )
    return httpx.Timeout(connect=connect, read=read, write=30.0, pool=10.0)
```

Change the signature and client handling in `proxy_request`:

```python
async def proxy_request(  # noqa: PLR0913
    request: Request,
    agent_url: str,
    path: str,
    body: bytes | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str = "",
) -> StreamingResponse:
```

Add to the docstring:

```
    :param client: pooled client to use; a per-request client is created when None
    :type client: httpx.AsyncClient | None
    :param session_id: session this request belongs to, used in error frames
    :type session_id: str
```

Replace `client = httpx.AsyncClient()` with:

```python
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient()
```

Pass the timeout into `build_request`:

```python
        upstream_request = client.build_request(
            method=request.method,
            url=url,
            headers=forwarded_headers,
            content=raw,
            timeout=_timeout_for(path),
        )
```

Guard both `aclose()` calls so a pooled client is never closed — in the `except` block:

```python
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        if owns_client:
            await client.aclose()
        raise HTTPException(status_code=502, detail="agent unreachable") from exc
```

and in `generate()`'s `finally`:

```python
        finally:
            await response.aclose()
            if owns_client:
                await client.aclose()
```

In `boardfarm3_control/app.py`, make the fan-out timeout tunable — replace the `_STATE_TIMEOUT = 0.5` constant:

```python
_STATE_TIMEOUT = float(os.environ.get("BOARDFARM_STATE_TIMEOUT", "2.0"))
```

adding `import os` at the top. Create the pooled client in the lifespan, before `yield`:

```python
        app.state.http = httpx.AsyncClient()
```

and after `yield`, before the existing loop body is removed in Task 15:

```python
        await app.state.http.aclose()
```

Pass it from the catch-all proxy route:

```python
        return await proxy_request(
            request,
            info.agent_url,
            path,
            client=request.app.state.http,
            session_id=session_id,
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS. All pre-existing proxy tests still pass — `client` and `session_id` both default, so the existing call sites are unchanged.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/proxy.py boardfarm3_control/app.py unittests/control/test_proxy.py
git commit -m "fix(proxy): replace 5s default timeouts with per-request policy

Streaming paths get an unbounded read timeout; everything else gets 1800s,
both tunable via BOARDFARM_PROXY_*_TIMEOUT. Adds a pooled client owned by
the app lifespan and raises the GET /sessions fan-out timeout to 2s.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 2: Stream interruptions stop being silent

**Files:**
- Modify: `boardfarm3_control/proxy.py:92-102` (`generate()`)
- Test: `unittests/control/test_proxy.py`

**Interfaces:**
- Consumes: `proxy_request(..., session_id=...)` from Task 1.
- Produces: an `event: error` SSE frame on mid-flight transport failure.

- [ ] **Step 1: Write the failing test**

Append to `unittests/control/test_proxy.py`:

Add this helper near the top of the file, below the imports:

```python
class _Gen(httpx.SyncByteStream):
    """Wrap a byte generator as an httpx stream, for respx responses."""

    def __init__(self, gen: object) -> None:
        self._gen = gen

    def __iter__(self) -> object:
        return iter(self._gen)
```

Then append the route and the test:

```python
@_proxy_app.get("/sse-test/{path:path}")
async def _sse_route(path: str, request: Request) -> object:
    return await proxy_request(
        request, "http://fake-agent", path, session_id="s-4f2a",
    )


@respx.mock
def test_sse_stream_interruption_emits_error_frame() -> None:
    """A mid-flight transport error must be visible, not a clean EOF."""

    def broken_stream() -> object:
        yield b"data: one\n\n"
        msg = "connection reset"
        raise httpx.ReadError(msg)

    respx.get("http://fake-agent/console/stream").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Gen(broken_stream()),
        ),
    )
    resp = _client.get("/sse-test/console/stream")
    body = resp.text
    assert "data: one" in body
    assert "event: error" in body
    assert "StreamInterrupted" in body
    assert "s-4f2a" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/control/test_proxy.py::test_sse_stream_interruption_emits_error_frame -v -p no:randomly`
Expected: FAIL — the body contains `data: one` but no `event: error`, because the error is swallowed.

- [ ] **Step 3: Implement**

Add `import json` to `boardfarm3_control/proxy.py`, then replace `generate()`:

```python
    is_sse = "text/event-stream" in (response.headers.get("content-type") or "")

    async def generate() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        except httpx.TransportError as exc:
            # Response headers were already sent, so an HTTPException is
            # impossible here. Log it, and for SSE tell the client the stream
            # broke rather than letting it look like a clean end of stream.
            _log.warning(
                "proxy stream interrupted: %s %s: %s", request.method, url, exc,
            )
            if is_sse:
                payload = json.dumps(
                    {
                        "error": "StreamInterrupted",
                        "message": str(exc),
                        "session_id": session_id,
                    },
                )
                yield f"event: error\ndata: {payload}\n\n".encode()
        finally:
            await response.aclose()
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/proxy.py unittests/control/test_proxy.py
git commit -m "fix(proxy): surface mid-flight stream interruptions

A TransportError during streaming was silently swallowed, so a broken SSE
stream was indistinguishable from a finished one. It is now logged, and SSE
responses receive a final event: error frame.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 3: Agent SSE keepalive

**Files:**
- Modify: `boardfarm3/api/app.py:281-309` (`console_stream`)
- Test: `unittests/api/test_app.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `: keepalive\n\n` comment frames on the agent's `/console/stream`, plus `X-Accel-Buffering: no`.

- [ ] **Step 1: Write the failing test**

Append to `unittests/api/test_app.py`:

```python
def test_console_stream_emits_keepalive_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quiet console must still produce traffic, or proxies time it out."""
    monkeypatch.setenv("BOARDFARM_SSE_KEEPALIVE", "0")
    app = app_module.create_app("s-test", "board")
    with TestClient(app) as client, client.stream(
        "GET", "/console/stream",
    ) as response:
        assert response.headers["x-accel-buffering"] == "no"
        for line in response.iter_lines():
            if line.startswith(": keepalive"):
                break
        else:  # pragma: no cover - only on failure
            pytest.fail("no keepalive frame received")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/api/test_app.py::test_console_stream_emits_keepalive_when_idle -v -p no:randomly`
Expected: FAIL — `KeyError: 'x-accel-buffering'`.

- [ ] **Step 3: Implement**

Add `import os` and `import time` to `boardfarm3/api/app.py` if absent, then rewrite the body of `console_stream`:

```python
    @app.get("/console/stream")
    async def console_stream(
        request: Request,
        device: str | None = None,
        cursor: int = 0,
    ) -> StreamingResponse:
        keepalive = float(os.environ.get("BOARDFARM_SSE_KEEPALIVE", "15"))

        async def events() -> AsyncIterator[str]:
            buf = session().buffer
            last_sent = time.monotonic()
            async with buf.subscription() as queue:
                live_from = buf.next_seq
                past, _ = buf.read(cursor=cursor, limit=50_000, device=device)
                for event in past:
                    if event.seq < live_from:
                        yield f"data: {json.dumps(event.__dict__)}\n\n"
                        last_sent = time.monotonic()
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        # A quiet console must still produce bytes, or an
                        # intermediate proxy will treat the stream as dead.
                        if time.monotonic() - last_sent >= keepalive:
                            yield ": keepalive\n\n"
                            last_sent = time.monotonic()
                        continue
                    if device is not None and event.device != device:
                        continue
                    yield f"data: {json.dumps(event.__dict__)}\n\n"
                    last_sent = time.monotonic()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/app.py unittests/api/test_app.py
git commit -m "feat(api): emit SSE keepalives on a quiet console stream

An idle console produced no bytes, so any proxy read timeout severed the
stream. Emits a comment frame every BOARDFARM_SSE_KEEPALIVE seconds
(default 15) and disables intermediate buffering.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

# Phase 2 — Agent diagnostics

### Task 4: Always-on console logs

**Files:**
- Create: `boardfarm3/api/logs.py`
- Modify: `boardfarm3/api/runtime.py:23-33` (`RuntimeOptions`), `boardfarm3/api/session.py:86-92` (`configure`), `boardfarm3/api/app.py:133-142` (lifespan)
- Test: `unittests/api/test_runtime.py`, `unittests/api/test_session.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `boardfarm3.api.logs.artifact_dir(session_id: str) -> Path` — returns `<root>/{session_id}`, where root is `$BOARDFARM_ARTIFACT_DIR`, else `/var/log/boardfarm` when writable, else `<tempdir>/boardfarm`. Does **not** create the directory.

**Why the fallback is load-bearing:** turning console logs on unconditionally means `BoardfarmPexpect._configure_logging()` will now call `logs_directory.mkdir(parents=True, exist_ok=True)` on **every** connection. Under `DockerLauncher` the agent is root and `/var/log/boardfarm` is fine, but under `ProcessLauncher` — local development and the whole of `integrationtests/control/` — the agent runs as an unprivileged user and that `mkdir` raises `PermissionError`, crashing every device connection. A hardcoded `/var/log` default would turn an always-on convenience into a total outage for non-root agents.

- [ ] **Step 1: Write the failing tests**

Create `unittests/api/test_logs.py`:

```python
"""Unit tests for agent artifact-directory resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from boardfarm3.api import logs
from boardfarm3.api.logs import artifact_dir


def test_artifact_dir_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", "/tmp/bf")
    assert artifact_dir("s-4f2a") == Path("/tmp/bf/s-4f2a")


def test_artifact_dir_uses_var_log_when_writable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOARDFARM_ARTIFACT_DIR", raising=False)
    monkeypatch.setattr(logs.os, "access", lambda *_: True)
    assert artifact_dir("s-4f2a") == Path("/var/log/boardfarm/s-4f2a")


def test_artifact_dir_falls_back_when_var_log_is_unwritable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-root agent must not crash every device connection on mkdir."""
    monkeypatch.delenv("BOARDFARM_ARTIFACT_DIR", raising=False)
    monkeypatch.setattr(logs.os, "access", lambda *_: False)
    expected = Path(tempfile.gettempdir()) / "boardfarm" / "s-4f2a"
    assert artifact_dir("s-4f2a") == expected


def test_artifact_dir_does_not_create_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    assert not artifact_dir("s-4f2a").exists()
```

Append to `unittests/api/test_session.py`:

```python
@pytest.mark.asyncio
async def test_empty_save_console_logs_override_keeps_the_default(
    session: Session,
) -> None:
    """An empty override must not disable always-on console logging.

    :param session: session under test
    :type session: Session
    """
    session.options.save_console_logs = "/var/log/boardfarm/s-test"
    await session.configure({"inventory": {}, "env": {}}, {"save_console_logs": ""})
    assert session.options.save_console_logs == "/var/log/boardfarm/s-test"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_logs.py unittests/api/test_session.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3.api.logs`, and the override test fails because `configure()` sets it to `""`.

- [ ] **Step 3: Implement**

Create `boardfarm3/api/logs.py`:

```python
"""Artifact directory resolution and agent log file installation."""

from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_ROOT = "/var/log/boardfarm"
_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUPS = 3
_ATTACH_TO = ("boardfarm3", "uvicorn", "uvicorn.error", "uvicorn.access")

_log = logging.getLogger(__name__)


def _root() -> Path:
    """Return the artifact root, falling back when the default is unwritable.

    Console logging is unconditional, so device connections will ``mkdir``
    under this root on every connect. A non-root agent (ProcessLauncher, local
    development, integration tests) cannot write to ``/var/log``, and letting
    that raise would crash every device connection.

    :return: writable artifact root
    :rtype: Path
    """
    explicit = os.environ.get("BOARDFARM_ARTIFACT_DIR")
    if explicit:
        return Path(explicit)
    default = Path(_DEFAULT_ROOT)
    probe = default if default.exists() else default.parent
    if os.access(probe, os.W_OK):
        return default
    return Path(tempfile.gettempdir()) / "boardfarm"


def artifact_dir(session_id: str) -> Path:
    """Return the artifact directory for a session.

    The directory is not created — device connections create it lazily when
    they attach their own console log handlers.

    :param session_id: session identifier
    :type session_id: str
    :return: per-session artifact directory
    :rtype: Path
    """
    return _root() / session_id


def install_agent_log(session_id: str) -> Path | None:
    """Attach a rotating file handler capturing framework and uvicorn logs.

    Best-effort: an unwritable artifact directory is logged and ignored rather
    than preventing the agent from starting.

    :param session_id: session identifier
    :type session_id: str
    :return: path of the log file, or None when it could not be created
    :rtype: Path | None
    """
    directory = artifact_dir(session_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "agent.log",
            maxBytes=_LOG_BYTES,
            backupCount=_LOG_BACKUPS,
            encoding="utf-8",
        )
    except OSError as exc:
        _log.warning("could not open agent log in %s: %s", directory, exc)
        return None
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )
    for name in _ATTACH_TO:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return directory / "agent.log"
```

In `boardfarm3/api/app.py`, import it and set the default in the lifespan:

```python
from boardfarm3.api.logs import artifact_dir
```

```python
        session = build_session(
            session_id,
            RuntimeOptions(
                board_name=board_name,
                # console/ subdirectory, so agent.log sits beside it at the
                # artifact root rather than inside the console-logs archive
                # member (Task 12 relies on this layout).
                save_console_logs=str(artifact_dir(session_id) / "console"),
            ),
        )
```

Resulting layout:

```
<artifact root>/{session_id}/
    agent.log        framework + uvicorn logs (Task 5)
    console/         per-device console transcripts (RotatingFileHandler)
```

In `boardfarm3/api/session.py:86-92`, make an empty override a no-op:

```python
        for field_name, value in (options or {}).items():
            if field_name == "save_console_logs" and not value:
                # Console logging is always on: an empty override redirects
                # nothing, it must not disable it.
                continue
            if field_name == "plugin_args":
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/logs.py boardfarm3/api/app.py boardfarm3/api/session.py unittests/api/test_logs.py unittests/api/test_session.py
git commit -m "feat(api): make console logs always-on

save_console_logs now defaults to \$BOARDFARM_ARTIFACT_DIR/{session_id} and
an empty override no longer disables it, so every session writes console
files and GET /console/archive stops returning 404.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 5: Install the agent log at process start

**Files:**
- Modify: `boardfarm3/api/__main__.py:16-29` (`build_app_from_env`)
- Test: `unittests/api/test_entrypoint.py`

**Interfaces:**
- Consumes: `install_agent_log(session_id) -> Path | None` from Task 4.
- Produces: `agent.log` present in the artifact directory of a running agent.

Installed in `__main__`, **not** `create_app()`, so the hundreds of unit tests that build apps do not write to `/var/log`.

- [ ] **Step 1: Write the failing test**

Append to `unittests/api/test_entrypoint.py`:

```python
def test_build_app_from_env_installs_agent_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A production agent must have an on-disk log before anything can fail."""
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDFARM_BOARD_NAME", "board")
    monkeypatch.setenv("BOARDFARM_SESSION_ID", "s-4f2a")
    from boardfarm3.api.__main__ import build_app_from_env

    build_app_from_env()
    assert (tmp_path / "s-4f2a" / "agent.log").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/api/test_entrypoint.py::test_build_app_from_env_installs_agent_log -v -p no:randomly`
Expected: FAIL — `agent.log` does not exist.

- [ ] **Step 3: Implement**

In `boardfarm3/api/__main__.py`, import and call it:

```python
from boardfarm3.api.logs import install_agent_log
```

In `build_app_from_env()`, after resolving `session_id` and before `create_app`:

```python
    install_agent_log(session_id)
    return create_app(session_id, board_name)
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/__main__.py unittests/api/test_entrypoint.py
git commit -m "feat(api): write framework and uvicorn logs to agent.log

Installed at process start rather than in create_app(), so unit tests that
build apps do not write to the artifact directory.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 6: Tracebacks in the error envelope

**Files:**
- Modify: `boardfarm3/api/errors.py:50-100`
- Test: `unittests/api/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `error_envelope()` returns an extra key `traceback: list[str]`. `console_tail_from()` no longer filters to `stream="console"`.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/api/test_errors.py`:

```python
def test_error_envelope_carries_a_traceback() -> None:
    """An error with no traceback is not debuggable."""
    try:
        msg = "boom"
        raise ValueError(msg)
    except ValueError as exc:
        envelope = error_envelope(exc, session_id="s-1")
    assert envelope["error"] == "ValueError"
    assert any("ValueError: boom" in frame for frame in envelope["traceback"])
    assert any("test_error_envelope_carries" in frame for frame in envelope["traceback"])


def test_error_envelope_traceback_includes_the_cause_chain() -> None:
    """A chained exception must show both frames, not just the outermost."""
    try:
        try:
            msg = "inner"
            raise ValueError(msg)
        except ValueError as inner:
            msg = "outer"
            raise RuntimeError(msg) from inner
    except RuntimeError as exc:
        envelope = error_envelope(exc, session_id="s-1")
    joined = "".join(envelope["traceback"])
    assert "ValueError: inner" in joined
    assert "RuntimeError: outer" in joined


def test_console_tail_includes_framework_lines() -> None:
    """Framework output is where Python errors surface; it must be in the tail."""
    from boardfarm3.api.console import EventBuffer

    buffer = EventBuffer()
    buffer.append(stream="console", device="board", job_id="j-1", line="console line")
    buffer.append(stream="framework", device=None, job_id="j-1", line="framework line")
    tail = console_tail_from(buffer, "j-1")
    assert "console line" in tail
    assert "framework line" in tail
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_errors.py -v -p no:randomly`
Expected: FAIL — `KeyError: 'traceback'`, and the framework line is missing from the tail.

- [ ] **Step 3: Implement**

In `boardfarm3/api/errors.py`, add `import traceback as _traceback` at the top. In `error_envelope()`, add to the docstring `:return:` description and to the returned dict:

```python
    return {
        "error": type(exc).__name__,
        "message": str(exc),
        "device": device,
        "session_id": session_id,
        "job_id": job_id,
        "console_tail": console_tail,
        "traceback": _traceback.format_exception(exc),
    }
```

In `console_tail_from()`, drop the stream filter:

```python
    events, _ = buffer.read(job_id=job_id, limit=1_000_000)
```

and update its docstring summary to "Return the most recent console and framework lines produced during a job."

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/errors.py unittests/api/test_errors.py
git commit -m "feat(api): carry Python tracebacks in the error envelope

format_exception() walks the __cause__/__context__ chain, so a chained
failure now reports both frames. console_tail stops excluding framework
output, which is where Python errors surface.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 7: ConsoleCapture preserves exc_info

**Files:**
- Modify: `boardfarm3/api/console.py:181-201` (`emit`)
- Test: `unittests/api/test_console.py`

**Interfaces:**
- Consumes: nothing.
- Produces: buffer lines carry the formatted traceback when a record has `exc_info`.

- [ ] **Step 1: Write the failing test**

Append to `unittests/api/test_console.py`:

```python
def test_capture_preserves_exception_tracebacks() -> None:
    """record.getMessage() drops exc_info, which loses every traceback."""
    buffer = EventBuffer()
    capture = ConsoleCapture(buffer)
    capture.install()
    try:
        logger = logging.getLogger("boardfarm3.test")
        try:
            msg = "kaboom"
            raise ValueError(msg)
        except ValueError:
            logger.exception("job failed")
    finally:
        capture.uninstall()

    events, _ = buffer.read()
    joined = "\n".join(event.line for event in events)
    assert "job failed" in joined
    assert "ValueError: kaboom" in joined
    assert "Traceback" in joined
```

Ensure `import logging` and the `ConsoleCapture`/`EventBuffer` imports exist at the top of that file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/api/test_console.py::test_capture_preserves_exception_tracebacks -v -p no:randomly`
Expected: FAIL — `assert "ValueError: kaboom" in joined`.

- [ ] **Step 3: Implement**

In `boardfarm3/api/console.py`, add `import traceback` at the top, then in `emit()` replace the `self._buffer.append(...)` call:

```python
        line = record.getMessage()
        if record.exc_info:
            # getMessage() drops exc_info entirely, which is how every
            # traceback was being lost on the way into the buffer.
            line = f"{line}\n{''.join(traceback.format_exception(*record.exc_info))}"
        self._buffer.append(
            stream=stream,
            device=device,
            job_id=current_job_id.get(),
            line=line,
        )
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/console.py unittests/api/test_console.py
git commit -m "fix(api): preserve exc_info when capturing log records

ConsoleCapture.emit() used record.getMessage(), which discards exc_info, so
correctly-logged exceptions reached the buffer with no traceback.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 8: Every job failure is logged, and jobs are enumerable

**Files:**
- Modify: `boardfarm3/api/execution.py:75-107` (`_run`), add `all_jobs()`
- Test: `unittests/api/test_execution.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ExecutionQueue.all_jobs() -> list[Job]` — every retained job, oldest first. Task 12 uses it for `jobs.json`.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/api/test_execution.py`:

```python
@pytest.mark.asyncio
async def test_job_failure_is_logged_with_a_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every job failure must be logged, not only boot.

    :param caplog: pytest log capture fixture
    :type caplog: pytest.LogCaptureFixture
    """
    queue = ExecutionQueue()

    def boom() -> None:
        msg = "kaboom"
        raise ValueError(msg)

    with caplog.at_level(logging.DEBUG, logger="boardfarm3.api.execution"):
        await queue.submit(boom, mode="async")
        await asyncio.sleep(0.2)

    assert any(record.exc_info for record in caplog.records)
    assert "kaboom" in caplog.text
    queue.shutdown()


@pytest.mark.asyncio
async def test_all_jobs_returns_every_retained_job() -> None:
    """The bundle needs to enumerate jobs without touching private state."""
    queue = ExecutionQueue()
    await queue.submit(lambda: 1, mode="sync")
    await queue.submit(lambda: 2, mode="sync")
    jobs = queue.all_jobs()
    assert len(jobs) == 2
    assert [job.result for job in jobs] == [1, 2]
    queue.shutdown()
```

Ensure `import asyncio`, `import logging`, and `import pytest` are present in that file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_execution.py -v -p no:randomly`
Expected: FAIL — no record carries `exc_info`, and `AttributeError: 'ExecutionQueue' object has no attribute 'all_jobs'`.

- [ ] **Step 3: Implement**

In `boardfarm3/api/execution.py`, add `import logging` and `_log = logging.getLogger(__name__)` below the imports. In `_run()`'s except block, log before re-raising:

```python
        except BaseException as exc:
            job.state = JobState.ERROR
            job.error = exc
            job.finished_at = time.time()
            # Logged here so *every* job failure carries a traceback, not just
            # boot. current_job_id is still set, so ConsoleCapture attributes
            # the traceback to this job.
            _log.exception("job %s failed", job.id)
            raise
```

Add the accessor:

```python
    def all_jobs(self) -> list[Job]:
        """Return every retained job, oldest first.

        :return: retained jobs in submission order
        :rtype: list[Job]
        """
        return list(self._jobs.values())
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/execution.py unittests/api/test_execution.py
git commit -m "feat(api): log every job failure with a traceback

Only boot recorded an error envelope; every other job failure vanished.
Adds all_jobs() so diagnostics can enumerate jobs without private access.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 9: Replace STUCK with a reversible liveness signal

**Files:**
- Modify: `boardfarm3/api/console.py:34-80` (`EventBuffer`), `boardfarm3/api/session.py:19-28,34-65,142-173`, `boardfarm3/api/runtime.py:23-33`, `boardfarm3/api/app.py:41-48` (`ConfigOptions`)
- Test: `unittests/api/test_liveness.py` (new), `unittests/api/test_session.py:184-196` (replace)

**Interfaces:**
- Consumes: nothing.
- Produces: `EventBuffer.last_event_ts -> float`, `EventBuffer.last_line -> str | None`; `Session.liveness() -> dict[str, Any]` with keys `quiet`, `running_for`, `idle_for`, `last_line`, `last_event_ts`; `status()["liveness"]`. `SessionState.STUCK`, `Session.is_stuck()`, and `Session.stuck_after` are **removed**. `RuntimeOptions.quiet_after: float = 600.0` and `ConfigOptions.quiet_after: float | None = None` are added.

- [ ] **Step 1: Write the failing tests**

Create `unittests/api/test_liveness.py`:

```python
"""Liveness reporting: quiet is evidence, never a verdict."""

from __future__ import annotations

import asyncio
import time

import pytest

from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session, SessionState


class _FakeRuntime:
    """RuntimeContext stand-in that touches no devices."""

    def __init__(self) -> None:
        self.config: object | None = None
        self.device_manager: object | None = None

    def refresh_cmdline_args(self) -> None:
        """Re-materialise options. No-op for the fake."""

    def resolve(self, payload: dict[str, object]) -> object:  # noqa: ARG002
        """Resolve the payload.

        :param payload: opaque payload
        :type payload: dict[str, object]
        :return: placeholder config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Register devices.

        :return: placeholder device manager
        :rtype: object
        """
        self.device_manager = object()
        return self.device_manager


def _session() -> Session:
    options = RuntimeOptions(board_name="board", quiet_after=0.1)
    return Session("s-test", options, runtime=_FakeRuntime())


@pytest.mark.asyncio
async def test_idle_job_reports_quiet_without_changing_state() -> None:
    """A silent job must not destroy the real lifecycle state."""
    session = _session()
    await session.configure({"inventory": {}, "env": {}})
    await session.queue.submit(lambda: time.sleep(0.5), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.3)
    status = session.status()
    assert status["state"] == SessionState.CONFIGURED.value
    assert status["liveness"]["quiet"] is True
    assert status["liveness"]["running_for"] > 0
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_chatty_job_is_never_quiet() -> None:
    """A slow-but-chatty job is healthy and must not be flagged."""
    session = _session()
    await session.configure({"inventory": {}, "env": {}})

    def chatty() -> None:
        for _ in range(10):
            session.buffer.append(
                stream="console", device="board", job_id=None, line="working",
            )
            time.sleep(0.05)

    await session.queue.submit(chatty, mode="async")
    await asyncio.sleep(0.3)
    assert session.status()["liveness"]["quiet"] is False
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_quiet_clears_when_output_resumes() -> None:
    """quiet is reversible — one more log line clears it."""
    session = _session()
    await session.configure({"inventory": {}, "env": {}})
    await session.queue.submit(lambda: time.sleep(0.6), mode="async")  # noqa: ASYNC251
    await asyncio.sleep(0.3)
    assert session.status()["liveness"]["quiet"] is True
    session.buffer.append(
        stream="console", device="board", job_id=None, line="alive again",
    )
    liveness = session.status()["liveness"]
    assert liveness["quiet"] is False
    assert liveness["last_line"] == "alive again"
    session.queue.shutdown()


def test_liveness_with_no_running_job() -> None:
    """An idle session is not quiet — there is nothing to be quiet about."""
    session = _session()
    liveness = session.liveness()
    assert liveness["quiet"] is False
    assert liveness["running_for"] is None
    assert liveness["idle_for"] is None


def test_stuck_state_is_gone() -> None:
    """STUCK overwrote the real state and must not come back."""
    assert not hasattr(SessionState, "STUCK")
    assert not hasattr(Session, "is_stuck")
```

Delete `test_status_reports_stuck_when_a_job_overruns` from `unittests/api/test_session.py:184-196` — it asserts the removed behaviour.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_liveness.py -v -p no:randomly`
Expected: FAIL — `TypeError: RuntimeOptions.__init__() got an unexpected keyword argument 'quiet_after'`.

- [ ] **Step 3: Implement**

In `boardfarm3/api/console.py`, track the last event on `EventBuffer`. In `__init__`:

```python
        self._last_event: ConsoleEvent | None = None
        self._last_event_ts: float = time.time()
```

In `append()`, after `self._events.append(event)`:

```python
        self._last_event = event
        self._last_event_ts = event.ts
```

Add two properties beside `next_seq`:

```python
    @property
    def last_event_ts(self) -> float:
        """Timestamp of the most recent event, or of buffer creation.

        :return: UNIX timestamp
        :rtype: float
        """
        return self._last_event_ts

    @property
    def last_line(self) -> str | None:
        """Text of the most recent event, or None when nothing was captured.

        :return: last captured line
        :rtype: str | None
        """
        return self._last_event.line if self._last_event is not None else None
```

In `boardfarm3/api/runtime.py`, add to `RuntimeOptions` (it is not passed into the argparse `Namespace`, so `_build_cmdline_args` needs no change):

```python
    quiet_after: float = 600.0
```

In `boardfarm3/api/app.py`, add to `ConfigOptions`:

```python
    quiet_after: float | None = None
```

In `boardfarm3/api/session.py`: delete `STUCK = "stuck"` from `SessionState`; delete the `stuck_after` parameter, its docstring block, and `self.stuck_after`; delete `is_stuck()`. Add:

```python
    def liveness(self) -> dict[str, Any]:
        """Report progress evidence for the running job.

        ``quiet`` means only "no output for a while" and is reversible — one
        more log line clears it. It is deliberately advisory: no code branches
        on it, because a silent image flash and a wedged expect() are
        indistinguishable by idle time alone. Use ``GET /diagnostics/threads``
        to tell them apart.

        :return: liveness evidence
        :rtype: dict[str, Any]
        """
        last_ts = self.buffer.last_event_ts
        last_line = self.buffer.last_line
        running = self.queue.running_job()
        if running is None or running.started_at is None:
            return {
                "quiet": False,
                "running_for": None,
                "idle_for": None,
                "last_line": last_line,
                "last_event_ts": last_ts,
            }
        now = time.time()
        idle_for = now - max(running.started_at, last_ts)
        return {
            "quiet": idle_for > self.options.quiet_after,
            "running_for": now - running.started_at,
            "idle_for": idle_for,
            "last_line": last_line,
            "last_event_ts": last_ts,
        }
```

Rewrite `status()`:

```python
        return {
            "session_id": self.session_id,
            "board_name": self.options.board_name,
            "state": self.state.value,
            "liveness": self.liveness(),
            # True only after a full boot sequence completed (skip_boot=False)
            "booted": self.state is SessionState.READY and not self.options.skip_boot,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "error": self.error,
            "boot_job_id": self._boot_job.id if self._boot_job is not None else None,
        }
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS. Grep for stragglers: `grep -rn "is_stuck\|STUCK\|stuck_after" boardfarm3/ unittests/` must return nothing.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/console.py boardfarm3/api/session.py boardfarm3/api/runtime.py boardfarm3/api/app.py unittests/api/test_liveness.py unittests/api/test_session.py
git commit -m "feat(api): replace STUCK state with reversible liveness evidence

status() overwrote state with 'stuck', so a legitimately booting session
stopped reporting 'booting'. state is now always truthful and a sibling
liveness object reports quiet/running_for/idle_for/last_line. Threshold is
quiet_after, default 600s, settable per session. Nothing branches on it.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 10: Thread-stack snapshot

**Files:**
- Create: `boardfarm3/api/diagnostics.py`
- Modify: `boardfarm3/api/app.py` (add route beside `/diagnostics/skipped-routes`)
- Test: `unittests/api/test_diagnostics.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `boardfarm3.api.diagnostics.thread_snapshot() -> dict[str, Any]` with keys `captured_at: float` and `threads: list[dict]`, each thread having `name`, `ident`, `worker`, `daemon`, `stack: list[str]`. Also `format_threads(snapshot) -> str` for `threads.txt`. Route: `GET /diagnostics/threads`.

- [ ] **Step 1: Write the failing tests**

Create `unittests/api/test_diagnostics.py`:

```python
"""Thread-stack snapshot: the evidence that separates wedged from slow."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.diagnostics import format_threads, thread_snapshot

HTTP_OK = 200


def test_snapshot_includes_the_current_thread() -> None:
    snapshot = thread_snapshot()
    names = [thread["name"] for thread in snapshot["threads"]]
    assert threading.current_thread().name in names
    assert snapshot["captured_at"] > 0


def test_snapshot_flags_the_execution_worker() -> None:
    """The worker thread is the one that matters; it must be identifiable."""
    started = threading.Event()
    release = threading.Event()

    def block() -> None:
        started.set()
        release.wait(timeout=5)

    worker = threading.Thread(target=block, name="bf_0", daemon=True)
    worker.start()
    started.wait(timeout=5)
    try:
        snapshot = thread_snapshot()
        workers = [t for t in snapshot["threads"] if t["worker"]]
        assert len(workers) == 1
        assert workers[0]["name"] == "bf_0"
        assert any("block" in frame for frame in workers[0]["stack"])
    finally:
        release.set()
        worker.join(timeout=5)


def test_format_threads_is_readable_text() -> None:
    text = format_threads(thread_snapshot())
    assert "captured_at" in text
    assert threading.current_thread().name in text


def test_threads_route_returns_stacks() -> None:
    app = app_module.create_app("s-test", "board")
    with TestClient(app) as client:
        response = client.get("/diagnostics/threads")
    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["threads"]
    assert all("stack" in thread for thread in body["threads"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_diagnostics.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3.api.diagnostics`.

- [ ] **Step 3: Implement**

Create `boardfarm3/api/diagnostics.py`:

```python
"""Thread-stack sampling for distinguishing a wedged agent from a slow one."""

from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Any

# ThreadPoolExecutor in ExecutionQueue uses thread_name_prefix="bf", so its
# worker is named "bf_0". That thread is the one blocked in pexpect.
_WORKER_PREFIX = "bf"


def thread_snapshot() -> dict[str, Any]:
    """Capture the stack of every live thread.

    Read-only and allocation-light, so it is safe to call against a session
    whose worker thread is wedged. Two snapshots taken 30 s apart, diffed,
    distinguish a blocked ``expect()`` from a healthy long wait.

    :return: snapshot with a capture timestamp and one entry per thread
    :rtype: dict[str, Any]
    """
    frames = sys._current_frames()  # noqa: SLF001
    threads: list[dict[str, Any]] = [
        {
            "name": thread.name,
            "ident": thread.ident,
            "worker": thread.name.startswith(_WORKER_PREFIX),
            "daemon": thread.daemon,
            "stack": (
                traceback.format_stack(frames[thread.ident])
                if thread.ident in frames
                else []
            ),
        }
        for thread in threading.enumerate()
    ]
    return {"captured_at": time.time(), "threads": threads}


def format_threads(snapshot: dict[str, Any]) -> str:
    """Render a snapshot as plain text for the diagnostics bundle.

    :param snapshot: output of :func:`thread_snapshot`
    :type snapshot: dict[str, Any]
    :return: human-readable stack dump
    :rtype: str
    """
    lines = [f"captured_at: {snapshot['captured_at']}", ""]
    for thread in snapshot["threads"]:
        marker = " [WORKER]" if thread["worker"] else ""
        lines.append(f"--- {thread['name']} (ident={thread['ident']}){marker}")
        lines.extend(frame.rstrip() for frame in thread["stack"])
        lines.append("")
    return "\n".join(lines)
```

In `boardfarm3/api/app.py`, import `thread_snapshot` and add the route next to `diagnostics_skipped_routes`:

```python
    @app.get("/diagnostics/threads")
    async def diagnostics_threads() -> dict[str, Any]:
        """Return the stack of every live thread.

        Two samples taken 30 s apart, diffed, distinguish a wedged worker
        from a healthy long wait.

        :return: thread snapshot
        :rtype: dict[str, Any]
        """
        return thread_snapshot()
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/diagnostics.py boardfarm3/api/app.py unittests/api/test_diagnostics.py
git commit -m "feat(api): add GET /diagnostics/threads

Idle time cannot distinguish a wedged expect() from a silent image flash;
a thread stack can. Read-only and safe against a wedged session.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 11: Secret redaction

**Files:**
- Create: `boardfarm3/api/redact.py`
- Test: `unittests/api/test_redact.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `boardfarm3.api.redact.redact(value: Any) -> Any` — deep-copies, replacing values under secret-looking keys with `"***"`. `REDACTED = "***"`.

- [ ] **Step 1: Write the failing tests**

Create `unittests/api/test_redact.py`:

```python
"""Redaction of credentials in diagnostics output."""

from __future__ import annotations

from boardfarm3.api.redact import REDACTED, redact


def test_redacts_secret_looking_keys() -> None:
    out = redact({"username": "admin", "password": "hunter2", "authToken": "abc"})
    assert out["username"] == "admin"
    assert out["password"] == REDACTED
    assert out["authToken"] == REDACTED


def test_redacts_recursively_through_lists_and_dicts() -> None:
    out = redact({"devices": [{"name": "wan", "ssh_key": "PRIVATE"}]})
    assert out["devices"][0]["name"] == "wan"
    assert out["devices"][0]["ssh_key"] == REDACTED


def test_does_not_mutate_the_input() -> None:
    original = {"password": "hunter2"}
    redact(original)
    assert original["password"] == "hunter2"


def test_leaves_non_mapping_values_alone() -> None:
    assert redact("plain") == "plain"
    assert redact(42) == 42
    assert redact(None) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_redact.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3.api.redact`.

- [ ] **Step 3: Implement**

Create `boardfarm3/api/redact.py`:

```python
"""Redaction of credential-bearing values in diagnostics output."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***"

# Matched against dict *keys* only, so a value that merely contains the word
# "key" is preserved.
_SECRET_KEY = re.compile(r"pass|passwd|password|secret|token|key|auth", re.IGNORECASE)


def redact(value: Any) -> Any:  # noqa: ANN401
    """Return a copy of *value* with credential-bearing values replaced.

    Recurses through dicts and lists. Only dict keys are inspected; scalars
    are returned unchanged. The input is never mutated.

    :param value: arbitrary JSON-compatible structure
    :type value: Any
    :return: redacted copy
    :rtype: Any
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/redact.py unittests/api/test_redact.py
git commit -m "feat(api): add recursive credential redaction helper

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 12: The diagnostics bundle

**Files:**
- Create: `boardfarm3/api/bundle.py`
- Modify: `boardfarm3/api/session.py` (retain the payload), `boardfarm3/api/app.py` (add route)
- Test: `unittests/api/test_bundle.py` (new)

**Interfaces:**
- Consumes: `redact()` (Task 11), `thread_snapshot()`/`format_threads()` (Task 10), `ExecutionQueue.all_jobs()` (Task 8), `error_envelope()` (Task 6).
- Produces: `boardfarm3.api.bundle.write_bundle(session, dest: Path) -> dict[str, Any]` — writes a tar.gz to *dest* and returns the manifest. Route `GET /diagnostics/bundle` streaming `application/gzip`. `Session.payload: dict[str, Any]` retains the last configured payload.

- [ ] **Step 1: Write the failing tests**

Create `unittests/api/test_bundle.py`:

```python
"""Diagnostics bundle assembly."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.bundle import write_bundle
from boardfarm3.api.redact import REDACTED
from boardfarm3.api.runtime import RuntimeOptions
from boardfarm3.api.session import Session

HTTP_OK = 200
_EXPECTED = {
    "manifest.json",
    "session.json",
    "config.json",
    "jobs.json",
    "events.jsonl",
    "threads.txt",
}


class _FakeRuntime:
    """RuntimeContext stand-in that touches no devices."""

    def __init__(self) -> None:
        self.config: object | None = None
        self.device_manager: object | None = None

    def refresh_cmdline_args(self) -> None:
        """Re-materialise options. No-op for the fake."""

    def resolve(self, payload: dict[str, object]) -> object:  # noqa: ARG002
        """Resolve the payload.

        :param payload: opaque payload
        :type payload: dict[str, object]
        :return: placeholder config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Register devices.

        :return: placeholder device manager
        :rtype: object
        """
        self.device_manager = object()
        return self.device_manager


def _session(tmp_path: Path) -> Session:
    options = RuntimeOptions(
        board_name="board", save_console_logs=str(tmp_path / "console"),
    )
    return Session("s-test", options, runtime=_FakeRuntime())


@pytest.mark.asyncio
async def test_bundle_contains_every_documented_member(tmp_path: Path) -> None:
    session = _session(tmp_path)
    await session.configure({"inventory": {}, "env": {}})
    dest = tmp_path / "bundle.tar.gz"
    manifest = write_bundle(session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        names = set(archive.getnames())
    assert _EXPECTED.issubset(names)
    assert manifest["session_id"] == "s-test"
    assert manifest["board_name"] == "board"
    assert manifest["redacted"] == ["session.json", "config.json"]
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_bundle_redacts_credentials_in_config(tmp_path: Path) -> None:
    session = _session(tmp_path)
    await session.configure(
        {"inventory": {"board": {"password": "hunter2"}}, "env": {}},
    )
    dest = tmp_path / "bundle.tar.gz"
    write_bundle(session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        member = archive.extractfile("config.json")
        assert member is not None
        config = json.loads(member.read())
    assert config["inventory"]["board"]["password"] == REDACTED
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_bundle_records_absent_members(tmp_path: Path) -> None:
    """A missing console-log directory must be reported, not crash the bundle."""
    session = _session(tmp_path)
    await session.configure({"inventory": {}, "env": {}})
    dest = tmp_path / "bundle.tar.gz"
    manifest = write_bundle(session, dest)
    assert "console-logs" in manifest["absent"]
    session.queue.shutdown()


@pytest.mark.asyncio
async def test_bundle_jobs_carry_tracebacks(tmp_path: Path) -> None:
    session = _session(tmp_path)
    await session.configure({"inventory": {}, "env": {}})

    def boom() -> None:
        msg = "kaboom"
        raise ValueError(msg)

    await session.queue.submit(boom, mode="sync")
    dest = tmp_path / "bundle.tar.gz"
    write_bundle(session, dest)

    with tarfile.open(dest, "r:gz") as archive:
        member = archive.extractfile("jobs.json")
        assert member is not None
        jobs = json.loads(member.read())
    failed = [job for job in jobs if job["state"] == "error"]
    assert failed
    assert "ValueError: kaboom" in "".join(failed[0]["error"]["traceback"])
    session.queue.shutdown()


def test_bundle_route_streams_gzip() -> None:
    app = app_module.create_app("s-test", "board")
    with TestClient(app) as client:
        response = client.get("/diagnostics/bundle")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "application/gzip"
    assert response.content[:2] == b"\x1f\x8b"
```

Note: `await queue.submit(boom, mode="sync")` re-raises. Wrap it:

```python
    with pytest.raises(ValueError, match="kaboom"):
        await session.queue.submit(boom, mode="sync")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/api/test_bundle.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3.api.bundle`.

- [ ] **Step 3: Implement**

In `boardfarm3/api/session.py`, retain the payload. In `__init__`, add `self.payload: dict[str, Any] = {}`; at the top of `configure()`, add `self.payload = payload`.

Create `boardfarm3/api/bundle.py`:

```python
"""Assembly of the agent diagnostics bundle."""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boardfarm3 import __version__
from boardfarm3.api.diagnostics import format_threads, thread_snapshot
from boardfarm3.api.errors import error_envelope
from boardfarm3.api.redact import redact

if TYPE_CHECKING:
    from boardfarm3.api.session import Session

_REDACTED_MEMBERS = ["session.json", "config.json"]


def _add_text(archive: tarfile.TarFile, name: str, text: str) -> None:
    """Add an in-memory string to the archive as a file.

    :param archive: open tar archive
    :type archive: tarfile.TarFile
    :param name: member name inside the archive
    :type name: str
    :param text: file contents
    :type text: str
    """
    data = text.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(time.time())
    archive.addfile(info, io.BytesIO(data))


def _jobs_payload(session: Session) -> list[dict[str, Any]]:
    """Serialise every retained job, with tracebacks for failures.

    :param session: session whose queue to enumerate
    :type session: Session
    :return: one entry per retained job
    :rtype: list[dict[str, Any]]
    """
    return [
        {
            "job_id": job.id,
            "state": job.state.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": (
                error_envelope(
                    job.error, session_id=session.session_id, job_id=job.id,
                )
                if job.error is not None
                else None
            ),
        }
        for job in session.queue.all_jobs()
    ]


def write_bundle(session: Session, dest: Path) -> dict[str, Any]:
    """Write the diagnostics bundle for *session* to *dest*.

    Written to disk rather than buffered in memory: console logs are capped at
    25 MB per device by the connection layer's rotating handler.

    Console transcripts are deliberately not redacted — a credential echoed by
    a login prompt cannot be reliably scrubbed. ``manifest.json`` records
    exactly which members were processed.

    :param session: session to capture
    :type session: Session
    :param dest: path of the tar.gz to write
    :type dest: Path
    :return: the manifest that was embedded in the archive
    :rtype: dict[str, Any]
    """
    console_dir = Path(session.options.save_console_logs or "")
    has_console = bool(session.options.save_console_logs) and console_dir.is_dir()
    agent_log = console_dir.parent / "agent.log" if has_console else None
    has_agent_log = agent_log is not None and agent_log.is_file()

    absent = [
        name
        for name, present in (
            ("console-logs", has_console),
            ("agent.log", has_agent_log),
        )
        if not present
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "session_id": session.session_id,
        "board_name": session.options.board_name,
        "agent_version": __version__,
        "created_at": session.created_at,
        "captured_at": time.time(),
        "state": session.state.value,
        "redacted": list(_REDACTED_MEMBERS),
        "absent": absent,
    }

    events, _ = session.buffer.read(cursor=0, limit=1_000_000)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as archive:
        _add_text(archive, "manifest.json", json.dumps(manifest, indent=2))
        _add_text(
            archive, "session.json", json.dumps(redact(session.status()), indent=2),
        )
        _add_text(
            archive, "config.json", json.dumps(redact(session.payload), indent=2),
        )
        _add_text(archive, "jobs.json", json.dumps(_jobs_payload(session), indent=2))
        _add_text(
            archive,
            "events.jsonl",
            "\n".join(json.dumps(event.__dict__) for event in events),
        )
        _add_text(archive, "threads.txt", format_threads(thread_snapshot()))
        if has_agent_log and agent_log is not None:
            archive.add(agent_log, arcname="agent.log")
        if has_console:
            archive.add(console_dir, arcname="console-logs")
    return manifest
```

In `boardfarm3/api/app.py`, add the route beside `/console/archive`:

```python
    @app.get("/diagnostics/bundle")
    async def diagnostics_bundle() -> StreamingResponse:
        """Return a tar.gz of everything needed to debug this session.

        Valid in any state including ready — taking a bundle has no side
        effects on the session.

        :return: streaming gzip archive
        :rtype: StreamingResponse
        """
        tmp = Path(tempfile.mkdtemp(prefix="bf-bundle-")) / "bundle.tar.gz"
        write_bundle(session(), tmp)

        async def stream() -> AsyncIterator[bytes]:
            try:
                with tmp.open("rb") as handle:
                    while chunk := handle.read(64 * 1024):
                        yield chunk
            finally:
                shutil.rmtree(tmp.parent, ignore_errors=True)

        return StreamingResponse(
            stream(),
            media_type="application/gzip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{session_id}-diagnostics.tar.gz"'
                ),
            },
        )
```

Add `import shutil`, `import tempfile`, and `from boardfarm3.api.bundle import write_bundle` to `boardfarm3/api/app.py`.

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/api -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/bundle.py boardfarm3/api/app.py boardfarm3/api/session.py unittests/api/test_bundle.py
git commit -m "feat(api): add GET /diagnostics/bundle

Streams a tar.gz of manifest, session, config, jobs (with tracebacks),
events, thread stacks, agent.log, and console logs. Valid in any state
including ready. session.json and config.json are redacted; console
transcripts deliberately are not, and the manifest says so.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

# Phase 3 — Control plane retention and diagnostics

### Task 13: Launcher gains purge and capture

**Files:**
- Modify: `boardfarm3_control/launcher.py` — `Launcher` protocol, `FakeLauncher`, `ProcessLauncher`, `DockerLauncher`
- Test: `unittests/control/test_launcher.py`

**Interfaces:**
- Consumes: nothing.
- Produces: on every launcher — `stop(session_id, *, remove: bool = True) -> None`, `purge(session_id) -> None`, `capture_logs(session_id) -> bytes`, `capture_files(session_id, path: str) -> bytes`. `DockerLauncher.list_sessions()` includes stopped containers and sets `AgentInfo.state`.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/control/test_launcher.py`:

```python
@pytest.mark.asyncio
async def test_fake_launcher_retains_on_stop_without_remove() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1", remove=False)
    sessions = await launcher.list_sessions()
    assert [s.session_id for s in sessions] == ["s-1"]
    assert sessions[0].state == "dead"


@pytest.mark.asyncio
async def test_fake_launcher_purge_removes_the_record() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1", remove=False)
    await launcher.purge("s-1")
    assert await launcher.list_sessions() == []


@pytest.mark.asyncio
async def test_fake_launcher_stop_with_remove_purges() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    await launcher.stop("s-1")
    assert await launcher.list_sessions() == []


@pytest.mark.asyncio
async def test_fake_launcher_capture_returns_bytes() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-1", "board", "img", "prplos")
    assert isinstance(await launcher.capture_logs("s-1"), bytes)
    assert isinstance(await launcher.capture_files("s-1", "/var/log"), bytes)


@pytest.mark.asyncio
async def test_capture_on_unknown_session_returns_empty() -> None:
    launcher = FakeLauncher()
    assert await launcher.capture_logs("nope") == b""
    assert await launcher.capture_files("nope", "/var/log") == b""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_launcher.py -v -p no:randomly`
Expected: FAIL — `TypeError: stop() got an unexpected keyword argument 'remove'`.

- [ ] **Step 3: Implement**

In `boardfarm3_control/models.py`, add to `AgentInfo`:

```python
    state: str = "live"
    ended_at: float | None = None
```

In `boardfarm3_control/launcher.py`, extend the `Launcher` protocol with the four signatures (each with a full Sphinx docstring matching the existing style), then implement.

`FakeLauncher` — replace `stop` and add the rest:

```python
    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Mark a session dead, optionally dropping its record.

        :param session_id: session to stop
        :type session_id: str
        :param remove: also forget the session, as ``docker rm`` would
        :type remove: bool
        """
        if remove:
            self._sessions.pop(session_id, None)
            return
        info = self._sessions.get(session_id)
        if info is not None:
            self._sessions[session_id] = info.model_copy(
                update={"state": "dead", "ended_at": time.time()},
            )

    async def purge(self, session_id: str) -> None:
        """Forget a stopped session.

        :param session_id: session to purge
        :type session_id: str
        """
        self._sessions.pop(session_id, None)

    async def capture_logs(self, session_id: str) -> bytes:
        """Return synthetic agent output for tests.

        :param session_id: session whose output to capture
        :type session_id: str
        :return: log bytes, empty when the session is unknown
        :rtype: bytes
        """
        if session_id not in self._sessions:
            return b""
        return f"fake logs for {session_id}\n".encode()

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return synthetic tar bytes for tests.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the agent
        :type path: str
        :return: tar bytes, empty when the session is unknown
        :rtype: bytes
        """
        if session_id not in self._sessions:
            return b""
        return f"fake tar of {path} for {session_id}".encode()
```

`ProcessLauncher` — redirect output to a file instead of `DEVNULL`. In `start()`:

```python
        log_dir = Path(
            os.environ.get("BOARDFARM_CONTROL_STORE", "/var/lib/boardfarm-control"),
        ) / "sessions" / session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = (log_dir / "process.log").open("wb")
        proc = await asyncio.create_subprocess_exec(
            ...,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
        )
```

Keep a reference so it is closed on stop; store `log_file` alongside the process in `self._sessions`. Change the tuple to a small dataclass or a 3-tuple `(proc, info, log_file)` and update every unpack site (`stop`, `list_sessions`, `_save_state`). Add:

```python
    async def capture_logs(self, session_id: str) -> bytes:
        """Read the subprocess output file for a session.

        :param session_id: session whose output to read
        :type session_id: str
        :return: log bytes, empty when unavailable
        :rtype: bytes
        """
        path = Path(
            os.environ.get("BOARDFARM_CONTROL_STORE", "/var/lib/boardfarm-control"),
        ) / "sessions" / session_id / "process.log"
        try:
            return path.read_bytes()
        except OSError:
            return b""

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path*, which is local for this launcher.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: local path to archive
        :type path: str
        :return: tar bytes, empty when the path does not exist
        :rtype: bytes
        """
        source = Path(path)
        if not source.exists():
            return b""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            archive.add(source, arcname=source.name)
        return buffer.getvalue()

    async def purge(self, session_id: str) -> None:
        """Delete the on-disk record for a stopped session.

        :param session_id: session to purge
        :type session_id: str
        """
        self._sessions.pop(session_id, None)
        self._save_state()
```

Add `import io`, `import tarfile` to the module.

`DockerLauncher` — add a container lookup that includes stopped containers:

```python
    def _find(self, session_id: str) -> list[object]:
        """Return every container for a session, running or not.

        :param session_id: session to look up
        :type session_id: str
        :return: matching containers
        :rtype: list[object]
        """
        return self._client.containers.list(
            all=True,
            filters={"label": f"{self._LABEL_SESSION}={session_id}"},
        )
```

Replace `stop()`:

```python
    async def stop(self, session_id: str, *, remove: bool = True) -> None:
        """Stop the container, and remove it only when *remove* is set.

        A stopped container releases every tty and socket the agent held, so a
        retained corpse can never contend with a fresh session on the board.

        :param session_id: session whose container to stop
        :type session_id: str
        :param remove: also ``docker rm`` the container
        :type remove: bool
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        for container in containers:
            await loop.run_in_executor(None, container.stop)
            if remove:
                await loop.run_in_executor(None, container.remove)

    async def purge(self, session_id: str) -> None:
        """Remove the stopped container for a session.

        :param session_id: session whose container to remove
        :type session_id: str
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        for container in containers:
            await loop.run_in_executor(
                None, lambda c=container: c.remove(force=True),
            )

    async def capture_logs(self, session_id: str) -> bytes:
        """Return the container's stdout and stderr.

        A daemon API call, so it works against a remote host and a stopped
        container alike.

        :param session_id: session whose logs to capture
        :type session_id: str
        :return: log bytes, empty when the container is gone
        :rtype: bytes
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        if not containers:
            return b""
        return await loop.run_in_executor(
            None, lambda: containers[0].logs(stdout=True, stderr=True),
        )

    async def capture_files(self, session_id: str, path: str) -> bytes:
        """Return a tar of *path* from inside the container.

        :param session_id: session whose files to capture
        :type session_id: str
        :param path: path inside the container
        :type path: str
        :return: tar bytes, empty when unavailable
        :rtype: bytes
        """
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, self._find, session_id)
        if not containers:
            return b""

        def _archive() -> bytes:
            stream, _ = containers[0].get_archive(path)
            return b"".join(stream)

        try:
            return await loop.run_in_executor(None, _archive)
        except Exception:  # noqa: BLE001
            _log.warning("could not archive %s from session %s", path, session_id)
            return b""
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS. Existing `stop()` call sites are unaffected — `remove` defaults to `True`.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/launcher.py boardfarm3_control/models.py unittests/control/test_launcher.py
git commit -m "feat(control): separate container stop from removal

Adds stop(remove=), purge(), capture_logs(), and capture_files() to every
launcher. The capture methods are Docker daemon API calls, so they work
against a remote host and a stopped container. ProcessLauncher stops
discarding agent output to DEVNULL.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 14: The diagnostics store

**Files:**
- Create: `boardfarm3_control/store.py`
- Test: `unittests/control/test_store.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `DiagnosticsStore(root: Path | None = None)` with `session_dir(sid) -> Path`, `write_meta(sid, meta: dict) -> None`, `read_meta(sid) -> dict | None`, `bundle_path(sid) -> Path`, `has_bundle(sid) -> bool`, `write_bundle(sid, chunks: Iterable[bytes]) -> int`, `list_sessions() -> list[str]`, `total_bytes() -> int`, `delete(sid) -> None`. Root defaults to `$BOARDFARM_CONTROL_STORE` or `/var/lib/boardfarm-control`.

- [ ] **Step 1: Write the failing tests**

Create `unittests/control/test_store.py`:

```python
"""On-disk diagnostics store."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardfarm3_control.store import DiagnosticsStore


@pytest.fixture(name="store")
def store_fixture(tmp_path: Path) -> DiagnosticsStore:
    """Return a store rooted in a temporary directory.

    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :return: store under test
    :rtype: DiagnosticsStore
    """
    return DiagnosticsStore(root=tmp_path)


def test_meta_round_trips(store: DiagnosticsStore) -> None:
    store.write_meta("s-1", {"board_name": "board", "ended_at": 1.0})
    assert store.read_meta("s-1") == {"board_name": "board", "ended_at": 1.0}


def test_read_meta_for_unknown_session_is_none(store: DiagnosticsStore) -> None:
    assert store.read_meta("nope") is None


def test_write_bundle_returns_byte_count(store: DiagnosticsStore) -> None:
    written = store.write_bundle("s-1", [b"abc", b"de"])
    assert written == 5
    assert store.has_bundle("s-1")
    assert store.bundle_path("s-1").read_bytes() == b"abcde"


def test_list_sessions_and_total_bytes(store: DiagnosticsStore) -> None:
    store.write_bundle("s-1", [b"a" * 10])
    store.write_bundle("s-2", [b"b" * 20])
    assert sorted(store.list_sessions()) == ["s-1", "s-2"]
    assert store.total_bytes() >= 30


def test_delete_removes_everything_for_a_session(store: DiagnosticsStore) -> None:
    store.write_meta("s-1", {"board_name": "board"})
    store.write_bundle("s-1", [b"abc"])
    store.delete("s-1")
    assert store.list_sessions() == []
    assert not store.session_dir("s-1").exists()


def test_root_defaults_to_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path / "custom"))
    assert DiagnosticsStore().session_dir("s-1") == tmp_path / "custom" / "sessions" / "s-1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_store.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3_control.store`.

- [ ] **Step 3: Implement**

Create `boardfarm3_control/store.py`:

```python
"""On-disk store for archived agent diagnostics."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

_DEFAULT_ROOT = "/var/lib/boardfarm-control"
_log = logging.getLogger(__name__)


class DiagnosticsStore:
    """Per-session directory of archived bundles and metadata.

    ``meta.json`` outlives both the container and the bundle, so a dead
    session stays listable and explicable after either has been purged.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Initialise the store.

        :param root: store root; ``$BOARDFARM_CONTROL_STORE`` when omitted
        :type root: Path | None
        """
        self._root = root or Path(
            os.environ.get("BOARDFARM_CONTROL_STORE") or _DEFAULT_ROOT,
        )

    def session_dir(self, session_id: str) -> Path:
        """Return the directory holding a session's artifacts.

        :param session_id: session identifier
        :type session_id: str
        :return: session directory
        :rtype: Path
        """
        return self._root / "sessions" / session_id

    def bundle_path(self, session_id: str) -> Path:
        """Return the archived bundle path for a session.

        :param session_id: session identifier
        :type session_id: str
        :return: bundle path
        :rtype: Path
        """
        return self.session_dir(session_id) / "bundle.tar.gz"

    def has_bundle(self, session_id: str) -> bool:
        """Report whether an archived bundle exists.

        :param session_id: session identifier
        :type session_id: str
        :return: True when a bundle is on disk
        :rtype: bool
        """
        return self.bundle_path(session_id).is_file()

    def write_meta(self, session_id: str, meta: dict[str, Any]) -> None:
        """Persist session metadata.

        :param session_id: session identifier
        :type session_id: str
        :param meta: metadata to store
        :type meta: dict[str, Any]
        """
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8",
        )

    def read_meta(self, session_id: str) -> dict[str, Any] | None:
        """Read session metadata.

        :param session_id: session identifier
        :type session_id: str
        :return: metadata, or None when absent or unreadable
        :rtype: dict[str, Any] | None
        """
        path = self.session_dir(session_id) / "meta.json"
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data

    def write_bundle(self, session_id: str, chunks: Iterable[bytes]) -> int:
        """Write an archived bundle from an iterable of byte chunks.

        :param session_id: session identifier
        :type session_id: str
        :param chunks: bundle payload
        :type chunks: Iterable[bytes]
        :return: number of bytes written
        :rtype: int
        """
        path = self.bundle_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with path.open("wb") as handle:
            for chunk in chunks:
                handle.write(chunk)
                written += len(chunk)
        return written

    def list_sessions(self) -> list[str]:
        """Return every session id present in the store.

        :return: session identifiers
        :rtype: list[str]
        """
        base = self._root / "sessions"
        if not base.is_dir():
            return []
        return [entry.name for entry in base.iterdir() if entry.is_dir()]

    def total_bytes(self) -> int:
        """Return the total size of the store in bytes.

        :return: byte count
        :rtype: int
        """
        base = self._root / "sessions"
        if not base.is_dir():
            return 0
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file())

    def delete(self, session_id: str) -> None:
        """Delete every artifact for a session.

        :param session_id: session identifier
        :type session_id: str
        """
        shutil.rmtree(self.session_dir(session_id), ignore_errors=True)
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/store.py unittests/control/test_store.py
git commit -m "feat(control): add on-disk diagnostics store

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 15: Restart correctness

**Files:**
- Modify: `boardfarm3_control/launcher.py` (`DockerLauncher.list_sessions`), `boardfarm3_control/app.py:63-71` (lifespan)
- Test: `unittests/control/test_app.py`, `unittests/control/test_launcher.py`

**Interfaces:**
- Consumes: `AgentInfo.state` (Task 13).
- Produces: `DockerLauncher.list_sessions()` returns stopped containers with `state="dead"`; `BoardLease.rebuild_from()` receives live sessions only; the lifespan no longer stops agents on shutdown.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/control/test_app.py`:

```python
@pytest.mark.asyncio
async def test_shutdown_leaves_running_agents_alone(
    fake_launcher: FakeLauncher, profiles: dict[str, str],
) -> None:
    """A control plane restart must not destroy live sessions.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    """
    await fake_launcher.start("s-existing", "board", "img", "prplos")
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app):
        pass
    assert [s.session_id for s in await fake_launcher.list_sessions()] == ["s-existing"]


@pytest.mark.asyncio
async def test_dead_sessions_do_not_reacquire_a_lease(
    fake_launcher: FakeLauncher, profiles: dict[str, str],
) -> None:
    """A corpse must never block its board after a restart.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    """
    await fake_launcher.start("s-dead", "board-a", "img", "prplos")
    await fake_launcher.stop("s-dead", remove=False)
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={
                "board_name": "board-a",
                "runtime_profile": "prplos",
                "payload": {},
            },
        )
    # Board is free: the request proceeds past the lease check (it fails later
    # on the health poll, which is a 503 — not the 409 a held lease produces).
    assert response.status_code != 409
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_app.py -v -p no:randomly`
Expected: FAIL — the shutdown test finds zero sessions; the lease test returns 409.

- [ ] **Step 3: Implement**

In `boardfarm3_control/launcher.py`, `DockerLauncher.list_sessions()` — list all containers and derive lifecycle from status (Docker labels cannot be mutated after creation, so status is the signal):

```python
        containers = await loop.run_in_executor(
            None,
            lambda: self._client.containers.list(
                all=True,
                filters={"label": self._LABEL_SESSION},
            ),
        )
```

and inside the loop, when building each `AgentInfo`:

```python
                    state="live" if container.status == "running" else "dead",
```

In `boardfarm3_control/app.py`, rewrite the lifespan:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await registry.rebuild(launcher)
        existing = await launcher.list_sessions()
        # Only live sessions hold a board. A retained corpse must never
        # re-acquire a lease and block its board after a restart.
        await lease.rebuild_from([s for s in existing if s.state == "live"])
        app.state.http = httpx.AsyncClient()
        yield
        # Running agents are deliberately left alone: a control plane restart
        # must not destroy live sessions or the containers being debugged.
        await app.state.http.aclose()
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/launcher.py boardfarm3_control/app.py unittests/control/test_app.py
git commit -m "fix(control): correct restart semantics for retained sessions

list_sessions() now includes stopped containers, so a corpse survives a
restart instead of being orphaned. Dead sessions no longer re-acquire a
lease, and shutdown stops destroying live agents, as the control plane
design already specified.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 16: Registry and response model carry lifecycle and liveness

**Files:**
- Modify: `boardfarm3_control/registry.py`, `boardfarm3_control/models.py` (`SessionResponse`), `boardfarm3_control/app.py:198-239` (`list_sessions`)
- Test: `unittests/control/test_registry.py`, `unittests/control/test_app.py`

**Interfaces:**
- Consumes: `AgentInfo.state`/`ended_at` (Task 13), agent `status()["liveness"]` (Task 9).
- Produces: `SessionRegistry.mark_dead(session_id, ended_at: float) -> None`; `SessionResponse.liveness: dict[str, Any] | None`.

- [ ] **Step 1: Write the failing tests**

Append to `unittests/control/test_registry.py`:

```python
def test_mark_dead_keeps_the_session_listed() -> None:
    """A corpse stays listed so it can be found and purged."""
    registry = SessionRegistry()
    registry.add(
        AgentInfo(
            session_id="s-1",
            board_name="board",
            runtime_profile="prplos",
            container_id="c",
            host_port=1,
            created_at=0.0,
        ),
    )
    registry.mark_dead("s-1", ended_at=123.0)
    info = registry.get("s-1")
    assert info is not None
    assert info.state == "dead"
    assert info.ended_at == 123.0
    assert registry.list_page(0, 10)[1] == 1


def test_mark_dead_on_unknown_session_is_a_noop() -> None:
    registry = SessionRegistry()
    registry.mark_dead("nope", ended_at=1.0)
    assert registry.get("nope") is None
```

Append to `unittests/control/test_app.py`:

```python
@respx.mock
def test_list_sessions_forwards_liveness(
    fake_launcher: FakeLauncher, profiles: dict[str, str],
) -> None:
    """A list view must show progress without a round trip per session.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    """
    asyncio.run(fake_launcher.start("s-1", "board", "img", "prplos"))
    respx.get("http://localhost:18000/session").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": "booting",
                "booted": False,
                "last_activity": 5.0,
                "liveness": {"quiet": True, "idle_for": 700.0},
            },
        ),
    )
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app) as client:
        body = client.get("/sessions").json()
    assert body["sessions"][0]["liveness"]["quiet"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_registry.py unittests/control/test_app.py -v -p no:randomly`
Expected: FAIL — `AttributeError: 'SessionRegistry' object has no attribute 'mark_dead'`, and `liveness` missing from the response.

- [ ] **Step 3: Implement**

In `boardfarm3_control/registry.py`, add:

```python
    def mark_dead(self, session_id: str, ended_at: float) -> None:
        """Mark a session dead while keeping it listed.

        A corpse stays in the registry so it can be found, its diagnostics
        served, and its container purged. ``AgentInfo`` is frozen, so the
        entry is replaced rather than mutated.

        :param session_id: session to mark
        :type session_id: str
        :param ended_at: when the session ended
        :type ended_at: float
        """
        info = self._sessions.get(session_id)
        if info is None:
            return
        self._sessions[session_id] = info.model_copy(
            update={"state": "dead", "ended_at": ended_at},
        )
```

In `boardfarm3_control/models.py`, add to `SessionResponse`:

```python
    ended_at: float | None = None
    liveness: dict[str, Any] | None = None
```

In `boardfarm3_control/app.py`, inside `fetch_state()`, capture and forward liveness:

```python
                liveness: dict[str, Any] | None = data.get("liveness")
```

with `liveness = None` in the `except` branch, and add `liveness=liveness, ended_at=info.ended_at` to the `SessionResponse(...)` construction. Dead sessions never reach the HTTP branch successfully, so their `liveness` is `None` as specified — add an early return for them:

```python
            if info.state == "dead":
                return SessionResponse(
                    session_id=info.session_id,
                    board_name=info.board_name,
                    runtime_profile=info.runtime_profile,
                    state="dead",
                    booted=False,
                    agent_url=info.agent_url,
                    pid=info.pid,
                    created_at=info.created_at,
                    ended_at=info.ended_at,
                    last_activity=registry.last_activity(info.session_id),
                    liveness=None,
                )
```

as the first statement of `fetch_state()`.

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/registry.py boardfarm3_control/models.py boardfarm3_control/app.py unittests/control/test_registry.py unittests/control/test_app.py
git commit -m "feat(control): track dead sessions and forward liveness

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 17: The teardown sequence

**Files:**
- Create: `boardfarm3_control/teardown.py`
- Modify: `boardfarm3_control/app.py:241-261` (`delete_session`)
- Test: `unittests/control/test_teardown.py` (new)

**Interfaces:**
- Consumes: `DiagnosticsStore` (Task 14), launcher `stop(remove=)`/`capture_*` (Task 13), `registry.mark_dead` (Task 16).
- Produces: `boardfarm3_control.teardown.teardown_session(*, session_id, info, launcher, registry, lease, store, http, retain: bool) -> None` and `archive_bundle(*, session_id, agent_url, launcher, store, http) -> str` returning the tier that produced it (`"agent"`, `"launcher"`, or `"none"`).

- [ ] **Step 1: Write the failing tests**

Create `unittests/control/test_teardown.py`:

```python
"""The teardown matrix: what is pulled, retained, and released."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.lease import BoardLease
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore
from boardfarm3_control.teardown import archive_bundle, teardown_session


async def _prepare(tmp_path: Path) -> tuple:
    launcher = FakeLauncher()
    info = await launcher.start("s-1", "board", "img", "prplos")
    registry = SessionRegistry()
    registry.add(info)
    lease = BoardLease()
    await lease.acquire("board", "s-1")
    return launcher, info, registry, lease, DiagnosticsStore(root=tmp_path)


@pytest.mark.asyncio
@respx.mock
async def test_retain_keeps_the_container_and_marks_dead(tmp_path: Path) -> None:
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"BUNDLE"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={}),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1", info=info, launcher=launcher, registry=registry,
            lease=lease, store=store, http=http, retain=True,
        )
    assert store.bundle_path("s-1").read_bytes() == b"BUNDLE"
    assert [s.session_id for s in await launcher.list_sessions()] == ["s-1"]
    listed = registry.get("s-1")
    assert listed is not None
    assert listed.state == "dead"
    assert lease.held_by("board") is None


@pytest.mark.asyncio
@respx.mock
async def test_clean_delete_removes_container_but_keeps_bundle(
    tmp_path: Path,
) -> None:
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"BUNDLE"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        return_value=httpx.Response(200, json={}),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1", info=info, launcher=launcher, registry=registry,
            lease=lease, store=store, http=http, retain=False,
        )
    assert store.has_bundle("s-1")
    assert await launcher.list_sessions() == []
    assert registry.get("s-1") is None
    assert lease.held_by("board") is None


@pytest.mark.asyncio
@respx.mock
async def test_lease_is_released_even_when_every_step_fails(
    tmp_path: Path,
) -> None:
    """A dead agent must never strand a board."""
    launcher, info, registry, lease, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    respx.delete(f"{info.agent_url}/session").mock(
        side_effect=httpx.ConnectError("down"),
    )
    async with httpx.AsyncClient() as http:
        await teardown_session(
            session_id="s-1", info=info, launcher=launcher, registry=registry,
            lease=lease, store=store, http=http, retain=True,
        )
    assert lease.held_by("board") is None


def test_retain_and_purge_are_mutually_exclusive(
    fake_launcher: FakeLauncher, profiles: dict[str, str],
) -> None:
    """Contradictory teardown flags must be rejected, not silently ordered.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    """
    from fastapi.testclient import TestClient

    from boardfarm3_control.app import create_app

    asyncio.run(fake_launcher.start("s-1", "board", "img", "prplos"))
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app) as client:
        response = client.delete("/sessions/s-1?retain=true&purge=true")
    assert response.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_archive_falls_back_to_the_launcher(tmp_path: Path) -> None:
    """A crashed agent cannot serve HTTP; the launcher still can."""
    launcher, info, _, _, store = await _prepare(tmp_path)
    respx.get(f"{info.agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    async with httpx.AsyncClient() as http:
        source = await archive_bundle(
            session_id="s-1", agent_url=info.agent_url, launcher=launcher,
            store=store, http=http,
        )
    assert source == "launcher"
    assert store.has_bundle("s-1")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_teardown.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3_control.teardown`.

- [ ] **Step 3: Implement**

Create `boardfarm3_control/teardown.py`:

```python
"""The single teardown sequence used by DELETE and by every failure unwind."""

from __future__ import annotations

import io
import logging
import tarfile
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.lease import BoardLease
    from boardfarm3_control.models import AgentInfo
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)
_BUNDLE_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def _launcher_bundle(logs: bytes, files: bytes) -> bytes:
    """Wrap launcher-captured bytes in the same tar.gz shape as an agent bundle.

    :param logs: container stdout/stderr
    :type logs: bytes
    :param files: tar bytes of the agent artifact directory
    :type files: bytes
    :return: gzip archive
    :rtype: bytes
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in (("docker.log", logs), ("artifacts.tar", files)):
            if not payload:
                continue
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = int(time.time())
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


async def archive_bundle(
    *,
    session_id: str,
    agent_url: str,
    launcher: Launcher,
    store: DiagnosticsStore,
    http: httpx.AsyncClient,
) -> str:
    """Pull a diagnostics bundle and archive it, preferring the live agent.

    :param session_id: session to capture
    :type session_id: str
    :param agent_url: base URL of the agent
    :type agent_url: str
    :param launcher: launcher used for the fallback capture
    :type launcher: Launcher
    :param store: store to archive into
    :type store: DiagnosticsStore
    :param http: pooled HTTP client
    :type http: httpx.AsyncClient
    :return: which tier produced the bundle: agent, launcher, or none
    :rtype: str
    """
    try:
        response = await http.get(
            f"{agent_url}/diagnostics/bundle", timeout=_BUNDLE_TIMEOUT,
        )
        response.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        _log.info("agent bundle unavailable for %s: %s", session_id, exc)
    else:
        store.write_bundle(session_id, [response.content])
        return "agent"

    logs = await launcher.capture_logs(session_id)
    files = await launcher.capture_files(session_id, "/var/log/boardfarm")
    if not logs and not files:
        return "none"
    store.write_bundle(session_id, [_launcher_bundle(logs, files)])
    return "launcher"


async def teardown_session(  # noqa: PLR0913
    *,
    session_id: str,
    info: AgentInfo,
    launcher: Launcher,
    registry: SessionRegistry,
    lease: BoardLease,
    store: DiagnosticsStore,
    http: httpx.AsyncClient,
    retain: bool,
) -> None:
    """Archive, release devices, stop the container, and free the board.

    Steps 1 and 2 are best-effort: a diagnostics or graceful-release failure
    must never strand a board or leak a container, so the lease is released
    and the container stopped regardless.

    :param session_id: session to tear down
    :type session_id: str
    :param info: registry entry for the session
    :type info: AgentInfo
    :param launcher: launcher owning the container
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param lease: board lease table
    :type lease: BoardLease
    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param http: pooled HTTP client
    :type http: httpx.AsyncClient
    :param retain: keep the stopped container for post-mortem
    :type retain: bool
    """
    ended_at = time.time()

    # 1. Capture while the agent can still answer — the only moment this works.
    source = "none"
    try:
        source = await archive_bundle(
            session_id=session_id, agent_url=info.agent_url,
            launcher=launcher, store=store, http=http,
        )
    except Exception:  # noqa: BLE001
        _log.warning("diagnostics capture failed for %s", session_id)

    store.write_meta(
        session_id,
        {
            "session_id": session_id,
            "board_name": info.board_name,
            "runtime_profile": info.runtime_profile,
            "created_at": info.created_at,
            "ended_at": ended_at,
            "retained": retain,
            "bundle_source": source,
        },
    )

    # 2. Graceful device release, so board-side state is not left half-open.
    try:
        await http.delete(f"{info.agent_url}/session")
    except httpx.HTTPError as exc:
        _log.info("graceful release skipped for %s: %s", session_id, exc)

    # 3-5. Always run, whatever happened above.
    await launcher.stop(session_id, remove=not retain)
    await lease.release(session_id)
    if retain:
        registry.mark_dead(session_id, ended_at=ended_at)
    else:
        registry.remove(session_id)
```

In `boardfarm3_control/app.py`, build one store in `create_app` (`store = DiagnosticsStore()`) and rewrite `delete_session`:

```python
    @app.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        request: Request,
        retain: bool = False,
        purge: bool = False,
    ) -> dict[str, str]:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        if retain and purge:
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_REQUEST),
                detail="retain and purge are mutually exclusive",
            )
        if info.state == "dead":
            # Already stopped: purge the corpse and its bundle.
            await launcher.purge(session_id)
            store.delete(session_id)
            registry.remove(session_id)
            return {"status": "purged"}
        await teardown_session(
            session_id=session_id, info=info, launcher=launcher,
            registry=registry, lease=lease, store=store,
            http=request.app.state.http, retain=retain,
        )
        return {"status": "retained" if retain else "released"}
```

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/teardown.py boardfarm3_control/app.py unittests/control/test_teardown.py
git commit -m "feat(control): add the teardown sequence with bundle archiving

Archives a bundle while the agent can still answer, releases devices
gracefully, then stops the container — retaining it on request. The lease is
released and the container stopped regardless of earlier failures, so a dead
agent can never strand a board.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 18: Failure unwinds retain instead of destroying

**Files:**
- Modify: `boardfarm3_control/app.py:79-196` (`create_session`)
- Test: `unittests/control/test_app.py`

**Interfaces:**
- Consumes: `teardown_session()` (Task 17).
- Produces: each unwind path returns an error body containing `session_id` and `diagnostics`, and leaves the session registered as `dead`.

- [ ] **Step 1: Write the failing test**

Append to `unittests/control/test_app.py`:

```python
def test_health_timeout_retains_the_container_and_points_at_diagnostics(
    fake_launcher: FakeLauncher,
    profiles: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A 503 must say where to look, and leave something to look at.

    :param fake_launcher: launcher test double
    :type fake_launcher: FakeLauncher
    :param profiles: profile map
    :type profiles: dict[str, str]
    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    """
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    monkeypatch.setattr(app_module, "_HEALTH_TIMEOUT", 0.2)
    app = create_app(launcher=fake_launcher, profiles=profiles)
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={
                "board_name": "board",
                "runtime_profile": "prplos",
                "payload": {},
            },
        )
        assert response.status_code == 503
        body = response.json()
        session_id = body["detail"]["session_id"]
        assert body["detail"]["diagnostics"] == f"/sessions/{session_id}/diagnostics"

        listed = client.get("/sessions").json()["sessions"]
        assert [s["state"] for s in listed] == ["dead"]

        # Board is free again despite the corpse.
        retry = client.post(
            "/sessions",
            json={
                "board_name": "board",
                "runtime_profile": "prplos",
                "payload": {},
            },
        )
        assert retry.status_code != 409
```

Add `from pathlib import Path` and `from boardfarm3_control import app as app_module` to that test module if absent.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/control/test_app.py::test_health_timeout_retains_the_container_and_points_at_diagnostics -v -p no:randomly`
Expected: FAIL — `detail` is a plain string, and the session is not listed.

- [ ] **Step 3: Implement**

In `boardfarm3_control/app.py`, add a helper inside `create_app` above `create_session`:

```python
    async def _unwind(
        session_id: str,
        info: AgentInfo,
        http: httpx.AsyncClient,
        status: HTTPStatus,
        error: str,
        message: str,
    ) -> HTTPException:
        """Retain the failed container and build the error to raise.

        :param session_id: failed session
        :type session_id: str
        :param info: registry entry for the failed session
        :type info: AgentInfo
        :param http: pooled HTTP client
        :type http: httpx.AsyncClient
        :param status: HTTP status to return
        :type status: HTTPStatus
        :param error: machine-readable error name
        :type error: str
        :param message: human-readable detail
        :type message: str
        :return: the exception the caller should raise
        :rtype: HTTPException
        """
        registry.add(info)
        await teardown_session(
            session_id=session_id, info=info, launcher=launcher,
            registry=registry, lease=lease, store=store, http=http, retain=True,
        )
        return HTTPException(
            status_code=int(status),
            detail={
                "error": error,
                "message": message,
                "session_id": session_id,
                "diagnostics": f"/sessions/{session_id}/diagnostics",
            },
        )
```

Add `request: Request` to `create_session`'s signature and replace each of the three unwind blocks. Health poll:

```python
        if not healthy:
            raise await _unwind(
                session_id, info, request.app.state.http,
                HTTPStatus.SERVICE_UNAVAILABLE,
                "AgentUnhealthy",
                f"agent did not become healthy within {_HEALTH_TIMEOUT} s",
            )
```

Config rejection (both the exception and the non-200 branch):

```python
            raise await _unwind(
                session_id, info, request.app.state.http,
                HTTPStatus.BAD_REQUEST,
                "AgentConfigRejected",
                f"agent rejected config: {cfg.text}",
            )
```

Boot rejection (both branches):

```python
            raise await _unwind(
                session_id, info, request.app.state.http,
                HTTPStatus.BAD_GATEWAY,
                "AgentBootRejected",
                f"agent boot rejected: {boot.status_code}",
            )
```

The container-start failure path keeps its current behaviour — there is no container to retain — but drops the lease as before.

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/app.py unittests/control/test_app.py
git commit -m "feat(control): retain containers on session-create failure

Every unwind path now archives a bundle, retains the stopped container, and
returns session_id plus a diagnostics link instead of destroying the
evidence. The lease is still released immediately.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 19: Control plane diagnostics endpoints

**Files:**
- Modify: `boardfarm3_control/app.py` (two routes, registered **before** the catch-all proxy)
- Test: `unittests/control/test_diagnostics_routes.py` (new)

**Interfaces:**
- Consumes: `archive_bundle()` (Task 17), `DiagnosticsStore` (Task 14), `proxy_request()` (Task 1).
- Produces: `GET /sessions/{sid}/diagnostics` → `application/gzip`; `POST /sessions/{sid}/diagnostics/snapshot` → `{path, size, source, captured_at}`.

Route order matters: FastAPI matches in registration order, and the catch-all `"/sessions/{session_id}/{path:path}"` would otherwise swallow both.

- [ ] **Step 1: Write the failing tests**

Create `unittests/control/test_diagnostics_routes.py`:

```python
"""Three-tier resolution of the control plane diagnostics endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boardfarm3_control.app import create_app
from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.store import DiagnosticsStore

HTTP_OK = 200
HTTP_NOT_FOUND = 404


@pytest.fixture(name="wired")
def wired_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profiles: dict[str, str],
) -> tuple:
    """Return an app with one registered session and a temp store.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path: pytest temporary directory
    :type tmp_path: Path
    :param profiles: profile map
    :type profiles: dict[str, str]
    :return: (app, launcher, store, agent_url)
    :rtype: tuple
    """
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(tmp_path))
    launcher = FakeLauncher()
    info = asyncio.run(launcher.start("s-1", "board", "img", "prplos"))
    app = create_app(launcher=launcher, profiles=profiles)
    return app, launcher, DiagnosticsStore(root=tmp_path), info.agent_url


@respx.mock
def test_tier1_streams_from_a_live_agent(wired: tuple) -> None:
    app, _, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(
            200, content=b"LIVE", headers={"content-type": "application/gzip"},
        ),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content == b"LIVE"


@respx.mock
def test_tier2_serves_the_archived_bundle(wired: tuple) -> None:
    app, _, store, agent_url = wired
    store.write_bundle("s-1", [b"ARCHIVED"])
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content == b"ARCHIVED"


@respx.mock
def test_tier3_builds_from_the_launcher(wired: tuple) -> None:
    app, _, _, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        side_effect=httpx.ConnectError("down"),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/s-1/diagnostics")
    assert response.status_code == HTTP_OK
    assert response.content


def test_unknown_session_is_404(wired: tuple) -> None:
    app, _, _, _ = wired
    with TestClient(app) as client:
        assert client.get("/sessions/nope/diagnostics").status_code == HTTP_NOT_FOUND


@respx.mock
def test_snapshot_reports_its_source(wired: tuple) -> None:
    app, _, store, agent_url = wired
    respx.get(f"{agent_url}/diagnostics/bundle").mock(
        return_value=httpx.Response(200, content=b"SNAP"),
    )
    with TestClient(app) as client:
        body = client.post("/sessions/s-1/diagnostics/snapshot").json()
    assert body["source"] == "agent"
    assert body["size"] == len(b"SNAP")
    assert store.bundle_path("s-1").read_bytes() == b"SNAP"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_diagnostics_routes.py -v -p no:randomly`
Expected: FAIL — the catch-all proxy handles the path and returns 502.

- [ ] **Step 3: Implement**

In `boardfarm3_control/app.py`, add both routes **immediately before** the catch-all `@app.api_route(...)` proxy:

```python
    @app.post("/sessions/{session_id}/diagnostics/snapshot")
    async def diagnostics_snapshot(
        session_id: str, request: Request,
    ) -> dict[str, Any]:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        source = await archive_bundle(
            session_id=session_id, agent_url=info.agent_url,
            launcher=launcher, store=store, http=request.app.state.http,
        )
        if source == "none":
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_GATEWAY),
                detail="agent unreachable and launcher capture produced nothing",
            )
        path = store.bundle_path(session_id)
        return {
            "path": str(path),
            "size": path.stat().st_size,
            "source": source,
            "captured_at": time.time(),
        }

    @app.get("/sessions/{session_id}/diagnostics")
    async def diagnostics(session_id: str, request: Request) -> object:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        attempted: list[str] = []
        # Tier 1 — live agent: stream straight through, nothing buffered.
        if info.state == "live":
            try:
                return await proxy_request(
                    request, info.agent_url, "diagnostics/bundle",
                    client=request.app.state.http, session_id=session_id,
                )
            except HTTPException:
                attempted.append("agent: unreachable")
        else:
            attempted.append("agent: session is dead")
        # Tier 2 — archived bundle.
        if store.has_bundle(session_id):
            return FileResponse(
                store.bundle_path(session_id),
                media_type="application/gzip",
                filename=f"{session_id}-diagnostics.tar.gz",
            )
        attempted.append("archive: no bundle stored")
        # Tier 3 — build one now from the launcher.
        source = await archive_bundle(
            session_id=session_id, agent_url=info.agent_url,
            launcher=launcher, store=store, http=request.app.state.http,
        )
        if source != "none":
            return FileResponse(
                store.bundle_path(session_id),
                media_type="application/gzip",
                filename=f"{session_id}-diagnostics.tar.gz",
            )
        attempted.append("launcher: capture produced nothing")
        raise HTTPException(
            status_code=int(HTTPStatus.NOT_FOUND),
            detail={"error": "NoDiagnostics", "attempted": attempted},
        )
```

Add the imports: `from fastapi.responses import FileResponse`, `from boardfarm3_control.store import DiagnosticsStore`, `from boardfarm3_control.teardown import archive_bundle, teardown_session`.

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/app.py unittests/control/test_diagnostics_routes.py
git commit -m "feat(control): add three-tier diagnostics endpoints

GET /sessions/{sid}/diagnostics resolves live agent -> archived bundle ->
launcher capture. POST .../diagnostics/snapshot forces an archive now and
works on a healthy ready session.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 20: The corpse reaper

**Files:**
- Create: `boardfarm3_control/reaper.py`
- Modify: `boardfarm3_control/app.py` (start/stop the task in the lifespan)
- Test: `unittests/control/test_reaper.py` (new)

**Interfaces:**
- Consumes: `DiagnosticsStore` (Task 14), launcher `purge()` (Task 13), `registry.mark_dead` (Task 16).
- Produces: `reap_once(*, launcher, registry, store, now: float) -> dict[str, int]` returning `{"containers": n, "bundles": n, "bytes": n}`, and `run_reaper(...)` as the background loop.

**The reaper must never call `stop()`.** It operates only on entries already in state `dead`.

- [ ] **Step 1: Write the failing tests**

Create `unittests/control/test_reaper.py`:

```python
"""Corpse and bundle reaping."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardfarm3_control.launcher import FakeLauncher
from boardfarm3_control.reaper import reap_once
from boardfarm3_control.registry import SessionRegistry
from boardfarm3_control.store import DiagnosticsStore

_DAY = 86_400


async def _dead_session(launcher: FakeLauncher, registry: SessionRegistry) -> None:
    info = await launcher.start("s-1", "board", "img", "prplos")
    registry.add(info)
    await launcher.stop("s-1", remove=False)
    registry.mark_dead("s-1", ended_at=0.0)


@pytest.mark.asyncio
async def test_purges_a_corpse_past_the_ttl(tmp_path: Path) -> None:
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    await _dead_session(launcher, registry)
    result = await reap_once(
        launcher=launcher, registry=registry, store=store, now=2 * _DAY,
    )
    assert result["containers"] == 1
    assert await launcher.list_sessions() == []
    assert registry.get("s-1") is None


@pytest.mark.asyncio
async def test_keeps_a_corpse_within_the_ttl(tmp_path: Path) -> None:
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    await _dead_session(launcher, registry)
    result = await reap_once(
        launcher=launcher, registry=registry, store=store, now=60.0,
    )
    assert result["containers"] == 0
    assert registry.get("s-1") is not None


@pytest.mark.asyncio
async def test_never_touches_a_live_session(tmp_path: Path) -> None:
    """The reaper must be incapable of reaching a running agent."""
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    info = await launcher.start("s-live", "board", "img", "prplos")
    registry.add(info)
    await reap_once(
        launcher=launcher, registry=registry, store=store, now=10 * _DAY,
    )
    assert registry.get("s-live") is not None
    assert [s.session_id for s in await launcher.list_sessions()] == ["s-live"]


@pytest.mark.asyncio
async def test_size_cap_evicts_oldest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDFARM_BUNDLE_MAX_BYTES", "40")
    launcher, registry = FakeLauncher(), SessionRegistry()
    store = DiagnosticsStore(root=tmp_path)
    store.write_meta("s-old", {"ended_at": 1.0})
    store.write_bundle("s-old", [b"x" * 30])
    store.write_meta("s-new", {"ended_at": 100.0})
    store.write_bundle("s-new", [b"y" * 30])
    await reap_once(launcher=launcher, registry=registry, store=store, now=200.0)
    assert not store.has_bundle("s-old")
    assert store.has_bundle("s-new")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/control/test_reaper.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: boardfarm3_control.reaper`.

- [ ] **Step 3: Implement**

Create `boardfarm3_control/reaper.py`:

```python
"""Background purge of stopped containers and aged diagnostics bundles.

This module operates only on containers that have *already* stopped. It never
calls ``Launcher.stop()`` and can therefore not terminate a live session.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3_control.launcher import Launcher
    from boardfarm3_control.registry import SessionRegistry
    from boardfarm3_control.store import DiagnosticsStore

_log = logging.getLogger(__name__)

_CORPSE_TTL = "BOARDFARM_CORPSE_TTL"
_BUNDLE_TTL = "BOARDFARM_BUNDLE_TTL"
_MAX_BYTES = "BOARDFARM_BUNDLE_MAX_BYTES"
_INTERVAL = "BOARDFARM_REAP_INTERVAL"


async def reap_once(
    *,
    launcher: Launcher,
    registry: SessionRegistry,
    store: DiagnosticsStore,
    now: float,
) -> dict[str, int]:
    """Run one reaping pass.

    :param launcher: launcher used to purge stopped containers
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param store: diagnostics store
    :type store: DiagnosticsStore
    :param now: current time, injected for testability
    :type now: float
    :return: counts of purged containers, deleted bundles, and bytes reclaimed
    :rtype: dict[str, int]
    """
    corpse_ttl = float(os.environ.get(_CORPSE_TTL, "86400"))
    bundle_ttl = float(os.environ.get(_BUNDLE_TTL, "604800"))
    max_bytes = int(os.environ.get(_MAX_BYTES, str(20 * 1024**3)))

    containers = 0
    page, _ = registry.list_page(0, 10_000)
    for info in page:
        if info.state != "dead" or info.ended_at is None:
            continue
        age = now - info.ended_at
        if age <= corpse_ttl:
            continue
        await launcher.purge(info.session_id)
        registry.remove(info.session_id)
        containers += 1
        _log.info(
            "reaped container for %s (age %.0fs)", info.session_id, age,
        )

    bundles = 0
    reclaimed = 0
    aged: list[tuple[float, str, int]] = []
    for session_id in store.list_sessions():
        meta = store.read_meta(session_id) or {}
        ended_at = float(meta.get("ended_at") or 0.0)
        size = (
            store.bundle_path(session_id).stat().st_size
            if store.has_bundle(session_id)
            else 0
        )
        if now - ended_at > bundle_ttl:
            store.delete(session_id)
            bundles += 1
            reclaimed += size
            _log.info("reaped bundle for %s (%d bytes)", session_id, size)
            continue
        aged.append((ended_at, session_id, size))

    # Size cap: evict oldest-first until under the limit.
    total = store.total_bytes()
    for _, session_id, size in sorted(aged):
        if total <= max_bytes:
            break
        store.delete(session_id)
        total -= size
        bundles += 1
        reclaimed += size
        _log.info(
            "evicted bundle for %s to stay under the %d byte cap",
            session_id,
            max_bytes,
        )

    return {"containers": containers, "bundles": bundles, "bytes": reclaimed}


async def run_reaper(
    *,
    launcher: Launcher,
    registry: SessionRegistry,
    store: DiagnosticsStore,
) -> None:
    """Run :func:`reap_once` on a fixed interval until cancelled.

    :param launcher: launcher used to purge stopped containers
    :type launcher: Launcher
    :param registry: session registry
    :type registry: SessionRegistry
    :param store: diagnostics store
    :type store: DiagnosticsStore
    """
    interval = float(os.environ.get(_INTERVAL, "900"))
    while True:
        await asyncio.sleep(interval)
        try:
            await reap_once(
                launcher=launcher, registry=registry, store=store, now=time.time(),
            )
        except Exception:  # noqa: BLE001
            _log.exception("reaper pass failed")
```

In `boardfarm3_control/app.py`, start and cancel it in the lifespan:

```python
        app.state.reaper = asyncio.create_task(
            run_reaper(launcher=launcher, registry=registry, store=store),
        )
        yield
        app.state.reaper.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.reaper
        await app.state.http.aclose()
```

Add `from contextlib import asynccontextmanager, suppress` and `from boardfarm3_control.reaper import run_reaper`.

- [ ] **Step 4: Run the tests**

Run: `pytest unittests/control -v -p no:randomly && nox -s lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/reaper.py boardfarm3_control/app.py unittests/control/test_reaper.py
git commit -m "feat(control): reap aged corpses and bundles

Purges stopped containers past CORPSE_TTL and bundles past BUNDLE_TTL, with
an oldest-first size cap. Operates only on already-stopped containers and
never calls stop(), so it cannot reach a live session.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

# Phase 4 — Integration

### Task 21: End-to-end retention and diagnostics

**Files:**
- Modify: `integrationtests/control/test_proxy_and_lifecycle.py`
- Test: same file

**Interfaces:**
- Consumes: everything above.
- Produces: no new code — proof that the phases compose.

These tests run against `integrationtests/control/conftest.py`, which uses `ProcessLauncher` (real agent subprocesses, no Docker) with profile map `{"local": "unused-image"}` and board `integration-board`. The available fixtures are `control_client` (an `httpx.AsyncClient` bound to the control plane over ASGI) and `session` (a created session id). There is no `board_name` or `VALID_PAYLOAD` fixture — use the literals below.

- [ ] **Step 1: Fix the pre-existing conftest signature break**

`_ReadyProcessLauncher.start()` in `integrationtests/control/conftest.py:60-71` overrides `start` with four parameters, but `create_app` calls `launcher.start(..., agent_env=...)` (`boardfarm3_control/app.py:98-101`). Verify with `pytest integrationtests/control -x -p no:randomly`; if it raises `TypeError: start() got an unexpected keyword argument 'agent_env'`, add the parameter and forward it:

```python
    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,
        runtime_profile: str,
        agent_env: dict[str, str] | None = None,
    ) -> AgentInfo:
        info = await super().start(
            session_id, board_name, image, runtime_profile, agent_env,
        )
        await _wait_for_health(info.host_port)
        return info
```

Also point the store and artifact root at a temp location for the whole integration run, by adding to `conftest.py`:

```python
@pytest.fixture(autouse=True)
def _isolated_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Keep integration artifacts out of /var, which is not writable in CI.

    :param monkeypatch: pytest monkeypatch fixture
    :type monkeypatch: pytest.MonkeyPatch
    :param tmp_path_factory: pytest temp directory factory
    :type tmp_path_factory: pytest.TempPathFactory
    """
    root = tmp_path_factory.mktemp("bf-integration")
    monkeypatch.setenv("BOARDFARM_CONTROL_STORE", str(root / "control"))
    monkeypatch.setenv("BOARDFARM_ARTIFACT_DIR", str(root / "artifacts"))
    # Keep the SSE keepalive test from waiting the 15 s production default.
    monkeypatch.setenv("BOARDFARM_SSE_KEEPALIVE", "1")
```

- [ ] **Step 2: Write the failing tests**

Append to `integrationtests/control/test_proxy_and_lifecycle.py`:

```python
async def test_diagnostics_bundle_on_a_healthy_session(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """A snapshot must work on a ready session, before anything is torn down."""
    snap = await control_client.post(f"/sessions/{session}/diagnostics/snapshot")
    assert snap.status_code == 200, snap.text
    assert snap.json()["source"] == "agent"

    bundle = await control_client.get(f"/sessions/{session}/diagnostics")
    assert bundle.status_code == 200
    assert bundle.content[:2] == b"\x1f\x8b"
    with tarfile.open(fileobj=io.BytesIO(bundle.content), mode="r:gz") as archive:
        names = archive.getnames()
    assert "manifest.json" in names
    assert "jobs.json" in names
    assert "threads.txt" in names


async def test_failed_create_retains_evidence_and_frees_the_board(
    control_client: httpx.AsyncClient,
) -> None:
    """A failed session must leave evidence and must not block its board."""
    # An inventory the agent cannot resolve makes POST /session/config fail,
    # exercising the config-rejection unwind path.
    bad = await control_client.post(
        "/sessions",
        json={
            "board_name": "integration-board",
            "runtime_profile": "local",
            "payload": {"inventory": {}, "env": {}},
            "options": {"skip_boot": True},
        },
    )
    assert bad.status_code in (400, 502, 503), bad.text
    session_id = bad.json()["detail"]["session_id"]
    assert bad.json()["detail"]["diagnostics"] == (
        f"/sessions/{session_id}/diagnostics"
    )

    listed = (await control_client.get("/sessions")).json()["sessions"]
    assert any(
        s["session_id"] == session_id and s["state"] == "dead" for s in listed
    )

    bundle = await control_client.get(f"/sessions/{session_id}/diagnostics")
    assert bundle.status_code == 200
    assert bundle.content[:2] == b"\x1f\x8b"

    # The corpse must not block the board.
    good = await control_client.post(
        "/sessions",
        json={
            "board_name": "integration-board",
            "runtime_profile": "local",
            "payload": {
                "inventory": {"integration-board": {"devices": []}},
                "env": {"environment_def": {}},
            },
            "options": {"skip_boot": True},
        },
    )
    assert good.status_code == 202, good.text
    live_id = good.json()["session_id"]

    assert (
        await control_client.delete(f"/sessions/{session_id}")
    ).status_code == 200
    assert (await control_client.delete(f"/sessions/{live_id}")).status_code == 200


async def test_async_mode_round_trips_through_the_control_plane(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """?mode=async must survive the proxy and yield a pollable job."""
    resp = await control_client.post(
        f"/sessions/{session}/session/boot?mode=async",
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["boot_job_id"]
    assert job_id

    job = await control_client.get(f"/sessions/{session}/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["job_id"] == job_id


async def test_sse_console_stream_survives_a_quiet_period(
    control_client: httpx.AsyncClient,
    session: str,
) -> None:
    """The old 5 s proxy read timeout severed a quiet stream; it must not now."""
    received: list[str] = []
    async with control_client.stream(
        "GET", f"/sessions/{session}/console/stream",
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            received.append(line)
            # A keepalive proves the stream outlived the old ceiling.
            if line.startswith(": keepalive") or len(received) > 200:
                break
    assert any(line.startswith(": keepalive") for line in received)
```

Add `import io` and `import tarfile` to the module's imports. Set `BOARDFARM_SSE_KEEPALIVE=1` in the `_isolated_store` fixture so the last test does not wait 15 s.

- [ ] **Step 3: Run the tests and fix what they expose**

Run: `pytest integrationtests/control -v -p no:randomly`

No new production code is planned here. If a test fails, the defect is in Tasks 13-20 — fix it there and re-run. Do **not** weaken an assertion to make it pass. The one exception is the conftest signature fix in Step 1, which is a pre-existing break.

- [ ] **Step 4: Run the full suite**

Run: `pytest unittests -v && pytest integrationtests/control -v && nox -s lint && nox -s pylint && pre-commit run --all-files`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrationtests/control/test_proxy_and_lifecycle.py integrationtests/control/conftest.py
git commit -m "test(control): end-to-end retention and diagnostics coverage

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

## Spec Coverage

| Spec section | Task(s) |
|---|---|
| §5.1-5.2 teardown matrix | 17 |
| §5.3 create failure unwinds | 18 |
| §5.4 corpse reaper | 20 |
| §5.5 restart correctness | 15 |
| §6 Launcher protocol | 13 |
| §7.1 always-on console logs | 4 |
| §7.2 tracebacks (three places) | 6, 7, 8 |
| §7.3 agent.log | 5 |
| §8 diagnostics bundle | 12 |
| §8.1 redaction | 11, 12 |
| §9 control diagnostics surface + store | 14, 19 |
| §10.1 proxy timeouts + error frames | 1, 2 |
| §10.2 SSE keepalive | 3 |
| §10.3 liveness + SessionResponse.liveness | 9, 16 |
| §10.4 thread stacks | 10 |
| §11 error handling | 17 (best-effort), 19 (404 tiers), 17 (mutually-exclusive 400) |
| §12 testing | every task, plus 21 |
| §13 configuration reference | 1, 3, 4, 9, 14, 20 |

`?mode=async` (spec §4, "rejected alternatives") needs no implementation — it already exists. Task 21 asserts it round-trips through the control plane.

## Deviations from the Spec

Two, both found while writing the plan. Neither changes a decision; both make a stated one survive contact with a non-root agent.

1. **`BOARDFARM_ARTIFACT_DIR` gains a fallback (Task 4).** Spec §13 gives the default as `/var/log/boardfarm` flat. Making console logs unconditional means `BoardfarmPexpect._configure_logging()` calls `mkdir(parents=True)` on every connection, so under `ProcessLauncher` — local development and all of `integrationtests/control/` — an unprivileged agent would hit `PermissionError` and crash every device connection. The root now falls back to `<tempdir>/boardfarm` when `/var/log` is not writable. `DockerLauncher` agents run as root and are unaffected.
2. **Artifact layout gains a `console/` subdirectory (Task 4).** Spec §8 lists `agent.log` and `console-logs/` as sibling bundle members. Writing both into one flat directory would nest `agent.log` inside the `console-logs` archive member. The agent now writes `{artifact_dir}/agent.log` and `{artifact_dir}/console/`, which produces exactly the member layout §8 specifies.

Both are worth folding back into the spec's §7.1 and §13 before implementation starts.
