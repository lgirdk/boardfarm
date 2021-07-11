import pexpect
from boardfarm_docsis.exceptions import VoiceSetupConfigureFailure
from nested_lookup import nested_lookup

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
