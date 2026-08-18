# Template & Use-Case Router Expansion — Design

**Date:** 2026-08-18
**Status:** Approved (design)
**Builds on:** [2026-08-18-template-routers-design.md](2026-08-18-template-routers-design.md)

## Problem

The runtime API agent auto-generates FastAPI routes from Template ABCs, but
only `LAN` is currently wired ([plugin.py](../../../boardfarm3/api/plugin.py)).
Three gaps remain:

1. **Other device templates are not exposed.** `WAN`, `WLAN`, `ACS`,
   `Provisioner`, `SIPServer`, `SIPPhone`, `CoreRouter`, `NTU` all have
   route-able methods but no routes.
2. **CPE has no usable surface.** The `CPE` ABC is composed of only three
   properties (`config`, `hw`, `sw`), so the generator produces an empty
   router. Its real behaviour lives on the `CPESW` and `CPEHW` sub-templates,
   reached via `cpe.sw` / `cpe.hw`. The frontend needs these flattened under a
   single `/templates/cpe/<method>` path — the sw/hw split is an internal
   developer convenience and must be invisible over HTTP.
3. **Use cases are not routable at all.** The ~127 protocol-oriented functions
   in `boardfarm3/use_cases/` are the primary test-facing API but have no HTTP
   surface.

## Goals

- Expose the remaining device templates with zero new per-template code.
- Flatten `CPESW` + `CPEHW` methods under one `/templates/cpe/` prefix.
- Auto-generate routes for use-case functions, resolving device parameters
  from the running device registry by name.
- Keep every skipped method/function auditable via the existing
  `GET /diagnostics/skipped-routes` endpoint.
- Remain fully backward compatible with the existing `LAN` template routing
  and its tests.

## Non-goals

- Serialising complex return types (dataclasses, `DataFrame`, `IPv4Address`,
  `IPerf3TrafficGenerator`, device lists). These auto-skip and are out of scope.
- Routing `@contextmanager` use cases (they annotate `Generator`/`Iterator`
  returns and auto-skip).
- Reconstructing dataclass/trace state from JSON (e.g. the DHCP trace
  analysers that take `DHCPTraceData`). These auto-skip as unroutable.
- Changing the control-plane proxy or OpenAPI aggregation — they pick up new
  routes automatically.

## Current state (verified)

- `generate_template_routers(templates: list[type])` in
  [`_generator.py`](../../../boardfarm3/api/routers/_generator.py) introspects a
  Template ABC and builds `POST /templates/<name>/<method>` and
  `POST /templates/<name>/{index}/<method>` per accepted method. Handler
  dispatch is `getattr(device, method)(**body)` where the device is resolved via
  `_resolve(session, template, index)`.
- `_is_serialisable(annotation)` accepts `str/int/float/bool/dict/list/None/Any`
  and unions/generics of those; rejects everything else. It already correctly
  rejects every problematic use-case return type.
- `_resolve` uses `device_manager.get_devices_by_type(template).values()` indexed
  by position. `get_devices_by_type` returns `dict[name → device]`.
- `DeviceManager` has `get_devices_by_type` and `get_device_by_type` but **no**
  `get_device_by_name`.
- CPESW and CPEHW have **no method-name collisions** (verified across both
  files), so flattening is unambiguous.
- The `boardfarm_add_api_routers` hookimpl in `plugin.py` returns a single
  `RouterBundle(namespace="core", ...)`. Everything mounts under `/core`.

## Design

### Part A — Expand template routers

Add the remaining template ABCs to the list passed to
`generate_template_routers` in `plugin.py`:

```python
from boardfarm3.templates.wan import WAN
from boardfarm3.templates.wlan import WLAN
from boardfarm3.templates.acs import ACS
from boardfarm3.templates.provisioner import Provisioner
from boardfarm3.templates.sip_server import SIPServer
from boardfarm3.templates.sip_phone import SIPPhone
from boardfarm3.templates.core_router import CoreRouter
from boardfarm3.templates.ntu.ntu import NTU
```

No generator changes. Non-serialisable methods (e.g. anything returning a
`BoardfarmPexpect` or an `IPv4Address`) auto-skip and appear in
`/diagnostics/skipped-routes`.

### Part B — CPE flattening via `TemplateMount`

Introduce a spec dataclass in `_generator.py` describing how a template's
methods mount as routes:

```python
@dataclass
class TemplateMount:
    """Describes how a template's methods mount as routes.

    :param mount: URL segment under ``/templates/`` (e.g. ``"cpe"``)
    :param resolve_as: template type looked up in the device manager
    :param introspect: template ABC whose methods become routes
    :param accessor: attribute on the resolved device to dispatch through
        (``"sw"`` / ``"hw"``); ``None`` dispatches on the device itself
    """

    mount: str
    resolve_as: type
    introspect: type
    accessor: str | None = None
```

`generate_template_routers` accepts `list[type | TemplateMount]`. Bare types are
normalised to `TemplateMount(name=cls.__name__.lower(), resolve_as=cls,
introspect=cls, accessor=None)`, preserving today's behaviour and tests exactly.

Specs are grouped by `mount`; each mount produces one `APIRouter`. For each
spec, methods are introspected on `introspect` but the handler resolves the
device via `resolve_as` and dispatches through the accessor:

```python
target = device if accessor is None else getattr(device, accessor)
result = getattr(target, method_name)(**body.model_dump())
```

**Duplicate-name policy:** within one mount, if two specs contribute the same
method name, the first wins and the later one is recorded as
`SkippedMethod(introspect.__name__, name, "duplicate in mount 'cpe'")`. No
collisions exist today; this is a safety net.

CPE wiring in `plugin.py`:

```python
from boardfarm3.templates.cpe import CPE, CPEHW, CPESW

cpe_mounts = [
    TemplateMount("cpe", CPE, CPESW, "sw"),
    TemplateMount("cpe", CPE, CPEHW, "hw"),
]
```

Result: `POST /core/templates/cpe/reset` (from CPESW via `cpe.sw`),
`POST /core/templates/cpe/power_cycle` (from CPEHW via `cpe.hw`), etc. The
frontend sees a single flat CPE surface.

### Part C — Use-case routers

New module `boardfarm3/api/routers/_usecase_generator.py`.

**Discovery.** For each use-case module (`cpe`, `dhcp`, `networking`, `wifi`,
`iperf`, `voice`, `device_getters`, `multicast`, `ripv2`, `image_comparison`),
introspect public module-level functions (not starting with `_`).

**Parameter classification.** For each parameter annotation:

- **device** — the annotation is a template ABC, or a `Union`/`X | Y` whose
  every arm is a template ABC (covers aliases like
  `DeviceWithFwType = LAN | WAN | ACS | CPE` and `SSHDeviceType`). A template
  ABC is detected by its module living under `boardfarm3.templates`.
- **primitive** — `_is_serialisable(annotation)` is True (includes `Literal`,
  treated as its underlying string/int choices).
- **unroutable** — anything else (dataclass, `type[T]`, `Generator`, custom
  objects). A single unroutable parameter makes the whole function unroutable →
  recorded as `SkippedMethod` and no route is generated.

**Return classification.** Reuse `_is_serialisable(return_annotation)`.
Non-serialisable → skip. This automatically drops context managers
(`Generator`/`Iterator`), dataclass returns, `DataFrame`, `IPv4Address`,
`IPerf3TrafficGenerator`, and device-list returns (`list[LAN]`).

**Request model (flat).** One dynamically built Pydantic model per function:

- device parameters become `str` fields (the device name), described as
  `"device name"`.
- primitive parameters become their native typed fields with defaults.

The generator keeps a `{param_name: is_device}` map for the handler.

**Handler.** Mounted at `POST /use_cases/<module>/<function>`:

1. For each device field, call `session.runtime.device_manager
   .get_device_by_name(value)`; `404` if not found.
2. Validate the resolved device `isinstance` the parameter's template/union;
   `422` if the name refers to a device of the wrong type.
3. Assemble kwargs (resolved devices + primitives) and submit through
   `session.queue.submit(lambda: fn(**kwargs), mode=mode)` — same `mode=sync|
   async` contract as template routes; async returns `202 {job_id, state}`.

**Lib addition.** Add `DeviceManager.get_device_by_name(name: str)`:

```python
def get_device_by_name(self, device_name: str) -> BoardfarmDevice:
    """Return the registered device with the given name.

    :param device_name: registered device name
    :raises DeviceNotFound: when no device with that name is registered
    :return: the device instance
    """
```

Backed by `self._plugin_manager.get_plugin(device_name)` (or a scan of
`list_name_plugin()`), raising `DeviceNotFound` when absent.

**Wiring.** `boardfarm_add_api_routers` in `plugin.py` calls a new
`generate_usecase_routers([...modules...])` and adds the routers/skipped to the
same `"core"` bundle, so use cases mount under `/core/use_cases/...`.

## Data flow (unchanged envelope)

```
plugin.boardfarm_add_api_routers()
  → generate_template_routers([LAN, WAN, ..., *cpe_mounts])   # Part A + B
  → generate_usecase_routers([cpe, dhcp, networking, ...])    # Part C
  → RouterBundle(namespace="core", routers=[...], skipped=[...])
load_plugin_routers()  → wraps under /core
create_app()           → mounts routers, exposes /diagnostics/skipped-routes
```

## Error handling

| Condition | Status |
|---|---|
| Session not booted (`device_manager is None`) | 409 (existing `_resolve`) |
| Template index out of range | 404 (existing `_resolve`) |
| Use-case device name not found | 404 |
| Device name resolves to wrong template type | 422 |
| Async submission | 202 `{job_id, state}` |
| Unroutable method/function | no route; listed in `/diagnostics/skipped-routes` |

## Testing

**Unit — `TemplateMount` / template generator:**
- Bare type still normalises to the pre-existing router shape (regression).
- Two mounts sharing `"cpe"` merge into one router; sw methods dispatch via
  `.sw`, hw via `.hw`.
- CPE flatten produces `/templates/cpe/reset` and `/templates/cpe/power_cycle`.
- Duplicate method name across specs → one route + a `SkippedMethod("duplicate…")`.

**Unit — use-case classifier:**
- Single template param → device field; `LAN | WAN | WLAN` union → device field.
- Primitive + `Literal` params → typed body fields.
- Dataclass / `type[T]` / `Generator` param → function skipped as unroutable.
- Non-serialisable return → skipped.
- Multi-device function (e.g. iperf `source_device` + `destination_device`)
  → two device fields.

**Integration — `TestClient` with fake runtime:**
- By-name use-case call (sync) returns `{"result": ...}`.
- Async call returns `202` with `job_id`.
- Unknown device name → 404; wrong-type device name → 422.
- Unbooted session → 409.
- New template routes appear under `/core/templates/<name>/...`.
- `/diagnostics/skipped-routes` includes use-case skips with reasons.

## Backward compatibility

- `generate_template_routers` still accepts `list[type]`; existing LAN tests
  pass unchanged.
- Namespace stays `"core"`; existing paths are unaffected.
- Control-plane proxy and OpenAPI aggregation require no changes.

## Files touched

- `boardfarm3/api/routers/_generator.py` — add `TemplateMount`, mount grouping,
  accessor dispatch, duplicate policy.
- `boardfarm3/api/routers/_usecase_generator.py` — **new**; param classifier,
  flat request model, by-name handler, `generate_usecase_routers`.
- `boardfarm3/api/plugin.py` — wire remaining templates, CPE mounts, use-case
  modules.
- `boardfarm3/lib/device_manager.py` — add `get_device_by_name`.
- `unittests/api/` — new tests for `TemplateMount`, CPE flatten, use-case
  classifier and handler.
