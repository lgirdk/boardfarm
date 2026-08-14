# Design: Skip-Boot Default and PID/URL Tracking in Control Plane

**Date**: 2026-08-14
**Status**: Approved

## Overview

Two improvements to `boardfarm3_control` following completion of Phase 2:

1. **Skip-boot default** — the control plane always calls `POST /session/boot` on the agent, but defaults to `skip_boot=true` (init-only: connect consoles, initialise device variables). The frontend explicitly triggers a full boot when ready.
2. **PID/URL tracking** — `AgentInfo` stores an explicit `pid` (numeric OS PID) and `agent_url` (full base URL) for every session. `ProcessLauncher` persists this state to disk so orphaned subprocesses can be killed after a control plane restart.

---

## 1. Model changes

### `SessionCreate`

Add one top-level field:

```python
boot: bool = False
# False (default) → skip_boot init; True → full boot sequence
```

`mode=async` is fixed and not exposed to callers.

### `AgentInfo`

Add two fields:

```python
pid: int | None   # OS PID; set by ProcessLauncher, None for DockerLauncher
agent_url: str    # e.g. "http://localhost:18432" — stored, not computed
```

`container_id` is retained (Docker container ID, or PID-as-string for ProcessLauncher). `pid` is the canonical numeric form of the PID, avoiding callers parsing `container_id`.

### `SessionResponse`

Add:

```python
booted: bool       # False until a full boot has completed
agent_url: str     # surfaced for operational visibility
pid: int | None    # None when running in Docker
```

`booted` starts as `False` on session creation regardless of `boot` flag. On `GET /sessions`, the fan-out reads the agent's `GET /session` response; `booted` is derived as `state == "booted"` (the agent's own state machine uses this label once a full boot sequence completes). If the agent is unreachable, `booted=False` is assumed.

---

## 2. `create_session` flow

```text
POST /sessions  { boot: false }   →  POST /session/boot?mode=async&skip_boot=true
POST /sessions  { boot: true  }   →  POST /session/boot?mode=async
```

Response state:

| `boot` flag | `state`     | `booted` |
|-------------|-------------|----------|
| `false`     | `"ready"`   | `false`  |
| `true`      | `"booting"` | `false`  |

Error handling for the boot call is unchanged: transport failures or non-202 responses trigger `launcher.stop()` + `lease.release()` and return an HTTP error.

---

## 3. PID/URL tracking and orphan cleanup

### `ProcessLauncher`

- `start()` stores `proc.pid` as `AgentInfo.pid` and constructs `AgentInfo.agent_url = f"http://localhost:{host_port}"`.
- After every `start()` and `stop()`, serialises the current sessions dict (info only, no live process objects) to a JSON state file. Default path: `/tmp/boardfarm-control-sessions.json`; overridable via `BOARDFARM_CONTROL_STATE_FILE`.
- `list_sessions()` reads the state file and returns the stored `AgentInfo` list.
- On startup, `SessionRegistry.rebuild(launcher)` calls `list_sessions()`. For `ProcessLauncher`, each returned entry has its PID probed via `os.kill(pid, 0)`. PIDs still alive are SIGTERMed. After cleanup, the state file is rewritten with only the entries that were not orphaned (empty after a clean restart).

### `DockerLauncher`

- `pid = None` always.
- `agent_url` stored at container start time: `f"http://localhost:{host_port}"`.
- Orphan cleanup unchanged — `list_sessions()` uses Docker labels.

### `FakeLauncher`

- `pid = None`, `agent_url = f"http://localhost:{port}"`.
- No state file. Orphan cleanup not applicable.

### `SessionRegistry`

- `agent_url()` method removed. All internal usages of `f"http://localhost:{info.host_port}"` replaced with `info.agent_url`.

---

## 4. State file format (ProcessLauncher)

```json
{
  "s-aabbccdd": {
    "session_id": "s-aabbccdd",
    "board_name": "board1",
    "runtime_profile": "default",
    "container_id": "12345",
    "host_port": 18432,
    "created_at": 1723632000.0,
    "pid": 12345,
    "agent_url": "http://localhost:18432"
  }
}
```

Written atomically (write to `.tmp`, then `os.replace`).

---

## 5. Error handling

- **State file missing on startup**: treated as empty — no orphan cleanup needed, no error.
- **State file corrupt (bad JSON)**: log a warning, treat as empty, proceed.
- **`os.kill(pid, 0)` raises `ProcessLookupError`**: PID is already gone — prune silently.
- **SIGTERM timeout**: send SIGKILL after 5 s (same as live `stop()` behaviour).

---

## 6. Out of scope

- `booted` state management: the control plane does not track this transition; it comes from the agent's own state machine via the fan-out in `GET /sessions`.
- Docker orphan cleanup: no change — labels already cover restart recovery.
- `ProcessLauncher` inter-host process tracking: this is a local-only, dev-oriented launcher.
