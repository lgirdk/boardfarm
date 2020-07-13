# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm import lib
from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


def install_netperf(device):
    # Check version
    device.sendline("\nnetperf -V")
    try:
        device.expect("Netperf version 2", timeout=10)
        device.expect(device.prompt)
    except:
        # Install Netperf
        device.sendline("apt-get update")
        device.expect(device.prompt, timeout=120)
        device.sendline("apt-get install netperf")
        device.expect(device.prompt, timeout=120)


class NetperfTest(rootfs_boot.RootFSBootTest):
    """Setup Netperf and Run Throughput."""

    @lib.common.run_once
    def lan_setup(self):
        lan = self.dev.lan

        super(NetperfTest, self).lan_setup()
        install_netperf(lan)

    @lib.common.run_once
    def wan_setup(self):
        wan = self.dev.wan

        super(NetperfTest, self).wan_setup()
        install_netperf(wan)
        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("kill -9 `pidof netserver`")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")

    def recover(self):
        lan = self.dev.lan
        wan = self.dev.wan

        lan.sendcontrol("c")
        lib.common.test_msg("Recover..kill netserver on wan")
        self.kill_netserver(wan)

    # if you are spawning a lot of connections, sometimes it
    # takes too long to wait for the connection to be established
    # so we use this version
    def run_netperf_cmd_nowait(self, device, ip, opts="", quiet=False):
        device.sendline("netperf -H %s %s &" % (ip, opts))

    def run_netperf_cmd(self, device, ip, opts="", quiet=False):
        if quiet:
            device.sendline("netperf -H %s %s > /dev/null &" % (ip, opts))
        else:
            device.sendline("netperf -H %s %s &" % (ip, opts))
            device.expect("TEST.*\r\n")

    def run_netperf_parse(self, device, timeout=60):
        device.expect(
            "[0-9]+\s+[0-9]+\s+[0-9]+\s+[0-9]+.[0-9]+\s+([0-9]+.[0-9]+)",
            timeout=timeout,
        )
        ret = device.match.group(1)
        lib.common.test_msg("Speed was %s 10^6bits/sec" % ret)
        return float(ret)

    def run_netperf(self, device, ip, opts="", timeout=60):
        self.run_netperf_cmd(device, ip, opts=opts)
        return self.run_netperf_parse(device)

    def kill_netserver(self, device):
        device.sendline("kill -9 `pidof netserver`")
        device.expect(prompt)

    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan
        wan = self.dev.wan

        super(NetperfTest, self).runTest()

        board.arm.sendline("mpstat -P ALL 30 1")
        board.arm.expect("Linux")

        speed = self.run_netperf(lan, "%s -c -C -l 30" % wan.gw)

        board.sendcontrol("c")
        board.expect(
            "Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){9}\r\n", timeout=60
        )
        idle_cpu = float(board.match.group(1))
        avg_cpu = 100 - float(idle_cpu)
        lib.common.test_msg("Average cpu usage was %s" % avg_cpu)
        self.kill_netserver(wan)

        self.result_message = (
            "Setup Netperf and Ran Throughput (Speed = %s 10^6bits/sec, CPU = %s)"
            % (speed, avg_cpu)
        )


###########################


def run_netperf_tcp(device, run_time, pkt_size, wangw, direction="up"):

    if direction == "up":
        cmd = "netperf -H %s -c -C -l %s -- -m %s -M %s -D" % (
            wangw,
            run_time,
            pkt_size,
            pkt_size,
        )
    else:
        cmd = "netperf -H %s -c -C -l %s -t TCP_MAERTS -- -m %s -M %s -D" % (
            wangw,
            run_time,
            pkt_size,
            pkt_size,
        )
    device.sendline(cmd)
    device.expect("TEST.*\r\n")
    device.expect(device.prompt, timeout=run_time + 4)


class Netperf_UpTCP256(rootfs_boot.RootFSBootTest):
    """Netperf upload throughput (TCP, packets size 256 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 256, wan.gw)
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)


class Netperf_UpTCP512(rootfs_boot.RootFSBootTest):
    """Netperf upload throughput (TCP, packets size 512 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 512, wan.gw)
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)


class Netperf_UpTCP1024(rootfs_boot.RootFSBootTest):
    """Netperf upload throughput (TCP, packets size 1024 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 1024, wan.gw)
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)


class Netperf_DownTCP256(rootfs_boot.RootFSBootTest):
    """Netperf download throughput (TCP, packets size 256 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 256, wan.gw, direction="down")
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)


class Netperf_DownTCP512(rootfs_boot.RootFSBootTest):
    """Netperf download throughput (TCP, packets size 512 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 512, wan.gw, direction="down")
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)


class Netperf_DownTCP1024(rootfs_boot.RootFSBootTest):
    """Netperf download throughput (TCP, packets size 1024 Bytes)."""

    def runTest(self):
        wan = self.dev.wan
        lan = self.dev.lan

        lib.common.test_msg("Starting netserver on wan...")
        wan.sendline("/usr/bin/netserver")
        wan.expect("Starting netserver with host")
        run_netperf_tcp(lan, 15, 1024, wan.gw, direction="down")
        wan.sendline("kill -9 `pidof netserver`")
        wan.expect(prompt)
