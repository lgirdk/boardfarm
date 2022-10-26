"""Boardfarm common utilities module."""

import logging
import os
import time
from ipaddress import IPv4Address
from typing import Any, Callable, Union

from netaddr import EUI, mac_unix_expanded

_LOGGER = logging.getLogger(__name__)


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
    :return: list of ip addresses based on min ip address and maximum
             ip address of the pool
    :rtype: list[IPv4Address]
    """
    ip_list = []
    while end_ip >= start_ip and start_ip != end_ip + 1:
        ip_list.append(start_ip)
        start_ip += 1
    return ip_list


# TODO: consider replacing this with Tenacity or other solutions.
def retry(func_name: Callable, max_retry: int, *args: Any) -> Any:
    """Retry a function if the output of the function is false.

    :param func_name: name of the function to retry
    :type func_name: Callable
    :param max_retry: maximum number of times to be retried
    :type max_retry: int
    :param args: arguments to the function
    :type args: Tuple[Any, ...]
    :return: output of the function
    :rtype: Any
    """
    for _ in range(max_retry - 1):
        output = func_name(*args)
        if output and output != "False":
            return output
        time.sleep(5)
    return func_name(*args)


def retry_on_exception(
    method: Callable, args: Union[list, tuple], retries: int = 10, tout: int = 5
) -> Any:
    """Retry a method if any exception occurs.

    Eventually, at last, throw the exception.
    NOTE: args must be a tuple, hence a 1 arg tuple is (<arg>,)

    :param method: name of the function to retry
    :type method: Callable
    :param args: arguments to the function
    :type args: Union[List, Tuple]
    :param retries: maximum number of retries when a exception occur,defaults
                    to 10. When negative, no retries are made.
    :type retries: int
    :param tout: sleep time after every exception occur, defaults to 5
    :type tout: int
    :return: output of the function
    :rtype: Any
    """
    for re_try in range(1, retries):
        try:
            return method(*args)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("method failed %d time (%s)", re_try, exc)
            time.sleep(tout)
    return method(*args)
