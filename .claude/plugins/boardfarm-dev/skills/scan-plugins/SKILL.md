---
name: boardfarm-dev:scan-plugins
description: Discover installed boardfarm plugins and report which templates, devices, and use-cases they contribute beyond core boardfarm3. Use when a developer wants to see what's installed, or is automatically invoked by other boardfarm-dev sub-skills before their own discovery phase, to avoid duplicating components a plugin already provides. Triggers on: "what boardfarm plugins are installed", "scan plugins", "check my boardfarm environment", "what templates do I have", "list installed boardfarm devices".
---

# boardfarm-dev: scan-plugins

You discover installed boardfarm plugins (packages registered under the
`boardfarm` entry-point group) and report the templates, devices, and
use-cases they contribute, in addition to core `boardfarm3`. Other
boardfarm-dev sub-skills invoke you at the start of their own Phase 1 so
their menus reflect the live environment, not just core.

You perform **no** code generation. You only discover and report.

---

## Step 1 — Discover installed plugins

Run:

```bash
python -c "
from importlib.metadata import entry_points
eps = entry_points(group='boardfarm')
for ep in eps:
    print(f'{ep.name} -> {ep.value}')
"
```

This lists every package registered under `[project.entry-points."boardfarm"]`
across the current Python environment — core `boardfarm3` plus any installed
plugins (e.g. `boardfarm3-docsis`).

If the command errors (no plugins group registered, or `importlib.metadata`
unavailable), report core-only and continue — never block the calling skill.

## Step 2 — Locate each plugin's source and grep its contributions

For each entry-point value discovered in Step 1 (the part before ` -> ` is
the top-level dotted module, e.g. `boardfarm3.plugins.core` belongs to the
`boardfarm3` package), resolve its installed source directory:

```bash
python -c "
import importlib.util
spec = importlib.util.find_spec('<package_import_name>')
print(spec.submodule_search_locations[0] if spec else 'NOT FOUND')
"
```

`<package_import_name>` is the top-level package name (e.g. `boardfarm3`, or
an external plugin's own top-level package such as `boardfarm3_docsis`).
Use the resolved directory as the search root, then run the same greps
`boardfarm-context.md` runs against core:

```bash
# Templates
find <package_root>/templates -name "*.py" ! -name "__init__.py" \
  -exec grep -H "^class " {} \; 2>/dev/null

# Devices
find <package_root>/devices -name "*.py" ! -name "__init__.py" \
  -exec grep -H "^class " {} \; 2>/dev/null

# Use-cases
find <package_root>/use_cases -name "*.py" ! -name "__init__.py" \
  -exec grep -Hn "^def \|^async def " {} \; 2>/dev/null
```

Skip a category directory that doesn't exist in that package (e.g. a
connection-only plugin with no `templates/`) — this is not an error.

## Step 3 — Merge into unified lists

Combine every result from Step 2 across all discovered plugins with core
`boardfarm3`'s own discovery output (re-run the same greps against
`boardfarm3/templates/`, `boardfarm3/devices/`, `boardfarm3/use_cases/` if
invoked standalone, or reuse the calling skill's own Phase 1 output if
invoked internally). Build three flat lists:

- **Templates:** `{name, source_package, file_path}`
- **Devices:** `{name, source_package, file_path}`
- **Use-cases:** `{name, template_params, first_docstring_line, source_package, file_path}`
  — for use-cases, additionally read the first line of the docstring
  immediately following each `def`/`async def` match, and the parameter
  type annotations from the signature.

Tag every entry with `source_package` = `core` for boardfarm3 results, or the
distribution name (e.g. `boardfarm3-docsis`) for plugin results.

## Step 4 — Report

**When invoked standalone**, print:

```
Installed boardfarm plugins:
  <checkmark> <package_name> (<version>)  — <N> templates, <N> devices, <N> use-cases
  ...

Unified template list (<total>):  <name> (core), <name> (<package>), ...
Unified device list (<total>):    <name> (core), <name> (<package>), ...
Unified use-case list (<total>):  <name> (core), <name> (<package>), ...
```

If only core is installed, print:

```
No boardfarm plugins detected beyond core boardfarm3.

Unified template list (<total>): <name>, <name>, ...
Unified device list (<total>): <name>, <name>, ...
Unified use-case list (<total>): <name>, <name>, ...
```

**When invoked internally by another sub-skill**, skip the printed report and
hand back the three unified lists directly for that skill's own Phase 1/2 to
consume — the calling skill's own instructions decide what to show the
developer.

## Output contract

The three unified lists above are the fixed shape every other boardfarm-dev
sub-skill relies on:

- Templates: `{name, source_package, file_path}`
- Devices: `{name, source_package, file_path}`
- Use-cases: `{name, template_params, first_docstring_line, source_package, file_path}`

Any sub-skill invoking you may assume this shape without re-deriving it.
