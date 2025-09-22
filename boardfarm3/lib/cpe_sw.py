"""Common libraries of CPE Sw component."""

from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Interface
from typing import TYPE_CHECKING, Any, cast

import pexpect
from jc import parse

from boardfarm3.exceptions import BoardfarmException
from boardfarm3.lib.dmcli import DMCLIAPI
from boardfarm3.lib.network_utils import NetworkUtility
from boardfarm3.lib.networking import IptablesFirewall, is_link_up
from boardfarm3.templates.cpe.cpe_sw import CPESW

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from jc.jc_types import JSONDictType

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.custom_typing.jc import ParsedPSOutput
    from boardfarm3.templates.cpe.cpe_hw import CPEHW


# pylint: disable-next=too-many-public-methods
class CPESwLibraries(CPESW):
    """CPE SW common libraries."""

    def __init__(self, hardware: CPEHW) -> None:
        """Initialise the CPE software.

        :param hardware: cpe hardware instance
        :type hardware: CPEHW
        """
        self._hw = hardware
        self._nw_utility = NetworkUtility(self._get_console("networking"))
        self._firewall = IptablesFirewall(self._get_console("networking"))
        self._dmcli = DMCLIAPI(hardware.get_console("console"))

    @property
    def _console(self) -> BoardfarmPexpect:
        return self._get_console("default_shell")

    def _get_console(self, usage: str) -> BoardfarmPexpect:
        """Return console instance for the given usage.

        :param usage: usage of the console(dmcli/networking/wifi)
        :type usage: str
        :return: console instance for the given usage
        :rtype: BoardfarmPexpect
        :raises ValueError: if failed to get console for the component
        """
        if usage in ("networking", "default_shell"):
            return self._hw.get_console("console")
        msg = f"Unknown console usage: {usage}"
        raise ValueError(msg)

    @property
    def nw_utility(self) -> NetworkUtility:
        """Network utility component of cpe software.

        :return: Network utility libraries
        :rtype: NetworkUtility
        """
        return self._nw_utility

    @property
    def firewall(self) -> IptablesFirewall:
        """Firewall component of cpe software.

        :return: Network firewall libraries
        :rtype: IptablesFirewall
        """
        return self._firewall

    @property
    def dmcli(self) -> DMCLIAPI:
        """Dmcli instance running in CPE Software.

        :return: the object instance
        :rtype: DMCLIAPI
        """
        return self._dmcli

    def get_seconds_uptime(self) -> float:
        """Return uptime in seconds.

        :return: uptime in seconds
        :rtype: float
        :raises ValueError: if failed to get uptime
        """
        result = self._get_console("default_shell").execute_command("cat /proc/uptime")
        regex_match = re.search(r"((\d+)\.(\d{2}))(\s)(\d+)\.(\d{2})", result)
        if regex_match is None:
            msg = "Failed to get the uptime"
            raise ValueError(msg)
        return float(regex_match[1])

    def is_online(self) -> bool:
        """Is the device online.

        :return: True if the device is online, False otherwise
        :raises ValueError: if erouter mode not in ["dual", "ipv4", "ipv6"]
        """
        mode = self._hw.config.get("eRouter_Provisioning_mode", "dual")
        if mode not in ["dual", "ipv4", "ipv6"]:
            msg = f"Unsupported mode: {mode}"
            raise ValueError(msg)
        online: bool = True
        try:
            if mode in ["dual", "ipv4"]:
                online &= bool(self.get_interface_ipv4addr(self.erouter_iface))
            if mode in ["dual", "ipv6"]:
                online &= bool(self.get_interface_ipv6addr(self.erouter_iface))
        except ValueError:
            online = False
        return online

    def _get_nw_interface_ip_address(
        self,
        interface_name: str,
        is_ipv6: bool,
    ) -> list[str]:
        """Return network interface ip address.

        :param interface_name: interface name
        :param is_ipv6: is ipv6 address
        :returns: IP address list
        """
        prefix = "inet6" if is_ipv6 else "inet"
        ip_regex = prefix + r"\s(?:addr:)?\s*([^\s/]+)"
        output = self._get_console("networking").execute_command(
            f"ifconfig {interface_name}",
        )
        return re.findall(ip_regex, output)

    def _get_interface_ipv6_address(self, interface: str, address_type: str) -> str:
        """Return IPv6 address of the given network interface.

        :param interface: network interface name
        :param address_type: ipv6 address type
        :returns: IPv6 address of the given interface
        :raises ValueError: if IPv6 address is not found
        """
        address_type = address_type.replace("-", "_")
        ip_addresses = self._get_nw_interface_ip_address(interface, is_ipv6=True)
        for ip_addr in ip_addresses:
            if getattr(IPv6Interface(ip_addr), f"is_{address_type}"):
                return ip_addr
        msg = f"Failed to get IPv6 address of {interface} {address_type} address"
        raise ValueError(msg)

    def get_interface_ipv4addr(self, interface: str) -> str:
        """Return given interface IPv4 address.

        :param interface: interface name
        :return: IPv4 address
        :rtype: str
        :raises ValueError: if unable to parse IPv4Address
        """
        if ips := self._get_nw_interface_ip_address(interface, is_ipv6=False):
            return ips[0]
        msg = f"Failed to get IPv4 address of {interface} interface"
        raise ValueError(msg)

    def get_interface_ipv6addr(self, interface: str) -> str:
        """Return given interface IPv6 address.

        :param interface: interface name
        :return: IPv6 address
        """
        return self._get_interface_ipv6_address(interface, "global")

    def get_interface_link_local_ipv6_addr(self, interface: str) -> str:
        """Return given interface link local IPv6 address.

        :param interface: interface name
        :return: link local IPv6 address
        """
        return self._get_interface_ipv6_address(interface, address_type="link-local")

    def get_interface_ipv4_netmask(self, interface: str) -> IPv4Address:
        """Return given interface IPv4 netmask.

        :param interface: name of the interface
        :type interface: str
        :return: netmask of the interface
        :rtype: IPv4Address
        """
        output = self._get_console("networking").execute_command(
            f"ifconfig {interface}",
        )
        netmask = output.split("Mask:")[-1].split()[0]
        return IPv4Address(netmask)

    def is_link_up(
        self,
        interface: str,
        pattern: str = "BROADCAST,MULTICAST,UP",
    ) -> bool:
        """Check given interface is up or not.

        :param interface: interface name, defaults to "BROADCAST,MULTICAST,UP"
        :type interface: str
        :param pattern: interface state
        :type pattern: str
        :return: True if the link is up
        :rtype: bool
        """
        return is_link_up(self._get_console("networking"), interface, pattern)

    def get_interface_mac_addr(self, interface: str) -> str:
        """Return given interface mac address.

        :param interface: interface name
        :return: mac address of the given interface
        """
        return (
            self._get_console("networking")
            .execute_command(f"cat /sys/class/net/{interface}/address")
            .strip()
        )

    def is_tr069_connected(self) -> bool:
        """Is TR-69 agent is connected.

        :raises NotImplementedError: pending implementation
        """
        raise NotImplementedError

    def get_load_avg(self) -> float:
        """Return current load average of the cable modem.

        :return: current load average for the past minute
        :rtype: float
        """
        return float(
            self._get_console("default_shell")
            .execute_command(r"cat /proc/loadavg | cut -d\  -f1")
            .strip(),
        )

    def get_memory_utilization(self) -> dict[str, int]:
        """Return current memory utilization of the cable modem.

        :return: current memory utilization of cpe
        :rtype: dict[str, int]
        """
        memory_keys = []
        memory_val: list[str] = []
        result = self._get_console("default_shell").execute_command("free -m")
        if regex_match := re.search(
            r"Mem:\s+((\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(\d+))",
            result,
        ):
            memory_keys = [
                "total",
                "used",
                "free",
                "shared",
                "cache",
                "available",
            ]
            memory_val = regex_match.group(1).strip().split()
        # ignoring pylint error as fixing it would cause mypy to complain
        # about unreachable code...
        return dict(zip(memory_keys, map(int, memory_val)))

    def enable_logs(self, component: str, flag: str = "enable") -> None:
        """Enable logs for given component.

        :param component: component name
        :param flag: flag name, Default: "enable"
        :raises NotImplementedError: pending implementation
        """
        raise NotImplementedError

    def get_board_logs(self, timeout: int = 300) -> str:
        """Get the console log for the time period mentioned.

        :param timeout: time value to collect the logs for, defaults to 300
        :type timeout: int
        :return: Console logs for a given time period
        :rtype: str
        :raises BoardfarmException: if the console is not initialised,
            i.e. board has no console connections
        """
        if self._console:
            self._console.sendline()
            self._console.expect(pexpect.TIMEOUT, timeout=timeout)
            return str(self._console.before)
        msg = "Console obj is not initialized"
        raise BoardfarmException(msg)

    def read_event_logs(
        self,
    ) -> JSONDictType | list[JSONDictType] | Iterator[JSONDictType]:
        """Return the event logs from the `logread` command.

        .. code-block:: python

            # example output
            [
                {
                    "priority": None,
                    "date": "May  8 02:28:26",
                    "hostname": "mv1cbn-arm",
                    "tag": "kern",
                    "content": ".debug kernel: PP MC Session delete: failed for src...",
                },
                {
                    "priority": None,
                    "date": "May  8 02:42:46",
                    "hostname": "mv1cbn-arm",
                    "tag": "user",
                    "content": ".debug MCPROXY: del mroute gaddr: 239.255.255.250, ...",
                },
                {
                    "priority": None,
                    "date": "May  8 02:42:56",
                    "hostname": "mv1cbn-arm",
                    "tag": "kern",
                    "content": ".debug kernel: PP MC Session delete: failed for src...",
                },
                {
                    "priority": None,
                    "date": "May  8 02:57:16",
                    "hostname": "mv1cbn-arm",
                    "tag": "user",
                    "content": ".debug MCPROXY: del mroute gaddr: 239.255.255.250, ...",
                },
            ]

        :return: the event logs from the `logread` command.
        :rtype: JSONDictType | list[JSONDictType] | Iterator[JSONDictType]
        """
        return parse(
            "syslog-bsd",
            self._get_console("default_shell").execute_command("logread"),
        )

    def get_running_processes(
        self, ps_options: str | None = "-A"
    ) -> Iterable[ParsedPSOutput]:
        """Return the currently running processes in the CPE via the `ps` command.

        .. code-block:: python

            # parsed_ps_output
            [
                {"pid": 1, "tty": None, "time": "00:02:29", "cmd": "init"},
                {"pid": 2, "tty": None, "time": "00:00:00", "cmd": "kthreadd"},
                {"pid": 3, "tty": None, "time": "00:00:36", "cmd": "ksoftirqd/0"},
                {"pid": 5, "tty": None, "time": "00:00:00", "cmd": "kworker/0:0H"},
                ...
                {'pid': 2613, 'tty': None, 'time': '00:03:25', 'cmd': 'CcspTr069PaSsp'}
                ...
            ]

        :param ps_options: The options to be passed to the ps command, defaults to "-A"
        :type ps_options: str | None
        :return: the currently running processes as a parsed tuple of dictionaries
        :rtype: Iterable[ParsedPSOutput]
        """
        return cast(
            "tuple[ParsedPSOutput]",
            parse(
                "ps",
                self._get_console("default_shell").execute_command(f"ps {ps_options}"),
            ),
        )

    def get_ntp_sync_status(
        self,
    ) -> list[dict[str, Any]]:
        """Execute ntpq command to get the synchronization status.

        :raises NotImplementedError: pending implementation
        """
        raise NotImplementedError

    def kill_process_immediately(self, pid: int) -> None:
        """Kill the process based on the provided PID.

        :param pid: process number
        :type pid: int
        """
        self._get_console("default_shell").execute_command(f"kill -9 {pid}")

    def get_boottime_log(self) -> list[str]:
        """Return the boot time log from the board.

        :raises NotImplementedError: pending implementation
        """
        raise NotImplementedError

    def get_tr069_log(self) -> list[str]:
        """Return the TR-069 log from the board.

        :raises NotImplementedError: pending implementation
        """
        raise NotImplementedError

    def get_file_content(self, fname: str, timeout: int) -> str:
        """Get the content of the given file.

        :param fname: name of the file with absolute path
        :type fname: str
        :param timeout: timeout value to fetch the file content
        :type timeout: int
        :return: contents of the file
        :rtype: str
        """
        return self._get_console("default_shell").execute_command(
            f"cat {fname}",
            timeout,
        )

    def add_info_to_file(self, to_add: str, fname: str) -> None:
        """Add data into a file.

        :param to_add: contents/data to be added to a file.
        :type to_add: str
        :param fname: filename with absolute path
        :type fname: str
        """
        self._get_console("default_shell").execute_command(f"echo {to_add} >> {fname}")

    def get_date(self) -> str | None:
        """Get the system date and time.

        .. code-block:: python

            # example output
            donderdag, mei 23, 2024 14:23:39


        :return: date
        :rtype: str | None
        """
        cpe_date = self._console.execute_command("date '+%A, %B %d, %Y %T'")
        date = re.search(
            r"(\w+,\s\w+\s\d+,\s\d+\s(([0-1]?[0-9])|(2[0-3])):[0-5][0-9]:[0-5][0-9])",
            cpe_date,
        )
        if date is not None:
            return date.group(0)
        return None

    def set_date(self, date_string: str) -> bool:
        """Set the device's date and time.

        It should execute `date -s {date_string}` on the device's console.

        :param date_string: value to be changed
        :type date_string: str
        :return: True if set is successful
        :rtype: bool
        """
        cmd_out = self._console.execute_command(f"date -s {date_string}")
        return bool(cmd_out)

    @property
    def lan_network_ipv4(self) -> IPv4Network:
        """LAN IPv4 network.

        :return: LAN IPv4 network
        :rtype: IPv4Network
        """
        lan_network_mask = self.get_interface_ipv4_netmask(self.lan_iface)
        return IPv4Network(f"{self.lan_gateway_ipv4}/{lan_network_mask}", strict=False)

    @property
    def lan_gateway_ipv6(self) -> IPv6Address:
        """LAN Gateway IPv6 address.

        :return: IPv6 address of LAN GW
        :rtype: IPv6Address
        """
        return IPv6Address(self.get_interface_ipv6addr(self.lan_iface))
