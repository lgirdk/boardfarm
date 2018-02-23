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
import os

class Qemu(openwrt_router.OpenWrtRouter):
    '''
    Emulated QEMU board
    '''
    model = ("qemux86")

    wan_iface = "eth0"
    lan_iface = "brlan0"

    # allowed open ports (starting point, dns is on wan?)
    wan_open_ports = ['22', '53']

    cleanup_files = []

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
                 kernel=None,
                 env=None,
                 **kwargs):
        self.consoles.append(self)

        if rootfs is None:
            raise Exception("The QEMU device type requires specifying a rootfs")

        def temp_download(url):
            dl_console = pexpect.spawn("bash --noprofile --norc")
            dl_console.sendline('export PS1="prompt>>"')
            dl_console.expect_exact("prompt>>")
            dl_console.sendline('mktemp')
            dl_console.expect('/tmp/tmp.*')
            fname = dl_console.match.group(0).strip()
            dl_console.expect_exact("prompt>>")
            self.cleanup_files.append(fname)
            atexit.register(self.run_cleanup_cmd)
            dl_console.logfile_read = sys.stdout
            print("Temp downloaded file = %s" % url)
            dl_console.sendline("curl -n -L -k '%s' > %s" % (url, fname))
            dl_console.expect_exact("prompt>>", timeout=500)
            dl_console.logfile_read = None
            dl_console.sendline('exit')
            dl_console.expect(pexpect.EOF)
            return fname

        if rootfs.startswith("http://") or rootfs.startswith("https://"):
            rootfs = temp_download(rootfs)

        cmd = "%s %s" % (conn_cmd, rootfs)

        if kernel is not None:
            if kernel.startswith("http://") or kernel.startswith("https://"):
                kernel = temp_download(kernel)
            cmd += " -kernel %s --append root=/dev/hda2" % kernel

        # check if we can run kvm
        kvm_chk = pexpect.spawn('sudo kvm-ok')
        if 0 != kvm_chk.expect(['KVM acceleration can be used', pexpect.EOF]):
            cmd = cmd.replace('--enable-kvm ', '')

        # spawn a simple bash shell for now, will launch qemu later
        self.cmd = cmd
        pexpect.spawn.__init__(self, command='/bin/bash',
                        args=["-c", cmd], env=env)
        if kernel is None:
            self.expect("SYSLINUX")
        self.logfile_read = output

    def run_cleanup_cmd(self):
        for f in self.cleanup_files:
            if os.path.isfile(f):
                os.remove(f)

    def wait_for_boot(self):
        pass

    def setup_uboot_network(self, tftp_server=None):
        pass

    def flash_rootfs(self, ROOTFS):
        pass

    def flash_linux(self, KERNEL):
        pass

    def wait_for_linux(self):
        self.expect('login:')
        self.sendline('root')
        self.expect(self.prompt, timeout=60) # long for non-kvm qemu

    def boot_linux(self, rootfs=None, bootargs=None):
        pass

    def reset(self):
        self.sendcontrol('a')
        self.send('c')
        self.sendline('system_reset')
        self.expect_exact('system_reset')
        if '-kernel' not in self.cmd:
            self.expect('SYSLINUX')
        self.sendcontrol('a')
        self.send('c')
