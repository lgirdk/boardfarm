# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from cdrouter import CDRouter
from cdrouter.configs import Config
from cdrouter.jobs import Job
from cdrouter.packages import Package

import time
from boardfarm.tests import rootfs_boot
from boardfarm.devices import board, lan, wan
from boardfarm.devices import prompt
from boardfarm.orchestration import TestResult
from boardfarm import lib
import os
import pexpect
import ipaddress
import six


class CDrouterStub(rootfs_boot.RootFSBootTest):
    '''First attempt at test that runs a CDrouter job, waits for completion,
       and grabs results'''

    # To be overriden by children class
    tests = None
    extra_config = False
    cdrouter_server = None

    def runTest(self):
        from boardfarm.devices import cdrouter
        self.cdrouter_server = "http://" + cdrouter.ipaddr
        self.cdrouter_wan_iface = cdrouter.wan_iface
        self.cdrouter_lan_iface = cdrouter.lan_iface

        if self.tests is None:
            self.skipTest("No tests defined!")

        if self.cdrouter_server is None:
            self.skipTest("No cdrouter server specified")

        lan.sendline('ifconfig %s down' % lan.iface_dut)
        lan.expect(prompt)

        if not board.has_cmts:
            wan.sendline('ifconfig %s down' % wan.iface_dut)
            wan.expect(prompt)

        c = CDRouter(self.cdrouter_server)

        #try:
        #    board.sendcontrol('c')
        #    board.expect(prompt)
        #    board.sendline('reboot')
        #    board.expect('reboot: Restarting system')
        #except:
        #    board.reset()
        #board.wait_for_linux()
        #board.wait_for_network()

        ## Add extra board specific delay
        #board.expect(pexpect.TIMEOUT, timeout=getattr(board, 'cdrouter_bootdelay', 0))

        # If alt mac addr is specified in config, use that..
        # CMTS = we route so no wan mac is used
        # if we route, we need to add routes
        wandutmac = None
        if board.has_cmts:
            from boardfarm.devices import provisioner
            # TODO: there are more missing ones CDrouter expects
            provisioner.sendline('ip route add 200.0.0.0/8 via 192.168.3.2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route add 3.3.3.3 via 192.168.3.2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route add 3001:cafe:1::/64 via 2001:dead:beef:1::2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route add 3001:51a:cafe::1 via 2001:dead:beef:1::2')
            provisioner.expect(prompt)
        elif not wan.static_ip:
            for device in self.config.board['devices']:
                if device['name'] == 'wan':
                    if 'alt_macaddr' in device:
                        wandutmac = device['alt_macaddr']
                    break

            # Otherwise grab this from the device interface
            if wandutmac is None:
                board.sendline('ifconfig %s' % board.wan_iface)
                board.expect('([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})')
                wandutmac = board.match.group()
                board.expect(prompt)

            print("Using %s for WAN mac address" % wandutmac)

        lan.vlan = wan.vlan = 0
        for device in self.config.board['devices']:
            d = None
            if device['name'] == 'wan':
                d = wan
            elif device['name'] == 'lan':
                d = lan
            else:
                continue

            if d is not None:
                d.vlan = getattr(device, 'vlan', 0)
            if d.vlan == 0:
                d.sendline('cat /proc/net/vlan/config')
                d.expect_exact('cat /proc/net/vlan/config')
                if 0 == d.expect([pexpect.TIMEOUT, '%s.*\|\s([0-9]+).*\|' % d.iface_dut], timeout=5):
                    d.vlan = 0
                else:
                    d.vlan = d.match.group(1)
                d.expect(prompt)

        # TODO: WIP
        wan.vlan = "136"
        print("Using %s for WAN vlan" % wan.vlan)
        print("Using %s for LAN vlan" % lan.vlan)

        # TODO: move wan and lan interface to bft config?
        contents="""
testvar wanInterface """ + self.cdrouter_wan_iface
        if wandutmac is not None:
            contents=contents +"""
testvar wanDutMac """ + wandutmac

        if wan.vlan != 0:
            contents=contents + """
testvar wanVlanId """ + wan.vlan

        contents=contents + """
testvar lanInterface """ + self.cdrouter_lan_iface

        if lan.vlan != 0:
            contents=contents + """
testvar lanVlanId """ + lan.vlan

        if self.extra_config:
            contents=contents + "\n" + self.extra_config.replace(',', '\n')

        def add_cdrouter_config(config):
            p = os.path.realpath(config)
            cdr_conf = open(os.path.join(p, config), 'r').readlines()

            return "\n" + "".join(cdr_conf)

        if board.cdrouter_config is not None:
            contents = contents + add_cdrouter_config(board.cdrouter_config)

        if board.has_cmts:
            for i in range(5):
                exp = None
                try:
                    wan_ip = board.get_interface_ipaddr(board.erouter_iface)
                    # TODO: this breaks ipv6 only
                    wan_ip6 = board.get_interface_ip6addr(board.erouter_iface)

                    lan.start_lan_client()
                    lan_ip6 = lan.get_interface_ip6addr(lan.iface_dut)
                    ip6 = ipaddress.IPv6Network(six.text_type(lan_ip6))
                    fixed_prefix6 = str(ip6.supernet(new_prefix=64).network_address)
                    break
                except Exception as e:
                    exp = e
                    board.expect(pexpect.TIMEOUT, timeout=15)
                    continue
            else:
                if i == 4:
                    raise exp

            # TODO: mask from config? wanNatIp vs. wanIspAssignGateway?
            contents=contents + """
testvar ipv6LanIp %s%%eui64%%
testvar ipv6LanPrefixLen 64
testvar healthCheckEnable yes
testvar supportsIPv6 yes
testvar ipv6WanMode static
testvar ipv6WanIspIp %s
testvar ipv6WanIspGateway %s
testvar ipv6WanIspAssignIp %s
testvar ipv6WanIspPrefixLen 64
testvar ipv6LanMode autoconf
testvar ipv6RemoteHost            3001:51a:cafe::1
testvar ipv6FreeNetworkStart      3001:cafe:1::
testvar ipv6FreeNetworkEnd        3001:cafe:ffff::
testvar ipv6FreeNetworkPrefixLen  64
testvar wanMode static
testvar wanIspIp %s
testvar wanIspGateway %s
testvar wanIspMask 255.255.255.128
testvar wanIspAssignIp %s
testvar wanNatIp %s
testvar remoteHostIp 3.3.3.3
testvar FreeNetworkStart 200.0.0.0
testvar FreeNetworkMask  255.255.255.0
testvar FreeNetworkStop  201.0.0.0
testvar IPv4HopCount %s
testvar lanDnsServer %s
testvar wanDnsServer %s
""" % (fixed_prefix6,
       cdrouter.wanispip_v6, \
       cdrouter.wanispgateway_v6, \
       wan_ip6, \
       cdrouter.wanispip, \
       cdrouter.wanispgateway, \
       wan_ip, wan_ip, \
       cdrouter.ipv4hopcount, \
       board.get_dns_server(), \
       board.get_dns_server_upstream())

        print("Using below for config:")
        print(contents)
        print("#######################")

        config_name="bft-automated-job-%s" % str(time.time()).replace('.', '')
        cfg = c.configs.create(Config(name=config_name, contents=contents))

        p = c.packages.create(Package(name=config_name,
                                      testlist=self.tests,
                                      config_id=cfg.id))

        self.start_time = time.time()
        j = c.jobs.launch(Job(package_id=p.id))

        while j.result_id is None:
            if (time.time() - self.start_time) > 300:
                # delete job if it fails to start
                c.jobs.delete(j.id)
                raise Exception("Failed to start CDrouter job")

            board.expect(pexpect.TIMEOUT, timeout=1)
            j = c.jobs.get(j.id)

        print('Job Result-ID: {0}'.format(j.result_id))

        self.job_id = j.result_id
        self.results = c.results
        unpaused = False
        end_of_start = False
        no_more_pausing = False
        while True:
            r = c.results.get(j.result_id)
            print(r.status)

            # we are ready to go from boardfarm reset above
            if r.status == "paused" and unpaused == False:
                c.results.unpause(j.result_id)
                unpaused = True
                board.expect(pexpect.TIMEOUT, timeout=1)
                c.results.pause(j.result_id, when="end-of-test")
                end_of_start = True
                continue


            if r.status == "paused" and end_of_start == True:
                end_of_start = False
                # TODO: do we need this anymore? we have board specific cdrouter_bootdelay
                board.expect(pexpect.TIMEOUT, timeout=60)
                c.results.unpause(j.result_id)
                board.expect(pexpect.TIMEOUT, timeout=1)
                no_more_pausing = True
                continue

            if no_more_pausing and r.status == "paused":
                print("Error: test is still paused")
                c.results.stop(j.result_id)
                break

            if r.status != "running" and r.status != "paused":
                break

            board.expect(pexpect.TIMEOUT, timeout=5)

        print(r.result)
        self.result_message = r.result.encode('ascii','ignore')
        # TODO: results URL?
        elapsed_time = time.time() - self.start_time
        print("Test took %s" % time.strftime("%H:%M:%S", time.gmtime(elapsed_time)))

        summary = c.results.summary_stats(j.result_id)

        self.result_message = six.text_type(self.result_message) + \
                " (Failed= %s, Passed = %s, Skipped = %s)" \
                % (summary.result_breakdown.failed, \
                   summary.result_breakdown.passed, \
                   summary.result_breakdown.skipped)

        for test in summary.test_summaries:
            self.logged[test.name] = vars(test)

            if str(test.name) not in ["start", "final"]:
                try:
                    grade_map = {"pass": "OK", "fail": "FAIL", "skip": "SKIP"}[test.result]
                    tr = TestResult(test.name, grade_map, test.description)
                    if test.started is not None:
                        tr.start_time = test.started
                        tr.stop_time = test.started + test.duration
                    else:
                        tr.elapsed_time = test.duration
                    self.subtests.append(tr)
                except:
                    continue

            # TODO: handle skipped tests

            try:
                metric = c.results.get(j.result_id, test.name, "bandwidth")
                print(vars(metric))
                # TODO: decide how to export data to kibana
            except:
                # Not all tests have this metric, no other way?
                pass


        assert (r.result == "The package completed successfully")

        self.recover()

    def recover(self):
        if board.has_cmts:
            from boardfarm.devices import provisioner
            # TODO: there are more missing ones CDrouter expects
            provisioner.sendline('ip route del 200.0.0.0/8 via 192.168.3.2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route del 3.3.3.3 via 192.168.3.2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route del 3001:cafe:1::/64 via 2001:dead:beef:1::2')
            provisioner.expect(prompt)
            provisioner.sendline('ip route del 3001:51a:cafe::1 via 2001:dead:beef:1::2')
            provisioner.expect(prompt)

        if hasattr(self, 'results'):
            r = self.results.get(self.job_id)

            if r.status == "running":
                self.results.stop(self.job_id)
        # TODO: full recovery...
        for d in [wan,lan]:
            d.sendline('ifconfig %s up' % d.iface_dut)
            d.expect(prompt)

        # make sure board is back in a sane state
        board.sendcontrol('c')
        board.sendline()
        if 0 != board.expect([pexpect.TIMEOUT] + board.uprompt, timeout=5):
            board.reset()
            board.wait_for_linux()

    @staticmethod
    @lib.common.run_once
    def parse(config):
        try:
            from boardfarm.devices import cdrouter
            url = 'http://' + cdrouter.ipaddr
        except:
            return []

        c = CDRouter(url)
        new_tests = []
        for mod in c.testsuites.list_modules():
            name = "CDrouter" + mod.name.replace('.', '').replace('-','_')
            list_of_tests = [ six.text_type(x) for x in mod.tests ]
            new_tests.append(type(six.text_type(name) , (CDrouterStub, ),
                                    {
                                        'tests': list_of_tests
                                    }))

        return new_tests

class CDrouterCustom(CDrouterStub):
    tests = os.environ.get("BFT_CDROUTER_CUSTOM", "").split(" ")
    extra_config = os.environ.get("BFT_CDROUTER_CUSTOM_CONFIG", "")
