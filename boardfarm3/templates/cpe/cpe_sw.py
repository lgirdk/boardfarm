"""CPE SW Template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from ipaddress import IPv4Address, IPv4Network, IPv6Address

    from jc.jc_types import JSONDictType

    from boardfarm3.lib.custom_typing.jc import ParsedPSOutput
    from boardfarm3.lib.dmcli import DMCLIAPI
    from boardfarm3.lib.hal.cpe_wifi import WiFiHal
    from boardfarm3.lib.network_utils import NetworkUtility
    from boardfarm3.lib.networking import IptablesFirewall


# pylint: disable=too-many-public-methods,duplicate-code
class CPESW(ABC):
    """CPE Software Template."""

    @property
    @abstractmethod
    def wifi(self) -> WiFiHal:
        """Wifi instance CPE Software."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dmcli(self) -> DMCLIAPI:
        """Dmcli instance running in CPE Software (if any)."""
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """CPE software version.

        This will reload after each flash.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def erouter_iface(self) -> str:
        """e-Router interface name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_iface(self) -> str:
        """LAN interface name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def guest_iface(self) -> str:
        """Guest network interface name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def json_values(self) -> dict[str, Any]:
        """CPE Specific JSON values."""
        raise NotImplementedError

    @property
    @abstractmethod
    def gui_password(self) -> str:
        """GUI login password."""
        raise NotImplementedError

    @property
    @abstractmethod
    def cpe_id(self) -> str:
        """TR069 CPE ID."""
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_gateway_ipv4(self) -> IPv4Address:
        """LAN Gateway IPv4 address."""
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_gateway_ipv6(self) -> IPv6Address:
        """LAN Gateway IPv6 address."""
        raise NotImplementedError

    @property
    @abstractmethod
    def lan_network_ipv4(self) -> IPv4Network:
        """LAN IPv4 network."""
        raise NotImplementedError

    @property
    @abstractmethod
    def nw_utility(self) -> NetworkUtility:
        """Network utility component of cpe software."""
        raise NotImplementedError

    @property
    @abstractmethod
    def firewall(self) -> IptablesFirewall:
        """Firewall component of cpe software."""
        raise NotImplementedError

    @abstractmethod
    def verify_cpe_is_booting(self) -> None:
        """Verify CPE is booting."""
        raise NotImplementedError

    @abstractmethod
    def get_provision_mode(self) -> str:
        """Return provision mode."""
        raise NotImplementedError

    @abstractmethod
    def is_production(self) -> bool:
        """Is production software.

        Production software has limited capabilities.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self, method: str | None = None) -> None:
        """Perform reset via given method.

        :param method: reset method. Default None
        :type method: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def factory_reset(self, method: str | None = None) -> bool:
        """Perform factory reset CPE via given method.

        :param method: factory reset method. Default None.
        :type method: str | None
        :return: True on successful factory reset, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def wait_for_boot(self) -> None:
        """Wait for CPE to boot."""
        raise NotImplementedError

    @abstractmethod
    def get_seconds_uptime(self) -> float:
        """Return uptime in seconds.

        :return: uptime in seconds
        """
        raise NotImplementedError

    @abstractmethod
    def is_online(self) -> bool:
        """Is CPE online.

        :return: True if the CPE is online, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv4addr(self, interface: str) -> str:
        """Return given interface IPv4 address.

        :param interface: interface name
        :return: IPv4 address
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return given interface IPv6 address.

        :param interface: interface name
        :return: IPv6 address
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_link_local_ipv6_addr(self, interface: str) -> str:
        """Return given interface link local IPv6 address.

        :param interface: interface name
        :return: link local IPv6 address
        """
        raise NotImplementedError

    @abstractmethod
    def is_link_up(
        self,
        interface: str,
        pattern: str = "BROADCAST,MULTICAST,UP",
    ) -> bool:
        """Return the link status.

        :param interface: interface state
        :type interface: str
        :param pattern: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type pattern: str
        :return: True if the link is up
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def get_interface_mac_addr(self, interface: str) -> str:
        """Return given interface mac address.

        :param interface: interface name
        :return: mac address of the given interface
        """
        raise NotImplementedError

    @abstractmethod
    def is_tr069_connected(self) -> bool:
        """Is TR-69 agent is connected.

        :return: True is TR-69 is connected, otherwise False
        """
        raise NotImplementedError

    @abstractmethod
    def get_load_avg(self) -> float:
        """Return current load average of the CPE.

        :return: current load average
        """
        raise NotImplementedError

    @abstractmethod
    def get_memory_utilization(self) -> dict[str, int]:
        """Return the current memory utilization of the CPE.

        :return: current memory utilization
        :rtype: dict[str, int]
        """
        raise NotImplementedError

    @abstractmethod
    def enable_logs(self, component: str, flag: str = "enable") -> None:
        """Enable logs for given component.

        :param component: component name
        :param flag: flag name, Default: "enable"
        """
        raise NotImplementedError

    @abstractmethod
    def get_board_logs(self, timeout: int = 300) -> str:
        """Return board console logs for given timeout.

        :param timeout: log capture time in seconds
        :return: captured logs
        """
        raise NotImplementedError

    @abstractmethod
    def read_event_logs(
        self,
    ) -> JSONDictType | list[JSONDictType] | Iterator[JSONDictType]:
        """Return the event logs from the `logread` command.

        :return: the event logs from the `logread` command.
        :rtype: JSONDictType | list[JSONDictType] | Iterator[JSONDictType]
        """
        raise NotImplementedError

    @abstractmethod
    def get_running_processes(
        self,
        ps_options: str = "-A",
    ) -> Iterable[ParsedPSOutput]:
        """Return the currently running processes in the CPE via the `ps` command.

        :param ps_options: The options to be passed to the ps command, defaults to "-A"
        :type ps_options: str
        :return: the currently running processes as a parsed tuple of dictionaries
        :rtype: Iterable[ParsedPSOutput]
        """
        raise NotImplementedError

    @abstractmethod
    def get_ntp_sync_status(
        self,
    ) -> list[dict[str, Any]]:
        """Execute ntpq command to get the synchronization status.

        :return: parsed output of ntpq command
        :rtype: list[dict[str, Any]]
        """
        raise NotImplementedError

    @abstractmethod
    def kill_process_immediately(self, pid: int) -> None:
        """Kills any process based on the provided process ID.

        :param pid: process number
        :type pid: int
        """
        raise NotImplementedError

    @abstractmethod
    def get_boottime_log(self) -> list[str]:
        """Return the boot time log from the board.

        :return: boot time log
        :rtype: list[str]
        """
        raise NotImplementedError

    @abstractmethod
    def get_tr069_log(self) -> list[str]:
        """Return the TR-069 log from the board.

        :return: TR-069 logs
        :rtype: list[str]
        """
        raise NotImplementedError

    @abstractmethod
    def get_file_content(self, fname: str, timeout: int) -> str:
        """Get the content of the given file.

        :param fname: name of the file with absolute path
        :type fname: str
        :param timeout: timeout value to fetch the file content
        :type timeout: int
        :return: contents of the file
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def add_info_to_file(self, to_add: str, fname: str) -> None:
        """Add data into a file.

        :param to_add: contents/data to be added to a file.
        :type to_add: str
        :param fname: filename with absolute path
        :type fname: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_date(self) -> str | None:
        """Get the system date and time.

        .. code-block:: python

            # example output
            donderdag, mei 23, 2024 14:23:39


        :return: date
        :rtype: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def set_date(self, date_string: str) -> bool:
        """Set the device's date and time.

        It should execute `date -s {date_string}` on the device's console.

        :param date_string: value to be changed
        :type date_string: str
        :return: True if set is successful
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def finalize_boot(self) -> bool:
        """Validate board settings post boot.

        :return: True on successful validation
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def aftr_iface(self) -> str:
        """AFTR interface name."""
        raise NotImplementedError

    @abstractmethod
    def get_interface_mtu_size(self, interface: str) -> int:
        """Get the MTU size of the interface in bytes.

        :param interface: name of the interface
        :type interface: str
        :return: size of the MTU in bytes
        :rtype: int
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def tr69_cpe_id(self) -> str:
        """TR-69 CPE Identifier."""
        raise NotImplementedError
