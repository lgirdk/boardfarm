# ruff: noqa

"""Common Networking use cases."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

    from boardfarm3.lib.networking import HTTPResult
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN

_LOGGER = logging.getLogger(__name__)


def ping(  # noqa: PLR0913
    device: LAN | WLAN | WAN,
    ping_ip: str,
    ping_count: int = 4,
    ping_interface: str | None = None,
    timeout: int = 50,
    json_output: bool = False,
) -> bool | dict[str, Any]:
    """Ping remote host ip.

    Return True if ping has 0% loss or parsed output in JSON if
    json_output=True flag is provided.

    :param device: device on which ping is performed
    :type device: LAN
    :param ping_ip: ip to ping
    :type ping_ip: str
    :param ping_count: number of concurrent pings, defaults to 4
    :type ping_count: int
    :param ping_interface: ping via interface, defaults to None
    :type ping_interface: str | None
    :param timeout: timeout, defaults to 50
    :type timeout: int
    :param json_output: True if ping output in dictionary format else False,
        defaults to False
    :type json_output: bool
    :return: bool or dict of ping output
    :rtype: bool | dict[str, Any]
    """
    return device.ping(
        ping_ip,
        ping_count,
        ping_interface,
        timeout=timeout,
        json_output=json_output,
    )


@contextmanager
def start_http_server(
    device: LAN | WAN,
    port: int | str,
    ip_version: str | int,
) -> Generator:
    """Start http server on given client.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start the HTTP server on the [] client

    :param device: device on which server will start
    :type device: LAN | WAN
    :param port: port on which the server listen for incomming connections
    :type port: int | str
    :param ip_version: ip version of server values can strictly be 4 or 6
    :type ip_version: str | int
    :raises ValueError: wrong ip_version value is given in api call
    :yield: PID of the http server process
    """
    port = str(port)
    ip_version = str(ip_version)
    if ip_version not in ["4", "6"]:
        reason = f"Invalid ip_version argument {ip_version}."
        raise ValueError(reason)
    # stop http service if running
    device.stop_http_service(port)
    try:
        yield device.start_http_service(port, ip_version)
    finally:
        device.stop_http_service(port)


def http_get(
    device: LAN | WAN, url: str, timeout: int = 20, options: str = ""
) -> HTTPResult:
    """Check if the given HTTP server is running.

    This Use Case executes a curl command with a given timeout from the given
    client. The destination is specified by the url parameter

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify HTTP server is accessible from [] via erouter IP
        - Verify that the HTTP server running on the client is accessible
        - Try to connect to the HTTP server from [] client

    :param device: the device from where HTTP response to get
    :type device: LAN | WAN
    :param url: URL to get the response
    :type url: str
    :param timeout: connection timeout for the curl command in seconds, default 20
    :type timeout: int
    :param options: additional options to pass to the curl command, defaults to ""
    :type options: str
    :return: parsed HTTP get response
    :rtype: HTTPResult
    """
    return device.http_get(url, timeout, options)
