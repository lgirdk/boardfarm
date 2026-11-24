"""Browser Python shell: a ptpython REPL on the session's live objects.

The REPL runs in a thread of its own on a fresh PTY per attach, inside a
prompt_toolkit app session bound to the PTY slave; the master is bridged to
the WebSocket like a device console. The namespace outlives attaches and is
dropped with the session. It mirrors the CLI interact's ``p`` option: the
user gets ``device_manager``, ``cmdline_args`` and, with ``legacy``,
``devices``.

While a connection controls the shell it holds the whole session (``ALL``):
every job is refused and device terminals open view-only, since the code
typed here drives the consoles directly from the REPL thread.

Output is routed by thread: ``!cmd`` lines (a child process on the agent's
own fd 1) and threads the user starts write to the agent's stdout, not the PTY.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import ctypes
import fcntl
import logging
import os
import select
import struct
import sys
import termios
import threading
from argparse import Namespace
from queue import SimpleQueue
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TextIO

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_input
from prompt_toolkit.input.typeahead import get_typeahead, store_typeahead
from prompt_toolkit.output.vt100 import Vt100_Output
from ptpython.repl import embed

from boardfarm3.api.holds import ALL
from boardfarm3.api.terminal import (
    _CLOSE_INTERNAL_ERROR,
    CLOSE_SESSION_ENDED,
    USER_HEADER,
    _close,
    _not_ready,
)
from boardfarm3.api.terminal_io import Fanout, pump_ws, send_status
from boardfarm3.devices.base_devices.boardfarm_device import BoardfarmDevice
from boardfarm3.lib.repl_config import configure_repl, disable_jedi_descriptor_getattr

if TYPE_CHECKING:
    from collections.abc import Callable

    from ptpython.repl import PythonRepl

    from boardfarm3.api.execution import ExecutionQueue
    from boardfarm3.api.runtime import RuntimeContext
    from boardfarm3.api.session import Session

_log = logging.getLogger(__name__)

# Off unless the operator sets 1/true/yes/on: the endpoint is arbitrary code
# execution inside the agent. See python_shell_enabled().
PYTHON_SHELL_ENV = "BOARDFARM_PYTHON_SHELL"
CLOSE_DISABLED = 4403
CLOSE_HELD = 4409
_CLOSE_NORMAL = 1000

_READ_SIZE = 4096
# How often the PTY reader wakes to check whether the REPL must stop.
_POLL = 0.05
# How long the writer waits for room in a full PTY input queue per lap.
_WRITE_WAIT = 0.1
# Bounds how long a re-attach waits for the previous REPL thread to end.
_JOIN_TIMEOUT = 5.0
# How long a session release waits for the shell sockets to finish closing.
_CLOSE_ALL_TIMEOUT = 5.0
_DEFAULT_SIZE = (24, 80)  # rows, cols, until the client sends a resize


def shell_hold_reason(owner: str | None) -> str:
    """Return the reason of the session hold the Python shell takes.

    :param owner: user in control of the shell, or None
    :type owner: str | None
    :return: text refused jobs and device terminals report
    :rtype: str
    """
    return f"session held by Python shell (user {owner})"


def build_namespace(runtime: RuntimeContext) -> dict[str, Any]:
    """Seed a shell namespace like the CLI interact's ``embed()`` frame.

    :param runtime: the session's runtime context, with devices registered
    :type runtime: RuntimeContext
    :return: ``device_manager`` and ``cmdline_args``, plus ``devices`` when
        the session's ``legacy`` option is set
    :rtype: dict[str, Any]
    """
    namespace: dict[str, Any] = {
        "__name__": "__main__",
        "device_manager": runtime.device_manager,
        "cmdline_args": runtime.cmdline_args,
    }
    if runtime.options.legacy and runtime.device_manager is not None:
        namespace["devices"] = Namespace(
            **runtime.device_manager.get_devices_by_type(BoardfarmDevice)
        )
    return namespace


def _legacy_banner(namespace: dict[str, Any]) -> str | None:
    """Return the CLI's green ``devices`` banner, or None without ``legacy``.

    :param namespace: shell namespace built by :func:`build_namespace`
    :type namespace: dict[str, Any]
    :return: the banner line, with ANSI colour and CRLF
    :rtype: str | None
    """
    devices = namespace.get("devices")
    if devices is None:
        return None
    names = list(vars(devices).keys())
    return f"\x1b[32mUse devices.<name> to access one of {names}\x1b[0m\r\n"


class ThreadRoutedStream:
    """``sys.stdout``/``sys.stderr`` proxy routing writes by thread.

    Writes from a thread registered with :meth:`route` go to that thread's
    file (its PTY); every other thread writes to the original stream. The
    routes are shared by every instance, so a stream re-wrapped after
    someone replaced ``sys.stdout`` (pytest's capture) still routes. Threads
    the user starts from the REPL write to the original stream.
    """

    _routes: ClassVar[dict[int, TextIO]] = {}

    def __init__(self, original: TextIO) -> None:
        """Wrap *original*.

        :param original: stream unregistered threads write to
        :type original: TextIO
        """
        self._original = original

    @classmethod
    def install(cls) -> None:
        """Wrap ``sys.stdout`` and ``sys.stderr`` unless they already are.

        Idempotent, and never undone: the proxy is harmless for unregistered
        threads.
        """
        for name in ("stdout", "stderr"):
            current = getattr(sys, name)
            if not isinstance(current, cls):
                setattr(sys, name, cls(current))

    @classmethod
    def route(cls, target: TextIO) -> None:
        """Send the calling thread's writes to *target*.

        :param target: file the calling thread writes to from now on
        :type target: TextIO
        """
        cls._routes[threading.get_ident()] = target

    @classmethod
    def unroute(cls) -> None:
        """Send the calling thread's writes back to the original stream."""
        cls._routes.pop(threading.get_ident(), None)

    def _target(self) -> TextIO:
        return self._routes.get(threading.get_ident(), self._original)

    def write(self, text: str) -> int:
        """Write *text* to the calling thread's stream.

        :param text: text to write
        :type text: str
        :return: what the target's ``write`` returned
        :rtype: int
        """
        return self._target().write(text)

    def flush(self) -> None:
        """Flush the calling thread's stream."""
        self._target().flush()

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        """Delegate everything else to the calling thread's stream.

        :param name: attribute name
        :type name: str
        :return: the attribute of the calling thread's stream
        :rtype: Any
        """
        return getattr(self._target(), name)


def _exit_prompt(app: Any) -> None:  # noqa: ANN401
    """End a running prompt with EOFError, making ``repl.run()`` return.

    Runs on the prompt's own event loop; a prompt that has already finished
    is left alone (``exit`` twice raises).

    :param app: the REPL's prompt_toolkit application
    :type app: Any
    """
    if app.is_running and app.future is not None and not app.future.done():
        app.exit(exception=EOFError())


class _ReplRun:  # pylint: disable=too-many-instance-attributes
    """One attach: a PTY, the REPL thread on its slave, and the master's I/O.

    The reader thread drains the master until the REPL thread has ended and
    closed the slave, even after a detach: a statement left running must not
    block on a full PTY. It is also what ends the prompt once a stop is
    requested, polling because the prompt may only start after the request.

    A stop (detach) lets input typed before it run first: the prompt is only
    ended once nothing typed is left unread. A kill (close) drops that input.
    The master is non-blocking and no lock is ever held across a wait, so a
    full PTY input queue (a statement running) can stall nothing but the
    writer thread, and that one gives up once the master closes.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        shell: PyShell,
        rows: int,
        cols: int,
        on_output: Callable[[str], None] | None,
        on_exit: Callable[[], None] | None,
    ) -> None:
        self._shell = shell
        self._on_output = on_output
        self._on_exit = on_exit
        self.master, slave = os.openpty()
        try:
            _set_size(self.master, rows, cols)
            os.set_blocking(self.master, False)
            # No echo while a statement runs; the prompt echoes what is typed.
            attrs = termios.tcgetattr(slave)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
            # Text mode: prompt_toolkit's input wants the stream's encoding.
            self._slave_in = os.fdopen(os.dup(slave), "r", encoding="utf-8")
            self._slave_out = os.fdopen(
                os.dup(slave), "w", encoding="utf-8", errors="replace", buffering=1
            )
        except BaseException:
            for stream in ("_slave_in", "_slave_out"):
                with contextlib.suppress(AttributeError, OSError):
                    getattr(self, stream).close()
            os.close(self.master)
            raise
        finally:
            os.close(slave)
        self.stopping = threading.Event()
        # Set by close(): input still queued is dropped, the prompt ends now.
        self.killed = threading.Event()
        self.repl: PythonRepl | None = None
        self.thread_id: int | None = None
        # Guards ``running`` against interrupt(): an exception is only raised
        # into the thread while it runs a statement.
        self._state_lock = threading.Lock()
        self.running = False
        # Guards the master fd: nothing writes or resizes it once closed.
        # Held only around non-blocking calls.
        self._fd_lock = threading.Lock()
        self.master_closed = False
        self._pending: SimpleQueue[bytes | None] = SimpleQueue()
        # Input chunks queued or being written; guarded by _state_lock.
        self._unwritten = 0
        self.thread = threading.Thread(
            target=self._run_repl, name="pyshell-repl", daemon=True
        )
        self._reader = threading.Thread(
            target=self._read_master, name="pyshell-out", daemon=True
        )
        self._writer = threading.Thread(
            target=self._write_master, name="pyshell-in", daemon=True
        )
        self.thread.start()
        self._reader.start()
        self._writer.start()

    def _configure(self, repl: PythonRepl) -> None:
        """Apply the CLI settings and hook statement tracking into *repl*.

        :param repl: the REPL ``embed`` created
        :type repl: PythonRepl
        """
        configure_repl(repl)
        self.repl = repl
        # History kept in memory across attaches, for the session.
        repl.history = repl.default_buffer.history = self._shell.history
        evaluate, read = repl.run_and_show_expression, repl.read

        def run_and_show_expression(expression: str) -> None:
            with self._state_lock:
                self.running = True
            try:
                evaluate(expression)
            except KeyboardInterrupt as error:
                # Landed just outside ptpython's own handler.
                repl._handle_keyboard_interrupt(error)  # noqa: SLF001  # pylint: disable=protected-access
            finally:
                with self._state_lock:
                    # An interrupt raised but not yet delivered must not land
                    # after this statement, outside every handler.
                    self._clear_async_exc()
                    self.running = False

        def read_unless_stopping() -> str:
            if self._may_end(repl):
                raise EOFError
            return read()

        repl.run_and_show_expression = run_and_show_expression  # type: ignore[method-assign]
        repl.read = read_unless_stopping  # type: ignore[method-assign]

    def _clear_async_exc(self) -> None:
        """Drop an async exception pending on the REPL thread (call it there)."""
        if self.thread_id is not None:
            # A NULL exception clears what SetAsyncExc left pending.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(self.thread_id), None
            )

    def _input_pending(self) -> bool:
        """Tell whether typed input has not reached the prompt yet.

        :return: True while input is queued, being written, or unread on the PTY
        :rtype: bool
        """
        with self._state_lock:
            if self._unwritten:
                return True
        try:
            unread = fcntl.ioctl(self._slave_in.fileno(), termios.FIONREAD, b"\0" * 4)
        except (OSError, ValueError):
            # The slave is closed: nothing can be read any more.
            return False
        return bool(struct.unpack("i", unread)[0])

    def _may_end(self, repl: PythonRepl) -> bool:
        """Tell whether the REPL should end instead of prompting again.

        Called in the REPL thread between prompts, when no prompt reads the
        input, so the typeahead check cannot race a prompt.

        :param repl: the running REPL
        :type repl: PythonRepl
        :return: True once stopped with nothing typed left, or killed
        :rtype: bool
        """
        if self.killed.is_set():
            return True
        if not self.stopping.is_set() or self._input_pending():
            return False
        # Keys a finished prompt read past its line wait for the next one.
        keys = get_typeahead(repl.app.input)
        store_typeahead(repl.app.input, keys)
        return not keys

    def _run_repl(self) -> None:
        self.thread_id = threading.get_ident()
        ThreadRoutedStream.route(self._slave_out)
        try:
            banner = self._shell.banner
            if banner:
                self._slave_out.write(banner)
            with create_app_session(
                input=create_input(self._slave_in),
                output=Vt100_Output.from_pty(self._slave_out),
            ):
                while not self.killed.is_set():
                    try:
                        embed(
                            globals=self._shell.namespace,
                            locals=self._shell.namespace,
                            configure=self._configure,
                        )
                        break
                    except KeyboardInterrupt:
                        # An interrupt that landed between ptpython's handlers
                        # ends embed(); the namespace is intact, so prompt anew.
                        with self._state_lock:
                            self.running = False
                        continue
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            _log.exception("Python shell REPL failed")
        finally:
            ThreadRoutedStream.unroute()
            with self._state_lock:
                self.running = False
            # Closing the last slave fds makes the master read EIO.
            for stream in (self._slave_out, self._slave_in):
                with contextlib.suppress(OSError):
                    stream.close()

    def _read_master(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                if self.killed.is_set() or (
                    self.stopping.is_set() and not self._input_pending()
                ):
                    self._request_prompt_exit()
                data = self._read_once()
                if data is None:
                    break
                text = decoder.decode(data)
                if text and self._on_output is not None:
                    self._on_output(text)
        finally:
            with self._fd_lock:
                self.master_closed = True
                os.close(self.master)
            self._pending.put(None)
            # Only an ending nobody asked for: exit(), Ctrl+D at the prompt.
            if self._on_exit is not None and not self.stopping.is_set():
                self._on_exit()

    def _read_once(self) -> bytes | None:
        """Read what the master has within one poll interval.

        :return: the bytes read (empty when nothing came), or None at the end
        :rtype: bytes | None
        """
        try:
            ready, _, _ = select.select([self.master], [], [], _POLL)
            # EOF (b"") from a ready fd ends the reader like EIO does.
            return (os.read(self.master, _READ_SIZE) or None) if ready else b""
        except BlockingIOError:
            return b""
        except OSError:
            # EIO: the REPL thread ended and closed the slave.
            return None

    def _write_master(self) -> None:
        # A thread, not the event loop: while the REPL runs a statement its
        # PTY input queue fills, and the write must wait for room.
        while (data := self._pending.get()) is not None:
            try:
                self._write_all(memoryview(data))
            finally:
                with self._state_lock:
                    self._unwritten -= 1

    def _write_all(self, view: memoryview) -> None:
        """Write *view* to the master, waiting for room without holding a lock.

        Gives up when the master closes or the run is killed.

        :param view: bytes still to write
        :type view: memoryview
        """
        while view:
            if self.killed.is_set():
                return
            with self._fd_lock:
                if self.master_closed:
                    return
                try:
                    written = os.write(self.master, view)
                except BlockingIOError:
                    written = 0
                except OSError:
                    return
            if written:
                view = view[written:]
                continue
            # The fd may close meanwhile; the next lap sees master_closed.
            with contextlib.suppress(OSError, ValueError):
                select.select([], [self.master], [], _WRITE_WAIT)

    def _request_prompt_exit(self) -> None:
        repl = self.repl
        if repl is None:
            return
        app = repl.app
        loop = app.loop
        if loop is None or not app.is_running:
            # Running a statement: read() refuses to prompt once it returns.
            return
        # RuntimeError: the prompt's loop closed meanwhile.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(_exit_prompt, app)

    def write(self, data: bytes) -> None:
        """Queue *data* for the PTY input without blocking.

        :param data: raw input bytes
        :type data: bytes
        """
        if self.stopping.is_set():
            return
        with self._state_lock:
            self._unwritten += 1
        self._pending.put(data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY and redraw the prompt; never blocks.

        :param rows: terminal rows
        :type rows: int
        :param cols: terminal columns
        :type cols: int
        """
        with self._fd_lock:
            if self.master_closed:
                return
            _set_size(self.master, rows, cols)
        # The REPL thread is not the main thread, so no SIGWINCH reaches it.
        if self.repl is not None:
            self.repl.app.invalidate()

    def interrupt(self) -> bool:
        """Raise KeyboardInterrupt in the REPL thread if it runs a statement.

        :return: True when an interrupt was raised
        :rtype: bool
        """
        with self._state_lock:
            if not self.running or self.thread_id is None:
                return False
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(self.thread_id), ctypes.py_object(KeyboardInterrupt)
            )
            return True

    def stop(self) -> None:
        """Ask the REPL to end once what was typed has run; keep draining."""
        self.stopping.set()
        self._pending.put(None)

    def kill(self) -> None:
        """End the REPL as soon as it is at a prompt, dropping queued input."""
        self.killed.set()
        self.stop()
        self.interrupt()

    def join(self, timeout: float) -> bool:
        """Wait for the REPL and the reader to end.

        :param timeout: seconds to wait for each
        :type timeout: float
        :return: True when both ended
        :rtype: bool
        """
        self.thread.join(timeout)
        self._reader.join(timeout)
        return not (self.thread.is_alive() or self._reader.is_alive())


def _set_size(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class _Connection:  # pylint: disable=too-few-public-methods
    """One Python shell WebSocket."""

    def __init__(self, ws: WebSocket, owner: str | None, out: asyncio.Queue) -> None:
        self.ws = ws
        self.owner = owner
        self.out: asyncio.Queue[str | None] = out
        self.close_code = CLOSE_SESSION_ENDED
        self.close_reason = ""
        # Set once the connection has released everything it held.
        self.done = asyncio.Event()


class PyShell:  # pylint: disable=too-many-instance-attributes
    """The session's Python shell: its namespace, REPL and sockets.

    One per session, created on first open. :meth:`attach` and
    :meth:`detach` drive the REPL; :meth:`serve` runs one WebSocket. At most
    one connection controls the shell; any number view it.
    """

    def __init__(self, namespace: dict[str, Any], queue: ExecutionQueue) -> None:
        """Initialise the shell; no REPL runs until :meth:`attach`.

        :param namespace: globals the REPL runs in, kept across attaches
        :type namespace: dict[str, Any]
        :param queue: the session's execution queue, whose ``ALL`` hold it takes
        :type queue: ExecutionQueue
        """
        self.namespace = namespace
        self.banner = _legacy_banner(namespace)
        self.history = InMemoryHistory()
        self._queue = queue
        self._run: _ReplRun | None = None
        self._fanout: Fanout | None = None
        self.connections: set[_Connection] = set()
        # Whoever is stored here took the ALL hold; only it may release it.
        self.controller: _Connection | None = None
        self._holding = False
        self._release_task: asyncio.Task[None] | None = None
        self._closed = False

    # -- REPL ---------------------------------------------------------------

    @property
    def running_statement(self) -> bool:
        """Tell whether the REPL thread is executing a statement.

        Stays True after a detach until that statement returns.

        :return: True while user code runs
        :rtype: bool
        """
        return self._run is not None and self._run.running

    @property
    def repl_thread(self) -> threading.Thread | None:
        """Return the thread of the latest attach, or None before any.

        :return: the REPL thread
        :rtype: threading.Thread | None
        """
        return self._run.thread if self._run is not None else None

    def attach(
        self,
        cols: int = _DEFAULT_SIZE[1],
        rows: int = _DEFAULT_SIZE[0],
        *,
        on_output: Callable[[str], None] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> int:
        """Start the REPL on a new PTY; blocking, so call it off the event loop.

        Waits (bounded) for the previous attach's REPL to end first.

        :param cols: terminal columns
        :type cols: int
        :param rows: terminal rows
        :type rows: int
        :param on_output: called from a thread with each decoded output chunk
        :type on_output: Callable[[str], None] | None
        :param on_exit: called from a thread once the REPL and its PTY are gone,
            when the REPL ended by itself rather than on :meth:`detach`
        :type on_exit: Callable[[], None] | None
        :return: the PTY master fd
        :rtype: int
        """
        previous = self._run
        if previous is not None:
            previous.stop()
            if not previous.join(_JOIN_TIMEOUT):
                _log.warning("previous Python shell REPL did not end in time")
        logging.getLogger("parso").setLevel("INFO")
        logging.getLogger("asyncio").setLevel("INFO")
        disable_jedi_descriptor_getattr()
        ThreadRoutedStream.install()
        self._run = _ReplRun(self, rows, cols, on_output, on_exit)
        return self._run.master

    def detach(self) -> None:
        """End the REPL loop once it is at a prompt; keep the namespace.

        A running statement is not interrupted: it finishes first.
        """
        if self._run is not None:
            self._run.stop()

    def interrupt(self) -> None:
        """Raise KeyboardInterrupt in the REPL thread while it runs a statement.

        Best effort: the exception lands at the next Python bytecode, so a
        statement blocked in a C call (``time.sleep``, a socket read) is
        interrupted only once that call returns to Python.
        """
        if self._run is not None:
            self._run.interrupt()

    def write(self, data: bytes) -> None:
        """Type *data* into the REPL.

        :param data: raw input bytes
        :type data: bytes
        """
        if self._run is not None:
            self._run.write(data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the REPL's terminal.

        :param rows: terminal rows
        :type rows: int
        :param cols: terminal columns
        :type cols: int
        """
        if self._run is not None:
            self._run.resize(rows, cols)

    def close(self) -> None:
        """End the REPL, interrupting a running statement, and drop the namespace.

        Blocking (bounded), so call it off the event loop.
        """
        run = self._run
        if run is not None:
            run.kill()
            if not run.join(_JOIN_TIMEOUT):
                _log.warning(
                    "Python shell REPL thread %s (ident %s) still runs a statement"
                    " after %.0f s; leaving it behind",
                    run.thread.name,
                    run.thread.ident,
                    _JOIN_TIMEOUT,
                )
        self.namespace.clear()

    # -- WebSocket ----------------------------------------------------------

    @property
    def owner(self) -> str | None:
        """Return who controls the shell.

        :return: the controller's user, or None when nobody controls it
        :rtype: str | None
        """
        return self.controller.owner if self.controller is not None else None

    async def serve(self, ws: WebSocket, *, owner: str | None, control: bool) -> None:
        """Run one accepted shell connection until either side closes.

        :param ws: accepted WebSocket
        :type ws: WebSocket
        :param owner: user the connection belongs to, or None
        :type owner: str | None
        :param control: True when the client asked for control
        :type control: bool
        """
        if self._closed:
            await _close(ws, CLOSE_SESSION_ENDED, "session ended")
            return
        if control:
            # Atomic: a device terminal cannot take control between a check
            # and the hold. Refused, not queued, while anything is held.
            conflict = self._queue.holds.try_hold(ALL, shell_hold_reason(owner))
            if conflict is not None:
                await _close(ws, CLOSE_HELD, conflict)
                return
            self._holding = True
        if self._fanout is None:
            self._fanout = Fanout(asyncio.get_running_loop())
        conn = _Connection(ws, owner, self._fanout.subscribe())
        self.connections.add(conn)
        if control:
            self.controller = conn
        try:
            code = conn.close_code
            try:
                if control:
                    await self._start(conn)
                else:
                    await self._send_status(conn)
                await pump_ws(
                    ws,
                    conn.out,
                    (lambda data: self._input(conn, data)) if control else None,
                    (lambda r, c: self._resize(conn, r, c)) if control else None,
                )
                code = conn.close_code
            except WebSocketDisconnect:
                pass
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                # A receive error is a dead client: clean up as for a close.
                _log.exception("Python shell connection failed")
                code = _CLOSE_INTERNAL_ERROR
            finally:
                await self._leave(conn)
            await _close(ws, code, conn.close_reason)
        finally:
            conn.done.set()

    async def _start(self, conn: _Connection) -> None:
        """Wait for running jobs, then start the REPL for *conn*.

        :param conn: the new controller
        :type conn: _Connection
        """
        # The controller hears "busy"; viewers learn who controls the shell.
        await self._broadcast_status()
        await self._queue.wait_idle(frozenset({ALL}))
        if self.controller is not conn or self._closed:
            return
        loop = asyncio.get_running_loop()
        fanout = self._fanout

        def on_exit() -> None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._repl_ended)

        await anyio.to_thread.run_sync(
            lambda: self.attach(
                on_output=fanout.publish if fanout is not None else None,
                on_exit=on_exit,
            )
        )
        await self._send_status(conn)

    def _repl_ended(self) -> None:
        """Close every socket when the REPL ends by itself (``exit()``, Ctrl+D).

        Runs on the event loop.
        """
        if self._fanout is None:
            return
        for conn in self.connections:
            conn.close_code, conn.close_reason = _CLOSE_NORMAL, "Python shell exited"
        self._fanout.close()

    def _input(self, conn: _Connection, data: bytes) -> None:
        if self.controller is not conn:
            return
        if data == b"\x03" and self.running_statement:
            self.interrupt()
            return
        self.write(data)

    def _resize(self, conn: _Connection, rows: int, cols: int) -> None:
        if self.controller is conn:
            self.resize(rows, cols)

    async def _send_status(self, conn: _Connection) -> None:
        if conn is self.controller:
            state = "attached" if self._attached() else "busy"
            await send_status(conn.ws, "control", self.owner, state)
        else:
            # The terminal vocabulary has no "detached": "busy" while a new
            # controller waits for jobs, "closing" while no REPL is attached
            # (none started yet, or a detached one finishing its statement).
            if self._attached():
                state = "attached"
            elif self.controller is not None:
                state = "busy"
            else:
                state = "closing"
            await send_status(conn.ws, "view", self.owner, state)

    def _attached(self) -> bool:
        run = self._run
        return run is not None and not run.stopping.is_set()

    async def _broadcast_status(self) -> None:
        for conn in list(self.connections):
            # A client that has gone is cleaned up by its own pump.
            with contextlib.suppress(Exception):
                await self._send_status(conn)

    async def _leave(self, conn: _Connection) -> None:
        """Drop *conn*; as the controller, detach and release the hold later.

        :param conn: the closing connection
        :type conn: _Connection
        """
        self.connections.discard(conn)
        if self._fanout is not None:
            self._fanout.unsubscribe(conn.out)
        if self.controller is not conn:
            return
        self.controller = None
        # Shielded: TestClient (and a cancelled task) cancels the endpoint on
        # disconnect, and the hold must still go.
        with anyio.CancelScope(shield=True):
            self.detach()
            self._release_task = asyncio.get_running_loop().create_task(
                self._release_when_ended(self._run)
            )
            await self._broadcast_status()

    async def _release_when_ended(self, run: _ReplRun | None) -> None:
        """Release the ``ALL`` hold once the detached REPL thread has ended.

        Not on ``running_statement``: a line typed just before the detach may
        not have started yet, and the thread ends only after it has run.

        :param run: the attach being detached, or None when none started
        :type run: _ReplRun | None
        """
        while run is not None and run.thread.is_alive():  # noqa: ASYNC110
            await asyncio.sleep(_POLL)
        self._release_hold()
        await self._broadcast_status()

    def _release_hold(self) -> None:
        if self._holding and self.controller is None:
            self._holding = False
            self._queue.holds.release(ALL)

    async def close_all(self, code: int = CLOSE_SESSION_ENDED) -> None:
        """Close every shell socket with *code*, end the REPL, drop the namespace.

        Waits a bounded time for each connection, so a session release never
        hangs on the shell.

        :param code: WebSocket close code sent to every client
        :type code: int
        """
        self._closed = True
        pending = []
        for conn in self.connections:
            conn.close_code = code
            pending.append(conn.done)
        if self._fanout is not None:
            # The None sentinel ends every pump.
            self._fanout.close()
        with anyio.move_on_after(_CLOSE_ALL_TIMEOUT) as waited:
            for done in pending:
                await done.wait()
        if waited.cancelled_caught:
            _log.warning("Python shell sockets did not close in time")
        if self._release_task is not None:
            self._release_task.cancel()
        await anyio.to_thread.run_sync(self.close)
        self.controller = None
        self._release_hold()


_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})


def python_shell_enabled() -> bool:
    """Tell whether the operator enabled the Python shell.

    Opt-in: only ``BOARDFARM_PYTHON_SHELL`` set to ``1``, ``true``, ``yes`` or
    ``on`` (any case, surrounding blanks ignored) enables it; unset or anything
    else leaves it disabled.

    :return: True when the shell is enabled
    :rtype: bool
    """
    value = os.environ.get(PYTHON_SHELL_ENV, "")
    return value.strip().lower() in _ENABLED_VALUES


pyshell_router = APIRouter()


@pyshell_router.websocket("/python")
async def python_shell(
    ws: WebSocket, mode: Literal["control", "view"] = "view"
) -> None:
    """Open the session's Python shell: a ptpython REPL on its live objects.

    :param ws: the WebSocket
    :type ws: WebSocket
    :param mode: ``control`` to type (holds the whole session), ``view`` to watch
    :type mode: Literal["control", "view"]
    """
    await ws.accept()
    if not python_shell_enabled():
        await _close(ws, CLOSE_DISABLED, "Python shell disabled")
        return
    session: Session = ws.app.state.session
    refusal = _not_ready(session)
    if refusal is not None:
        await _close(ws, *refusal)
        return
    if session.pyshell is None:
        session.pyshell = PyShell(build_namespace(session.runtime), session.queue)
    await session.pyshell.serve(
        ws, owner=ws.headers.get(USER_HEADER), control=mode == "control"
    )
