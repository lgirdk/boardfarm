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
        regex = f"((\d+\.\d+).*{msg.src_ip}.*{msg.dest_ip}.*{msg.message})"
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
