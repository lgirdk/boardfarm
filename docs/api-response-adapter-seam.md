# The response adapter seam

This document is for a plugin author working in a *different* repository who
wants their `boardfarm_api` plugin to speak a different JSON contract than
core boardfarm's native `{"result": ...}` / `{"job_id": ..., "state": ...}`
shape. It describes the seam as implemented, not as originally proposed —
every symbol named below exists in the `boardfarm3` and `boardfarm3_control`
packages at the version you are reading this against.

## 1. What the seam is for

`generate_template_routers` (`boardfarm3.api.routers._generator`) and
`generate_usecase_routers` (`boardfarm3.api.routers._usecase_generator`)
are the two functions that turn Template ABC methods and `use_cases`
functions into FastAPI routes. Historically they
produced exactly one response shape. The response adapter seam lets a plugin
pass its own `adapter` argument to either generator so it can reuse all of
the introspection, skip-detection and dispatch machinery — the same code
path core boardfarm uses — while substituting its own request-model field
types, its own JSON-to-Python coercion, and its own response body. A plugin
that wants an alternate response contract does not need to fork either
generator and does not change how the native `core` routes behave, because
omitting `adapter` (or passing `None`) still yields the native contract
exactly.

## 2. The override points

`ResponseAdapter` (`boardfarm3.api.routers.adapter`) is a `typing.Protocol`
with five methods and one attribute. `DefaultAdapter`, in the same module,
implements all six and reproduces the native contract; it is what both
generators use internally whenever no adapter is supplied.

| Member | Core decision it overrides | Default behaviour (`DefaultAdapter`) | When a plugin would change it |
|---|---|---|---|
| `field_spec_for(name, annotation, default)` | The `(field_type, default)` pair used to build one field of the generated Pydantic request model | Substitutes API-friendly types via `_annotation_to_field_type` (`Enum` → `Literal[member_names]`, `tuple` → `list`), keeps the original default | To accept a different wire representation for a parameter, or to return `Unsupported(reason)` and exclude a method the native generator would otherwise route |
| `coerce(value, annotation)` | How a JSON-decoded value is converted back to the real Python type before the target callable is invoked | Delegates to the shared `_coerce` helper (`Literal` name → `Enum` member, `list` → `tuple`, element-wise recursion, first-match `Union` handling) | If `field_spec_for` swaps in a different wire type, `coerce` must know how to invert it |
| `extra_fields()` | Fields merged into every generated request model in addition to the method's own parameters | Returns `{}` — no extra fields | To carry adapter-specific metadata (e.g. a correlation id) on every request without changing the target method's signature. A name that collides with a real parameter is not merged silently: the generator detects the collision and returns `Unsupported(reason)` for that method instead, so it is skipped and reported rather than shadowing the real parameter. |
| `check_request(body, required)` | Whether to short-circuit before dispatch, and with what response | Returns `None` unconditionally — "Pydantic already enforced required fields" | To validate something Pydantic's type system cannot express (e.g. a required field that must be non-empty, or a value that must come from `extra_fields()`) and return an adapter-shaped error response without ever touching `queue.submit` |
| `respond(outcome)` | The HTTP response built from a completed or failed call | Re-raises `outcome.error` when set (so the native path is unchanged end to end); otherwise returns the 202 job ticket for async mode or `{"result": outcome.value}` for sync | To wrap success and failure into the plugin's own contract, e.g. `{"status": ..., "payload": ..., "detail": ...}` |
| `supports_async` (attribute, `bool`) | Whether the generated route accepts a `mode` query/body parameter and can run in async (queued) mode at all | `True` | To force every dispatch through the sync path only, e.g. because the plugin's contract has no notion of a job ticket |

## 3. What a plugin cannot reach

The adapter is consulted only after the core generators have already decided
a method is routable. The following are entirely internal to
`boardfarm3.api.routers._generator` / `_usecase_generator` and are never
passed to, or overridable through, an adapter:

- `_is_serialisable` — the JSON-serialisability check applied to every
  parameter and return annotation. A method whose signature this rejects is
  recorded as a `SkippedMethod` before `field_spec_for` is ever called.
- `_validate_sig` — rejects `*args`/`**kwargs`, missing annotations, and
  non-serialisable parameter or return types, for the template generator.
- `_parse_sphinx_params` — extracts `:param name: description` text from the
  method/function docstring to populate `Field(description=...)`. An adapter
  cannot change how descriptions are sourced.
- `_classify_param` — decides, for use-case functions, whether a parameter
  is a `"device"` (resolved from the device manager by name), a
  `"primitive"` (goes through the adapter), or `"unroutable"` (skipped).
- `_resolve` — the template generator's device-manager lookup
  (`boardfarm3.api.routers._resolve`), including its 409 (session not booted)
  and 404 (no device of that type at that index) `HTTPException`s.
- Mount grouping — how multiple `TemplateMount` specs sharing a `mount`
  string flatten into one router, and which spec's method wins when two
  specs contribute the same name.
- Duplicate detection — a second method with the same name in the same
  mount is always skipped with reason `"duplicate in mount '<mount>'"`,
  regardless of adapter.
- The route paths themselves — `/templates/{mount}/{name}`,
  `/templates/{mount}/{index}/{name}`, `/use_cases/{module}/{fn_name}` are
  fixed by the generators, not the adapter.

Any method or function skipped by one of these rules never reaches
`field_spec_for`; the adapter only sees signatures that already passed
serialisability, signature-shape and classification checks.

## 4. Control flow, annotated

Both generators build an async FastAPI handler closure per method/function.
The two closures differ in how they resolve their targets but share the same
adapter call sequence: **parse → check → dispatch → respond**, with
everything from the first attempt to reach the target inside a single
`try`/`except Exception`.

**Template generator** (`_generator.py:_make_handler`, one route per
Template ABC method):

1. FastAPI parses the request body into the generated Pydantic model
   (`request_model`) before the handler runs; a validation failure here
   never reaches the adapter at all.
2. `effective_mode = mode if adapter.supports_async else "sync"`.
3. `adapter.check_request(body, required)` — if it returns anything other
   than `None`, that value is returned immediately. No device is resolved,
   no job is submitted.
4. Inside `try`:
   - `_resolve(session, resolve_as, index)` looks up the target device.
   - The inner `_run()` closure calls `body.model_dump()`, then for each
     name recorded in the coercion plan calls `adapter.coerce(data[name],
     orig_annotation)`, then **pops every name returned by
     `adapter.extra_fields()` out of the dict**, then calls
     `getattr(target, method_name)(**data)`.
   - `job = await session.queue.submit(_run, mode=effective_mode)`.
   - `outcome = Outcome(job=job, value=job.result if effective_mode !=
     "async" else None, error=None, mode=effective_mode)`. In async mode the
     job is still running when this line executes, so `job.result` is not
     read; the seam's contract is that `outcome.value` is `None` for async.
5. `except Exception as exc:` — `outcome = Outcome(job=job, value=None,
   error=exc, mode=effective_mode)`. `job` is whatever it was bound to when
   the exception hit (`None` if `_resolve` itself raised).
6. `return adapter.respond(outcome)`.

**Use-case generator** (`_usecase_generator.py:_make_usecase_handler`, one
route per use-case function):

1. Pydantic parse of the body, as above.
2. `effective_mode` computed the same way.
3. `adapter.check_request(body, required)` — same short-circuit contract.
4. Inside `try`:
   - If `session.runtime.device_manager is None`, an `HTTPException(409)`
     is raised (and caught by the `except` below, becoming `outcome.error`
     — it does not propagate directly).
   - `data = body.model_dump()`; for each `_ParamPlan` in order: a
     primitive parameter is coerced with `adapter.coerce(raw, orig_ann)`
     when the plan records an original annotation, else passed through
     unchanged; a device parameter is looked up by name via
     `dm.get_device_by_name(name)` (`DeviceNotFound` becomes
     `HTTPException(404)`) and `isinstance`-checked against the plan's
     accepted template types (`HTTPException(422)` on mismatch). Both
     exceptions are raised inside the `try` and land in `outcome.error`
     exactly like the device-manager check above.
   - `job = await session.queue.submit(lambda: fn(**kwargs),
     mode=effective_mode)`.
   - `outcome = Outcome(job=job, value=job.result if effective_mode !=
     "async" else None, error=None, mode=effective_mode)` — same async-mode
     guard as the template generator.
5. `except Exception as exc:` — same shape as the template generator.
6. `return adapter.respond(outcome)`.

`DefaultAdapter.respond` re-raises `outcome.error` when it is set. That
re-raise is what keeps the native path byte-for-byte unchanged: the
exception propagates out of the handler with its original type and
traceback, reaching FastAPI's default exception handling exactly as it did
before the adapter existed. An adapter only changes error behaviour by
choosing, in its own `respond`, not to re-raise.

## 5. Two traps, with the reason

**(a) `extra_fields()` entries never reach the target callable, but the two
generators exclude them by different mechanisms.** In the template
generator, `extra_fields()` keys are merged into the Pydantic model
alongside the method's real parameters, so they *are* present in
`body.model_dump()`; `_run()` explicitly pops each one
(`data.pop(extra, None)`) before calling
`getattr(target, method_name)(**data)`. Skipping that pop would raise
`TypeError: unexpected keyword argument` on every call, because the target
method never declared the field. In the use-case generator no such pop
exists or is needed: `kwargs` is built field-by-field from the `_ParamPlan`
list derived from the function's own signature, so an adapter's
`extra_fields()` keys are simply never copied into `kwargs` in the first
place — there is nothing to strip.

**(b) The dispatch `try` blocks catch `Exception`, not `BaseException`.**
`except Exception as exc:` in both `_make_handler` and
`_make_usecase_handler` deliberately excludes `asyncio.CancelledError` and
`KeyboardInterrupt` (`asyncio.CancelledError` has derived from
`BaseException`, not `Exception`, since Python 3.8). A slow call cancelled by client
disconnect or a queue shutdown propagates normally instead of being
captured into `outcome.error` and handed to `adapter.respond` — an adapter
never sees, and cannot suppress or reshape, a cancellation.

## 6. The control-plane edge

The runtime agent (where the generators above run) and the control plane
(`boardfarm3_control`, which fronts one or more agents and proxies requests
to them) are separate processes. `RouterBundle`
(`boardfarm3.api.routers.RouterBundle`) carries two fields that only matter
at the control-plane edge, because the agent-side adapter has no visibility
into control-plane-only failures:

- `error_shaper: Callable[[Exception], Response] | None` — converts an
  exception raised while the control plane is dispatching a proxied request
  into a response in the bundle's own contract, instead of FastAPI's default
  error body. It covers exactly three failure points, all raised inside
  `boardfarm3_control.openapi._dispatch_proxy_request` before the request
  ever reaches the agent: a missing `session_id` on the body
  (`HTTPException(422)`), an unrecognised `session_id`
  (`HTTPException(404)`), and the downstream agent being unreachable or
  timing out (`HTTPException(502)`, raised by
  `boardfarm3_control.proxy.proxy_request`). When `error_shaper` is `None`
  the exception is re-raised and FastAPI's default handling applies — the
  same "unchanged by default" guarantee as `DefaultAdapter.respond`.
- `optional_session_id: bool` — when `True`, the `session_id` field the
  control plane injects into the proxied request model is optional
  (`str | None = None`) instead of required (`str = ...`). A caller who
  omits it reaches the endpoint — and `error_shaper`, or the plugin's own
  `check_request`/`respond` logic — instead of failing a pre-handler 422
  from Pydantic.

Nothing crosses the process boundary to carry these fields. The runtime
agent (`boardfarm3/api/app.py`, via
`boardfarm3.api.routers.load_plugin_routers`) and the control plane
(`boardfarm3_control.openapi.load_plugin_routers`) each build their own
`pluggy.PluginManager`, each call `load_setuptools_entrypoints("boardfarm_api")`
independently, and each execute the plugin's `boardfarm_add_api_routers()`
hookimpl in their own process — so the plugin code that builds the
`RouterBundle` runs twice, once per process, not once with the result
shipped across. `_flatten_bundle` stamps
`route.endpoint.__bf_error_shaper__` and
`route.endpoint.__bf_optional_session_id__` onto each route's endpoint
function entirely inside the control-plane process, using the
`RouterBundle` its own local hookimpl call just returned; `_make_proxy_endpoint`
then reads them back in that same process with
`getattr(original_endpoint, "__bf_error_shaper__", None)` /
`getattr(original_endpoint, "__bf_optional_session_id__", False)`. The
plain function-attribute channel exists because `create_app` also accepts
`extra_routers` (used in tests) that were never built from a `RouterBundle`
at all — those routers' endpoint functions simply lack the attributes, and
`getattr`'s defaults keep them on the native, unshaped path. Threading the
values through as an explicit parameter instead would require every caller
of `create_app` to also carry a bundle, which `extra_routers` by design
does not.

The practical consequence: a plugin package must be installed and
importable in **both** the agent environment and the control-plane
environment. If it is only installed on the agent side, the agent's own
`load_setuptools_entrypoints` call finds it and the agent serves its
routes directly, but the control plane's independent entrypoint scan never
sees it — the plugin's routes are silently absent from the control
plane's unified OpenAPI schema, no proxy route is registered for them at
all, and `error_shaper`/`optional_session_id` never apply, because there is
no control-plane-side `RouterBundle` to read them from in the first place.

Two constraints this proxy layer imposes on any adapter-backed route, beyond
the ordinary FastAPI route rules:

1. The body parameter must be named `body`. `_make_proxy_endpoint` looks it
   up by that exact name (`p.name == "body"`) to inject `session_id`; an
   endpoint with a differently-named body parameter compiles without error
   but raises `KeyError` the first time the control plane calls it — unless
   the bundle supplies an `error_shaper`, in which case the `KeyError` is
   caught and shaped like any other dispatch-edge failure (harder to
   diagnose).
2. The Pydantic request model must survive reconstruction through
   `pydantic.create_model`. `_make_proxy_endpoint` rebuilds a `Proxied<Model>`
   model from `original_model.model_fields`, adding `session_id`. A field
   whose type cannot round-trip through `create_model` (for example, one
   depending on model-class-specific validators not carried by
   `model_fields`) breaks the proxy, not the agent-side route.

## 7. The deny-list

`BOARDFARM_API_DISABLED_PLUGINS` (the string constant is exported as
`boardfarm3.api.routers.DISABLED_PLUGINS_ENV`) is a comma-separated list of
`boardfarm_api` entry-point names to exclude entirely. It is read by
`_disabled_plugins()` and consulted inside
`boardfarm3.api.routers.iter_plugin_bundles` — the single generator function
both the runtime agent (`boardfarm3.api.routers.load_plugin_routers`) and
the control plane (`boardfarm3_control.openapi.load_plugin_routers`) call to
enumerate plugin bundles. Because both deployables call the same
`iter_plugin_bundles`, they cannot disagree about which plugins are active
as long as they see the same environment variable.

That agreement is not automatic across process boundaries: an agent runs in
its own container/process with its own environment. The control plane closes
that gap in `boardfarm3_control.app._agent_env`, called from
`create_session`: it merges `BOARDFARM_API_DISABLED_PLUGINS` from the
control plane's own environment into the `agent_env` mapping passed to the
launcher, unless the session-create request body already set that key
explicitly (an explicit per-session value wins). The launcher then seeds it
into the agent's process/container environment before the agent starts, so
by the time the agent calls `iter_plugin_bundles` it sees the same deny-list
the control plane does.

## 8. A minimal worked example

The following is a complete, self-contained plugin module. It implements a
neutral `{"status": ..., "payload": ..., "detail": ...}` contract instead of
boardfarm's native `{"result": ...}` shape, exposes routes for one core
Template ABC (`LAN`, chosen only because it ships with boardfarm — a plugin
would normally route its own templates or use-case functions the same way),
and registers under both required entry-point groups.

`pyproject.toml` (excerpt — register under both entry-point groups so the
plugin's hookspecs load on the main `boardfarm` PluginManager and its
routers load on the `boardfarm_api` PluginManager):

```toml
[project.entry-points."boardfarm"]
mypackage = "mypackage.plugin"

[project.entry-points."boardfarm_api"]
mypackage = "mypackage.plugin"
```

`mypackage/plugin.py`:

```python
"""Example plugin implementing a neutral status/payload/detail contract."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from pluggy import HookimplMarker

from boardfarm3.api.routers import RouterBundle
from boardfarm3.api.routers._generator import generate_template_routers
from boardfarm3.api.routers.adapter import Outcome, Unsupported
from boardfarm3.templates.lan import LAN

hookimpl_api = HookimplMarker("boardfarm_api")


class NeutralAdapter:
    """Response adapter for a neutral status/payload/detail contract.

    Implements every member of ``ResponseAdapter`` explicitly rather than
    subclassing ``DefaultAdapter``, so each override point is visible here
    with no inherited behaviour.
    """

    supports_async = True

    def field_spec_for(
        self,
        name: str,
        annotation: Any,
        default: Any,
    ) -> tuple[Any, Any] | Unsupported:
        """Accept every field's native annotation unchanged.

        :param name: parameter name
        :type name: str
        :param annotation: the parameter's Python type annotation
        :type annotation: Any
        :param default: the parameter's default, or ``...`` when required
        :type default: Any
        :return: the annotation and default unchanged
        :rtype: tuple[Any, Any] | Unsupported
        """
        return (annotation, default)

    def coerce(self, value: Any, annotation: Any) -> Any:
        """Return the decoded value unchanged.

        Because ``field_spec_for`` never substitutes a wire type, no
        parameter is ever recorded in a coercion plan, so this is never
        actually called for this adapter — it is implemented to satisfy the
        protocol and as the hook a future field substitution would use.

        :param value: the JSON-decoded value
        :type value: Any
        :param annotation: the original Python type annotation
        :type annotation: Any
        :return: the value unchanged
        :rtype: Any
        """
        return value

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Add an optional correlation id to every generated request model.

        :return: mapping of field name to ``(type, default)``
        :rtype: dict[str, tuple[Any, Any]]
        """
        return {"request_id": (str | None, None)}

    def check_request(
        self,
        body: Any,
        required: frozenset[str],
    ) -> Any | None:
        """Reject required string fields that decoded as empty.

        Pydantic enforces presence but not non-emptiness, so this catches a
        class of malformed request Pydantic itself lets through.

        :param body: the parsed Pydantic request model instance
        :type body: Any
        :param required: names of parameters that had no default
        :type required: frozenset[str]
        :return: a neutral-shaped error body, or None to proceed
        :rtype: Any | None
        """
        for name in required:
            value = getattr(body, name, None)
            if isinstance(value, str) and value == "":
                return {
                    "status": "error",
                    "payload": None,
                    "detail": f"{name} must not be empty",
                }
        return None

    def respond(self, outcome: Outcome) -> Any:
        """Build the neutral response body for a completed or failed call.

        :param outcome: the result of the dispatch attempt
        :type outcome: Outcome
        :return: a status/payload/detail body
        :rtype: Any
        """
        if outcome.error is not None:
            return {"status": "error", "payload": None, "detail": str(outcome.error)}
        if outcome.mode == "async":
            job = outcome.job
            return {
                "status": "accepted",
                "payload": {"job_id": job.id, "state": job.state.value},
                "detail": None,
            }
        return {"status": "ok", "payload": outcome.value, "detail": None}


def _error_shaper(exc: Exception) -> JSONResponse:
    """Shape a control-plane dispatch-edge failure into the neutral contract.

    :param exc: the exception raised while dispatching the proxied request
    :type exc: Exception
    :return: a neutral-shaped error response
    :rtype: JSONResponse
    """
    status_code = getattr(exc, "status_code", 502)
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "payload": None, "detail": str(detail)},
    )


@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    """Return this plugin's routers under the neutral response contract.

    :return: one RouterBundle for the ``neutral`` namespace
    :rtype: list[RouterBundle]
    """
    adapter = NeutralAdapter()
    routers, skipped = generate_template_routers([LAN], adapter=adapter)
    return [
        RouterBundle(
            namespace="neutral",
            routers=routers,
            skipped=skipped,
            error_shaper=_error_shaper,
            optional_session_id=True,
        )
    ]
```

With this in place, `LAN` routes are generated at
`/neutral/templates/lan/{name}` (and the `{index}/{name}` variant), every
response uses the `status`/`payload`/`detail` shape instead of `{"result":
...}`, and a request missing `session_id` at the control plane still reaches
`check_request` and `respond` instead of failing a pre-handler 422, because
`optional_session_id=True`.

## 9. Stability

The following are public API, consumed out of tree by plugin authors, and
must not change shape without a deprecation path:

- `boardfarm3.api.routers.adapter.ResponseAdapter` — the six-member protocol:
  `field_spec_for`, `coerce`, `extra_fields`, `check_request`, `respond`,
  `supports_async`.
- `boardfarm3.api.routers.adapter.Unsupported` — the `reason: str` marker
  returned from `field_spec_for` to skip a method.
- `boardfarm3.api.routers.adapter.Outcome` — the `job`, `value`, `error`,
  `mode` dataclass passed to `respond`.
- `boardfarm3.api.routers.adapter.DefaultAdapter` — the reference
  implementation; a plugin may compose with it (call through to its methods)
  as well as replace it entirely.
- The `adapter: ResponseAdapter | None` keyword parameter on
  `boardfarm3.api.routers._generator.generate_template_routers` and
  `boardfarm3.api.routers._usecase_generator.generate_usecase_routers`.
- `boardfarm3.api.routers.RouterBundle`, including the `error_shaper` and
  `optional_session_id` fields specifically (the rest of the dataclass —
  `namespace`, `routers`, `skipped` — predates this seam).
- `boardfarm3.api.routers.DISABLED_PLUGINS_ENV` — the
  `BOARDFARM_API_DISABLED_PLUGINS` environment variable name.
- `boardfarm3.api.routers.iter_plugin_bundles` — the shared enumeration
  function both deployables call, including its deny-list behaviour.
- The `boardfarm_api` entry-point group name and the `boardfarm_add_api_routers`
  hookspec signature (`() -> list[RouterBundle]`) it must satisfy.
