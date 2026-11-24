"""Mapping of boardfarm exceptions onto the API error envelope."""

from __future__ import annotations

import re
import traceback as _traceback
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pexpect

from boardfarm3.api.execution import JOB_ID_ATTR, JobCancelled, QueueFull
from boardfarm3.api.holds import ConsoleHeld
from boardfarm3.exceptions import (
    DeviceConnectionError,
    DeviceNotFound,
    EnvConfigError,
    NotSupportedError,
    TR069FaultCode,
    TR069ResponseError,
    UseCaseFailure,
)

if TYPE_CHECKING:
    from boardfarm3.api.console import EventBuffer

# Ordered most specific first; the first isinstance match wins.
_STATUS_BY_EXCEPTION: tuple[tuple[type[BaseException], int], ...] = (
    (DeviceNotFound, HTTPStatus.NOT_FOUND),
    (NotSupportedError, HTTPStatus.NOT_IMPLEMENTED),
    (EnvConfigError, HTTPStatus.BAD_REQUEST),
    (UseCaseFailure, HTTPStatus.UNPROCESSABLE_ENTITY),
    (TR069FaultCode, HTTPStatus.BAD_GATEWAY),
    (TR069ResponseError, HTTPStatus.BAD_GATEWAY),
    (DeviceConnectionError, HTTPStatus.BAD_GATEWAY),
    (pexpect.TIMEOUT, HTTPStatus.GATEWAY_TIMEOUT),
    (QueueFull, HTTPStatus.TOO_MANY_REQUESTS),
    (JobCancelled, HTTPStatus.CONFLICT),
    (ConsoleHeld, HTTPStatus.CONFLICT),
)


# Credentials that inventories embed in connection strings, and that
# exceptions about those connections then quote.
# A value: quoted (spaces and all) or a bare word.
_VALUE = r"""(?:"[^"]*"|'[^']*'|[^\s,;'"}]+)"""
_SCRUBBERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(sshpass\s+-p\s*){_VALUE}"), r"\1***"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1***@"),
    (
        # Also the quoted forms of dict reprs and JSON: 'password': 'x'.
        re.compile(
            rf"((?:password|passwd|pwd|secret|token)['\"]?\s*[=:]\s*){_VALUE}",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
)


def scrub(text: str) -> str:
    """Mask passwords embedded in connection strings.

    :param text: text that may quote a connection string
    :type text: str
    :return: the text with credential values replaced by ``***``
    :rtype: str
    """
    for pattern, replacement in _SCRUBBERS:
        text = pattern.sub(replacement, text)
    return text


def http_status_for(exc: BaseException) -> int:
    """Map an exception to its HTTP status.

    :param exc: exception raised by boardfarm
    :type exc: BaseException
    :return: HTTP status code
    :rtype: int
    """
    for exception_type, status in _STATUS_BY_EXCEPTION:
        if isinstance(exc, exception_type):
            return int(status)
    return int(HTTPStatus.INTERNAL_SERVER_ERROR)


def error_envelope(
    exc: BaseException,
    *,
    session_id: str,
    job_id: str | None = None,
    device: str | None = None,
    console_tail: str = "",
) -> dict[str, Any]:
    """Build the API error envelope for an exception.

    :param exc: exception raised by boardfarm
    :type exc: BaseException
    :param session_id: session the failure belongs to
    :type session_id: str
    :param job_id: job that was running, if any
    :type job_id: str | None
    :param device: device involved, if known
    :type device: str | None
    :param console_tail: recent console output
    :type console_tail: str
    :return: error envelope containing error type, message, device, session/job IDs,
             console tail, and formatted traceback (including chained exceptions)
    :rtype: dict[str, Any]
    """
    return {
        "error": type(exc).__name__,
        "message": scrub(str(exc)),
        "device": device,
        "session_id": session_id,
        "job_id": job_id if job_id is not None else getattr(exc, JOB_ID_ATTR, None),
        # The tail includes framework log lines, which quote exceptions too.
        "console_tail": scrub(console_tail),
        "traceback": [scrub(line) for line in _traceback.format_exception(exc)],
    }


def console_tail_from(
    buffer: EventBuffer,
    job_id: str | None,
    lines: int = 40,
) -> str:
    """Return the most recent console and framework lines produced during a job.

    :param buffer: event buffer to read from
    :type buffer: EventBuffer
    :param job_id: job to filter by; None returns the global tail
    :type job_id: str | None
    :param lines: how many lines to return
    :type lines: int
    :return: newline joined console tail
    :rtype: str
    """
    events, _ = buffer.read(job_id=job_id, limit=1_000_000)
    return "\n".join(event.line for event in events[-lines:])
