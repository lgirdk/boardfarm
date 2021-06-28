#!/usr/bin/env python3

import binascii
import re


def configure_option(opt, args):
    dhcp_opt = {
        "60": configure_option60,
        "61": configure_option61,
        "125": configure_option125,
        "17": configure_v6_option17,
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
        mac = device.get_interface_macaddr(device.iface_dut)
        cmd = (
            "sed -i -e 's/^#\{0,\}send dhcp-client-identifier.*/send dhcp-client-identifier %s;/' /etc/dhcp/dhclient.conf"  # noqa: W605
            % (mac)
        )
    else:
        cmd = "sed -i -e 's/^send dhcp-client-identifier/#send dhcp-client-identifier/' /etc/dhcp/dhclient.conf"
    device.check_output(cmd)
    device.check_output("cat /etc/dhcp/dhclient.conf |grep dhcp-client-identifier")


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
            mac = device.get_interface_macaddr(device.iface_dut)
            value = "VAAU" + "".join(mac.split(":")[0:4]).upper()
            encoded_name = str.encode(value)
            hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
            code_02 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
            len_02 = hex(len(value)).replace("0x", "").zfill(2)
            total_len = hex(18 + len(value)).replace("0x", "").zfill(2)
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


def configure_v6_option17(device, enable=False):
    """
    Configure LAN identity DHCPv6 option 17.
    :param device: LAN device to configure option 17
    :type device: LAN object
    :param enable: Add or remove dhcpv6 option 17
    :type enable: bool
    """
    if not enable:
        device.sendline(
            "sed -i -e 's|ntp-servers, dhcp6.vendor-opts|ntp-servers|' /etc/dhcp/dhclient.conf"
        )
        device.expect(device.prompt)
        device.sendline("sed -i '/dhcp6.vendor-opts/d' /etc/dhcp/dhclient.conf")
        device.expect(device.prompt)
    else:
        out = device.check_output("egrep 'dhcp6.vendor-opts' /etc/dhcp/dhclient.conf")
        if not re.search("request dhcp6.vendor-opts,", out):
            device.sendline(
                "sed -i -e 's|ntp-servers;|ntp-servers, dhcp6.vendor-opts; |' /etc/dhcp/dhclient.conf"
            )
            device.expect(device.prompt)
            # Enterprise code (3561) 00:00:0D:E9
            # code 11  length 06  (BFVER0) 42:46:56:45:52:30
            # code 13  length 06  (BFCLAN)  42:46:43:4c:41:4e
            encoded_name = str.encode(device.name)
            hex_name = iter(binascii.hexlify(encoded_name).decode("utf-8"))
            code_12 = ":".join([f"{j}{k}" for j, k in zip(hex_name, hex_name)])
            len_12 = hex(len(device.name)).replace("0x", "").zfill(2)
            option_17 = f"00:00:0D:E9:00:0b:00:06:42:46:56:45:52:30:00:0c:00:{len_12}:{code_12}:00:0d:00:06:42:46:43:4c:41:4e"
            device.sendline("cat >> /etc/dhcp/dhclient.conf << EOF")
            device.sendline(f"send dhcp6.vendor-opts {option_17};")
            device.sendline("")
            device.sendline("EOF")
            device.expect(device.prompt)
