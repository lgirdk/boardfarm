# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import common
import openwrt_router
import pexpect

class CougarPark(openwrt_router.OpenWrtRouter):
    '''
    Intel Cougar Park board
    '''

    wan_iface = "erouter0"
    lan_iface = "brlan0"

    uprompt = ["Shell>"]
    delaybetweenchar = 0.2
    uboot_ddr_addr = "0x10000000"
    uboot_eth = "eth0"

    def wait_for_boot(self):
        '''
        Break into Shell.
        '''
        # Try to break into uboot
        self.expect('Remaining timeout:',timeout=30)
        self.send('\x1B')
        self.expect('startup.nsh',timeout=30)
        self.send('\x1B')
        self.expect_exact('Shell>',timeout=30)

    def setup_uboot_network(self):
        # line sep for UEFI
        self.linesep = '\x0D'
        # required delay for networking to work...
        self.expect(pexpect.TIMEOUT, timeout=15)
        self.sendline('ifconfig -c %s' % self.uboot_eth)
        self.sendline('ifconfig -s %s dhcp' % self.uboot_eth)
        self.expect_exact('Shell>',timeout=30)
        self.sendline('ifconfig -l')
        self.expect_exact('IP address: 192.168.0.')
        self.expect_exact('Gateway: 192.168.0.1')
        self.expect_exact('Shell>',timeout=30)
        self.sendline('ping 192.168.0.1')
        self.sendline('10 packets transmitted, 10 received, 0% packet loss, time 0ms')
        self.expect_exact('Shell>',timeout=30)

    def flash_linux(self, KERNEL):
        print("\n===== Updating kernel and rootfs =====\n")
        filename = self.prepare_file(KERNEL)

        self.sendline('tftp -p %s -d 192.168.0.1 %s' % (self.uboot_ddr_addr, filename))
        self.expect_exact('TFTP  general status Success')
        self.expect_exact('Shell>',timeout=30)

        self.sendline('update -a A -s %s' % self.uboot_ddr_addr)
        self.expect_exact('Congrats! Looks like everything went as planned! Your flash has been updated! Have a good day!')
        self.expect_exact('Shell>',timeout=30)

    def boot_linux(self, rootfs=None, bootargs=None):
        common.print_bold("\n===== Booting linux for %s on %s =====" % (self.model, self.root_type))
        self.sendline('bootkernel')
        self.delaybetweenchar = None
