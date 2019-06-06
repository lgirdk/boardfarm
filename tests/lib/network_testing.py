# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import re

def tcpdump_capture(device, interface, port=None, capture_file='pkt_capture.pcap'):
    if port == None:
        device.sudo_sendline("tcpdump -i %s -n -w %s &" %(interface, capture_file))
    else:
        device.sudo_sendline("tcpdump -i %s -n \'portrange %s\' -w %s &" %(interface, port, capture_file))
    device.expect(device.prompt)
    return device.before

def kill_process(device, process="tcpdump"):
    device.sudo_sendline("killall %s" %process)
    device.expect(device.prompt)
    return device.before

def tcpdump_read(device, capture_file):
    device.sudo_sendline("tcpdump -n -r %s" %(capture_file))
    device.expect(device.prompt)
    output = device.before
    device.sudo_sendline("rm %s" %(capture_file))
    device.expect(device.prompt)
    return output

def nmap_cli(device, ip_address, port, protocol=None, retry="0"):
    if protocol == "tcp":
        device.sudo_sendline("nmap -sS %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    elif protocol == "udp":
        device.sudo_sendline("nmap -sU %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    else:
        device.sudo_sendline("nmap -sS -sU %s -p %s -Pn -r -max-retries %s" %(ip_address,port,retry))
    device.expect(device.prompt,timeout=200)
    return device.before

def ping(device, ping_ip, ping_interface=None, count=4):
    if ping_interface == None:
        device.sudo_sendline("ping -c %s %s"%(count,ping_ip))
    else:
        device.sudo_sendline("ping -I %s -c %s %s"%(ping_interface,count,ping_ip))
    device.expect(device.prompt, timeout=50)
    match = re.search("%s packets transmitted, %s received, 0%% packet loss" % (count, count), device.before)
    if match:
        return True
    else:
        return False

def ssh_service_verify(device, ip, password, username=None, opts=""):
    if username == None:
        device.sendline("ssh %s" %ip)
    else:
        device.sendline("ssh %s@%s" %(username, ip))
    try:
        idx = device.expect(['diffie-hellman-group1-sha1']+ ['(yes/no)']+ ['assword:'], timeout=60)
        if idx == 0:
            device.expect(device.prompt)
            if username == None:
                device.sendline(" ssh -oKexAlgorithms=+diffie-hellman-group1-sha1 %s" %ip)
            else:
                device.sendline(" ssh -oKexAlgorithms=+diffie-hellman-group1-sha1 %s@%s %s" %(username, ip, opts))
            indx = device.expect(['(yes/no)']+ ['assword:'], timeout=60)
            assert indx <= 1, "Login using diffie-hellman-group1-sha1 failed"
            if indx == 0:
                device.sendline('yes')
                device.expect("assword:")
        if idx == 1 :
            device.sendline('yes')
            device.expect("assword:")
        device.sendline(password)
        device.expect(["mainMenu>"]+ device.prompt)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except:
        raise Exception("Failed to connect SSH to :%s" %device.before)
