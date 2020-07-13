# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import signal

from boardfarm.lib.bft_logging import LoggerMeta
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class BaseDevice(bft_pexpect_helper):
    __metaclass__ = LoggerMeta
    log = ""
    log_calls = ""

    prompt = [
        "root\\@.*:.*#",
    ]
    delaybetweenchar = None

    def get_interface_ipaddr(self, interface):
        """Get ipv4 address of interface."""
        raise Exception("Not implemented!")

    def get_interface_ip6addr(self, interface):
        """Get ipv6 address of interface."""
        raise Exception("Not implemented!")

    def get_interface_macaddr(self, interface):
        """Get the interface mac address."""
        raise Exception("Not implemented!")

    def get_seconds_uptime(self):
        """Return seconds since last reboot. Stored in /proc/uptime."""
        raise Exception("Not implemented!")

    # perf related
    def parse_sar_iface_pkts(self, wan, lan):
        self.expect(r"Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){6}\r\n")
        idle = float(self.match.group(1))
        self.expect("Average.*rxmcst/s.*\r\n")

        wan_pps = None
        client_pps = None
        if lan is None:
            exp = [wan]
        else:
            exp = [wan, lan]

        for _ in range(0, len(exp)):
            i = self.expect(exp)
            if i == 0:  # parse wan stats
                self.expect(r"(\d+.\d+)\s+(\d+.\d+)")
                wan_pps = float(self.match.group(1)) + float(self.match.group(2))
            if i == 1:
                self.expect(r"(\d+.\d+)\s+(\d+.\d+)")
                client_pps = float(self.match.group(1)) + float(self.match.group(2))

        return idle, wan_pps, client_pps

    def check_perf(self):
        self.sendline("uname -r")
        self.expect("uname -r")
        self.expect(self.prompt)

        self.kernel_version = self.before

        self.sendline("\nperf --version")
        i = self.expect(["not found", "perf version"])
        self.expect(self.prompt)

        if i == 0:
            return False

        return True

    def check_output_perf(self, cmd, events):
        perf_args = self.perf_args(events)

        self.sendline("perf stat -a -e %s time %s" % (perf_args, cmd))

    def parse_perf(self, events):
        mapping = self.parse_perf_board()
        ret = []

        for e in mapping:
            if e["name"] not in events:
                continue
            self.expect(r"(\d+) %s" % e["expect"])
            e["value"] = int(self.match.group(1))
            ret.append(e)

        return ret

    # end perf related

    def enable_ipv6(self, interface):
        """Enable ipv6 in interface."""
        raise Exception("Not implemented!")

    def disable_ipv6(self, interface):
        """Disable IPv6 in interface."""
        raise Exception("Not implemented!")

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
        """Print the when debug enabled."""
        raise Exception("Not implemented!")

    def prefer_ipv4(self, pref=True):
        """Edits the /etc/gai.conf file.

        This is to give/remove ipv4 preference (by default ipv6 is preferred)
        See /etc/gai.conf inline comments for more details
        """
        raise Exception("Not implemented!")

    def ping(self, ping_ip, source_ip=None, ping_count=4, ping_interface=None):
        """Check Ping verification from device."""
        raise Exception("Not implemented!")

    def reset(self, break_into_uboot=False):
        """Power-cycle this device."""
        if not break_into_uboot:
            self.power.reset()
            return
        for _ in range(3):
            try:
                self.power.reset()
                self.expect("U-Boot", timeout=30)
                self.expect("Hit any key ")
                self.sendline("\n\n\n\n\n\n\n")  # try really hard
                self.expect(self.uprompt, timeout=4)
                # Confirm we are in uboot by typing any command.
                # If we weren't in uboot, we wouldn't see the command
                # that we type.
                self.sendline("echo FOO")
                self.expect("echo FOO", timeout=4)
                self.expect(self.uprompt, timeout=4)
                return
            except Exception as e:
                print(e)
                print("\nWe appeared to have failed to break into U-Boot...")

    def check_memory_addresses(self):
        """Check/set memory addresses and size for proper flashing."""
        raise Exception("Not implemented!")

    def flash_uboot(self, uboot):
        raise Exception(
            "Code not written for flash_uboot for this board type, %s" % self.model
        )

    def flash_rootfs(self, ROOTFS):
        raise Exception(
            "Code not written for flash_rootfs for this board type, %s" % self.model
        )

    def flash_linux(self, KERNEL):
        raise Exception(
            "Code not written for flash_linux for this board type, %s." % self.model
        )

    def flash_meta(self, META_BUILD, wan, lan):
        raise Exception(
            "Code not written for flash_meta for this board type, %s." % self.model
        )

    def prepare_nfsroot(self, NFSROOT):
        raise Exception(
            "Code not written for prepare_nfsroot for this board type, %s." % self.model
        )

    def kill_console_at_exit(self):
        """Killing console."""
        self.kill(signal.SIGKILL)

    def get_dns_server(self):
        """Get dns server ip address."""
        raise Exception("Not implemented!")

    def touch(self):
        """Keep consoles active, so they don't disconnect for long running activities."""
        self.sendline()

    def boot_linux(self, rootfs=None, bootargs=""):
        raise Exception(
            "\nWARNING: We don't know how to boot this board to linux."
            "please write the code to do so."
        )
