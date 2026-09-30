"""The runtime registry of lab hosts, persisted to hosts.json."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from boardfarm3_control._jsonfile import read_json, write_json_atomic
from boardfarm3_control.errors import HostInUse, UnknownHost
from boardfarm3_control.models import HostSpec

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from boardfarm3_control.launcher.docker_host import DockerHost

_log = logging.getLogger(__name__)

IMPLICIT_LOCAL = "local"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# Fields that only affect future sessions; everything else re-points the host.
_SOFT_FIELDS = frozenset({"drain", "registry", "default"})
_VERSION = 1


def implicit_local_spec() -> HostSpec:
    """Return the host used when no seed and no hosts.json exist (today's behaviour).

    :return: the local daemon via ``from_env()``, agents on ``localhost``
    :rtype: HostSpec
    """
    return HostSpec(advertise_addr="localhost", registry="", default=True)


def _validate_name(name: str) -> None:
    if not _NAME.match(name):
        msg = f"host name {name!r} must match {_NAME.pattern}"
        raise ValueError(msg)


def parse_hosts(raw: Any) -> dict[str, HostSpec]:  # noqa: ANN401
    """Validate a ``{name: record}`` mapping from a seed or hosts.json.

    :param raw: decoded JSON object keyed by host name
    :type raw: Any
    :return: validated records by name
    :rtype: dict[str, HostSpec]
    :raises ValueError: on a bad name, a bad record or more than one default
    """
    if not isinstance(raw, dict):
        msg = "hosts must be a JSON object keyed by host name"
        raise ValueError(msg)  # noqa: TRY004
    specs: dict[str, HostSpec] = {}
    for name, item in raw.items():
        _validate_name(name)
        try:
            specs[name] = HostSpec.model_validate(item)
        except ValidationError as exc:
            msg = f"host {name!r}: {exc}"
            raise ValueError(msg) from exc
    defaults = sorted(name for name, spec in specs.items() if spec.default)
    if len(defaults) > 1:
        msg = f"at most one default host, got {', '.join(defaults)}"
        raise ValueError(msg)
    return specs


def _hard_fields_differ(old: HostSpec, new: HostSpec) -> bool:
    return old.model_dump(exclude=_SOFT_FIELDS) != new.model_dump(exclude=_SOFT_FIELDS)


class HostRegistry:
    """Lab hosts by name: their records, their DockerHost objects and hosts.json.

    The admin API is the only writer after first boot; the seed is read only
    when hosts.json does not exist yet.
    """

    def __init__(
        self,
        path: Path,
        specs: dict[str, HostSpec],
        host_factory: Callable[[str, HostSpec], DockerHost],
    ) -> None:
        """Build one DockerHost per record; nothing touches the network.

        :param path: hosts.json location
        :type path: Path
        :param specs: validated records by name
        :type specs: dict[str, HostSpec]
        :param host_factory: builds a DockerHost for a name and record
        :type host_factory: Callable[[str, HostSpec], DockerHost]
        """
        self._path = path
        self._specs = dict(specs)
        self._factory = host_factory
        self._hosts = {
            name: host_factory(name, spec) for name, spec in self._specs.items()
        }
        self._lock = asyncio.Lock()

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        seed: Any,  # noqa: ANN401
        host_factory: Callable[[str, HostSpec], DockerHost],
    ) -> HostRegistry:
        """Load hosts.json, else the seed, else the implicit local host; then save.

        :param path: hosts.json location
        :type path: Path
        :param seed: decoded ``BOARDFARM_HOSTS``/``BOARDFARM_HOSTS_FILE``, or None
        :type seed: Any
        :param host_factory: builds a DockerHost for a name and record
        :type host_factory: Callable[[str, HostSpec], DockerHost]
        :return: the registry
        :rtype: HostRegistry
        """
        seed_specs = parse_hosts(seed) if seed is not None else None
        if path.exists():
            specs = parse_hosts(read_json(path).get("hosts", {}))
            if seed_specs is not None and seed_specs != specs:
                _log.warning("hosts seed ignored; %s is authoritative", path)
        elif seed_specs is not None:
            specs = seed_specs
        else:
            specs = {IMPLICIT_LOCAL: implicit_local_spec()}
        registry = cls(path, specs, host_factory)
        registry.save()
        return registry

    def names(self) -> list[str]:
        """Return every host name, sorted.

        :return: host names
        :rtype: list[str]
        """
        return sorted(self._specs)

    def spec(self, name: str) -> HostSpec:
        """Return one host's record.

        :param name: host name
        :type name: str
        :return: the record
        :rtype: HostSpec
        :raises UnknownHost: when no such host exists
        """
        try:
            return self._specs[name]
        except KeyError:
            msg = f"unknown host {name}"
            raise UnknownHost(msg, host=name) from None

    def docker_host(self, name: str) -> DockerHost:
        """Return one host's DockerHost.

        :param name: host name
        :type name: str
        :return: the DockerHost
        :rtype: DockerHost
        :raises UnknownHost: when no such host exists
        """
        try:
            return self._hosts[name]
        except KeyError:
            msg = f"unknown host {name}"
            raise UnknownHost(msg, host=name) from None

    def default_host(self) -> str | None:
        """Return the host used when an inventory names no ``agent_host``.

        :return: the default host's name, or None
        :rtype: str | None
        """
        return next((name for name in self.names() if self._specs[name].default), None)

    async def put(self, name: str, spec: HostSpec, *, in_use: bool) -> HostSpec:
        """Create or replace a host.

        :param name: host name
        :type name: str
        :param spec: the new record
        :type spec: HostSpec
        :param in_use: whether the host has sessions of any kind
        :type in_use: bool
        :return: the stored record
        :rtype: HostSpec
        :raises HostInUse: when an in-use host would change a non-soft field
        """
        _validate_name(name)
        async with self._lock:
            current = self._specs.get(name)
            hard = current is None or _hard_fields_differ(current, spec)
            if current is not None and hard and in_use:
                msg = f"host {name} has sessions; only drain, registry and default can change"
                raise HostInUse(msg, host=name)
            self._apply(name, spec, recreate=hard)
            return spec

    async def patch(
        self, name: str, changes: dict[str, Any], *, in_use: bool
    ) -> HostSpec:
        """Change some fields of a host.

        :param name: host name
        :type name: str
        :param changes: fields to change
        :type changes: dict[str, Any]
        :param in_use: whether the host has sessions of any kind
        :type in_use: bool
        :return: the stored record
        :rtype: HostSpec
        :raises HostInUse: when an in-use host would change a non-soft field
        """
        async with self._lock:
            current = self.spec(name)
            merged = HostSpec.model_validate({**current.model_dump(), **changes})
            hard = _hard_fields_differ(current, merged)
            if hard and in_use:
                msg = f"host {name} has sessions; only drain, registry and default can change"
                raise HostInUse(msg, host=name)
            self._apply(name, merged, recreate=hard)
            return merged

    async def delete(self, name: str, *, in_use: bool) -> None:
        """Remove a host.

        :param name: host name
        :type name: str
        :param in_use: whether the host still has sessions
        :type in_use: bool
        :raises HostInUse: when the host still has sessions
        """
        async with self._lock:
            self.spec(name)
            if in_use:
                msg = f"host {name} has sessions"
                raise HostInUse(msg, host=name)
            del self._specs[name]
            self._hosts.pop(name).close()
            self.save()

    def save(self) -> None:
        """Write hosts.json atomically."""
        hosts = {name: self._specs[name].model_dump() for name in self.names()}
        write_json_atomic(self._path, {"version": _VERSION, "hosts": hosts})

    def close(self) -> None:
        """Close every host's thread pool and client."""
        for host in self._hosts.values():
            host.close()

    def _apply(self, name: str, spec: HostSpec, *, recreate: bool) -> None:
        if spec.default:
            for other, other_spec in list(self._specs.items()):
                if other != name and other_spec.default:
                    cleared = other_spec.model_copy(update={"default": False})
                    self._specs[other] = cleared
                    self._hosts[other].update_spec(cleared)
        self._specs[name] = spec
        if recreate:
            old = self._hosts.pop(name, None)
            if old is not None:
                old.close()
            self._hosts[name] = self._factory(name, spec)
        else:
            self._hosts[name].update_spec(spec)
        self.save()
