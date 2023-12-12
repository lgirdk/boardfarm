"""Unit tests for networking.py module."""

from pathlib import Path

from boardfarm3.lib.networking import _LinuxConsole, dns_lookup

_DNS_LOOKUP_REPLY = Path(__file__).parents[1] / "testdata/dns_lookup"


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
