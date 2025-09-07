# Development (How-to-Guide)

- [Writing a Boardfarm plugin](/docs/development.md#writing-a-boardfarm-plugin)
- [Writing a Connection class](/docs/development.md#writing-a-connection-class)
- [Writing a Device class](/docs/development.md#writing-a-device-class)
- [Writing a Use Case](/docs/development.md#writing-a-use-case)

## Writing a Boardfarm plugin

A Boardfarm plugin project typically follows the convention `boardfarm_<plugin_name>` and contains a small, focused set of packages that implement devices, plugin registration, templates, use cases and shared libraries.

> **Note:** below I use DeviceA as a generic device implementation name. Replace DeviceA and <plugin_name> with your concrete names.

```bash
boardfarm_<plugin_name>/
├── devices/             # concrete device implementations (classes)
│   ├── __init__.py
│   └── device_a.py
├── plugins/             # modules that register to the plugin manager (hookimpl)
│   ├── __init__.py
│   └── registration.py
├── templates/           # optional: extra Template ABCs (vendor/plugin-specific)
│   ├── __init__.py
│   └── custom_template.py
├── use_cases/           # optional: plugin-level use cases
│   ├── __init__.py
│   └── provisioning.py
├── lib/                 # helper libraries reused by devices / use cases
│   ├── __init__.py
│   └── helpers.py
├── pyproject.toml
└── README.md
```

### Directory roles

- `devices/` — Concrete implementations of templates (e.g. `DeviceA`). These classes will be instantiated by Boardfarm (via `DeviceManager`) when inventory entries reference your `type`.
- `plugins/` — Module(s) that export `@hookimpl` functions such as `boardfarm_add_devices()`, `boardfarm_add_cmdline_args()`, `boardfarm_setup_env()`, etc. These make your package discoverable to Boardfarm and Pluggy.
- `templates/` — *(optional)* Plugin-specific additional ABCs or mixins. Prefer extending the main boardfarm repo templates where possible.
- `use_cases/` — *(optional)* Higher-level plugin logic composed from template methods (for internal tests or helper scripts).
- `lib/` — Shared utilities used by your device drivers (parsers, networking helpers, common retry wrappers, …).
- `pyproject.toml` — Project metadata and entry-points so Boardfarm can discover the plugin.

---

### pyproject.toml (entry-point)

Boardfarm discovers plugins by loading setuptools/PEP-621 entry-points in the `boardfarm` group.

Here's an example `pyproject.toml` (replace `<plugin_name>` with your package name — example below uses `boardfarm_plugin_a`):

```toml
[project]
name = "boardfarm_plugin_a"
version = "0.0.1"
description = "Boardfarm plugin with Device A"
readme = "README.md"
requires-python = ">=3.11"
authors = [
  { name = "Ketone", email = "devs@ketone.example" }
]

[project.entry-points."boardfarm"]
# the importable module path that contains your @hookimpl functions
boardfarm_plugin = "boardfarm_plugin_a.plugins.registration"
```

**Template (Generic)**:

```toml
[project]
name = "boardfarm_<plugin_name>"
...
[project.entry-points."boardfarm"]
boardfarm_plugin = "boardfarm_<plugin_name>.plugins.registration"

```

> **Notes:**
>
> - `boardfarm_plugin` is an arbitrary key — Boardfarm will load the value (plugin module) in the `boardfarm` entry-point group.
> - Ensure your package name and entry-point module are importable when the package is installed.

### Making your plugin discoverable

From your project root, install the package (use editable option during development):

```bash
pip install -e .
```

This registers the `boardfarm` entry-point for your package in the current environment so `plugin_manager.load_setuptools_entrypoints("boardfarm")` can find it. This way the runner registers the @hookimpl functions with the Pluggy PluginManager.

After loading:

- Boardfarm may call your core hooks (e.g., `boardfarm_add_cmdline_args`) during runner setup.
- The runner uses `boardfarm_add_devices()` mapping to know which concrete classes correspond to inventory "type" values.

## Writing a Device class

### Minimal plugin example

Create `plugins/registration.py` and implement `@hookimpl` functions. Keep core hooks module-level and device hooks as `@hookimpl` instance methods inside device classes in `devices/`.

#### `plugin/registration.py`

```python
# plugins/registration.py
from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm_<plugin_name>.devices.device_a import DeviceA  # replace with your package

@hookimpl
def boardfarm_add_devices() -> dict[str, type[BoardfarmDevice]]:
    """Register the concrete device types this package provides."""
    return {
        "device_a": DeviceA,
    }

@hookimpl
def boardfarm_add_cmdline_args(argparser):
    argparser.add_argument("--devicea-debug", action="store_true", help="Enable DeviceA plugin debug")

```

#### `templates/device.py` (Skeleton)

```python
# templates/device.py
from abc import ABC, abstractmethod

class DevA(ABC):
    """Minimal template for DeviceA-style devices.

    Implementations must provide `method_x`. Use cases and tests should
    depend on this ABC, not concrete classes.
    """

    @abstractmethod
    def method_x(self, payload=None, timeout=None):
        """Perform method_x on the device.

        :param payload: optional input data
        :param timeout: optional timeout in seconds
        :return: result (implementation-specific)
        """
        raise NotImplementedError

```

#### `devices/device_a.py` (Skeleton)

```python
# devices/device_a.py
from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm_plugin_a.templates.device import DevA

class DeviceA(LinuxDevice, DevA):
    def __init__(self, config, cmdline_args):
        super().__init__(config, cmdline_args)
        # initialization...

    def method_x(self, payload=None, timeout=None):
        """Concrete implementation of the template method."""
        # do device interaction (SSH/HTTP/console/etc.)
        return {"status": "ok", "payload": payload}

    @hookimpl
    def boardfarm_server_boot(self):
        self._connect()
        # any init steps

    @hookimpl
    def contingency_check(self, env_req, device_manager=None):
        # raise ContingencyCheckError on failure, or return None on success
        pass
```

**Why instance methods for device hooks?**

Device hooks often require access to device instance state (console, HTTP client, config). Decorating instance methods with @hookimpl allows the runner to call the method on the instantiated device object.

#### Inventory example for `DeviceA`

Boardfarm looks up the `type` value from the inventory and instantiates the registered class (e.g. `DeviceA`) for that entry.
The root-level key in this example is `plugin-a-board1` and it contains a `devices` list.

```json
{
  "plugin-a-board1": {
    "devices": [
      {
        "name": "devicea-1",
        "type": "device_a",
        "connection_type": "authenticated_ssh",
        "ipaddr": "192.168.1.10",
        "port": 22,
        "username": "root",
        "password": "changeme",
        "options": "some-option,other-flag",
        "color": "blue"
      }
    ]
  }
}
```

#### Runtime behavior

- At setup the runner passes the device entry (the full dict) into the device constructor: `DeviceA(config_for_entry, cmdline_args)`.
- Device implementations should read required fields from their `config` (e.g. `self._config.get("ipaddr")`) and raise a clear error if required keys are missing.
- If your driver needs additional inventory keys (serial, product_class, oui, vlans, etc.), document them in your plugin README and validate them in `validate_device_requirements` or during device instantiation.

## Writing a Connection class

### Connection layer (transport vs device logic)

Boardfarm separates **transport** (how you talk to a device) from **device logic** (what you do with the device). The connection layer (classes like `SSHConnection`, `TelnetConnection`, `LocalCmd`, etc.) implements a small, consistent console API (based on `BoardfarmPexpect`) that device implementations use to execute commands, read output, and perform interactive tasks.

The `connection_factory(...)` centralizes creating the right connection object based on the inventory `connection_type` and parameters. Devices call the factory, get back a `BoardfarmPexpect`-derived object, and use its methods (`sendline`, `expect`, `execute_command`, `get_last_output`, async variants, etc.) — the device code does not need to know whether the transport is SSH, serial, telnet or a `docker exec`-style local command.

#### Benefits

- **Transport abstraction** — device code is written once; the transport can change without touching use-cases or device implementations.
- **Consistent API** — devices always call the same methods (sync/async) on the returned connection object.
- **Centralized error handling & logging** — connection classes raise framework errors (`DeviceConnectionError`, `BoardfarmException`, `EnvConfigError`) and handle console-log saving in one place.
- **Easier testing & mocking** — swap real connections for fakes/mocks implementing the same API.
- **Extensibility** — add new transports by implementing a connection class and registering it in `connection_factory`.
- **Async support** — many connection classes provide both sync and async methods (`login_to_server_async`, `execute_command_async`) for scalable parallel provisioning.

---

### How devices use it — typical flow (`_connect`)

A device usually implements a `_connect()` helper that:

1. Calls `connection_factory(...)` with `connection_type` and connection params from the `inventory` JSON entry.
2. Calls `login_to_server(...)` (or `login_to_server_async(...)`) to complete authentication.
3. Normalizes the terminal (for example `stty columns 400; export TERM=xterm`) to make command output parsing stable.

#### Compact example (`_connect` method for device A)

```python
def _connect(self) -> None:
    """Establish connection to the device via SSH (or other transport)."""
    if self._console is None:
        # create the right connection object based on inventory
        self._console = connection_factory(
            self._config.get("connection_type"), # check INV JSON
            f"{self.device_name}.console",
            ... # remaining args
        )

        # perform authentication (sync or async variant)
        self._console.login_to_server(password=self._password)

        # stabilize terminal for predictable parsing
        self._console.execute_command("stty columns 400; export TERM=xterm")
```

#### Notes / tips

- **Use `connection_factory`** rather than creating transport objects directly — it keeps device code portable and consistent.
- **Prefer high-level helpers** like `execute_command()` unless you need fine-grained `expect()` control. High-level helpers handle prompt/timeout edge cases for you.
- **Validate required inventory fields** (`ipaddr`, `port`, `username`, etc.) during device construction or in `validate_device_requirements` so failures are detected early.
- **Use async methods for concurrency**: if your device supports asyncio and you implement `*_async` hooks, call `login_to_server_async()` and `execute_command_async()` to avoid blocking other provisioning tasks.

## Writing a Use Case

This short how-to shows a small **use case** that provisions a `DeviceA`-style device by calling the templated API `method_x`. The use case depends only on the **template (ABC)** — `DevA` — not on any concrete implementation. This keeps tests and scripts vendor-agnostic.

**File:** `use_cases/provisioning.py`

```python
# use_cases/provisioning.py
from __future__ import annotations
from typing import Any

# import the template/ABC, not a concrete class
from boardfarm_plugin_a.templates.device import DevA


def provision_device(
    device: DevA,
    config: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Provision a DeviceA-style device."""
    payload = config or {"action": "default_provision"}

    # call the templated API
    # concrete DeviceA (or any other implementation)
    # will perform the actual transport/IO
    result = device.method_x(payload=payload, timeout=timeout)

    # basic validation of result (example)
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise RuntimeError(f"Provisioning failed: {result}")

    return result
```

### Example Usage

#### Interactive Shell (IPython)

```Python
from boardfarm_plugin_a.templates.device import DevA
from boardfarm3.lib.device_manager import DeviceManager
from boardfarm_plugin_a.use_cases.provisioning import provision_device

# device_manager is provided by the runner / interact session
device: DevA = device_manager.get_device_by_type(DevA)
result = provision_device(device, config={"action": "apply_profile", "profile": "A1"})
print(result)

```

#### Pytest Example

```Python
def test_provision_device(device_manager):
    device = device_manager.get_device_by_type(DevA)
    res = provision_device(device, {"action": "apply_profile", "profile": "CI"}, timeout=60)
    assert res["status"] == "ok"

```

### Design notes & best practices

- **Type hints use the template (ABC)** — `DevA` — so the use case is independent of concrete drivers.
- **Keep use cases small and focused** — orchestration and business logic belong here; transport and vendor quirks remain in device implementations.
- **Propagate errors** so tests/runner can handle retries or fail fast. Optionally use retry helpers (e.g. `retry_on_exception`) for transient operations.
- **Return a stable structure** (e.g. `{"status": "ok", "data": {...}}`) so callers can assert on consistent fields across vendors.
- **Document expected payload keys** for `config` in the plugin README so integrators know which fields a concrete `DeviceA` expects.

> **Tip — use-cases are business logic, name them by protocol/behavior, not by device type.**
> In networking, prefer protocol- or feature-oriented names for use case modules (for example `use_cases/tr069.py` for ACS/TR-069 operations) rather than `use_cases/acs_device.py`. Templates abstract device types — use case names should reflect the business operation (e.g. `tr069`, `dhcp_provision`, `firmware_flash`) so they remain meaningful across different implementations.


---

Click here to go back to main [README](/README.md#documentation)
