---
name: boardfarm-dev:new-device
description: Guide for creating a new boardfarm concrete device class. Use when a developer needs to implement a vendor- or transport-specific device that satisfies an existing template. Triggers on: "new device", "add a device", "implement a template", "write a device class", "new CPE device", "new ACS implementation", "concrete implementation of". Follow the 3-phase contract: Discover → Interview → Generate.
---

# boardfarm-dev: new-device

You scaffold a new boardfarm device class in `boardfarm3/devices/`.

---

## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory.

**Then run:**

```bash
# Available templates to implement
for f in boardfarm3/templates/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    grep -H "^class " "$f"
done

# Templates in subdirectories
find boardfarm3/templates -name "*.py" ! -name "__init__.py" \
  -exec grep -H "^class " {} \;

# Available connection types (class names)
grep "^class " boardfarm3/lib/connections/*.py

# Connection type string keys registered in connection_factory
grep -o '"[a-z_]*":' boardfarm3/lib/connection_factory.py

# Base classes available
grep "^class " boardfarm3/devices/base_devices/boardfarm_device.py \
              boardfarm3/devices/base_devices/linux_device.py

# Existing device type keys (to avoid collisions)
grep '"type"' boardfarm3/configs/boardfarm_inventory_schema.json | head -30
```

Build menus for: available templates, available connection type keys, base
classes. **Ask no questions yet.**

---

## Phase 2 — Interview (one question at a time)

**Before Q1:** check whether
`.claude/plugins/boardfarm-dev/.cache/interview-defaults.json` exists and has
a `"new-device"` entry:

```bash
python -c "
import json, os
path = '.claude/plugins/boardfarm-dev/.cache/interview-defaults.json'
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(json.dumps(data.get('new-device', {}), indent=2))
else:
    print('{}')
"
```

If it returns a non-empty object, remember these values as suggested
defaults for Q3 (`base_class`), Q4 (`connection_type`), and Q5
(`hook_category`) below — weave each into its question as "(used last
time)" next to the matching option. The developer still answers every
question; this never skips a question or silently reuses a value without
the developer seeing and confirming it.

**Q1:** What is the Python class name? (PascalCase, vendor or transport prefix +
category, e.g. `AxirosACS`, `KeaProvisioner`, `LinuxWAN`)

**Q2:** Which template(s) does this device implement?

Show the discovered template list. The developer may pick one or more.
Remind them: if the template doesn't exist yet, run `/boardfarm-dev:new-template` first.

**Q3:** Which base class?

```
[1] LinuxDevice  — device has a Linux shell (SSH / serial / telnet access)
[2] BoardfarmDevice — device has no shell (REST API, HTTP only, etc.)
```

If the cache lookup above returned a `base_class` value, annotate the
matching option with "(used last time)", e.g. if the cached value is
`LinuxDevice`:

```
[1] LinuxDevice (used last time) — device has a Linux shell (SSH / serial / telnet access)
[2] BoardfarmDevice — device has no shell (REST API, HTTP only, etc.)
```

**Q4:** Which connection type does it use?

Show the discovered connection type key list. Also accept "none" if the device
uses only HTTP (e.g. a REST-only ACS). If the cache lookup returned a
`connection_type` value, annotate the matching key in the list with "(used
last time)".

**Q5:** Which hook category?

```
[1] server         — boots before other devices (e.g., WAN, ACS, DHCP, TFTP)
[2] device         — the DUT under test (e.g., CPE)
[3] attached device — client devices (e.g., LAN, WLAN clients, phones)
```

If the cache lookup returned a `hook_category` value, annotate the matching
option with "(used last time)".

**Q6:** What inventory JSON keys does this device require?

Say: "Tell me the inventory keys one at a time. For each: key name, value type,
required or optional, example value. Say 'done' when finished."

Must-haves for console-connected devices: `name`, `type`, `ipaddr`, `username`,
`password`, `connection_type`. Remind the developer if they omit required keys.

**Q7:** What is the inventory `type` string (the entry-point key)?

Suggest `<vendor>_<category>` in snake_case (e.g., `axiros_acs_rest`,
`kea_provisioner`). Confirm it doesn't collide with existing keys discovered
in Phase 1.

**Q8:** Confirm before generating.

Show a summary:
```
Class:        <ClassName>(<BaseClass>, <TemplateName>)
Module:       boardfarm3/devices/<module_name>.py
Template(s):  <TemplateName>
Connection:   <connection_type_key>
Hook category: <server|device|attached device>
Entry-point:  <entry_point_key> = "boardfarm3.devices.<module_name>"
Inventory keys: <key_list>
```

Ask: "Does this look right? (yes / adjust)"

---

## Phase 3 — Generate

### Artefact 1 — Python stub

Write `boardfarm3/devices/<module_name>.py`:

```python
"""Boardfarm <ClassName> device module."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import TYPE_CHECKING

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import <BaseClass>
from boardfarm3.lib.connection_factory import connection_factory
from boardfarm3.templates.<template_module> import <TemplateName>

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_config import BoardfarmConfig
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


class <ClassName>(<BaseClass>, <TemplateName>):
    """<ClassName> — <one-line description>."""

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize <ClassName>.

        :param config: device configuration dictionary; required keys:
            ``name``, ``type``, <list required inventory keys>
        :type config: dict
        :param cmdline_args: parsed command-line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)

    def _connect(self) -> None:
        """Establish connection to the device.

        :return: None
        :rtype: None
        """
        self._console: BoardfarmPexpect = connection_factory(
            "<connection_type_key>",
            self.device_name,
            ip_addr=self._config["ipaddr"],
            username=self._config.get("username", "root"),
            password=self._config.get("password"),
            shell_prompt=self._shell_prompt,
            port=self._config.get("port", 22),
            save_console_logs=self._config.get("save_console_logs", ""),
        )

    # -------------------------------------------------------------------------
    # <TemplateName> abstract method implementations
    # -------------------------------------------------------------------------

    # TODO: implement every abstract method declared in <TemplateName>
    # Run: grep "@abstractmethod" boardfarm3/templates/<template_module>.py
    # to see the full list.

    # -------------------------------------------------------------------------
    # Lifecycle hooks
    # -------------------------------------------------------------------------

    @hookimpl
    def boardfarm_<hook_category>_boot(
        self,
        config: BoardfarmConfig,
        cmdline_args: Namespace,
        device_manager: DeviceManager,
    ) -> None:
        """Boot the <ClassName> device.

        :param config: boardfarm environment configuration
        :type config: BoardfarmConfig
        :param cmdline_args: parsed command-line arguments
        :type cmdline_args: Namespace
        :param device_manager: device registry instance
        :type device_manager: DeviceManager
        :return: None
        :rtype: None
        """
        self._connect()
        # TODO: add boot steps (e.g. wait for prompt, check version)

    @hookimpl
    def boardfarm_<hook_category>_configure(
        self,
        config: BoardfarmConfig,
        cmdline_args: Namespace,
        device_manager: DeviceManager,
    ) -> None:
        """Configure the <ClassName> device.

        :param config: boardfarm environment configuration
        :type config: BoardfarmConfig
        :param cmdline_args: parsed command-line arguments
        :type cmdline_args: Namespace
        :param device_manager: device registry instance
        :type device_manager: DeviceManager
        :return: None
        :rtype: None
        """
        # TODO: add configure steps (apply user-driven config)
```

Use the hook method names from `boardfarm-context.md` section 4, rule 6.
If the developer asked for async hooks too, add the `_async` variants with
`async def` signatures.

### Artefact 2 — Inventory JSON snippet

```json
{
    "name": "<device-name>",
    "type": "<entry_point_key>",
    "ipaddr": "192.168.1.1",
    "username": "root",
    "password": "changeme",
    "connection_type": "<connection_type_key>",
    "port": 22
}
```

Include only the keys the developer listed in Q6. Omit optional keys that have
sensible defaults in `__init__`.

### Artefact 3 — Unit test stub

Write `unittests/devices/test_<module_name>.py`:

```python
"""Unit tests for <ClassName>."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

import pytest

from boardfarm3.templates.<template_module> import <TemplateName>


def test_<module_name>_is_<template_lower>_subclass() -> None:
    """Verify <ClassName> is a subclass of <TemplateName>.

    :return: None
    :rtype: None
    """
    from boardfarm3.devices.<module_name> import <ClassName>

    assert issubclass(<ClassName>, <TemplateName>)


def test_<module_name>_init_with_valid_config() -> None:
    """Verify <ClassName> initialises without error given a minimal valid config.

    :return: None
    :rtype: None
    """
    from boardfarm3.devices.<module_name> import <ClassName>

    config = {
        "name": "test-<module_name>",
        "type": "<entry_point_key>",
        "ipaddr": "127.0.0.1",
        "username": "root",
        "password": "test",
        "connection_type": "<connection_type_key>",
    }
    with patch.object(<ClassName>, "_connect", return_value=None):
        device = <ClassName>(config, Namespace())

    assert device.device_name == "test-<module_name>"
    assert device.device_type == "<entry_point_key>"
```

### Artefact 4 — pyproject.toml snippet

```toml
# Add this line under the existing [project.entry-points."boardfarm"] section
# in pyproject.toml at the repo root:
<entry_point_key> = "boardfarm3.devices.<module_name>"
```

### Save interview defaults

After the developer confirms "yes" at Q8 and all artefacts above are
written, persist the stable answers for next time:

```bash
python -c "
import json, os
path = '.claude/plugins/boardfarm-dev/.cache/interview-defaults.json'
os.makedirs(os.path.dirname(path), exist_ok=True)
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data['new-device'] = {
    'base_class': '<chosen_base_class>',
    'connection_type': '<chosen_connection_type_key>',
    'hook_category': '<chosen_hook_category>',
}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"
```

Substitute `<chosen_base_class>`, `<chosen_connection_type_key>`, and
`<chosen_hook_category>` with the developer's actual Q3/Q4/Q5 answers.
Free-text answers (class name, inventory keys) are never cached.

### Completion checklist

```
Scaffold complete for <ClassName>.

Created:
  ✓ boardfarm3/devices/<module_name>.py
  ✓ unittests/devices/test_<module_name>.py

Still to do:
  □ Implement all abstract methods from <TemplateName>
    (run: grep "@abstractmethod" boardfarm3/templates/<template_module>.py)
  □ Add real inventory key validation in __init__ (raise early if keys missing)
  □ Fill in _connect() with correct parameters from your inventory config
  □ Add boot and configure logic to the hook methods
  □ Add entry-point to pyproject.toml (snippet printed above)
  □ Run: nox -s lint
  □ Run: pytest unittests/devices/test_<module_name>.py
```
