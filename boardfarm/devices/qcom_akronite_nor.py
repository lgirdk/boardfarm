# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.lib import common
from . import qcom_arm_base

class QcomAkroniteRouterNOR(qcom_arm_base.QcomArmBase):
    """QcomAkroniteRouter board loader/configuration class derived from QcomArmBase
    """
    model = ("ap148-nor")

    def __init__(self, *args, **kwargs):
        """The constructor initializes all the related arguement in the parent class QcomArmBase also initializes the uboot ddr address.
        Also validates if the model passed from json actually matches the mach_id table.

        :param args: arguements to be used
        :type args: list
        :param kwargs: named arguments
        :type kwargs: dict
        :raises: Unknown machid Exception
        """
        super(QcomAkroniteRouterNOR, self).__init__(*args, **kwargs)
        self.uboot_ddr_addr = "0x42000000"
        machid_table = {"ap148-nor": "1260"}
        if self.model in machid_table:
            self.machid = machid_table[self.model]
        else:
            raise Exception("Unknown machid for %s, please add to table")

    def flash_rootfs(self, ROOTFS):
        """This method flashes the Qcom Akronite board with the ROOTFS (which in general is a patch update on the firmware).

        :param ROOTFS: Indicates the absolute location of the file to be used to flash.
        :type ROOTFS: string
        """
        common.print_bold("\n===== Flashing rootfs =====\n")
        filename = self.prepare_file(ROOTFS)

        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.spi_flash_bin("0x006b0000", size, self.uboot_ddr_addr, "0x1920000")

    def flash_linux(self, KERNEL):
        """This method flashes the Qcom Akronite board by copying file to the board.

        :param KERNEL: Indicates the absolute location of the file to be used to flash.
        :type KERNEL: string
        """
        common.print_bold("\n===== Flashing linux =====\n")
        filename = self.prepare_file(KERNEL)

        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.spi_flash_bin("0x0062b0000", size, self.uboot_ddr_addr, "0x400000")

    def boot_linux(self, rootfs = None, bootargs = ""):
        """This method boots Qcom Akronite board.

        :param rootfs: Indicates the rootsfs image path if needs to be loaded (parameter to be used at later point), defaults to None.
        :type rootfs: NA
        :param bootargs: Indicates the boot parameters to be specified if any (parameter to be used at later point), defaults to empty string "".
        :type bootargs: string
        """
        common.print_bold("\n===== Booting linux for %s on %s =====" % (self.model, self.root_type))
        self.reset()
        self.wait_for_boot()
        self.sendline("set bootargs 'console=ttyMSM0,115200'")
        self.expect(self.uprompt)
        self.sendline("set fsbootargs 'rootfstype=squashfs,jffs2'")
        self.expect(self.uprompt)
        self.sendline('set bootcmd bootipq')
        self.expect(self.uprompt)
        self.sendline("saveenv")
        self.expect(self.uprompt)
        self.sendline("print")
        self.expect(self.uprompt)
        self.sendline('run bootcmd')
