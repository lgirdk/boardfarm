# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm.devices import board, wan
from boardfarm.devices import prompt


class SNMPSysDescrWAN(rootfs_boot.RootFSBootTest):
    '''Runs SNMP sysDescr on WAN iface'''
    def runTest(self):
        wan.sendline(
            'apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install snmp'
        )
        wan.expect(prompt)

        wan_ip = board.get_interface_ipaddr(board.wan_iface)

        wan.sendline('snmpget -v2c -c public %s 1.3.6.1.2.1.1.1.0' % wan_ip)
        wan.expect('iso.3.6.1.2.1.1.1.0 = STRING: ')
        wan.expect(prompt)

        self.result_message = wan.before
