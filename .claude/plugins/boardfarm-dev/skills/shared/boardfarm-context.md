# Boardfarm Shared Context

This file is read at the start of Phase 1 by every boardfarm-dev sub-skill.
It contains the architecture overview, live discovery commands, naming
conventions, and layer discipline rules that all sub-skills must follow.

---

## 1. Architecture Overview

Boardfarm is a 4-layer framework. Dependencies always flow inward (outer layers
depend on inner layers; inner layers never import outer layers).

| Layer | Location | Purpose |
|-------|----------|---------|
| **Templates** | `boardfarm3/templates/` | Abstract base classes (ABCs) — the stable, vendor-agnostic API surface. Use cases and tests import only these. |
| **Devices** | `boardfarm3/devices/` | Concrete classes implementing Templates. Handle transport I/O (SSH/serial/HTTP) and vendor quirks. No business logic. |
| **Use Cases** | `boardfarm3/use_cases/` | Protocol/feature functions typed against Template ABCs. The API that tests and the interactive shell call. |
| **Lib** | `boardfarm3/lib/` | Shared infrastructure: connections, device manager, pexpect, parsers. |

The plugin system (Pluggy) orchestrates device lifecycle hooks in a fixed order:
`server_boot → server_configure → device_boot → device_configure →
attached_device_boot → attached_device_configure`

---

## 2. Discovery Commands

Run these commands to build menus from the live repo state before interviewing.

### Available templates

```bash
for f in boardfarm3/templates/*.py boardfarm3/templates/**/*.py; do
    [ -f "$f" ] && grep -H "^class " "$f"
done
```

For detail on a specific template's abstract methods:

```bash
grep -n "@abstractmethod\|^    def \|^class " boardfarm3/templates/<filename>.py
```

### Available connection types (for device classes)

```bash
grep "^class " boardfarm3/lib/connections/*.py
```

Connection type keys registered in `connection_factory`:

```bash
grep '"[a-z_]*":' boardfarm3/lib/connection_factory.py
```

### Base device classes

```bash
grep "^class " boardfarm3/devices/base_devices/boardfarm_device.py \
              boardfarm3/devices/base_devices/linux_device.py
```

- `BoardfarmDevice` — base for all devices; use when device has no Linux shell
- `LinuxDevice(BoardfarmDevice)` — use when device has a Linux shell (SSH/serial/telnet)

### Existing device `type` keys (avoid duplicates)

```bash
grep -o '"[a-z_]*"' boardfarm3/configs/boardfarm_inventory_schema.json | sort -u | head -40
```

---

## 3. Naming Conventions

| Thing | Pattern | Examples |
|-------|---------|----------|
| Template class | `PascalCase`, noun | `ACS`, `LAN`, `Provisioner`, `SIPServer` |
| Device class | vendor/transport prefix + category | `AxirosACS`, `LinuxLAN`, `KeaProvisioner` |
| Connection class | transport + `Connection` suffix | `SSHConnection`, `TelnetConnection` |
| Use-case module | protocol or feature name | `dhcp.py`, `voice.py`, `wifi.py` |
| Module file | `snake_case.py` | `axiros_acs.py`, `linux_lan.py` |
| Entry-point key | `snake_case`, matches inventory `"type"` field | `axiros_acs_rest`, `linux_lan` |

---

## 4. Layer Discipline Rules (enforce when generating)

These rules must be reflected in every generated scaffold. Violating them
causes `nox -s lint` and `mypy` failures.

1. **Use cases import Templates, never concrete device classes.**
   ```python
   # correct
   from boardfarm3.templates.lan import LAN
   # wrong — never do this in use_cases/
   from boardfarm3.devices.linux_lan import LinuxLAN
   ```

2. **Devices use `connection_factory()`, never direct transport instantiation.**
   ```python
   # correct
   from boardfarm3.lib.connection_factory import connection_factory
   self._console = connection_factory("ssh_connection", self.device_name, ...)
   # wrong
   self._console = SSHConnection(...)
   ```

3. **Device lifecycle hooks are `@hookimpl` instance methods.**
   ```python
   from boardfarm3 import hookimpl

   class MyDevice(LinuxDevice, MyTemplate):
       @hookimpl
       def boardfarm_device_boot(self, config, cmdline_args, device_manager):
           ...
   ```

4. **Docstrings are sphinx-style on all public APIs.**
   ```python
   def my_method(self, param: str) -> int:
       """One-line summary.

       :param param: description of param
       :type param: str
       :return: description of return value
       :rtype: int
       """
   ```

5. **All public APIs must have complete type annotations** (enforced by
   `mypy --disallow-untyped-defs`). Use `from __future__ import annotations`
   at the top of every generated file.

6. **Hook category determines which hook methods to implement:**

   | Category | Boot hook | Configure hook |
   |----------|-----------|----------------|
   | server | `boardfarm_server_boot` | `boardfarm_server_configure` |
   | device | `boardfarm_device_boot` | `boardfarm_device_configure` |
   | attached device | `boardfarm_attached_device_boot` | `boardfarm_attached_device_configure` |

   Each hook also has an `_async` variant (e.g., `boardfarm_device_boot_async`).
   Implement the async variant only if the device needs async I/O.

---

## 5. Generated Artefacts Checklist (all four required per sub-skill)

Every sub-skill Phase 3 must produce:

1. **Python stub** — placed in the correct `boardfarm3/` subdirectory per sub-skill type
2. **Inventory JSON snippet** — minimal valid block, consistent with `boardfarm_inventory_schema.json`
3. **Unit test stub** — under `unittests/`, types against Template ABC (never concrete class)
4. **pyproject.toml snippet** — `[project.entry-points."boardfarm"]` registration line

After generating, print a **completion checklist** listing what was created and
what the developer still needs to fill in, plus the lint/test commands to run:
`nox -s lint` and `pytest unittests/<path>/test_<name>.py`.
