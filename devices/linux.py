import base
import pexpect, ipaddress, re
from lib.regexlib import ValidIpv4AddressRegex, AllValidIpv6AddressesRegex, LinuxMacFormat

class LinuxDevice(base.BaseDevice):
    '''Linux implementations '''

    def get_interface_ipaddr(self, interface):
        '''Get ipv4 address of interface'''
        self.sendline("\nifconfig %s" % interface)
        regex = ['addr:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(Bcast|P-t-P):',
                 'inet (\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(broadcast|P-t-P)',
                 'inet ('+ValidIpv4AddressRegex+').*netmask ('+ValidIpv4AddressRegex+').*destination '+ValidIpv4AddressRegex]
        self.expect(regex, timeout=5)
        ipaddr = self.match.group(1)
        ipv4address = str(ipaddress.IPv4Address(unicode(ipaddr)))
        self.expect(self.prompt)
        return ipv4address

    def get_interface_ip6addr(self, interface):
        '''Get ipv6 address of interface'''
        self.sendline("\nifconfig %s" % interface)
        self.expect_exact("ifconfig %s" % interface)
        self.expect(self.prompt)
        for match in re.findall(AllValidIpv6AddressesRegex, self.before):
            ip6address = ipaddress.IPv6Address(unicode(match))
            if not ip6address.is_link_local:
                return str(ip6address)
        raise Exception("Did not find non-link-local ipv6 address")

    def get_interface_macaddr(self, interface):
        '''Get the interface macaddress '''
        self.sendline('cat /sys/class/net/%s/address' % interface)
        self.expect_exact('cat /sys/class/net/%s/address' % interface)
        self.expect(LinuxMacFormat)
        macaddr = self.match.group()
        self.expect(self.prompt)
        return macaddr

    def get_seconds_uptime(self):
        '''Return seconds since last reboot. Stored in /proc/uptime'''
        self.sendcontrol('c')
        self.expect(self.prompt)
        self.sendline('\ncat /proc/uptime')
        self.expect('((\d+)\.(\d{2}))(\s)(\d+)\.(\d{2})')
        seconds_up = float(self.match.group(1))
        self.expect(self.prompt)
        return seconds_up

    def enable_ipv6(self, interface):
        '''Enable ipv6 of the interface '''
        self.sendline("sysctl net.ipv6.conf."+interface+".accept_ra=2")
        self.expect(self.prompt, timeout=30)
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=0")
        self.expect(self.prompt, timeout=30)

    def disable_ipv6(self, interface):
        '''Disable ipv6 of the interface '''
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=1")
        self.expect(self.prompt, timeout=30)

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
        '''Modifies the log level in kernel'''
        try:
            self.sendline('echo "%d %d %d %d" > /proc/sys/kernel/printk' % (CUR, DEF, MIN, BTDEF))
            self.expect(self.prompt, timeout=10)
            if not BFT_DEBUG:
                common.print_bold("printk set to %d %d %d %d" % (CUR, DEF, MIN, BTDEF))
        except:
            pass

    def prefer_ipv4(self, pref=True):
        """Edits the /etc/gai.conf file

        This is to give/remove ipv4 preference (by default ipv6 is preferred)
        See /etc/gai.conf inline comments for more details
        """
        if pref is True:
            self.sendline("sed -i 's/^#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/'  /etc/gai.conf")
        else:
            self.sendline("sed -i 's/^precedence ::ffff:0:0\/96  100/#precedence ::ffff:0:0\/96  100/'  /etc/gai.conf")
        self.expect(self.prompt)

    def ping(self, ping_ip, source_ip=None, ping_count=4, ping_interface=None):
        '''Check ping from any device'''
        if source_ip == None and ping_interface == None:
            self.sendline('ping -c %s %s' % (ping_count, ping_ip))
        elif ping_interface != None:
            self.sendline('ping -I %s -c %s %s' % (ping_interface, ping_count, ping_ip))
        else:
            self.sendline("ping -S %s -c %s %s" % (source_ip, ping_count, ping_ip))
        self.expect(self.prompt, timeout=50)
        match = re.search("%s packets transmitted, %s received, 0%% packet loss" %
                          (ping_count, ping_count), self.before)
        if match:
            return 'True'
        else:
            return 'False'
