"""Use Cases to check the performance of CPE."""

from __future__ import annotations

import os
from contextlib import contextmanager
from string import Template
from typing import TYPE_CHECKING, Literal

from boardfarm3.exceptions import UseCaseFailure

if TYPE_CHECKING:
    from collections.abc import Generator

    from boardfarm3.templates.cpe import CPE
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN


_TOO_MANY_NTPS = 1

_UPNP_URL = Template("http://$IP:49152/IGDdevicedesc_brlan0.xml")


def get_cpu_usage(board: CPE) -> float:
    """Return the current CPU usage of CPE.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Return the current CPU usage of CPE.

    :param board: CPE device instance
    :type board: CPE
    :return: current CPU usage of the CPE
    :rtype: float
    """
    return board.sw.get_load_avg()


def get_memory_usage(board: CPE) -> dict[str, int]:
    """Return the memory usage of CPE.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Return the memory usage of CPE.

    :param board: CPE device instance
    :type board: CPE
    :return: current memory utilization of the CPE
    :rtype: dict[str, int]
    """
    return board.sw.get_memory_utilization()


def create_upnp_rule(
    device: LAN, int_port: str, ext_port: str, protocol: str, url: str | None = None
) -> str:
    """Create UPnP rule on the device.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Create UPnP rule through cli.

    :param device: LAN device instance
    :type device: LAN
    :param int_port: internal port for UPnP
    :type int_port: str
    :param ext_port: external port for UPnP
    :type ext_port: str
    :param protocol: protocol to be used
    :type protocol: str
    :param url: url to be used
    :type url: str | None
    :return: output of UPnP add port command
    :rtype: str
    """
    if url is None:
        url = _UPNP_URL.safe_substitute(IP=device.get_default_gateway())
    return device.create_upnp_rule(int_port, ext_port, protocol, url)


def delete_upnp_rule(device: LAN, ext_port: str, protocol: str, url: str | None) -> str:
    """Delete UPnP rule on the device.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Delete UPnP rule through cli.

    :param device: LAN device instance
    :type device: LAN
    :param ext_port: external port for UPnP
    :type ext_port: str
    :param protocol: protocol to be used
    :type protocol: str
    :param url: url to be used
    :type url: str | None
    :return: output of UPnP delete port command
    :rtype: str
    """
    if url is None:
        url = _UPNP_URL.safe_substitute(IP=device.get_default_gateway())
    return device.delete_upnp_rule(ext_port, protocol, url)


def is_ntp_synchronized(board: CPE) -> bool:
    """Get the NTP synchronization status.

    Sample block of the output

    .. code-block:: python

        [
            {
                "remote": "2001:dead:beef:",
                "refid": ".XFAC.",
                "st": 16,
                "t": "u",
                "when": 65,
                "poll": 18,
                "reach": 0,
                "delay": 0.0,
                "offset": 0.0,
                "jitter": 0.0,
                "state": "*",
            }
        ]

    This Use Case validates the 'state' from the parsed output and returns bool based on
    the value present in it. The meaning of the indicators are given below,

    '*' - synchronized candidate
    '#' - selected but not synchronized
    '+' - candidate to be selected
    [x/-/ /./None] - discarded candidate

    :param board: CPE device instance
    :type board: CPE
    :raises ValueError: when the output has more than one list item
    :return: True if NTP is synchronized, false otherwise
    :rtype: bool
    """
    ntp_output = board.sw.get_ntp_sync_status()
    if len(ntp_output) == 0:
        msg = "No NTP server available to the device"
        raise ValueError(msg)
    if len(ntp_output) > _TOO_MANY_NTPS:
        msg = "Unclear NTP status. There is more than one NTP server present"
        raise ValueError(msg)
    return ntp_output[0]["state"] == "*"


def enable_logs(board: CPE, component: str) -> None:
    """Enable logs for the specified component on the CPE.

    .. note::
        - The component can be one of "voice" and "pacm" for mv2p
        - The component can be one of "voice", "docsis", "common_components",
            "gw", "vfe", "vendor_cbn", "pacm" for mv1

    :param board: The board instance
    :type board: CPE
    :param component: The component for which logs have to be enabled.
    :type component: str
    """
    board.sw.enable_logs(component=component, flag="enable")


def disable_logs(board: CPE, component: str) -> None:
    """Disable logs for the specified component on the CPE.

    .. note::
        - The component can be one of "voice" and "pacm" for mv2p
        - The component can be one of "voice", "docsis", "common_components",
            "gw", "vfe", "vendor_cbn", "pacm" for mv1

    :param board: The board instance
    :type board: CPE
    :param component: The component for which logs have to disabled.
    :type component: str
    """
    board.sw.enable_logs(component=component, flag="disable")


def factory_reset(board: CPE, method: None | str = None) -> bool:
    """Perform factory reset CPE via given method.

    :param board: The board instance.
    :type board: CPE
    :param method: Factory reset method
    :type method: None | str
    :return: True on successful factory reset
    :rtype: bool
    """
    return board.sw.factory_reset(method)


def get_seconds_uptime(board: CPE) -> float:
    """Return board uptime in seconds.

    :param board: The board instance
    :type board: CPE
    :return: board uptime in seconds
    :rtype: float
    """
    return board.sw.get_seconds_uptime()


def is_tr069_agent_running(board: CPE) -> bool:
    """Check if TR069 agent is running or not.

    :param board: The board instance
    :type board: CPE
    :return: True if agent is running, false otherwise
    :rtype: bool
    """
    return board.sw.is_tr069_connected()


def get_cpe_provisioning_mode(board: CPE) -> str:
    """Get the provisioning mode of the board.

    :param board: The board object, from which the provisioning mode is fetched.
    :type board: CPE
    :return: The provisioning mode of the board.
    :rtype: str
    """
    return board.sw.get_provision_mode()


def board_reset_via_console(board: CPE) -> None:
    """Reset board via console.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Reboot from console.

    :param board: The board instance
    :type board: CPE
    """
    board.sw.reset(method="sw")
    board.sw.wait_for_boot()


@contextmanager
def tcpdump(
    fname: str,
    interface: str,
    board: CPE,
    filters: dict | None = None,
) -> Generator[str]:
    """Contextmanager to perform tcpdump on the board.

    Start ``tcpdump`` on the board console and kill it outside its scope

    :param fname: the filename or the complete path of the resource
    :type fname: str
    :param interface: interface name on which the tcp traffic will listen to
    :type interface: str
    :param board: CPE device instance
    :type board: CPE
    :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
    :type filters: dict | None
    :yield: yields the process id of the tcp capture started
    :rtype: Generator[str, None, None]
    """
    pid: str = ""
    try:
        pid = board.sw.nw_utility.start_tcpdump(fname, interface, filters=filters)
        yield pid
    finally:
        board.sw.nw_utility.stop_tcpdump(pid)


def read_tcpdump(
    fname: str,
    board: CPE,
    protocol: str = "",
    opts: str = "",
    rm_pcap: bool = True,
) -> str:
    """Read the tcpdump packets and delete the capture file afterwards.

    :param fname: filename or the complete path of the pcap file
    :type fname: str
    :param board: CPE device instance
    :type board: CPE
    :param protocol: protocol to filter, defaults to ""
    :type protocol: str
    :param opts: defaults to ""
    :type opts: str
    :param rm_pcap: defaults to True
    :type rm_pcap: bool
    :return: output of tcpdump read command
    :rtype: str
    """
    return board.sw.nw_utility.read_tcpdump(
        fname,
        protocol=protocol,
        opts=opts,
        rm_pcap=rm_pcap,
    )


def transfer_file_via_scp(  # pylint: disable=protected-access  # noqa: PLR0913
    source_dev: CPE,
    source_file: str,
    dest_file: str,
    dest_host: LAN | WAN,
    action: Literal["download", "upload"],
    port: int | str = 22,
    ipv6: bool = False,
) -> None:
    """Copy files and directories between the board and the remote host.

    Copy is made over SSH.

    :param source_dev: CPE device instance
    :type source_dev: CPE
    :param source_file: path on the board
    :type source_file: str
    :param dest_file: path on the remote host
    :type dest_file: str
    :param dest_host: the remote host instance
    :type dest_host: LAN | WAN
    :param port: host port
    :type port: int | str
    :param action: scp action to perform i.e upload, download
    :type action: Literal["download", "upload"]
    :param port: host port, defaults to 22
    :type port: str
    :param ipv6: whether scp should be done to IPv4 or IPv6, defaults to IPv4
    :type ipv6: bool
    """
    (src, dst) = (
        (source_file, dest_file) if action == "upload" else (dest_file, source_file)
    )
    # TODO: private members should not be used, BOARDFARM-5040
    username = dest_host._username  # type: ignore[union-attr]  # noqa: SLF001
    password = dest_host._password  # type: ignore[union-attr]  # noqa: SLF001
    ip_addr = (
        dest_host.get_interface_ipv6addr(dest_host.iface_dut)
        if ipv6
        else dest_host.get_interface_ipv4addr(dest_host.iface_dut)
    )
    source_dev.sw.nw_utility.scp(ip_addr, port, username, password, src, dst, action)


def upload_file_to_tftp(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_dev: CPE,
    source_file: str,
    tftp_server: LAN | WAN,
    path_on_tftpserver: str,
    ipv6: bool = False,
    timeout: int = 60,
) -> None:
    """Transfer file onto tftp server.

    .. hint:: This Use Case helps to copy files from board to tftp servre

        - can be used after a tcpdump on board

    :param source_dev: CPE device instance
    :type source_dev: CPE
    :param source_file: Path on the board
    :type source_file: str
    :param tftp_server: the remote tftp server instance
    :type tftp_server: LAN | WAN
    :param path_on_tftpserver: Path on the tftp server
    :type path_on_tftpserver: str
    :param ipv6: if scp should be done to ipv4 or ipv6, defaults to ipv4
    :type ipv6: bool
    :param timeout: timeout value for the usecase
    :type timeout: int
    :raises UseCaseFailure: when file not found
    """
    serv_tftp_folder = "/tftpboot"
    server_ip_addr = (
        tftp_server.get_interface_ipv6addr(tftp_server.iface_dut)
        if ipv6
        else tftp_server.get_interface_ipv4addr(tftp_server.iface_dut)
    )
    _, filename = os.path.split(source_file)
    file_location_on_server = f"{serv_tftp_folder}/{filename}"
    tftp_server.console.execute_command(
        f"chmod 777 {serv_tftp_folder}", timeout=timeout
    )
    source_dev.sw.nw_utility.tftp(
        server_ip_addr, source_file, filename, timeout=timeout
    )
    # move file to given tftp location and perform check of transfer
    mv_command = f"mv {file_location_on_server} {path_on_tftpserver}"
    output = tftp_server.console.execute_command(mv_command, timeout=timeout)
    if "No such file or directory" in output:
        msg = f"file not found {output}"
        raise UseCaseFailure(msg)
