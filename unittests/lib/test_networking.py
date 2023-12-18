"""Unit tests for networking.py module."""

from pathlib import Path

import pytest

from boardfarm3.lib.networking import (
    UseCaseFailure,
    _LinuxConsole,
    dns_lookup,
    http_get,
    is_link_up,
)

_DNS_LOOKUP_REPLY = Path(__file__).parents[1] / "testdata/dns_lookup"

_RG_IP_LINK_REPLY = Path(__file__).parents[1] / "testdata/rg_ip-link-show-erouter0"

_HTTP_RESPONSE = Path(__file__).parents[1] / "testdata/http_get"

_HTTP_RESPONSE_CONN_TIMED_OUT = (
    Path(__file__).parents[1] / "testdata/http_get_failed_conn_timed_out"
)

_HTTP_RESPONSE_CONN_REFUSED = (
    Path(__file__).parents[1] / "testdata/http_get_failed_conn_refused"
)


class MyLinuxConsole(_LinuxConsole):
    """Implement protocol _LinuxConsole."""

    def __init__(self, command_output: str) -> None:
        """Initialize _LinuxConsole protocol.

        :param command_output: answer param
        :type command_output: str
        """
        self.command_output = command_output

    def execute_command(self, command: str, timeout: int = -1) -> str:  # noqa: ARG002
        """Execute command.

        :param command: command to execute
        :type command: str
        :param timeout: timeout in seconds. Defaults is -1
        :type timeout: int
        :return: result of command execution
        :rtype: str
        """
        return self.command_output


def test_dns_lookup() -> None:
    """Verify dns lookup returns proper ip."""
    reply = dns_lookup(
        console=MyLinuxConsole(_DNS_LOOKUP_REPLY.read_text()),
        domain_name="www.google.com",
    )
    assert "172.217.168.196" in reply[1]["answer"][0]["data"]


def test_is_link_up() -> None:
    """Test link is up."""
    rg_link = is_link_up(
        console=MyLinuxConsole(_RG_IP_LINK_REPLY.read_text()),
        interface="erouter0",
    )
    assert rg_link is True


def test_http_get_200_ok() -> None:
    """Test get HTTP response."""
    http_response = http_get(
        console=MyLinuxConsole(_HTTP_RESPONSE.read_text()),
        url="www.google.com",
        timeout=1,
    )
    assert "Host: www.google.com" in http_response.response
    assert "200 OK" in http_response.response


def test_http_get_connection_timed_out() -> None:
    """Test exception thrown if connection timed out in HTTP response."""
    with pytest.raises(
        UseCaseFailure,
        match="Curl Failure due to the following reason Connection timed out",
    ):
        http_get(
            console=MyLinuxConsole(_HTTP_RESPONSE_CONN_TIMED_OUT.read_text()),
            url="",
            timeout=1,
        )


def test_http_get_connection_refused() -> None:
    """Test exception thrown if connection refused in HTTP response."""
    with pytest.raises(
        UseCaseFailure,
        match="Curl Failure due to the following reason Connection refused",
    ):
        http_get(
            console=MyLinuxConsole(_HTTP_RESPONSE_CONN_REFUSED.read_text()),
            url="",
            timeout=1,
        )
