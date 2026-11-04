"""Shared-console terminal: a WebSocket onto a device's existing pexpect console.

Any number of connections may watch a console; at most one controls it. The
controller holds the device, so API jobs on it are refused (409) until the
controller leaves. While it is attached, a reader thread drains the console so
its output reaches every viewer through the console's raw tee, and a writer
thread types its input.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import select
import threading
import time
from queue import SimpleQueue
from typing import TYPE_CHECKING, Any, Literal

import anyio
import pexpect
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from boardfarm3.api.errors import scrub
from boardfarm3.api.modes import INTERACT
from boardfarm3.api.routers import require_device_manager
from boardfarm3.api.terminal_io import Fanout, bound_reason, pump_ws, send_status
from boardfarm3.templates.cpe import CPE

if TYPE_CHECKING:
    from collections.abc import Callable

    from boardfarm3.api.execution import ExecutionQueue
    from boardfarm3.api.session import Session

_log = logging.getLogger(__name__)

USER_HEADER = "X-Boardfarm-User"

# Application close codes, shared with the control plane and the portal.
CLOSE_NOT_FOUND = 4404
CLOSE_SESSION_ENDED = 4410
CLOSE_NOT_READY = 4423
CLOSE_TOO_MANY = 4429
_CLOSE_INTERNAL_ERROR = 1011

_READ_SIZE = 4096
# Bounds how long stopping the reader takes: it checks its stop flag this often.
_READ_TIMEOUT = 0.2
# How long the writer waits for room in a full console per lap; it checks its
# stop flag between laps.
_WRITE_WAIT = 0.1
# How often a detach checks whether the threads have ended.
_STOP_POLL = 0.02
# A detach still waiting after this long logs a warning (and keeps waiting).
_STOP_WARN_AFTER = 2.0
# How long a session release waits for its terminals to finish closing.
_CLOSE_ALL_TIMEOUT = 5.0

SSH_CONNECTION_TYPES = frozenset({"ssh_connection", "authenticated_ssh"})
MAX_SSH_TERMINALS_ENV = "BOARDFARM_MAX_SSH_TERMINALS"
_DEFAULT_MAX_SSH_TERMINALS = 5


def _hold_reason(device: str, owner: str | None) -> str:
    return f"device {device} held by terminal (user {owner})"


class _Reader:
    """Daemon thread draining a console while a human controls it.

    It discards what it reads: the console's raw tee has already published
    it to the viewers and the console log, and an empty pexpect buffer means
    the next ``expect()`` after the terminal starts on fresh output.
    """

    def __init__(self, console: Any, on_eof: Callable[[], None]) -> None:  # noqa: ANN401
        self._console = console
        self._on_eof = on_eof
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"terminal-{getattr(console, 'name', 'console')}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._console.read_nonblocking(_READ_SIZE, timeout=_READ_TIMEOUT)
            except pexpect.TIMEOUT:  # noqa: PERF203
                continue
            except pexpect.EOF:
                self._on_eof()
                return
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                # A closed fd and the like: the console is gone, same as EOF.
                _log.exception("terminal reader stopped on a console error")
                self._on_eof()
                return

    def stop(self) -> None:
        """Ask the thread to stop after its current read."""
        self._stop.set()

    def is_alive(self) -> bool:
        """Tell whether the thread still runs.

        :return: True until the thread has ended
        :rtype: bool
        """
        return self._thread.is_alive()


class _Writer:
    """Daemon thread typing the controller's input into the console.

    Writes straight to the PTY: ``spawn.send`` sleeps ``delaybeforesend``
    (50 ms) per call, which would stall the event loop on every keystroke and
    make a paste crawl, and it wants text, which a frame boundary can split
    inside a multibyte character.

    The console fd is non-blocking while the writer runs, so a console that
    does not drain (a big paste into a slow serial line) never pins the thread
    in ``os.write``: it waits for room in short ``select`` laps and checks its
    stop flag between them. Stopping drops whatever input is still queued.
    """

    def __init__(self, console: Any) -> None:  # noqa: ANN401
        self._fd: int = console.child_fd
        self._stop = threading.Event()
        # None wakes the thread on stop; FIFO keeps keystrokes in order.
        self._pending: SimpleQueue[bytes | None] = SimpleQueue()
        self._flags = _set_nonblocking(self._fd)
        self._thread = threading.Thread(
            target=self._run,
            name=f"terminal-in-{getattr(console, 'name', 'console')}",
            daemon=True,
        )
        self._thread.start()

    def put(self, data: bytes) -> None:
        """Queue *data* for the console without blocking.

        :param data: raw input bytes
        :type data: bytes
        """
        if not self._stop.is_set():
            self._pending.put(data)

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._pending.get()
                if data is None or not self._write_all(memoryview(data)):
                    return
        finally:
            _restore_flags(self._fd, self._flags)

    def _write_all(self, view: memoryview) -> bool:
        """Write *view* to the console, waiting for room in short laps.

        :param view: bytes still to write
        :type view: memoryview
        :return: False when the writer must end (stopped or console gone)
        :rtype: bool
        """
        while view:
            if self._stop.is_set():
                return False
            try:
                written = os.write(self._fd, view)
            except BlockingIOError:
                written = 0
            except OSError:
                # The console is gone; the reader reports it as EOF.
                _log.exception("terminal writer stopped on a console error")
                return False
            if written:
                view = view[written:]
                continue
            # The fd may close meanwhile; the next lap's write reports it.
            with contextlib.suppress(OSError, ValueError):
                select.select([], [self._fd], [], _WRITE_WAIT)
        return True

    def stop(self) -> None:
        """Ask the thread to stop now, dropping the input still queued."""
        self._stop.set()
        self._pending.put(None)

    def is_alive(self) -> bool:
        """Tell whether the thread still runs.

        :return: True until the thread has ended
        :rtype: bool
        """
        return self._thread.is_alive()


def _set_nonblocking(fd: int) -> int | None:
    """Make *fd* non-blocking.

    :param fd: file descriptor
    :type fd: int
    :return: its previous flags, or None when they could not be read
    :rtype: int | None
    """
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except OSError:
        return None
    return flags


def _restore_flags(fd: int, flags: int | None) -> None:
    """Give *fd* back the *flags* :func:`_set_nonblocking` saved.

    :param fd: file descriptor
    :type fd: int
    :param flags: saved flags, or None to leave the fd alone
    :type flags: int | None
    """
    if flags is not None:
        with contextlib.suppress(OSError):
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)


async def _wait_ended(thread: _Reader | _Writer, what: str) -> None:
    """Poll, without blocking the loop, until *thread* has ended.

    :param thread: the stopped reader or writer
    :type thread: _Reader | _Writer
    :param what: name used in the slow-stop warning
    :type what: str
    """
    started = time.monotonic()
    warned = False
    while thread.is_alive():
        if not warned and time.monotonic() - started > _STOP_WARN_AFTER:
            _log.warning(
                "terminal %s still running %.0f s after stop", what, _STOP_WARN_AFTER
            )
            warned = True
        await anyio.sleep(_STOP_POLL)


class _Attachment:  # pylint: disable=too-few-public-methods
    """The reader and writer threads of an attached controller."""

    def __init__(self, console: Any, on_eof: Callable[[], None]) -> None:  # noqa: ANN401
        self.reader = _Reader(console, on_eof)
        self.writer = _Writer(console)

    async def stop(self) -> None:
        """Stop the writer, then the reader; return once both have ended.

        The writer goes first and drops its queued input, so nothing types
        into the console once this returns. Never blocks the event loop.
        """
        self.writer.stop()
        await _wait_ended(self.writer, "writer")
        self.reader.stop()
        await _wait_ended(self.reader, "reader")


class _Connection:  # pylint: disable=too-few-public-methods
    """One terminal WebSocket."""

    def __init__(self, ws: WebSocket, owner: str | None, out: asyncio.Queue) -> None:
        self.ws = ws
        self.owner = owner
        self.out: asyncio.Queue[str | None] = out
        self.close_code = CLOSE_SESSION_ENDED
        # Why this connection was refused control, sent with every status.
        self.held_by: str | None = None
        # Set once the connection has released everything it held.
        self.done = asyncio.Event()


class _ConsoleTerminal:
    """Shared state of every connection on one (device, console)."""

    def __init__(self, device: str, console: Any) -> None:  # noqa: ANN401
        self.device = device
        self.console = console
        self.fanout = Fanout(asyncio.get_running_loop())
        self.connections: set[_Connection] = set()
        # The controller is identified by its connection object: whoever is
        # stored here owns the device hold, and only it may release it.
        self.controller: _Connection | None = None
        self.attachment: _Attachment | None = None
        # Set by the reader thread when the console reaches EOF.
        self.dead = False
        console.add_raw_listener(self.fanout.publish)

    @property
    def owner(self) -> str | None:
        """Return who is in control of the console.

        :return: the controller's user, or None when nobody controls it
        :rtype: str | None
        """
        return self.controller.owner if self.controller is not None else None

    def mark_dead(self) -> None:
        """Record the console's EOF and end every pump on it (reader thread)."""
        self.dead = True
        self.fanout.close()

    async def send_status(self, conn: _Connection) -> None:
        """Tell *conn* its role, who controls the console and the state.

        :param conn: connection to tell
        :type conn: _Connection
        """
        if conn is self.controller:
            state = "attached" if self.attachment is not None else "busy"
            await send_status(conn.ws, "control", self.owner, state)
        else:
            await send_status(
                conn.ws, "view", self.owner, "attached", held_by=conn.held_by
            )

    async def broadcast_status(self) -> None:
        """Send every connection its status; used when the controller changes."""
        for conn in list(self.connections):
            # A client that has gone is cleaned up by its own pump.
            with contextlib.suppress(Exception):
                await self.send_status(conn)

    def detach(self) -> None:
        """Stop teeing the console into this terminal's fan-out."""
        self.console.remove_raw_listener(self.fanout.publish)

    def send_input(self, conn: _Connection, data: bytes) -> None:
        """Type *data* into the console if *conn* is the attached controller.

        A demoted controller keeps its pump; its input is dropped here.

        :param conn: connection the input came from
        :type conn: _Connection
        :param data: raw input bytes
        :type data: bytes
        """
        if self.controller is conn and self.attachment is not None:
            self.attachment.writer.put(data)

    def resize(self, conn: _Connection, rows: int, cols: int) -> None:
        """Resize the console's PTY if *conn* is the attached controller.

        :param conn: connection the resize came from
        :type conn: _Connection
        :param rows: terminal rows
        :type rows: int
        :param cols: terminal columns
        :type cols: int
        """
        if self.controller is conn and self.attachment is not None:
            self.console.setwinsize(rows, cols)


class _SshTerminal:  # pylint: disable=too-many-instance-attributes
    """One private ssh console and the socket that controls it."""

    def __init__(self, ws: WebSocket, device: str, owner: str | None) -> None:
        self.ws = ws
        self.device = device
        self.owner = owner
        self.fanout = Fanout(asyncio.get_running_loop())
        self.out = self.fanout.subscribe()
        self.close_code = CLOSE_SESSION_ENDED
        self.console: Any = None
        self.attachment: _Attachment | None = None
        # Set once the terminal has closed its console.
        self.done = asyncio.Event()

    def attach(self, console: Any) -> None:  # noqa: ANN401
        """Tee *console* into the fan-out and start its reader and writer.

        :param console: the freshly opened, logged-in console
        :type console: Any
        """
        self.console = console
        console.add_raw_listener(self.fanout.publish)
        self.attachment = _Attachment(console, on_eof=self.fanout.close)

    def send_input(self, data: bytes) -> None:
        """Type *data* into the console.

        :param data: raw input bytes
        :type data: bytes
        """
        if self.attachment is not None:
            self.attachment.writer.put(data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the console's PTY.

        :param rows: terminal rows
        :type rows: int
        :param cols: terminal columns
        :type cols: int
        """
        if self.console is not None:
            self.console.setwinsize(rows, cols)

    async def close(self) -> None:
        """Stop the threads, then close the console off the event loop."""
        if self.attachment is not None:
            await self.attachment.stop()
            self.attachment = None
        if self.console is not None:
            self.console.remove_raw_listener(self.fanout.publish)
            await anyio.to_thread.run_sync(self.console.close)


class TerminalRegistry:
    """Every shared-console terminal of one session."""

    def __init__(self, queue: ExecutionQueue) -> None:
        """Initialise an empty registry.

        :param queue: the session's execution queue, whose holds it takes
        :type queue: ExecutionQueue
        """
        self._queue = queue
        self._terminals: dict[tuple[str, str], _ConsoleTerminal] = {}
        self._ssh: set[_SshTerminal] = set()
        # Per device, never reused for the session's lifetime.
        self._ssh_counter: dict[str, int] = {}
        self._closed = False

    @property
    def closed(self) -> bool:
        """Tell whether the session release has closed the registry.

        :return: True once :meth:`close_all` has run
        :rtype: bool
        """
        return self._closed

    async def close_all(self, code: int = CLOSE_SESSION_ENDED) -> None:
        """Close every terminal socket with *code* and release their holds.

        New connections are refused (4410) from here on. Waits a bounded time
        for each connection to finish, then force-releases what is left, so
        a session release never hangs on a terminal.

        :param code: WebSocket close code sent to every client
        :type code: int
        """
        self._closed = True
        pending: list[asyncio.Event] = []
        for term in list(self._terminals.values()):
            for conn in term.connections:
                conn.close_code = code
                pending.append(conn.done)
            # The None sentinel ends every pump on this console.
            term.fanout.close()
        for ssh in list(self._ssh):
            ssh.close_code = code
            pending.append(ssh.done)
            ssh.fanout.close()
        with anyio.move_on_after(_CLOSE_ALL_TIMEOUT) as waited:
            for done in pending:
                await done.wait()
        if waited.cancelled_caught:
            _log.warning("terminals did not close in time; releasing anyway")
        for term in list(self._terminals.values()):
            if term.attachment is not None:
                # Shielded: the release must not leave the hold half-done.
                with anyio.CancelScope(shield=True):
                    await term.attachment.stop()
                term.attachment = None
            term.controller = None
            self._release_device(term.device)
            term.detach()
        self._terminals.clear()

    async def serve(  # noqa: PLR0913
        self,
        ws: WebSocket,
        device: str,
        console_name: str,
        console: Any,  # noqa: ANN401
        *,
        owner: str | None,
        control: bool,
    ) -> None:
        """Run one accepted terminal connection until either side closes.

        :param ws: accepted WebSocket
        :type ws: WebSocket
        :param device: device name
        :type device: str
        :param console_name: console name on that device
        :type console_name: str
        :param console: the device's pexpect console
        :type console: Any
        :param owner: user the connection belongs to, or None
        :type owner: str | None
        :param control: True when the client asked for control
        :type control: bool
        """
        key = (device, console_name)
        term = self._terminals.get(key)
        if term is not None and term.dead:
            # Its console hit EOF; the entry goes when its last pump ends.
            await _close(ws, CLOSE_SESSION_ENDED, "console closed")
            return
        if term is None:
            term = self._terminals[key] = _ConsoleTerminal(device, console)
        conn = _Connection(ws, owner, term.fanout.subscribe())
        term.connections.add(conn)
        code = conn.close_code
        try:
            try:
                controlling = await self._attach(term, conn, control=control)
                await pump_ws(
                    ws,
                    conn.out,
                    (lambda data: term.send_input(conn, data)) if controlling else None,
                    (lambda r, c: term.resize(conn, r, c)) if controlling else None,
                )
                code = conn.close_code
            except WebSocketDisconnect:
                pass
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                # A receive error is a dead client: clean up as for a close.
                _log.exception("terminal %s/%s failed", device, console_name)
                code = _CLOSE_INTERNAL_ERROR
            finally:
                await self._detach(key, term, conn)
            await _close(ws, code)
        finally:
            conn.done.set()

    async def _attach(  # pylint: disable=too-many-return-statements
        self, term: _ConsoleTerminal, conn: _Connection, *, control: bool
    ) -> bool:
        """Make *conn* a viewer or the controller; return True for control.

        :param term: the console's terminal state
        :type term: _ConsoleTerminal
        :param conn: the new connection
        :type conn: _Connection
        :param control: True when the client asked for control
        :type control: bool
        :return: True when the connection may send input
        :rtype: bool
        """
        holds = self._queue.holds
        if not control:
            await term.send_status(conn)
            return False
        # Taken (or re-labelled on hand-over) before waiting, so no new job
        # can start on the device while the running one drains. One atomic
        # call: the Python shell cannot take ALL between a check and the hold.
        conflict = holds.try_hold(term.device, _hold_reason(term.device, conn.owner))
        if conflict is not None:
            # The Python shell holds the whole session: watch only.
            conn.held_by = conflict
            await term.send_status(conn)
            return False
        term.controller = conn
        # The new controller gets "busy" (or "attached" on a hand-over, the
        # threads already run); everyone else learns who controls the console,
        # including a demoted controller, which stays connected as a viewer.
        await term.broadcast_status()
        await self._queue.wait_idle(frozenset({term.device}))
        if term.controller is conn and term.attachment is None:
            term.attachment = _Attachment(term.console, on_eof=term.mark_dead)
            await term.send_status(conn)
        # Handed over while waiting: already told "view" by the broadcast.
        return True

    async def _detach(
        self, key: tuple[str, str], term: _ConsoleTerminal, conn: _Connection
    ) -> None:
        """Drop *conn*; release the hold if it was the current controller.

        The console itself is left as the user left it: no Ctrl+C, no newline.

        :param key: (device, console) key of *term*
        :type key: tuple[str, str]
        :param term: the console's terminal state
        :type term: _ConsoleTerminal
        :param conn: the closing connection
        :type conn: _Connection
        """
        term.connections.discard(conn)
        term.fanout.unsubscribe(conn.out)
        if term.controller is conn:
            term.controller = None
            attachment, term.attachment = term.attachment, None
            # Shielded: TestClient (and a cancelled task) cancels the endpoint
            # on disconnect, and the hold must still go.
            with anyio.CancelScope(shield=True):
                try:
                    if attachment is not None:
                        # Polls until the writer (then the reader) has ended:
                        # nothing may read or write the console once a job
                        # may run on it.
                        await attachment.stop()
                finally:
                    self._release_device(term.device)
                await term.broadcast_status()
        if not term.connections and self._terminals.get(key) is term:
            term.detach()
            del self._terminals[key]

    async def serve_ssh(
        self,
        ws: WebSocket,
        device: str,
        target: Any,  # noqa: ANN401
        *,
        owner: str | None,
    ) -> None:
        """Open a private ssh console for *ws* and pump it until either side ends.

        Takes no hold: the console is independent of the device's shared one.

        :param ws: accepted WebSocket
        :type ws: WebSocket
        :param device: device name
        :type device: str
        :param target: the device, offering ``open_extra_console``
        :type target: Any
        :param owner: user the connection belongs to, or None
        :type owner: str | None
        """
        limit = max_ssh_terminals()
        if limit == 0:
            await _close(ws, CLOSE_NOT_FOUND, "ssh terminals are disabled")
            return
        open_here = sum(1 for term in self._ssh if term.device == device)
        if open_here >= limit:
            await _close(ws, CLOSE_TOO_MANY, "too many ssh terminals")
            return
        number = self._ssh_counter[device] = self._ssh_counter.get(device, 0) + 1
        term = _SshTerminal(ws, device, owner)
        self._ssh.add(term)
        try:
            await self._run_ssh(term, device, target, number)
        finally:
            with anyio.CancelScope(shield=True):
                await term.close()
            self._ssh.discard(term)
            term.done.set()

    async def _run_ssh(
        self,
        term: _SshTerminal,
        device: str,
        target: Any,  # noqa: ANN401
        number: int,
    ) -> None:
        """Log in, then pump; close the socket with the right code.

        :param term: the terminal's state
        :type term: _SshTerminal
        :param device: device name
        :type device: str
        :param target: the device
        :type target: Any
        :param number: this terminal's number on the device
        :type number: int
        """
        ws = term.ws
        code = CLOSE_SESSION_ENDED
        try:
            await send_status(ws, "control", term.owner, "busy")
            login = asyncio.ensure_future(
                asyncio.to_thread(target.open_extra_console, f"{device}.term{number}")
            )
            try:
                console = await asyncio.shield(login)
            except asyncio.CancelledError:
                # The client went mid-login: close what the login yields.
                login.add_done_callback(_close_login_result)
                raise
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                reason = scrub(str(error)) or type(error).__name__
                await _close(ws, CLOSE_NOT_FOUND, reason)
                return
            term.attach(console)
            if self._closed:
                # The session was released while the login ran.
                await _close(ws, CLOSE_SESSION_ENDED, "session ended")
                return
            await send_status(ws, "control", term.owner, "attached")
            # The login consumed the first prompt before the tee existed.
            term.send_input(b"\n")
            await pump_ws(ws, term.out, term.send_input, term.resize)
            code = term.close_code
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            _log.exception("ssh terminal on %s failed", device)
            code = _CLOSE_INTERNAL_ERROR
        await _close(ws, code)

    def _release_device(self, device: str) -> None:
        # Another console of the same device may still be controlled.
        for term in self._terminals.values():
            if term.device == device and term.controller is not None:
                self._queue.holds.hold(
                    device, _hold_reason(device, term.controller.owner)
                )
                return
        self._queue.holds.release(device)


async def _close(ws: WebSocket, code: int, reason: str = "") -> None:
    """Close *ws* unless either side already has.

    The reason is cut to the 123 UTF-8 bytes a close frame allows.

    :param ws: terminal WebSocket
    :type ws: WebSocket
    :param code: close code
    :type code: int
    :param reason: close reason
    :type reason: str
    """
    if (
        ws.application_state is WebSocketState.CONNECTED
        and ws.client_state is WebSocketState.CONNECTED
    ):
        # The client may vanish between the check and the send.
        with contextlib.suppress(Exception):
            await ws.close(code, bound_reason(reason))


def _find_console(session: Session, device: str, console: str) -> Any:  # noqa: ANN401
    """Return the named console of a device, or None when either is unknown.

    :param session: READY interact session
    :type session: Session
    :param device: device name
    :type device: str
    :param console: console name
    :type console: str
    :return: the pexpect console, or None
    :rtype: Any
    """
    try:
        found = require_device_manager(session).get_device_by_name(device)
        return found.get_interactive_consoles().get(console)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        # DeviceNotFound, or a device without interactive consoles.
        return None


def _not_ready(  # pylint: disable=too-many-return-statements
    session: Session,
) -> tuple[int, str] | None:
    """Tell why a terminal may not attach to the session yet.

    :param session: the agent's session
    :type session: Session
    :return: ``(close code, reason)``, or None when the session is ready
    :rtype: tuple[int, str] | None
    """
    if session.terminals.closed:
        return CLOSE_SESSION_ENDED, "session ended"
    if session.state.value != "ready" or session.mode != INTERACT:
        return CLOSE_NOT_READY, f"session is {session.state.value}"
    try:
        require_device_manager(session)
    except HTTPException:
        return CLOSE_NOT_READY, "session has no devices"
    return None


def max_ssh_terminals() -> int:
    """Return how many ssh terminals a device may have open at once.

    ``BOARDFARM_MAX_SSH_TERMINALS`` is an int >= 0; 0 disables ssh terminals.
    Anything else falls back to the default, with a warning.

    :return: the limit from the environment, or the default
    :rtype: int
    """
    raw = os.environ.get(MAX_SSH_TERMINALS_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_MAX_SSH_TERMINALS
    try:
        value = int(raw.strip())
    except ValueError:
        value = -1
    if value < 0:
        _log.warning(
            "invalid %s=%r; using %d",
            MAX_SSH_TERMINALS_ENV,
            raw,
            _DEFAULT_MAX_SSH_TERMINALS,
        )
        return _DEFAULT_MAX_SSH_TERMINALS
    return value


def _close_login_result(future: asyncio.Future[Any]) -> None:
    """Close the console of a login nobody waits for any more.

    :param future: the finished login
    :type future: asyncio.Future[Any]
    """
    if future.cancelled() or future.exception() is not None:
        return
    threading.Thread(target=future.result().close, daemon=True).start()


def ssh_terminal_eligible(  # pylint: disable=too-many-return-statements
    device: Any,  # noqa: ANN401
) -> bool:
    """Tell whether a device may open extra ssh terminals.

    :param device: a registered device
    :type device: Any
    :return: True for a non-CPE device on an ssh connection with a console,
        while ssh terminals are enabled
    :rtype: bool
    """
    if isinstance(device, CPE) or not hasattr(device, "open_extra_console"):
        return False
    if max_ssh_terminals() == 0:
        return False
    config = getattr(device, "_config", None)
    if not isinstance(config, dict):
        return False
    if config.get("connection_type") not in SSH_CONNECTION_TYPES:
        return False
    try:
        return bool(device.get_interactive_consoles())
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return False


def _resolve(  # pylint: disable=too-many-return-statements
    session: Session, device: str, console: str
) -> tuple[Any, tuple[int, str] | None]:
    """Find the console a terminal attaches to, or why it may not attach.

    :param session: the agent's session
    :type session: Session
    :param device: device name
    :type device: str
    :param console: console name
    :type console: str
    :return: ``(console, None)``, or ``(None, (close code, reason))``
    :rtype: tuple[Any, tuple[int, str] | None]
    """
    refusal = _not_ready(session)
    if refusal is not None:
        return None, refusal
    spawn = _find_console(session, device, console)
    if spawn is None:
        return None, (CLOSE_NOT_FOUND, f"no console {console!r} on {device}")
    if not _alive(spawn):
        # Attaching would report "attached" on a console nobody can drive.
        return None, (CLOSE_SESSION_ENDED, f"console {console!r} on {device} closed")
    return spawn, None


def _alive(console: Any) -> bool:  # noqa: ANN401
    """Tell whether a console's process still runs; True when it cannot tell.

    :param console: pexpect console
    :type console: Any
    :return: False only when the console reports it has exited
    :rtype: bool
    """
    try:
        return bool(console.isalive())
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return True


terminal_router = APIRouter()


@terminal_router.websocket("/devices/{device}/consoles/{console}/terminal")
async def terminal(
    ws: WebSocket,
    device: str,
    console: str,
    mode: Literal["control", "view"] = "view",
) -> None:
    """Attach a browser terminal to a device's existing pexpect console.

    :param ws: the WebSocket
    :type ws: WebSocket
    :param device: device name
    :type device: str
    :param console: console name on the device
    :type console: str
    :param mode: ``control`` to type, ``view`` to watch
    :type mode: Literal["control", "view"]
    """
    await ws.accept()
    session: Session = ws.app.state.session
    spawn, refusal = _resolve(session, device, console)
    if refusal is not None:
        await _close(ws, *refusal)
        return
    await session.terminals.serve(
        ws,
        device,
        console,
        spawn,
        owner=ws.headers.get(USER_HEADER),
        control=mode == "control",
    )


@terminal_router.websocket("/devices/{device}/ssh-terminal")
async def ssh_terminal(ws: WebSocket, device: str) -> None:
    """Open a private ssh terminal: a new connection to the device.

    :param ws: the WebSocket
    :type ws: WebSocket
    :param device: device name
    :type device: str
    """
    await ws.accept()
    session: Session = ws.app.state.session
    refusal = _not_ready(session)
    if refusal is not None:
        await _close(ws, *refusal)
        return
    try:
        target = require_device_manager(session).get_device_by_name(device)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        await _close(ws, CLOSE_NOT_FOUND, f"no device {device!r}")
        return
    if not ssh_terminal_eligible(target):
        await _close(ws, CLOSE_NOT_FOUND, f"{device} offers no ssh terminals")
        return
    await session.terminals.serve_ssh(
        ws, device, target, owner=ws.headers.get(USER_HEADER)
    )
