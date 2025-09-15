"""Boardfarm LGI DHCP IPv4 Use Cases."""

from __future__ import annotations

import binascii
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from json import JSONDecodeError, JSONDecoder
from time import sleep
from typing import TYPE_CHECKING, Any

from boardfarm3.exceptions import UseCaseFailure
from boardfarm3.lib.dataclass.dhcp import DHCPV6Options, DHCPV6TraceData
from boardfarm3.lib.dataclass.interface import IPAddresses

if TYPE_CHECKING:
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.line_termination import LTS
    from boardfarm3.templates.provisioner import Provisioner
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN

RecursiveDict = dict[str, Any]


@dataclass
class DHCPTraceData:
    """Provides a DHCPTraceData data class.

    Holds source, destination, dhcp_packet and dhcp_message_type.
    """

    source: IPAddresses
    destination: IPAddresses
    dhcp_packet: RecursiveDict
    dhcp_message_type: int


def _manage_duplicates(pairs: dict) -> dict:
    updated_dict = {}
    k_counter: dict = Counter(defaultdict(int))
    for key, value in pairs:
        index_str = "" if k_counter[key] == 0 else "_" + str(k_counter[key])
        updated_dict[key + index_str] = value
        k_counter[key] += 1
    return updated_dict


def parse_dhcp_trace(
    on_which_device: LAN | WAN | Provisioner | LTS,
    fname: str,
    timeout: int = 30,
) -> list[DHCPTraceData]:
    """Read and filter the DHCP packets from the pcap file and returns the DHCP packets.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify from the packet capture
        - Verify that the following messages are exchanged
        - Check that [] messages are exchanged

    :param on_which_device: Object of the device class where tcpdump is captured
    :type on_which_device: LAN | WAN | Provisioner | CMTS
    :param fname: Name of the captured pcap file
    :type fname: str
    :param timeout: time out for ``tshark read`` to be executed, defaults to 30
    :type timeout: int
    :raises UseCaseFailure: on DHCP parse issue
    :return: Sequence of DHCP packets filtered from captured pcap file
    :rtype: List[DHCPTraceData]
    """
    try:
        out = on_which_device.tshark_read_pcap(
            fname=fname,
            additional_args="-Y bootp -T json",
            timeout=timeout,
        )
        output: list[DHCPTraceData] = []
        data = "[" + out.split("[", 1)[-1].replace("\r\n", "")

        # replacing bootp to dhcp as the devices still use older tshark versions
        replaced_data = data.replace("bootp", "dhcp")
        decoder = JSONDecoder(
            object_pairs_hook=_manage_duplicates,  # type: ignore [arg-type]
        )
        obj = decoder.decode(replaced_data)
        output = [
            DHCPTraceData(
                IPAddresses(
                    element["_source"]["layers"]["ip"]["ip.src"],
                    None,
                    None,
                ),
                IPAddresses(
                    element["_source"]["layers"]["ip"]["ip.dst"],
                    None,
                    None,
                ),
                element["_source"]["layers"]["dhcp"],
                int(
                    element["_source"]["layers"]["dhcp"]["dhcp.option.type_tree"][
                        "dhcp.option.dhcp"
                    ],
                ),
            )
            for element in obj
        ]
    except Exception as exception:
        msg = f"Failed to parse DHCP packets due to {exception} "
        raise UseCaseFailure(msg) from exception
    return output


def get_dhcp_packet_by_message(
    trace: list[DHCPTraceData],
    message_type: str,
) -> list[DHCPTraceData]:
    """Get the DHCP packets for the particular message from the pcap file.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Following messages are exchanged
        - Discover, Offer, Request and Ack messages
        - DHCP messages are exchanged

    :param trace: sequence of DHCP packets filtered from captured pcap file
                  and stored in DHCPTraceData
    :type trace: List[DHCPTraceData]
    :param message_type: DHCP message according to RFC2132 and could be any of:

        * DHCPDISCOVER,
        * DHCPOFFER,
        * DHCPREQUEST,
        * DHCPDECLINE,
        * DHCPACK,
        * DHCPACK,
        * DHCPRELEASE,
        * DHCPINFORM

    :type message_type: str
    :return: Sequence of DHCP packets filtered with the message type
    :rtype: List[DHCPTraceData]
    """
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
    return list[DHCPTraceData](
        [
            packet
            for packet in trace
            if dhcp_message_dict.get(message_type) == packet.dhcp_message_type
        ],
    )


def get_all_dhcp_options(packet: DHCPTraceData) -> RecursiveDict:
    """Get all the DHCP options in a DHCP packet.

    :param packet: desired packet from DHCP trace (only one packet)
    :type packet: DHCPTraceData
    :return: all the DHCP options
    :rtype: RecursiveDict
    """
    return {
        key: value
        for key, value in packet.dhcp_packet.items()
        if "dhcp.option.type" in key
    }


def get_dhcp_option_details(packet: DHCPTraceData, option: int) -> RecursiveDict:
    """Get all required option details when option is provided.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify packet capture has option
        - Verify [] is present in DHCP [] message
        - Verify all the Mandatory_Fields are available in DHCP message

    :param packet: the packet data structure
    :type packet: DHCPTraceData
    :param option: DHCP option
    :type option: int
    :raises UseCaseFailure: on failing to find the option
    :return: option Dict along with suboptions
    :rtype: RecursiveDict
    """
    option_data = get_all_dhcp_options(packet)
    # pylint: disable=too-many-nested-blocks
    try:
        for key, value in option_data.items():
            if value == str(option):
                if re.search(r"_\d", key) is None:
                    out = option_data[key + "_tree"]
                else:
                    out = option_data[
                        key.split("_")[0]
                        + "_tree_"
                        + key.split("_")[len(key.split("_")) - 1]
                    ]
                    break
    except KeyError as exception:
        msg = f"Failed to find option {option!s}"
        raise UseCaseFailure(msg) from exception
    return out


def get_dhcp_suboption_details(
    packet: DHCPTraceData,
    option: int,
    suboption: int,
) -> RecursiveDict:
    """Get all required sub option details when option & sub option are provided.

    .. hint:: This Use Case implements statements from the test suite such as:

        - DHCP option [] suboptions
        - Verify [] suboptions are present in DHCP

    :param packet: the packet data structure
    :type packet: DHCPTraceData
    :param option: DHCP option
    :type option: int
    :param suboption: DHCP sub option
    :type suboption: int
    :raises UseCaseFailure: on failing to find the suboption
    :return: suboption dictionary
    :rtype: RecursiveDict
    """
    option_key_dict = {125: "dhcp.option.vi.enterprise_tree"}
    sub_option_data = get_dhcp_option_details(packet, option)
    out = {}
    if option in option_key_dict:
        sub_options = sub_option_data[option_key_dict[option]]
    else:
        sub_options = sub_option_data
    # pylint: disable=too-many-nested-blocks
    try:
        for key, value in sub_options.items():
            if "suboption" in key and value == str(suboption):
                if re.search(r"_\d", key) is None:
                    out = sub_options[key + "_tree"]
                else:
                    out = sub_options[
                        key.split("_")[0]
                        + "_tree_"
                        + key.split("_")[len(key.split("_")) - 1]
                    ]
                    break
        if not out:
            msg = (
                f"Failed to fetch suboption {suboption} for option {option} in"
                f" \n{sub_options}"
            )
            raise UseCaseFailure(msg)
    except KeyError as exception:
        msg = f"Failed to find suboption {suboption!s} "
        raise UseCaseFailure(msg) from exception
    return out


def configure_dhcp_inform(client: LAN | WAN) -> None:
    """Configure dhclient.conf to send DHCPINFORM messages.

    :param client: Device where dhclient.conf needs to be configured for DHCPINFORM,=,
    :type client: LAN | WAN
    """
    msg_type = "send dhcp-message-type 8;"
    out = client.console.execute_command(f"egrep '{msg_type}' /etc/dhcp/dhclient.conf")
    if not re.search(msg_type, out):
        # following statement is unreachable, according to mypy
        # however if you try with out = "" you can execute this branch
        # pylint:disable-next=line-too-long
        client.console.execute_command("cat>>/etc/dhcp/dhclient.conf<<EOF")  # type:ignore[unreachable]
        client.console.execute_command(msg_type)
        client.console.execute_command("EOF")


def remove_dhcp_inform_config(client: LAN | WAN) -> None:
    """Remove the DHCPINFORM related configuration on dhclient.conf.

    :param client: Device from where the configuration needs to be removed.
    :type client: LAN | WAN
    """
    client.console.execute_command(
        "sed -i '/dhcp-message-type 8/d' /etc/dhcp/dhclient.conf"
    )


def configure_dhcp_option125(client: LAN | WAN) -> None:
    """Configure device's vendor-specific suboptions in DHCP option 125.

    This function modifies the device's `dhclient.conf`.

    :param client: Linux device to be configured.
    :type client: LAN | WAN
    """
    # this is an copy/paste of BFv2 boardfarm/lib/dhcpoption.py
    out = client.console.execute_command(
        "egrep 'request option-125' /etc/dhcp/dhclient.conf"
    )
    if not re.search("request option-125,", out):
        # unreachable seems to be a false positive by MyPy
        client.console.execute_command(  # type:ignore[unreachable]
            "sed -i -e "
            "'s|request |\\noption option-125 code 125 = string;\\n\\nrequest option-125, |' "
            "/etc/dhcp/dhclient.conf"
        )
        # details of Text for HexaDecimal value as
        # Enterprise code (3561) 00:00:0D:E9 length  (22)16
        # code 01  length 06  (BFVER0) 42:46:56:45:52:30
        # code 03  length 06  (BFCLAN)  42:46:43:4c:41:4e
        mac = client.get_interface_macaddr(client.iface_dut)
        value = "VAAU" + "".join(mac.split(":")[0:4]).upper()
        encoded_name = str.encode(value)
        hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
        code_02 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
        len_02 = hex(len(value)).replace("0x", "").zfill(2)
        total_len = hex(18 + len(value)).replace("0x", "").zfill(2)
        option_125 = (
            f"00:00:0D:E9:{total_len}:01:06:44:38:42:36:42:37:02:"
            f"{len_02}:{code_02}:03:06:42:46:43:4c:41:4e"
        )
        client.execute_command("cat >> /etc/dhcp/dhclient.conf << EOF")
        client.execute_command(f"send option-125 = {option_125};")
        client.execute_command("")
        client.execute_command("EOF")


def remove_dhcp_option125(client: LAN | WAN) -> None:
    """Remove the information in DHCP option 125.

    This function modifies the Linux device's `dhclient.conf`.

    :param client: Linux device to be configured.
    :type client: LAN | WAN
    """
    # this is an copy/paste of BFv2 boardfarm/lib/dhcpoption.py
    client.console.execute_command(
        "sed -i -e 's|request option-125,|request |' /etc/dhcp/dhclient.conf"
    )
    client.console.execute_command("sed -i '/option-125/d' /etc/dhcp/dhclient.conf")


def _update_trace_data(
    output: list[DHCPV6TraceData], msg: dict[str, Any], element: dict
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
    nested_dict: dict[str, str | dict], val_list: list[str | dict]
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

    :param nested_dict: DHCP nested configuration
    :type nested_dict: dict[str, str  |  dict]
    :param val_list: DHCP values
    :type val_list: list[str  |  dict]
    """
    nested_val_list = []
    nested_key_list = []
    for key, val in nested_dict.items():
        # not using regex as mypy would complain about unreachable code
        if key.startswith("dhcpv6.option.type_str") and isinstance(val, str):
            nested_key_list.append(val)
        elif key.startswith("dhcpv6.option.type_str_tree"):
            nested_val_list.append(val)
        else:
            nested_key_list.append(key)
            nested_val_list.append(val)
    val_list.append(dict(zip(nested_key_list, nested_val_list)))


def _parse_options(
    pkt_dict: dict[str, str | dict[str, str | dict]],
    key_list: list[str],
    val_list: list[str | dict],
) -> dict:
    for pkt_key, pkt_value in pkt_dict.items():
        # not using regex as mypy would complain about unreachable code
        if pkt_key.startswith("dhcpv6.option.type_str") and isinstance(pkt_value, str):
            key_list.append(pkt_value)
        elif pkt_key.startswith("dhcpv6.option.type_str_tree") and isinstance(
            pkt_value, dict
        ):
            _modify_format(pkt_value, val_list)
        else:
            key_list.append(pkt_key)
            val_list.append(pkt_value)
    return dict(zip(key_list, val_list))


def parse_dhcpv6_trace(
    on_which_device: LAN | WAN | Provisioner | LTS,
    fname: str,
    timeout: int = 30,
    additional_args: str = "dhcpv6",
) -> list[DHCPV6TraceData]:
    """Read and filter the DHCPv6 packets from the pcap file.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Check that the following messages are exchanged [] DHCPv6
        - Verify from the packet capture that DHCPv6

    :param on_which_device: Object of the device class where tcpdump is captured
    :type on_which_device: LAN | WAN | Provisioner | CMTS
    :param fname: Name of the captured pcap file
    :type fname: str
    :param timeout: time out for ``tshark`` command to be executed, defaults to 30
    :type timeout: int
    :param additional_args: additional arguments for tshark command to
                            display filtered output, defaults to dhcpv6
    :type additional_args: str
    :raises UseCaseFailure: on failure to parse DHCPv6 data
    :return: sequence of DHCPv6 packets filtered from captured pcap file
    :rtype: List[DHCPV6TraceData]
    """
    output: list[DHCPV6TraceData] = []
    key_list: list[str] = []
    val_list: list[str | dict] = []
    out = on_which_device.tshark_read_pcap(
        fname=fname, additional_args=f"-Y '{additional_args}' -T json", timeout=timeout
    )
    data = "[" + out.split("[", 1)[-1].replace("\r\n", "")
    try:
        obj = JSONDecoder(
            object_pairs_hook=_manage_duplicates,  # type: ignore [arg-type]
        ).decode(data)
    except JSONDecodeError as exception:
        msg = f"Failed to parse JSON due to {exception} "
        raise UseCaseFailure(msg) from exception
    try:
        for element in obj:
            # condition for mv3 eth packets because the packets are
            # not wrapped under Relay message.
            # the below logic updates the dhcp packet dict to have
            # the consistent format across gateways
            if "Relay Message" not in element["_source"]["layers"]["dhcpv6"]:
                pkt_dict = element["_source"]["layers"]["dhcpv6"]
                dhcp_dict = _parse_options(pkt_dict, key_list, val_list)
                _update_trace_data(output, dhcp_dict, element)
            else:
                _update_trace_data(
                    output, element["_source"]["layers"]["dhcpv6"], element
                )
        return output  # noqa: TRY300

    except KeyError as exception:
        msg = f"Failed due to missing key {exception} in dictionary"
        raise UseCaseFailure(msg) from exception
    except TypeError as exception:
        msg = f"Failed due to type error: {exception}"
        raise UseCaseFailure(msg) from exception


def get_dhcpv6_packet_by_message(
    trace: list[DHCPV6TraceData],
    message_type: str,
) -> list[DHCPV6TraceData]:
    """Get the DHCPv6 packets for the particular message from the pcap file.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Following messages are exchanged DHCPv6
        - Discover, Offer, Request and Ack DHCPv6 messages
        - DHCPv6 messages are exchanged

    :param trace: sequence of DHCPv6 packets filtered from captured pcap file
                  and stored in DHCPV6TraceData
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
    :return: Sequence of DHCPv6 packets filtered with the message type
    :rtype: List[DHCPV6TraceData]
    """
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
    return [
        packet
        for packet in trace
        if dhcpv6_message_dict.get(message_type) == packet.dhcpv6_message_type
    ]


def get_all_dhcpv6_options(packet: DHCPV6TraceData) -> DHCPV6Options:
    """Get all the DHCPv6 options in a DHCPv6 packet.

    .. hint:: This Use Case implements statements from the test suite such as:

        - DHCPv6 includes the [] option


    :param packet: desired packet from DHCPv6 trace (only one packet)
    :type packet: DHCPV6TraceData
    :return: all the DHCPv6 options
    :rtype: DHCPV6Options
    """
    if packet.dhcpv6_message_type in [12, 13]:
        out = dict(packet.dhcpv6_packet["Relay Message"]["DHCPv6"].items())
    else:
        out = dict(packet.dhcpv6_packet.items())
    return DHCPV6Options(out)


def dhcp_renew_ipv4(host: LAN | WLAN) -> IPv4Address:
    """Release and renew IPv4 in the device and return IPv4.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Trigger DHCP DISCOVER for the LAN Client IPv4 acquisition
        - Verify the IP acquisition on LAN devices
        - Check if the LAN Client connected to CPE obtains both IPv4 and IPv6 address

    :param host: host where the IP has to be renewed
    :type host: LAN | WLAN
    :return: IPv4 address of the device
    :rtype: IPv4Address
    """
    host.release_dhcp(host.iface_dut)
    host.renew_dhcp(host.iface_dut)
    return IPv4Address(host.get_interface_ipv4addr(host.iface_dut))


def dhcp_renew_stateful_ipv6(host: LAN | WLAN) -> IPv6Address:
    """Release and renew stateful IPv6 in the device and return IPv6.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Initiate the IPv6 acquisition from LAN Ethernet client
        - Initiate the IPv6 process from LAN Ethernet client
        - Release and renew IPv6 address on LAN client

    :param host: host where the IP has to be renewed
    :type host: LAN | WLAN
    :return: IPv6 address of the device
    :rtype: IPv6Address
    """
    host.release_ipv6(host.iface_dut)
    host.renew_ipv6(host.iface_dut)
    return IPv6Address(host.get_interface_ipv6addr(host.iface_dut))


def dhcp_renew_stateless_ipv6(host: LAN | WLAN) -> IPv6Address:
    """Release and renew stateless IPv6 in the device and return IPv6.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Initiate the IPv6 stateless acquisition from LAN Ethernet client
        - Initiate the IPv6 stateless  process from LAN Ethernet client
        - Release and renew stateless IPv6 address on LAN client

    :param host: host where the IP has to be renewed
    :type host: LAN | WLAN
    :return: IPv6 address of the device
    :rtype: IPv6Address
    """
    host.release_ipv6(host.iface_dut, stateless=True)
    host.set_link_state(host.iface_dut, "down")
    host.set_link_state(host.iface_dut, "up")
    host.renew_ipv6(host.iface_dut, stateless=True)
    sleep(10)
    return IPv6Address(host.get_interface_ipv6addr(host.iface_dut))
