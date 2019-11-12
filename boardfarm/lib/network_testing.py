# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

from boardfarm.lib.common import retry_on_exception
import ipaddress

def tcpdump_capture(device, interface, port=None, capture_file='pkt_capture.pcap'):

    if port == None:
        device.sudo_sendline("tcpdump -i %s -n -w %s &" % (interface, capture_file))
    else:
        device.sudo_sendline("tcpdump -i %s -n \'portrange %s\' -w %s &" % (interface, port, capture_file))
    device.expect(device.prompt)
    return device.before

def kill_process(device, process="tcpdump"):
    device.sudo_sendline("killall %s" % process)
    device.expect(device.prompt)
    device.sudo_sendline("sync")
    device.expect(device.prompt)
    return device.before

def tcpdump_read(device, capture_file, protocol=''):
    device.sudo_sendline("tcpdump -n -r %s %s" % (capture_file, protocol))
    device.expect(device.prompt)
    output = device.before
    device.sudo_sendline("rm %s" % (capture_file))
    device.expect(device.prompt)
    return output


def sip_read(device, capture_file):
    """
    To filter SIP packets from the captured file.
    Parameters:
        device (obj): Device where the captured file is located
        capture_file : return value of tcpdump_capture fn
    Returns:
        output_sip (str): Filtered SIP packets
    """
    device.sudo_sendline("tshark -r %s -Y sip" % (capture_file))
    device.expect(device.prompt)
    output_sip = device.before
    return output_sip

def rtp_read_verify(device, capture_file):
    """
    To filter RTP packets from the captured file and verify.
    Parameters:
        device (obj): Device where the captured file is located
        capture_file : return value of tcpdump_capture fn
    Returns:
        None
    """
    device.sudo_sendline("tshark -r %s -Y rtp" % (capture_file))
    device.expect("RTP")

def basic_call_verify(output_sip, ip_src):
    """
    To verify basic call flow with sip messages.
    Parameters:
        output_sip (str): return value of sip_read
        ip_src (str): IP of device which initiates the call
    Returns:
        None
    """
    import re
    sip_msg = re.search(".*" + ip_src + ".*INVITE.*?" + ip_src + "\s+SIP.*100\s+Trying.*?" + ip_src + "\s+SIP.*180\s+Ringing.*?" + ip_src + "\s+SIP\/SDP.*200\s+OK.*?" + ip_src + ".*ACK.*?" + ip_src + ".*BYE.*?" + ip_src + "\s+SIP.*200\s+OK\s+\|", output_sip, re.DOTALL)
    assert sip_msg is not None, "SIP call failed"

def nmap_cli(device, ip_address, port, protocol = None, retry = 0, timing = '', optional = ''):
    """
    To run port scanning on the specified target.
    This method is used to perform port scanning on the specified port range of the target ip specified from the device specified.
    Parameters: (object)device
                (string)target_ip
                (string)port rane to be scanned
                (string)protocol (tcp/ucp/both)
                (int)max_retries
                (string)timing (-T[1-4])
                (int)min_rate
    Returns: (string) output of namp command.
    """
    if not protocol:
        protocol = "both"
    ipv6 = '-6' if 'IPv6Address' == type(ipaddress.ip_address(unicode(ip_address))).__name__ else ''
    protocol_commandmap = {"tcp" : "-sT" , "udp" : "-sU", "both" : "-sT -sU"}
    device.sudo_sendline("nmap %s %s %s %s -p%s -Pn -r -max-retries %s %s > nmap_logs.txt" % (ipv6, timing, protocol_commandmap[protocol], ip_address, port, retry, optional))
    retry_on_exception(device.expect, (device.prompt,), retries = 16, tout = 30)
    device.sendline("cat nmap_logs.txt")
    device.expect(device.prompt)
    nmap_output = device.before
    device.sendline("rm nmap_logs.txt")
    device.expect(device.prompt)
    return nmap_output

def ssh_service_verify(device, dest_device, ip, opts="", ssh_key="-oKexAlgorithms=+diffie-hellman-group1-sha1"):
    """
    This function assumes that the server does not know the identity of the client!!!!!
    I.e. no passwordless login
    """
    device.sendline("ssh %s@%s" % (dest_device.username, ip))
    try:
        idx = device.expect(['no matching key exchange method found'] + ['(yes/no)'] + ['assword:'], timeout=60)
        if idx == 0:
            device.expect(device.prompt)
            device.sendline("ssh %s %s@%s %s" % (ssh_key, dest_device.username, ip, opts))
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
        raise Exception("Failed to connect SSH to :%s" % device.before)

def telnet_service_verify(device, dest_device, ip, opts=""):
    device.sendline("telnet%s %s" % (opts, ip))
    try:
        device.expect(["Username:"] + ["login:"], timeout=60)
        device.sendline(dest_device.username)
        device.expect(["assword:"])
        device.sendline(dest_device.password)
        device.expect(dest_device.prompt, timeout=40)
        device.sendline("exit")
        device.expect(device.prompt, timeout=20)
    except Exception as e:
        print(e)
        raise Exception("Failed to connect telnet to :%s" % device.before)
