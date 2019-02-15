# -*- coding: utf-8 -*-
from netaddr import *
import socket
import struct
import re

def mac_to_snmp_format(mac_addr):
    if mac_addr != None:
        try:
            mac_tmp = re.sub("[\s+\.\!\-\:\/_,$%^*(+\"\')]+|[+()?【】“”！，。？、~@#￥%……&*（）]+',","",mac_addr)
            mac = EUI(mac_tmp,dialect=mac_unix)
            mac_final = str(mac).upper()
            return mac_final
        except:
            assert False , 'Mac Type is Error!'
    else:
        assert False , 'Error, MAC is None!'

'''IP Decimal Type 2, 10, 16
e.g.
ip2addr = '10101100000100000000000100000001'
ip10addr = '2886729985'
ip16addr = 'AC100101'
ip = ipv4_format(ip$addr,$decimal)
also turn to 172.16.1.1
'''
def ipv4_to_snmp_format(ipv4_str,ip_decimal):
    type_list = [2,10,16]
    ipv4_format = re.sub("[\s+\.\!\-\:\/_,$%^*(+\"\')]+|[+()?【】“”！，。？、~@#￥%……&*（）]+',","",ipv4_str)
    if ip_decimal in type_list:
        ipv4_address = socket.inet_ntoa(struct.pack('I',socket.htonl(int(ipv4_format,ip_decimal))))
    else:
        assert False , "IP Address Type Error"
    return ipv4_address
