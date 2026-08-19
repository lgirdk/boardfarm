"""Unit tests for boardfarm API error mapping."""

import pexpect
import pytest

from boardfarm3.api.console import EventBuffer
from boardfarm3.api.errors import console_tail_from, error_envelope, http_status_for
from boardfarm3.exceptions import (
    ConfigurationFailure,
    DeviceConnectionError,
    DeviceNotFound,
    EnvConfigError,
    NotSupportedError,
    SSHConnectionError,
    TR069FaultCode,
    UseCaseFailure,
)

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500
HTTP_NOT_IMPLEMENTED = 501
HTTP_BAD_GATEWAY = 502
HTTP_GATEWAY_TIMEOUT = 504


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (DeviceNotFound("no lan"), HTTP_NOT_FOUND),
        (NotSupportedError("nope"), HTTP_NOT_IMPLEMENTED),
        (EnvConfigError("bad json"), HTTP_BAD_REQUEST),
        (UseCaseFailure("ping failed"), HTTP_UNPROCESSABLE),
        (DeviceConnectionError("down"), HTTP_BAD_GATEWAY),
        (SSHConnectionError("refused"), HTTP_BAD_GATEWAY),
        (TR069FaultCode("9001"), HTTP_BAD_GATEWAY),
        (pexpect.TIMEOUT("timed out"), HTTP_GATEWAY_TIMEOUT),
        (ConfigurationFailure("boot"), HTTP_SERVER_ERROR),
        (RuntimeError("unknown"), HTTP_SERVER_ERROR),
    ],
)
def test_exception_maps_to_expected_status(
    exception: BaseException,
    expected: int,
) -> None:
    """Each boardfarm exception maps to its documented status.

    :param exception: exception instance
    :type exception: BaseException
    :param expected: expected HTTP status
    :type expected: int
    """
    assert http_status_for(exception) == expected


def test_subclass_maps_before_its_base() -> None:
    """The SSHConnectionError subclass must not fall through to a broader mapping."""
    assert http_status_for(SSHConnectionError("x")) == HTTP_BAD_GATEWAY


def test_envelope_carries_context() -> None:
    """The envelope names the error type, device, session and job."""
    envelope = error_envelope(
        DeviceConnectionError("SSH to 172.25.1.2 refused"),
        session_id="s-4f2a",
        job_id="j-8f3a",
        device="lan",
        console_tail="login:",
    )
    assert envelope["error"] == "DeviceConnectionError"
    assert envelope["message"] == "SSH to 172.25.1.2 refused"
    assert envelope["device"] == "lan"
    assert envelope["session_id"] == "s-4f2a"
    assert envelope["job_id"] == "j-8f3a"
    assert envelope["console_tail"] == "login:"
    assert "traceback" in envelope


def test_console_tail_returns_last_lines_for_the_job() -> None:
    """The tail is the most recent lines produced during that job."""
    buffer = EventBuffer()
    for index in range(60):
        buffer.append(
            stream="console",
            device="board",
            job_id="j-1",
            line=f"line-{index}",
        )
    buffer.append(stream="console", device="board", job_id="j-2", line="other")
    tail = console_tail_from(buffer, "j-1", lines=40)
    assert tail.splitlines()[0] == "line-20"
    assert tail.splitlines()[-1] == "line-59"
    assert "other" not in tail


def test_error_envelope_carries_a_traceback() -> None:
    """An error with no traceback is not debuggable."""
    try:
        msg = "boom"
        raise ValueError(msg)  # noqa: TRY301
    except ValueError as exc:
        envelope = error_envelope(exc, session_id="s-1")
    assert envelope["error"] == "ValueError"
    assert any("ValueError: boom" in frame for frame in envelope["traceback"])
    assert any(
        "test_error_envelope_carries" in frame for frame in envelope["traceback"]
    )


def test_error_envelope_traceback_includes_the_cause_chain() -> None:
    """A chained exception must show both frames, not just the outermost."""
    try:
        try:
            msg = "inner"
            raise ValueError(msg)  # noqa: TRY301
        except ValueError as inner:
            msg = "outer"
            raise RuntimeError(msg) from inner
    except RuntimeError as exc:
        envelope = error_envelope(exc, session_id="s-1")
    joined = "".join(envelope["traceback"])
    assert "ValueError: inner" in joined
    assert "RuntimeError: outer" in joined


def test_console_tail_includes_framework_lines() -> None:
    """Framework output is where Python errors surface; it must be in the tail."""
    buffer = EventBuffer()
    buffer.append(stream="console", device="board", job_id="j-1", line="console line")
    buffer.append(stream="framework", device=None, job_id="j-1", line="framework line")
    tail = console_tail_from(buffer, "j-1")
    assert "console line" in tail
    assert "framework line" in tail
