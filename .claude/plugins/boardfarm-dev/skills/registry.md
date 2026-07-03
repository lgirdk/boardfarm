# Boardfarm Dev Skill Registry

This file is the single source of truth for which sub-skills exist. The root
orchestrator (`/boardfarm-dev`) reads this file to build its interactive menu.

**Rules:**
- All four columns must be filled for every row.
- SKILL.md paths are relative to the plugin root (`.claude/plugins/boardfarm-dev/`).
- A sub-skill that exists on disk but is absent from this table is invisible to
  the orchestrator.
- The "Covers" column text is shown verbatim in the orchestrator's menu.

## Adding a sub-skill

Add a new row to the table below AND create the corresponding SKILL.md file.
Both steps are required — one without the other is incomplete.

## Registry

| Skill name     | Invokable as                    | SKILL.md path                      | Covers                                        |
|----------------|---------------------------------|------------------------------------|-----------------------------------------------|
| new-template   | /boardfarm-dev:new-template     | skills/new-template/SKILL.md       | Abstract base class (template) definition     |
| new-device     | /boardfarm-dev:new-device       | skills/new-device/SKILL.md         | Concrete device class + hookimpl wiring       |
| new-connection | /boardfarm-dev:new-connection   | skills/new-connection/SKILL.md     | Transport / connection driver                 |
| new-use-case   | /boardfarm-dev:new-use-case     | skills/new-use-case/SKILL.md       | Use-case function(s) typed against a template |
