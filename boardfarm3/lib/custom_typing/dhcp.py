"""DHCP type hints for Provisioner Templates."""

from typing import Literal, TypedDict

DHCPSubOption = TypedDict(
    "DHCPSubOption",
    {"data": str, "name": str, "sub-option-code": int},
)

DHCPVendorOptions = TypedDict(
    "DHCPVendorOptions",
    {"sub-options": list[DHCPSubOption], "vendor-id": int},
)


# DHCPv4 Options that a Provisioner Template must support.

# These shall contain all the IPv4 information that are required in
# order to provision a CPE.

# All DHCPv4 options currently supported:
#     - valid-lifetime
#     - DNS (option 6)
#     - NTP (option 42)
#     - VSIO (option 43)
#     - VIVSO (option 125)

DHCPServicePools = Literal["mng", "voice", "data", "all"]

DHCPv4Options = TypedDict(
    "DHCPv4Options",
    {
        "dns-server": str,
        "ntp-server": str,
        "valid-lifetime": str,
        "vsio": list[DHCPSubOption],
        "vivso": DHCPVendorOptions,
    },
    total=False,
)


# DHCPv6 Options that a Provisioner Template must support.

# These shall contain all the IPv6 information that are required in
# order to provision a CPE.

# All DHCPv4 options currently supported:
#     - valid-lifetime
#     - DNS (option 23)
#     - NTP (option 56)
#     - VIVSO (option 17)

DHCPv6Options = TypedDict(
    "DHCPv6Options",
    {
        "dns-server": str,
        "ntp-server": str,
        "valid-lifetime": str,
        "vivso": DHCPVendorOptions,
    },
    total=False,
)
