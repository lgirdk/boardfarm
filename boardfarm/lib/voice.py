from typing import List, Tuple

import pexpect
from boardfarm_docsis.exceptions import VoiceSetupConfigureFailure
from nested_lookup import nested_lookup

from boardfarm.devices.base_devices.sip_template import SIPTemplate
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.installers import apt_install
from boardfarm.lib.network_testing import kill_process


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


def parse_sip_trace(
    device: SIPTemplate, fname: str, fields: str = ""
) -> List[List[str]]:
    """Read and filter SIP packets from the captured file.

    The Session Initiation Protocol is a signaling protocol used for initiating,
    maintaining, and terminating real-time sessions that include voice,
    video and messaging applications.

    :param device: SIP server
    :type device: SIPTemplate
    :param fname: PCAP file to be read
    :type fname: str
    :param fields: Additional field which need to be , defaults to ""
    :type fields: str, optional
    :return: list of SIP packets as [src ip, dst ip, sip contact, sip msg]
    :rtype: List[List[str]]
    """
    cmd = f"tshark -r {fname} -Y sip "
    fields = (
        "-T fields -e ip.src -e ip.dst -e sip.from.user -e sip.contact.user "
        "-e sip.Request-Line -e sip.Status-Line " + fields
    )

    device.sudo_sendline(cmd + fields)
    device.expect(device.prompt)
    out = device.before.splitlines()[1::]
    if "This could be dangerous." in out[0]:
        out = out[1::]

    output = []
    for line in out:
        src, dst, sfrom, contact, req, status = line.split("\t")
        output.append([src, dst, contact or sfrom, req or status])
    return output


def is_sip_sequence_matching(
    sequence: List[Tuple[str]], captured_sequence: List[List[str]]
) -> bool:
    """Check if the expected ```sequence``` is a match with the ```captured_sequence```.

    :param sequence: Expected sequence.
    :type sequence: List[Tuple[str]]
    :param captured_sequence: Captured sequence
    :type captured_sequence: List[List[str]]
    :return: True if sequences match, else False
    :rtype: bool
    """
    last_check = 0
    for src, dst, sip_contact, msg in sequence:
        flag = False
        for i in range(last_check, len(captured_sequence)):
            result = []
            src_o, dst_o, sip_contact_o, msg_o = captured_sequence[i]
            result.append(str(src) == src_o)
            result.append(str(dst) == dst_o)
            result.append(sip_contact == sip_contact_o)
            result.append(msg in msg_o)
            if all(result):
                last_check = i
                print(
                    f"Verified:\t{src_o}\t--->\t{dst_o}\t from: {sip_contact_o} | {msg_o}"
                )
                flag = True
                break
        if not flag:
            print(f"Failed:\t{src}\t--->\t{dst}\t from: {sip_contact} | {msg}")
            break
    else:
        return True
    return False
