from nested_lookup import nested_lookup

def add_dns_auth_record(dns,sipserver_name):
    '''
    To add a record and srv to the dns server

    Parameters:
    dns(object): device where the dns server is installed
    sipserver_name(string): name of the sipserver
    '''
    sip_domain = sipserver_name+".boardfarm.com"
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
    dns.sendline('sed \'/auth-zone\=/,/mx-host\=/d\' /etc/dnsmasq.conf > /etc/tmpfile.txt')
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
                boot_list = nested_lookup("on_boot",voice_device.profile.get(voice_device.name, {}))
                for profile_boot in boot_list:
                    profile_boot()
                if 'softphone' in voice_device.name:
                    voice_device.phone_config(sip_server.ipaddr)
    except Exception as e:
        sip_server.kill_asterisk()
        raise Exception("Unable to initialize Voice devices, failed due to the error : ", e)

def dns_setup_sipserver(sip_server):
    '''
    To setup dns with auth records

    Parameters:
    sip_server(obj): sipserver device
    '''
    try:
        if sip_server:
            sip_server.setup_dnsmasq()
            add_dns_auth_record(sip_server,sip_server.name)
    except Exception as e:
        raise Exception("Unable to initialize dns, failed due to the error : ", e)
