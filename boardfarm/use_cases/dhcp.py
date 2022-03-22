import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from json import JSONDecoder
from typing import Any, Dict, List, Union

from boardfarm.devices.debian_isc import DebianISCProvisioner
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.devices.debian_wan import DebianWAN
from boardfarm.exceptions import UseCaseFailure
from boardfarm.use_cases.networking import IPAddresses

RecursiveDict = Dict[str, Any]


@dataclass
class DHCPTraceData:
    """This is a DHCPTraceData data class to hold source,destination,dhcp_packet and dhcp_message_type"""

    source: IPAddresses
    destination: IPAddresses
    dhcp_packet: RecursiveDict
    dhcp_message_type: int


def _manage_duplicates(pairs):
    """Internal function to manage duplicate keys in the Json"""
    d = {}
    k_counter = Counter(defaultdict(int))
    for k, v in pairs:
        index_str = "" if k_counter[k] == 0 else "_" + str(k_counter[k])
        d[k + index_str] = v
        k_counter[k] += 1
    return d


def parse_dhcp_trace(
    on_which_device: Union[DebianLAN, DebianWAN, DebianISCProvisioner], fname: str
) -> List[DHCPTraceData]:
    """Read and filter the DHCP packets from the pcap file and returns the DHCP packets.

    :param on_which_device: Object of the device class where tcpdump is captured
    :type on_which_device: Union[DebianLAN, DebianWAN,DebianISCProvisioner]
    :param fname: Name of the captured pcap file
    :type fname: str
    :return: Sequence of DHCP packets filtered from captured pcap file
    :rtype: List[DHCPTraceData]
    """
    try:
        out = on_which_device.tshark_read_pcap(
            fname=fname, additional_args="-Y bootp -T json"
        )
        output: List[DHCPTraceData] = []
        data = "[" + out.split("[", 1)[-1].replace("\r\n", "")

        # replacing bootp to dhcp as the devices still use older tshark versions
        replaced_data = data.replace("bootp", "dhcp")
        decoder = JSONDecoder(object_pairs_hook=_manage_duplicates)
        obj = decoder.decode(replaced_data)
        for element in obj:
            output.append(
                DHCPTraceData(
                    IPAddresses(
                        element["_source"]["layers"]["ip"]["ip.src"], None, None
                    ),
                    IPAddresses(
                        element["_source"]["layers"]["ip"]["ip.dst"], None, None
                    ),
                    element["_source"]["layers"]["dhcp"],
                    int(
                        element["_source"]["layers"]["dhcp"]["dhcp.option.type_tree"][
                            "dhcp.option.dhcp"
                        ]
                    ),
                )
            )
        return output
    except Exception as e:
        raise UseCaseFailure(f"Failed to parse DHCP packets due to {e} ")


def get_dhcp_packet_by_message(
    trace: List[DHCPTraceData],
    message_type: str,
) -> List[DHCPTraceData]:
    """Get the dhcp packets for the particular message from the pcap file and returns the DHCP packets.

    :param trace:  Sequence of DHCP packets filtered from captured pcap file and stored in DHCPTraceData
    :type trace: List[DHCPTraceData]
    :param message_type: DHCP message according to RFC2132 and could be any of DHCPDISCOVER,DHCPOFFER,DHCPREQUEST,DHCPDECLINE,DHCPACK,DHCPACK,DHCPRELEASE,DHCPINFORM
    :type message_type: str
    :return: Sequence of DHCP packets filtered with the message type
    :rtype: List[DHCPTraceData]
    """
    output: List[DHCPTraceData] = []
    dhcp_message_dict = {
        "DHCPDISCOVER": 1,
        "DHCPOFFER": 2,
        "DHCPREQUEST": 3,
        "DHCPDECLINE": 4,
        "DHCPACK": 5,
        "DHCPNAK": 6,
        "DHCPRELEASE": 7,
        "DHCPINFORM": 8,
    }
    message_code = dhcp_message_dict.get(message_type)
    for packet in trace:
        if message_code == packet.dhcp_message_type:
            output.append(packet)
    return output


def get_all_dhcp_options(packet: DHCPTraceData) -> RecursiveDict:
    """Get all the dhcp options in a DHCP packet.

    :param packet: desired packet from DHCP trace (only one packet)
    :type packet: DHCPTraceData
    :return: all the dhcp options
    :rtype: DHCPOptions
    """
    out = {
        key: value
        for key, value in packet.dhcp_packet.items()
        if "dhcp.option.type" in key
    }
    return out


def get_dhcp_option_details(packet: DHCPTraceData, option: int) -> RecursiveDict:
    """Get all required option details when option is provided.

    :param option: dhcp option
    :type option: int
    :return: option Dict along with suboptions
    :rtype: Dict
    """
    option_data = get_all_dhcp_options(packet)
    try:
        for key, value in option_data.items():
            if value == str(option):
                if re.search(r"_\d", key):
                    out = option_data[
                        key.split("_")[0]
                        + "_tree_"
                        + key.split("_")[len(key.split("_")) - 1]
                    ]
                    break
                else:
                    out = option_data[key + "_tree"]
        return out
    except KeyError:
        raise UseCaseFailure(f"Failed to find option {str(option)}")


def get_dhcp_suboption_details(
    packet: DHCPTraceData, option: int, suboption: int
) -> RecursiveDict:
    """Get all required sub option details when option & sub option are provided.

    :param option: dhcp option
    :type option: int
    :param suboption: dhcp sub option
    :type suboption: int
    :return: suboption Dict
    :rtype: Dict
    """
    sub_option_data = get_dhcp_option_details(packet, option)
    try:
        for key, value in sub_option_data.items():
            if "suboption" in key and value == str(suboption):
                if re.search(r"_\d", key):
                    out = sub_option_data[
                        key.split("_")[0]
                        + "_tree_"
                        + key.split("_")[len(key.split("_")) - 1]
                    ]
                    break
                else:
                    out = sub_option_data[key + "_tree"]
        return out
    except KeyError:
        raise UseCaseFailure(f"Failed to find suboption {str(suboption)} ")
