#!/usr/bin/env python3
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import ipaddress
import logging
import re
from collections import namedtuple
from contextlib import suppress

import netaddr
from pexpect.exceptions import TIMEOUT

from boardfarm.exceptions import ConnectionRefused, PexpectErrorTimeout, RTPNotFound
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.DeviceManager import device_type

sip_msg = namedtuple("SIPData", ["src_ip", "dest_ip", "message"])
rtp_msg = namedtuple("RTPMessage", ["src_ip", "dest_ip"])
logger = logging.getLogger("bft")


def tcpdump_capture(
    device,
    interface,
    port=None,
    capture_file="pkt_capture.pcap",
    filters=None,
    return_pid=False,
    additional_filters="",
):
    """Capture network traffic using tcpdump.
    Note: This function will keep capturing until you Kill tcpdump.
    The kill_process method can be used to kill the process.

    :param device: lan or wan
    :type device: Object
    :param interface: interface on which the packets to be captured (eg: eth0)
    :type interface: String
    :param port: Port number to capture. Can be a single port or range of ports (for https: 443 or 443-433)
    :type port: String
    :param capture_file: Filename to create in which packets shall be stored. Defaults to 'pkt_capture.pcap'
    :type capture_file: String, Optional
    :param filters: dictionary of additional filters and filter_values as key value pair (eg: {"-v":"","-c": "4"})
    :type filters: dict
    :param return_pid: flag to return pid number (as a string) instead of the whole command output.Defaults to False
    :type return_pid: boolean
    :return: Console output of tcpdump sendline command/pid depends on the return_pid flag
    :rtype: string
    """
    base = f"tcpdump -Z root -C 2 -W 10  -U -i {interface} -n -w {capture_file} "
    run_background = " &"
    filter_str = " ".join([" ".join(i) for i in filters.items()]) if filters else ""
    filter_str += additional_filters
    if port:
        device.sudo_sendline(
            base + f"'portrange {port}' " + filter_str + run_background
        )
    else:
        device.sudo_sendline(base + filter_str + run_background)
    device.expect_exact(f"tcpdump: listening on {interface}")
    if return_pid:
        return re.search(r"(\[\d{1,10}\]\s(\d{1,6}))", device.before).group(2)
    return device.before


def kill_process(device, process="tcpdump", pid=None, sync=True, port=None):
    """Kill any active process.

    :param device: lan or wan
    :type device: Object
    :param process: process to kill, defaults to tcpdump
    :type process: String, Optional
    :param pid: process id to kill, defaults to None
    :type pid: String, Optional
    :param sync: Marked False if sync should not be executed;defaults to True
    :type sync: Boolean,optional
    :param port: port number to kill
    :type port: int
    :return: Console output of sync sendline command after kill process
    :rtype: string
    """
    if pid:
        device.sudo_sendline(f"kill {pid}")
    elif port:
        device.sudo_sendline(r"kill $(lsof -t -i:%s)" % str(port))
    else:
        device.sudo_sendline(f"killall {process}")
    device.expect(device.prompt)
    if sync:
        with suppress(TIMEOUT):
            for _ in range(3):
                device.sudo_sendline("sync")
                device.expect(device.prompt)
                if "Done" in device.before:
                    break
    return device.before


def tcpdump_read(device, capture_file, protocol="", opts="", timeout=30, rm_pcap=True):
    """Read the tcpdump packets and deletes the capture file after read

    :param device: lan or wan
    :type device: Object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :param protocol: protocol to filter. Defaults to ''
    :type protocol: String, Optional
    :param opts: can be more than one parameter but it should be joined with "and" eg: ('host '+dest_ip+' and port '+port). Defaults to ''
    :type opts: String, Optional
    :param timeout: timeout after executing the tcpdump read; default 30 seconds
    :type timeout: int
    :param rm_pcap: Argument determining if the pcap file needs to be removed.
    :type rm_pcap: Boolean default to True
    :return: Output of tcpdump read command.
    :rtype: string
    """
    if opts:
        protocol = protocol + " and " + opts
    device.sudo_sendline(f"tcpdump -n -r {capture_file} {protocol}")
    device.expect(device.prompt, timeout=timeout)
    output = device.before
    if rm_pcap:
        device.sudo_sendline(f"rm {capture_file}")
        device.expect(device.prompt)
    return output


def tshark_read(
    device,
    capture_file,
    packet_details=False,
    filter_str=None,
    timeout=60,
    rm_file=True,
):
    """Read the packets via tshark

    :param device: lan or wan...
    :type device: Object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :param packet_details: output of packet tree (Packet Details)
    :type packet_details: Bool
    :param filter_str: capture filter, ex. 'data.len == 1400'
    :type filter_str: String
    :param timeout: timeout after executing the read command; default is 30 seconds
    :type timeout: int
    :param rm_file: Flag to remove capture file
    :type rm_file: bool
    """
    command_string = f"tshark -r {capture_file} "
    if packet_details:
        command_string += "-V "
    if filter_str:
        command_string += f"{filter_str}"

    device.sendline(command_string)
    device.expect(device.prompt, timeout=timeout)
    output = device.before
    if rm_file:
        device.sudo_sendline(f"rm {capture_file}")
        device.expect(device.prompt)
    return output


def sip_read(device, capture_file, rm_pcap_file=True):
    """Read and filter SIP packets from the captured file.
    The Session Initiation Protocol is a signaling protocol used for initiating, maintaining, and
    terminating real-time sessions that include voice, video and messaging applications

    :param device: lan or wan
    :type device: Object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :return: Output of tshark read command.
    :rtype: string
    """

    device.sudo_sendline(f"tshark -r {capture_file} -Y sip")
    device.expect(device.prompt)
    output_sip = device.before
    if rm_pcap_file:
        device.sudo_sendline(f"rm {capture_file}")
        device.expect(device.prompt)
    return output_sip


def rtp_read_verify(device, capture_file, msg_list=None, rm_pcap=True):
    """To filter RTP packets from the captured file and verify. Delete the capture file after verify.
    Real-time Transport Protocol is for delivering audio and video over IP networks.

    :param device: lan or wan
    :type device: Object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :param msg_list: list of 'rtp_msg' named_tuples having the source and
                    destination IPs of the endpoints.
    :type msg_list: list
    :return: True if RTP messages found else False
    :rtype: Boolean
    """
    device.sudo_sendline(f"tshark -r {capture_file} -Y rtp > rtp.txt")
    device.expect_prompt()
    result_list = []
    if not msg_list:
        try:
            device.sendline("grep RTP rtp.txt|wc -l")
            device.expect("[1-9]\\d*\r\n", timeout=5)
            result_list.append(True)
        except PexpectErrorTimeout:
            logger.error("No RTP Packets found")
            result_list.append(False)
        device.expect_prompt()
    else:
        for msg in msg_list:
            try:
                device.sendline(
                    'grep ".*'
                    + msg.src_ip
                    + ".*"
                    + msg.dest_ip
                    + '.*RTP.*" rtp.txt | wc -l'
                )
                device.expect("[1-9]\\d*\r\n", timeout=10)
                device.expect_prompt()
                result_list.append(True)
            except PexpectErrorTimeout:
                logger.error(
                    f"No RTP Packets found with source {msg.src_ip} and destination {msg.dest_ip}"
                )
                device.expect_prompt()
                result_list.append(False)
    if rm_pcap:
        device.sudo_sendline("rm rtp.txt")
        device.expect_prompt()
        device.sudo_sendline(f"rm {capture_file}")
        device.expect_prompt()
    return all(result_list)


def basic_call_verify(output_sip, ip_src):
    """To verify basic call flow with sip messages.

    :param output_sip: return value of sip_read function
    :type output_sip: String
    :param ip_src: IP of device which initiates the call
    :type ip_src: String
    """
    import re

    sip_msg = re.search(
        ".*"
        + ip_src
        + ".*INVITE.*?"
        + ip_src
        + r"\s+SIP.*100\s+Trying.*?"
        + ip_src
        + r"\s+SIP.*180\s+Ringing.*?"
        + ip_src
        + r"\s+SIP\/SDP.*200\s+OK.*?"
        + ip_src
        + ".*ACK.*?"
        + ip_src
        + ".*BYE.*?"
        + ip_src
        + r"\s+SIP.*200\s+OK\s+\|",
        output_sip,
        re.DOTALL,
    )
    assert sip_msg is not None, "SIP call failed"


def get_mta_details(capture_file, device, mta_user=[]):
    """This function to get call id and expires from mta line0 and line1.
    :param capture_file: Filename where the packets captured in sipserver
    :type output_sip: String
    :param device: object
    :param return: Returns the call id and expires of line0 and line1
    :type device: Dictionary
    """
    import re

    output = tcpdump_read(device, capture_file, protocol="-vvv port 5060")
    out_rep = output.replace("\r\n", "").replace("\t", "")
    split_out = re.compile(r"\d\d:\d\d:\d\d").split(out_rep)
    mta_line_info = {}
    for idx, mta in enumerate(mta_user):
        for line in split_out:
            regx_str = (
                r"SIP/2.0\s+200\s+OK(.*)From:\s+"
                + mta
                + r"(.*)Call-ID:\s+(\S+)CSeq.*expires=(\d+)"
            )
            match = re.search(regx_str, line)
            if match:
                mta_line_info[mta] = {
                    "call-ID": match.group(3),
                    "Expire": match.group(4),
                }
                break
    return mta_line_info


def check_mta_media_attribute(
    device,
    capture_file,
    sip_no,
    media_attr="sendonly",
    port="5060",
    src_ip=None,
    dst_ip=None,
    timeout=30,
    **kwargs,
):
    """This function used to parse and verify the invite message media attribute
    :param capture_file: Filename where the packets captured in sipserver
    :type capture_file: file
    :param device: object
    :param sip_no: SIP specific number example(sip:2000@<sip_host>) only the number
    :type sip_no: String
    :param media_attr: Hold what type of media attribute needs to be captured; default is sendonly
    :type media_attr: String
    :param port: port hold what port the packet needs to be filtered; default is 5060
    :type port: String
    :param src_ip: source ip address to be used as filter; default is None
    :type src_ip: String
    :param dst_ip: destination ip address to be used as filter; default is None
    :type dst_ip: String
    :param timeout: timeout value sent to tcpdump read; default is 30 seconds
    :type timeout: int
    :param return: Returns dictionary as result
    :type return: Dictionary
    """

    msg_type = kwargs.pop("msg_type", "INVITE")
    verify_IN4 = kwargs.pop("verify_IN4", False)
    IN4_ip = kwargs.pop("IN4_ip", "0.0.0.0")
    rm_pcap = kwargs.pop("rm_pcap", True)

    result = {}

    if src_ip and dst_ip:
        protocol_attribute = f"-vvv 'port {port} and src {src_ip} and dst {dst_ip}'"
    elif src_ip:
        protocol_attribute = f"-vvv 'port {port} and src {src_ip}'"
    elif dst_ip:
        protocol_attribute = f"-vvv 'port {port} and dst {dst_ip}'"
    else:
        protocol_attribute = f"-vvv 'port {port}'"

    output = tcpdump_read(
        device,
        capture_file,
        protocol=protocol_attribute,
        timeout=timeout,
        rm_pcap=rm_pcap,
    )
    out_rep = output.replace("\r\n", "").replace("\t", "")
    packets = re.compile(r"\d\d:\d\d:\d\d").split(out_rep)

    for packet in packets:
        if msg_type == "INVITE":
            if verify_IN4:
                regex_pattern = (
                    r".*INVITE (sip:{}@.*)\sSIP.*CSeq:"
                    r"\s(\d*)\sINVITE.*c=IN\sIP4\s({}).*a=({}).*".format(
                        sip_no, IN4_ip, media_attr
                    )
                )
            else:
                regex_pattern = (
                    r".*INVITE (sip:{}@.*)\sSIP.*CSeq:"
                    r"\s(\d*)\sINVITE.*a=({}).*".format(sip_no, media_attr)
                )
        elif msg_type == "response":
            regex_pattern = r".*SIP.*200\sOK.*Contact:\s<sip:{}@.*a=({})".format(
                sip_no, media_attr
            )
        match = re.search(regex_pattern, packet)
        if match:
            result["status"] = True
            result["matched_packet"] = match.group(0)
            return result
    result["status"] = False
    result["matched_packet"] = None
    return result


def nmap_cli(device, ip_address, port, protocol=None, retry=0, timing="", optional=""):
    """To run port scanning on the specified target.Port scan is a method for determining which ports on a interface are open.
    This method is used to perform port scanning on the specified port range of the target ip specified from the device specified.

    :param device: device on which nmap command to run
    :type device: object
    :param ip_address: target ip address
    :type ip_address: string
    :param port: port range to be scanned
    :type port: string
    :param protocol: protocol (tcp/ucp/both), default to None
    :type protocol: String, Optional
    :param retry: maximum number of retries, defaults to 0
    :type retry: integer, Optional
    :param timing: Timing templates(-T[1-4]), defaults to ''
                   Each template will have different timings for different actions
    :type timing: String, Optional
    :param optional: Other options like minimum rate limit(packets/sec), max rate limit(packets/sec)
    :type optional: String
    :return: Output of namp command.
    :rtype: string
    """

    if not protocol:
        protocol = "both"
    ipv6 = (
        "-6"
        if "IPv6Address" == type(ipaddress.ip_address(str(ip_address))).__name__
        else ""
    )
    protocol_commandmap = {"tcp": "-sT", "udp": "-sU", "both": "-sT -sU"}
    device.sudo_sendline(
        "nmap %s %s %s %s -p%s -Pn -r -max-retries %s %s > nmap_logs.txt"
        % (
            ipv6,
            timing,
            protocol_commandmap[protocol],
            ip_address,
            port,
            retry,
            optional,
        )
    )
    retry_on_exception(device.expect, (device.prompt,), retries=16, tout=30)
    device.sendline("cat nmap_logs.txt")
    device.expect(device.prompt)
    nmap_output = device.before
    device.sendline("rm nmap_logs.txt")
    device.expect(device.prompt)
    return nmap_output


def ssh_service_verify(
    device,
    dest_device,
    ip,
    opts="",
    ssh_key="-oKexAlgorithms=+diffie-hellman-group1-sha1",
):
    """This function will try to verify if SSH service is running on a target device.
    If the ssh connection expects key exchange, then ssh_key provided is used to add the target device to known hosts.
    If connection is accepted and SSH password of target device is provided for login.

    :param device: client device from which the SSH session is initaited
    :type device: object
    :param dest_device: target device to connect
    :type dest_device: string
    :param ip: target device ip address
    :type ip: string
    :param opts: SSH options if any, default to ""
    :type opts: String, Optional
    :param ssh_key: SSH key for authentication, defaults to "-oKexAlgorithms=+diffie-hellman-group1-sha1"
    :type ssh_key: String, Optional
    :raises Exception: Exception thrown on SSH connection fail
    """
    device.sendline(f"ssh {dest_device.username}@{ip}")
    try:
        idx = device.expect(
            ["no matching key exchange method found"] + ["(yes/no)"] + ["assword:"],
            timeout=60,
        )
        if idx == 0:
            device.expect(device.prompt)
            device.sendline(f"ssh {ssh_key} {dest_device.username}@{ip} {opts}")
            idx = device.expect(["(yes/no)"] + ["assword:"], timeout=60)
            if idx == 0:
                idx = 1
        if idx == 1:
            device.sendline("yes")
            device.expect("assword:")
        device.sendline(dest_device.password)
        device.expect(dest_device.prompt)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except Exception as e:
        logger.error(e)
        value = device.before
        device.sendcontrol("c")
        device.expect(device.prompt)
        raise ConnectionRefused(f"Failed to connect to SSH due to {value}")


def telnet_service_verify(device, dest_device, ip, opts=""):
    """Verify telent service connection

    :param device: client device from which the telent session is initaited
    :type device: object
    :param dest_device: target device to connect
    :type dest_device: string
    :param ip: target device ip address
    :type ip: string
    :param opts: telent options if any, default to ""
    :type opts: String, Optional
    :raises Exception: Exception thrown on telnet connection fail
    """
    device.sendline(f"telnet{opts} {ip}")
    try:
        device.expect(["Username:"] + ["login:"], timeout=60)
        device.sendline(dest_device.username)
        device.expect(["assword:"])
        device.sendline(dest_device.password)
        device.expect(dest_device.prompt, timeout=40)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except Exception as e:
        for _ in range(2):
            device.sendcontrol("c")
            device.expect(device.prompt)
        raise ConnectionRefused(f"Failed to connect to telnet due to {e}")


def custom_telnet_service(device, dest_prompt, ip, username, password, opts="", cmd=[]):
    """Telnet service connection

    :param device: client device from which the telnet session is initiated
    :type device: object
    :param dest_prompt: target device prompt
    :type dest_prompt: list of prompt
    :param ip: ip address of the target device
    :type ip: string
    :param username: target device username
    :type: string
    :param password: target device password
    :type: string
    :param opts: telnet options if any, defaults to ""
    :type opts: string, Optional
    :param cmd: list of commands to send
    :type: list of strings
    :return: returns the command output
    """
    result = []
    send_control = False
    try:
        device.sendline(f"telnet {opts} {ip}")
        device.expect(["Username:"] + ["login:"], timeout=60)
        device.sendline(username)
        device.expect(["Password:"])
        device.sendline(password)
        device.expect(dest_prompt, timeout=60)
        send_control = True
        for cm in cmd:
            device.sendline(cm)
            device.expect(dest_prompt, timeout=60)
            result.append(device.before)
        device.sendcontrol("]")
        device.sendline("quit")
        send_control = False
        device.expect(device.prompt, timeout=60)
        return result
    except Exception as e:
        print(e)
        if send_control:
            device.sendcontrol("]")
            device.sendline("quit")
            device.expect(device.prompt, timeout=60)
        else:
            device.sendcontrol("c")
            device.expect(device.prompt, timeout=60)


def dhcping_inform_trigger(device, server_ip, opts=None):
    """This function is used to trigger dhcpv4 inform message
    :param device:  client device from which the dhcping inform is triggered
    :type device: object
    :param server_ip: DHCP server Ip address to which inform is triggered
    :param server_ip: String
    :param opts: can be more than one parameter but it should be joined
    :type opts: String, Optional
    :return: boolean value based on success of dhcpv4 inform trigger
    :rtype: Boolean
    """

    client_ip = device.get_interface_ipaddr(device.iface_dut)
    mac = device.get_interface_macaddr(device.iface_dut).upper()
    command_builder = f'dhcping -i -c {client_ip} -s {server_ip} -h "{mac}"'
    if opts:
        command_builder = f"{command_builder} {opts}"
    output = device.check_output(command_builder)
    out = re.search(r"(\wot\sanswer\s\w+)", output)
    return True if out else False


def verify_sip_status(device, capture_file, msg_list, rm_pcap=True, user_num=None):
    """This function is used to validate the SIP messages
    :param device: device where the SIP traces are generated. The SIP server.
    :type device: object
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :param msg_list: list of 'sip_msg' named_tuples
    :type msg_list: list
    :param rm_pcap: True if pcap needs to be removed else False
    :type rm_pcap: Boolean
    :param user_num: Number of the user to filter sip messages
    :type user_num: Integer/String
    :return: boolean value based on success of the message(s) being found or not
    :rtype: Boolean
    """
    if user_num:
        num = str(user_num)
        output = tshark_read(
            device,
            capture_file,
            filter_str=f"-Y sip -z sip,stat,sip.contact.user=={num}",
            rm_file=rm_pcap,
        )
    else:
        output = sip_read(device, capture_file, rm_pcap)

    out_rep = output.replace("\r\n", "").replace("\t", "")
    split_out = out_rep.split("|")
    result_list = []
    for msg in msg_list:
        split = msg.message.split()
        code_list = []
        text_list = []
        for x in split:
            if re.search(r"\d+", x):
                code_list.append(x)
            else:
                text_list.append(x)
        checker = code_list[0] if code_list else text_list[0]
        regex_str = f".*{msg.src_ip}.*{msg.dest_ip}.*{checker}"
        for line in split_out:
            if re.search(regex_str, line):
                result_list.append(True)
                break
        else:
            result_list.append(False)
    return all(result_list)


def rtp_flow_check(device, capture_file, src_ip, dst_ip, rm_file=False, negate=False):
    """Function to check the RTP flow based on SIP/SDP Invite for given src and dst IP's
    and return bool based on validation
    Examples:
    -To validate RTP flow between userA and userB
    for src, dst, file in zip(["userA_ip", "sipcenter_ip"], ["sipcenter_ip", "userB_ip"], [False, True])
        rtp_flow_check(self.dev.sipcenter, "test.pcap", src, dst, rm_file)
    -To validate no RTP flow between userA and userB
    for src, dst, file in zip(["userA_ip", "sipcenter_ip"], ["sipcenter_ip", "userB_ip"], [False, True])
        rtp_flow_check(self.dev.sipcenter, "test.pcap", src, dst, rm_file, negate=True)
    :param device: sipcenter where traces are collected
    :type device: object
    :param capture_file: pcap filename
    :type capture_file: str
    :param src_ip: src_ip of sip invite/rtp
    :type src_ip: str
    :param dst_ip: dst_ip of sip invite/rtp
    :type dst_ip: str
    :param rm_file: Flag if same pcap is required for further verification
    :type rm_file: bool
    :param negate: To validate negative cases like no RTP flow
    :type negate: bool
    :return: Return bool based on validation
    :rtype: bool
    """
    sip_pcap = tshark_read(
        device, capture_file, filter_str="sip.Method == 'INVITE'", rm_file=False
    )
    split_sip_pcap = sip_pcap.splitlines()
    invite = [
        re.search(r"\d+", trace).group(0)
        for trace in split_sip_pcap
        if re.search(rf".*{src_ip}.*{dst_ip}.*SIP.*sip:\d+@", trace)
    ]
    invite_num_reverse = invite[::-1]
    if invite:
        try:
            count = 0
            for setup_frame in invite_num_reverse:
                device.sendline(
                    f"tshark -r {capture_file} rtp.setup-frame == {setup_frame} | wc -l"
                )
                idx = device.expect(["[1-9]\\d*\r\n", "0\r\n"], timeout=10)
                device.expect(device.prompt)
                count = count + 1
                if idx == 0:
                    break
                elif idx == 1 and count == len(invite):
                    raise RTPNotFound
            return True
        except (PexpectErrorTimeout):
            device.expect(device.prompt)
            return False
        except (RTPNotFound):
            return True if negate else False
        finally:
            if rm_file:
                device.sudo_sendline(f"rm {capture_file}")
                device.expect(device.prompt)
            pass
    else:
        raise ValueError(f"{capture_file} doesnt have SIP invite")


class Iperf3Lib:
    """Iperf3Lib run iperf3 results are obtained"""

    def __init__(
        self,
        server=None,
        client=None,
        serverIPAddr=None,
        clientOpts="",
        serverOpts="",
        port="5002",
        udp_data=False,
    ):
        """constructor to Iperf3Lib class
        :param server : device on which iperf3 server will be ran
        :type server : devices
        :param client : device on which iperf3 client will be ran
        :type client : devices
        :param serverIPAddr : IP address of the iperf3 server
        :type serverIPAddr : str
        :param clientOpts : holds the options of iperf3 client
        :type clientOpts : str
        :param serverOpts : holds the option of iperf3 server
        :type serverOpts : str
        :param port : contains port number on which the iperf3 server and client should run
        :type port : str
        :param udp_data : flag that is set when UDP packet needs to be checked
        :type udp_data : boolean
        """
        self.udp_data = udp_data
        self.server = server
        self.client = client
        self.serverIPAddr = serverIPAddr
        self.clientOpts = clientOpts
        self.serverOpts = serverOpts
        self.port = port
        if not self.server:
            self.server = self.dev.by_type(device_type.wan)
        if not self.client:
            self.client = self.dev.by_type(device_type.lan)
        if not serverIPAddr:
            raise AssertionError(
                "Iperf3 server IP Address missing to perform iperf testing"
            )

    def run_iperf3_server(self, stop_previous_instance=True, nohup=False):
        """function to run iperf3 server
        :param stop_previous_instance : if True stops existing server
        :type stop_previous_instance : bool
        :param nohup : server variable, if True then it redirects to /dev/null
        :type nohup : bool
        """
        if stop_previous_instance:
            self.kill_iperf3(self.server)
        if nohup:
            self.server.sendline(f"nohup iperf3 {self.serverOpts} -s -p {self.port} &")
            self.server.expect(self.server.prompt)
        else:
            self.server.sendline(f"iperf3 {self.serverOpts} -s -p {self.port} &")
            self.server.expect(f"Server listening on {self.port}")

    def kill_iperf3(self, device):
        """function to kill all iperf3 instance that is spawned on the device
        :param device : device on which iperf run instance to be killed
        :type device : devices object
        """
        try:
            device.sendline("killall -9 iperf3")
            device.expect(device.prompt)
        except Exception as error:
            print(error)
            device.sendcontrol("c")
            device.sendcontrol("c")
            device.expect(device.prompt)
            device.sendline("killall -9 iperf3")
            device.expect(device.prompt)

    def run_iperf(
        self,
        DS=False,
        timeout=300,
        process_bg=False,
        stop_previous_instance=True,
        nohup=False,
    ):
        """function to start the execution of iperf3
        :param DS : Downstream flag is used to change the data flow between iperf client and server
        :type DS : bool
        :param timeout : max timeout to wait
        :type timeout : int
        :param process_bg : if True runs command in background (client side),
        defaults to False
        :type process_bg : bool
        :param stop_previous_instance : True to stop the existing server,
        defaults to True
        :type stop_previous_instance : bool
        :param nohup : server variable, if True then it redirects to /dev/null
        :type nohup : bool
        :return : returns the output data according to iperf results
        :rtype : dict
        """
        self.run_iperf3_server(stop_previous_instance, nohup)
        if process_bg:
            # -R can be given as part of ClientOpts to run Downstream traffic
            commandBuilder = "iperf3 -c {} -p {} {} &".format(
                self.serverIPAddr,
                self.port,
                self.clientOpts,
            )
            self.client.sendline(commandBuilder)
            self.client.expect(self.client.prompt, timeout=timeout)
        else:
            commandBuilder = "iperf3 {} -c {} -p {}".format(
                self.clientOpts,
                self.serverIPAddr,
                self.port,
            )
            if DS:
                commandBuilder = commandBuilder + " -R"
            self.client.sendline(commandBuilder)
            self.client.expect(self.client.prompt, timeout=timeout)
            self.output = self.parse_iperf3(self.client.before)
            self.kill_iperf3(self.server)
            return self.output

    def get_parsed_value(self, data=None, rates=None):
        """function used to parse the iperf3 results
        :param data : data that has been sent/received via Iperf
        :type data : str
        :param rates : transfer rates /bandwidth that has been used to send the data
        :type rates : str
        :return : returns the convered float value to Mega
        :rtype : float
        """
        value = None
        if rates:
            if "Mbits" in rates:
                value = float(rates.split()[0])
            elif "Kbits" in rates:
                value = float(rates.split()[0]) / 1024
            elif "Gbits" in rates:
                value = float(rates.split()[0]) * 1024
            else:
                value = None
        elif data:
            if "MBytes" in data:
                value = float(data.split()[0])
            elif "KBytes" in data:
                value = float(data.split()[0]) / 1024
            elif "GBytes" in data:
                value = float(data.split()[0]) * 1024
            else:
                value = None
        else:
            value = None
        return value

    def parse_iperf3(self, iperfResult):
        """function used to compute the iperf3 results
        :param iperfResult : contains the iperf output
        :type iperfResult : str
        :return : return the sent and received data and rates
        :rtype : dict
        """
        errorMessage = re.findall(r"iperf3\:\s*error\s*.*", iperfResult)
        if errorMessage:
            return {"error": errorMessage[-1]}
        if self.udp_data:
            match = re.findall(
                r".*sec\s*(.*\s*Bytes)\s*(.*\s*bits/sec)\s*(.*\s*s)\s*(.*)\/.*\((.*)\%.*",
                iperfResult.split("Datagrams")[-1],
            )[-1]
            return {
                "data": self.get_parsed_value(data=match[0]),
                "rate": self.get_parsed_value(rates=match[1]),
                "jitter": match[2],
                "loss_percent": float(match[3]),
                "error": None,
            }
        sent_rate = self.get_parsed_value(
            rates=re.findall(r".*Bytes\s*(.*/sec).*sender", iperfResult)[-1]
        )
        recv_rate = self.get_parsed_value(
            rates=re.findall(r".*Bytes\s*(.*/sec).*receiver", iperfResult)[-1]
        )
        sent_data = self.get_parsed_value(
            data=re.findall(r".*sec\s*(.*Bytes)\s*.*/sec.*sender", iperfResult)[-1]
        )
        recv_data = self.get_parsed_value(
            data=re.findall(r".*sec\s*(.*Bytes)\s*.*/sec.*receiver", iperfResult)[-1]
        )
        return {
            "sent_rate": sent_rate,
            "received_rate": recv_rate,
            "sent_data": sent_data,
            "received_data": recv_data,
            "error": None,
        }


def mac_to_eui64(mac_address):
    """Generate a IPv6 addr by EUI-64 with MAC
    :param str mac: a MAC address
    :return: an IPv6 Address
    :rtype: netaddr.IPAddress
    """
    try:
        eui64 = int(netaddr.EUI(mac_address).eui64())
        return netaddr.IPAddress(eui64 ^ (1 << 57))
    except (ValueError, netaddr.AddrFormatError):
        raise TypeError(
            f"Bad mac format for generating IPv6address by EUI-64:  {mac_address}:"
        )
