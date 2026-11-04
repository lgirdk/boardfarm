"""Holds that keep API jobs off devices a human is using interactively."""

from __future__ import annotations

import threading
from typing import Final

# Hold key (and job tag) meaning "every device".
ALL: Final = "*"


class ConsoleHeld(RuntimeError):
    """A job touches a device that is held for interactive use."""


class Holds:
    """Thread-safe registry of held devices and the reason for each hold.

    A key is a device name or :data:`ALL`. The queue worker and the event loop
    both read it, so every access goes through one lock.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._reasons: dict[str, str] = {}
        self._lock = threading.Lock()

    def hold(self, key: str, reason: str) -> None:
        """Hold a device, or everything when *key* is :data:`ALL`.

        :param key: device name or ``ALL``
        :type key: str
        :param reason: text a refused job reports, e.g. in the 409 detail
        :type reason: str
        """
        with self._lock:
            self._reasons[key] = reason

    def try_hold(self, key: str, reason: str) -> str | None:
        """Hold *key* unless a conflicting hold exists; check and take atomically.

        :data:`ALL` conflicts with any hold, including another ``ALL``. A
        device conflicts only with ``ALL``: re-holding the same device is a
        hand-over (or a re-label) and succeeds.

        :param key: device name or ``ALL``
        :type key: str
        :param reason: text a refused job reports, e.g. in the 409 detail
        :type reason: str
        :return: None when the hold was taken, else the conflicting reason
        :rtype: str | None
        """
        with self._lock:
            if key == ALL:
                if self._reasons:
                    return self._reasons.get(ALL) or next(iter(self._reasons.values()))
            elif ALL in self._reasons:
                return self._reasons[ALL]
            self._reasons[key] = reason
            return None

    def release(self, key: str) -> None:
        """Release a hold; releasing a key that is not held is a no-op.

        :param key: device name or ``ALL``
        :type key: str
        """
        with self._lock:
            self._reasons.pop(key, None)

    def is_held(self, key: str) -> bool:
        """Tell whether exactly *key* is held, ignoring what ``ALL`` implies.

        :param key: device name or ``ALL``
        :type key: str
        :return: True when a hold is stored under that exact key
        :rtype: bool
        """
        with self._lock:
            return key in self._reasons

    def reason(self, key: str) -> str | None:
        """Return the reason stored for exactly *key*.

        :param key: device name or ``ALL``
        :type key: str
        :return: the reason, or None when that key is not held
        :rtype: str | None
        """
        with self._lock:
            return self._reasons.get(key)

    def held_reason(  # pylint: disable=too-many-return-statements
        self, devices: frozenset[str]
    ) -> str | None:
        """Return why a job tagged with *devices* may not run, if it may not.

        :param devices: device names the job touches, or ``{ALL}``
        :type devices: frozenset[str]
        :return: the reason when a tagged device or ``ALL`` is held, or when the
            job is tagged ``ALL`` and anything is held; otherwise None
        :rtype: str | None
        """
        with self._lock:
            if not self._reasons:
                return None
            if ALL in self._reasons:
                return self._reasons[ALL]
            if ALL in devices:
                return next(iter(self._reasons.values()))
            for name in sorted(devices):
                if name in self._reasons:
                    return self._reasons[name]
            return None

    def check(self, devices: frozenset[str]) -> None:
        """Refuse a job that touches a held device.

        :param devices: device names the job touches, or ``{ALL}``
        :type devices: frozenset[str]
        :raises ConsoleHeld: when :meth:`held_reason` finds a reason
        """
        reason = self.held_reason(devices)
        if reason is not None:
            raise ConsoleHeld(reason)
