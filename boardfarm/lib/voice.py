import pexpect
from nested_lookup import nested_lookup
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.installers import apt_install


def add_dns_auth_record(dns, sipserver_name):
    '''
    To add a record and srv to the dns server

    Parameters:
    dns(object): device where the dns server is installed
    sipserver_name(string): name of the sipserver
    '''
    sip_domain = sipserver_name + ".boardfarm.com"
    #removing the auth record lines if present
    rm_dns_auth_record(dns)
    dns.sendline('cat >> /etc/dnsmasq.conf << EOF')
    dns.sendline('auth-zone=%s' % sip_domain)
    dns.sendline('auth-soa=12345678,admin.%s' % sip_domain)
    dns.sendline('srv-host=_sip._tcp,%s,5060,20,10' % sip_domain)
    dns.sendline('srv-host=_sip._tcp,%s,5060,20,10' % sip_domain)
    dns.sendline('mx-host=%s' % sip_domain)
    dns.sendline('EOF')
    dns.expect(dns.prompt)
    dns.sendline('/etc/init.d/dnsmasq restart')
    dns.expect(dns.prompt)


def rm_dns_auth_record(dns):
    '''
    To remove A record and srv to the dns server

    Parameters:
    dns(object): device where the dns server is installed
    '''
    dns.sendline(
        'sed \'/auth-zone\=/,/mx-host\=/d\' /etc/dnsmasq.conf > /etc/tmpfile.txt'
    )
    dns.expect(dns.prompt)
    dns.sendline('mv /etc/tmpfile.txt /etc/dnsmasq.conf')
    dns.expect(dns.prompt)
    dns.sendline('/etc/init.d/dnsmasq restart')
    dns.expect(dns.prompt)


def voice_devices_configure(voice_devices_list, sip_server):
    '''
    Initialize the Voice test setup

    Parameters:
    voice_devices_list(list of obj): list of voice devices
    sip_server(obj): sipserver device
    '''
    try:
        for voice_device in voice_devices_list:
            if hasattr(voice_device, "profile"):
                boot_list = nested_lookup(
                    "on_boot", voice_device.profile.get(voice_device.name, {}))
                for profile_boot in boot_list:
                    profile_boot()
                if 'softphone' in voice_device.name:
                    voice_device.phone_config(sip_server.ipaddr)
    except Exception as e:
        sip_server.kill_asterisk()
        raise Exception(
            "Unable to initialize Voice devices, failed due to the error : ",
            e)


def dns_setup_sipserver(sip_server, config):
    '''
    To setup dns with auth records

    Parameters:
    sip_server(obj): sipserver device
    '''
    try:
        if sip_server:
            sip_server.prefer_ipv4()
            sip_server.sendline('echo "nameserver 8.8.8.8" > /etc/resolv.conf')
            apt_install(sip_server, 'dnsmasq')
            sip_server.setup_dnsmasq(config)
            add_dns_auth_record(sip_server, sip_server.name)
    except Exception as e:
        raise Exception("Unable to initialize dns, failed due to the error : ",
                        e)


def basic_call(sipcenter, caller, callee, board, sipserver_ip, dial_number,
               tcid):
    '''
    To make a basic call

    Parameters:
    sipcenter(object): sipcenter device
    caller(object): caller device
    callee(object): callee device
    sipserver_ip(string): sipserver_ip
    dial_number(string): number to be dialed

    Return:
    media_out(string): media output through which tones are validated
    '''
    #phone start
    retry_on_exception(caller.phone_start, ())
    retry_on_exception(callee.phone_start, ())
    #phone dial
    caller.dial(dial_number, sipserver_ip)
    #phone answer
    callee.answer()
    #board verify
    media_out = board.check_media_started(tcid)
    #call hangup
    board.expect(pexpect.TIMEOUT, timeout=20)
    board.send_sip_offhook_onhook(flag="onhook", tcid=tcid)
    #phone kill
    caller.phone_kill()
    callee.phone_kill()
    return media_out
