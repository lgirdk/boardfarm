# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import common
import openwrt_router

class CougarPark(openwrt_router.OpenWrtRouter):
    '''
    Intel Cougar Park board
    '''

    #wan_iface = "erouter0"
    #lan_iface = "brlan0"

    #uprompt = ["U-Boot>"]
    #uboot_eth = "sms0"
    #uboot_ddr_addr = "0x1000000"
    #uboot_net_delay = 0

    #def flash_uboot(self, uboot):
    #    common.print_bold("\n===== Flashing bootloader (and u-boot) =====\n")

    #def flash_rootfs(self, ROOTFS):
    #    common.print_bold("\n===== Flashing rootfs =====\n")

    #def flash_linux(self, KERNEL):
    #    common.print_bold("\n===== Flashing linux =====\n")

    #def boot_linux(self, rootfs=None, bootargs=""):
    #    common.print_bold("\n===== Booting linux for %s on %s =====" % (self.model, self.root_type))
