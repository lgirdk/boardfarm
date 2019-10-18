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
from boardfarm.devices import board, wan, lan, wlan, prompt
import os
import pexpect

class CDrouterStub(rootfs_boot.RootFSBootTest):
    '''First attempt at test that runs a CDrouter job, waits for completion,
       and grabs results'''

    # To be overriden by children class
    tests = None
    extra_config = False
    cdrouter_server = None

    def runTest(self):
        if 'cdrouter_server' in self.config.board:
            self.cdrouter_server = self.config.board['cdrouter_server']
        elif self.config.cdrouter_server is not None:
            self.cdrouter_server = self.config.cdrouter_server

        if 'cdrouter_wan_iface' in self.config.board:
            self.cdrouter_wan_iface = self.config.board['cdrouter_wan_iface']
        else:
            self.cdrouter_wan_iface = self.config.cdrouter_wan_iface

        if 'cdrouter_lan_iface' in self.config.board:
            self.cdrouter_lan_iface = self.config.board['cdrouter_lan_iface']
        else:
            self.cdrouter_lan_iface = self.config.cdrouter_lan_iface

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

        try:
            board.sendcontrol('c')
            board.expect(prompt)
            board.sendline('reboot')
            board.expect('reboot: Restarting system')
        except:
            board.reset()
        board.wait_for_linux()
        board.wait_for_network()

        # Add extra board specific delay
        board.expect(pexpect.TIMEOUT, timeout=getattr(board, 'cdrouter_bootdelay', 0))

        # If alt mac addr is specified in config, use that..
        # CMTS = we route so no wan mac is used
        # if we route, we need to add routes
        wandutmac = None
        if board.has_cmts and wan.wan_cmts_provisioner:
            # TODO: there are more missing ones CDrouter expects
            wan.sendline('ip route add 200.0.0.0/8 via 192.168.3.2')
            wan.expect(prompt)
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

        def add_cdrouter_config(config):
            cdr_conf = None

            # TODO: make a generic helper to search path and overlays
            if os.path.isfile(config):
                cdr_conf = open(config, 'r').readlines()
            elif 'BFT_OVERLAY' in os.environ:
                for p in os.environ['BFT_OVERLAY'].split(' '):
                    p = os.path.realpath(p)
                    try:
                        cdr_conf = open(os.path.join(p, config), 'r').readlines()
                    except:
                        continue
                    else:
                        break

            return "\n" + "".join(cdr_conf)

        # Take config from overall config, but fallback to board config
        if self.config.cdrouter_config is not None:
            contents = contents + add_cdrouter_config(self.config.cdrouter_config)
        elif board.cdrouter_config is not None:
            contents = contents + add_cdrouter_config(board.cdrouter_config)

        if self.extra_config:
            contents=contents + "\n" + self.extra_config.replace(',', '\n')

        if board.has_cmts:
            for i in range(5):
                try:
                    wan_ip = board.get_interface_ipaddr(board.erouter_iface)
                except:
                    board.expect(pexpect.TIMEOUT, timeout=15)
                    continue
                else:
                    if i == 4:
                        raise Exception("Failed to get erouter ip address")
                    break

            # TODO: mask from config? wanNatIp vs. wanIspAssignGateway?
            contents=contents + """
testvar wanMode static
testvar wanIspIp %s
testvar wanIspGateway %s
testvar wanIspMask 255.255.255.0
testvar wanIspAssignIp %s
testvar wanNatIp %s
testvar IPv4HopCount %s
testvar lanDnsServer %s
testvar wanDnsServer %s""" % (self.config.board['cdrouter_wanispip'], \
                              self.config.board['cdrouter_wanispgateway'], \
                              wan_ip, wan_ip, \
                              self.config.board['cdrouter_ipv4hopcount'], \
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

        self.result_message += " (Failed= %s, Passed = %s, Skipped = %s)" \
                % (summary.result_breakdown.failed, \
                   summary.result_breakdown.passed, \
                   summary.result_breakdown.skipped)

        for test in summary.test_summaries:
            self.logged[test.name] = vars(test)

            if str(test.name) not in ["start", "final"]:
                from boardfarm.lib.common import TestResult
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
        if board.has_cmts and wan.wan_cmts_provisioner:
            # TODO: there are more missing ones (see above)
            wan.sendline('ip route del 200.0.0.0/8 via 192.168.3.2')
            wan.expect(prompt)

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

class CDrouterCustom(CDrouterStub):
    tests = os.environ.get("BFT_CDROUTER_CUSTOM", "").split(" ")
    extra_config = os.environ.get("BFT_CDROUTER_CUSTOM_CONFIG", "")
