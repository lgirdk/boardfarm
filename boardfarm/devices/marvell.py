# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time

import pexpect
from boardfarm.lib import common

from . import openwrt_router


class WRT3200ACM(openwrt_router.OpenWrtRouter):
    """Marvell board loader/configuration class implementation extends OpenWrtRouter
    """
    model = ("wrt3200acm")

    prompt = [
        'root\\@.*:.*#',
    ]
    uprompt = ['Venom>>']
    uboot_eth = "egiga1"
    wan_iface = "wan"

    def reset(self, break_into_uboot=False):
        """This method resets the marvell board.
        Enters into uboot menu if the param break_into_uboot is True
        else it will just power reset.

        :param break_into_uboot: indicates if we want to enter to uboot menu if True enters into uboot menu else will do a power reset.
        :type break_into_uboot: boolean
        """
        if not break_into_uboot:
            self.power.reset()
        else:
            self.wait_for_boot()

    def wait_for_boot(self):
        """This method power cycles the marvell and enters to uboot menu.
        """
        self.power.reset()

        self.expect_exact('General initialization - Version: 1.0.0')
        for _ in range(10):
            self.expect(pexpect.TIMEOUT, timeout=0.1)
            self.sendline('echo FOO')
            if 0 != self.expect([pexpect.TIMEOUT] + ['echo FOO'], timeout=0.1):
                break
            if 0 != self.expect([pexpect.TIMEOUT] + ['FOO'], timeout=0.1):
                break
            if 0 != self.expect([pexpect.TIMEOUT] + self.uprompt, timeout=0.1):
                break
            time.sleep(1)

    def wait_for_linux(self):
        """This method power cycles the device waits for the linux menu.
        """
        self.wait_for_boot()
        self.sendline("boot")
        super(WRT3200ACM, self).wait_for_linux()

    def flash_linux(self, KERNEL):
        """This method flashes the marvell board by copying file to the board.

        :param KERNEL: Indicates the absoulte location of the file to be used to flash.
        :type KERNEL: string
        """
        common.print_bold("\n===== Flashing linux =====\n")
        filename = self.prepare_file(KERNEL)
        self.sendline('setenv firmwareName %s' % filename)
        self.expect(self.uprompt)
        self.sendline('run update_both_images')
        self.expect(self.uprompt, timeout=90)

    def boot_linux(self, rootfs=None, bootargs=""):
        """This method boots marvell board.

        :param rootfs: parameter to be used at later point, defaults to None.
        :type rootfs: NA
        :param bootargs: parameter to be used at later point, defaults to empty string "".
        :type bootargs: string
        """
        self.sendline('boot')
