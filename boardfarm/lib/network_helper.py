# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
"""Global functions to permatting acctions on network related variables."""
import ipaddress
import re

import netaddr


def mac_to_snmp_format(mac_addr):
    """Convert mac address separated with space,'.' or '-' to SNMP format.

    :param mac_addr: mac address to change format
    :type mac_addr: string
    :return: Mac address in snmp format (1A:2B:3C:4D:2A:3D)
    :rtype: string
    """
    mac_tmp = re.sub(r"[\s\.\-]", "", mac_addr)
    mac = netaddr.EUI(mac_tmp, dialect=netaddr.mac_unix_expanded)
    mac_final = str(mac).upper()

    return mac_final


def ipv4_to_snmp_format(ipv4_str):
    """Convert ipv4 address separated with space,'.' or '-' to SNMP format.

    :param ipv4_str: ipv4 address to change format
    :type ipv4_str: string
    :return: ipv4 address in snmp format("192.168.1.1" is converted to "1.146.22.1")
    :rtype: string
    """
    ipv4_tmp = re.sub(r"[\s\.\-]", "", ipv4_str)
    ipv4_decimal = int(ipv4_tmp, 16)
    ipv4_format = ipaddress.IPv4Address(ipv4_decimal)
    ipv4_address = ipaddress.ip_address(f"{ipv4_format}")

    return ipv4_address


def ipv6_to_snmp_format(ipv6_str):
    """Convert ipv6 address separated with space,'.' or '-' to SNMP format.

    :param ipv6_str: ipv6 address to change format
    :type ipv6_str: string
    :return: ipv6 address in snmp format(ex: 1.4.16.254.128.0.2.0.0.0.0.2.224.184.255.254.48.53.45)
    :rtype: string
    """
    ipv6_tmp = re.sub(r"[\s\.\-]", "", ipv6_str)
    pattern = re.compile(".{4}")
    ipv6_tmp_ip = ":".join(pattern.findall(ipv6_tmp))
    ipv6_address = ipaddress.ip_address(f"{ipv6_tmp_ip}")

    return ipv6_address


def valid_ipv4(ip_str):
    """Check whether IP address provided is valid ipv4 address.

    validation checks:
    1. A string in decimal-dot notation, consisting of four decimal integers in the inclusive range 0 to 255, separated by dots (e.g. 192.168.0.1).
    -  Each integer represents an octet (byte) in the address.
    -  Leading zeroes are tolerated only for values less than 8 (as there is no ambiguity between the decimal and octal interpretations of such strings).
    2. An integer that fits into 32 bits.
    3. An integer packed into a bytes object of length 4 (most significant octet first).

    :param ip_str: ipv4 address to check
    :type ip_str: string
    """
    ipaddress.IPv4Address(str(ip_str))


def valid_ipv6(ip_str):
    """Check whether IP address provided is valid ipv6 address.

    validation Checks
    1. A string consisting of eight groups of four hexadecimal digits, each group representing 16 bits.
    -  The groups are separated by colons. This describes an exploded (longhand) notation.
    -  The string can also be compressed (shorthand notation) by various means.
    2. An integer that fits into 128 bits.
    3. An integer packed into a bytes object of length 16, big-endian.

    :param ip_str: ipv6 address to change format
    :type ip_str: string
    """
    ipaddress.IPv6Address(str(ip_str))


def block_board_to_device_traffic(device, unblock=False):
    """block traffic to device IPs from board.

    :param device : clas device which will get block from board
    :type device: device object
    :param unblock : set true to unblock traffic to dest ip
    :type unblock : boolean
    """
    if device in [device.dev.acs_server]:
        device.block_traffic(unblock)
