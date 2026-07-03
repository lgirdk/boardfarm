# boardfarm-dev

A Claude Code plugin that acts as a cookie-cutter for boardfarm contributors. It
guides you through building new boardfarm components and produces ready-to-fill
scaffold files.

## Installation

From the boardfarm repo root (one-time setup):

```bash
claude plugin marketplace add .claude/plugins/boardfarm-dev
claude plugin install boardfarm-dev@boardfarm-dev
```

Restart Claude Code after installation for the skills to become available.

## Usage

```
/boardfarm-dev              — interactive menu, pick what to build
/boardfarm-dev:new-template — scaffold a new Template (ABC)
/boardfarm-dev:new-device   — scaffold a new device class
/boardfarm-dev:new-connection — scaffold a new connection driver
/boardfarm-dev:new-use-case — scaffold new use-case function(s)
```

## Adding a new sub-skill

1. Create `skills/<new-name>/SKILL.md` following the Phase 1 → 2 → 3 contract
   described in `skills/shared/boardfarm-context.md`.
2. Add a row to `skills/registry.md` with all four columns filled.
3. Add a one-line description of the sub-skill to this README under **Usage**.
4. Test by invoking `/boardfarm-dev` (new entry must appear in menu) and
   `/boardfarm-dev:<new-name>` directly.

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
