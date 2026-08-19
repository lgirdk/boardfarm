# Agent Diagnostics and Stream Robustness — Design

**Date:** 2026-08-19
**Status:** Approved, ready for implementation planning
**Phase:** 4 of the boardfarm REST API roadmap
**Predecessors:**
- `2026-08-10-boardfarm-fastapi-backend-design.md` (Phase 1 — agent core)
- `2026-08-13-boardfarm-control-plane-design.md` (Phase 2 — control plane)

---

## 1. Goal

Make a failed, wedged, or crashed agent **debuggable**, and make long-running
operations survive the control plane proxy.

Today an agent that fails is destroyed before anyone can look at it, the only
failure detail that reaches a caller is an exception class name, and any proxied
call lasting more than five seconds is severed. This design fixes all three
without changing the shape of the existing API surface the JS client is
generated from.

Three outcomes:

1. **Post-mortem is possible.** A failed container is retained (stopped, not
   removed), and its artifacts are pulled to the control plane before it dies.
2. **Failures carry evidence.** Python tracebacks reach the API, console logs
   are always written, and a single bundle endpoint returns everything.
3. **Long operations work.** The proxy stops imposing a 5 s ceiling, SSE streams
   stay alive through quiet periods, and a slow-but-healthy job is no longer
   mislabelled as stuck.

### Non-goal

**Nothing in this design terminates a live session.** There is no watchdog, no
auto-kill, and no automatic remediation. Every teardown of a running session
remains caller-initiated. This is stated explicitly because §5 introduces a
reaper and §9 introduces a liveness signal, and the two must not be conflated:
the reaper only purges containers that have *already* stopped, and the liveness
signal is reported, never acted upon.

---

## 2. Problems, with evidence

### 2.1 Post-mortem is impossible by construction

`DockerLauncher.stop()` (`boardfarm3_control/launcher.py:398-413`) always does
`container.stop()` **and** `container.remove()`. `create_session`
(`boardfarm3_control/app.py:126-178`) calls it on every failure-unwind path —
health timeout, config rejection, boot rejection — and `delete_session` calls it
on teardown. By the time a caller reads the 503, the evidence is gone.

`ProcessLauncher` discards the evidence even earlier: agent stdout and stderr go
to `DEVNULL` (`boardfarm3_control/launcher.py:214-215`), so a Python traceback
from a crashing agent is destroyed at the source.

### 2.2 No traceback reaches any API

`error_envelope()` (`boardfarm3/api/errors.py:50-80`) emits `error`, `message`,
`device`, `session_id`, `job_id`, and `console_tail`. There is no traceback.
`console_tail_from()` (`boardfarm3/api/errors.py:83-100`) filters to
`stream="console"`, so framework-logger output — where a Python error would
surface — is excluded from the tail as well.

`ConsoleCapture.emit()` (`boardfarm3/api/console.py:181-201`) calls
`record.getMessage()`, which drops `record.exc_info`. Even a correctly-logged
exception loses its traceback on the way into the buffer.

### 2.3 Console logs are opt-in and usually off

`RuntimeOptions.save_console_logs` defaults to `""`
(`boardfarm3/api/runtime.py:31`). `BoardfarmPexpect._configure_logging()`
(`boardfarm3/lib/boardfarm_pexpect.py:102-115`) only attaches its
`RotatingFileHandler` when that value is truthy, and `GET /console/archive`
(`boardfarm3/api/app.py:311-331`) returns 404 without it. In the default
configuration no console file is ever written.

### 2.4 The proxy imposes a 5 s ceiling on everything

`proxy_request()` builds `httpx.AsyncClient()` with **default timeouts**
(`boardfarm3_control/proxy.py:74`) — 5 s connect, read, write, and pool. Two
consequences:

- Any proxied call taking longer than 5 s to produce its first byte returns
  `502 agent unreachable`.
- An SSE stream idle for 5 s hits the read timeout. The resulting
  `httpx.TransportError` is caught and silently `return`ed
  (`boardfarm3_control/proxy.py:96-99`), so the client sees a *clean* end of
  stream and cannot distinguish "finished" from "broken".

The agent's SSE loop (`boardfarm3/api/app.py:298-307`) wakes every 1 s and
`continue`s without emitting anything, so a quiet console guarantees the 5 s
trip. A client is also created and discarded per request — no connection reuse.

### 2.5 "stuck" is a wall-clock guess that destroys information

`Session.is_stuck()` (`boardfarm3/api/session.py:142-154`) reports stuck when the
running job has been running longer than `stuck_after` — 900 s, hardcoded at
`boardfarm3/api/session.py:39` and absent from `ConfigOptions`, so it cannot be
tuned per board.

Worse, `status()` (`boardfarm3/api/session.py:162`) *replaces* `state` with
`"stuck"`. A session that is legitimately booting stops reporting `booting`. A
slow-but-healthy pexpect wait is indistinguishable from a wedged one, and the
frontend is handed a terminal-looking verdict with no evidence behind it.

`is_stuck()` has exactly one consumer — that line. Nothing acts on it.

### 2.6 Restart semantics contradict the control plane design

Two defects that are load-bearing for retention:

- `SessionRegistry.rebuild()` (`boardfarm3_control/registry.py:80-90`) calls
  `launcher.list_sessions()`, which for `DockerLauncher` uses
  `containers.list()` — **running containers only**
  (`boardfarm3_control/launcher.py:425-429`). A retained corpse would disappear
  from the registry on a control plane restart: orphaned, invisible to the API,
  and never reaped.
- The lifespan shutdown hook (`boardfarm3_control/app.py:69-70`) stops **every**
  session when the control plane exits. This contradicts §4.4 of the control
  plane design ("Running sessions are unaffected") and, with removal on by
  default, would destroy the very containers being debugged whenever the control
  plane restarts.

---

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Retain failed containers **stopped, not removed**; pull artifacts over HTTP before stopping | A stopped container releases every tty and socket, so a corpse can never contend with a fresh session on the same board — while `docker logs`, `get_archive`, and `inspect` all still work against it |
| D2 | Artifacts move **over the wire**, never via a shared filesystem | A bind-mount hardcodes "the agent runs on the control host", which is exactly the assumption `MultiHostDockerLauncher` exists to break |
| D3 | `Launcher` remains the only host-aware seam | `logs()` and `get_archive()` are Docker *daemon API* calls, so they work identically against a remote daemon; a future `KubernetesLauncher` implements the same four methods |
| D4 | The lease is released immediately on failure; the corpse holds nothing | A crash at 2 am must not block a board until a human intervenes |
| D5 | Liveness is reported as **evidence, not a verdict**; `SessionState.STUCK` is removed | Idle time alone cannot distinguish a wedged `expect()` from a silent image flash; a thread stack can |
| D6 | No automation. Nothing kills a live session | The threshold is a heuristic; acting on a heuristic is how a healthy 20-minute flash gets killed |

### Consequence of D4 accepted explicitly

Because the lease is released while the corpse remains listed, `board_name` is
**no longer unique** across the sessions returned by `GET /sessions`. A dead
session and a live one may name the same board. Clients must key on `session_id`
and filter on `state`.

---

## 4. Rejected alternatives

**Bind-mount a per-session artifact directory from the control host.** Simplest
and most robust for a single host — files land on the control plane as they are
written, surviving even a hard crash, with nothing to copy. Rejected because it
assumes the control plane and the Docker daemon share a filesystem, which is
false the moment agents run on a second host. `agent_url` is already hardcoded
to `http://localhost:{host_port}` (`boardfarm3_control/launcher.py:394`); that
is a one-field fix, whereas a filesystem assumption would be baked into the
artifact path of every component.

**Launcher-only capture, with no agent endpoint.** One code path and multi-host
safe, but a healthy `ready` session could not hand over its own logs without
going through the Docker daemon, and every future launcher would have to
implement file extraction even where its platform makes that awkward.

**Agent pushes its bundle to the control plane.** Works through NAT, but a hard
crash (SIGKILL, OOM) pushes nothing — precisely the case this design exists to
serve — and it adds an inbound write endpoint plus an agent→control auth story.

**Auto-reaping stuck sessions.** Rejected per D6. If it is ever wanted, the safe
gate is: worker stack byte-identical across N samples spanning M minutes, AND
console silent throughout, AND `/health` still answering — defaulting to off.

**Making generated routes async-first.** Unnecessary: `?mode=async` already
exists on every generated route (`boardfarm3/api/routers/_generator.py:357`,
`boardfarm3/api/routers/_usecase_generator.py:199`) and the proxy forwards the
query string verbatim. It needs a round-trip test, not a redesign.

---

## 5. Container retention

### 5.1 Two mechanisms, deliberately separate

**Teardown** is always caller-initiated, via `DELETE /sessions/{sid}` or a
failure unwind inside `POST /sessions`. It decides *whether the container is
removed*.

**The corpse reaper** is a background task that operates **only on containers
that are already stopped**. It never inspects, contacts, or terminates a live
session, and has no access to liveness state.

### 5.2 Teardown matrix

| Session's last state | Bundle pulled | Container | Registry |
|---|---|---|---|
| `failed` / `unreachable` | yes | stopped, **retained** | kept, `state: "dead"` |
| `ready` / `created`, clean `DELETE` | yes | stopped + removed | removed |
| `DELETE ?retain=true` | yes | stopped, **retained** | kept, `state: "dead"` |
| `DELETE ?purge=true` | yes | stopped + removed | removed |

Retention deliberately does **not** key on the `quiet` liveness signal (§10.3).
A wedged session is retained by the caller passing `?retain=true`; a UI may
default that toggle from `quiet`, but the server never infers it. This keeps
D5 and D6 intact: no server-side behaviour branches on a heuristic.

The bundle is archived to the control plane store in **every** row, so a cleanly
deleted session still leaves its logs behind; only the ability to `docker
commit` its filesystem is lost.

Order of operations on every teardown path:

```
1. Pull diagnostics bundle over HTTP        (agent still alive — the only moment this works)
2. DELETE /session on the agent             graceful boardfarm_release_devices; skipped if unreachable
3. launcher.stop(sid, remove=<per matrix>)  SIGTERM -> pexpect children die -> ttys/sockets released
4. lease.release(sid)                       unconditional
5. registry: remove, or mark state="dead"
```

Steps 1 and 2 are best-effort: a failure in either is logged and does not
prevent 3, 4, or 5. A dead agent must never strand a board or leak a container.

### 5.3 Failure unwinds in `POST /sessions`

The three unwind paths in `create_session` (health timeout, config rejection,
boot rejection) currently call `launcher.stop()` and drop the lease. They change
to run the sequence in §5.2 with `remove=False`, and their error responses gain
two fields so a 503 says where to look:

```json
{
  "error":       "AgentUnhealthy",
  "message":     "agent did not become healthy within 30 s",
  "session_id":  "s-4f2a",
  "diagnostics": "/sessions/s-4f2a/diagnostics"
}
```

The session is registered with `state: "dead"` rather than discarded.

### 5.4 The corpse reaper

A background task started in the control plane lifespan, running every
`BOARDFARM_REAP_INTERVAL` (default 900 s):

- Purges retained containers whose `ended_at` is older than
  `BOARDFARM_CORPSE_TTL` (default 86 400 s).
- Deletes archived bundles older than `BOARDFARM_BUNDLE_TTL` (default
  604 800 s).
- Enforces `BOARDFARM_BUNDLE_MAX_BYTES` (default 20 GiB) over the whole store by
  deleting oldest-first until under the cap.

Every purge and eviction is logged with the session id, age, and reclaimed
bytes. The reaper never calls `stop()`, only `purge()`.

### 5.5 Restart correctness

Both defects in §2.6 are fixed here, because retention is meaningless without
them:

- `DockerLauncher.list_sessions()` uses `containers.list(all=True)` and derives
  lifecycle from container status: `running` → live, anything else → dead.
  Docker labels cannot be mutated after creation, so status is the signal, not a
  label.
- The control plane store is the source of truth for dead sessions.
  `sessions/{sid}/meta.json` records `session_id`, `board_name`,
  `runtime_profile`, `created_at`, `ended_at`, and `reason`, and survives both a
  control plane restart and the eventual container purge.
- `BoardLease.rebuild_from()` is given **live sessions only**. A corpse must
  never re-acquire a lease on restart.
- The lifespan shutdown hook no longer stops sessions. Control plane restarts
  leave running agents untouched, as §4.4 of the control plane design already
  specifies.

---

## 6. Launcher protocol

```python
async def start(self, session_id, board_name, image, runtime_profile,
                agent_env=None) -> AgentInfo: ...
async def stop(self, session_id: str, *, remove: bool = True) -> None: ...
async def purge(self, session_id: str) -> None: ...
async def capture_logs(self, session_id: str) -> bytes: ...
async def capture_files(self, session_id: str, path: str) -> bytes: ...
async def list_sessions(self) -> list[AgentInfo]: ...
```

`capture_logs()` returns the agent's stdout/stderr. `capture_files()` returns
tar bytes for a path inside the agent. Both are the **fallback** used only when
the agent's own HTTP endpoint is unreachable.

**`DockerLauncher`** implements them with `container.logs(stdout=True,
stderr=True)` and `container.get_archive(path)`. Both are daemon API calls, so
they work against a remote daemon and against a stopped container.
`purge()` is `container.remove()`.

**`ProcessLauncher`** stops sending output to `DEVNULL`. stdout and stderr are
redirected to `{store}/sessions/{sid}/process.log`, which is what
`capture_logs()` reads; `capture_files()` reads the local path directly;
`purge()` deletes the session directory.

**`FakeLauncher`** implements all four in memory, returning synthetic bytes, so
no control plane test needs a Docker daemon.

`AgentInfo` gains `state: str = "live"` and `ended_at: float | None = None`. The
model is frozen, so transitions use `model_copy(update=...)`.

---

## 7. Agent: always-on logs and real tracebacks

### 7.1 Console logs are always written

`RuntimeOptions.save_console_logs` defaults to
`{BOARDFARM_ARTIFACT_DIR}/{session_id}`, where `BOARDFARM_ARTIFACT_DIR` defaults
to `/var/log/boardfarm`. `ConfigOptions.save_console_logs` may still *redirect*
it, but an empty or omitted value no longer disables it — it resolves back to
the default.

This resolves during `Session.configure()`, which calls
`refresh_cmdline_args()` before `register_devices()`. Device connections are
built later, inside the boot hooks, so
`BoardfarmPexpect._configure_logging()` sees a populated value and attaches its
`RotatingFileHandler` for every session. `GET /console/archive` consequently
stops returning 404.

### 7.2 Tracebacks, in the three places they are currently dropped

1. **`error_envelope()`** gains `traceback: list[str]`, from
   `traceback.format_exception(exc)` — which already walks the `__cause__` and
   `__context__` chain. `console_tail_from()` stops filtering on
   `stream="console"` so framework lines appear in the tail too.
2. **`ConsoleCapture.emit()`** formats `record.exc_info` when present and
   appends it to the captured line, so exceptions become visible in `/console`,
   the SSE stream, and `/jobs/{id}/console`.
3. **`ExecutionQueue._run()`** calls `_log.exception()` before re-raising, so
   *every* job failure is captured — not just boot, which is the only path that
   records an envelope today.

### 7.3 An agent log file

A `RotatingFileHandler` on the `boardfarm3` framework logger writes
`{artifact_dir}/agent.log` (10 MiB × 3), installed at agent startup before the
session is built. Uvicorn's loggers are attached to it as well, so an unhandled
error in the ASGI layer is on disk even when nobody is watching the stream and
even when the process subsequently dies.

---

## 8. The diagnostics bundle

New agent route:

```
GET /diagnostics/bundle    -> streaming application/gzip
```

Valid in **any** session state, including `ready` — it is a snapshot, not a
teardown step, and taking one has no side effects on the session.

```
manifest.json     session id, board, profile, agent version, timestamps, bundle schema version
session.json      status() output + resolved options (redacted)
config.json       resolved inventory/env payload (redacted)
jobs.json         every job: id, state, timings, error envelope incl. traceback
events.jsonl      full EventBuffer dump, one JSON object per line
threads.txt       stack of every live thread at capture time (see §10.4)
agent.log         framework log including tracebacks
console-logs/     contents of the save_console_logs directory
```

The archive streams — it is built with `tarfile` writing into the response, not
buffered into memory, because console logs are capped at 25 MB per device by the
existing `RotatingFileHandler`.

### 8.1 Redaction is mandatory

The session payload carries device credentials. In `session.json` and
`config.json`, any key matching `pass|passwd|password|secret|token|key|auth`
(case-insensitive) has its value replaced with `"***"`, recursively through
nested dicts and lists.

`console-logs/`, `events.jsonl`, and `agent.log` are **not** redacted — a
credential echoed by a login prompt cannot be reliably scrubbed from a console
transcript. This is a documented property of the bundle: it is as sensitive as
the console it captures, and must be handled accordingly. `manifest.json`
carries `"redacted": ["session.json", "config.json"]` so consumers know exactly
what was and was not processed.

---

## 9. Control plane diagnostics surface

```
GET  /sessions/{sid}/diagnostics           -> application/gzip
POST /sessions/{sid}/diagnostics/snapshot  -> 200 {path, size, source, captured_at}
```

`GET` resolves in three tiers:

1. **Agent reachable** — proxy-stream `GET /diagnostics/bundle` straight
   through. Nothing is buffered or stored.
2. **Agent unreachable, bundle archived** — serve the stored bundle from
   `{store}/sessions/{sid}/bundle.tar.gz`.
3. **Agent unreachable, nothing archived** — build one now from
   `launcher.capture_logs()` and `launcher.capture_files()`, archive it, and
   serve it. This is the hard-crash path, and it is the reason `Launcher` grew
   those two methods.

If all three fail, `404` with a body naming which tiers were attempted and why
each failed.

`POST .../diagnostics/snapshot` forces tier 1 or 3 to run *now* and archives the
result, returning where it went and which tier produced it. It works on a
healthy `ready` session, which is the explicit requirement: capture evidence
before deciding to tear anything down.

The control plane also runs a snapshot automatically as step 1 of every teardown
(§5.2), including every `POST /sessions` failure unwind — the only moment a
crashing agent can still answer HTTP.

**Store layout:**

```
{BOARDFARM_CONTROL_STORE}/sessions/{sid}/
    meta.json           survives container purge; source of truth for dead sessions
    bundle.tar.gz       archived agent bundle
    process.log         ProcessLauncher stdout/stderr only
```

---

## 10. Stream and liveness

### 10.1 Proxy

A single pooled `httpx.AsyncClient` is created in the control plane lifespan and
closed at shutdown, replacing the per-request client at
`boardfarm3_control/proxy.py:74`. Timeouts are chosen per request:

| Request class | Timeout |
|---|---|
| Streaming — path ends `/stream`, or is under `/diagnostics` | `connect=10, read=None, write=30, pool=10` |
| Everything else | `connect=10, read=1800, write=30, pool=10` |

`read` and `connect` for the non-streaming class are settable via
`BOARDFARM_PROXY_READ_TIMEOUT` and `BOARDFARM_PROXY_CONNECT_TIMEOUT`. Streaming
reads are unbounded deliberately: the agent bounds its own operations (pexpect
timeouts), and a bounded read here is exactly the bug being fixed.

A mid-flight `httpx.TransportError` is no longer swallowed
(`boardfarm3_control/proxy.py:96-99`). It is logged with the session id and
path, and for `text/event-stream` responses a final frame is emitted so the
client can tell a broken stream from a finished one:

```
event: error
data: {"error": "StreamInterrupted", "message": "...", "session_id": "s-4f2a"}
```

`_STATE_TIMEOUT` for the `GET /sessions` fan-out goes from 0.5 s to 2.0 s,
settable via `BOARDFARM_STATE_TIMEOUT`. 500 ms is tight enough to report a
healthy agent as `unreachable` under load.

### 10.2 Agent SSE

The 1 s queue-wait loop (`boardfarm3/api/app.py:298-307`) emits a comment frame
`: keepalive\n\n` after `BOARDFARM_SSE_KEEPALIVE` seconds (default 15) without
having sent anything. The response carries `X-Accel-Buffering: no` so an
intermediate proxy does not buffer the stream into uselessness.

### 10.3 Liveness as evidence

`SessionState.STUCK` is **removed**, and `status()` no longer overwrites `state`
(`boardfarm3/api/session.py:162`). `state` stays truthful; a sibling object
carries the signal:

```json
{
  "state": "booting",
  "liveness": {
    "quiet":         true,
    "running_for":   742.1,
    "idle_for":      241.0,
    "last_line":     "flashing image, 34% ...",
    "last_event_ts": 1723500742.1
  }
}
```

`EventBuffer` records `last_event_ts` on append. `quiet` is
`now - max(job.started_at, last_event_ts) > quiet_after`, and is **reversible** —
one more log line clears it. `Session.stuck_after` (900 s, hardcoded) is
replaced by `quiet_after`, **default 600 s**, settable via `ConfigOptions`.

600 s rather than a tighter value because image flash and CPE-online waits are
legitimately silent for minutes at a time. It is documented as a *display*
threshold: no code branches on `quiet`.

When no job is running, `liveness` is `{"quiet": false, "running_for": null,
"idle_for": null, "last_line": null, "last_event_ts": <ts>}`.

`SessionResponse` gains `liveness: dict[str, Any] | None`, forwarded verbatim by
the `GET /sessions` fan-out (`boardfarm3_control/app.py:203-231`) so a list view
can show progress without a second round trip per session. It is `None` for
sessions in state `dead` or `unreachable`.

### 10.4 Thread stacks — the part that actually answers "stuck or slow?"

Idle time alone cannot distinguish a wedged `expect()` from a silent flash. A
stack can:

```
GET /diagnostics/threads   -> {"threads": [{"name": "bf_0", "worker": true, "stack": [...]}, ...]}
```

Built from `sys._current_frames()` and `traceback.format_stack()`, with the
execution queue's worker identified by its `bf` thread-name prefix
(`boardfarm3/api/execution.py:56`). Read-only, allocation-light, and safe to
call against a wedged session — it does not touch the queue or any console.

A snapshot is included in the bundle as `threads.txt`. The documented procedure
for proving wedged-versus-working is **two samples 30 s apart, diffed**:
identical stack plus no console output means wedged; a moving stack or moving
output means working.

---

## 11. Error handling

| Condition | HTTP | Notes |
|---|---|---|
| `GET /diagnostics` — all three tiers failed | 404 | body lists each tier attempted and why it failed |
| `GET /diagnostics` — unknown session | 404 | |
| `POST /diagnostics/snapshot` — agent unreachable and launcher capture failed | 502 | |
| `DELETE` with both `?retain=true` and `?purge=true` | 400 | mutually exclusive |
| Bundle pull fails during teardown | — | logged, teardown continues; a diagnostics failure must never strand a board |
| Agent `GET /diagnostics/bundle` while artifact dir missing | 200 | bundle is emitted with whatever exists; `manifest.json` records what was absent |
| Proxy stream interrupted mid-flight | — | `event: error` frame for SSE; logged for all other content types |

---

## 12. Testing

**Agent unit tests** (`unittests/api/`):
- `save_console_logs` resolves to a default and cannot be disabled by an empty
  `ConfigOptions` value.
- `error_envelope()` carries a traceback; a chained exception carries both
  frames.
- `ConsoleCapture.emit()` preserves `exc_info`.
- Every job failure — not only boot — records an envelope with a traceback.
- `GET /diagnostics/bundle` returns a valid tar.gz containing each documented
  member, in `created`, `ready`, and `failed` states.
- Redaction: a password in the payload appears as `***` in `session.json` and
  `config.json`; `manifest.json` lists what was redacted.
- Liveness: a slow-but-chatty job reports `quiet: false`; a silent job reports
  `quiet: true` **without** changing `state`; `quiet` clears when output
  resumes.
- `GET /diagnostics/threads` returns the worker frame while a job is blocked.
- SSE emits a keepalive after the configured idle interval.

**Control plane unit tests** (`unittests/control/`, `FakeLauncher` throughout —
no Docker):
- Each row of the §5.2 teardown matrix, asserting bundle-pulled,
  container-retained-or-removed, registry state, and **lease released in every
  row**.
- Each `POST /sessions` unwind path retains the container, registers the session
  as `dead`, and returns `session_id` + `diagnostics` in the error body.
- `GET /diagnostics` tier resolution: agent reachable, agent dead with an
  archive, agent dead without one, and all-tiers-failed → 404.
- `POST /diagnostics/snapshot` on a `ready` session archives without disturbing
  the session.
- Reaper purges past `CORPSE_TTL`, evicts bundles past `BUNDLE_TTL`, and
  enforces the size cap oldest-first — and never calls `stop()`.
- Restart: `rebuild()` recovers both live and dead sessions; `rebuild_from()`
  re-leases **only** live ones; lifespan shutdown leaves running agents alone.
- Proxy: an SSE stream idle well past the old 5 s window survives; a 10 s
  response body is not truncated; a mid-flight transport error yields an
  `event: error` frame rather than a silent close.
- `?mode=async` round-trips through a control plane wrapper route and the job is
  pollable via the proxied `/jobs/{id}`.

**Integration** (extends `integrationtests/control/`): force a boot failure
against the prplOS compose stack, then assert — the container is retained and in
`exited` state; `GET /sessions/{sid}/diagnostics` returns a bundle whose
`jobs.json` contains a Python traceback; a second session on the **same board**
starts cleanly while the corpse is still present; `DELETE ?purge=true` removes
both container and bundle.

---

## 13. Configuration reference

| Variable | Component | Default | Purpose |
|---|---|---|---|
| `BOARDFARM_ARTIFACT_DIR` | agent | `/var/log/boardfarm` | root of per-session artifact dirs |
| `BOARDFARM_SSE_KEEPALIVE` | agent | `15` | seconds of SSE silence before a keepalive frame |
| `BOARDFARM_CONTROL_STORE` | control | `/var/lib/boardfarm-control` | bundle and metadata store |
| `BOARDFARM_CORPSE_TTL` | control | `86400` | seconds before a retained container is purged |
| `BOARDFARM_BUNDLE_TTL` | control | `604800` | seconds before an archived bundle is deleted |
| `BOARDFARM_BUNDLE_MAX_BYTES` | control | `21474836480` | total store cap, evicted oldest-first |
| `BOARDFARM_REAP_INTERVAL` | control | `900` | seconds between reaper passes |
| `BOARDFARM_PROXY_READ_TIMEOUT` | control | `1800` | read timeout for non-streaming proxied calls |
| `BOARDFARM_PROXY_CONNECT_TIMEOUT` | control | `10` | connect timeout for all proxied calls |
| `BOARDFARM_STATE_TIMEOUT` | control | `2.0` | per-agent timeout for the `GET /sessions` fan-out |

`quiet_after` is a per-session `ConfigOptions` field (default `600.0`), not an
environment variable, because it is board-dependent.

---

## 14. Out of scope

- **A pexpect progress heartbeat.** Having long device waits emit
  "still waiting on X (Ns)" every ~60 s would make console silence a *true*
  signal rather than a proxy for one, and would let `quiet_after` drop to
  ~120 s. It is a `boardfarm3/lib/boardfarm_pexpect.py` change — Layer 4, relied
  on by every device and every external plugin — and deserves its own spec.
- **Automatic remediation of a live session.** Per D6.
- **Multi-host launching.** This design keeps the `Launcher` seam clean and
  removes the filesystem assumption that would have blocked it, but
  `MultiHostDockerLauncher` and the `agent_url` hardcode at
  `boardfarm3_control/launcher.py:394` are separate work.
- **Authentication on the diagnostics endpoints.** They expose console
  transcripts and are therefore at least as sensitive as the existing proxy
  routes. The control plane remains the single future auth choke point, as in §8
  of the control plane design; this work adds no auth and no new trust boundary.
- **Bundle retrieval for a session whose container was already purged.**
  `meta.json` survives, so the session is still listable and explicable, but the
  bundle is subject to `BUNDLE_TTL` like any other.
