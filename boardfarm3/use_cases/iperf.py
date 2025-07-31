"""Common Iperf use cases."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from boardfarm3.exceptions import CodeError, UseCaseFailure
from boardfarm3.lib.dataclass.network_models import IPerf3TrafficGenerator

if TYPE_CHECKING:
    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN


def start_iperf_ipv4(  # pylint: disable=too-many-arguments,R0914  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    direction: str | None = None,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    client_port: int | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv4 downstream traffic from source device to destination device.

    Starts the iPerf3 server on a traffic receiver and triggers the IPv4 only
    traffic from source device.

    if unable to start traffic sender, stops the process for receiver

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance
    :type destination_device: LAN | WAN | WLAN
    :param source_port: source port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param direction: `--reverse` to run in reverse mode (server sends, client receives)
        defaults to None
    :type direction: str | None
    :param destination_port: destination port to listen on/connect to
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None
    :param destination_ip: IPv4 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param client_port: client port from where the traffic is getting started
    :type client_port: int | None
    :param udp_only: to be used if protocol is UDP only,
        backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip = (
        destination_device.get_interface_ipv4addr(destination_device.iface_dut)
        if destination_ip is None
        else destination_ip
    )
    destination_port = source_port if destination_port is None else destination_port
    dest_pid, server_log_file = destination_device.start_traffic_receiver(
        destination_port, bind_to_ip=bind_receiver_ip, ip_version=4, udp_only=udp_only
    )
    try:
        source_pid, client_log_file = source_device.start_traffic_sender(
            dest_ip,
            source_port,
            bind_to_ip=bind_sender_ip,
            ip_version=4,
            udp_protocol=udp_protocol,
            time=time,
            direction=direction,
            client_port=client_port,
            udp_only=udp_only,
        )
    # handles scenario where server started but unable to start traffic sender(client)
    # IPerf3TrafficGenerator is sent with empty pid for receiver, so that sender's
    # process can be killed by test case.
    except CodeError:
        source_pid = None
        client_log_file = ""
        stop_iperf_traffic(
            IPerf3TrafficGenerator(
                source_device, source_pid, destination_device, dest_pid
            )
        )
    return IPerf3TrafficGenerator(
        source_device,
        source_pid,
        destination_device,
        dest_pid,
        server_log_file,
        client_log_file,
    )


def start_iperf_ipv6(  # pylint: disable=too-many-arguments,R0914  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    direction: str | None = None,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    client_port: int | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv6 downstream traffic from source device to destination device.

    Starts the iPerf3 server on a traffic receiver and triggers the IPv6 only
    traffic from source device.

    if unable to start traffic sender, stops the process for receiver

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance
    :type destination_device: LAN | WAN | WLAN
    :type direction: Literal["--reverse", "--bidir"]
    :param source_port: source port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param direction: `--reverse` to run in reverse mode (server sends, client receives)
        defaults to None
    :type direction: str | None
    :param destination_port: destination port to listen on/connect to
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None
    :param destination_ip: IPv6 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param client_port: client port from where the traffic is getting started
    :type client_port: int | None
    :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    dest_ip6 = (
        destination_device.get_interface_ipv6addr(destination_device.iface_dut)
        if destination_ip is None
        else destination_ip
    )
    destination_port = source_port if destination_port is None else destination_port
    dest_pid, server_log_file = destination_device.start_traffic_receiver(
        destination_port, bind_to_ip=bind_receiver_ip, ip_version=6, udp_only=udp_only
    )
    try:
        source_pid, client_log_file = source_device.start_traffic_sender(
            dest_ip6,
            source_port,
            bind_to_ip=bind_sender_ip,
            ip_version=6,
            udp_protocol=udp_protocol,
            time=time,
            direction=direction,
            client_port=client_port,
            udp_only=udp_only,
        )
    # handles scenario where server started but unable to start traffic sender(client)
    # IPerf3TrafficGenerator is sent with empty pid for receiver, so that sender's
    # process can be killed by test case.
    except CodeError:
        source_pid = None
        client_log_file = ""
        stop_iperf_traffic(
            IPerf3TrafficGenerator(
                source_device, source_pid, destination_device, dest_pid
            )
        )
    return IPerf3TrafficGenerator(
        source_device,
        source_pid,
        destination_device,
        dest_pid,
        server_log_file,
        client_log_file,
    )


def start_iperf_ipv4_bidirectional(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv4 bidirectional traffic from source device to destination device.

    Executes the initiate_v4_traffic Use Case in bidirectional mode.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance
    :type destination_device: LAN | WAN | WLAN
    :param source_port: source port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param destination_port: destination port to listen on/connect to
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None
    :param destination_ip: IPv4 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    return start_iperf_ipv4(
        source_device=source_device,
        destination_device=destination_device,
        direction="--bidir",
        source_port=source_port,
        time=time,
        udp_protocol=udp_protocol,
        destination_port=destination_port,
        bind_sender_ip=bind_sender_ip,
        bind_receiver_ip=bind_receiver_ip,
        destination_ip=destination_ip,
        udp_only=udp_only,
    )


def set_device_interface_state(
    device: LAN | WAN | WLAN,
    interface: str,
    action: Literal["up", "down"],
) -> None:
    """Toggle the interface based on the action passed.

    :param device: device instance
    :type device: LAN | WAN | WLAN
    :param interface: name of the interface
    :type interface: str
    :param action: up or down
    :type action: Literal["up", "down"]
    """
    device.set_link_state(interface, action)


def start_iperf_ipv6_bidirectional(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv6 bidirectional traffic from source device to destination device.

    Executes the initiate_v6_traffic Use Case in bidirectional mode.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance for iperf client
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance for iPerf server
    :type destination_device: LAN | WAN | WLAN
    :param source_port: server port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param destination_port: destination port to listen on/connect to, defaults to None
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address,, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None,
    :param destination_ip: IPv6 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    return start_iperf_ipv6(
        source_device=source_device,
        destination_device=destination_device,
        direction="--bidir",
        source_port=source_port,
        time=time,
        udp_protocol=udp_protocol,
        destination_port=destination_port,
        bind_sender_ip=bind_sender_ip,
        bind_receiver_ip=bind_receiver_ip,
        destination_ip=destination_ip,
        udp_only=udp_only,
    )


def start_iperf_ipv4_downstream(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv4 downstream traffic from source device to destination device.

    Executes the initiate_v4_traffic Use Case in downstream mode.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance
    :type destination_device: LAN | WAN | WLAN
    :param source_port: source port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param destination_port: destination port to listen on/connect to
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None
    :param destination_ip: IPv4 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    return start_iperf_ipv4(
        source_device=source_device,
        destination_device=destination_device,
        direction="--reverse",
        source_port=source_port,
        time=time,
        udp_protocol=udp_protocol,
        destination_port=destination_port,
        bind_sender_ip=bind_sender_ip,
        bind_receiver_ip=bind_receiver_ip,
        destination_ip=destination_ip,
        udp_only=udp_only,
    )


def start_iperf_ipv6_downstream(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    source_device: LAN | WAN | WLAN,
    destination_device: LAN | WAN | WLAN,
    source_port: int,
    time: int,
    udp_protocol: bool,
    destination_port: int | None = None,
    bind_sender_ip: str | None = None,
    bind_receiver_ip: str | None = None,
    destination_ip: str | None = None,
    udp_only: bool | None = None,
) -> IPerf3TrafficGenerator:
    """Initiate IPv6 downstream traffic from source device to destination device.

    Executes the initiate_v6_traffic Use Case with downstream mode.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start an iPerf server on LAN/WAN host
        - Start an iPerf client on LAN/WAN host

    :param source_device: device instance for iperf client
    :type source_device: LAN | WAN | WLAN
    :param destination_device: device instance for iPerf server
    :type destination_device: LAN | WAN | WLAN
    :param source_port: server port to listen on/connect to
    :type source_port: int
    :param time: time in seconds to transmit
    :type time: int
    :param udp_protocol: use UDP rather than TCP
    :type udp_protocol: bool
    :param destination_port: destination port to listen on/connect to, defaults to None
    :type destination_port: int | None
    :param bind_sender_ip: bind to the interface associated with the
        client address,, defaults to None
    :type bind_sender_ip: str | None
    :param bind_receiver_ip: bind to the interface associated with the
        host address, defaults to None
    :type bind_receiver_ip: str | None,
    :param destination_ip: IPv6 address used for iPerf traffic, defaults to None
    :type destination_ip: str | None
    :param udp_only: to be used if protocol is UDP only,
            backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :return: IPerf3TrafficGenerator data class that holds
        sender/receiver devices, their process ids and log
        file details
    :rtype: IPerf3TrafficGenerator
    """
    return start_iperf_ipv6(
        source_device=source_device,
        destination_device=destination_device,
        direction="--reverse",
        source_port=source_port,
        time=time,
        udp_protocol=udp_protocol,
        destination_port=destination_port,
        bind_sender_ip=bind_sender_ip,
        bind_receiver_ip=bind_receiver_ip,
        destination_ip=destination_ip,
        udp_only=udp_only,
    )


def get_iperf_logs(iperf_data: IPerf3TrafficGenerator) -> dict:
    """Check logs and returns traffic flow.

    :param iperf_data: IPerf3TrafficGenerator, holds sender and reciever info.
    :type iperf_data: IPerf3TrafficGenerator
    :return: traffic logs of both server and client.
    :rtype: dict
    """
    server_logs = iperf_data.traffic_receiver.get_iperf_logs(iperf_data.server_log_file)
    client_logs = iperf_data.traffic_sender.get_iperf_logs(iperf_data.client_log_file)
    return {"client_logs": client_logs, "server_logs": server_logs}


def stop_iperf_traffic(iperf_generator: IPerf3TrafficGenerator) -> None:
    """Stop the iPerf3 processes on sender as well as receiver.

    :param iperf_generator: data class that holds sender/receiver devices and
        their process IDs
    :type iperf_generator: IPerf3TrafficGenerator
    :raises UseCaseFailure: when either iPerf3 server or client PID can't be killed
    """
    sender = (
        iperf_generator.traffic_sender.stop_traffic(iperf_generator.sender_pid)
        if iperf_generator.traffic_sender and iperf_generator.sender_pid
        else None
    )

    receiver = (
        iperf_generator.traffic_receiver.stop_traffic(iperf_generator.receiver_pid)
        if iperf_generator.traffic_receiver and iperf_generator.receiver_pid
        else None
    )

    if (iperf_generator.sender_pid and not sender) or (
        iperf_generator.receiver_pid and not receiver
    ):
        msg = (
            "Either Sender(Client) or Receiver(Server) process cannot be killed:",
            f"{sender=} - {receiver=}",
        )
        raise UseCaseFailure(msg)


def parse_iperf_logs(
    iperf_logs: str, is_client_log: bool = False, udp_only: bool | None = None
) -> dict[str, str]:
    """Parse iperf logs and return bitrate, transfer etc.

    :param iperf_logs: client or server logs
    :type iperf_logs: str
    :param is_client_log: True if client logs to be prased, defaults to False
    :type is_client_log: bool
    :param udp_only: to be used if protocol is UDP only,
        backward compatibility with iperf version 2
    :type udp_only: bool, optional
    :raises UseCaseFailure: If unable to parse output
    :return: dict with throughput, transfer, interval values.
    :rtype: dict[str, str]
    """
    if udp_only:
        search_pattern = ""
    else:
        search_pattern = r"[\d]+\s+sender" if is_client_log else "receiver"
    if matching_object := re.search(
        r"([\d.]+-[\d.]+)\s+sec\s+([\d.]+\s+\w?Bytes)\s+([\d.]+\s+\w?bits/sec)\s+"
        f"{search_pattern}",
        iperf_logs,
    ):
        interval, transfer, bitrate = matching_object.groups()
        return {"Interval": interval, "Transfer": transfer, "Bitrate": bitrate}
    msg = "Sender / Receiver data not found in the output."  # type:ignore[unreachable]
    raise UseCaseFailure(msg)
