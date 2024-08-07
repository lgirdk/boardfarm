"""DHCPv6 Use Cases library."""
import re
from dataclasses import dataclass
from json import JSONDecoder
from typing import Any, Dict, List, Optional, Union

from boardfarm.devices.debian_isc import DebianISCProvisioner
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.exceptions import UseCaseFailure
from boardfarm.use_cases.dhcp import _manage_duplicates
from boardfarm.use_cases.networking import IPAddresses

ResultDict = Dict[str, Any]


@dataclass
class DHCPV6Options:
    """DHCPv6 options parsing."""

    option_data: ResultDict

    @property
    def option_3(self) -> Optional[ResultDict]:
        """Return option 3."""
        try:
            return self.option_data["Identity Association for Non-temporary Address"]
        except KeyError:
            return None

    @property
    def option_5(self) -> Optional[ResultDict]:
        """Return option 5."""
        try:
            return self.option_data["Identity Association for Non-temporary Address"][
                "IA Address"
            ]
        except KeyError:
            return None

    @property
    def option_25(self) -> Optional[ResultDict]:
        """Return option 25."""
        try:
            return self.option_data["Identity Association for Prefix Delegation"]
        except KeyError:
            return None

    @property
    def option_26(self) -> Optional[ResultDict]:
        """Return option 26."""
        try:
            return self.option_data["Identity Association for Prefix Delegation"][
                "IA Prefix"
            ]
        except KeyError:
            return None

    @property
    def option_8(self) -> Optional[ResultDict]:
        """Return option 8."""
        try:
            return self.option_data["Elapsed time"]
        except KeyError:
            return None

    @property
    def option_2(self) -> Optional[ResultDict]:
        """Return option 8."""
        try:
            return self.option_data["Server Identifier"]
        except KeyError:
            return None

    @property
    def option_1(self) -> Optional[ResultDict]:
        """Return option 1."""
        try:
            return self.option_data["Client Identifier"]
        except KeyError:
            return None

    @property
    def option_20(self) -> Optional[ResultDict]:
        """Return option 20."""
        try:
            return self.option_data["Reconfigure Accept"]
        except KeyError:
            return None

    @property
    def option_16(self) -> Optional[ResultDict]:
        """Return option 16."""
        try:
            return self.option_data["Vendor Class"]
        except KeyError:
            return None

    @property
    def option_17(self) -> Optional[ResultDict]:
        """Return option 17."""
        try:
            return self.option_data["Vendor-specific Information"]
        except KeyError:
            return None

    @property
    def option_6(self) -> Optional[ResultDict]:
        """Return option 6."""
        try:
            return self.option_data["Vendor-specific Information"]
        except KeyError:
            return None

    @property
    def option_23(self) -> Optional[ResultDict]:
        """Return option 23."""
        try:
            return self.option_data["Option Request"]
        except KeyError:
            return None

    @property
    def option_24(self) -> Optional[ResultDict]:
        """Return option 24."""
        try:
            return self.option_data["Domain Search List"]
        except KeyError:
            return None

    @property
    def option_64(self) -> Optional[ResultDict]:
        """Return option 64."""
        try:
            return self.option_data["Dual-Stack Lite AFTR Name"]
        except KeyError:
            return None

    @property
    def option_14(self) -> Optional[ResultDict]:
        """Return option 14."""
        try:
            return self.option_data["Rapid Commit"]
        except KeyError:
            return None


@dataclass
class DHCPV6TraceData:
    """This is a DHCPv6TraceData data class to hold source,destination,dhcpv6_packet and dhcpv6_message_type."""

    source: IPAddresses
    destination: IPAddresses
    dhcpv6_packet: ResultDict
    dhcpv6_message_type: int


def _update_trace_data(
    output: List[DHCPV6TraceData], msg: dict[str, Any], element: dict
) -> None:
    output.append(
        DHCPV6TraceData(
            IPAddresses(None, element["_source"]["layers"]["ipv6"]["ipv6.src"], None),
            IPAddresses(None, element["_source"]["layers"]["ipv6"]["ipv6.dst"], None),
            msg,
            int(element["_source"]["layers"]["dhcpv6"]["dhcpv6.msgtype"]),
        )
    )


def _modify_format(
    nested_dict: dict[str, Union[str, dict]], val_list: list[dict]
) -> None:
    """Modify the dict format.

    .. code-block:: python

        # modifies below format:

        {
            "dhcpv6.option.type_str": "Identity Association for Prefix Delegation",
            "dhcpv6.option.type_str_tree": {
                "dhcpv6.option.type": "25",
                ...
                }
        }

        to this format:

        {
            "Identity Association for Prefix Delegation": {
                "dhcpv6.option.type": "25",
                ...
            }
        }
    """
    nested_val_list = []
    nested_key_list = []
    for key, val in nested_dict.items():
        if re.search(r"type_str(?:_\d+)?$", key):
            nested_key_list.append(val)
        elif re.search(r"type_str_tree(?:_\d+)?$", key):
            nested_val_list.append(val)
        else:
            nested_key_list.append(key)
            nested_val_list.append(val)
    val_list.append(dict(zip(nested_key_list, nested_val_list)))


def parse_dhcpv6_trace(
    on_which_device: Union[DebianLAN, DebianWAN, DebianISCProvisioner],
    fname: str,
    timeout: int = 30,
    additional_args: str = "dhcpv6",
) -> List[DHCPV6TraceData]:
    """Read and filter the DHCPV6 packets from the pcap file and returns the DHCPV6 packets.

    :param on_which_device: Object of the device class where tcpdump is captured
    :type on_which_device: Union[DebianLAN, DebianWAN,DebianISCProvisioner]
    :param fname: Name of the captured pcap file
    :type fname: str
    :param timeout: time out for tshark command to be executed, defaults to 30
    :type timeout: int
    :param additional_args: additional arguments for tshark command to
                            display filtered output, defaults to dhcpv6
    :type additional_args: str
    :return: Sequence of DHCPV6 packets filtered from captured pcap file
    :rtype: List[DHCPV6TraceData]
    """
    try:
        out = on_which_device.tshark_read_pcap(
            fname=fname,
            additional_args=f"-Y '{additional_args}' -T json",
            timeout=timeout,
        )
        output: List[DHCPV6TraceData] = []
        key_list = []
        val_list = []
        data = "[" + out.split("[", 1)[-1].replace("\r\n", "")
        decoder = JSONDecoder(object_pairs_hook=_manage_duplicates)
        obj = decoder.decode(data)
        for element in obj:
            # condition for mv3 eth packets because the packets are not wrapped under Relay message
            # the below logic updates the dhcp packet dict to have the consistent format across gateways
            if "Relay Message" not in element["_source"]["layers"]["dhcpv6"].keys():
                pkt_dict = element["_source"]["layers"]["dhcpv6"]
                for pkt_key, pkt_value in pkt_dict.items():
                    if re.search(r"type_str(?:_\d+)?$", pkt_key):
                        key_list.append(pkt_value)
                    elif re.search(r"type_str_tree(?:_\d+)?$", pkt_key):
                        _modify_format(pkt_value, val_list)
                    else:
                        key_list.append(pkt_key)
                        val_list.append(pkt_value)
                dhcp_dict = dict(zip(key_list, val_list))
                _update_trace_data(output, dhcp_dict, element)
            else:
                _update_trace_data(
                    output, element["_source"]["layers"]["dhcpv6"], element
                )
        return output
    except Exception as e:
        raise UseCaseFailure(f"Failed to parse DHCPV6 packets due to {e} ")


def get_dhcpv6_packet_by_message(
    trace: List[DHCPV6TraceData],
    message_type: str,
) -> List[DHCPV6TraceData]:
    """Get the dhcpv6 packets for the particular message from the pcap file and returns the DHCPV6 packets.

    :param trace: Sequence of DHCPV6 packets filtered from captured pcap file and stored in DHCPV6TraceData
    :type trace: List[DHCPV6TraceData]
    :param message_type: DHCP message according to RFC3315 and could be any of:

        * SOLICIT,
        * ADVERTISE,
        * REQUEST,
        * CONFIRM,
        * RENEW,
        * REBIND,
        * REPLY,
        * RELEASE,
        * DECLINE,
        * RECONFIGURE,
        * INFORMATION-REQUEST,
        * RELAY-FORW,
        * RELAY-REPL

    :type message_type: str
    :return: Sequence of DHCPV6 packets filtered with the message type
    :rtype: List[DHCPV6TraceData]
    """
    output: List[DHCPV6TraceData] = []
    dhcpv6_message_dict = {
        "SOLICIT": 1,
        "ADVERTISE": 2,
        "REQUEST": 3,
        "CONFIRM": 4,
        "RENEW": 5,
        "REBIND": 6,
        "REPLY": 7,
        "RELEASE": 8,
        "DECLINE": 9,
        "RECONFIGURE": 10,
        "INFORMATION-REQUEST": 11,
        "RELAY-FORW": 12,
        "RELAY-REPLY": 13,
    }
    message_code = dhcpv6_message_dict.get(message_type)
    for packet in trace:
        if message_code == packet.dhcpv6_message_type:
            output.append(packet)
    return output


def get_all_dhcpv6_options(packet: DHCPV6TraceData) -> DHCPV6Options:
    """Get all the dhcpv6 options in a DHCPV6 packet.

    :param packet: desired packet from DHCPV6 trace (only one packet)
    :type packet: DHCPV6TraceData
    :return: all the dhcpv6 options
    :rtype: DHCPV6Options
    """
    if packet.dhcpv6_message_type in [12, 13]:
        out = {
            key: value
            for key, value in packet.dhcpv6_packet["Relay Message"]["dhcpv6"].items()
        }
    else:
        out = {key: value for key, value in packet.dhcpv6_packet.items()}
    return DHCPV6Options(out)
