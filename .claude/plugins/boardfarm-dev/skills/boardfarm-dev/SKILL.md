---
name: boardfarm-dev
description: Cookie-cutter entry point for boardfarm plugin development. Use when a developer wants to build any new boardfarm component — template (ABC), device class, connection driver, or use-case function. Triggers on: "new boardfarm component", "help me write a boardfarm plugin", "I want to build a new boardfarm device", "boardfarm cookiecutter", "scaffold a boardfarm template/device/connection/use-case", or any request to create new boardfarm code. Dispatches to the right sub-skill; performs no code generation itself.
---

# boardfarm-dev — Root Orchestrator

Your job is to present a numbered menu and dispatch to the right sub-skill.
You do NOT generate any code, stubs, or scaffolding yourself.

## Step 1 — Read the registry

Read the file at `skills/registry.md` inside this plugin directory
(`.claude/plugins/boardfarm-dev/skills/registry.md` relative to the repo root).
Parse the table to extract the "Skill name" and "Covers" columns.

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

## Step 3 — Dispatch

**Developer picks a number or names a sub-skill:**
Announce `"Using /boardfarm-dev:<name> to guide you through this."` then invoke
that sub-skill.

**Developer describes something spanning multiple sub-skills** (e.g. "I need a
new template AND a device for it"):
Say: "I handle one component at a time. Since your template doesn't exist yet,
start with `/boardfarm-dev:new-template` to create the ABC, then come back and
run `/boardfarm-dev:new-device` to implement it. Shall I start with the template?"

**Developer names a sub-skill not in the registry:**
Say: "That sub-skill isn't in the registry. Here's what's currently available:"
then print the full registry table and stop.

## Constraints

- You perform **no** code generation, file creation, or scaffolding.
- You read the registry fresh every time (do not cache between sessions).
- If the registry file is missing, say: "The registry at
  `skills/registry.md` could not be found. Ensure the boardfarm-dev plugin
  is correctly installed from the repo root with
  `claude plugin install .claude/plugins/boardfarm-dev`."
