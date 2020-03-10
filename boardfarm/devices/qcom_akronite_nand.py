# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.lib import common

from . import qcom_arm_base


class QcomAkroniteRouterNAND(qcom_arm_base.QcomArmBase):
    """QcomAkroniteRouter board loader/configuration class derived from QcomArmBase
    """
    model = ("ipq8066", "db149", "ap145", "ap148", "ap148-osprey",
             "ap148-beeliner", "ap160-1", "ap160-2", "ap161")

    machid_table = {
        "db149": "125b",
        "ap145": "12ca",
        "ap148": "1260",
        "ap148-beeliner": "1260",
        "ap148-osprey": "1260",
        "ap160-1": "136b",
        "ap160-2": "136b",
        "ap161": "136c",
        "dk04": "8010001"
    }
    uboot_ddr_addr = "0x42000000"

    def __init__(self, *args, **kwargs):
        """The constructor initializes all the related arguement in the parent class QcomArmBase.
        Also validates if the model passed from json actually matches the mach_id table

        :param args: arguements to be used
        :type args: list
        :param kwargs: named arguments
        :type kwargs: dict
        :raises: Unknown machid Exception
        """
        super(QcomAkroniteRouterNAND, self).__init__(*args, **kwargs)
        if self.model in self.machid_table:
            self.machid = self.machid_table[self.model]
        else:
            raise Exception("Unknown machid for %s, please add to table")

    def flash_uboot(self, uboot):
        """This method flashes the Qcom Akronite board with the Universal Bootloader image.

        :param uboot: Indicates the absolute location of the file to be used to flash.
        :type uboot: string
        """
        common.print_bold("\n===== Flashing u-boot =====\n")
        filename = self.prepare_file(uboot)
        self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.sendline('ipq_nand sbl')
        self.expect(self.uprompt)
        self.nand_flash_bin(self.uboot_addr, self.uboot_size,
                            self.uboot_ddr_addr)
        self.reset()
        self.wait_for_boot()
        self.setup_uboot_network()

    def flash_rootfs(self, ROOTFS):
        """This method flashes the Qcom Akronite board with the ROOTFS (which in general is a patch update on the firmware).

        :param ROOTFS: Indicates the absolute location of the file to be used to flash.
        :type ROOTFS: string
        """
        common.print_bold("\n===== Flashing rootfs =====\n")
        filename = self.prepare_file(ROOTFS)

        self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)
        self.nand_flash_bin(self.rootfs_addr, self.rootfs_size,
                            self.uboot_ddr_addr)

    def flash_linux(self, KERNEL):
        """This method flashes the Qcom Akronite board by copying file to the board using TFTP protocol.

        :param KERNEL: Indicates the absoulte location of the file to be used to flash.
        :type KERNEL: string
        """
        common.print_bold("\n===== Flashing linux =====\n")
        self.prepare_file(KERNEL)

        raise Exception("Kernel is in UBI rootfs, not separate")

    def boot_linux(self, rootfs=None, bootargs=""):
        """This method boots Qcom Akronite board.

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
        self.sendline("saveenv")
        self.expect(self.uprompt)
        self.sendline("print")
        self.expect(self.uprompt)
        self.sendline('run bootcmd')
        # if run isn't support, we just reset u-boot and
        # let the bootcmd run that way
        try:
            self.expect('Unknown command', timeout=5)
        except:
            pass
        else:
            self.sendline('reset')
