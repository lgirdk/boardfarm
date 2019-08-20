import ipaddress
import re
import sys
import base
import connection_decider
from boardfarm.lib.regexlib import AllValidIpv6AddressesRegex

class WindowsTelnet(base.BaseDevice):

    model = ('windows-telnet')
    # This prompt regex could use more work
    prompt = ['[a-zA-Z]:\\\\.*>$']

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.ip = self.kwargs['ipaddr']
        self.username = self.kwargs.get('username', 'Administrator')
        self.password = self.kwargs.get('password', 'bigfoot1')

        conn_cmd = "telnet %s" % self.ip

        self.connection = connection_decider.connection("local_cmd", device=self, conn_cmd=conn_cmd)
        self.connection.connect()
        self.linesep = '\r'

        self.expect('login: ')
        self.sendline(self.username)
        self.expect('password: ')
        self.sendline(self.password)
        self.expect(self.prompt)

        # Hide login prints, resume after that's done
        self.logfile_read = sys.stdout

    def get_ip(self, wifi_interface):

        self.sendline('netsh interface ip show config '+wifi_interface)

        self.expect("(.+)>",timeout=30)
        Wifi_log = self.match.group(1)

        match = re.search('IP Address:\s+([\d.]+)' , str(Wifi_log))
        if match:
            return match.group(1)
        else:
            return None

    def ping(self, ping_ip ,source_ip=None, ping_count=4, ping_interface=None):

        if source_ip == None :
            self.sendline('ping -n %s %s'%(ping_count, ping_ip))
        else:
            self.sendline("ping -S %s -n %s %s"%(source_ip, ping_count, ping_ip))

        self.expect("(.+)>",timeout=30)
        Wifi_log = self.match.group(1)

        match = re.search('Reply from .+: bytes=.+ TTL=' , str(Wifi_log))
        if match:
            return 'True'
        else:
            return 'False'

    def set_dhcp(self , wifi_interface):
        self.sendline('netsh interface ip set address '+wifi_interface+" dhcp")
        self.expect(self.prompt)

    def set_static_ip(self , wifi_interface, fix_ip, fix_mark, fix_gateway):
        self.sendline('netsh interface ip set address '+wifi_interface+" static "+fix_ip+" "+fix_mark+" "+fix_gateway+" 1")
        self.expect(self.prompt)

    def get_default_gateway(self, wifi_interface):
        self.sendline('netsh interface ip show config '+wifi_interface)

        self.expect("(.+)>",timeout=30)
        Wifi_log = self.match.group(1)

        match = re.search('Default Gateway:\s+([\d.]+)' , str(Wifi_log))
        if match:
            return match.group(1)
        else:
            return None

    def get_interface_ipaddr(self, interface):
        self.get_ip(interface)

    def get_interface_ip6addr(self, interface):
        self.sendline("netsh interface ipv6 show addresses %s" %interface)
        self.expect(self.prompt)
        for match in re.findall(AllValidIpv6AddressesRegex, self.before):
            ipv6addr = ipaddress.IPv6Address(unicode(match))
            if not ipv6addr.is_link_local:
                return ipv6addr
