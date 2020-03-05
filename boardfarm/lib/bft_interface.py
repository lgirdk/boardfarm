import six
import ipaddress, netaddr
import re
import pexpect
from boardfarm.exceptions import BFTypeError
from boardfarm.lib.regexlib import LinuxMacFormat


class bft_iface(object):

    _ipv4 = None
    _ipv6 = None
    _ipv6_link_local = None
    _mac = None

    def __str__(self):
        return (str(self.dev.name))

    def __init__(self, device, iface, ip_cmd="ifconfig"):
        self.iface = iface
        self.ip_cmd = ip_cmd
        self.dev = device

    def refresh(self):
        output = self.dev.check_output("%s %s" % (self.ip_cmd, self.iface))
        self.get_interface_ipv4addr(output)
        self.get_interface_ipv6addr(output)
        self.get_interface_macaddr()

    def get_interface_ipv4addr(self, value):
        """
        Function to get the ipv4 interface address.
        This will return the object of ipv4 interface module.

        """
        ipaddr = re.search('inet?\s([\d./\d]*).*', value)
        if ipaddr:
            ipaddr4 = ipaddr.group(1)
            if re.search('netmask?\s([\d./\d]*).*', value):
                netmask = re.search('netmask?\s([\d./\d]*).*', value).group(1)
                ipaddr4 = "/".join([ipaddr4, netmask])
            try:
                self._ipv4 = ipaddress.IPv4Interface(six.text_type(ipaddr4))

            except (ipaddress.AddressValueError):
                raise BFTypeError(
                    "Failed at calculating IP address for the given data - device: %s interface: %s"
                    % (self.dev.name, self.iface))

    def get_interface_ipv6addr(self, output):
        """
        Function to get the ipv6 interface address.
        This will return the object of ipv6 interface module.

        """
        ipv6_list = re.findall('(inet6\s[0-9a-fA-F]{0,4}[:]{0,2}.*)', output)
        if ipv6_list:
            for var in ipv6_list:
                ipaddr = re.search(
                    'inet6\s(([0-9a-fA-F]{0,4}[:]{0,2}[/\d]*)*).*', var)
                try:
                    if 'global' in var:
                        self.global_ipv6_list = []
                        self.global_ipv6_list.append(
                            ipaddress.IPv6Interface(
                                six.text_type(ipaddr.group(1))))
                        self._ipv6 = self.global_ipv6_list[0]
                    if 'link' in var:
                        self._ipv6_link_local = ipaddress.IPv6Interface(
                            six.text_type(ipaddr.group(1)))

                except (ipaddress.AddressValueError):
                    raise BFTypeError(
                        "Failed at calculating IP address for the given data - device: %s interface: %s"
                        % (self.dev.name, self.iface))
        else:
            pass

    def get_interface_macaddr(self):
        """
        Function to get the interface mac address.
        This will return the object of mac interface module.

        """
        self.dev.sendline('cat /sys/class/net/%s/address' % self.iface)
        self.dev.expect_exact('cat /sys/class/net/%s/address' % self.iface)
        self.dev.expect(LinuxMacFormat)
        self._mac = netaddr.EUI(self.dev.after)
        self.dev.expect(pexpect.TIMEOUT, timeout=1)

    netmask = property(lambda self: self._ipv4.netmask, None)
    network = property(lambda self: self._ipv4.network, None)
    prefixlen = property(lambda self: self._ipv6._prefixlen, None)
    ipv6_link_local = property(lambda self: self._ipv6_link_local.ip, None)
    network_v6 = property(lambda self: self._ipv6.network, None)
    ipv4 = property(lambda self: self._ipv4.ip, None)
    ipv6 = property(lambda self: self._ipv6.ip, None)
    mac_address = property(lambda self: self._mac, None)


if __name__ == '__main__':
    import sys
    from boardfarm.devices.base import BaseDevice

    class DummyDevice(BaseDevice):
        def __init__(self):
            super().__init__(command="bash --noprofile --norc",
                             encoding='utf-8')
            self.sendline('export PS1="dummy>"')
            self.expect_exact('export PS1="dummy>"')
            self.prompt = ["dummy>"]

    dev = DummyDevice()
    dev.obj = bft_iface(dev, sys.argv[1], sys.argv[2])
    dev.obj.refresh()
