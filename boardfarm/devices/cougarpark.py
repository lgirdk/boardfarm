# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.lib import common
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from . import openwrt_router
import ipaddress
from . import connection_decider
import signal
from . import linux
import sys

KEY_ESCAPE = '\x1B'
KEY_UP = '\x1b[A'
KEY_DOWN = '\x1b[B'
KEY_F4 = '\x1b[OS'

MODE_DISABLED = 0
MODE_NSGMII1 = 2
MODE_NSGMII2 = 3


class CougarPark(openwrt_router.OpenWrtRouter):
    '''
    Intel Cougar Park board
    '''
    model = ("cougarpark")

    wan_iface = "erouter0"
    lan_iface = "brlan0"

    lan_network = ipaddress.IPv4Network(u"192.168.0.0/24")
    lan_gateway = ipaddress.IPv4Address(u"192.168.0.1")

    uprompt = ["Shell>"]
    delaybetweenchar = 0.2
    uboot_ddr_addr = "0x10000000"
    uboot_eth = "eth0"

    arm = None

    def __init__(self, *args, **kwargs):
        super(CougarPark, self).__init__(*args, **kwargs)

        del kwargs['conn_cmd']
        self.arm = bft_pexpect_helper.spawn.__new__(linux.LinuxDevice)
        arm_conn = connection_decider.connection(kwargs['connection_type'],
                                                 device=self.arm,
                                                 conn_cmd=self.conn_list[1],
                                                 **kwargs)
        arm_conn.connect()
        self.consoles.append(self.arm)
        self.arm.logfile_read = sys.stdout
        self.arm.start = self.start

    def kill_console_at_exit(self):
        self.kill(signal.SIGKILL)
        self.arm.kill(signal.SIGKILL)

    def wait_for_boot(self):
        '''
        Break into Shell.
        '''
        # Try to break into uboot
        self.expect('Remaining timeout:', timeout=30)
        self.send(KEY_ESCAPE)
        self.expect('startup.nsh', timeout=30)
        self.send(KEY_ESCAPE)
        self.expect_exact(self.uprompt, timeout=30)

    def switch_to_mode(self, index):
        self.sendline('exit')
        self.expect_exact('Device Manager')
        self.send(KEY_DOWN)
        self.send(KEY_DOWN)
        self.sendline(KEY_DOWN)
        self.expect_exact('System  Setup')
        self.sendline()
        self.expect_exact('Puma7 Configuration')
        self.sendline(KEY_DOWN)
        self.expect_exact('BIOS Network Configuration')
        self.send(KEY_DOWN)
        self.send(KEY_DOWN)
        self.sendline(KEY_DOWN)
        self.expect_exact('Disabled')
        self.send(KEY_UP)
        self.send(KEY_UP)
        self.send(KEY_UP)
        self.send(KEY_UP)
        for i in range(1, index):
            self.send(KEY_DOWN)
        self.sendline()
        self.send(KEY_F4)
        self.send(KEY_F4)
        self.send('Y')
        self.send(KEY_ESCAPE)
        self.send(KEY_UP)
        self.send(KEY_UP)
        self.sendline(KEY_UP)
        self.sendline()
        self.wait_for_boot()

    def setup_uboot_network(self, tftp_server):
        lan = self.dev.lan

        # we override to use LAN because that's the only way it works for this device
        lan.start_tftp_server()
        self.tftp_server_int = lan.gw

        # line sep for UEFI
        self.linesep = '\x0D'

        self.switch_to_mode(MODE_NSGMII2)

        self.sendline('ifconfig -l')
        self.expect_exact(self.uprompt)
        self.sendline('ifconfig -c %s' % self.uboot_eth)
        self.expect_exact(self.uprompt, timeout=30)
        self.sendline('ifconfig -s %s static %s 255.255.255.0 %s' %
                      (self.uboot_eth, tftp_server + 1, tftp_server))
        self.expect_exact(self.uprompt, timeout=30)
        self.sendline('ifconfig -l')
        self.expect_exact(self.uprompt)
        self.sendline('ping %s' % tftp_server)
        if 0 == self.expect([
                'Echo request sequence 1 timeout',
                '10 packets transmitted, 10 received, 0% packet loss, time 0ms'
        ]):
            raise Exception("Failing to ping tftp server, aborting")
        self.expect_exact(self.uprompt, timeout=30)

    def flash_linux(self, KERNEL):
        print("\n===== Updating kernel and rootfs =====\n")
        lan = self.dev.lan
        filename = self.prepare_file(KERNEL,
                                     tserver=lan.ipaddr,
                                     tport=lan.port)

        self.sendline(
            'tftp -p %s -d %s %s' %
            (self.uboot_ddr_addr, lan.tftp_server_ip_int(), filename))
        self.expect_exact('TFTP  general status Success')
        if 0 == self.expect_exact(['TFTP TFTP Read File status Time out'] +
                                  self.uprompt,
                                  timeout=60):
            raise Exception("TFTP timed out")

        self.sendline('update -a A -s %s' % self.uboot_ddr_addr)
        if 0 == self.expect_exact([
                'UImage has wrong version magic',
                'Congrats! Looks like everything went as planned! Your flash has been updated! Have a good day!'
        ]):
            raise Exception("Image looks corrupt")
        self.expect_exact(self.uprompt, timeout=30)

    def boot_linux(self, rootfs=None, bootargs=None):
        common.print_bold("\n===== Booting linux for %s =====" % self.model)
        self.switch_to_mode(MODE_DISABLED)
        self.sendline('npcpu start')
        self.sendline('bootkernel -c %kernel_cmd_line%')
        self.delaybetweenchar = None
