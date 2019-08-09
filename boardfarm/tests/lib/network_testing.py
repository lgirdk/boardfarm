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
    device.sudo_sendline("sync")
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

def ssh_service_verify(device, dest_device, ip, opts="", ssh_key="-oKexAlgorithms=+diffie-hellman-group1-sha1"):
    """
    This function assumes that the server does not know the identity of the client!!!!!
    I.e. no passwordless login
    """
    device.sendline("ssh %s@%s" %(dest_device.username, ip))
    try:
        idx = device.expect(['no matching key exchange method found']+ ['(yes/no)']+ ['assword:'], timeout=60)
        if idx == 0:
            device.expect(device.prompt)
            device.sendline("ssh %s %s@%s %s" %(ssh_key, dest_device.username, ip, opts))
            idx = device.expect(['(yes/no)'] + ['assword:'], timeout=60)
            if idx == 0:
                idx = 1
        if idx == 1:
            device.sendline('yes')
            device.expect("assword:")
        device.sendline(dest_device.password)
        device.expect(dest_device.prompt)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except Exception as e:
        print(e)
        raise Exception("Failed to connect SSH to :%s" %device.before)

def telnet_service_verify(device, dest_device, ip, opts=""):
    device.sendline("telnet%s %s" %(opts, ip))
    try:
        device.expect(["Username:"], timeout=60)
        device.sendline(dest_device.username)
        device.expect(["assword:"])
        device.sendline(dest_device.password)
        device.expect(dest_device.prompt, timeout=40)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except Exception as e:
        print(e)
        raise Exception("Failed to connect telnet to :%s" %device.before)
