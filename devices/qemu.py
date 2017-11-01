# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import common
import openwrt_router
import sys
import pexpect
import atexit

class Qemu(openwrt_router.OpenWrtRouter):
    '''
    Emulated QEMU board
    '''

    wan_iface = "eth0"
    lan_iface = "brlan0"

    # allowed open ports (starting point, dns is on wan?)
    wan_open_ports = ['22', '53']

    def __init__(self,
                 model,
                 conn_cmd,
                 power_ip,
                 power_outlet,
                 output=sys.stdout,
                 password='bigfoot1',
                 web_proxy=None,
                 tftp_server=None,
                 tftp_username=None,
                 tftp_password=None,
                 tftp_port=None,
                 connection_type=None,
                 power_username=None,
                 power_password=None,
                 rootfs=None,
                 env=None,
                 **kwargs):

        self.dl_console = None
        if rootfs.startswith("http://") or rootfs.startswith("https://"):
            self.dl_console = pexpect.spawn("bash --noprofile --norc")
            self.dl_console.sendline('export PS1="prompt>>"')
            self.dl_console.expect_exact("prompt>>")
            self.dl_console.sendline('mktemp')
            self.dl_console.expect('/tmp/tmp.*')
            self.fname = self.dl_console.match.group(0).strip()
            self.dl_console.expect_exact("prompt>>")
            atexit.register(self.run_cleanup_cmd)
            self.dl_console.logfile_read = sys.stdout
            print("Temp downloaded rootfs = %s" % rootfs)
            self.dl_console.sendline("curl -n -L -k '%s' > %s" % (rootfs, self.fname))
            self.dl_console.expect_exact("prompt>>", timeout=500)
            rootfs = self.fname

        cmd = "%s %s" % (conn_cmd, rootfs)

        # spawn a simple bash shell for now, will launch qemu later
        pexpect.spawn.__init__(self, command='/bin/bash',
                        args=["-c", cmd], env=env)
        self.expect("SYSLINUX")
        self.logfile_read = output

        # we can delete the downloaded rootfs now
        if self.dl_console is not None:
            self.dl_console.sendline('rm %s' % self.fname)

    def run_cleanup_cmd(self):
        if self.dl_console is not None:
            self.dl_console.sendline('rm %s' % self.fname)

    def wait_for_boot(self):
        pass

    def setup_uboot_network(self):
        pass

    def flash_rootfs(self, ROOTFS):
        pass

    def wait_for_linux(self):
        if 0 != self.expect(["login:", "Automatic boot in"]):
            self.sendline()
            self.expect('login:')

    def boot_linux(self, rootfs=None, bootargs=None):
        pass

    def reset(self):
        self.sendcontrol('a')
        self.send('c')
        self.sendline('system_reset')
        self.expect('SYSLINUX')
        self.sendcontrol('a')
        self.send('c')
