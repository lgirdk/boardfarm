import base
import pexpect, ipaddress, re
from lib.regexlib import ValidIpv4AddressRegex, AllValidIpv6AddressesRegex

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
