# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import re

import netaddr
import ipaddress

def mac_to_snmp_format(mac_addr):
    mac_tmp = re.sub("[\s\.\-]", "", mac_addr)
    mac = netaddr.EUI(mac_tmp, dialect=netaddr.mac_unix)
    mac_final = str(mac).upper()

    return mac_final

def ipv4_to_snmp_format(ipv4_str):
    ipv4_tmp = re.sub("[\s\.\-]", "", ipv4_str)
    ipv4_decimal = int(ipv4_tmp, 16)
    ipv4_format = ipaddress.IPv4Address(ipv4_decimal)
    ipv4_address = ipaddress.ip_address(u'%s' % ipv4_format)

    return ipv4_address

def ipv6_to_snmp_format(ipv6_str):
    ipv6_tmp = re.sub("[\s\.\-]", "", ipv6_str)
    pattern = re.compile('.{4}')
    ipv6_tmp_ip = ':'.join(pattern.findall(ipv6_tmp))
    ipv6_address = ipaddress.ip_address(u'%s' % ipv6_tmp_ip)

    return ipv6_address

def valid_ipv4(ip_str):
    try:
        ipaddress.IPv4Address(unicode(ip_str))
        return True
    except:
        return False

def valid_ipv6(ip_str):
    try:
        ipaddress.IPv6Address(unicode(ip_str))
        return True
    except:
        return False
