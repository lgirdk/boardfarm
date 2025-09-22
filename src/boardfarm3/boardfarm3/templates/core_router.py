"""Core Router Template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class CoreRouter(ABC):
    """Core Router Template."""

    @property
    @abstractmethod
    def config(self) -> dict:
        """Device configuration."""
        raise NotImplementedError

    @property
    @abstractmethod
    def console(self) -> BoardfarmPexpect:
        """Returns WAN console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :return: IPv4 of the interface
        :raises BoardfarmException: in case IPv4 is not found
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return ipv4 address of the interface.

        :param interface: interface name
        :return: IPv6 of the interface
        :raises BoardfarmException: in case IPv6 is not found
        """
        raise NotImplementedError

    @abstractmethod
    def is_link_up(
        self,
        interface: str,
        pattern: str = "BROADCAST,MULTICAST,UP",
    ) -> bool:
        """Return the link status.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str
        :return: True if the link is up
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: str | None = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> bool | dict:
        """Ping remote host.

        Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping ip
        :param ping_count: number of ping, defaults to 4
        :param ping_interface: ping via interface, defaults to None
        :param options: extra ping options, defaults to ""
        :param timeout: timeout, defaults to 50
        :param json_output: return ping output in dictionary format, defaults to False
        :return: ping output
        """
        raise NotImplementedError

    @abstractmethod
    def nmap(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        ipaddr: str,
        ip_type: str,
        port: str | int | None = None,
        protocol: str | None = None,
        max_retries: int | None = None,
        min_rate: int | None = None,
        opts: str | None = None,
    ) -> dict:
        """Perform nmap operation on linux device.

        :param ipaddr: ip address on which nmap is performed
        :type ipaddr: str
        :param ip_type: type of ip eg: ipv4/ipv6
        :type ip_type: str
        :param port: destination port on ip, defaults to None
        :type port: Optional[Union[str, int]], optional
        :param protocol: specific protocol to follow eg: tcp(-sT)/udp(-sU),
            defaults to None
        :type protocol: Optional[str], optional
        :param max_retries: number of port scan probe retransmissions, defaults to None
        :type max_retries: Optional[int], optional
        :param min_rate: Send packets no slower than per second, defaults to None
        :type min_rate: Optional[int], optional
        :param opts: other options for a nmap command, defaults to None
        :type opts: str, optional
        :raises BoardfarmException: Raises exception if ip type is invalid
        :return: response of nmap command in xml/dict format
        :rtype: dict
        """
        raise NotImplementedError

    @abstractmethod
    def add_route(self, destination: str, hop: str, gw_interface: str | None) -> None:
        """Add a route to a destination via a specific gateway interface.

        The method will internally calculate the exit interface's ip address
        before adding the route.
        The gw_interface must be an interface name that exists on the host.
        Alternatively, you can provide a hop value.

        :param destination: ip address of the destination
        :type destination: str
        :param hop: ip address of the hop
        :type hop: str
        :param gw_interface: name of the interface
        :type gw_interface: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def delete_route(self, destination: str) -> None:
        """Delete a route to a destination.

        :param destination: ip address of the destination
        :type destination: str
        """
        raise NotImplementedError
