"""Collection on Enum to be used."""

from enum import Enum


class CPEInterfaces(Enum):
    """Define all the interfaces on CPE.

    The corresponding value should be available as an instance on board object.
    """

    ROUTER_WAN = "erouter_iface"
    VOICE = "mta_iface"
    ROUTER_LAN = "lan_iface"
    MGMT = "wan_iface"


class HostInterfaces(Enum):
    """Define all the interfaces on the Host device.

    The corresponding value should be available as an instance on the device object.
    """

    DATA = "iface_dut"
    MGMT = "iface_dut_mgmt"
