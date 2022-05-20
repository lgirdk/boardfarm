"""Networking use cases."""

from contextlib import contextmanager
from typing import Generator, Union

from boardfarm.templates.lan import LAN
from boardfarm.templates.wan import WAN


@contextmanager
def start_http_server(
    device: Union[LAN, WAN], port: Union[int, str], ip_version: Union[str, int]
) -> Generator:
    """Start http server on given client.

    :param device: device on which server will start
    :param port: port on which the server listen for incomming connections
    :param ip_version: ip version of server values can strictly be 4 or 6
    :raises ValueError: wrong ip_version value is given in api call
    :raises UseCaseFailure: if the port is being used by other process
    :yield: PID of the http server process
    """
    port = str(port)
    ip_version = str(ip_version)
    if ip_version not in ["4", "6"]:
        raise ValueError(f"Invalid ip_version argument {ip_version}.")
    # stop http service if running
    device.stop_http_service(port)
    try:
        yield device.start_http_service(port, ip_version)
    finally:
        device.stop_http_service(port)
