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
grep -o '"[a-z0-9_]*":' boardfarm3/lib/connection_factory.py
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
