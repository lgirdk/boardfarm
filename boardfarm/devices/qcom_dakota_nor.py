# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.lib import common

from . import qcom_arm_base


class QcomDakotaRouterNOR(qcom_arm_base.QcomArmBase):
    """QcomDakotaRouter board loader/configuration class derived from QcomArmBase."""

    model = ("dk01-nor", "dk04-nor")

    uboot_ddr_addr = "0x88000000"
    machid_table = {"dk01-nor": "8010000", "dk04-nor": "8010001"}

    def __init__(self, *args, **kwargs):
        """Instance initialization.

        The constructor initializes all the related arguements in the parent class QcomArmBase.
        Also validates if the model passed from json actually matches the mach_id table.

        :param args: arguements to be used
        :type args: list
        :param kwargs: named arguments
        :type kwargs: dict
        :raises: Unknown machid Exception
        """
        super(QcomDakotaRouterNOR, self).__init__(*args, **kwargs)
        if self.model in self.machid_table:
            self.machid = self.machid_table[self.model]
        else:
            raise Exception("Unknown machid for %s, please add to table" %
                            self.model)

    def flash_rootfs(self, ROOTFS):
        """Flashes the Qcom Dakota board with the ROOTFS.

        (which in general is a patch update on the firmware).

        :param ROOTFS: Indicates the absolute location of the file to be used to flash.
        :type ROOTFS: string
        """
        common.print_bold("\n===== Flashing rootfs =====\n")
        filename = self.prepare_file(ROOTFS)

        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.spi_flash_bin(self.rootfs_addr, size, self.uboot_ddr_addr,
                           self.rootfs_size)

    def flash_linux(self, KERNEL):
        """Flashes the Qcom Dakota board by copying file to the board.

        :param KERNEL: Indicates the absoulte location of the file to be used to flash.
        :type KERNEL: string
        """
        common.print_bold("\n===== Flashing linux =====\n")
        filename = self.prepare_file(KERNEL)

        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.spi_flash_bin(self.kernel_addr, size, self.uboot_ddr_addr,
                           self.kernel_size)

    def boot_linux(self, rootfs=None, bootargs=""):
        """Boots Qcom Dakota board.

        :param rootfs: Indicates the rootsfs image path if needs to be loaded (parameter to be used at later point), defaults to None.
        :type rootfs: NA
        :param bootargs: Indicates the boot parameters to be specified if any (parameter to be used at later point), defaults to empty string "".
        :type bootargs: string
        """
        common.print_bold("\n===== Booting linux for %s =====" % self.model)
        self.reset()
        self.wait_for_boot()
        self.sendline("setenv bootcmd bootipq")
        self.expect(self.uprompt)
        self.sendline("setenv bootargs")
        self.expect(self.uprompt)
        self.sendline("saveenv")
        self.expect(self.uprompt)
        self.sendline("print")
        self.expect(self.uprompt)
        self.sendline("run bootcmd")
        # if run isn't support, we just reset u-boot and
        # let the bootcmd run that way
        try:
            self.expect("Unknown command", timeout=5)
        except Exception:
            pass
        else:
            self.sendline("reset")
