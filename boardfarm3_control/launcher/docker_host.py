"""One lab host's Docker endpoint: lazy client, own thread pool, timeouts, breaker."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

from boardfarm3_control.errors import HostUnreachable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from boardfarm3_control.models import HostSpec

_log = logging.getLogger(__name__)
_T = TypeVar("_T")

DEFAULT_WORKERS = 4
DEFAULT_TIMEOUT = 10.0
FAILURE_THRESHOLD = 2
# Added to every per-call limit so docker-py's own timeout normally fires first.
_OUTER_MARGIN = 2.0


def is_transport_error(exc: BaseException) -> bool:
    """Tell a host that did not answer apart from a daemon that answered.

    ``docker.errors.APIError`` subclasses ``requests.HTTPError`` and therefore
    ``OSError``, so it is ruled out before the transport check.

    :param exc: exception raised by a Docker call
    :type exc: BaseException
    :return: True when the host did not answer (refused, reset, timed out)
    :rtype: bool
    """
    import docker.errors  # noqa: PLC0415

    if isinstance(exc, docker.errors.APIError):
        return False
    return isinstance(exc, (docker.errors.DockerException, OSError, TimeoutError))


def _is_api_error(exc: BaseException) -> bool:
    import docker.errors  # noqa: PLC0415

    return isinstance(exc, docker.errors.APIError)


def _default_client_factory(spec: HostSpec, timeout: float) -> Any:  # noqa: ANN401
    import docker  # noqa: PLC0415

    if spec.docker_url is None:
        return docker.from_env(timeout=int(timeout))
    kwargs: dict[str, Any] = {"base_url": spec.docker_url, "timeout": int(timeout)}
    if spec.docker_url.startswith("ssh://"):
        kwargs["use_ssh_client"] = True
    if spec.tls:
        import docker.tls  # noqa: PLC0415
        kwargs["tls"] = docker.tls.TLSConfig(
            client_cert=(spec.tls["cert"], spec.tls["key"]),
            ca_cert=spec.tls["ca"],
            verify=True,
        )
    return docker.DockerClient(**kwargs)


def _names_registry(image: str) -> bool:
    # Docker's own rule: the first path component is a registry host when it
    # contains "." or ":" or is "localhost".
    first, sep, _ = image.partition("/")
    return bool(sep) and ("." in first or ":" in first or first == "localhost")


class DockerHost:
    """One lab host's Docker daemon, isolated from every other host.

    Every Docker call for the host runs on the host's own thread pool, so a
    host that stops answering can only exhaust its own threads. The docker-py
    client is created lazily inside that pool, because constructing one
    already talks to the daemon (API version negotiation).
    """

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        spec: HostSpec,
        *,
        default_registry: str | None = None,
        client_factory: Callable[[HostSpec, float], Any] | None = None,
        workers: int = DEFAULT_WORKERS,
        timeout: float = DEFAULT_TIMEOUT,
        failure_threshold: int = FAILURE_THRESHOLD,
    ) -> None:
        """Describe one host; no network traffic happens here.

        :param name: host name that inventories use in ``agent_host``
        :type name: str
        :param spec: the host's record from hosts.json
        :type spec: HostSpec
        :param default_registry: ``BOARDFARM_DEFAULT_REGISTRY``, if set
        :type default_registry: str | None
        :param client_factory: builds the docker-py client; tests inject fakes
        :type client_factory: Callable[[HostSpec, float], Any] | None
        :param workers: size of this host's thread pool
        :type workers: int
        :param timeout: per-call Docker timeout in seconds
        :type timeout: float
        :param failure_threshold: consecutive transport failures that open the breaker
        :type failure_threshold: int
        """
        self.name = name
        self.spec = spec
        self.timeout = timeout
        self.last_error: str | None = None
        self.last_ok_at: float | None = None
        self.conflicts = 0
        self._default_registry = default_registry or None
        self._client_factory = client_factory or _default_client_factory
        self._client: Any = None
        self._client_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=f"docker-{name}",
        )
        # Pulls and archive downloads run for minutes; on their own pool they
        # can never starve the pings, lists and stops of the same host.
        self._long_executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=f"docker-{name}-long",
        )
        self._flights: dict[str, asyncio.Future[Any]] = {}
        self._failure_threshold = failure_threshold
        self._failures = 0

    @property
    def is_down(self) -> bool:
        """Report whether the circuit breaker is open.

        :return: True after ``failure_threshold`` consecutive transport failures
        :rtype: bool
        """
        return self._failures >= self._failure_threshold

    @property
    def advertise_addr(self) -> str:
        """Return the address control uses to reach agents on this host.

        :return: the host's advertise address
        :rtype: str
        """
        return self.spec.effective_advertise_addr()

    @property
    def effective_registry(self) -> str | None:
        """Return the registry prepended to relative profile images.

        :return: the host's ``registry`` (``""`` means none), else the default
        :rtype: str | None
        """
        if self.spec.registry is not None:
            return self.spec.registry or None
        return self._default_registry

    def update_spec(self, spec: HostSpec) -> None:
        """Swap in a record that differs only in drain, registry or default.

        :param spec: the new record
        :type spec: HostSpec
        """
        self.spec = spec

    def agent_url(self, port: int) -> str:
        """Build the URL of an agent published on *port*.

        :param port: Docker-assigned host port
        :type port: int
        :return: base URL for the agent
        :rtype: str
        """
        return f"http://{self.advertise_addr}:{port}"

    def image_ref(self, image: str) -> str:
        """Resolve a profile image against this host's registry.

        :param image: profile image, relative or naming its own registry
        :type image: str
        :return: the reference this host pulls and runs
        :rtype: str
        """
        registry = self.effective_registry
        if registry is None or _names_registry(image):
            return image
        return f"{registry.rstrip('/')}/{image}"

    async def call(
        self,
        fn: Callable[..., _T],
        *args: object,
        timeout: float | None = None,
        long: bool = False,
        **kwargs: object,
    ) -> _T:
        """Run ``fn(client, *args, **kwargs)`` on this host's thread pool.

        :param fn: blocking function that takes the docker-py client first
        :type fn: Callable[..., _T]
        :param args: extra positional arguments for *fn*
        :type args: object
        :param timeout: seconds before giving up; defaults to the host timeout
        :type timeout: float | None
        :param long: run on the long-operation pool (pulls, archives); running
            out of time there says nothing about the daemon, so it does not
            count against the breaker
        :type long: bool
        :param kwargs: extra keyword arguments for *fn*
        :type kwargs: object
        :return: whatever *fn* returns
        :rtype: _T
        :raises HostUnreachable: when the breaker is open or the host did not answer
        """
        if self.is_down:
            msg = f"host {self.name} is unreachable"
            raise HostUnreachable(msg, host=self.name, last_error=self.last_error)
        return await self._run(fn, *args, timeout=timeout, long=long, **kwargs)

    async def single_flight(self, key: str, make: Callable[[], Awaitable[_T]]) -> _T:
        """Share one in-progress operation between concurrent callers.

        Concurrent creates of the same image await one pull instead of each
        pulling. One caller's cancellation never cancels the shared operation.

        :param key: identifies the operation, e.g. ``pull:<ref>``
        :type key: str
        :param make: starts the operation when none is in progress
        :type make: Callable[[], Awaitable[_T]]
        :return: the operation's result
        :rtype: _T
        """
        flight = self._flights.get(key)
        if flight is None:
            flight = asyncio.ensure_future(make())
            self._flights[key] = flight
            flight.add_done_callback(lambda _done: self._flights.pop(key, None))
        return await asyncio.shield(flight)

    async def ping(self) -> bool:
        """Probe the daemon, bypassing the breaker; success closes it.

        :return: True when the daemon answered
        :rtype: bool
        """
        try:
            await self._run(lambda client: client.ping(), timeout=self.timeout)
        except HostUnreachable:
            return False
        return True

    def close(self) -> None:
        """Stop the thread pools and close the client.

        Queued calls still run: cancelling them would hand their awaiting
        coroutines a CancelledError nobody asked for (e.g. a create would then
        skip releasing its lease).
        """
        self._executor.shutdown(wait=False)
        self._long_executor.shutdown(wait=False)
        with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    async def _run(
        self,
        fn: Callable[..., _T],
        *args: object,
        timeout: float | None,
        long: bool = False,
        **kwargs: object,
    ) -> _T:
        loop = asyncio.get_running_loop()
        executor = self._long_executor if long else self._executor
        job = functools.partial(self._invoke, fn, args, kwargs)
        limit = (self.timeout if timeout is None else timeout) + _OUTER_MARGIN
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, job),
                timeout=limit,
            )
        except Exception as exc:
            if long and isinstance(exc, TimeoutError):
                msg = f"host {self.name}: operation did not finish within {limit:.0f} s"
                raise HostUnreachable(msg, host=self.name) from exc
            if is_transport_error(exc):
                self._record_failure(exc)
                msg = f"host {self.name} did not answer: {self.last_error}"
                raise HostUnreachable(msg, host=self.name) from exc
            if _is_api_error(exc):
                self._record_success()
            raise
        self._record_success()
        return result

    def _invoke(
        self,
        fn: Callable[..., _T],
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> _T:
        return fn(self._get_client(), *args, **kwargs)

    def _get_client(self) -> Any:  # noqa: ANN401
        with self._client_lock:
            if self._client is None:
                self._client = self._client_factory(self.spec, self.timeout)
            return self._client

    def _record_failure(self, exc: BaseException) -> None:
        was_down = self.is_down
        self._failures += 1
        self.last_error = str(exc) or type(exc).__name__
        if self.is_down and not was_down:
            _log.warning("host %s marked down: %s", self.name, self.last_error)

    def _record_success(self) -> None:
        if self.is_down:
            _log.info("host %s is reachable again", self.name)
        self._failures = 0
        self.last_ok_at = time.time()
