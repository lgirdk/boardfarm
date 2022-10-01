"""Boardfarm common utilities module."""

import os
import time
from ipaddress import IPv4Address
from typing import Any, Callable

from netaddr import EUI, mac_unix_expanded


def get_nth_mac_address(mac_address: str, nth_number: int) -> str:
    """Get nth mac address from base mac address.

    :param mac_address: base mac address
    :param nth_number: n'th number from base mac address
    :return: n'th mac address
    """
    return str(EUI(int(EUI(mac_address)) + nth_number, dialect=mac_unix_expanded))


def get_pytest_name() -> str:
    """Get the test name from the test filename during runtime.

    :return: current test name
    """
    return (
        (os.environ.get("PYTEST_CURRENT_TEST").split(" (setup)")[0])
        .split("::")[1]
        .replace(" ", "_")
    )


def ip_pool_to_list(start_ip: IPv4Address, end_ip: IPv4Address) -> list[IPv4Address]:
    """Generate ip address list based on ip pool boundaries.

    :param start_ip: first ip of the pool
    :type start_ip: IPv4Address
    :param end_ip: last ip of the pool
    :type end_ip: IPv4Address
    :return: list of ip address based on min ip address and maximum
     ip address of the pool
    :rtype: List[IPv4Address]
    """
    ip_list = []
    while end_ip >= start_ip and start_ip != end_ip + 1:
        ip_list.append(start_ip)
        start_ip += 1
    return ip_list


def retry(func_name: Callable, max_retry: int, *args: str) -> Any:
    """Retry a function if the output of the function is false.

    TODO: consider replacing this with Tenacity or other solutions.

    :param func_name: name of the function to retry
    :type func_name: Object
    :param max_retry: Maximum number of times to be retried
    :type max_retry: Integer
    :param args: Arguments passed to the function
    :type args: args
    :return: Output of the function if function is True
    :rtype: Boolean (True/False) or None Type(None)
    """
    output = None
    for _ in range(max_retry):
        output = func_name(*args)
        if output and output != "False":
            return output
        time.sleep(5)
    return output
