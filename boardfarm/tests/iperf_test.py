# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm import lib
from boardfarm.devices import prompt
from boardfarm.lib import installers
from boardfarm.tests import ipv6_setup, rootfs_boot

# change this if you want to one time tweak iperf opts
time = 60
conns = 5
opts = "-t %s -P %s" % (time, conns)
#opts="-t %s -P %s -N -m -M 100" % (time, conns)


class iPerfTest(rootfs_boot.RootFSBootTest):
    '''iPerf from LAN to WAN'''
    @lib.common.run_once
    def wan_setup(self):
        wan = self.dev.wan

        installers.install_iperf(wan)

    @lib.common.run_once
    def lan_setup(self):
        lan = self.dev.lan

        installers.install_iperf(lan)

    @lib.common.run_once
    def wlan_setup(self):
        wlan = self.dev.wlan

        installers.install_iperf(wlan)

    def run_iperf_server(self, srv, opts=None):
        if opts is None:
            opts = self.server_opts_forward()

        self.kill_iperf(srv)
        srv.sendline('iperf -s %s > /dev/null &' % opts)
        srv.expect(prompt)

    def run_iperf(self, client, target=None, opts=""):
        if target is None:
            target = self.forward_ip()

        client.sendline('iperf %s -c %s %s | grep -v SUM' %
                        (self.client_opts(), target, opts))
        client.expect('Client connecting to')

    def parse_iperf(self, client, connections=conns, t=time):
        rate = 0.0
        for i in range(0, connections):
            m = client.expect(['Bytes([^M]*)Mbits', 'Bytes([^K]*)Kbits'],
                              timeout=t + 30)
            if m == 0:
                rate += float(client.match.group(1))
            elif m == 1:
                rate += float(client.match.group(1)) / 1000
            else:
                lib.common.test_msg("Unknown units for iPerf results!\n")
                assert False

        client.expect(prompt)
        return rate

    def kill_iperf(self, client):
        client.sendline("killall -9 iperf")
        client.expect(prompt)

    def server_opts_forward(self):
        return ""

    def server_opts_reverse(self, node):
        board = self.dev.board

        try:
            lan_priv_ip = node.get_interface_ipaddr(node.iface_dut)
        except:
            lan_priv_ip = node.get_interface_ipaddr("wlan0")
        board.uci_forward_traffic_redirect("tcp", "5001", lan_priv_ip)
        self.rip = board.get_interface_ipaddr(board.wan_iface)
        return ""

    def client_opts(self):
        return ""

    def forward_ip(self):
        return "192.168.0.1"

    def reverse_ip(self):
        return self.rip

    def mpstat_ok(self):
        board = self.dev.board

        board.sendline('mpstat -V')
        if board.expect(['sysstat version', 'BusyBox', 'not found'],
                        timeout=5) == 0:
            mpstat_present = True
        else:
            mpstat_present = False
        board.expect(prompt)

        return mpstat_present

    def runTest(self, client, server):
        board = self.dev.board

        mpstat_present = self.mpstat_ok()

        # this is running an arbitrary time, we will ctrl-c and get results
        self.run_iperf_server(server, opts=self.server_opts_forward())
        if mpstat_present:
            board.sendline('mpstat -P ALL 10000 1')
            board.expect('Linux')
        self.run_iperf(client, opts=opts)
        rate = self.parse_iperf(client)

        if mpstat_present:
            board.sendcontrol('c')
            board.expect(
                r'Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){10}\r\n')
            idle_cpu = float(board.match.group(1))
            avg_cpu = 100 - float(idle_cpu)
            self.logged['avg_cpu'] = float(avg_cpu)
        else:
            avg_cpu = "N/A"

        self.kill_iperf(server)
        msg = '%s (%s Mbps, CPU=%s)' % (self.__doc__, rate, avg_cpu)
        lib.common.test_msg("\n%s" % msg)

        self.logged['rate'] = float(rate)
        self.result_message = msg

    def recover(self, client, server):
        board = self.dev.board

        board.sendcontrol('c')
        board.sendcontrol('c')
        client.sendcontrol('c')
        client.sendcontrol('c')
        client.expect(prompt)
        self.kill_iperf(server)


class iPerfTestWLAN(iPerfTest):
    '''iPerf from LAN to WAN over Wifi'''
    def runTest(self):
        wlan = self.dev.wlan

        if not wlan:
            self.skipTest("skipping test no wlan")
        wlan.sendline('iwconfig')
        wlan.expect(prompt)
        super(iPerfTestWLAN, self).runTest(client=self.dev.wlan,
                                           server=self.dev.wan)


class iPerfTestIPV6(ipv6_setup.Set_IPv6_Addresses, iPerfTest):
    '''iPerf IPV6 from LAN to WAN'''
    def forward_ip(self):
        return "5aaa::6"

    def server_opts_forward(self):
        return "-V -B %s" % self.forward_ip()

    def client_opts(self):
        return "-V"

    def runTest(self):
        ipv6_setup.Set_IPv6_Addresses.runTest(self)
        iPerfTest.runTest(self)


class iPerfNonRoutedTest(iPerfTest):
    '''iPerf from LAN to Router'''
    def forward_ip(self):
        board = self.dev.board

        return board.get_interface_ipaddr(board.lan_iface)

    def runTest(self):
        super(iPerfNonRoutedTest, self).runTest(client=self.dev.lan,
                                                server=self.dev.board)

    def recover(self):
        super(iPerfNonRoutedTest, self).recover(client=self.dev.lan,
                                                server=self.dev.board)


class iPerfReverseTest(iPerfTest):
    '''iPerf from WAN to LAN'''
    def runTest(self, client, server):
        board = self.dev.board

        mpstat_present = self.mpstat_ok()

        # this is running an arbitrary time, we will ctrl-c and get results
        self.run_iperf_server(server,
                              opts=self.server_opts_reverse(node=server))
        if mpstat_present:
            board.sendline('mpstat -P ALL 10000 1')
            board.expect('Linux')
        self.run_iperf(client, opts=opts, target=self.reverse_ip())
        rate = self.parse_iperf(client)
        if mpstat_present:
            board.sendcontrol('c')
            board.expect(
                r'Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){10}\r\n')
            idle_cpu = float(board.match.group(1))
            avg_cpu = 100 - float(idle_cpu)
            self.logged['avg_cpu'] = float(avg_cpu)
        else:
            avg_cpu = "N/A"

        self.kill_iperf(server)
        msg = 'iPerf from WAN to LAN (%s Mbps, CPU=%s)' % (rate, avg_cpu)
        lib.common.test_msg("\n%s" % msg)

        self.logged['rate'] = float(rate)
        self.result_message = msg

    def recover(self, client, server):
        board = self.dev.board

        board.sendcontrol('c')
        board.sendcontrol('c')
        client.sendcontrol('c')
        client.sendcontrol('c')
        client.expect(prompt)
        self.kill_iperf(server)


class iPerfReverseTestWLAN(iPerfReverseTest):
    '''iPerf from WAN to LAN over Wifi'''
    def runTest(self):
        wlan = self.dev.wlan

        if not wlan:
            self.skipTest("skipping test no wlan")
        wlan.sendline('iwconfig')
        wlan.expect(prompt)
        super(iPerfReverseTestWLAN, self).runTest(client=self.dev.wan,
                                                  server=self.dev.wlan)

    def recover(self):
        super(iPerfReverseTestWLAN, self).recover(client=self.dev.wan,
                                                  server=self.dev.wlan)


class iPerfReverseTestIPV6(ipv6_setup.Set_IPv6_Addresses, iPerfReverseTest):
    '''iPerf IPV6 from WAN to LAN'''
    def reverse_ip(self):
        return "4aaa::6"

    def server_opts_reverse(self, node):
        board = self.dev.board

        board.uci_forward_traffic_rule("tcp", "5001", "4aaa::6")
        return "-V -B %s" % self.reverse_ip()

    def client_opts(self):
        return "-V"

    def runTest(self):
        ipv6_setup.Set_IPv6_Addresses.runTest(self)
        iPerfReverseTest.runTest(self)


class iPerfBiDirTest(iPerfTest):
    '''iPerf from LAN to/from WAN'''
    def runTest(self, node1, node2, firewall=True):
        board = self.dev.board

        mpstat_present = self.mpstat_ok()

        if firewall:
            self.run_iperf_server(node1, opts=self.server_opts_reverse(node1))
        else:
            self.run_iperf_server(node1, opts=self.server_opts_forward())
        self.run_iperf_server(node2, opts=self.server_opts_forward())
        board.sendline('cat /proc/net/nf_conntrack | wc -l')
        board.expect(prompt)
        # this is running an arbitrary time, we will ctrl-c and get results
        if mpstat_present:
            board.sendline('mpstat -P ALL 10000 1')
            board.expect('Linux')
        self.run_iperf(node2, opts=opts, target=self.reverse_ip())
        self.run_iperf(node1, opts=opts)
        rate = 0.0
        rate += float(self.parse_iperf(node1))
        rate += float(self.parse_iperf(node2))
        if mpstat_present:
            board.sendcontrol('c')
            board.expect(
                r'Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){10}\r\n')
            idle_cpu = float(board.match.group(1))
            avg_cpu = 100 - float(idle_cpu)
            self.logged['avg_cpu'] = float(avg_cpu)
        else:
            avg_cpu = "N/A"

        self.kill_iperf(node1)
        self.kill_iperf(node2)
        msg = 'iPerf bidir  WAN to LAN (%s Mbps, CPU=%s)' % (rate, avg_cpu)
        lib.common.test_msg("\n%s" % msg)

        self.logged['rate'] = float(rate)
        self.result_message = msg

    def recover(self, node1, node2):
        board = self.dev.board

        lib.common.test_msg("sending board ctrl-c")
        board.sendcontrol('c')
        board.sendcontrol('c')
        board.expect(prompt)
        lib.common.test_msg("sending node1 ctrl-c")
        node1.sendcontrol('c')
        node1.sendcontrol('c')
        node1.expect(prompt)
        lib.common.test_msg("sending node2ctrl-c")
        node2.sendcontrol('c')
        node2.sendcontrol('c')
        node2.expect(prompt)
        lib.common.test_msg("killing iperf on node1")
        self.kill_iperf(node1)
        lib.common.test_msg("killing iperf on node2")
        self.kill_iperf(node2)

        board.sendline('cat /proc/net/nf_conntrack | wc -l')
        board.expect(prompt)
        try:
            board.sendline('cat /proc/devices | grep sfe')
            board.expect('cat /proc/devices | grep sfe')
            board.expect('([0-9]+) sfe_ipv4')
            char_dev = board.match.group(1).strip()
            board.expect(prompt)
            board.sendline('mknod /dev/sfe c %s 0' % char_dev)
            board.expect(prompt)
            board.sendline('cat /dev/sfe')
            board.expect(prompt)
        except:
            pass
        board.sendline('ifconfig; route')
        board.expect_exact('ifconfig; route')
        board.expect(prompt)
        node1.sendline('ifconfig; route')
        node1.expect_exact('ifconfig; route')
        node1.expect(prompt)
        node2.sendline('ifconfig; route')
        node2.expect_exact('ifconfig; route')
        node2.expect(prompt)


class iPerfBiDirTestWLAN(iPerfBiDirTest):
    '''iPerf from WAN to LAN over Wifi'''
    def runTest(self):
        wlan = self.dev.wlan

        if not wlan:
            self.skipTest("skipping test no wlan")
        wlan.sendline('iwconfig')
        wlan.expect(prompt)
        super(iPerfBiDirTestWLAN, self).runTest(node1=self.dev.wlan,
                                                node2=self.dev.wan)

    def recover(self):
        super(iPerfBiDirTestWLAN, self).recover(node1=self.dev.wlan,
                                                node2=self.dev.wan)


class iPerfBiDirTestLANtoWLAN(iPerfBiDirTest):
    '''iPerf from WAN to LAN over Wifi'''
    def forward_ip(self):
        return self.fip

    def reverse_ip(self):
        return self.rip

    def runTest(self):
        wlan = self.dev.wlan
        lan = self.dev.lan

        if not wlan:
            self.skipTest("skipping test no wlan")

        self.fip = lan.get_interface_ipaddr(lan.iface_dut)
        self.rip = wlan.get_interface_ipaddr("wlan0")

        wlan.sendline('iwconfig')
        wlan.expect(prompt)
        super(iPerfBiDirTestLANtoWLAN, self).runTest(node1=self.dev.wlan,
                                                     node2=self.dev.lan,
                                                     firewall=False)

    def recover(self):
        super(iPerfBiDirTestWLAN, self).recover(node1=self.dev.wlan,
                                                node2=self.dev.lan)


class iPerfBiDirTestIPV6(ipv6_setup.Set_IPv6_Addresses, iPerfBiDirTest):
    '''iPerf IPV6 from LAN to/from WAN'''
    def reverse_ip(self):
        return "4aaa::6"

    def forward_ip(self):
        return "5aaa::6"

    def server_opts_forward(self):
        return "-V -B %s" % self.forward_ip()

    def server_opts_reverse(self, node):
        board = self.dev.board

        board.uci_forward_traffic_rule("tcp", "5001", "4aaa::6")
        return "-V -B %s" % self.reverse_ip()

    def client_opts(self):
        return "-V"

    def runTest(self):
        ipv6_setup.Set_IPv6_Addresses.runTest(self)
        iPerfBiDirTest.runTest(self)

    def recover(self):
        iPerfBiDirTest.recover(self)
