"""Dataclasses to store DHCP info."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boardfarm3.lib.dataclasses.interface import IPAddresses

ResultDict = dict[str, Any]


@dataclass
class DHCPV6Options:
    """DHCPV6Options data class."""

    option_data: ResultDict

    @property
    def option_3(self) -> ResultDict | None:
        """DHCP IPv6 option 3.

        :return: DHCP IPv6 option 3.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Identity Association for Non-temporary Address"]
        except KeyError:
            return None

    @property
    def option_5(self) -> ResultDict | None:
        """DHCP IPv6 option 5.

        :return: DHCP IPv6 option 5.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Identity Association for Non-temporary Address"][
                "IA Address"
            ]
        except KeyError:
            return None

    @property
    def option_25(self) -> ResultDict | None:
        """DHCP IPv6 option 25.

        :return: DHCP IPv6 option 25.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Identity Association for Prefix Delegation"]
        except KeyError:
            return None

    @property
    def option_26(self) -> ResultDict | None:
        """DHCP IPv6 option 26.

        :return: DHCP IPv6 option 26.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Identity Association for Prefix Delegation"][
                "IA Prefix"
            ]
        except KeyError:
            return None

    @property
    def option_8(self) -> ResultDict | None:
        """DHCP IPv6 option 8.

        :return: DHCP IPv6 option 8.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Elapsed time"]
        except KeyError:
            return None

    @property
    def option_2(self) -> ResultDict | None:
        """DHCP IPv6 option 2.

        :return: DHCP IPv6 option 2.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Server Identifier"]
        except KeyError:
            return None

    @property
    def option_1(self) -> ResultDict | None:
        """DHCP IPv6 option 1.

        :return: DHCP IPv6 option 1.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Client Identifier"]
        except KeyError:
            return None

    @property
    def option_20(self) -> ResultDict | None:
        """DHCP IPv6 option 20.

        :return: DHCP IPv6 option 20.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Reconfigure Accept"]
        except KeyError:
            return None

    @property
    def option_16(self) -> ResultDict | None:
        """DHCP IPv6 option 16.

        :return: DHCP IPv6 option 16.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Vendor Class"]
        except KeyError:
            return None

    @property
    def option_17(self) -> ResultDict | None:
        """DHCP IPv6 option 17.

        :return: DHCP IPv6 option 17.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Vendor-specific Information"]
        except KeyError:
            return None

    @property
    def option_6(self) -> ResultDict | None:
        """DHCP IPv6 option 6.

        :return: DHCP IPv6 option 6.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Vendor-specific Information"]
        except KeyError:
            return None

    @property
    def option_23(self) -> ResultDict | None:
        """DHCP IPv6 option 23.

        :return: DHCP IPv6 option 23.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Option Request"]
        except KeyError:
            return None

    @property
    def option_24(self) -> ResultDict | None:
        """DHCP IPv6 option 24.

        :return: DHCP IPv6 option 24.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Domain Search List"]
        except KeyError:
            return None

    @property
    def option_64(self) -> ResultDict | None:
        """DHCP IPv6 option 64.

        :return: DHCP IPv6 option 64.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Dual-Stack Lite AFTR Name"]
        except KeyError:
            return None

    @property
    def option_14(self) -> ResultDict | None:
        """DHCP IPv6 option 14.

        :return: DHCP IPv6 option 14.
        :rtype: ResultDict | None
        """
        try:
            return self.option_data["Rapid Commit"]
        except KeyError:
            return None


@dataclass
class DHCPV6TraceData:
    """DHCPv6TraceData data class.

    Holds source, destination, DHCPv6_packet and DHCPv6_message_type.
    """

    source: IPAddresses
    destination: IPAddresses
    dhcpv6_packet: ResultDict
    dhcpv6_message_type: int
