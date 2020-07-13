# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# !/usr/bin/env python

import sys

import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper

from . import base


class DellSwitch(base.BaseDevice):
    """Connect to and configures a Dell Switch."""

    prompt = ["console>", "console#", r"console\(config.*\)#"]

    def __init__(self, conn_cmd, password=""):
        """Instance initialization."""
        bft_pexpect_helper.spawn.__init__(self, "/bin/bash", args=["-c", conn_cmd])
        self.logfile_read = sys.stdout
        self.password = password

    def connect(self):
        """Connect and login to switch."""
        for _ in range(10):
            self.sendline("exit")
            if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=5):
                self.sendline("enable")
                if 0 == self.expect(["Password:"] + self.prompt):
                    self.sendline(self.password)
                    self.expect(self.prompt)
                self.sendline("config")
                self.expect(self.prompt)
                return

        raise Exception("Unable to get prompt on Dell switch")

    def create_vlan(self, vlan):
        """Create a Virtual LAN."""
        self.sendline("vlan database")
        self.expect(self.prompt)
        self.sendline("vlan %s" % vlan)
        self.expect(self.prompt)
        self.sendline("exit")
        self.expect(self.prompt)

    def configure_basic_settings(self):
        """Set simple parameters."""
        self.create_vlan(4093)
        self.sendline("ip address dhcp")
        self.expect(self.prompt)
        self.sendline("ip address vlan 4093")
        self.expect(self.prompt)

    def configure_eth_private_port(self, port, override_vlan=None):
        """Set given ethernet port to ignore all VLAN tags except for one."""
        if override_vlan is None:
            vlan = 100 + port
        else:
            vlan = override_vlan

        self.create_vlan(vlan)
        self.sendline("interface ethernet 1/g%s" % port)
        self.expect(self.prompt)
        self.sendline("spanning-tree disable")
        self.expect(self.prompt)
        self.sendline("switchport mode general")
        self.expect(self.prompt)
        # NOTE: we can't change the PVID otherwise it breaks other containers
        self.sendline("switchport general pvid %s" % (100 + port))
        self.expect(self.prompt)
        self.sendline("switchport general ingress-filtering disable")
        self.expect(self.prompt)
        self.sendline("switchport forbidden vlan add 1,4093")
        self.expect(self.prompt)
        self.sendline("switchport general allowed vlan add %s" % vlan)
        self.expect(self.prompt)
        self.sendline("exit")
        self.expect(self.prompt)

    def configure_eth_trunk_port(self, port):
        """Set an ethernet port to tag traffic with VLAN identifiers."""
        self.sendline("interface ethernet 1/g%s" % port)
        self.expect(self.prompt)
        self.sendline("switchport mode trunk")
        self.expect(self.prompt)
        self.sendline("switchport forbidden vlan add 1")
        self.expect(self.prompt)
        # TODO: this secondary range should be configurable
        # maybe setting trunk ports on the device class first?
        self.sendline("switchport trunk allowed vlan add 101-148,200-210,4093")
        self.expect(self.prompt)
        self.sendline("exit")
        self.expect(self.prompt)

    def save_running_to_startup_config(self):
        """Save current configuration settings."""
        self.sendline("exit")
        self.expect(self.prompt)
        self.sendline("copy running-config startup-config")
        self.expect(self.prompt)
        self.sendline("config")
        self.expect(self.prompt)


if __name__ == "__main__":
    dell_switch = DellSwitch(sys.argv[1])
    dell_switch.connect()

    dell_switch.configure_basic_settings()
    for i in range(1, 42 + 1):
        dell_switch.configure_eth_private_port(i)
    for i in range(43, 48 + 1):
        dell_switch.configure_eth_trunk_port(i)

    print()
    print("Press Control-] to exit interact mode")
    print("=====================================")
    dell_switch.interact()
    print()
