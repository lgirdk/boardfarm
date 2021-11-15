import datetime
from typing import List, Tuple

import pexpect
from boardfarm_docsis.exceptions import VoiceSetupConfigureFailure
from nested_lookup import nested_lookup

from boardfarm.exceptions import CodeError
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.installers import apt_install
from boardfarm.lib.network_testing import kill_process
from boardfarm.use_cases.voice import VoiceServer


def add_dns_auth_record(dns, sipserver_name):
    """
    To add a record and srv to the dns server.

    Parameters:
    dns(object): device where the dns server is installed
    sipserver_name(string): name of the sipserver
    """
    sip_domain = sipserver_name + ".boardfarm.com"
    # removing the auth record lines if present
    rm_dns_auth_record(dns)
    dns.sendline("cat >> /etc/dnsmasq.conf << EOF")
    dns.sendline(f"auth-zone={sip_domain}")
    dns.sendline(f"auth-soa=12345678,admin.{sip_domain}")
    dns.sendline(f"srv-host=_sip._tcp,{sip_domain},5060,20,10")
    dns.sendline(f"srv-host=_sip._tcp,{sip_domain},5060,20,10")
    dns.sendline(f"mx-host={sip_domain}")
    dns.sendline("EOF")
    dns.expect(dns.prompt)
    dns.sendline("/etc/init.d/dnsmasq restart")
    dns.expect(dns.prompt)


def rm_dns_auth_record(dns):
    """
    To remove A record and srv to the dns server.

    Parameters:
    dns(object): device where the dns server is installed
    """
    dns.sendline(
        r"sed '/auth-zone\=/,/mx-host\=/d' /etc/dnsmasq.conf > /etc/tmpfile.txt"
    )
    dns.expect(dns.prompt)
    dns.sendline("mv /etc/tmpfile.txt /etc/dnsmasq.conf")
    dns.expect(dns.prompt)
    dns.sendline("/etc/init.d/dnsmasq restart")
    dns.expect(dns.prompt)


def voice_configure(voice_devices_list, sip_server, config):
    """
    Initialize the Voice test setup.

    Parameters:
    voice_devices_list(list of obj): list of voice devices
    sip_server(obj): sipserver device
    config(obj): config object
    """

    try:
        sip_server.prefer_ipv4()
        kill_process(sip_server, port=5060)
        apt_install(sip_server, "tshark")
        dns_setup_sipserver(sip_server, config)
        for voice_device in voice_devices_list:
            if hasattr(voice_device, "profile"):
                boot_list = nested_lookup(
                    "on_boot", voice_device.profile.get(voice_device.name, {})
                )
                for profile_boot in boot_list:
                    profile_boot()
                if "softphone" in voice_device.name:
                    voice_device.phone_config(
                        sip_server.get_interface_ipaddr(sip_server.iface_dut)
                    )
    except Exception as e:
        kill_process(sip_server, port=5060)
        raise VoiceSetupConfigureFailure(e)


def dns_setup_sipserver(sip_server, config):
    """
    To setup dns with auth records.

    Parameters:
    sip_server(obj): sipserver device
    """
    try:
        if sip_server:
            sip_server.prefer_ipv4()
            sip_server.sendline('echo "nameserver 8.8.8.8" > /etc/resolv.conf')
            apt_install(sip_server, "dnsmasq")
            sip_server.setup_dnsmasq(config)
            add_dns_auth_record(sip_server, sip_server.name)
    except Exception as e:
        raise Exception("Unable to initialize dns, failed due to the error : ", e)


def basic_call(sipcenter, caller, callee, board, sipserver_ip, dial_number, tcid):
    """
    To make a basic call.

    Parameters:
    sipcenter(object): sipcenter device
    caller(object): caller device
    callee(object): callee device
    sipserver_ip(string): sipserver_ip
    dial_number(string): number to be dialed

    Return:
    media_out(string): media output through which tones are validated
    """
    # phone start
    retry_on_exception(caller.phone_start, ())
    retry_on_exception(callee.phone_start, ())
    # phone dial
    caller.dial(dial_number, sipserver_ip)
    # phone answer
    callee.answer()
    # board verify
    media_out = board.check_media_started(tcid)
    # call hangup
    board.expect(pexpect.TIMEOUT, timeout=20)
    board.send_sip_offhook_onhook(flag="onhook", tcid=tcid)
    # phone kill
    caller.phone_kill()
    callee.phone_kill()
    return media_out


def rtpproxy_install(dev):
    """Install rtpproxy"""
    apt_install(dev, "rtpproxy", timeout=60)


def rtpproxy_start(dev):
    """Start the rtpproxy in background."""
    dev.sendline("service rtpproxy start")
    dev.expect("Starting")
    dev.expect(dev.prompt)


def rtpproxy_stop(dev):
    """Stop the rtpproxy in background."""
    dev.sendline("service rtpproxy stop")
    dev.expect(["Stopping", "unrecognized service"])
    dev.expect(dev.prompt)


def rtpproxy_configuration(dev):
    """To generate rtpproxy configuration files"""
    ip_address = dev.get_interface_ipaddr(dev.iface_dut)
    gen_rtpproxy_conf = f"""cat > /etc/default/rtpproxy << EOF
CONTROL_SOCK=udp:127.0.0.1:7722
EXTRA_OPTS="-l {ip_address}"
USER=kamailio
GROUP=kamailio
EOF"""
    dev.sendline(gen_rtpproxy_conf)
    dev.expect(dev.prompt)


def _read_sip_trace(dev: VoiceServer, fname: str) -> List[Tuple[str]]:
    """Read and filter SIP packets from the captured file.

    The Session Initiation Protocol is a signaling protocol used for initiating,
    maintaining, and terminating real-time sessions that include voice,
    video and messaging applications.

    :param dev: SIP server
    :type dev: SIPTemplate
    :param fname: PCAP file to be read
    :type fname: str
    :return: list of SIP packets as [(frame, src ip, dst ip, sip contact, sip msg:media_attribute:connection:info, time)]
    :rtype: List[Tuple[str]]
    """
    device = dev._obj()
    cmd = f"tshark -r {fname} -Y sip "
    fields = (
        "-T fields -e frame.number -e ip.src -e ip.dst -e sip.from.user -e sip.contact.user "
        "-e sip.Request-Line -e sip.Status-Line -e sdp.media_attr -e sdp.connection_info -e frame.time"
    )

    device.sudo_sendline(cmd + fields)
    device.expect(device.prompt)
    out = device.before.splitlines()
    for _i, o in enumerate(out):
        if "This could be dangerous." in o:
            break
    out = out[_i + 1 :]

    output = []
    for line in out:
        (
            frame,
            src,
            dst,
            sfrom,
            contact,
            req,
            status,
            media_attr,
            connection_info,
            frame_time,
        ) = line.split("\t")
        output.append(
            (
                frame,
                src,
                dst,
                contact or sfrom,
                f"{req or status}:{media_attr}:{connection_info}",
                frame_time,
            )
        )
    return output


def parse_sip_trace(
    dev: VoiceServer, fname: str, expected_sequence: List[Tuple[str]]
) -> List[Tuple[str]]:
    """Reads the pcap file and creates the matched sequence with the expected sequence of sip packets.
    This creates a matched sequence of the same size as expected sequence with the rtp traces appended as it is
    from expected sequence

    :param dev: SIP Server
    :type dev: VoiceServer
    :param fname: name of the PCAP file
    :type fname: str
    :param expected_sequence: expected list of sequence to match for the captured sequence
    :type expected_sequence: List[Tuple[str]]
    :return: matched expected sequence with the captured sequence
    :rtype: List[Tuple[str]]
    """
    captured_sequence = _read_sip_trace(dev, fname)
    last_check = 0
    final_result = []
    for src, dst, sip_contact, msg in expected_sequence:
        if "RTP_CHECK" not in msg:
            flag = False
            for i in range(last_check, len(captured_sequence)):
                result = []
                frame_o, src_o, dst_o, sip_contact_o, msg_o, time_o = captured_sequence[
                    i
                ]
                result.append(str(src) == src_o)
                result.append(str(dst) == dst_o)
                result.append(sip_contact == sip_contact_o)
                result.append(all(i in msg_o for i in msg.split(":")))
                if all(result):
                    last_check = i
                    print(
                        f"Verified:\t{src_o}\t--->\t{dst_o}\t from: {sip_contact_o} | {msg_o}"
                    )
                    flag = True
                    final_result.append(
                        (frame_o, src_o, dst_o, sip_contact_o, msg_o, time_o)
                    )
                    break
            if not flag:
                print(f"Failed:\t{src}\t--->\t{dst}\t from: {sip_contact} | {msg}")
                final_result.append(())
        else:
            final_result.append(("_", src, dst, sip_contact, msg, "_"))
    return final_result


def _parse_rtp_trace(
    dev: VoiceServer,
    fname: str,
    matched_sequence: List[Tuple[str]],
    start_index: int,
    end_index: int,
) -> List[list]:
    """Checks the pcap for any existence of the rtp packed within a particular sip range of the matched sequence

    :param dev: SIP Server
    :type dev: VoiceServer
    :param fname: name of the PCAP file
    :type fname: str
    :param matched_sequence: matched expected sequence with the captured sequence
    :type matched_sequence: List[Tuple[str]]
    :param start_index: start index of the sip trace in the expected sequence to check for the rtp after that
    :type start_index: int
    :param end_index: end index of the sip trace in the expected sequence to check for the rtp before that
    :type end_index: int
    :return: the list of all the frames found corresponding to each tuple of the matched sequence
    :rtype: List[list]
    """
    time_format = "%b %d, %Y %H:%M:%S.%f"
    try:
        start_frame = matched_sequence[start_index][0]
        end_frame = matched_sequence[end_index][0]
        time_string = (
            matched_sequence[start_index][5]
            .strip()
            .rsplit(" ", 1)[0]
            .strip()
            .strip("0")
        )
        frame_time = datetime.datetime.strptime(time_string, time_format)
    except AttributeError:
        raise CodeError(
            "SIP sequence does not match or the start/end indexes are invalid"
        )
    # Check for the RTP checks after 1sec delay on captured SIP frame
    frame_time += datetime.timedelta(seconds=1)
    cmd_start_frame = (
        f'frame.number>{start_frame} && frame.time>"{frame_time.strftime(time_format)}"'
    )
    cmd_end_frame = "" if start_frame == end_frame else f" && frame.number<{end_frame}"
    device = dev._obj()
    output = []
    for index in range(start_index, end_index + 1):
        try:
            src = matched_sequence[index][1]
            dst = matched_sequence[index][2]
            if (
                index not in [start_index, end_index]
                and "RTP_CHECK" not in matched_sequence[index][4]
            ):
                raise CodeError(
                    "Should not provide any other sequence between start and end indexes other than RTP_CHECK"
                )
        except AttributeError:
            raise CodeError(
                "SIP sequence does not match or the start/end indexes are invalid"
            )
        cmd = f'tshark -r {fname} -Y \'{cmd_start_frame}{cmd_end_frame} && ip.src_host=="{src}" && ip.dst_host=="{dst}" && rtp\' -T fields -e frame.number'
        device.sudo_sendline(cmd)
        device.expect(device.prompt)
        out = device.before.splitlines()
        for _i, o in enumerate(out):
            if "This could be dangerous." in o:
                break
        out = out[_i + 1 :]
        print(
            f"Found RTP traces: \nTotal traces {len(out)} --> {start_frame} to {end_frame} frames --> from ipaddress {src} to {dst}\n"
        )
        output.append(out)
    return output


def is_sip_sequence_matching(matched_sequence: List[Tuple[str]]) -> bool:
    """Checks if all the tuples in the expected sequence matches with the captured sequence

    :param matched_sequence: matched expected sequence with the captured sequence
    :type matched_sequence: List[Tuple[str]]
    :return: True if all the tuples in a sip sequence match else False if even one is unmatched
    :rtype: bool
    """
    return all(matched_sequence)


def is_rtp_trace_found(
    dev: VoiceServer,
    fname: str,
    matched_sequence: List[Tuple[str]],
    start_index: int,
    end_index: int,
) -> bool:
    """Checks if all the expected rtp traces are found between the sip traces
    Note: User should always call is_sip_sequence_matching before calling this method to identify any error
    in the sequence otherwise the index failures in this usecase could never be identified

    :param dev: SIP server
    :type dev: VoiceServer
    :param fname: name of the PCAP file
    :type fname: str
    :param matched_sequence: matched expected sequence with the captured sequence
    :type matched_sequence: List[Tuple[str]]
    :param start_index: start index of the sip trace in the expected sequence to check for the rtp after that
    :type start_index: int
    :param end_index:  end index of the sip trace in the expected sequence to check for the rtp before that
    :type end_index: int
    :return: True if rtp frames are found within the range of start_index and end_index
    :rtype: bool
    """
    rtp_traces = _parse_rtp_trace(dev, fname, matched_sequence, start_index, end_index)
    return all(rtp_traces)


def is_rtp_trace_not_found(
    dev: VoiceServer,
    fname: str,
    matched_sequence: List[Tuple[str]],
    start_index: int,
    end_index: int,
) -> bool:
    """Checks if either of the expected rtp traces are not found between the sip traces
    Note: User should always call is_sip_sequence_matching before calling this method to identify any error
    in the sequence otherwise the index failures in this usecase could never be identified

    :param dev: SIP server
    :type dev: VoiceServer
    :param fname: name of the PCAP file
    :type fname: str
    :param matched_sequence: matched expected sequence with the captured sequence
    :type matched_sequence: List[Tuple[str]]
    :param start_index: start index of the sip trace in the expected sequence to check for the rtp after that
    :type start_index: int
    :param end_index:  end index of the sip trace in the expected sequence to check for the rtp before that
    :type end_index: int
    :return: True if none of the rtp frames are found within the range of start_index and end_index
    :rtype: bool
    """
    rtp_traces = _parse_rtp_trace(dev, fname, matched_sequence, start_index, end_index)
    return not any(rtp_traces)
