# boardfarm-dev Plugin Enhancements — Design

## Context

The `boardfarm-dev` Claude Code plugin (`.claude/plugins/boardfarm-dev/`) is a
cookie-cutter skill set for scaffolding boardfarm components: templates,
devices, connections, and use-cases. Today it is entirely prose — five
`SKILL.md` files, a shared context file, and a registry — with no
verification, no environment awareness, and no memory across interview runs.

This design adds three capabilities identified as high-value next steps:

1. **Verification after scaffolding** — a way to check that a generated
   device class actually works, at three levels of rigor.
2. **Cached interview defaults** — reduce repeated re-answering of stable
   questions (base class, connection type, hook category) across
   `new-device` / `new-connection` runs.
3. **Plugin-aware environment discovery** — boardfarm is a plugin host;
   external packages (e.g. `boardfarm3-docsis`) contribute their own
   templates, devices, and use-cases. The dev plugin should discover what's
   installed and route developers toward existing components instead of
   duplicating them.

## Non-goals

- No RAG / vector search. The use-case corpus (core + plugins) is small
  enough today (~100-200 functions) to fit directly in an LLM's context for
  semantic comparison. See "Future extension point" below for how this could
  be added later without a redesign.
- No new Python runtime code, dependencies, or servers. Everything is
  implemented as prose instructions + shell one-liners inside `SKILL.md`
  files, consistent with how the plugin works today.
- No automatic conflict resolution. Duplicate-detection features inform and
  offer choices; they never block or silently reuse/rename on the
  developer's behalf.

## Architecture overview

### Files that change

| File | Change |
|------|--------|
| `skills/shared/boardfarm-context.md` | Phase 1 discovery section now opens by invoking `scan-plugins`, then builds unified (core + plugin) lists for templates, devices, connection types, and use-cases |
| `skills/new-template/SKILL.md` | Structural duplicate check against the unified template list (Section: Duplicate detection) |
| `skills/new-use-case/SKILL.md` | Two-step (gather/judge) duplicate check against the unified use-case list (Section: Duplicate detection) |
| `skills/new-device/SKILL.md` | Cached interview defaults (read at start of Phase 2, write at end of Phase 3) |
| `skills/new-connection/SKILL.md` | Cached interview defaults (read at start of Phase 2, write at end of Phase 3) |
| `skills/registry.md` | Two new rows: `scan-plugins`, `verify-device` |
| `skills/boardfarm-dev/SKILL.md` (root orchestrator) | Menu gains two lines for the new sub-skills |
| `.gitignore` | Add `.claude/plugins/boardfarm-dev/.cache/` |

### New files

| File | Purpose |
|------|---------|
| `skills/scan-plugins/SKILL.md` | Discovers installed boardfarm entry-point plugins; builds unified templates/devices/use-cases lists tagged by source package. Invocable standalone or called internally by every other sub-skill's Phase 1. |
| `skills/verify-device/SKILL.md` | Three-tier verification: lint+unit-test, connectivity smoke check, full boardfarm boot. Invocable standalone (not just from `new-device`'s Phase 3), since verification may happen days after scaffolding. |

### Unchanged

`skills/new-template/SKILL.md`'s and `skills/new-use-case/SKILL.md`'s
existing Phase 1/2/3 flow structure is preserved — duplicate detection is
inserted as an additional check within the existing interview, not a
restructuring.

## Component design

### 1. `scan-plugins`

**Purpose:** discover installed boardfarm plugins and build the unified
inventories every other skill's Phase 1 depends on.

**Invocation:** standalone (`/boardfarm-dev:scan-plugins`) for a developer who
just wants to see their environment, or internally at the start of every
other sub-skill's Phase 1.

**Mechanism:**

1. Discover installed boardfarm plugins via entry points:
   ```bash
   python -c "from importlib.metadata import entry_points; \
   eps = entry_points(group='boardfarm'); \
   [print(f'{ep.name} -> {ep.value}') for ep in eps]"
   ```
2. For each discovered plugin package, locate its installed source (via
   `importlib.util.find_spec`) and grep it the same way
   `boardfarm-context.md` greps core:
   - `^class ` in its `templates/` dir → external templates
   - `^class ` in its `devices/` dir → external devices
   - `^def ` in its `use_cases/` dir → external use-cases (also capturing
     parameter types and the first docstring line)
3. Merge with core `boardfarm3` results into one unified table per category,
   tagged with source package (`core` vs `boardfarm3-docsis` vs other).
4. Print a summary report showing installed plugins and unified list counts.

**Output contract:** three flat lists — templates, devices, use-cases — each
entry shaped as `{name, source_package, file_path}` (use-cases additionally
carry `template_params` and `first_docstring_line`). This is the fixed
"candidates" shape that downstream duplicate-detection steps consume.

**Failure mode:** if no plugins are installed beyond core, report core-only.
Never blocks the calling skill — a `scan-plugins` failure degrades to
core-only discovery with a warning, not a hard stop.

### 2. Duplicate detection in `new-template` (structural)

Templates are named classes, so this check is purely structural:

- Phase 1 calls `scan-plugins`, gets the unified template list.
- Phase 2 Q1 (class name): check exact match, then a normalized match
  (strip `Device`/`Template`/`Base` suffixes, lowercase, compare).
- **On hit:** show the existing template and its source package/file, then
  offer three choices:
  1. Open/edit that file instead
  2. Extend via mixin
  3. Proceed anyway with a different name (developer confirms the intent is
     genuinely distinct)
- **No hit:** proceed silently, no extra noise.

### 3. Duplicate detection in `new-use-case` (semantic, gather/judge split)

Use-cases can share intent under different names, so structural matching
alone is insufficient. The check is split into two independent steps with a
fixed handoff shape, so the gathering mechanism can be swapped later (e.g.
for retrieval-based search) without touching the judgment logic:

**Step A — Gather candidates** (mechanics only, no judgment)
Input: none (reads from `scan-plugins`' output). Output: a flat list of
`{name, template_params, first_docstring_line, source_package}` for every
existing use-case across core + discovered plugins.

**Step B — Judge candidates** (judgment only, no mechanics)
Input: the candidate list from Step A + the developer's stated intent and
parameter signature. Output: a verdict — either "overlaps with `X` in
`<file>`, because `<reasoning>`" or "no overlap."

**Interview flow:**

- Phase 2 Q1: "What Template(s) does your function take as parameters?" →
  structural filter narrows Step A's candidate list to those sharing the
  same Template parameter set.
- Phase 2 Q2: "In one sentence, what does your function do?" → Step B
  compares stated intent against the (possibly narrowed) candidate list.
- **On hit:** show the existing use-case and its source, offer: reuse it /
  extend it / proceed with a stated justification for why it's distinct.
- **No hit:** proceed silently.

Asking for parameters before intent lets the cheap structural filter narrow
the list before the more expensive semantic judgment runs over it — this
matters as plugin use-case counts grow.

**Future extension point:** Step A's "gather" mechanism can later be
replaced by real retrieval (e.g. embedding-based nearest-neighbor search)
without changing Step B's contract, since Step B only ever consumes "a list
of candidates" regardless of how they were gathered. This is not being built
now — see Non-goals.

### 4. Cached interview defaults in `new-device` / `new-connection`

**Storage:** a single gitignored cache file at
`.claude/plugins/boardfarm-dev/.cache/interview-defaults.json`, keyed by
skill name:

```json
{
  "new-device": {
    "base_class": "LinuxDevice",
    "connection_type": "ssh_connection",
    "hook_category": "attached_device"
  },
  "new-connection": {
    "transport": "ssh"
  }
}
```

This is local developer convenience, not shared team config — it is added to
`.gitignore`.

**Start of Phase 2 (read, before Q1):** if the cache file has an entry for
this skill, weave the last-used value into the relevant question as a
suggested default rather than skipping the question, e.g.:

```
Q3: Which base class?
[1] LinuxDevice (used last time)
[2] BoardfarmDevice
```

The developer still answers every question — caching only reduces
re-typing/re-reading effort, and never silently reuses an old answer without
the developer seeing and confirming it.

**Phase 3 (write, after generation succeeds):** once the developer confirms
"yes" at the pre-generation summary and files are written, overwrite this
skill's entry in the cache file with the answers just given.

**Scope:** only stable-across-runs fields are cached — `base_class`,
`connection_type`, `hook_category` for `new-device`; `transport` for
`new-connection`. Free-text fields (class name, inventory keys) are never
cached, since they are unique per component by definition.

### 5. `verify-device` (three-tier verification)

**Invocation:** standalone (`/boardfarm-dev:verify-device`) — verification
may happen well after scaffolding, e.g. right before a commit, or days later
while debugging.

**Opens by asking which tier:**

```
What level of verification do you need?

[1] Lint + unit tests        — safe, no hardware needed, run before committing
[2] Connectivity smoke check — quick pexpect probe against a live host, while writing _connect()
[3] Full boardfarm boot      — runs the actual boardfarm CLI against target hardware
```

**Tier 1 — Lint + unit tests**
- Runs `nox -s lint` and `pytest unittests/devices/test_<module_name>.py`
  (prompts for the path if run standalone, not immediately after
  `new-device`).
- Reports pass/fail per check with the actual error output on failure; does
  not attempt to auto-fix.
- Use case: "I'm confident in my change, about to commit."

**Tier 2 — Connectivity smoke check**
- Asks for host/IP, port, connection type (from the discovered connection
  type keys), and credentials.
- Writes a throwaway pexpect probe (not saved to the repo) that calls
  `connection_factory(...)` and performs a single `sendline`/`expect`
  round-trip, then closes the connection.
- Reports: connected / prompt matched / timed out / auth failed.
- Use case: "I'm mid-way through writing `_connect()` and want fast signal
  without a full boardfarm run."

**Tier 3 — Full boardfarm boot**
- Always asks for `--inventory-config` and `--env-config` paths first —
  never assumes the example configs.
- Always defaults to `--skip-boot` unless the developer explicitly confirms
  a full boot:
  > "This will run `boardfarm --board-name <name> --inventory-config <path>
  > --env-config <path> --skip-boot`. Run a full boot instead (no
  > `--skip-boot`)? This actually drives hardware/lab state — confirm
  > (yes/no)."
- On confirmation for a full boot, verifies `board-name` matches an entry in
  the given inventory before executing.
- Surfaces boardfarm's raw log output directly rather than a summarized
  verdict — this is the "debug why a hook is failing" path, where the
  unabridged logs are the point.

## Final registry state

| Skill name | Invokable as | Covers |
|---|---|---|
| new-template | `/boardfarm-dev:new-template` | Abstract base class (template) definition — now with structural duplicate check |
| new-device | `/boardfarm-dev:new-device` | Concrete device class + hookimpl wiring — now with cached interview defaults |
| new-connection | `/boardfarm-dev:new-connection` | Transport / connection driver — now with cached interview defaults |
| new-use-case | `/boardfarm-dev:new-use-case` | Use-case function(s) typed against a template — now with intent-based duplicate check |
| scan-plugins | `/boardfarm-dev:scan-plugins` | Discover installed boardfarm plugins; build unified template/device/use-case lists |
| verify-device | `/boardfarm-dev:verify-device` | Three-tier verification: lint+test, connectivity smoke check, full boardfarm boot |

The root orchestrator's menu (`skills/boardfarm-dev/SKILL.md`) gains two
lines for `scan-plugins` and `verify-device`, sourced from the registry as
today.

## Testing / validation approach

Since this plugin is entirely prose-driven (no Python code to unit test),
validation is manual dry-runs of each sub-skill against this repo's actual
state:

- `scan-plugins` — run in an environment with only core `boardfarm3`
  installed, and (if available) one with `boardfarm3-docsis` installed, to
  confirm both the core-only and plugin-aware paths work.
- `new-template` — attempt to create a template name that collides with an
  existing one (e.g. `CPE`) and confirm the duplicate check fires with the
  correct file reference.
- `new-use-case` — attempt to describe a use-case whose intent matches an
  existing function's docstring under a different name, and confirm Step B
  flags it.
- `new-device` / `new-connection` — run the interview twice in a row and
  confirm the second run surfaces the first run's answers as defaults.
- `verify-device` — exercise Tier 1 against an existing device's test file;
  exercise Tier 3's `--skip-boot` default and confirm it refuses to run a
  full boot without explicit confirmation.
