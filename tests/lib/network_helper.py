# -*- coding: utf-8 -*-
from netaddr import *
import socket
import struct

class mac_snmp(mac_unix):
    word_fmt = '.%2X'
    word_sep = ':'

def mac_to_snmp_format(mac_addr):
    mac = EUI(mac_tmp, dialect=mac_snmp)
    return str(mac)

def ipv4_to_snmp_format(ipv4_str, ip_decimal=10):
    assert ip_decimal in [2, 10, 16] , "IP Address Type Errori, unsupported base type"

    return socket.inet_ntoa(struct.pack('I',socket.htonl(int(ipv4_format, ip_decimal))))
