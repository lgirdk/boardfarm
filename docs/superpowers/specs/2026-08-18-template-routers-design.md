# Template Routers — Design

**Date:** 2026-08-18
**Status:** Approved, ready for implementation planning
**Phase:** 3 of the boardfarm REST API roadmap
**Predecessor:** `2026-08-13-boardfarm-control-plane-design.md` (Phase 2 — control plane)

---

## 1. Goal

Expose boardfarm Template ABC methods as REST API endpoints so the JS orchestrator (frontend) can call device operations over HTTP. The frontend chains the outputs of one call into the inputs of the next, so results must be returned synchronously in the HTTP response body.

This phase covers the **thin slice**: LAN template methods only, wired all the way through — agent router → control plane OpenAPI → TypeScript client. The code generator (Phase 3b) scales this pattern to all templates without additional hand-writing.

---

## 2. Architecture

The full call path, with no direct frontend-to-agent contact:

```
Frontend
  │
  POST /sessions/{sid}/templates/lan/ping
  │
  ▼
Control Plane  (single base URL, one future auth point)
  │  catch-all proxy: /sessions/{sid}/** → agent at localhost:{port}
  │
  POST /templates/lan/ping
  │
  ▼
Agent  (per-board Docker container)
  │  FastAPI handler → ExecutionQueue → single worker thread
  │
  device.ping(...)    ← blocking pexpect call, serialised by the queue
  │
  ▼
Result propagates back through proxy → frontend
```

The control plane's existing `openapi.py` aggregates the agent's plugin routers into the unified `/openapi.json` with no changes required. The frontend's TypeScript client is generated from that unified spec.

---

## 3. Component Map

| File | Change |
|---|---|
| `boardfarm3/api/routers/__init__.py` | Create — `_resolve()` device-lookup helper |
| `boardfarm3/api/routers/lan.py` | Create — LAN template router (thin slice) |
| `boardfarm3/api/plugin.py` | Modify — implement `boardfarm_add_api_routers` |
| `boardfarm3/api/app.py` | Modify — load + mount plugin routers in `create_app()` |
| `unittests/api/test_routers_lan.py` | Create — unit tests for the LAN router |

No changes to `boardfarm3_control/` — the control plane's `openapi.py` picks up the new routes automatically at startup.

---

## 4. URL Structure

Both forms address the same device; the shorthand implies index 0:

```
POST /templates/lan/ping            ← LAN device at index 0 (shorthand)
POST /templates/lan/0/ping          ← LAN device at index 0 (explicit)
POST /templates/lan/1/ping          ← second LAN device (lan2 in inventory)
```

Template name is derived as `TemplateClass.__name__.lower()` — `LAN` → `"lan"`, `ACS` → `"acs"`, `SIPServer` → `"sipserver"`.

Device index maps to insertion order in `device_manager.get_devices_by_type(LAN)`, which follows inventory JSON order.

Through the control plane the frontend sees:

```
POST /sessions/{session_id}/templates/lan/ping
POST /sessions/{session_id}/templates/lan/{index}/ping
```

---

## 5. Device Resolution

A shared helper in `boardfarm3/api/routers/__init__.py` used by every template router:

```python
def _resolve(session: Session, template: type[T], index: int) -> T:
    """Return the device of *template* type at *index*, or raise 404.

    :param session: active session
    :type session: Session
    :param template: Template ABC to resolve
    :type template: type[T]
    :param index: zero-based position in registration order
    :type index: int
    :return: resolved device instance
    :rtype: T
    :raises HTTPException: 409 if session not booted; 404 if index out of range
    """
    if session.runtime.device_manager is None:
        raise HTTPException(
            status_code=409,
            detail="session is not booted — device_manager unavailable",
        )
    devices = list(session.runtime.device_manager.get_devices_by_type(template).values())
    if index >= len(devices):
        raise HTTPException(
            status_code=404,
            detail=f"no {template.__name__} device at index {index}",
        )
    return devices[index]
```

---

## 6. Execution Model

**Default: synchronous.** The handler submits to the `ExecutionQueue` (preserving serial pexpect access) and awaits the result before responding. The frontend receives the result directly in the response body — no polling required, which enables clean call chaining.

**`?mode=async` escape hatch.** For long-running operations where the result is not needed for chaining (tcpdump, sustained traffic, packet capture), the caller passes `?mode=async` to receive `202 + job_id` immediately and poll `GET /jobs/{jid}` for completion.

Both paths go through the queue. The difference is only whether the HTTP handler awaits the job result.

```python
@router.post("/ping")
@router.post("/{index}/ping")
async def lan_ping(
    request: Request,
    body: LanPingRequest,
    index: int = 0,
    mode: Literal["sync", "async"] = "sync",
) -> dict[str, Any]:
    session = request.app.state.session
    device = _resolve(session, LAN, index)
    job = await session.queue.submit(
        lambda: device.ping(**body.model_dump()),
        mode=mode,
    )
    if mode == "async":
        return {"job_id": job.id, "state": job.state.value}
    # sync: job is complete; exceptions propagate and are handled by the
    # existing BoardfarmException / pexpect.TIMEOUT / pexpect.EOF handlers
    return {"result": job.result}
```

---

## 7. Pydantic Schema Strategy — Two Phases

### Phase 3a (this design): hand-written models for the thin slice

Explicit request models per method. Complete control over the OpenAPI schema. Sets the exact code pattern the generator will reproduce.

**Initial LAN methods (thin slice — chosen to cover all return type categories):**

| Method | Return type | Why included |
|---|---|---|
| `ping` | `bool` | Most representative; simple in/out |
| `get_interface_macaddr` | `str` | Read-only, str return |
| `get_interface_ipv4addr` | `str` | Read-only, str return |
| `set_link_state` | `None` | Write operation, None return |

Example models:

```python
class LanPingRequest(BaseModel):
    ping_ip: str
    ping_count: int = 4
    ping_interface: str | None = None
    timeout: int = 50
    json_output: bool = False
    options: str = ""

class LanGetInterfaceMacaddrRequest(BaseModel):
    interface: str

class LanGetInterfaceIpv4addrRequest(BaseModel):
    interface: str

class LanSetLinkStateRequest(BaseModel):
    interface: str
    state: str
```

### Phase 3b (follow-on): offline code generator

A script reads each Template ABC, emits a router `.py` file in the exact same style as the hand-written one above, and commits it. A CI `git diff --exit-code` check catches drift when templates change.

**Exclusion rules for the generator (methods that stay hand-written):**

| Reason | Examples |
|---|---|
| Parameter is a device/template instance | `def foo(self, other: LAN)` |
| Return type is non-serializable | `BoardfarmPexpect`, `DataFrame`, `Generator`, `Iterator`, context managers |
| Method is a property | `iface_dut`, `console`, `firewall`, etc. |
| Return annotation absent | `inspect.Parameter.empty` |
| Name starts with `_` | private/dunder |

---

## 8. Agent `app.py` Wiring

`create_app()` gains one block after the FastAPI app is constructed, before route definitions:

```python
from boardfarm3.main import get_plugin_manager
_pm = get_plugin_manager()
for _routers in _pm.hook.boardfarm_add_api_routers():
    for _router in _routers:
        app.include_router(_router)
```

The process-global `PluginManager` already has the API hookspecs registered and all `boardfarm_api` entrypoints loaded — no new instantiation needed.

`boardfarm3/api/plugin.py` implements the hook:

```python
@hookimpl
def boardfarm_add_api_routers() -> list[APIRouter]:
    from boardfarm3.api.routers import lan
    return [lan.router]
```

External plugins follow the identical pattern — implement `boardfarm_add_api_routers`, return their own `APIRouter` objects.

---

## 9. Error Handling

| Condition | HTTP | When |
|---|---|---|
| Session not booted | 409 | `device_manager` is None |
| No device at index | 404 | `index >= len(devices)` |
| Method execution failure | Job `state: "error"` | Recorded on the `Job`; caller sees it via `GET /jobs/{jid}` or in sync response |
| Agent unreachable | 502 | Control plane proxy — existing behaviour |

In sync mode, if the job raises, the handler re-raises the exception. The existing `BoardfarmException` / `pexpect.TIMEOUT` / `pexpect.EOF` exception handlers already registered on the FastAPI app format the error envelope with `session_id` and `console_tail`.

---

## 10. Testing

### Unit tests (`unittests/api/test_routers_lan.py`)

Uses a fake session with a mock LAN device. No real pexpect, no Docker.

- `POST /templates/lan/ping` sync → `{"result": true}`
- `POST /templates/lan/ping?mode=async` → `{"job_id": "j-...", "state": "queued"}`
- `POST /templates/lan/1/ping` with one LAN device → 404
- `POST /templates/lan/ping` before boot (no device_manager) → 409
- `POST /templates/lan/get_interface_macaddr` → `{"result": "aa:bb:cc:dd:ee:ff"}`
- `POST /templates/lan/set_link_state` → `{"result": null}`

### Integration test (extends prplOS compose job)

After a full session boot:
- `POST /sessions/{sid}/templates/lan/ping` with a real IP → `{"result": true}`

### Control plane OpenAPI test (extends `unittests/control/test_openapi.py`)

- Pass `lan.router` as `extra_routers` to `create_app()` in the control plane test
- Assert `/openapi.json` contains `/sessions/{session_id}/templates/lan/ping`
- Assert `LanPingRequest` schema is present in the spec components

---

## 11. Deferred

- **Code generator (Phase 3b)** — scales the hand-written pattern to all templates automatically
- **Use-case routers** — follow the same pattern; use cases call template ABCs by type, so device resolution is the same `_resolve()` helper
- **`WAN`, `CPE`, `ACS`, etc. routers** — identical structure, added incrementally or via the generator
- **Auth on template routes** — inherited from the control plane auth layer when it lands; no agent changes needed
