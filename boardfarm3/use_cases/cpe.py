"""Use Cases to check the performance of CPE."""

from __future__ import annotations

from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3.templates.cpe import CPE
    from boardfarm3.templates.lan import LAN


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
