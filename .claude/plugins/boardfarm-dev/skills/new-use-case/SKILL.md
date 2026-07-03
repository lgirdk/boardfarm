---
name: boardfarm-dev:new-use-case
description: Guide for creating new boardfarm use-case functions. Use when a developer needs to add a protocol- or feature-oriented function typed against template ABCs. Triggers on: "new use case", "add a use case", "write a use-case function", "protocol function", "feature function for boardfarm", "add to use_cases". Follow the 3-phase contract: Discover → Interview → Generate.
---

# boardfarm-dev: new-use-case

You scaffold new boardfarm use-case function(s) in `boardfarm3/use_cases/`.

Use-case functions take Template ABCs as parameters, never concrete device
classes. They contain business/protocol logic. Devices contain none.

---

## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory.

**Then run:**

```bash
# Existing use-case modules
ls boardfarm3/use_cases/

# Available templates (the types use-case params will be typed against)
for f in boardfarm3/templates/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    grep -H "^class " "$f"
done

# Existing use-case function names in the most relevant module
# (replace <protocol> with what the developer is targeting, e.g. dhcp)
grep -n "^def \|^async def " boardfarm3/use_cases/<protocol>.py 2>/dev/null | head -30
```

Build a list of existing use-case modules and the template ABCs available as
parameter types. **Ask no questions yet.**

---

## Phase 2 — Interview (one question at a time)

**Q1:** Which protocol or feature does this use case cover?

Show the existing use-case modules. Ask:
> "Which existing module should this go into (e.g. `dhcp`, `voice`, `wifi`),
> or is this a new module? If new, what should the module be named?"

**Q2:** Which template ABCs does this function take as parameters?

Show the discovered template list. The developer may pick one or more.
Remind them: use-case functions must type parameters against Template ABCs,
not concrete device classes.

**Q3:** What is the function name? (snake_case verb phrase, e.g.
`verify_dhcp_lease`, `start_iperf_server`, `get_connected_clients`)

**Q4:** What does the function return?

Ask for the return type (e.g. `str`, `list[IPv4Address]`, `None`,
a custom dataclass the developer defines).

**Q5:** Does this function need to be async?

```
[1] Sync (def)
[2] Async (async def)
```

**Q6:** Confirm before generating. Show a summary:

```
Module:     boardfarm3/use_cases/<module_name>.py  (<new|existing>)
Function:   <function_name>(<param>: <TemplateName>, ...) -> <return_type>
Async:      <yes|no>
```

---

## Phase 3 — Generate

### Artefact 1 — Python stub

If the module **already exists**, show the snippet to append at the end of
`boardfarm3/use_cases/<module_name>.py`. If it is **new**, create the full file.

**New module:**

```python
"""Boardfarm <Protocol/Feature> use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3.templates.<template_module> import <TemplateName>


def <function_name>(
    <device_param>: <TemplateName>,
) -> <return_type>:
    """<One-line summary of what this use case does>.

    :param <device_param>: <description of the device>
    :type <device_param>: <TemplateName>
    :return: <description of return value>
    :rtype: <return_type>
    """
    # TODO: implement the protocol/feature logic here
    raise NotImplementedError
```

**Existing module — append only:**

```python
def <function_name>(
    <device_param>: <TemplateName>,
) -> <return_type>:
    """<One-line summary>.

    :param <device_param>: <description>
    :type <device_param>: <TemplateName>
    :return: <description>
    :rtype: <return_type>
    """
    # TODO: implement
    raise NotImplementedError
```

If async: use `async def` and `await` accordingly.

### Artefact 2 — Inventory JSON note

Print:

```
Note: Use-case functions don't define inventory configuration.
Inventory is defined by the device classes whose templates the function accepts.
No inventory snippet needed here.
```

### Artefact 3 — Unit test stub

Write `unittests/use_cases/test_<module_name>.py` (or append to it if it exists):

```python
"""Unit tests for <function_name> use case."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boardfarm3.templates.<template_module> import <TemplateName>


@pytest.fixture(name="mock_<device_param>")
def mock_<device_param>_fixture() -> <TemplateName>:
    """Return a mock <TemplateName> for testing.

    :return: mock <TemplateName> instance
    :rtype: <TemplateName>
    """
    mock = MagicMock(spec=<TemplateName>)
    # Configure mock return values to match what the real device returns.
    # e.g. mock.<method>.return_value = <expected_value>
    return mock


def test_<function_name>_with_valid_input(
    mock_<device_param>: <TemplateName>,
) -> None:
    """Verify <function_name> returns expected result given a cooperative device.

    :param mock_<device_param>: mock device fixture
    :type mock_<device_param>: <TemplateName>
    :return: None
    :rtype: None
    """
    from boardfarm3.use_cases.<module_name> import <function_name>

    # TODO: set up mock_<device_param> return values, call the function,
    # assert the result matches expectations.
    pytest.skip("implement stub")
```

### Artefact 4 — pyproject.toml note

Print:

```
Note: Use-case modules don't need pyproject.toml entry-points.
They are plain Python modules imported directly by tests and the interactive shell.
No pyproject.toml change needed.
```

### Completion checklist

```
Scaffold complete for <function_name>.

Created / updated:
  ✓ boardfarm3/use_cases/<module_name>.py
  ✓ unittests/use_cases/test_<module_name>.py

Still to do:
  □ Implement the function body (replace NotImplementedError)
  □ Configure mock return values in the test fixture
  □ Replace pytest.skip("implement stub") with real assertions
  □ Run: nox -s lint
  □ Run: pytest unittests/use_cases/test_<module_name>.py
```
