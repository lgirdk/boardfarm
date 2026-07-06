# boardfarm-dev Plugin Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `boardfarm-dev` Claude Code plugin with plugin-aware environment discovery, duplicate-detection for templates and use-cases, cached interview defaults for device/connection scaffolding, and a three-tier device verification skill.

**Architecture:** All changes are prose (`SKILL.md`) instructions plus one JSON cache file convention — no new Python runtime code. Two new sub-skills (`scan-plugins`, `verify-device`) are added; four existing sub-skills (`new-template`, `new-use-case`, `new-device`, `new-connection`) gain new sections; `registry.md`, the root orchestrator, and `README.md` are updated to reference the two new sub-skills.

**Tech Stack:** Claude Code plugin skills (Markdown + YAML frontmatter), Python one-liners (`importlib.metadata`, `importlib.util`, `json`) invoked via Bash from within skill instructions, `nox`/`pytest`/`boardfarm` CLI (already used elsewhere in the repo).

## Global Constraints

- No new Python runtime code, dependencies, or servers — every new capability is a prose instruction or a `python -c` / `bash` one-liner embedded in a `SKILL.md`, matching how this plugin already works (per `docs/superpowers/specs/2026-07-06-boardfarm-dev-plugin-enhancements-design.md`, Non-goals).
- No automatic conflict resolution. Duplicate-detection features inform and offer choices; they never block silently or auto-rename/auto-reuse on the developer's behalf.
- No RAG / vector search — duplicate detection reads the full candidate list into context for judgment (see design doc, Non-goals and Component 3's "Future extension point").
- The existing scaffolding sub-skills' three-phase contract (Discover → Interview → Generate) must remain intact; new sections are additive insertions, not restructurings.
- The gitignore requirement is already satisfied: `.gitignore:44` contains a bare `.cache` pattern, which (per `git check-ignore`, verified against `.claude/plugins/boardfarm-dev/.cache/interview-defaults.json`) already matches `.claude/plugins/boardfarm-dev/.cache/` at any depth. **No `.gitignore` edit is needed** — Task 10 only adds a verification step confirming this, and the design doc's mention of adding a `.gitignore` line is superseded by this finding.
- Commit messages follow this repo's Conventional Commits convention (`<type>(<scope>): <subject>`, see `git log` precedent such as `feat(.claude/plugins): add all four boardfarm-dev sub-skills`) and must end with:
  ```
  Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
  ```

---

### Task 1: Create the `scan-plugins` sub-skill

**Files:**
- Create: `.claude/plugins/boardfarm-dev/skills/scan-plugins/SKILL.md`

**Interfaces:**
- Produces: a sub-skill invocable as `/boardfarm-dev:scan-plugins`, whose documented **output contract** is three flat lists — Templates `{name, source_package, file_path}`, Devices `{name, source_package, file_path}`, Use-cases `{name, template_params, first_docstring_line, source_package, file_path}` — that Tasks 2, 3, and 4 reference by this exact shape.

- [ ] **Step 1: Write the new skill file**

Create `.claude/plugins/boardfarm-dev/skills/scan-plugins/SKILL.md` with this exact content:

````markdown
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
````

- [ ] **Step 2: Dry-run the discovery mechanism against this repo**

Run:

```bash
python -c "
from importlib.metadata import entry_points
eps = entry_points(group='boardfarm')
for ep in eps:
    print(f'{ep.name} -> {ep.value}')
"
```

Expected output (this environment has no external plugins installed beyond
core):

```
booting -> boardfarm3.plugins.setup_environment
core -> boardfarm3.plugins.core
no_reservation -> boardfarm3.plugins.no_reservation
```

Then run:

```bash
python -c "
import importlib.util
spec = importlib.util.find_spec('boardfarm3')
print(spec.submodule_search_locations[0] if spec else 'NOT FOUND')
"
```

Expected output: a path ending in `.../boardfarm3` (the repo's own
`boardfarm3` package directory). This confirms Step 2's source-resolution
mechanism works.

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/scan-plugins/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): add scan-plugins sub-skill to boardfarm-dev

Discovers installed boardfarm entry-point plugins and builds unified
template/device/use-case lists so other sub-skills' menus and
duplicate-detection checks reflect the live environment, not just core.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 2: Wire `scan-plugins` into the shared discovery context

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md:27-29`

**Interfaces:**
- Consumes: Task 1's `scan-plugins` output contract (three unified lists).
- Produces: an instruction, referenced by name ("the Plugin-aware discovery note") from Tasks 3 and 4, telling every sub-skill's Phase 1 to invoke `scan-plugins` before running its own core-only greps.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "scan-plugins" .claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md
```

Expected output: `0` (the reference doesn't exist yet).

- [ ] **Step 2: Insert the plugin-aware discovery note**

Using the Edit tool on `.claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md`, replace:

```
## 2. Discovery Commands

Run these commands to build menus from the live repo state before interviewing.

### Available templates
```

with:

```
## 2. Discovery Commands

Run these commands to build menus from the live repo state before interviewing.

**Plugin-aware discovery:** boardfarm is a plugin host — installed packages
beyond core `boardfarm3` (e.g. `boardfarm3-docsis`) can contribute their own
templates, devices, and use-cases via the `boardfarm` entry-point group.
Before running the core-only greps below, invoke
`/boardfarm-dev:scan-plugins` (or read
`.claude/plugins/boardfarm-dev/skills/scan-plugins/SKILL.md` and follow it
inline) to discover installed plugins. Merge its three unified lists
(templates, devices, use-cases — each tagged with `source_package`) with the
core-only results below before building any menu. This ensures menus and
duplicate-detection checks reflect the live environment, not just core.

### Available templates
```

- [ ] **Step 3: Verify the insertion**

```bash
grep -c "scan-plugins" .claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md
```

Expected output: `2` (one in prose, one in the backtick-quoted invocation).

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): wire scan-plugins into shared discovery context

Every boardfarm-dev sub-skill's Phase 1 now invokes scan-plugins before
its own core-only greps, so menus and duplicate checks account for
installed plugins, not just boardfarm3 core.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 3: Add structural duplicate detection to `new-template`

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/new-template/SKILL.md:12-53`

**Interfaces:**
- Consumes: Task 1's unified template list `{name, source_package, file_path}`.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "Duplicate check" .claude/plugins/boardfarm-dev/skills/new-template/SKILL.md
```

Expected output: `0`.

- [ ] **Step 2: Update Phase 1 to build the unified template list**

Using the Edit tool, replace:

```
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
```

with:

```
## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory
(`.claude/plugins/boardfarm-dev/skills/shared/boardfarm-context.md` relative to
repo root). Internalize all naming conventions and layer discipline rules before
proceeding. This step invokes `/boardfarm-dev:scan-plugins` per the
"Plugin-aware discovery" note — do not skip it.

**Then run these commands** to understand what already exists in core:

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

Merge these core results with `scan-plugins`' template list to build one
**unified template list**, each entry tagged `source_package` (`core` or the
plugin's distribution name). Use this unified list — not just core — so you
can:
- Warn if the developer tries to duplicate a template that exists in core
  **or in any installed plugin**
- Show a representative example when explaining structure

**Ask no questions yet.**
```

- [ ] **Step 3: Add the duplicate check to Q2**

Using the Edit tool, replace:

```
**Q2:** What is the Python class name for this template?

Suggest a name following the naming convention (PascalCase, noun, e.g. `MyServer`).
Confirm with the developer.
```

with:

```
**Q2:** What is the Python class name for this template?

Suggest a name following the naming convention (PascalCase, noun, e.g. `MyServer`).

**Duplicate check (structural):** before confirming, check the developer's
proposed name against the unified template list from Phase 1:

1. **Exact match** — the name already exists verbatim in the unified list
   (in core or a plugin). This is a hard flag.
2. **Normalized match** — strip common suffixes (`Device`, `Template`,
   `Base`) from both the proposed name and every unified-list name,
   lowercase both, and compare. A match here (e.g. proposed `CpeDevice`
   normalizes to `cpe`, matching existing `CPE`) is a soft flag.

If either check fires, show the existing template and its source:

> "`<ExistingName>` already exists in `<source_package>` at `<file_path>`.
> Do you want to:
> [1] Open/edit that file instead of creating a new template
> [2] Extend it via a mixin
> [3] Proceed anyway — `<ProposedName>` is genuinely distinct from `<ExistingName>`"

If the developer picks [3], continue the interview with the proposed name.
If [1] or [2], stop this skill and tell the developer to edit
`<file_path>` directly (or come back once they've decided how to extend it).

If neither check fires, confirm the name with the developer and continue
silently — no extra noise.
```

- [ ] **Step 4: Verify the insertion**

```bash
grep -c "Duplicate check" .claude/plugins/boardfarm-dev/skills/new-template/SKILL.md
```

Expected output: `1`.

- [ ] **Step 5: Dry-run the normalization logic against this repo's actual templates**

```bash
python3 -c "
import re, subprocess

names = subprocess.run(
    ['grep', '-rhoP', '(?<=^class )[A-Za-z0-9_]+', 'boardfarm3/templates/'],
    capture_output=True, text=True, check=True,
).stdout.split()

def normalize(n):
    for suffix in ('Device', 'Template', 'Base'):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n.lower()

proposed = 'CpeDevice'
for n in names:
    if normalize(n) == normalize(proposed):
        print(f'soft flag: {proposed} normalizes to {normalize(proposed)}, matches existing {n}')
"
```

Expected output: `soft flag: CpeDevice normalizes to cpe, matches existing CPE`
(confirms the normalized-match logic described in Step 3 actually catches
this case against the repo's real `CPE` template).

- [ ] **Step 6: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/new-template/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): add structural duplicate check to new-template

Checks a proposed template class name against the unified (core +
plugin) template list for exact and normalized-suffix matches before
scaffolding, offering to edit/extend/proceed instead of silently
duplicating an existing template.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 4: Add semantic duplicate detection to `new-use-case`

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/new-use-case/SKILL.md:15-76`

**Interfaces:**
- Consumes: Task 1's unified use-case list `{name, template_params, first_docstring_line, source_package, file_path}`.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "Step B" .claude/plugins/boardfarm-dev/skills/new-use-case/SKILL.md
```

Expected output: `0`.

- [ ] **Step 2: Update Phase 1 to build the unified use-case candidate list**

Using the Edit tool, replace:

```
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
```

with:

```
## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin directory.
This invokes `/boardfarm-dev:scan-plugins` per the "Plugin-aware discovery"
note — do not skip it.

**Then run:**

```bash
# Existing use-case modules
ls boardfarm3/use_cases/

# Available templates (the types use-case params will be typed against)
for f in boardfarm3/templates/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    grep -H "^class " "$f"
done

# Step A — Gather candidates: every existing use-case function across ALL
# modules (not just one protocol), for the duplicate-detection check in
# Phase 2.
for f in boardfarm3/use_cases/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    echo "=== $f ==="
    grep -n "^def \|^async def " "$f"
done
```

For each function found by the Step A grep above, read its signature (for
parameter Template types) and the first line of its docstring (the line
immediately after the opening `"""`). Merge this core-only candidate list
with `scan-plugins`' use-case list to build one **unified candidate list**:
`{name, template_params, first_docstring_line, source_package, file_path}`.

This unified list is the fixed output of **Step A — Gather candidates**. It
has no judgment applied yet — it is a plain enumeration, used by the
duplicate check in Phase 2.

Build a list of existing use-case modules and the template ABCs available as
parameter types. **Ask no questions yet.**
```

- [ ] **Step 3: Rework Phase 2 to add the structural filter and semantic judge step**

Using the Edit tool, replace the entire Phase 2 section:

```
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
```

with:

```
## Phase 2 — Interview (one question at a time)

**Q1:** Which protocol or feature does this use case cover?

Show the existing use-case modules. Ask:
> "Which existing module should this go into (e.g. `dhcp`, `voice`, `wifi`),
> or is this a new module? If new, what should the module be named?"

**Q2:** Which template ABCs does this function take as parameters?

Show the discovered template list. The developer may pick one or more.
Remind them: use-case functions must type parameters against Template ABCs,
not concrete device classes.

**Structural filter:** narrow Step A's unified candidate list (from Phase 1)
to only those candidates whose `template_params` match the same set of
Template types just chosen. Keep this narrowed list for Q3 — do not show it
to the developer yet.

**Q3:** In one sentence, what does your function do?

This is **Step B — Judge candidates**. Compare the developer's stated intent
against the narrowed candidate list from the structural filter above, using
your own judgment of semantic overlap (not just keyword matching) — e.g. a
developer describing "configure DHCP on the provisioner" should be checked
against an existing `configure_dhcp(provisioner: Provisioner)` even if they
plan to name their function `set_provisioner_dhcp`.

**On overlap found:** show the existing use-case and its source, then offer:

> "This looks similar to `<existing_name>` in `<source_package>` at
> `<file_path>`, which does: '<first_docstring_line>'. Do you want to:
> [1] Reuse the existing function
> [2] Extend the existing function
> [3] Proceed anyway — explain briefly why yours is distinct"

If the developer picks [1] or [2], stop this skill and point them to
`<file_path>`. If [3], record their justification and continue the
interview with Q4.

**On no overlap:** proceed silently to Q4 — no extra noise.

**Q4:** What is the function name? (snake_case verb phrase, e.g.
`verify_dhcp_lease`, `start_iperf_server`, `get_connected_clients`)

**Q5:** What does the function return?

Ask for the return type (e.g. `str`, `list[IPv4Address]`, `None`,
a custom dataclass the developer defines).

**Q6:** Does this function need to be async?

```
[1] Sync (def)
[2] Async (async def)
```

**Q7:** Confirm before generating. Show a summary:

```
Module:     boardfarm3/use_cases/<module_name>.py  (<new|existing>)
Function:   <function_name>(<param>: <TemplateName>, ...) -> <return_type>
Async:      <yes|no>
```
```

- [ ] **Step 4: Verify the insertion**

```bash
grep -c "Step B" .claude/plugins/boardfarm-dev/skills/new-use-case/SKILL.md
grep -c "^\*\*Q7" .claude/plugins/boardfarm-dev/skills/new-use-case/SKILL.md
```

Expected output: `1` for `Step B`, `1` for `**Q7` (confirming the
renumbering through Q7 landed correctly and there's no leftover `**Q6:**
Confirm` duplicate).

- [ ] **Step 5: Dry-run Step A's gather mechanism against this repo**

```bash
for f in boardfarm3/use_cases/*.py; do
    [ "$(basename $f)" = "__init__.py" ] && continue
    echo "=== $f ==="
    grep -n "^def \|^async def " "$f"
done | head -20
```

Expected: real output listing use-case module headers and function
signatures (e.g. `=== boardfarm3/use_cases/dhcp.py ===` followed by `def`
lines) — confirms the grep pattern used in Step A actually enumerates
functions in this repo's `use_cases/` directory without error.

- [ ] **Step 6: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/new-use-case/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): add semantic duplicate check to new-use-case

Splits duplicate detection into a gather step (Step A: enumerate every
existing use-case across core + plugins) and a judge step (Step B:
compare stated intent against the structurally-filtered candidates),
so intent-based overlaps surface even under a different function name.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 5: Add cached interview defaults to `new-device`

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/new-device/SKILL.md:48-76,294-302`

**Interfaces:**
- Produces: `.claude/plugins/boardfarm-dev/.cache/interview-defaults.json`, keyed `"new-device": {"base_class": str, "connection_type": str, "hook_category": str}`. Task 6 writes the same file under the `"new-connection"` key.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "interview-defaults.json" .claude/plugins/boardfarm-dev/skills/new-device/SKILL.md
```

Expected output: `0`.

- [ ] **Step 2: Add the cache-read step before Q1**

Using the Edit tool, replace:

```
## Phase 2 — Interview (one question at a time)

**Q1:** What is the Python class name? (PascalCase, vendor or transport prefix +
category, e.g. `AxirosACS`, `KeaProvisioner`, `LinuxWAN`)
```

with:

```
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
```

- [ ] **Step 3: Annotate Q3 (base class) with the cached-default pattern**

Using the Edit tool, replace:

```
**Q3:** Which base class?

```
[1] LinuxDevice  — device has a Linux shell (SSH / serial / telnet access)
[2] BoardfarmDevice — device has no shell (REST API, HTTP only, etc.)
```
```

with:

```
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
```

- [ ] **Step 4: Annotate Q4 (connection type) with the cached-default pattern**

Using the Edit tool, replace:

```
**Q4:** Which connection type does it use?

Show the discovered connection type key list. Also accept "none" if the device
uses only HTTP (e.g. a REST-only ACS).
```

with:

```
**Q4:** Which connection type does it use?

Show the discovered connection type key list. Also accept "none" if the device
uses only HTTP (e.g. a REST-only ACS). If the cache lookup returned a
`connection_type` value, annotate the matching key in the list with "(used
last time)".
```

- [ ] **Step 5: Annotate Q5 (hook category) with the cached-default pattern**

Using the Edit tool, replace:

```
**Q5:** Which hook category?

```
[1] server         — boots before other devices (e.g., WAN, ACS, DHCP, TFTP)
[2] device         — the DUT under test (e.g., CPE)
[3] attached device — client devices (e.g., LAN, WLAN clients, phones)
```
```

with:

```
**Q5:** Which hook category?

```
[1] server         — boots before other devices (e.g., WAN, ACS, DHCP, TFTP)
[2] device         — the DUT under test (e.g., CPE)
[3] attached device — client devices (e.g., LAN, WLAN clients, phones)
```

If the cache lookup returned a `hook_category` value, annotate the matching
option with "(used last time)".
```

- [ ] **Step 6: Add the cache-write step after Artefact 4**

Using the Edit tool, replace:

```
### Artefact 4 — pyproject.toml snippet

```toml
# Add this line under the existing [project.entry-points."boardfarm"] section
# in pyproject.toml at the repo root:
<entry_point_key> = "boardfarm3.devices.<module_name>"
```

### Completion checklist
```

with:

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

- [ ] **Step 7: Verify the insertion**

```bash
grep -c "interview-defaults.json" .claude/plugins/boardfarm-dev/skills/new-device/SKILL.md
```

Expected output: `2` (one read, one write).

- [ ] **Step 8: Dry-run the read/write cache mechanism**

```bash
python3 -c "
import json, os
path = '/tmp/claude-1000/-home-zoro-workspace-boardfarm-repos-boardfarm/a5d93f4f-04d5-45cc-a000-4b1c25d61e85/scratchpad/test-interview-defaults.json'
os.makedirs(os.path.dirname(path), exist_ok=True)
data = {}
data['new-device'] = {
    'base_class': 'LinuxDevice',
    'connection_type': 'ssh_connection',
    'hook_category': 'attached_device',
}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
with open(path) as f:
    loaded = json.load(f)
print(loaded['new-device']['base_class'])
os.remove(path)
"
```

Expected output: `LinuxDevice` (confirms the write-then-read roundtrip
described in Steps 2 and 6 works).

- [ ] **Step 9: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/new-device/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): cache interview defaults in new-device

Reads base_class/connection_type/hook_category from a local JSON cache
at the start of Phase 2 and annotates the matching option as "used
last time" without skipping the question; writes the developer's
actual answers back after generation succeeds.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 6: Add cached interview defaults to `new-connection`

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/new-connection/SKILL.md:37-47,228-236`

**Interfaces:**
- Produces: writes `.claude/plugins/boardfarm-dev/.cache/interview-defaults.json` under the `"new-connection": {"transport": str}` key (same file Task 5 writes under `"new-device"`).

- [ ] **Step 1: Verify starting state**

```bash
grep -c "interview-defaults.json" .claude/plugins/boardfarm-dev/skills/new-connection/SKILL.md
```

Expected output: `0`.

- [ ] **Step 2: Add the cache-read step and annotate Q1**

Using the Edit tool, replace:

```
## Phase 2 — Interview (one question at a time)

**Q1:** What transport protocol does this connection use?

```
[1] SSH (new variant or auth mechanism)
[2] Serial / ser2net
[3] Telnet
[4] HTTP/REST (non-pexpect — note: HTTP connections don't subclass BoardfarmPexpect)
[5] Other — describe it
```
```

with:

```
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
```

- [ ] **Step 3: Add the cache-write step after Artefact 4**

Using the Edit tool, replace:

```
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
```

with:

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
```

- [ ] **Step 4: Verify the insertion**

```bash
grep -c "interview-defaults.json" .claude/plugins/boardfarm-dev/skills/new-connection/SKILL.md
```

Expected output: `2`.

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/new-connection/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): cache interview defaults in new-connection

Reads the transport choice from the shared local JSON cache at the
start of Phase 2 and annotates the matching option as "used last
time"; writes the developer's actual answer back after generation
succeeds.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 7: Create the `verify-device` sub-skill

**Files:**
- Create: `.claude/plugins/boardfarm-dev/skills/verify-device/SKILL.md`

**Interfaces:**
- Consumes: nothing from earlier tasks structurally (invokes `scan-plugins` transitively via `boardfarm-context.md`, per Task 2).
- Produces: a sub-skill invocable as `/boardfarm-dev:verify-device`.

- [ ] **Step 1: Write the new skill file**

Create `.claude/plugins/boardfarm-dev/skills/verify-device/SKILL.md` with this exact content:

````markdown
---
name: boardfarm-dev:verify-device
description: Verify a boardfarm device class actually works, at one of three levels of rigor — lint plus unit tests, a live connectivity smoke check, or a full boardfarm boot. Use when a developer wants to check their work before committing, is mid-way through writing a device's _connect() method and wants fast signal, or needs to debug why a device's boot hook is failing. Triggers on: "verify my device", "test this device class", "check connectivity", "run boardfarm against my device", "does my device connect", "debug boot hook failure".
---

# boardfarm-dev: verify-device

You verify a boardfarm device class at one of three levels of rigor. You do
**not** generate any new device code — this is a check, not a scaffold.

---

## Phase 1 — Discover

**First:** read `skills/shared/boardfarm-context.md` from the plugin
directory. This invokes `/boardfarm-dev:scan-plugins`.

**Then run:**

```bash
# Existing device modules and their test files, to help resolve paths
# if the developer doesn't give an exact path
ls boardfarm3/devices/*.py
ls unittests/devices/test_*.py 2>/dev/null

# Discovered connection type keys, needed for Tier 2
grep -o '"[a-z_]*":' boardfarm3/lib/connection_factory.py
```

**Ask no questions yet.**

---

## Phase 2 — Interview

**Q1:** What level of verification do you need?

```
[1] Lint + unit tests        — safe, no hardware needed, run before committing
[2] Connectivity smoke check — quick pexpect probe against a live host, while writing _connect()
[3] Full boardfarm boot      — runs the actual boardfarm CLI against target hardware
```

Branch to the matching tier below based on the answer.

---

## Tier 1 — Lint + unit tests

**Q2 (Tier 1):** What is the device module name (e.g. `axiros_acs`,
`linux_lan`)? If you just ran `/boardfarm-dev:new-device`, this defaults to
the module you just created — confirm or override.

**Execute:**

```bash
nox -s lint
pytest unittests/devices/test_<module_name>.py -v
```

Report pass/fail for each command separately. On failure, show the actual
error output verbatim — do not summarize it away, and do not attempt to
auto-fix the underlying code.

**On success**, print:

```
Tier 1 verification passed for <module_name>.
  ✓ nox -s lint
  ✓ pytest unittests/devices/test_<module_name>.py

Safe to commit.
```

---

## Tier 2 — Connectivity smoke check

**Q2 (Tier 2):** Host/IP address to connect to?

**Q3 (Tier 2):** Port? (default 22 for SSH, ask if unsure for other transports)

**Q4 (Tier 2):** Connection type? Show the discovered connection type key
list from Phase 1.

**Q5 (Tier 2):** Username and password (or "none" if the connection type
needs no auth)?

**Execute:** write a throwaway probe script to
`/tmp/boardfarm_verify_device_probe.py` (never saved to the repo working
tree) using the answers above:

```python
from boardfarm3.lib.connection_factory import connection_factory

conn = connection_factory(
    "<connection_type_key>",
    "verify-device-probe",
    ip_addr="<host>",
    username="<username>",
    password="<password>",
    shell_prompt=["\\$"],
    port=<port>,
    save_console_logs="",
)
conn.sendline("echo boardfarm_verify_device_probe_ok")
conn.expect("boardfarm_verify_device_probe_ok")
print("CONNECTIVITY_OK")
conn.close()
```

Run it:

```bash
python /tmp/boardfarm_verify_device_probe.py
```

Then delete the probe script:

```bash
rm -f /tmp/boardfarm_verify_device_probe.py
```

Report one of: **connected / prompt matched** (probe printed
`CONNECTIVITY_OK`), **timed out** (pexpect `TIMEOUT` raised), or **auth
failed** (connection raised an authentication error) — with the underlying
exception message in all failure cases. This is scratch verification only;
nothing about it is written to the repo.

---

## Tier 3 — Full boardfarm boot

**Q2 (Tier 3):** Path to `--inventory-config` JSON? Never assume the example
config — always ask.

**Q3 (Tier 3):** Path to `--env-config` JSON? Same rule — always ask.

**Q4 (Tier 3):** Board name (must match an entry in the given inventory
config)? Verify it by running:

```bash
python -c "
import json
with open('<inventory_config_path>') as f:
    inv = json.load(f)
print('<board_name>' in inv)
"
```

If this prints `False`, stop and tell the developer the board name doesn't
match any entry in the given inventory file — ask them to re-check.

**Confirm before executing:**

> "This will run:
> `boardfarm --board-name <board_name> --inventory-config <inventory_config_path> --env-config <env_config_path> --skip-boot`
>
> Run a full boot instead (no `--skip-boot`)? This actually drives
> hardware/lab state — confirm (yes/no)."

**If the developer says no (or doesn't answer explicitly "yes"):** run with
`--skip-boot`:

```bash
boardfarm --board-name <board_name> \
  --inventory-config <inventory_config_path> \
  --env-config <env_config_path> \
  --skip-boot
```

**If the developer explicitly confirms "yes":** run without `--skip-boot`:

```bash
boardfarm --board-name <board_name> \
  --inventory-config <inventory_config_path> \
  --env-config <env_config_path>
```

**Execute and report:** surface boardfarm's raw log output directly, without
summarizing — this tier exists specifically to debug which hook is failing,
so the unabridged logs are the point. Do not truncate stack traces.

---

## Completion

There is no generated artefact for any tier — print only the tier's result
(pass/fail details as specified above). Do not print the four-artefact
completion checklist used by scaffolding sub-skills; this skill only
verifies.
````

- [ ] **Step 2: Dry-run Tier 1's command pattern against this repo**

```bash
pytest unittests/lib/test_device_manager.py -v 2>&1 | tail -5
```

Expected output: `10 passed` (or similar all-passing summary) — confirms
the `pytest unittests/<path>/test_<name>.py -v` invocation pattern used by
Tier 1 works in this repo, using an existing test file as a stand-in (no
device test files exist yet in this repo — `unittests/devices/` will only
be created once `/boardfarm-dev:new-device` is run for the first time).

```bash
nox -l 2>&1 | grep lint
```

Expected output: a line showing `lint-3.11 -> Lint boardfarm.` — confirms
the `lint` session referenced by Tier 1 exists in `noxfile.py`.

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/verify-device/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): add verify-device sub-skill to boardfarm-dev

Adds three-tier device verification: lint+unit-tests (pre-commit
gate), a throwaway pexpect connectivity smoke check (mid-development
signal), and a full boardfarm CLI boot defaulting to --skip-boot
unless the developer explicitly confirms driving real hardware.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 8: Register the two new sub-skills in `registry.md`

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/registry.md:20-25`

**Interfaces:**
- Consumes: Task 1's and Task 7's sub-skill names/paths.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "^|" .claude/plugins/boardfarm-dev/skills/registry.md
```

Expected output: `6` (1 header + 1 separator + 4 existing rows).

- [ ] **Step 2: Append the two new rows**

Using the Edit tool, replace:

```
| new-use-case   | /boardfarm-dev:new-use-case     | skills/new-use-case/SKILL.md       | Use-case function(s) typed against a template |
```

with:

```
| new-use-case   | /boardfarm-dev:new-use-case     | skills/new-use-case/SKILL.md       | Use-case function(s) typed against a template |
| scan-plugins   | /boardfarm-dev:scan-plugins     | skills/scan-plugins/SKILL.md       | Discover installed boardfarm plugins; build unified template/device/use-case lists |
| verify-device  | /boardfarm-dev:verify-device    | skills/verify-device/SKILL.md      | Three-tier verification: lint+test, connectivity smoke check, full boardfarm boot |
```

- [ ] **Step 3: Verify the insertion**

```bash
grep -c "^|" .claude/plugins/boardfarm-dev/skills/registry.md
```

Expected output: `8`.

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/registry.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): register scan-plugins and verify-device

Adds both new sub-skills to the registry table the root orchestrator
reads to build its menu.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 9: Update the root orchestrator's menu

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/skills/boardfarm-dev/SKILL.md:17-28`

**Interfaces:**
- Consumes: Task 8's final registry rows.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "scan-plugins\|verify-device" .claude/plugins/boardfarm-dev/skills/boardfarm-dev/SKILL.md
```

Expected output: `0`.

- [ ] **Step 2: Update the menu**

Using the Edit tool, replace:

```
## Step 2 — Present the menu

Present the menu using the "Covers" column text verbatim, numbered from 1:

> "What kind of boardfarm component do you want to build?
>
> [1] Abstract base class (template) definition  →  /boardfarm-dev:new-template
> [2] Concrete device class + hookimpl wiring     →  /boardfarm-dev:new-device
> [3] Transport / connection driver               →  /boardfarm-dev:new-connection
> [4] Use-case function(s) typed against a template → /boardfarm-dev:new-use-case
>
> Pick a number, or name the sub-skill directly (e.g. `new-device`)."
```

with:

```
## Step 2 — Present the menu

Present the menu using the "Covers" column text verbatim, numbered from 1:

> "What do you want to do?
>
> [1] Abstract base class (template) definition  →  /boardfarm-dev:new-template
> [2] Concrete device class + hookimpl wiring     →  /boardfarm-dev:new-device
> [3] Transport / connection driver               →  /boardfarm-dev:new-connection
> [4] Use-case function(s) typed against a template → /boardfarm-dev:new-use-case
> [5] Discover installed boardfarm plugins; build unified template/device/use-case lists → /boardfarm-dev:scan-plugins
> [6] Three-tier verification: lint+test, connectivity smoke check, full boardfarm boot → /boardfarm-dev:verify-device
>
> Pick a number, or name the sub-skill directly (e.g. `new-device`)."
```

- [ ] **Step 3: Verify the insertion**

```bash
grep -c "scan-plugins\|verify-device" .claude/plugins/boardfarm-dev/skills/boardfarm-dev/SKILL.md
```

Expected output: `2`.

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/boardfarm-dev/skills/boardfarm-dev/SKILL.md
git commit -m "$(cat <<'EOF'
feat(.claude/plugins): add scan-plugins and verify-device to root menu

Root orchestrator's menu now lists all six sub-skills, matching the
updated registry.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

### Task 10: Update README, document the utility-skill contract exception, and verify final state

**Files:**
- Modify: `.claude/plugins/boardfarm-dev/README.md:18-51`

**Interfaces:**
- Consumes: nothing new — this is documentation reflecting Tasks 1-9's final state.

- [ ] **Step 1: Verify starting state**

```bash
grep -c "scan-plugins\|verify-device" .claude/plugins/boardfarm-dev/README.md
```

Expected output: `0`.

- [ ] **Step 2: Update the Usage section**

Using the Edit tool, replace:

```
## Usage

```
/boardfarm-dev              — interactive menu, pick what to build
/boardfarm-dev:new-template — scaffold a new Template (ABC)
/boardfarm-dev:new-device   — scaffold a new device class
/boardfarm-dev:new-connection — scaffold a new connection driver
/boardfarm-dev:new-use-case — scaffold new use-case function(s)
```
```

with:

```
## Usage

```
/boardfarm-dev              — interactive menu, pick what to build
/boardfarm-dev:new-template — scaffold a new Template (ABC)
/boardfarm-dev:new-device   — scaffold a new device class
/boardfarm-dev:new-connection — scaffold a new connection driver
/boardfarm-dev:new-use-case — scaffold new use-case function(s)
/boardfarm-dev:scan-plugins — discover installed boardfarm plugins and their templates/devices/use-cases
/boardfarm-dev:verify-device — verify a device class: lint+test, connectivity smoke check, or full boardfarm boot
```
```

- [ ] **Step 3: Document the utility-skill contract exception**

Using the Edit tool, replace:

```
## Sub-skill contract (for contributors)

Every sub-skill SKILL.md must implement three phases:

**Phase 1 — Discover:** Read `skills/shared/boardfarm-context.md`, run the
discovery shell commands, build in-memory menus. Ask no questions yet.

**Phase 2 — Interview:** Ask one question at a time, using multiple-choice menus
built from discovery where possible. Confirm every significant choice before
moving on.

**Phase 3 — Generate:** Produce four artefacts without asking further questions:
Python stub, inventory JSON snippet, unit test stub, pyproject.toml snippet.
Print a completion checklist at the end.
```

with:

```
## Sub-skill contract (for contributors)

Every **scaffolding** sub-skill SKILL.md (new-template, new-device,
new-connection, new-use-case) must implement three phases:

**Phase 1 — Discover:** Read `skills/shared/boardfarm-context.md`, run the
discovery shell commands, build in-memory menus. Ask no questions yet.

**Phase 2 — Interview:** Ask one question at a time, using multiple-choice menus
built from discovery where possible. Confirm every significant choice before
moving on.

**Phase 3 — Generate:** Produce four artefacts without asking further questions:
Python stub, inventory JSON snippet, unit test stub, pyproject.toml snippet.
Print a completion checklist at the end.

**Utility sub-skills** that discover or verify rather than scaffold
(scan-plugins, verify-device) follow a lighter variant: Phase 1 — Discover,
Phase 2 — Interview (may be a single tier-selection question), Phase 3 —
Execute (run checks or print a report; no artefacts, no completion
checklist).
```

- [ ] **Step 4: Verify the insertion**

```bash
grep -c "scan-plugins\|verify-device" .claude/plugins/boardfarm-dev/README.md
```

Expected output: `3` (one Usage line for each of the two new sub-skills, plus
one mention in the contract-exception paragraph — verify by re-reading if
the count differs, since exact phrasing may repeat a name more than once).

- [ ] **Step 5: Confirm the cache directory is already gitignored**

```bash
mkdir -p .claude/plugins/boardfarm-dev/.cache
touch .claude/plugins/boardfarm-dev/.cache/interview-defaults.json
git check-ignore -v .claude/plugins/boardfarm-dev/.cache/interview-defaults.json
rm -rf .claude/plugins/boardfarm-dev/.cache
```

Expected output: `.gitignore:44:.cache	.claude/plugins/boardfarm-dev/.cache/interview-defaults.json`
— confirms the pre-existing bare `.cache` pattern already covers the new
cache file, so no `.gitignore` edit is needed (see Global Constraints).

- [ ] **Step 6: Final spec-coverage check**

```bash
echo "Registry rows:" && grep -c "^|" .claude/plugins/boardfarm-dev/skills/registry.md
echo "New skill files:" && ls .claude/plugins/boardfarm-dev/skills/scan-plugins/SKILL.md .claude/plugins/boardfarm-dev/skills/verify-device/SKILL.md
echo "Root menu entries:" && grep -c "^\[.\]" .claude/plugins/boardfarm-dev/skills/boardfarm-dev/SKILL.md
```

Expected: registry shows `8` rows (header + separator + 6 skills), both new
`SKILL.md` files exist, and the root menu shows `6` numbered entries. This
confirms every component from the design doc's "Final registry state"
section is in place.

- [ ] **Step 7: Commit**

```bash
git add .claude/plugins/boardfarm-dev/README.md
git commit -m "$(cat <<'EOF'
docs(.claude/plugins): document scan-plugins and verify-device usage

Adds both new sub-skills to the README usage list and documents the
lighter Discover/Interview/Execute contract that utility sub-skills
(vs. scaffolding sub-skills) follow.

Signed-off-by: Ketan Tewari <ktewari.contractor@libertyglobal.com>
EOF
)"
```

---

## Self-review notes

**Spec coverage:** every design-doc component maps to a task — `scan-plugins`
(Task 1), shared-context wiring (Task 2), `new-template` structural check
(Task 3), `new-use-case` semantic check (Task 4), `new-device` cache (Task
5), `new-connection` cache (Task 6), `verify-device` three tiers (Task 7),
registry (Task 8), root menu (Task 9), README + gitignore verification
(Task 10). One deviation from the design doc, called out in Global
Constraints: no `.gitignore` edit is made, because the existing bare
`.cache` pattern already covers the new cache path (verified with `git
check-ignore` before this plan was written).

**Type/name consistency:** the cache file key names (`base_class`,
`connection_type`, `hook_category` for `new-device`; `transport` for
`new-connection`) match exactly between Task 5/6's read and write snippets.
The unified-list shapes (`{name, source_package, file_path}` for
templates/devices, `{name, template_params, first_docstring_line,
source_package, file_path}` for use-cases) are identical across Task 1's
Output Contract and Tasks 2-4's consumption of it.
