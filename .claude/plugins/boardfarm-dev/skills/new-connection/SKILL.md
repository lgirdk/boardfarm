---
name: boardfarm-dev:new-connection
description: Guide for creating a new boardfarm connection driver (transport class). Use when a developer needs to add a new transport that doesn't exist in boardfarm3/lib/connections/ — e.g. a new protocol, auth mechanism, or wrapper. Triggers on: "new connection", "add a connection driver", "new transport", "write a connection class", "new SSH variant", "add a serial connection". Follow the 3-phase contract: Discover → Interview → Generate.
---

# boardfarm-dev: new-connection

You scaffold a new boardfarm connection driver in `boardfarm3/lib/connections/`.

All connection classes inherit from `BoardfarmPexpect` and are registered in
`boardfarm3/lib/connection_factory.py`.

---

## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory.

**Then run:**

```bash
# Existing connection classes
grep "^class " boardfarm3/lib/connections/*.py

# Existing connection type keys in the factory
grep -A 20 "connection_dispatcher" boardfarm3/lib/connection_factory.py

# BoardfarmPexpect API (the base class all connections inherit from)
grep -n "def \|class " boardfarm3/lib/boardfarm_pexpect.py | head -40
```

Build a list of existing connection type keys so you can avoid collisions.
**Ask no questions yet.**

---

## Phase 2 — Interview (one question at a time)

**Before Q1:** check whether
`.claude/plugins/boardfarm-dev/.cache/interview-defaults.json` exists and has
a `"new-connection"` entry:

```bash
python -c "
import json, os
path = '.claude/plugins/boardfarm-dev/.cache/interview-defaults.json'
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(json.dumps(data.get('new-connection', {}), indent=2))
else:
    print('{}')
"
```

If it returns a non-empty object, remember the `transport` value as a
suggested default for Q1 below — annotate the matching option with "(used
last time)". The developer still answers the question; this never skips it.

**Q1:** What transport protocol does this connection use?

```
[1] SSH (new variant or auth mechanism)
[2] Serial / ser2net
[3] Telnet
[4] HTTP/REST (non-pexpect — note: HTTP connections don't subclass BoardfarmPexpect)
[5] Other — describe it
```

If the cache lookup returned a `transport` value, annotate the matching
option, e.g. if the cached value is `ssh`:

```
[1] SSH (new variant or auth mechanism) (used last time)
[2] Serial / ser2net
[3] Telnet
[4] HTTP/REST (non-pexpect — note: HTTP connections don't subclass BoardfarmPexpect)
[5] Other — describe it
```

**Q2:** What is the Python class name? (PascalCase + `Connection` suffix, e.g.
`MyAuthSSHConnection`, `Ser2NetV2Connection`)

**Q3:** What is the connection type key string? (snake_case, registered in
`connection_factory.py`, e.g. `my_auth_ssh`, `ser2net_v2`)

Confirm it doesn't collide with existing keys discovered in Phase 1.

**Q4:** What authentication mechanism does it use?

```
[1] Username + password
[2] SSH key / certificate
[3] LDAP
[4] No auth (open)
[5] Other — describe
```

**Q5:** Does this connection need async support?

```
[1] Sync only
[2] Both sync and async methods
```

**Q6:** What constructor parameters does it need beyond the base class?

Base class `BoardfarmPexpect.__init__` takes: `name: str`, `command: str`,
`args: list[str]`, `shell_prompt: list[str]`, `save_console_logs: str`.
Ask what additional parameters this connection needs.

**Q7:** Confirm before generating. Show a summary:

```
Class:        <ClassName>(BoardfarmPexpect)
Module:       boardfarm3/lib/connections/<module_name>.py
Factory key:  "<connection_type_key>"
Auth:         <auth_type>
Async:        <yes|no>
Extra params: <param_list>
```

---

## Phase 3 — Generate

### Artefact 1 — Python stub

Write `boardfarm3/lib/connections/<module_name>.py`:

```python
"""Boardfarm <ClassName> connection module."""

from __future__ import annotations

from typing import Any

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class <ClassName>(BoardfarmPexpect):
    """<One-line description of what this connection does>."""

    def __init__(
        self,
        name: str,
        <extra_param>: <type>,
        shell_prompt: list[str],
        port: int = <default_port>,
        save_console_logs: str = "",
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize <ClassName>.

        :param name: connection name (used for logging)
        :type name: str
        :param <extra_param>: <description>
        :type <extra_param>: <type>
        :param shell_prompt: list of shell prompt patterns
        :type shell_prompt: list[str]
        :param port: port number
        :type port: int
        :param save_console_logs: path to save console logs, empty to disable
        :type save_console_logs: str
        :param kwargs: additional keyword arguments (ignored)
        """
        self._shell_prompt = shell_prompt
        # TODO: store extra params, build the pexpect command args, then call:
        # super().__init__(
        #     name,
        #     command="<transport_binary>",
        #     args=[<arg_list>],
        #     shell_prompt=shell_prompt,
        #     save_console_logs=save_console_logs,
        # )
```

If async support was requested, add async variants matching `BoardfarmPexpect`'s
async method signatures.

### Artefact 2 — `connection_factory.py` registration snippet

Print:

```python
# In boardfarm3/lib/connection_factory.py, add to connection_dispatcher:
"<connection_type_key>": <ClassName>,

# And add the import at the top of the file:
from boardfarm3.lib.connections.<module_name> import <ClassName>
```

Note: connection drivers are not registered via pyproject.toml entry-points —
they're registered in `connection_factory.py` directly.

### Artefact 3 — Inventory JSON snippet

```json
{
    "name": "<device-name>",
    "type": "<device_entry_point_key>",
    "connection_type": "<connection_type_key>",
    "ipaddr": "192.168.1.1",
    "port": <default_port>,
    "username": "root",
    "password": "changeme"
}
```

### Artefact 4 — Unit test stub

Write `unittests/lib/test_<module_name>.py` (flat under `unittests/lib/`, matching existing convention — see `unittests/lib/test_connection_factory.py`):

```python
"""Unit tests for <ClassName>."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


def test_<module_name>_is_boardfarmpexpect_subclass() -> None:
    """Verify <ClassName> is a BoardfarmPexpect subclass.

    :return: None
    :rtype: None
    """
    from boardfarm3.lib.connections.<module_name> import <ClassName>

    assert issubclass(<ClassName>, BoardfarmPexpect)


def test_<module_name>_registered_in_factory() -> None:
    """Verify '<connection_type_key>' is registered in connection_factory.

    :return: None
    :rtype: None
    """
    from boardfarm3.lib.connection_factory import connection_factory
    from boardfarm3.lib.connections.<module_name> import <ClassName>

    with patch.object(<ClassName>, "__init__", return_value=None):
        conn = connection_factory(
            "<connection_type_key>",
            "test-conn",
            ip_addr="127.0.0.1",
            username="root",
            password=None,
            shell_prompt=["\\$"],
            port=<default_port>,
            save_console_logs="",
        )
    assert isinstance(conn, <ClassName>)
```

### Save interview defaults

After the developer confirms "yes" at Q7 and all artefacts above are
written, persist the transport choice for next time:

```bash
python -c "
import json, os
path = '.claude/plugins/boardfarm-dev/.cache/interview-defaults.json'
os.makedirs(os.path.dirname(path), exist_ok=True)
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data['new-connection'] = {
    'transport': '<chosen_transport>',
}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"
```

Substitute `<chosen_transport>` with the developer's Q1 answer (e.g. `ssh`,
`serial`, `telnet`). Free-text answers (class name, factory key, extra
params) are never cached.

### Completion checklist

```
Scaffold complete for <ClassName>.

Created:
  ✓ boardfarm3/lib/connections/<module_name>.py
  ✓ unittests/lib/test_<module_name>.py

Still to do:
  □ Complete __init__: store params, build pexpect command args, call super().__init__()
  □ Add import + factory key to boardfarm3/lib/connection_factory.py (snippet above)
  □ Run: nox -s lint
  □ Run: pytest unittests/lib/test_<module_name>.py
```
