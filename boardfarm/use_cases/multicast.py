"""Multicast Use cases.

This will include connecting to a multicast stream via Iperf, ip mroute
or smcroute.
"""
from dataclasses import dataclass
from io import StringIO
from ipaddress import ip_address
from time import sleep
from typing import List, Optional, Union

import pandas

from boardfarm.exceptions import BFTypeError, UseCaseFailure
from boardfarm.use_cases.descriptors import LanClients, WanClients

IperfDevice = Union[LanClients, WanClients]


@dataclass
class IPerfSession:
    """Store details of IPerf server session."""

    device: IperfDevice
    pid: str
    address: str
    port: int
    output_file: str
    time: int = 0


@dataclass
class IPerfResult:
    """Store results of IPerf server session."""

    _data: Optional[pandas.DataFrame]

    @property
    def bandwidth(self) -> Optional[str]:
        """Return resultant bandwidth in Mbps."""
        return (
            self._data["bandwidth"].iloc[-1] / 1000000
            if self._data is not None
            else None
        )

    @property
    def total_loss(self) -> Optional[str]:
        """Return no. of datagrams lost."""
        return self._data["lost"].iloc[-1] if self._data is not None else None

    @property
    def result(self) -> Optional[pandas.DataFrame]:
        """Return the entire result."""
        return self._data


def kill_all_iperf(device_list: List[IperfDevice]):
    """Kill all iperf session on target devices.

    This should be called for cleaning purposes.

    :param device_name: list of target devices
    :type device_name: List[IperfDevice]
    """
    for obj in device_list:
        dev = obj._obj
        dev.sendcontrol("c")
        dev.expect_prompt()
        dev.check_output("for i in $(pgrep iperf); do kill -9 $i; done")


def _iperf_session_check(dev, multicast_address: str, port: int):
    if not ip_address(multicast_address).is_multicast:
        raise BFTypeError(f"{multicast_address} is not a multicast address")

    # check before running that there should be no iperf sessions with same port
    if dev.check_output(f"pgrep iperf -a | grep {port}"):
        raise UseCaseFailure(
            f"{dev.name} already has an iperf session with port {port}"
        )


def join_iperf_multicast_group(
    device: IperfDevice, multicast_address: str, port: int
) -> IPerfSession:
    """To start an iperf server binding to a multicast address in background.

    Session will have the following parameters by default:
    - 1s interval between periodic bandwidth, jitter, and loss reports.
    - bandwidth set to 30 MBps

    :param device_name: device descriptor object that runs iperf.
    :type device_name: IperfDevice
    :param multicast_address: multicast IP address
    :type multicast_address: str
    :param port: multicast port number
    :type port: int
    :raises BFTypeError: if address is not a multicast address
    :raises UseCaseFailure: if session with port exists
    :return: object holding data on the IPerf Session
    :rtype: IPerfSession
    """
    dev = device._obj
    _iperf_session_check(dev, multicast_address, port)
    fname = f"mclient_{port}.txt"

    # run iperf, format result as CSV
    dev.check_output(
        f"iperf -s -p {port} -u -B {multicast_address} -i 1 -w 30.0m"
        + f" -f m -y C > {fname} &"
    )

    pid = dev.check_output(f"pgrep iperf -a | grep {port} | awk '{{print$1}}'")
    return IPerfSession(device, pid, multicast_address, port, fname)


def leave_iperf_multicast_group(session: IPerfSession) -> IPerfResult:
    """To stop an iperf server bounded to a multicast address.

    Executes a kill -15 <iperf session pid> on target device

    :param session: Session object created during the join
    :type session: IPerfSession
    :raises UseCaseFailure: if the IPerf session does not exist on target
    :return: Iperf result
    :rtype: IPerfResult
    """
    dev = session.device._obj

    if not dev.check_output(f"pgrep iperf -a | grep {session.port}"):
        # Something is wrong, there should be a process ID always.
        raise UseCaseFailure(
            f"iperf session with port {session.port} does "
            + f"not exist on {session.device_name}"
        )

    # kill -15 iperf session
    dev.check_output(f"kill -15 {session.pid}")
    out = dev.check_output(f"cat {session.output_file}")

    # remove the file after reading results
    dev.check_output(f"rm {session.output_file}")
    if not out.strip():
        return IPerfResult(None)

    csv = pandas.read_csv(StringIO(out.strip()))
    cols = [
        "timestamp",
        "source_address",
        "source_port",
        "destination_address",
        "destination_port",
        "id",
        "interval",
        "transferred_bytes",
        "bandwidth",
        "jitter",
        "lost",
        "total",
    ]

    df = pandas.DataFrame(csv.iloc[:, :-2].values, columns=cols)
    return IPerfResult(df)


def start_iperf_multicast_stream(
    device: IperfDevice, multicast_address: str, port: int, time: int, bandwidth: int
) -> IPerfSession:
    """To start an iperf client sending data on multicast address in background.

    Session will have the following parameters by default:
    - TTL value set to 5

    :param device_name: device descriptor object that runs iperf.
    :type device_name: IperfDevice
    :param multicast_address: multicast IP address
    :type multicast_address: str
    :param port: multicast port number
    :type port: int
    :param time: total time the session should run for
    :type time: int
    :param bandwidth: bandwidth of data to be sent (in Mbps)
    :type bandwidth: int
    :raises BFTypeError: if address is not a multicast address
    :raises UseCaseFailure: if session with port exists
    :return: object holding data on the IPerf Session
    :rtype: IPerfSession
    """
    dev = device._obj
    _iperf_session_check(dev, multicast_address, port)
    fname = f"mserver_{port}.txt"

    dev.check_output(
        f"iperf -c {multicast_address} -p {port} -u --ttl 5"
        + f" -t {time} -b {bandwidth}m > {fname} &"
    )

    pid = dev.check_output(f"pgrep iperf -a | grep {port} | awk '{{print$1}}'")
    return IPerfSession(device, pid, multicast_address, port, fname, time)


def wait_for_multicast_stream_to_end(session_list: List[IPerfSession]) -> None:
    """Wait for all multicast stream sessions to end.

    The usecase will wait for a time equal to session with the highest wait time.
    If a session from the list does not exit within the max wait time, then
    throw an error.

    :param session_list: List of IPerfSessions
    :type session_list: List[IPerfSession]
    :raises BFTypeError: if empty list is passed
    :raises UseCaseFailure: if a session fails to exit.
    """
    if not session_list:
        raise BFTypeError("Cannot pass an empty session list!")

    max_time_to_wait = max(session.time for session in session_list)

    # Should expect all streams to be closed by now
    # This is not asyncio, no high expectations
    sleep(max_time_to_wait)

    failed_sessions = []
    for session in session_list:
        # try twice before raising exception.
        dev = session.device._obj
        for _ in range(2):
            if not dev.check_output(f"pgrep iperf -a | grep {session.port}"):
                break
            sleep(1)
        else:
            dev.check_output(f"kill -9 {session.pid}")
            failed_sessions.append(
                f"{session.address}:{session.port} did not exit within {session.time}s"
            )
        dev.check_output(f"rm {session.output_file}")

    if failed_sessions:
        raise UseCaseFailure("Following sessions failed:\n".join(failed_sessions))
