#!/usr/bin/env python3

import binascii
import re


def configure_option(opt, args):
    dhcp_opt = {
        "60": configure_option60,
        "61": configure_option61,
        "125": configure_option125,
    }
    dhcp_opt[opt](*args)


def configure_option60(device, enable=False):
    """
    Configure dhcp server option 60 in lan dhclient.conf

    :param device: lan device to configure option 60
    :type device: Lan device
    :param enable: add option 60 changes is True else remove
    :type enable: Boolean
    """
    if enable:
        out = device.check_output(
            "egrep 'vendor-class-identifier' /etc/dhcp/dhclient.conf"
        )
        if not re.search("vendor-class-identifier", out):
            device.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
            device.sendline('send vendor-class-identifier "BFClient";')
            device.sendline("EOF")
            device.expect(device.prompt)
    else:
        device.sendline("sed -i '/vendor-class-identifier/d' /etc/dhcp/dhclient.conf")
        device.expect(device.prompt)


def configure_option61(device, enable=False):
    """
    Configure dhcp server option 61 in lan dhclient.conf

    :param device: lan device to configure option 61
    :type device: Lan device
    :param enable: add option 61 changes is True else remove
    :type enable: Boolean
    """
    if enable:
        cmd = "sed -i -e 's/^#send dhcp-client-identifier/send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
    else:
        cmd = "sed -i -e 's/^send dhcp-client-identifier/#send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
    device.check_output(cmd)


def configure_option125(device, enable=False):
    """
    Configure dhcp server option 125 in lan dhclient.conf

    :param device: lan device to configure option 60
    :type device: Lan device
    :param enable: add option 125 changes is True else remove
    :type enable: Boolean

    :return: return False if option125 configuration is updated in dhclient.conf else True
    :rtype: Boolean
    """
    if not enable:
        device.sendline(
            "sed -i -e 's|request option-125,|request |' /etc/dhcp/dhclient.conf"
        )
        device.expect(device.prompt)
        device.sendline("sed -i '/option-125/d' /etc/dhcp/dhclient.conf")
        device.expect(device.prompt)
    else:
        out = device.check_output("egrep 'request option-125' /etc/dhcp/dhclient.conf")
        if not re.search("request option-125,", out):
            device.sendline(
                "sed -i -e 's|request |\\noption option-125 code 125 = string;\\n\\nrequest option-125, |' /etc/dhcp/dhclient.conf"
            )
            device.expect(device.prompt)
            # details of Text for HexaDecimal value as
            # Enterprise code (3561) 00:00:0D:E9 length  (22)16
            # code 01  length 06  (BFVER0) 42:46:56:45:52:30
            # code 03  length 06  (BFCLAN)  42:46:43:4c:41:4e
            encoded_name = str.encode(device.name)
            hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
            code_02 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
            len_02 = hex(len(device.name)).replace("0x", "").zfill(2)
            total_len = hex(18 + len(device.name)).replace("0x", "").zfill(2)
            option_125 = "00:00:0D:E9:{}:01:06:42:46:56:45:52:30:02:{}:{}:03:06:42:46:43:4c:41:4e".format(
                total_len, len_02, code_02
            )
            device.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
            device.sendline("send option-125 = {};".format(option_125))
            device.sendline("")
            device.sendline("EOF")
            device.expect(device.prompt)
            return False

    return True
