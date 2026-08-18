# Template & Use-Case Router Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose all device templates (and CPE/NTU's sw+hw sub-templates flattened) plus the `use_cases` functions as auto-generated FastAPI routes on the runtime agent.

**Architecture:** Extend the existing template-router generator with a `TemplateMount` spec so multiple sub-templates (`CPESW`, `CPEHW`) can flatten under one URL mount (`/templates/cpe`) with per-spec attribute dispatch (`.sw`/`.hw`). Add a parallel use-case generator that classifies each function parameter as device (resolved from the registry by name), primitive (request body field), or unroutable (skip), reusing the existing `_is_serialisable` return-type gate. Everything mounts under the existing `"core"` RouterBundle namespace.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2 (`create_model`), pluggy, pytest + `fastapi.testclient.TestClient`.

## Global Constraints

- Code must be valid on Python 3.11–3.13; `ruff target-version = py39` — no 3.12-only syntax.
- Lint stack must pass: `ruff format`, `ruff check` (`select = ["ALL"]`), `flake8` (max line length 88, max complexity 10), `mypy --disallow-untyped-defs`, `pylint`. Never relax `disallow_untyped_defs`.
- Docstrings: sphinx style with `:param:`/`:type:`/`:return:`/`:rtype:` on public APIs, enforced by darglint2.
- Tests live in `unittests/` (plural-less). Run a single test with `pytest unittests/api/<file>.py::<test> -v`.
- Commits: Conventional Commits (`feat:`/`fix:`/`test:`/`docs:` with scope). End every commit message with `Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>`.
- Backward compatibility: `generate_template_routers` must still accept `list[type]`; all existing tests in `unittests/api/test_generator.py` and `unittests/api/test_routers_lan.py` must pass unchanged.
- Namespace stays `"core"`: routes mount under `/core/templates/...` and `/core/use_cases/...`.

---

### Task 1: `DeviceManager.get_device_by_name`

**Files:**
- Modify: `boardfarm3/lib/device_manager.py`
- Test: `unittests/lib/test_device_manager.py`

**Interfaces:**
- Produces: `DeviceManager.get_device_by_name(device_name: str) -> BoardfarmDevice` — returns the registered device with that name; raises `boardfarm3.exceptions.DeviceNotFound` when absent. Backed by `pluggy`'s `PluginManager.get_plugin(name)`.

- [ ] **Step 1: Write the failing test**

Add to `unittests/lib/test_device_manager.py`:

```python
def test_get_device_by_name_returns_registered_device() -> None:
    from unittest.mock import MagicMock

    from boardfarm3.lib.device_manager import DeviceManager

    dm = DeviceManager.__new__(DeviceManager)  # bypass singleton __init__
    sentinel = object()
    pm = MagicMock()
    pm.get_plugin.return_value = sentinel
    dm._plugin_manager = pm  # noqa: SLF001

    assert dm.get_device_by_name("lan") is sentinel
    pm.get_plugin.assert_called_once_with("lan")


def test_get_device_by_name_missing_raises() -> None:
    from unittest.mock import MagicMock

    import pytest

    from boardfarm3.exceptions import DeviceNotFound
    from boardfarm3.lib.device_manager import DeviceManager

    dm = DeviceManager.__new__(DeviceManager)
    pm = MagicMock()
    pm.get_plugin.return_value = None
    dm._plugin_manager = pm  # noqa: SLF001

    with pytest.raises(DeviceNotFound):
        dm.get_device_by_name("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest unittests/lib/test_device_manager.py::test_get_device_by_name_returns_registered_device unittests/lib/test_device_manager.py::test_get_device_by_name_missing_raises -v`
Expected: FAIL with `AttributeError: 'DeviceManager' object has no attribute 'get_device_by_name'`

- [ ] **Step 3: Write minimal implementation**

Add this method to `DeviceManager` (after `get_device_by_type`, before `register_device`) in `boardfarm3/lib/device_manager.py`:

```python
    def get_device_by_name(self, device_name: str) -> BoardfarmDevice:
        """Return the registered device with the given name.

        :param device_name: registered device name
        :type device_name: str
        :raises DeviceNotFound: when no device with that name is registered
        :return: the device instance
        :rtype: BoardfarmDevice
        """
        device = self._plugin_manager.get_plugin(device_name)
        if device is None:
            msg = f"No device registered with name {device_name}"
            raise DeviceNotFound(msg)
        return device
```

Note: `BoardfarmDevice` is already imported under `TYPE_CHECKING` in this file, so the annotation resolves. `DeviceNotFound` is already imported at module top.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest unittests/lib/test_device_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/lib/device_manager.py unittests/lib/test_device_manager.py
git commit -m "feat(device_manager): add get_device_by_name lookup

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 2: `TemplateMount` spec + accessor dispatch in the generator

**Files:**
- Modify: `boardfarm3/api/routers/_generator.py`
- Test: `unittests/api/test_generator.py`

**Interfaces:**
- Consumes: `generate_template_routers` (existing), `_resolve` (existing), `SkippedMethod` (existing).
- Produces:
  - `TemplateMount(mount: str, resolve_as: type, introspect: type, accessor: str | None = None)` dataclass.
  - `generate_template_routers(templates: list[type | TemplateMount]) -> tuple[list[APIRouter], list[SkippedMethod]]` — now accepts bare types (normalised to `TemplateMount(cls.__name__.lower(), cls, cls, None)`) or `TemplateMount` specs; specs sharing a `mount` merge into one router; duplicate method names within a mount are skipped with reason `"duplicate in mount '<mount>'"`.

- [ ] **Step 1: Write the failing test**

Add to `unittests/api/test_generator.py`:

```python
def test_template_mount_flattens_two_introspect_sources() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )

    class _Sw:
        @abstractmethod
        def reset(self) -> None: ...

    class _Hw:
        @abstractmethod
        def power_cycle(self) -> None: ...

    class _Composite:
        pass

    mounts = [
        TemplateMount("cpe", _Composite, _Sw, "sw"),
        TemplateMount("cpe", _Composite, _Hw, "hw"),
    ]
    routers, _ = generate_template_routers(mounts)
    assert len(routers) == 1  # both specs merge into ONE mount router
    assert routers[0].prefix == "/templates/cpe"
    paths = set(_local_paths(routers[0]))
    assert "/reset" in paths  # from _Sw via .sw
    assert "/power_cycle" in paths  # from _Hw via .hw


def test_template_mount_duplicate_name_skipped() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )

    class _A:
        @abstractmethod
        def dup(self) -> None: ...

    class _B:
        @abstractmethod
        def dup(self) -> None: ...

    class _C:
        pass

    routers, skipped = generate_template_routers(
        [TemplateMount("x", _C, _A, "a"), TemplateMount("x", _C, _B, "b")]
    )
    paths = _local_paths(routers[0])
    assert paths.count("/dup") == 1  # only first wins (plus its /{index}/dup)
    assert any(s.method == "dup" and "duplicate" in s.reason for s in skipped)


def test_bare_type_still_normalises_to_router() -> None:
    routers, _ = generate_template_routers([_ReturnsBool])
    assert routers[0].prefix == "/templates/_returnsbool"
    assert "/check" in _local_paths(routers[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest unittests/api/test_generator.py::test_template_mount_flattens_two_introspect_sources -v`
Expected: FAIL with `ImportError: cannot import name 'TemplateMount'`

- [ ] **Step 3: Write minimal implementation**

In `boardfarm3/api/routers/_generator.py`:

(a) Add the dataclass after `SkippedMethod`:

```python
@dataclass
class TemplateMount:
    """Describes how a template's methods mount as routes.

    :param mount: URL segment under ``/templates/`` (e.g. ``"cpe"``)
    :type mount: str
    :param resolve_as: template type looked up in the device manager
    :type resolve_as: type
    :param introspect: template ABC whose methods become routes
    :type introspect: type
    :param accessor: attribute on the resolved device to dispatch through
        (``"sw"`` / ``"hw"``); ``None`` dispatches on the device itself
    :type accessor: str | None
    """

    mount: str
    resolve_as: type
    introspect: type
    accessor: str | None = None


def _normalise_mount(item: type | TemplateMount) -> TemplateMount:
    """Return *item* as a TemplateMount, wrapping a bare template type.

    :param item: a template class or an explicit TemplateMount
    :type item: type | TemplateMount
    :return: a TemplateMount describing how to mount the template
    :rtype: TemplateMount
    """
    if isinstance(item, TemplateMount):
        return item
    return TemplateMount(item.__name__.lower(), item, item, None)
```

(b) Change `_make_handler` to accept `resolve_as`, `introspect`, and `accessor` and dispatch through the accessor. Replace the existing `_make_handler` signature and body head:

```python
def _make_handler(
    resolve_as: type,
    introspect: type,
    method_name: str,
    request_model: type,
    accessor: str | None,
) -> Any:  # noqa: ANN401
    """Build an async route handler for *method_name*.

    Injects ``__signature__`` so FastAPI generates a correct OpenAPI schema
    for the dynamically created function.

    :param resolve_as: template type resolved from the device manager
    :type resolve_as: type
    :param introspect: template whose method is dispatched
    :type introspect: type
    :param method_name: name of the method to dispatch
    :type method_name: str
    :param request_model: Pydantic model for the request body
    :type request_model: type
    :param accessor: attribute to dispatch through, or None for the device
    :type accessor: str | None
    :return: async FastAPI route handler
    :rtype: Any
    """

    async def handler(
        request: Request,
        body: Any,  # noqa: ANN401
        index: int = 0,
        mode: str = "sync",
    ) -> dict[str, Any] | JSONResponse:
        session = request.app.state.session
        device: Any = _resolve(  # type: ignore[type-abstract]
            session, resolve_as, index
        )
        target = device if accessor is None else getattr(device, accessor)
        job = await session.queue.submit(
            lambda: getattr(target, method_name)(**body.model_dump()),
            mode=mode,
        )
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    handler.__name__ = f"{introspect.__name__.lower()}_{method_name}"
```

Keep the rest of `_make_handler` (the `__qualname__`, `__doc__`, `__signature__` block) unchanged — but the `__doc__` line's `template.__name__` reference must become `introspect.__name__`:

```python
    handler.__doc__ = (
        f"{method_name.replace('_', ' ').capitalize()} on"
        f" {introspect.__name__} device at *index*."
    )
```

(c) Change `_process_member` to stop building the handler itself — return the request model so the caller can build the handler with mount context. Replace its final lines:

```python
    skipped = _validate_sig(introspect.__name__, name, sig)
    if skipped is not None:
        return skipped

    return _make_request_model(name, sig)
```

and update its signature/param name from `template` to `introspect` and its docstring `:param introspect:` accordingly. The `getattr_static`/property/classmethod checks stay the same (operating on `introspect`). Its return type annotation becomes `SkippedMethod | type | None` (a `type` is the request model).

(d) Rewrite `generate_template_routers` to normalise, group by mount, and build handlers per spec:

```python
def generate_template_routers(
    templates: list[type | TemplateMount],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for each template mount.

    Bare template types are treated as a single-source mount. Multiple
    ``TemplateMount`` specs sharing a ``mount`` flatten into one router; a
    method name contributed by more than one spec is kept from the first
    spec only and the rest are skipped.

    :param templates: template classes or TemplateMount specs to introspect
    :type templates: list[type | TemplateMount]
    :return: generated routers and list of skipped methods with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    mounts = [_normalise_mount(t) for t in templates]
    grouped: dict[str, list[TemplateMount]] = {}
    order: list[str] = []
    for spec in mounts:
        if spec.mount not in grouped:
            grouped[spec.mount] = []
            order.append(spec.mount)
        grouped[spec.mount].append(spec)

    routers: list[APIRouter] = []
    all_skipped: list[SkippedMethod] = []

    for mount in order:
        router = APIRouter(
            prefix=f"/templates/{mount}",
            tags=[f"templates:{mount}"],
        )
        seen: set[str] = set()
        for spec in grouped[mount]:
            for name, obj in inspect.getmembers(spec.introspect):
                if name.startswith("__"):
                    continue
                if name.startswith("_"):
                    all_skipped.append(
                        SkippedMethod(spec.introspect.__name__, name, "private")
                    )
                    continue
                if name in seen:
                    all_skipped.append(
                        SkippedMethod(
                            spec.introspect.__name__,
                            name,
                            f"duplicate in mount '{mount}'",
                        )
                    )
                    continue

                result = _process_member(spec.introspect, name, obj)
                if result is None:
                    continue
                if isinstance(result, SkippedMethod):
                    all_skipped.append(result)
                    _log.warning(
                        "template route skipped: %s.%s — %s",
                        spec.introspect.__name__,
                        result.method,
                        result.reason,
                    )
                    continue

                request_model = result
                handler = _make_handler(
                    spec.resolve_as,
                    spec.introspect,
                    name,
                    request_model,
                    spec.accessor,
                )
                seen.add(name)
                router.post(f"/{name}", status_code=200, response_model=None)(handler)
                router.post(
                    f"/{{index}}/{name}", status_code=200, response_model=None
                )(handler)

        routers.append(router)

    return routers, all_skipped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest unittests/api/test_generator.py -v`
Expected: PASS (new tests + all pre-existing tests still green)

- [ ] **Step 5: Run lint on the changed file**

Run: `ruff check boardfarm3/api/routers/_generator.py && ruff format --check boardfarm3/api/routers/_generator.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add boardfarm3/api/routers/_generator.py unittests/api/test_generator.py
git commit -m "feat(api): add TemplateMount for flattened multi-source routers

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 3: Wire remaining templates + CPE/NTU flatten in the plugin

**Files:**
- Modify: `boardfarm3/api/plugin.py`
- Test: `unittests/api/test_generator.py`

**Interfaces:**
- Consumes: `TemplateMount`, `generate_template_routers` (Task 2), `RouterBundle` (existing).
- Produces: `boardfarm_add_api_routers()` now generates routers for `LAN, WAN, WLAN, ACS, Provisioner, SIPServer, SIPPhone, CoreRouter` plus flattened `cpe` (CPESW+CPEHW) and `ntu` (CPESW+CPEHW) mounts.

- [ ] **Step 1: Write the failing test**

Add to `unittests/api/test_generator.py`:

```python
def test_cpe_flatten_exposes_sw_and_hw_methods() -> None:
    from boardfarm3.api.routers._generator import (
        TemplateMount,
        generate_template_routers,
    )
    from boardfarm3.templates.cpe import CPE, CPEHW, CPESW

    routers, _ = generate_template_routers(
        [TemplateMount("cpe", CPE, CPESW, "sw"), TemplateMount("cpe", CPE, CPEHW, "hw")]
    )
    assert len(routers) == 1
    assert routers[0].prefix == "/templates/cpe"
    paths = set(_local_paths(routers[0]))
    assert "/reset" in paths  # CPESW.reset -> None
    assert "/factory_reset" in paths  # CPESW.factory_reset -> bool
    assert "/power_cycle" in paths  # CPEHW.power_cycle -> None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest unittests/api/test_generator.py::test_cpe_flatten_exposes_sw_and_hw_methods -v`
Expected: PASS already (Task 2 made the generator capable) — this test guards the CPE templates specifically. If it passes, that is expected; proceed to wire the plugin so the routes are actually served.

- [ ] **Step 3: Update the plugin wiring**

Replace the body of `boardfarm_add_api_routers` in `boardfarm3/api/plugin.py`:

```python
@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:
    """Return the core boardfarm API routers, generated from template ABCs.

    :return: one RouterBundle for the ``core`` namespace
    :rtype: list[RouterBundle]
    """
    from boardfarm3.api.routers import RouterBundle  # pylint: disable=import-outside-toplevel
    from boardfarm3.api.routers._generator import (  # pylint: disable=import-outside-toplevel
        TemplateMount,
        generate_template_routers,
    )
    from boardfarm3.templates.acs import ACS  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.core_router import (  # pylint: disable=import-outside-toplevel
        CoreRouter,
    )
    from boardfarm3.templates.cpe import (  # pylint: disable=import-outside-toplevel
        CPE,
        CPEHW,
        CPESW,
    )
    from boardfarm3.templates.lan import LAN  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.ntu.ntu import (  # pylint: disable=import-outside-toplevel
        NTU,
    )
    from boardfarm3.templates.provisioner import (  # pylint: disable=import-outside-toplevel
        Provisioner,
    )
    from boardfarm3.templates.sip_phone import (  # pylint: disable=import-outside-toplevel
        SIPPhone,
    )
    from boardfarm3.templates.sip_server import (  # pylint: disable=import-outside-toplevel
        SIPServer,
    )
    from boardfarm3.templates.wan import WAN  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.wlan import WLAN  # pylint: disable=import-outside-toplevel

    templates: list[type | TemplateMount] = [
        LAN,
        WAN,
        WLAN,
        ACS,
        Provisioner,
        SIPServer,
        SIPPhone,
        CoreRouter,
        TemplateMount("cpe", CPE, CPESW, "sw"),
        TemplateMount("cpe", CPE, CPEHW, "hw"),
        TemplateMount("ntu", NTU, CPESW, "sw"),
        TemplateMount("ntu", NTU, CPEHW, "hw"),
    ]
    routers, skipped = generate_template_routers(templates)
    return [RouterBundle(namespace="core", routers=routers, skipped=skipped)]
```

- [ ] **Step 4: Run the API test suite to verify nothing regressed**

Run: `pytest unittests/api -v`
Expected: PASS (existing LAN tests + Task 2/3 tests)

- [ ] **Step 5: Smoke-check the CLI still loads**

Run: `nox -s boardfarm_help`
Expected: exits 0 (plugin imports resolve)

- [ ] **Step 6: Commit**

```bash
git add boardfarm3/api/plugin.py unittests/api/test_generator.py
git commit -m "feat(api): expose all device templates and flatten CPE/NTU sw+hw

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 4: Use-case parameter classifier

**Files:**
- Create: `boardfarm3/api/routers/_usecase_generator.py`
- Test: `unittests/api/test_usecase_generator.py`

**Interfaces:**
- Consumes: `_is_serialisable`, `SkippedMethod`, `_UNION_TYPE`, `_NONE_TYPE` from `_generator.py`.
- Produces:
  - `_is_template(annotation: Any) -> bool` — True when annotation is a class under `boardfarm3.templates`.
  - `_classify_param(annotation: Any) -> str` — returns `"device"`, `"primitive"`, or `"unroutable"`.
  - `_template_types(annotation: Any) -> tuple[type, ...]` — the concrete template classes an annotation resolves to (single or union), for the handler's `isinstance` check.

- [ ] **Step 1: Write the failing test**

Create `unittests/api/test_usecase_generator.py`:

```python
"""Unit tests for the use-case router generator."""

from __future__ import annotations

from typing import Any, Literal

from boardfarm3.api.routers._usecase_generator import (
    _classify_param,
    _is_template,
    _template_types,
)
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.lan import LAN
from boardfarm3.templates.wan import WAN


def test_is_template_true_for_template_abc() -> None:
    assert _is_template(LAN) is True


def test_is_template_false_for_primitive() -> None:
    assert _is_template(str) is False


def test_classify_single_template_is_device() -> None:
    assert _classify_param(LAN) == "device"


def test_classify_union_of_templates_is_device() -> None:
    assert _classify_param(LAN | WAN | CPE) == "device"


def test_classify_primitive_is_primitive() -> None:
    assert _classify_param(str) == "primitive"
    assert _classify_param(int) == "primitive"


def test_classify_optional_primitive_is_primitive() -> None:
    assert _classify_param(str | None) == "primitive"


def test_classify_literal_is_primitive() -> None:
    assert _classify_param(Literal["up", "down"]) == "primitive"


def test_classify_unknown_object_is_unroutable() -> None:
    class _Weird:
        pass

    assert _classify_param(_Weird) == "unroutable"


def test_classify_type_param_is_unroutable() -> None:
    assert _classify_param(type[Any]) == "unroutable"


def test_template_types_single() -> None:
    assert _template_types(LAN) == (LAN,)


def test_template_types_union() -> None:
    assert set(_template_types(LAN | WAN)) == {LAN, WAN}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest unittests/api/test_usecase_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'boardfarm3.api.routers._usecase_generator'`

- [ ] **Step 3: Write minimal implementation**

Create `boardfarm3/api/routers/_usecase_generator.py`:

```python
"""Runtime use-case router generator for the boardfarm API.

Introspects public functions in the ``boardfarm3.use_cases`` modules and
builds FastAPI routes.  Device-typed parameters are resolved from the running
device registry by name; primitive parameters come from the request body.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Literal, Union, get_args, get_origin

from boardfarm3.api.routers._generator import (
    _NONE_TYPE,
    _UNION_TYPE,
    SkippedMethod,
    _is_serialisable,
)

_log = logging.getLogger(__name__)

_TEMPLATE_ROOT = "boardfarm3.templates"


def _is_template(annotation: Any) -> bool:  # noqa: ANN401
    """Return True when *annotation* is a template ABC class.

    :param annotation: a type annotation
    :type annotation: Any
    :return: True when the annotation is a class under boardfarm3.templates
    :rtype: bool
    """
    return isinstance(annotation, type) and annotation.__module__.startswith(
        _TEMPLATE_ROOT
    )


def _union_args(annotation: Any) -> tuple[Any, ...]:  # noqa: ANN401
    """Return the non-None args of a union annotation, or ().

    :param annotation: a type annotation
    :type annotation: Any
    :return: union member types excluding NoneType, or empty tuple
    :rtype: tuple[Any, ...]
    """
    origin = get_origin(annotation)
    is_union = (
        _UNION_TYPE is not None and isinstance(annotation, _UNION_TYPE)
    ) or origin is Union
    if not is_union:
        return ()
    return tuple(a for a in get_args(annotation) if a is not _NONE_TYPE)


def _template_types(annotation: Any) -> tuple[type, ...]:  # noqa: ANN401
    """Return the concrete template classes an annotation resolves to.

    :param annotation: a device-typed annotation (template or union thereof)
    :type annotation: Any
    :return: tuple of template classes for isinstance checks
    :rtype: tuple[type, ...]
    """
    if _is_template(annotation):
        return (annotation,)
    return tuple(a for a in _union_args(annotation) if _is_template(a))


def _classify_param(annotation: Any) -> str:  # noqa: ANN401
    """Classify a parameter annotation for route generation.

    :param annotation: the parameter's type annotation
    :type annotation: Any
    :return: one of ``"device"``, ``"primitive"``, ``"unroutable"``
    :rtype: str
    """
    if _is_template(annotation):
        return "device"
    args = _union_args(annotation)
    if args and all(_is_template(a) for a in args):
        return "device"
    if get_origin(annotation) is Literal:
        return "primitive"
    if _is_serialisable(annotation):
        return "primitive"
    return "unroutable"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest unittests/api/test_usecase_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add boardfarm3/api/routers/_usecase_generator.py unittests/api/test_usecase_generator.py
git commit -m "feat(api): add use-case parameter classifier

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 5: Use-case request model, handler, and `generate_usecase_routers`

**Files:**
- Modify: `boardfarm3/api/routers/_usecase_generator.py`
- Test: `unittests/api/test_usecase_generator.py`

**Interfaces:**
- Consumes: `_classify_param`, `_template_types` (Task 4); `_resolve`-style device lookup via `session.runtime.device_manager.get_device_by_name` (Task 1); `_async_response` from `boardfarm3.api.routers`.
- Produces: `generate_usecase_routers(modules: list[ModuleType]) -> tuple[list[APIRouter], list[SkippedMethod]]` — one `APIRouter(prefix=f"/use_cases/{module_short_name}")` per module; a `POST /<function>` route per routable function; functions with any unroutable param or a non-serialisable return are recorded as `SkippedMethod(module_short_name, fn_name, reason)`.

- [ ] **Step 1: Write the failing test**

Add to `unittests/api/test_usecase_generator.py`:

```python
def test_generate_usecase_routers_builds_routes_and_skips() -> None:
    import types as _types
    from typing import Any

    from boardfarm3.api.routers._usecase_generator import generate_usecase_routers
    from boardfarm3.templates.cpe import CPE

    mod = _types.ModuleType("fake_uc")

    def get_cpu_usage(board: CPE) -> float:  # routable: 1 device, serialisable
        return 0.0

    def parse_trace(packet: object) -> list:  # unroutable param
        return []

    def make_ctx(board: CPE) -> Any:  # non-serialisable return
        return board

    get_cpu_usage.__module__ = "boardfarm3.use_cases.fake_uc"
    parse_trace.__module__ = "boardfarm3.use_cases.fake_uc"
    make_ctx.__module__ = "boardfarm3.use_cases.fake_uc"
    mod.get_cpu_usage = get_cpu_usage
    mod.parse_trace = parse_trace
    mod.make_ctx = make_ctx
    mod.__name__ = "boardfarm3.use_cases.fake_uc"

    routers, skipped = generate_usecase_routers([mod])
    assert len(routers) == 1
    assert routers[0].prefix == "/use_cases/fake_uc"
    paths = [r.path.removeprefix(routers[0].prefix) for r in routers[0].routes]
    assert "/get_cpu_usage" in paths
    skipped_names = {s.method for s in skipped}
    assert "parse_trace" in skipped_names  # unroutable param
    assert "make_ctx" in skipped_names  # non-serialisable return
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest unittests/api/test_usecase_generator.py::test_generate_usecase_routers_builds_routes_and_skips -v`
Expected: FAIL with `ImportError: cannot import name 'generate_usecase_routers'`

- [ ] **Step 3: Write minimal implementation**

Append to `boardfarm3/api/routers/_usecase_generator.py`. Add these imports to the existing import block:

```python
from dataclasses import dataclass
from http import HTTPStatus
from types import ModuleType

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import create_model

from boardfarm3.api.routers import _async_response
from boardfarm3.exceptions import DeviceNotFound
```

Then add the model builder, handler factory, and public entry point:

```python
@dataclass
class _ParamPlan:
    """Resolution plan for one function parameter.

    :param name: parameter name
    :type name: str
    :param is_device: whether the parameter is resolved from the registry
    :type is_device: bool
    :param templates: template classes accepted (device params only)
    :type templates: tuple[type, ...]
    """

    name: str
    is_device: bool
    templates: tuple[type, ...]


def _build_request_model(fn_name: str, sig: inspect.Signature) -> type:
    """Build a flat Pydantic model; device params become str name fields.

    :param fn_name: function name, used for the model class name
    :type fn_name: str
    :param sig: the function signature
    :type sig: inspect.Signature
    :return: dynamically created Pydantic model
    :rtype: type
    """
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        default = param.default if param.default is not inspect.Parameter.empty else ...
        if _classify_param(param.annotation) == "device":
            fields[name] = (str, ... if default is ... else default)
        else:
            fields[name] = (param.annotation, default)
    model_name = "".join(p.capitalize() for p in fn_name.split("_")) + "Request"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _make_usecase_handler(
    fn: Any,  # noqa: ANN401
    request_model: type,
    plans: list[_ParamPlan],
) -> Any:  # noqa: ANN401
    """Build an async handler that resolves device params then calls *fn*.

    :param fn: the use-case function to invoke
    :type fn: Any
    :param request_model: Pydantic model for the request body
    :type request_model: type
    :param plans: per-parameter resolution plans
    :type plans: list[_ParamPlan]
    :return: async FastAPI route handler
    :rtype: Any
    """

    async def handler(
        request: Request,
        body: Any,  # noqa: ANN401
        mode: str = "sync",
    ) -> dict[str, Any] | JSONResponse:
        session = request.app.state.session
        dm = session.runtime.device_manager
        if dm is None:
            raise HTTPException(
                status_code=int(HTTPStatus.CONFLICT),
                detail="session is not booted — device_manager unavailable",
            )
        data = body.model_dump()
        kwargs: dict[str, Any] = {}
        for plan in plans:
            if not plan.is_device:
                kwargs[plan.name] = data[plan.name]
                continue
            name = data[plan.name]
            try:
                device = dm.get_device_by_name(name)
            except DeviceNotFound as exc:
                raise HTTPException(
                    status_code=int(HTTPStatus.NOT_FOUND),
                    detail=f"no device named {name!r}",
                ) from exc
            if not isinstance(device, plan.templates):
                raise HTTPException(
                    status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
                    detail=(
                        f"device {name!r} is not one of "
                        f"{[t.__name__ for t in plan.templates]}"
                    ),
                )
            kwargs[plan.name] = device
        job = await session.queue.submit(lambda: fn(**kwargs), mode=mode)
        if mode == "async":
            return _async_response(job)
        return {"result": job.result}

    handler.__name__ = f"usecase_{fn.__name__}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
    handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
            inspect.Parameter(
                "body",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=request_model,
            ),
            inspect.Parameter(
                "mode",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default="sync",
                annotation=Literal["sync", "async"],
            ),
        ]
    )
    return handler


def _plan_function(
    module_name: str, fn_name: str, fn: Any  # noqa: ANN401
) -> SkippedMethod | tuple[type, list[_ParamPlan]]:
    """Validate a function and return its request model + param plans.

    :param module_name: short module name for SkippedMethod records
    :type module_name: str
    :param fn_name: function name
    :type fn_name: str
    :param fn: the function object
    :type fn: Any
    :return: SkippedMethod when unroutable, else (request_model, plans)
    :rtype: SkippedMethod | tuple[type, list[_ParamPlan]]
    """
    try:
        sig = inspect.signature(fn, eval_str=True)
    except (ValueError, TypeError):
        return SkippedMethod(module_name, fn_name, "unintrospectable signature")
    except NameError:
        return SkippedMethod(module_name, fn_name, "unevaluable annotation")

    plans: list[_ParamPlan] = []
    for name, param in sig.parameters.items():
        if param.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            return SkippedMethod(module_name, fn_name, "has *args or **kwargs")
        if param.annotation is inspect.Parameter.empty:
            return SkippedMethod(
                module_name, fn_name, f"missing annotation on: {name}"
            )
        kind = _classify_param(param.annotation)
        if kind == "unroutable":
            return SkippedMethod(
                module_name, fn_name, f"unroutable parameter: {name}"
            )
        plans.append(
            _ParamPlan(name, kind == "device", _template_types(param.annotation))
        )

    ret = sig.return_annotation
    if ret is inspect.Parameter.empty:
        return SkippedMethod(module_name, fn_name, "missing return annotation")
    if not _is_serialisable(ret):
        return SkippedMethod(
            module_name, fn_name, f"non-serialisable return type: {ret!r}"
        )

    return _build_request_model(fn_name, sig), plans


def generate_usecase_routers(
    modules: list[ModuleType],
) -> tuple[list[APIRouter], list[SkippedMethod]]:
    """Generate FastAPI routers for the public functions of each module.

    :param modules: use-case modules to introspect
    :type modules: list[ModuleType]
    :return: generated routers and skipped functions with reasons
    :rtype: tuple[list[APIRouter], list[SkippedMethod]]
    """
    routers: list[APIRouter] = []
    all_skipped: list[SkippedMethod] = []

    for module in modules:
        short = module.__name__.rsplit(".", 1)[-1]
        router = APIRouter(
            prefix=f"/use_cases/{short}",
            tags=[f"use_cases:{short}"],
        )
        for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn_name.startswith("_"):
                continue
            if getattr(fn, "__module__", "") != module.__name__:
                continue  # skip imported symbols
            result = _plan_function(short, fn_name, fn)
            if isinstance(result, SkippedMethod):
                all_skipped.append(result)
                _log.warning(
                    "use-case route skipped: %s.%s — %s",
                    short,
                    result.method,
                    result.reason,
                )
                continue
            request_model, plans = result
            handler = _make_usecase_handler(fn, request_model, plans)
            router.post(f"/{fn_name}", status_code=200, response_model=None)(handler)
        routers.append(router)

    return routers, all_skipped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest unittests/api/test_usecase_generator.py -v`
Expected: PASS

- [ ] **Step 5: Run lint on the new module**

Run: `ruff check boardfarm3/api/routers/_usecase_generator.py && ruff format --check boardfarm3/api/routers/_usecase_generator.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add boardfarm3/api/routers/_usecase_generator.py unittests/api/test_usecase_generator.py
git commit -m "feat(api): generate use-case routers with by-name device resolution

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 6: Wire use-case modules into the plugin

**Files:**
- Modify: `boardfarm3/api/plugin.py`

**Interfaces:**
- Consumes: `generate_usecase_routers` (Task 5), the existing `RouterBundle` aggregation in `boardfarm_add_api_routers`.
- Produces: use-case routes served under `/core/use_cases/<module>/<function>`; their skips merged into the same bundle's `skipped` list.

- [ ] **Step 1: Extend the plugin hook**

In `boardfarm3/api/plugin.py`, inside `boardfarm_add_api_routers`, after computing `routers, skipped = generate_template_routers(templates)`, add use-case generation and merge before returning. Add these imports alongside the existing ones in the function:

```python
    from boardfarm3.api.routers._usecase_generator import (  # pylint: disable=import-outside-toplevel
        generate_usecase_routers,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        cpe as uc_cpe,
        dhcp as uc_dhcp,
        iperf as uc_iperf,
        networking as uc_networking,
        voice as uc_voice,
        wifi as uc_wifi,
    )
```

Then replace the `return` line:

```python
    uc_routers, uc_skipped = generate_usecase_routers(
        [uc_cpe, uc_dhcp, uc_networking, uc_wifi, uc_iperf, uc_voice]
    )
    return [
        RouterBundle(
            namespace="core",
            routers=[*routers, *uc_routers],
            skipped=[*skipped, *uc_skipped],
        )
    ]
```

- [ ] **Step 2: Run the API suite**

Run: `pytest unittests/api -v`
Expected: PASS

- [ ] **Step 3: Smoke-check the CLI + app import**

Run: `nox -s boardfarm_help`
Expected: exits 0

- [ ] **Step 4: Commit**

```bash
git add boardfarm3/api/plugin.py
git commit -m "feat(api): serve use-case routers under the core namespace

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

### Task 7: Integration tests via TestClient

**Files:**
- Create: `unittests/api/test_routers_usecase.py`

**Interfaces:**
- Consumes: the full app built by `boardfarm3.api.app.create_app`, mirroring the fixture style in `unittests/api/test_routers_lan.py` (monkeypatch `app_module.build_session`).

- [ ] **Step 1: Write the integration tests**

Create `unittests/api/test_routers_usecase.py`. Two device fakes are used deliberately: `_RealCPE` subclasses the actual `CPE` ABC (so the `isinstance` guard passes → 200 path), and `_NotACPE` does not (→ 422 path). The device manager registers both under different names.

```python
"""Integration tests for auto-generated use-case and CPE routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from boardfarm3.api import app as app_module
from boardfarm3.api.session import Session
from boardfarm3.exceptions import DeviceNotFound
from boardfarm3.templates.cpe import CPE, CPEHW, CPESW

if TYPE_CHECKING:
    from boardfarm3.api.runtime import RuntimeOptions

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_CONFLICT = 409


class _RealCPE(CPE):
    """A concrete CPE subclass so the handler's isinstance guard passes.

    The CPE ABC only requires the ``config``/``hw``/``sw`` properties; the
    use-case under test (``get_cpu_usage``) calls ``board.get_cpu_usage()``,
    which the real function delegates to ``board.sw``. To keep the test
    self-contained we stub ``get_cpu_usage`` directly on the device — the
    route dispatches to ``fn(board=<device>)`` where ``fn`` is the use-case,
    so we monkeypatch the use-case in the fixture instead (see below).
    """

    @property
    def config(self) -> dict:
        """Return an empty config.

        :return: empty dict
        :rtype: dict
        """
        return {}

    @property
    def hw(self) -> CPEHW:
        """Return a placeholder hardware object.

        :return: None placeholder
        :rtype: CPEHW
        """
        return None  # type: ignore[return-value]

    @property
    def sw(self) -> CPESW:
        """Return a placeholder software object.

        :return: None placeholder
        :rtype: CPESW
        """
        return None  # type: ignore[return-value]


class _NotACPE:
    """A device that is NOT a CPE subclass — exercises the 422 guard."""


class _FakeDeviceManager:
    """Resolves fake devices by name and by type."""

    def __init__(self) -> None:
        """Register a real CPE (``board``) and a non-CPE (``other``)."""
        self._devices: dict[str, Any] = {"board": _RealCPE(), "other": _NotACPE()}

    def get_device_by_name(self, device_name: str) -> Any:  # noqa: ANN401
        """Return the fake device by name.

        :param device_name: registered name
        :type device_name: str
        :raises DeviceNotFound: when unknown
        :return: the device
        :rtype: Any
        """
        if device_name not in self._devices:
            msg = f"no device named {device_name}"
            raise DeviceNotFound(msg)
        return self._devices[device_name]

    def get_devices_by_type(self, device_type: type) -> dict[str, Any]:
        """Return devices matching the requested type.

        :param device_type: template type to filter by
        :type device_type: type
        :return: name -> device
        :rtype: dict[str, Any]
        """
        return {
            name: dev
            for name, dev in self._devices.items()
            if isinstance(dev, device_type)
        }


class _FakeRuntime:
    """RuntimeContext stand-in installing the fake device manager on boot."""

    def __init__(self) -> None:
        """Initialise unconfigured."""
        self.config: object = None
        self.device_manager: object = None

    def refresh_cmdline_args(self) -> None:
        """No-op."""

    def resolve(self, payload: dict[str, Any]) -> object:  # noqa: ARG002
        """Set a placeholder config.

        :param payload: ignored
        :type payload: dict[str, Any]
        :return: config
        :rtype: object
        """
        self.config = object()
        return self.config

    def register_devices(self) -> object:
        """Install the fake device manager.

        :return: the device manager
        :rtype: object
        """
        self.device_manager = _FakeDeviceManager()
        return self.device_manager

    def boot_blocking(self) -> None:
        """No-op boot."""

    def release(self, deployment_status: dict[str, Any]) -> None:
        """No-op release.

        :param deployment_status: ignored
        :type deployment_status: dict[str, Any]
        """


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a booted client with a real CPE (``board``) and a non-CPE (``other``).

    The ``cpe.get_cpu_usage`` use-case is monkeypatched to a trivial stub so
    the route's dispatch (``fn(board=<device>)``) returns a fixed value
    without touching real device internals.

    :param monkeypatch: pytest monkeypatch
    :type monkeypatch: pytest.MonkeyPatch
    :yield: booted test client
    :rtype: TestClient
    """
    from boardfarm3.use_cases import cpe as uc_cpe

    def _stub_get_cpu_usage(board: CPE) -> float:  # noqa: ARG001
        return 12.5

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
        yield client
```

> **Important:** the fixture monkeypatches `boardfarm3.use_cases.cpe.get_cpu_usage` **before** `create_app` runs, because `generate_usecase_routers` captures the function object at app-build time. The stub must be installed prior to `create_app("s-test", "board-1")` in the fixture — which it is (the `monkeypatch.setattr` calls precede `create_app`).

Now add the tests to the same file:

```python
def test_usecase_route_by_name_sync(client: TestClient) -> None:
    """get_cpu_usage resolves the CPE by name and returns its value.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "board"})
    assert resp.status_code == HTTP_OK
    assert resp.json() == {"result": 12.5}


def test_usecase_route_async_returns_202(client: TestClient) -> None:
    """Async use-case call returns 202 with a job_id.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post(
        "/core/use_cases/cpe/get_cpu_usage?mode=async", json={"board": "board"}
    )
    assert resp.status_code == HTTP_ACCEPTED
    assert resp.json()["job_id"].startswith("j-")


def test_usecase_unknown_device_name_404(client: TestClient) -> None:
    """Unknown device name yields 404.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "ghost"})
    assert resp.status_code == HTTP_NOT_FOUND


def test_usecase_wrong_type_device_422(client: TestClient) -> None:
    """A device that is not a CPE yields 422.

    ``get_cpu_usage`` expects a CPE; ``other`` resolves to ``_NotACPE`` which
    is not a CPE subclass, so the isinstance guard rejects it.

    :param client: booted test client
    :type client: TestClient
    """
    resp = client.post("/core/use_cases/cpe/get_cpu_usage", json={"board": "other"})
    assert resp.status_code == HTTP_UNPROCESSABLE


def test_cpe_flatten_route_present_in_schema(client: TestClient) -> None:
    """CPE sw+hw methods are flattened under /core/templates/cpe/.

    :param client: booted test client
    :type client: TestClient
    """
    schema = client.get("/openapi.json").json()
    paths = list(schema["paths"].keys())
    assert "/core/templates/cpe/reset" in paths  # from CPESW
    assert "/core/templates/cpe/power_cycle" in paths  # from CPEHW


def test_usecase_routes_present_in_schema(client: TestClient) -> None:
    """Use-case routes are mounted under /core/use_cases/.

    :param client: booted test client
    :type client: TestClient
    """
    schema = client.get("/openapi.json").json()
    assert any(p.startswith("/core/use_cases/") for p in schema["paths"])
```

- [ ] **Step 2: Run the integration tests**

Run: `pytest unittests/api/test_routers_usecase.py -v`
Expected: PASS

- [ ] **Step 4: Run the whole API suite + lint**

Run: `pytest unittests/api -v && nox -s lint`
Expected: PASS / no lint errors

- [ ] **Step 5: Commit**

```bash
git add unittests/api/test_routers_usecase.py
git commit -m "test(api): integration coverage for use-case and CPE flatten routes

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>"
```

---

## Final verification

- [ ] Run the full unit suite: `pytest unittests -q`
- [ ] Run the full lint suite: `nox -s lint`
- [ ] Run pylint: `nox -s pylint`
- [ ] Smoke-check the CLI: `nox -s boardfarm_help`
- [ ] Inspect skipped routes at runtime (optional manual check): boot the agent and `GET /diagnostics/skipped-routes` — confirm CPE/NTU non-serialisable methods (e.g. `get_console`, `wifi`) and unroutable use cases (dataclass-param DHCP analysers, `@contextmanager` functions, iperf `IPerf3TrafficGenerator` returns) appear with reasons.
