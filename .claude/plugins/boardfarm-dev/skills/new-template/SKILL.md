---
name: boardfarm-dev:new-template
description: Guide for creating a new boardfarm Template (Abstract Base Class). Use when a developer needs to define a new device category API that does not yet exist in boardfarm3/templates/. Triggers on: "new template", "add a template", "write an ABC for", "create a boardfarm template", "define a device interface". Follow the 3-phase contract: Discover → Interview → Generate.
---

# boardfarm-dev: new-template

You scaffold a new boardfarm Template (ABC) in `boardfarm3/templates/`.

---

## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory
(`.claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md` relative to
repo root). Internalize all naming conventions and layer discipline rules before
proceeding.

**Then run these commands** to understand what already exists:

```bash
# List existing template files
ls boardfarm3/templates/

# For each .py file (excluding __init__.py), show class names and abstract methods
for f in boardfarm3/templates/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    echo "=== $f ==="
    grep -n "^class \|@abstractmethod\|^    def " "$f" | head -30
done
```

Build an internal list of existing template class names so you can:
- Warn if the developer tries to duplicate one
- Show a representative example when explaining structure

**Ask no questions yet.**

---

## Phase 2 — Interview (one question at a time)

**Q1:** What device category does this template cover?

Show the existing list (from discovery) and ask:
> "What device category is this new template for? (e.g., ACS, Provisioner, CPE,
> TFTP, SIPServer — pick something that doesn't already exist, or explain how
> yours differs)"

**Q2:** What is the Python class name for this template?

Suggest a name following the naming convention (PascalCase, noun, e.g. `MyServer`).
Confirm with the developer.

**Q3:** What abstract methods must this template define?

Say:
> "Let's define the abstract methods. Tell me the first method — I'll ask for
> name, parameter types, and return type. Say 'done' when you've listed all methods."

For each method the developer describes, confirm:
- Method name
- Parameters as `name: type` pairs (include `self`)
- Return type

Keep asking "Any more methods?" until the developer says done.

**Q4:** Confirm the full list before generating.

Show a summary table of all methods and ask:
> "Here's what I'll generate:
>
> Class: `<ClassName>` in `boardfarm3/templates/<module_name>.py`
>
> | Method | Parameters | Return type |
> |--------|-----------|-------------|
> | `<method>` | `self, <params>` | `<return_type>` |
>
> Does this look right? (yes / adjust)"

---

## Phase 3 — Generate

Produce all four artefacts without asking further questions.

### Artefact 1 — Python stub

Write `boardfarm3/templates/<module_name>.py`:

```python
"""Boardfarm <DeviceCategory> device template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # add TYPE_CHECKING-only imports here if return types need them


class <ClassName>(ABC):
    """Boardfarm <DeviceCategory> device template."""

    @abstractmethod
    def <method_name>(self, <typed_params>) -> <return_type>:
        """<One-line summary of what this method does>.

        :param <param_name>: <description>
        :type <param_name>: <type>
        :return: <description of return value>
        :rtype: <return_type>
        :raises NotImplementedError: must be implemented by subclass
        """
        raise NotImplementedError
```

Repeat the `@abstractmethod` block for each method the developer specified.

### Artefact 2 — Inventory JSON note

Templates are ABCs — they do not register a device `type` themselves. Print:

```
Note: Templates don't have an inventory snippet. The inventory "type" key is
registered by the concrete device class that implements this template.
When you run /boardfarm-dev:new-device and pick this template, it will
generate the inventory snippet and pyproject.toml entry for you.
```

### Artefact 3 — Unit test stub

Write `unittests/templates/test_<module_name>.py`:

```python
"""Unit tests for the <ClassName> template."""

from __future__ import annotations

import pytest

from boardfarm3.templates.<module_name> import <ClassName>


class _Concrete<ClassName>(<ClassName>):
    """Minimal concrete subclass used only for testing."""

    # Implement each abstract method with a stub that returns a sensible default.
    # Replace each stub body with actual logic when you implement the real device.
    def <method_name>(self, <typed_params>) -> <return_type>:  # type: ignore[override]
        """Stub implementation for testing.

        :return: <sensible default>
        :rtype: <return_type>
        """
        raise NotImplementedError("stub — implement in real device class")


def test_<class_name_lower>_cannot_instantiate_abstract() -> None:
    """Verify <ClassName> raises TypeError when instantiated directly.

    :return: None
    :rtype: None
    """
    with pytest.raises(TypeError):
        <ClassName>()  # type: ignore[abstract]


def test_concrete_subclass_is_valid_<class_name_lower>() -> None:
    """Verify a complete concrete subclass satisfies the <ClassName> protocol.

    :return: None
    :rtype: None
    """
    assert issubclass(_Concrete<ClassName>, <ClassName>)
```

### Artefact 4 — pyproject.toml note

Print:

```
Note: Templates themselves need no pyproject.toml entry-point.
Entry-points are registered by the concrete device class.
Run /boardfarm-dev:new-device when you are ready to create the implementation.
```

### Completion checklist

Print this after generating:

```
Scaffold complete for <ClassName>.

Created:
  ✓ boardfarm3/templates/<module_name>.py
  ✓ unittests/templates/test_<module_name>.py

Still to do:
  □ Add any TYPE_CHECKING-only imports in the template (for complex return types)
  □ Add a line to boardfarm3/templates/__init__.py if you want the class
    importable from the package root
  □ Run: nox -s lint
  □ Run: pytest unittests/templates/test_<module_name>.py
  □ When ready to implement: /boardfarm-dev:new-device
```
