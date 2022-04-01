#!/usr/bin/env python3
import re

from boardfarm.lib.network_testing import tshark_read


def duration_between_packets(
    device, capture_file, msg_list, user=None, count=10, **kwargs
):
    """Calculate the time duration between two packets until count

    :param device: lan or wan
    :type device: object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: str
    :param msg_list: list of 'sip_msg' named_tuples having the src and dest IP's.
    :type msg_list: list
    :param user: Endpoint sip user
    :type user: int/str
    :param count: No.of packet duration required + 1
    :type count: int
    :param kwargs: kwargs for filter_opt and remove pcap
    :return: return the interval between the packets
    :rtype: dict
    """
    filter_opt = kwargs.get("filter_str", f"""-Y "(sip.from.user == \\"{user}\\")" """)
    rm_file = kwargs.get("rm_file", True)
    time_list = []
    output = tshark_read(device, capture_file, filter_str=filter_opt, rm_file=rm_file)
    split_out = output.splitlines()
    for msg in msg_list:
        regex = rf"((\d+\.\d+).*{msg.src_ip}.*{msg.dest_ip}.*{msg.message})"
        for line in split_out:
            match = re.search(regex, line)
            if match:
                time_list.append(match.group(2).strip())
            if len(time_list) == count:
                break
    interval_dict = {}
    for idx in range(len(time_list) - 2):
        interval_dict[f"{idx}-{idx+1}"] = round(
            float(time_list[idx + 1]) - float(time_list[idx]), 1
        )
    return interval_dict


def get_sip_attributes(device, capture_file, src_ip, sip_auth=False):
    """Return the SIP attributes like from/to URI and Auth parameters from SIP packet

    :param device: lan or wan
    :type device: object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: str
    :param src_ip: Source IP address of packet
    :type src_ip: str
    :param sip_auth: Include SIP authentication parameters into return dict default to False
    :type sip_auth: bool
    :return: return sip attributes
    :rtype: dict
    """
    output = tshark_read(
        device,
        capture_file,
        packet_details=True,
        filter_str=f"ip.src == {src_ip} and sip.Method == 'INVITE'",
    )
    sip_attr = {}
    try:
        sip_attr["from_URI"] = re.search(r"From:.*sip:(.*)>", output).group(1)
        sip_attr["to_URI"] = re.search(r"To:.*sip:(.*)", output).group(1).strip()
        if sip_auth:
            sip_attr["SIP_auth"] = (
                re.search(r"Proxy-Authorization:\s\w+(.*)", output).group(0).strip()
            )
        return sip_attr
    except AttributeError:
        raise ValueError(f"{capture_file} doesn't have packet matching with filter")
