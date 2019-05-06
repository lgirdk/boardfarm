# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import re

def tcpdump_capture(device, ip_address, port, capture_file):
    device.sendline("tcpdump -i %s -n \'portrange %s\' -w /tmp/%s &" %(ip_address, port, capture_file))
    device.expect(device.prompt)
    return device.before

def kill_process(device, process="tcpdump"):
    device.sendline("killall %s" %process)
    device.expect(device.prompt)
    return device.before

def tcpdump_read(device, capture_file):
    device.sendline("tcpdump -n -r /tmp/%s" %(capture_file))
    device.expect(device.prompt)
    output = device.before
    device.sendline("rm /tmp/%s" %(capture_file))
    device.expect(device.prompt)
    return output

def nmap_cli(device, ip_address, port, protocol=None, retry="0"):
    if protocol == "tcp":
        device.sendline("nmap -sS %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    elif protocol == "udp":
        device.sendline("nmap -sU %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    else:
        device.sendline("nmap -sS -sU %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    device.expect(device.prompt,timeout=200)
    return device.before

def ping(device, ping_ip, ping_interface=None, count=4):
    if ping_interface == None:
        device.sendline("ping -c %s %s"%(count,ping_ip))
    else:
        device.sendline("ping -I %s -c %s %s"%(ping_interface,count,ping_ip))
    device.expect(device.prompt, timeout=50)
    match = re.search("%s packets transmitted, %s received, 0%% packet loss" % (count, count), device.before)
    if match:
        return True
    else:
        return False
