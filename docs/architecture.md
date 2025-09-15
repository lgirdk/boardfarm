# Overview

## Introduction

End-to-end (E2E) solutions for CPE, access and back-office stacks are inherently complex:

- they depend on **many different components** (CPE, ACS, DHCP, SIP, OSS/BSS, emulators, etc.),
- span **multiple layers of integration**,
- involve **multi-vendor delivery**, and
- evolve at **varying development cadences** with **many transitive dependencies**.

At every integration level, each incremental change must be validated against **multiple, evolving target deployment environments**:

- different customers run different topologies and component versions,
- each environment changes over time, and
- late discovery or poor reproducibility of environment differences drives up cost and delays.

## The vendor/team challenge

Vendors and engineering teams must simultaneously:

- deliver new functionality,
- design, build, integrate and validate features, and
- avoid regressions — which requires large amounts of regression testing.

To be effective, development and validation must happen **against the relevant environments**: using the particular versions and configurations of the neighbouring components that exist in a real E2E deployment.

## Architecture

Boardfarm’s architecture is designed to address these realities by emphasizing:

![boardfarm architecture](https://raw.githubusercontent.com/lgirdk/boardfarm/master/docs/images/architecture.svg)

- **Top-down (inward) dependencies only** — stable, inner layers define contracts; outer layers implement them.
- **Non-restrictive API standardization** — provide clear, compact templates (ABCs) so use cases and tests stay vendor-agnostic.
- **Maximized portability** — make each layer easy to reuse across customers and testbeds.
- **Extensibility via plugins** — add new device classes, transports or behaviors as plugins rather than changing the core.

### How this is achieved

- **Templates (ABCs)** define stable device APIs that use cases and hooks rely on.
- **Concrete device classes** implement those templates for vendors, emulators or transports.
- **Pluggy (plugin manager + hooks)** orchestrates multi-phase provisioning and lifecycle events across the infrastructure (boot, configure, attach, etc.).
- **Use Cases** protocol-specific, test-facing operations; the API tests and the interactive shell use.

Together, these principles make Boardfarm a portable, testable framework that helps teams develop, validate and debug E2E functionality against representative, reproducible environments while minimizing the cost of integrating multi-vendor stacks.

## Core Components

### Templates (ABCs)

**What they are**: Python Abstract Base Classes that describe the minimal set of methods a device must offer for Boardfarm use cases to work.

**Why they matter**: Use cases and hooks import these Templates, ***not concrete device classes***. That guarantees portability: a test calls the template API, not vendor-specific code.

**Example sketch:**

```python
from abc import ABC, abstractmethod

GpvInput = Union[str, list[str]]
GpvStruct = dict[str, Union[str, int, bool]]
GpvResponse = list[GpvStruct]

class ACS(ABC):
    """Boardfarm ACS device template."""

    @abstractmethod
    def GPV(
        self,
        param: GpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> GpvResponse:
        ...

    ... # rest of the API definition
```

**Guidelines**:

- Keep signatures high-level and stable.
- Add capabilities via optional mixins or new ABCs rather than changing existing method signatures.
- Document expected return types and exceptions.

### Devices (Concrete implementations)

**What they are**: Classes that implement a Template (ABC). They translate Template methods into transport-specific actions (SSH, serial, HTTP, local command, docker exec, QEMU socket, etc.).

> **Important**: Device classes may also implement device hooks (`hookspecs`) to participate in the boot/provision lifecycle — but those hook implementations should only call the templated APIs and perform device-specific I/O. Avoid exposing these vendor-specific private APIs to use cases.

**Example:**

```python
from boardfarm3.templates.acs import ACS, GpvInput, GpvResponse

class GenieACS(ACS):

    def GPV(
        self,
        param: GpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> GpvResponse:
        """Send GetParamaterValues command via ACS server."""
        quoted_id = quote('{"_id":"' + cpe_id + '"}', safe="")
        self._request_post(
            endpoint="/devices/" + quote(cpe_id) + "/tasks",
            data=self._build_input_structs_gpv(param),
            conn_request=True,
            timeout=timeout,
        )
        response_data = self._request_get(
            "/devices"  # noqa: ISC003
            + "?query="
            + quoted_id
            + "&projection="
            + self._build_input_structs(param),
            timeout=timeout,
        )
        return GpvResponse(self._convert_response(response_data))

    ... # rest of the implementation

```

**Rules:**

- Devices are only meant to drive I/O and vendor-specific quirks.
- Do not implement business logic in devices — they will always be implemented in use cases.

### Use Cases

**What they are**: The library of testable, protocol-specific operations.

#### Why use cases?

- Tests call use cases (e.g., GPV, flash_firmware) rather than device methods directly.
- Use cases hide which concrete device handles the operation — the Template contract ensures compatibility.

**Example**:

```python
"""TR-069 Use cases."""

from __future__ import annotations

if TYPE_CHECKING:
    from boardfarm3.templates.acs import ACS
    from boardfarm3.templates.cpe import CPE

def get_parameter_values(
    params: str | list[str],
    acs: ACS,
    board: CPE,
) -> list[dict[str, Any]]:
    """Perform TR-069 RPC call GetParameterValues."""

    return acs.GPV(params, cpe_id=board.sw.tr69_cpe_id)
```

**Example usage (in IPython or pytest)**:

```python
from boardfarm3.use_cases.tr069 import get_parameter_values
from boardfarm3.templates.acs import ACS
from boardfarm3.templates.cpe import CPE

from boardfarm3.lib.device_manager import DeviceManager

value = get_parameter_value(
    'Device.DeviceInfo.Manufacturer',
    device_manager.get_device_by_type(ACS),
    device_manager.get_device_by_type(CPE),
    )
```

## Summary

- **Stable contract (Template/ABC)** — The ACS template (an ABC) declares the `GPV`(...) -> `GpvResponse` API and the expected input/output types.
- **Dependency inversion** — Use cases (`get_parameter_values`) accept an ACS instance (the interface) rather than a concrete class.
- **Pluggable device implementations** — Concrete classes like `GenieACS` implement the ACS ABC and provide transport/vendor-specific logic.
- **Runtime selection via DeviceManager** — Tests call `device_manager.get_device_by_type(ACS)` to obtain any registered ACS device. The test code doesn’t change when you swap GenieACS for AxirosACS (or a simulator).
- **Easy mocking & CI-friendly** — You can inject fakes or mocks that implement the ACS interface for fast, deterministic unit tests and CI runs without hardware.

**Result:** tests written against the ACS template are vendor-agnostic — you can run the same test suite against real hardware, vendor servers, or simulated ACS backends without changing test code.

## Hooks Specification and Pluggy

Boardfarm uses **Pluggy** as the central plugin manager. Pluggy provides the extension points (`@hookspecs`) that let different repositories register device classes, extend runner behaviour, and participate in the multi-phase environment boot/provision lifecycle. The design principle is simple:

- **Framework (core) concerns** are exposed as `core hooks` — used to customize runner behavior (CLI args, config parsing, device reservation, environment setup, device registration, release and shutdown).
- **Device concerns** are expressed as `device hooks` — implemented by concrete device classes (plugins) to perform boot, configuration, validation and shutdown for that device.
- The runner invokes core hooks to orchestrate the run; core hooks in turn cause the runner to call device hooks for each device in the configured order.

### Hook categories & where they belong

**Core hooks (framework-level)** — implemented by runner or plugin authors.
These orchestrate the overall lifecycle of a run:

- `boardfarm_add_cmdline_args(argparser)` — add CLI flags.
- `boardfarm_parse_config(...) -> BoardfarmConfig` *(firstresult)* — produce/override the merged run config.
- `boardfarm_reserve_devices(...) -> inventory` *(firstresult)* — reserve lab hardware before deployment.
- `boardfarm_setup_env(...) -> DeviceManager` *(firstresult)* — deploy devices and build the `DeviceManager`.
- `boardfarm_register_devices(...) -> DeviceManager` *(firstresult)* & `boardfarm_add_devices()` — register device classes (map inventory `"type"` → class).
- `boardfarm_release_devices(...)` & `boardfarm_shutdown_device()` — release reserved devices and perform framework cleanup.

---

**Device hooks (device-level)** — implemented by device authors (usually as `@hookimpl` instance methods on concrete device classes).
These drive device-specific behavior within the lifecycle:

- `boardfarm_skip_boot` — initialize/attach to device without provisioning.
- `boardfarm_server_boot` / `boardfarm_device_boot` / `boardfarm_attached_device_boot` — boot device categories in sequence.
- `boardfarm_server_configure` / `boardfarm_device_configure` / `boardfarm_attached_device_configure` — apply environment-driven configuration.
- `contingency_check(env_req, device_manager)` — per-test health check used by pytest integration.
- `*_async` variants — available where concurrency helps speed up provisioning.

### Device categories

A Boardfarm device should be one of:

1. **server** — infrastructure services (ACS, DHCP, SIP, etc.).
2. **device** — main DUTs/CPEs that depend on infrastructure.
3. **attached device** — clients attached to devices (LAN clients, phones, etc.).

Each category participates in different lifecycle phases and must implement hooks appropriate to that category.

---

### Execution order

When boot is enabled, Boardfarm executes device hooks in this order (each name is an actual `@hookspec`):

```markdown
boardfarm_server_boot
↓
boardfarm_server_configure
↓
boardfarm_device_boot
↓
boardfarm_device_configure
↓
boardfarm_attached_device_boot
↓
boardfarm_attached_device_configure
```

### Minimal checklist for architecture readers

- **Core hooks** extend and orchestrate the runner; **device hooks** implement per-device behavior.
- **Use cases** depend on **Templates (ABCs)** only — device implementations plug in behind the Templates via hooks.
- The **runner** uses core hooks to build the environment and then calls device hooks in the documented order.
- See the dedicated **“How to implement”** page for step-by-step examples (device skeletons, core hook examples, tests and best practices).

### Execution Order (Comprehensive View)

The following diagram explains in brief the execution lifecycle of the boardfarm runner:
![Hook Flow architecture in detail.](https://raw.githubusercontent.com/lgirdk/boardfarm/master/docs/images/boardfarm_revised_hook_flow.svg)
