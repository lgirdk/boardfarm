# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import openwrt_router
import signal
import sys
import pexpect
import atexit
import os
import ipaddress

class Qemu(openwrt_router.OpenWrtRouter):
    '''
    Emulated QEMU board
    '''
    model = ("qemux86")

    wan_iface = "eth0"
    lan_iface = "brlan0"

    lan_network = ipaddress.IPv4Network(u"10.0.0.0/24")
    lan_gateway = ipaddress.IPv4Address(u"10.0.0.1")

    # allowed open ports (starting point, dns is on wan?)
    wan_open_ports = ['22', '53']

    cleanup_files = []
    kvm = False

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
        self.consoles = [self]

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
            self.kvm = False

        try:
            pexpect.spawn.__init__(self, command='/bin/bash',
                            args=["-c", cmd], env=env)
            self.expect(pexpect.TIMEOUT, timeout=1)
        except pexpect.EOF:
            self.pid = None
            if 'failed to initialize KVM: Device or resource busy' in self.before or \
                    'failed to initialize KVM: Cannot allocate memory' in self.before:
                cmd = cmd.replace('--enable-kvm ', '')
                self.kvm = False
                pexpect.spawn.__init__(self, command='/bin/bash',
                            args=["-c", cmd], env=env)
            else:
                raise

        self.cmd = cmd
        if kernel is None:
            self.expect(["SYSLINUX", "GNU GRUB"])
        self.logfile_read = output

        atexit.register(self.kill_console_at_exit)

    def run_cleanup_cmd(self):
        for f in self.cleanup_files:
            if os.path.isfile(f):
                os.remove(f)

    def close(self, *args, **kwargs):
        self.kill_console_at_exit()
        return super(Qemu, self).close(*args, **kwargs)

    def kill_console_at_exit(self):
        try:
            self.sendcontrol('a')
            self.send('c')
            self.sendline('q')
            self.kill(signal.SIGKILL)
        except:
            pass

    def wait_for_boot(self):
        pass

    def setup_uboot_network(self, tftp_server=None):
        pass

    def flash_rootfs(self, ROOTFS):
        pass

    def flash_linux(self, KERNEL):
        pass

    def wait_for_linux(self):
        if self.kvm:
            tout = 60
        else:
            tout = 180

        for t in range(0, tout, 10):
            self.sendline()
            i = self.expect([pexpect.TIMEOUT, 'login:'] + self.prompt, timeout=10)
            if i == 1:
                self.sendline('root')
                self.expect(self.prompt, timeout=tout)
            if i >= 1:
                break

    def boot_linux(self, rootfs=None, bootargs=None):
        pass

    def reset(self):
        self.sendcontrol('a')
        self.send('c')
        self.sendline('system_reset')
        self.expect_exact(['system_reset', 'Linux version'])
        if '-kernel' not in self.cmd:
            self.expect(['SYSLINUX', 'GNU GRUB'])
        self.sendcontrol('a')
        self.send('c')
