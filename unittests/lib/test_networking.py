"""Unit tests for networking.py module."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardfarm3.exceptions import SCPConnectionError
from boardfarm3.lib.networking import (
    UseCaseFailure,
    _LinuxConsole,
    dns_lookup,
    http_get,
    is_link_up,
    scp,
    start_tcpdump,
    tcpdump_read,
)

_TEST_DATA = Path(__file__).parents[1] / "testdata"

_DNS_LOOKUP_REPLY = _TEST_DATA / "dns_lookup"

_RG_IP_LINK_REPLY = _TEST_DATA / "rg_ip-link-show-erouter0"

_HTTP_RESPONSE = _TEST_DATA / "http_get"

_HTTP_RESPONSE_CONN_TIMED_OUT = _TEST_DATA / "http_get_failed_conn_timed_out"

_HTTP_RESPONSE_CONN_REFUSED = _TEST_DATA / "http_get_failed_conn_refused"

_TCPDUMP_OUTPUT = _TEST_DATA / "tcpdump_output"

_SCP_CONNECTION_ERROR = _TEST_DATA / "scp_conn_error"


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

    def expect_exact(
        self,
        pattern: str | list[str],  # noqa: ARG002, FA100, RUF100
        timeout: int = -1,  # noqa: ARG002
    ) -> int:
        """Wait for given exact pattern(s) and return the match index.

        :param pattern: expected pattern or pattern list
        :type pattern: Union[str, List[str]]
        :param timeout: timeout in seconds. Defaults to -1
        :type timeout: int
        :return: timeout
        :rtype: int
        """
        return 1

    def sendline(self, string: str) -> None:
        """Send given string to the console.

        :param string: string to send
        """

    def expect(
        self,
        pattern: str | list[str],
        timeout: int = -1,
    ) -> int:
        """Wait for given regex pattern(s) and return the match index.

        :param pattern: expected regex pattern or pattern list
        :type pattern: Union[str, List[str]]
        :param timeout: timeout in seconds. Defaults to -1
        :type timeout: int
        """


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


def test_start_tcpdump_value_error() -> None:
    """Test error thrown if tcpdump failed to begin pcap."""
    interface = "eth99"
    console = MyLinuxConsole("tcpdump: Invalid adapter index")
    with pytest.raises(ValueError, match=f"Failed to start tcpdump on {interface}"):
        start_tcpdump(console, interface, None, "")


def test_tcpdump_pcap_read() -> None:
    """Test if tcpdump pcap has been read."""
    console = MyLinuxConsole(_TCPDUMP_OUTPUT.read_text())
    output = tcpdump_read(
        console=console,
        capture_file=_TCPDUMP_OUTPUT.name,
        rm_pcap=True,
    )
    assert "listening on eth0" in output


def test_tcpdump_pcap_read_with_opts() -> None:
    """Test if tcpdump pcap has been read with options provided."""
    console = MyLinuxConsole(_TCPDUMP_OUTPUT.read_text())
    output = tcpdump_read(
        console=console,
        capture_file=_TCPDUMP_OUTPUT.name,
        opts="-qns 0",
        rm_pcap=True,
    )
    assert "listening on eth0" in output


def test_scp_conn_error_raises() -> None:
    """Test scp operations."""
    username = "scp_test"
    password = "scp_test"  # noqa: S105
    port = "2222"
    host = "10.10.10.10"
    src_path = "10.10.10.10"
    dst_path = "20.20.20.20"
    console = MyLinuxConsole(_SCP_CONNECTION_ERROR.read_text())
    with pytest.raises(
        SCPConnectionError,
        match=f"Failed to scp from {src_path} to {dst_path}",
    ):
        scp(
            console=console,
            host=host,
            port=port,
            username=username,
            password=password,
            src_path=src_path,
            dst_path=dst_path,
        )
