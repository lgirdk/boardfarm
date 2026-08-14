# Skip-Boot Default and PID/URL Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default session creation to skip-boot init, expose numeric PID and stored agent URL on every session, and give `ProcessLauncher` state-file persistence for orphan cleanup on restart.

**Architecture:** Four focused changes — models gain new fields; launchers populate `pid`/`agent_url`; `ProcessLauncher` writes a JSON state file and kills orphaned PIDs on startup; `app.py` builds the correct boot query string and surfaces `booted` in responses.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, `httpx`/`respx` (tests), `pytest-asyncio`

## Global Constraints

- Python 3.11–3.13 compatibility; no 3.12-only syntax
- All four linters must pass: `ruff`, `flake8`, `mypy --disallow-untyped-defs`, `pylint`
- Sphinx-style docstrings on all public methods (`:param:` / `:type:` / `:return:` / `:rtype:`)
- Conventional commit messages (`feat(control):`, `fix(control):`, etc.)
- Tests live in `unittests/control/` (unit) and `integrationtests/control/` (integration)
- Run unit tests with: `pytest unittests/control/ -v`
- State file default path: `/tmp/boardfarm-control-sessions.json`; overridable via `BOARDFARM_CONTROL_STATE_FILE` env var

---

## File Map

| File | Change |
|---|---|
| `boardfarm3_control/models.py` | Add `pid`, `agent_url` to `AgentInfo`; add `boot` to `SessionCreate`; add `booted`, `agent_url`, `pid` to `SessionResponse` |
| `boardfarm3_control/launcher.py` | `FakeLauncher`/`DockerLauncher`: populate new fields; `ProcessLauncher`: state file + orphan cleanup |
| `boardfarm3_control/registry.py` | Remove `agent_url()` method; replace computed-URL usages with `info.agent_url` |
| `boardfarm3_control/app.py` | Build skip_boot query param; derive `booted` from agent state; use `info.agent_url` |
| `unittests/control/test_app.py` | Update existing tests; add skip_boot and `boot=True` tests |
| `unittests/control/test_registry.py` | Update `_info()` helper; replace `agent_url()` calls; update rebuild test |
| `unittests/control/test_launcher.py` | Assert `pid` and `agent_url` on `FakeLauncher`; add `ProcessLauncher` state file tests |

---

### Task 1: Extend models

**Files:**
- Modify: `boardfarm3_control/models.py`
- Test: `unittests/control/test_launcher.py` (helper update only — no new test file needed yet)

**Interfaces:**
- Produces:
  - `AgentInfo.pid: int | None`
  - `AgentInfo.agent_url: str`
  - `SessionCreate.boot: bool = False`
  - `SessionResponse.booted: bool`
  - `SessionResponse.agent_url: str`
  - `SessionResponse.pid: int | None`

- [ ] **Step 1: Write failing test for new AgentInfo fields**

In `unittests/control/test_launcher.py`, add at the top of the file (after existing imports):

```python
from boardfarm3_control.models import AgentInfo


def test_agent_info_has_pid_and_agent_url() -> None:
    info = AgentInfo(
        session_id="s-aaa",
        board_name="board-1",
        runtime_profile="prplos",
        container_id="c-1",
        host_port=18000,
        created_at=0.0,
        pid=None,
        agent_url="http://localhost:18000",
    )
    assert info.pid is None
    assert info.agent_url == "http://localhost:18000"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest unittests/control/test_launcher.py::test_agent_info_has_pid_and_agent_url -v
```

Expected: FAIL — `AgentInfo` does not accept `pid` or `agent_url`

- [ ] **Step 3: Extend `AgentInfo` in `boardfarm3_control/models.py`**

Replace the `AgentInfo` class with:

```python
class AgentInfo(BaseModel):
    """Per-session runtime info stored in the registry and returned by launchers."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    board_name: str
    runtime_profile: str
    container_id: str
    host_port: int
    created_at: float
    pid: int | None = None
    agent_url: str = ""
```

- [ ] **Step 4: Write failing test for `SessionCreate.boot` field**

In `unittests/control/test_app.py`, add:

```python
def test_session_create_boot_defaults_to_false() -> None:
    from boardfarm3_control.models import SessionCreate

    sc = SessionCreate(board_name="b", runtime_profile="p", payload={})
    assert sc.boot is False


def test_session_create_boot_true_accepted() -> None:
    from boardfarm3_control.models import SessionCreate

    sc = SessionCreate(board_name="b", runtime_profile="p", payload={}, boot=True)
    assert sc.boot is True
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
pytest unittests/control/test_app.py::test_session_create_boot_defaults_to_false unittests/control/test_app.py::test_session_create_boot_true_accepted -v
```

Expected: FAIL — `SessionCreate` does not have a `boot` field

- [ ] **Step 6: Add `boot` to `SessionCreate` and new fields to `SessionResponse`**

Replace `SessionCreate` and `SessionResponse` in `boardfarm3_control/models.py`:

```python
class SessionCreate(BaseModel):
    """Body of POST /sessions."""

    model_config = ConfigDict(extra="forbid")

    board_name: str
    runtime_profile: str
    payload: dict[str, Any]
    options: dict[str, Any] = Field(default_factory=dict)
    boot: bool = False


class SessionResponse(BaseModel):
    """Response body for POST /sessions and per-item in GET /sessions."""

    session_id: str
    board_name: str
    runtime_profile: str
    state: str
    boot_job_id: str | None = None
    booted: bool = False
    agent_url: str = ""
    pid: int | None = None
    created_at: float
    last_activity: float | None = None
```

- [ ] **Step 7: Run all new model tests**

```bash
pytest unittests/control/test_launcher.py::test_agent_info_has_pid_and_agent_url unittests/control/test_app.py::test_session_create_boot_defaults_to_false unittests/control/test_app.py::test_session_create_boot_true_accepted -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add boardfarm3_control/models.py unittests/control/test_launcher.py unittests/control/test_app.py
git commit -m "feat(control): extend models with boot flag, pid, agent_url, and booted fields"
```

---

### Task 2: Update FakeLauncher and DockerLauncher

**Files:**
- Modify: `boardfarm3_control/launcher.py` (FakeLauncher and DockerLauncher sections only)
- Test: `unittests/control/test_launcher.py`

**Interfaces:**
- Consumes: `AgentInfo.pid`, `AgentInfo.agent_url` from Task 1
- Produces:
  - `FakeLauncher.start()` → `AgentInfo` with `pid=None`, `agent_url="http://localhost:{port}"`
  - `DockerLauncher.start()` → `AgentInfo` with `pid=None`, `agent_url="http://localhost:{host_port}"`
  - `DockerLauncher.list_sessions()` → `AgentInfo` with `pid=None`, `agent_url="http://localhost:{host_port}"`

- [ ] **Step 1: Write failing tests for FakeLauncher new fields**

Add to `unittests/control/test_launcher.py`:

```python
@pytest.mark.asyncio
async def test_fake_launcher_start_sets_pid_none_and_agent_url() -> None:
    launcher = FakeLauncher()
    info = await launcher.start("s-abc", "board-1", "agent:latest", "prplos")
    assert info.pid is None
    assert info.agent_url == "http://localhost:18000"


@pytest.mark.asyncio
async def test_fake_launcher_agent_url_increments_with_port() -> None:
    launcher = FakeLauncher()
    a = await launcher.start("s-aaa", "board-1", "img", "p")
    b = await launcher.start("s-bbb", "board-2", "img", "p")
    assert a.agent_url == "http://localhost:18000"
    assert b.agent_url == "http://localhost:18001"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest unittests/control/test_launcher.py::test_fake_launcher_start_sets_pid_none_and_agent_url unittests/control/test_launcher.py::test_fake_launcher_agent_url_increments_with_port -v
```

Expected: FAIL — `AgentInfo` returned by `FakeLauncher.start()` has no `agent_url`

- [ ] **Step 3: Update `FakeLauncher.start()` in `boardfarm3_control/launcher.py`**

Replace the `return AgentInfo(...)` block inside `FakeLauncher.start()`:

```python
        info = AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=f"fake-{session_id}",
            host_port=port,
            created_at=time.time(),
            pid=None,
            agent_url=f"http://localhost:{port}",
        )
```

- [ ] **Step 4: Update `DockerLauncher.start()` in `boardfarm3_control/launcher.py`**

Replace the `return AgentInfo(...)` block inside `DockerLauncher.start()`:

```python
        return AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=container.id,
            host_port=host_port,
            created_at=created_at,
            pid=None,
            agent_url=f"http://localhost:{host_port}",
        )
```

- [ ] **Step 5: Update `DockerLauncher.list_sessions()` in `boardfarm3_control/launcher.py`**

Replace the `result.append(AgentInfo(...))` block inside `DockerLauncher.list_sessions()`:

```python
            result.append(
                AgentInfo(
                    session_id=labels[self._LABEL_SESSION],
                    board_name=labels[self._LABEL_BOARD],
                    runtime_profile=labels[self._LABEL_PROFILE],
                    container_id=container.id,
                    host_port=host_port,
                    created_at=float(labels.get(self._LABEL_CREATED, 0)),
                    pid=None,
                    agent_url=f"http://localhost:{host_port}",
                ),
            )
```

- [ ] **Step 6: Run all launcher tests**

```bash
pytest unittests/control/test_launcher.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add boardfarm3_control/launcher.py unittests/control/test_launcher.py
git commit -m "feat(control): populate pid and agent_url in FakeLauncher and DockerLauncher"
```

---

### Task 3: ProcessLauncher state file and orphan cleanup

**Files:**
- Modify: `boardfarm3_control/launcher.py` (ProcessLauncher section only)
- Test: `unittests/control/test_launcher.py`

**Interfaces:**
- Consumes: `AgentInfo.pid`, `AgentInfo.agent_url`, `AgentInfo.model_dump()`, `AgentInfo.model_validate()` from Task 1
- Produces:
  - `ProcessLauncher.start()` → `AgentInfo` with `pid=proc.pid`, `agent_url="http://localhost:{port}"`
  - `ProcessLauncher.stop()` → removes session from state file
  - `ProcessLauncher.list_sessions()` → on first call reads state file, kills living orphaned PIDs, rewrites file empty, returns `[]`; on subsequent calls returns live `_sessions`

- [ ] **Step 1: Write failing tests for ProcessLauncher**

Add to `unittests/control/test_launcher.py`:

```python
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

from boardfarm3_control.launcher import ProcessLauncher


@pytest.mark.asyncio
async def test_process_launcher_start_sets_pid_and_agent_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    launcher = ProcessLauncher()
    info = await launcher.start("s-proc", "board-1", "ignored", "prplos")
    assert isinstance(info.pid, int)
    assert info.pid > 0
    assert info.agent_url == f"http://localhost:{info.host_port}"
    await launcher.stop("s-proc")


@pytest.mark.asyncio
async def test_process_launcher_start_writes_state_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    launcher = ProcessLauncher()
    info = await launcher.start("s-proc", "board-1", "ignored", "prplos")
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert "s-proc" in data
    assert data["s-proc"]["pid"] == info.pid
    await launcher.stop("s-proc")


@pytest.mark.asyncio
async def test_process_launcher_stop_removes_from_state_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    launcher = ProcessLauncher()
    await launcher.start("s-proc", "board-1", "ignored", "prplos")
    await launcher.stop("s-proc")
    data = json.loads(state_file.read_text())
    assert "s-proc" not in data


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_kills_orphaned_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh ProcessLauncher with a state file containing a live PID kills it."""
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))

    # Start a real process to use as an orphan target
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)",
    )
    orphan_pid = proc.pid

    # Write it into the state file as if a previous control plane left it
    state_file.write_text(json.dumps({
        "s-orphan": {
            "session_id": "s-orphan",
            "board_name": "board-x",
            "runtime_profile": "p",
            "container_id": str(orphan_pid),
            "host_port": 19999,
            "created_at": 0.0,
            "pid": orphan_pid,
            "agent_url": "http://localhost:19999",
        }
    }))

    # A fresh launcher should kill the orphan when list_sessions() is called
    fresh_launcher = ProcessLauncher()
    sessions = await fresh_launcher.list_sessions()

    assert sessions == []
    # PID should now be dead
    try:
        os.kill(orphan_pid, 0)
        is_dead = False
    except ProcessLookupError:
        is_dead = True
    assert is_dead, f"orphaned PID {orphan_pid} was not killed"


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_missing_state_file_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "nonexistent.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    launcher = ProcessLauncher()
    sessions = await launcher.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_process_launcher_list_sessions_corrupt_state_file_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "sessions.json"
    monkeypatch.setenv("BOARDFARM_CONTROL_STATE_FILE", str(state_file))
    state_file.write_text("not valid json {{{")
    launcher = ProcessLauncher()
    sessions = await launcher.list_sessions()
    assert sessions == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest unittests/control/test_launcher.py::test_process_launcher_start_sets_pid_and_agent_url unittests/control/test_launcher.py::test_process_launcher_start_writes_state_file -v
```

Expected: FAIL — `ProcessLauncher.start()` does not set `pid` or `agent_url`

- [ ] **Step 3: Rewrite `ProcessLauncher` in `boardfarm3_control/launcher.py`**

Add these imports at the top of `launcher.py` (after existing imports):

```python
import json
import logging
import os
import signal
from pathlib import Path

_log = logging.getLogger(__name__)

_DEFAULT_STATE_FILE = "/tmp/boardfarm-control-sessions.json"
```

Replace the entire `ProcessLauncher` class:

```python
class ProcessLauncher:
    """Launcher that starts boardfarm3.api as local subprocesses.

    No Docker daemon required — intended for local development and
    integration testing.
    """

    def __init__(self) -> None:
        """Initialise an empty process launcher."""
        self._sessions: dict[str, tuple[asyncio.subprocess.Process, AgentInfo]] = {}
        self._started = False  # True after first list_sessions() call

    def _state_path(self) -> Path:
        return Path(os.environ.get("BOARDFARM_CONTROL_STATE_FILE", _DEFAULT_STATE_FILE))

    def _save_state(self) -> None:
        path = self._state_path()
        data = {sid: info.model_dump() for sid, (_, info) in self._sessions.items()}
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    async def start(
        self,
        session_id: str,
        board_name: str,
        image: str,  # noqa: ARG002
        runtime_profile: str,
    ) -> AgentInfo:
        """Start a boardfarm3.api subprocess on a free local port.

        :param session_id: unique session identifier
        :type session_id: str
        :param board_name: board this agent will own
        :type board_name: str
        :param image: ignored — no container image is used
        :type image: str
        :param runtime_profile: profile key stored in AgentInfo
        :type runtime_profile: str
        :return: agent info with the subprocess pid as container_id
        :rtype: AgentInfo
        """
        from boardfarm3_control.models import AgentInfo

        host_port = _free_port()
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "boardfarm3.api",
            env={
                **os.environ,
                "BOARDFARM_SESSION_ID": session_id,
                "BOARDFARM_BOARD_NAME": board_name,
                "BOARDFARM_AGENT_PORT": str(host_port),
            },
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        info = AgentInfo(
            session_id=session_id,
            board_name=board_name,
            runtime_profile=runtime_profile,
            container_id=str(proc.pid),
            host_port=host_port,
            created_at=time.time(),
            pid=proc.pid,
            agent_url=f"http://localhost:{host_port}",
        )
        self._sessions[session_id] = (proc, info)
        self._save_state()
        return info

    async def stop(self, session_id: str) -> None:
        """Terminate the subprocess for a session.

        Sends SIGTERM and waits up to 5 s; kills if it does not exit.

        :param session_id: session whose subprocess to stop
        :type session_id: str
        """
        entry = self._sessions.pop(session_id, None)
        if entry is None:
            return
        proc, _ = entry
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._save_state()

    async def list_sessions(self) -> list[AgentInfo]:
        """Return info for all running agent sessions.

        On the first call, reads the state file and kills any orphaned PIDs
        left by a previous control plane instance.

        :return: list of agent infos
        :rtype: list[AgentInfo]
        """
        if not self._started:
            self._started = True
            await self._cleanup_orphans()
        return [info for _, info in self._sessions.values()]

    async def _cleanup_orphans(self) -> None:
        path = self._state_path()
        if not path.exists():
            return
        try:
            data: dict[str, object] = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            _log.warning("boardfarm control: state file corrupt, ignoring: %s", path)
            return

        loop = asyncio.get_running_loop()
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            pid = entry.get("pid")
            if not isinstance(pid, int):
                continue
            try:
                os.kill(pid, 0)  # probe — raises ProcessLookupError if dead
            except ProcessLookupError:
                continue  # already gone

            # PID is alive — terminate it
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue

            deadline = loop.time() + 5.0
            while loop.time() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                await asyncio.sleep(0.1)
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        # Rewrite state file — all orphans cleaned up, _sessions is empty
        self._save_state()
```

- [ ] **Step 4: Run all ProcessLauncher tests**

```bash
pytest unittests/control/test_launcher.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add boardfarm3_control/launcher.py unittests/control/test_launcher.py
git commit -m "feat(control): add ProcessLauncher state file persistence and orphan cleanup"
```

---

### Task 4: Update SessionRegistry

**Files:**
- Modify: `boardfarm3_control/registry.py`
- Test: `unittests/control/test_registry.py`

**Interfaces:**
- Consumes: `AgentInfo.agent_url` from Task 1
- Produces: `agent_url()` method **removed**; callers use `info.agent_url` directly

- [ ] **Step 1: Update the `_info()` helper in `test_registry.py`**

The factory helper used throughout the registry tests does not yet pass `pid` or `agent_url`. Replace the `_info` helper at the top of `unittests/control/test_registry.py`:

```python
def _info(sid: str, port: int = 18000, board: str = "board-1") -> AgentInfo:
    return AgentInfo(
        session_id=sid,
        board_name=board,
        runtime_profile="prplos",
        container_id=f"c-{sid}",
        host_port=port,
        created_at=0.0,
        pid=None,
        agent_url=f"http://localhost:{port}",
    )
```

- [ ] **Step 2: Replace `agent_url()` tests with direct field access**

In `unittests/control/test_registry.py`, replace the two `agent_url` method tests:

```python
def test_agent_info_agent_url_field() -> None:
    reg = SessionRegistry()
    reg.add(_info("s-aaa", port=19999))
    info = reg.get("s-aaa")
    assert info is not None
    assert info.agent_url == "http://localhost:19999"


def test_get_unknown_session_returns_none() -> None:
    reg = SessionRegistry()
    assert reg.get("s-unknown") is None
```

Also update the rebuild test at the bottom — replace `reg.agent_url("s-aaa")` with `reg.get("s-aaa").agent_url`:

```python
@pytest.mark.asyncio
async def test_rebuild_from_launcher() -> None:
    launcher = FakeLauncher()
    await launcher.start("s-aaa", "board-1", "img", "prplos")
    await launcher.start("s-bbb", "board-2", "img", "prplos")
    reg = SessionRegistry()
    await reg.rebuild(launcher)
    assert reg.get("s-aaa") is not None
    assert reg.get("s-bbb") is not None
    info = reg.get("s-aaa")
    assert info is not None
    assert info.agent_url == "http://localhost:18000"
```

- [ ] **Step 3: Run registry tests and confirm which ones break**

```bash
pytest unittests/control/test_registry.py -v
```

Expected: `test_agent_url_format` and `test_agent_url_unknown_returns_none` FAIL (method still exists but tests replaced); others PASS

- [ ] **Step 4: Remove `agent_url()` from `SessionRegistry` in `registry.py`**

Delete the entire `agent_url()` method from `boardfarm3_control/registry.py`:

```python
    def agent_url(self, session_id: str) -> str | None:
        """Return the base URL for the agent serving this session.
        ...
        """
        info = self._sessions.get(session_id)
        if info is None:
            return None
        return f"http://localhost:{info.host_port}"
```

- [ ] **Step 5: Run registry tests**

```bash
pytest unittests/control/test_registry.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add boardfarm3_control/registry.py unittests/control/test_registry.py
git commit -m "refactor(control): remove SessionRegistry.agent_url() in favour of AgentInfo.agent_url"
```

---

### Task 5: Update `app.py` — boot query param, booted field, agent_url usage

**Files:**
- Modify: `boardfarm3_control/app.py`
- Test: `unittests/control/test_app.py`

**Interfaces:**
- Consumes: `SessionCreate.boot`, `AgentInfo.agent_url`, `SessionResponse.booted`, `SessionResponse.agent_url`, `SessionResponse.pid` from Task 1

- [ ] **Step 1: Write failing tests for the new default (skip_boot) behaviour**

Add to `unittests/control/test_app.py`:

```python
@respx.mock
def test_post_sessions_default_skip_boot_returns_ready() -> None:
    """Default boot=False must call /session/boot?skip_boot=true and return state ready."""
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={"state": "ready"}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={"state": "configured"}))
    respx.post(_AGENT_BOOT).mock(
        return_value=httpx.Response(202, json={"boot_job_id": "j-skip"}),
    )
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["state"] == "ready"
    assert data["booted"] is False

    # Confirm the boot request had skip_boot=true in the query string
    boot_call = respx.calls.last
    assert "skip_boot=true" in str(boot_call.request.url)


@respx.mock
def test_post_sessions_boot_true_returns_booting() -> None:
    """boot=True must call /session/boot without skip_boot and return state booting."""
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={"state": "ready"}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={"state": "configured"}))
    respx.post(_AGENT_BOOT).mock(
        return_value=httpx.Response(202, json={"boot_job_id": "j-full"}),
    )
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}, "boot": True},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["state"] == "booting"
    assert data["booted"] is False

    boot_call = respx.calls.last
    assert "skip_boot" not in str(boot_call.request.url)


@respx.mock
def test_post_sessions_response_includes_agent_url_and_pid() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )
    data = resp.json()
    assert data["agent_url"].startswith("http://localhost:")
    assert data["pid"] is None  # FakeLauncher always returns None


@respx.mock
def test_get_sessions_booted_true_when_agent_reports_booted() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.get(_AGENT_SESSION).mock(
        return_value=httpx.Response(200, json={"state": "booted", "last_activity": 1.0}),
    )
    launcher = FakeLauncher()
    client = _make_client(launcher)
    client.post("/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}})
    resp = client.get("/sessions")
    sessions = resp.json()["sessions"]
    assert sessions[0]["booted"] is True


@respx.mock
def test_get_sessions_booted_false_when_agent_reports_ready() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={}))
    respx.post(_AGENT_BOOT).mock(return_value=httpx.Response(202, json={}))
    respx.get(_AGENT_SESSION).mock(
        return_value=httpx.Response(200, json={"state": "ready", "last_activity": 1.0}),
    )
    launcher = FakeLauncher()
    client = _make_client(launcher)
    client.post("/sessions", json={"board_name": "b1", "runtime_profile": "prplos", "payload": {}})
    resp = client.get("/sessions")
    sessions = resp.json()["sessions"]
    assert sessions[0]["booted"] is False
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest unittests/control/test_app.py::test_post_sessions_default_skip_boot_returns_ready unittests/control/test_app.py::test_post_sessions_boot_true_returns_booting -v
```

Expected: FAIL

- [ ] **Step 3: Update `create_session` in `boardfarm3_control/app.py`**

Replace the boot call block (lines starting with `# Boot (async mode)`):

```python
        # Boot — always called; skip_boot controls init-only vs full sequence
        skip_boot_param = "" if body.boot else "&skip_boot=true"
        boot_url = f"{agent_url}/session/boot?mode=async{skip_boot_param}"
        boot_job_id: str | None = None
        try:
            async with httpx.AsyncClient() as client:
                boot = await client.post(boot_url)
        except Exception as exc:
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.SERVICE_UNAVAILABLE),
                detail="agent boot failed",
            ) from exc
        if boot.status_code != int(HTTPStatus.ACCEPTED):
            await launcher.stop(session_id)
            await lease.release(session_id)
            raise HTTPException(
                status_code=int(HTTPStatus.BAD_GATEWAY),
                detail=f"agent boot rejected: {boot.status_code}",
            )
        boot_job_id = boot.json().get("boot_job_id")
        session_state = "booting" if body.boot else "ready"
```

Also replace the `agent_url = f"http://localhost:{info.host_port}"` line near the top of `create_session` with:

```python
        agent_url = info.agent_url
```

Replace the `return SessionResponse(...)` block at the end of `create_session`:

```python
        registry.add(info)
        registry.touch(session_id)

        return SessionResponse(
            session_id=session_id,
            board_name=info.board_name,
            runtime_profile=info.runtime_profile,
            state=session_state,
            boot_job_id=boot_job_id,
            booted=False,
            agent_url=info.agent_url,
            pid=info.pid,
            created_at=info.created_at,
            last_activity=registry.last_activity(session_id),
        )
```

- [ ] **Step 4: Update `fetch_state` inside `list_sessions` in `boardfarm3_control/app.py`**

Replace the `fetch_state` inner function to use `info.agent_url` and derive `booted`:

```python
        async def fetch_state(info: AgentInfo) -> SessionResponse:
            last_act: float | None
            try:
                async with httpx.AsyncClient() as client:
                    resp = await asyncio.wait_for(
                        client.get(f"{info.agent_url}/session"),
                        timeout=_STATE_TIMEOUT,
                    )
                data: dict[str, Any] = resp.json()
                state: str = data.get("state", "unknown")
                booted: bool = state == "booted"
                last_act = data.get("last_activity")
                if last_act is not None:
                    registry.touch(info.session_id)
            except (asyncio.TimeoutError, httpx.TransportError):
                state = "unreachable"
                booted = False
                last_act = registry.last_activity(info.session_id)
            return SessionResponse(
                session_id=info.session_id,
                board_name=info.board_name,
                runtime_profile=info.runtime_profile,
                state=state,
                booted=booted,
                agent_url=info.agent_url,
                pid=info.pid,
                created_at=info.created_at,
                last_activity=last_act,
            )
```

- [ ] **Step 5: Update `delete_session` to use `info.agent_url`**

Replace `agent_url = f"http://localhost:{info.host_port}"` inside `delete_session`:

```python
        agent_url = info.agent_url
```

- [ ] **Step 6: Update `proxy` route to use `info.agent_url`**

The `proxy` route calls `registry.agent_url(session_id)` which no longer exists. Replace it:

```python
    @app.api_route(
        "/sessions/{session_id}/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy(session_id: str, path: str, request: Request) -> object:
        info = registry.get(session_id)
        if info is None:
            raise HTTPException(
                status_code=int(HTTPStatus.NOT_FOUND),
                detail=f"unknown session {session_id}",
            )
        registry.touch(session_id)
        return await proxy_request(request, info.agent_url, path)
```

- [ ] **Step 7: Update the existing `test_post_sessions_happy_path` to match new defaults**

In `unittests/control/test_app.py`, update the existing happy-path test since the default is now `boot=False` → `state="ready"`:

```python
@respx.mock
def test_post_sessions_happy_path() -> None:
    respx.get(_AGENT_HEALTH).mock(return_value=httpx.Response(200, json={"state": "ready"}))
    respx.post(_AGENT_CONFIG).mock(return_value=httpx.Response(200, json={"state": "configured"}))
    respx.post(_AGENT_BOOT).mock(
        return_value=httpx.Response(202, json={"boot_job_id": "j-abc", "state": "booting"}),
    )
    client = _make_client()
    resp = client.post(
        "/sessions",
        json={"board_name": "board-1", "runtime_profile": "prplos", "payload": {}},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["board_name"] == "board-1"
    assert data["state"] == "ready"        # default skip_boot → ready
    assert data["booted"] is False
    assert data["agent_url"].startswith("http://localhost:")
```

- [ ] **Step 8: Run all app tests**

```bash
pytest unittests/control/test_app.py -v
```

Expected: all PASS

- [ ] **Step 9: Run the full control unit test suite**

```bash
pytest unittests/control/ -v
```

Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add boardfarm3_control/app.py unittests/control/test_app.py
git commit -m "feat(control): default to skip_boot, surface booted/agent_url/pid in session responses"
```

---

## Final verification

- [ ] **Run the complete unit test suite**

```bash
pytest unittests/ -v
```

Expected: all PASS, no regressions outside `unittests/control/`

- [ ] **Run linters**

```bash
nox -s lint
```

Expected: all linters pass

- [ ] **Smoke-check the integration tests (requires no live agent)**

```bash
pytest integrationtests/control/ -v --ignore=integrationtests/control/test_proxy_and_lifecycle.py
```

Expected: any non-lifecycle tests pass; lifecycle tests skipped if no real agent is available
