"""Raspberry pi board device class with OpenWrtRouter OS installed."""
# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import ipaddress
import os

import pexpect

from boardfarm.lib import common

from . import openwrt_router


class RPI(openwrt_router.OpenWrtRouter):
    """Raspberry pi board device class with OpenWrtRouter OS installed."""

    model = "rpi3"

    wan_iface = "erouter0"
    lan_iface = "brlan0"

    lan_network = ipaddress.IPv4Network("10.0.0.0/24")
    lan_gateway = ipaddress.IPv4Address("10.0.0.1")

    uprompt = ["U-Boot>"]
    uboot_eth = "sms0"
    uboot_ddr_addr = "0x1000000"
    uboot_net_delay = 0

    fdt = "uImage-bcm2710-rpi-3-b.dtb"
    fdt_overlay = "uImage-pi3-disable-bt-overlay.dtb"

    # can't get u-boot to work without a delay
    delaybetweenchar = 0.05

    # allowed open ports (starting point)
    wan_open_ports = ["22", "8080", "8087", "8088", "8090"]

    flash_meta_booted = True

    cdrouter_config = "configs/cdrouter-rdkb.conf"

    def flash_uboot(self, uboot):
        """Flash the Raspberry pi board with the Universal Bootloader image.

        In this case it's flashing the vfat partition of the bootload.
        Need to have that image u-boot and serial turned on via dtoverlay
        for things to work after flashing.

        :param uboot: Indicates the absolute location of the file to be used to flash.
        :type uboot: string
        """
        common.print_bold("\n===== Flashing bootloader (and u-boot) =====\n")
        filename = self.prepare_file(uboot)
        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)

        self.sendline("mmc part")
        # get offset of ext (83) partition after a fat (0c) partition
        self.expect(r"\r\n\s+\d+\s+(\d+)\s+(\d+).*0c( Boot)?\r\n")
        start = hex(int(self.match.groups()[0]))
        if int(size) != int(self.match.groups()[1]) * 512:
            raise Exception("Partition size does not match, refusing to flash")
        self.expect(self.uprompt)
        count = hex(int(size / 512))
        self.sendline(f"mmc erase {start} {count}")
        self.expect(self.uprompt)
        self.sendline(f"mmc write {self.uboot_ddr_addr} {start} {count}")
        self.expect(self.uprompt, timeout=120)

        self.reset()
        self.wait_for_boot()
        self.setup_uboot_network()

    def flash_rootfs(self, ROOTFS):
        """Flash the Raspberry pi board with the ROOTFS (which in general is a patch update on the firmware).

        :param ROOTFS: Indicates the absolute location of the file to be used to flash.
        :type ROOTFS: string
        """
        common.print_bold("\n===== Flashing rootfs =====\n")
        filename = self.prepare_file(ROOTFS)

        size = self.tftp_get_file_uboot(self.uboot_ddr_addr, filename, timeout=220)
        self.sendline("mmc part")
        # get offset of ext (83) partition after a fat (0c) partition
        self.expect(r"0c( Boot)?\r\n\s+\d+\s+(\d+)\s+(\d+).*83\r\n")
        start = hex(int(self.match.groups()[-2]))
        sectors = int(self.match.groups()[-1])
        self.expect(self.uprompt)

        # increase partition size if required
        if int(size) > (sectors * 512):
            self.sendline(f"mmc read {self.uboot_ddr_addr} 0 1")
            self.expect(self.uprompt)
            gp2_sz = int(self.uboot_ddr_addr, 16) + int("0x1da", 16)
            self.sendline(f"mm 0x{gp2_sz:08x}")
            self.expect(f"{gp2_sz:08x}: {sectors:08x} ?")
            # pad 100M
            self.sendline(f"0x{int((int(size) + 104857600) / 512):08x}")
            self.sendcontrol("c")
            self.sendcontrol("c")
            self.expect(self.uprompt)
            self.sendline("echo FOO")
            self.expect_exact("echo FOO")
            self.expect_exact("FOO")
            self.expect(self.uprompt)
            self.sendline(f"mmc write {self.uboot_ddr_addr} 0 1")
            self.expect(self.uprompt)
            self.sendline("mmc rescan")
            self.expect(self.uprompt)
            self.sendline("mmc part")
            self.expect(self.uprompt)

        count = hex(int(size / 512))
        self.sendline(f"mmc erase {start} {count}")
        self.expect(self.uprompt)
        self.sendline(f"mmc write {self.uboot_ddr_addr} {start} {count}")
        self.expect_exact(f"mmc write {self.uboot_ddr_addr} {start} {count}")
        self.expect(self.uprompt, timeout=480)

    def flash_linux(self, KERNEL):
        """Flash the Raspberry pi board with a file downloaded using TFTP protocol.

        :param KERNEL: Indicates the absolute location of the file to be used to flash.
        :type KERNEL: string
        """
        common.print_bold("\n===== Flashing linux =====\n")

        filename = self.prepare_file(KERNEL)
        self.tftp_get_file_uboot(self.uboot_ddr_addr, filename)

        self.kernel_file = os.path.basename(KERNEL)
        self.sendline(
            f"fatwrite mmc 0 {self.kernel_file} {self.uboot_ddr_addr} $filesize"
        )
        self.expect(self.uprompt)

    def flash_meta(self, META, wan, lan):
        """Flash an openembedded-core to RPi. (Flashes a combine signed image using TFTP).

        :param META: Indicates the absolute location of the file to be used to flash.
        :type META: string
        :param wan: Indicates the wan device to be used
        :type wan: object
        :param lan: Indicates the lan device to be used
        :type lan: object
        """
        print("\n===== Updating entire SD card image =====\n")
        # must start before we copy as it erases files
        wan.start_tftp_server()

        filename = self.prepare_file(
            META, tserver=wan.config["ipaddr"], tport=wan.config.get("port", "22")
        )

        wan_ip = wan.get_interface_ipaddr("eth1")
        self.sendline(f"ping -c1 {wan_ip}")
        self.expect_exact("1 packets transmitted, 1 packets received, 0% packet loss")
        self.expect(self.prompt)

        self.sendline("cd /tmp")
        self.expect(self.prompt)
        self.sendline(f" tftp -g -r {filename} 10.0.1.1")
        self.expect(self.prompt, timeout=500)

        self.sendline("systemctl isolate rescue.target")
        if 0 == self.expect(
            [
                "Give root password for maintenance",
                "Welcome Press Enter for maintenance",
                "Press Enter for maintenance",
            ]
        ):
            self.sendline("password")
        else:
            self.sendline()
        self.expect_exact("sh-3.2# ")
        self.sendline("cd /tmp")
        self.expect_exact("sh-3.2# ")
        self.sendline("mount -no remount,ro /")
        self.expect_exact("sh-3.2# ")
        self.sendline(f"dd if=$(basename {filename}) of=/dev/mmcblk0 && sync")
        self.expect(pexpect.TIMEOUT, timeout=120)
        self.reset()
        self.wait_for_boot()
        # we need to update bootargs, should be doing this at build time
        self.boot_linux()
        self.wait_for_linux()

    def wait_for_linux(self):
        """Reboot the device waits for the menu.

        This method enables Device.DeviceInfo.X_RDKCENTRAL-COM_CaptivePortalEnable before rebooting.
        """
        super(RPI, self).wait_for_linux()

        self.sendline("cat /etc/issue")
        if 0 == self.expect(["OpenEmbedded"] + self.prompt):
            self.routing = False
            self.wan_iface = "eth0"
            self.lan_iface = None
            self.expect(self.prompt)

        self.sendline(
            "dmcli eRT getv Device.DeviceInfo.X_RDKCENTRAL-COM_CaptivePortalEnable"
        )
        if (
            self.expect(
                ["               type:       bool,    value: false", "dmcli: not found"]
                + self.prompt
            )
            > 1
        ):
            self.sendline(
                "dmcli eRT setv Device.DeviceInfo.X_RDKCENTRAL-COM_CaptivePortalEnable bool false"
            )
            self.expect(self.prompt)
            self.sendline("reboot")
            super(RPI, self).wait_for_linux()

    def boot_linux(self, rootfs=None, bootargs=""):
        """Boots the RPi's OS.

        :param rootfs: Indicates the rootsfs image path if needs to be loaded (parameter to be used at later point), defaults to None.
        :type rootfs: NA
        :param bootargs: Indicates the boot parameters to be specified if any (parameter to be used at later point), defaults to empty string "".
        :type bootargs: string
        """
        common.print_bold(f"\n===== Booting linux for {self.model} =====")

        self.sendline("fdt addr $fdt_addr")
        self.expect(self.uprompt)
        self.sendline("fdt get value bcm_bootargs /chosen bootargs")
        self.expect(self.uprompt)

        self.sendline(f'setenv bootargs "$bcm_bootargs {bootargs}"')
        self.expect(self.uprompt)

        self.sendline(
            "setenv bootcmd 'fatload mmc 0 ${kernel_addr_r} %s; bootm ${kernel_addr_r} - ${fdt_addr}; booti ${kernel_addr_r} - ${fdt_addr}'"
            % getattr(self, "kernel_file", "uImage")
        )
        self.expect(self.uprompt)
        self.sendline("saveenv")
        self.expect(self.uprompt)
        self.sendline("boot")

        # Linux handles serial better ?
        self.delaybetweenchar = None
