# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from cdrouter import CDRouter
from cdrouter.configs import Config
from cdrouter.cdrouter import CDRouterError
from cdrouter.jobs import Job
from cdrouter.packages import Package

import time
import rootfs_boot
from devices import board, wan, lan, wlan, prompt
import os

class CDrouterStub(rootfs_boot.RootFSBootTest):
    '''First attempt at test that runs a CDrouter job, waits for completion,
       and grabs results'''

    # To be overriden by children class
    tests = None
    extra_config = False

    def runTest(self):
        if self.tests is None:
            self.skipTest("No tests defined!")

        if self.config.cdrouter_server is None:
            self.skipTest("No cdrouter server specified")

        for d in [wan, lan]:
            d.sendline('ifconfig eth1 down')
            d.expect(prompt)

        board.sendcontrol('c')
        board.expect(prompt)
        try:
            board.sendline('reboot')
            board.wait_for_linux()
        except:
            board.reset()
            board.wait_for_linux()

        # TODO: make host configurable in bft config?
        c = CDRouter(self.config.cdrouter_server)

        # TODO: more clean edit of a config, and use a special name per config?
        try:
            c.configs.delete(c.configs.get_by_name("bft-automated-job").id)
        except CDRouterError as e:
            if e == "no such config":
                pass

        board.sendline('ifconfig %s' % board.wan_iface)
        board.expect('([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})')
        wandutmac = board.match.group()
        board.expect(prompt)

        print ("Using %s for WAN mac address" % wandutmac)

        lan.vlan = wan.vlan = 0
        for device in self.config.board['devices']:
            d = None
            if device['name'] == 'wan':
                d = wan
            elif device['name'] == 'lan':
                d = lan

            if d is not None:
                d.vlan = getattr(device, 'vlan', 0)
            if d.vlan == 0:
                d.sendline('cat /proc/net/vlan/config')
                d.expect('eth1.*\|\s([0-9]+).*\|')
                d.vlan = d.match.group(1)
                d.expect(prompt)

        print ("Using %s for WAN vlan" % wan.vlan)
        print ("Using %s for LAN vlan" % lan.vlan)

        # TODO: move wan and lan interface to bft config?
        contents="""
testvar wanInterface """ + self.config.cdrouter_wan_iface
        contents=contents +"""
testvar wanDutMac """ + wandutmac

        if wan.vlan != 0:
            contents=contents + """
testvar wanVlanId """ + wan.vlan

        contents=contents + """
testvar lanInterface """ + self.config.cdrouter_lan_iface

        if lan.vlan != 0:
            contents=contents + """
testvar lanVlanId """ + lan.vlan

        if self.extra_config:
            contents=contents + "\n" + self.extra_config.replace(',', '\n')

        print("Using below for config:")
        print(contents)
        print("#######################")

        cfg = c.configs.create(Config(name='bft-automated-job', contents=contents))

        # TODO: more clean edit of a config, and use a special name per config?
        try:
            c.packages.delete(c.packages.get_by_name("bft-automated-job").id)
        except CDRouterError as e:
            if e == "no such package":
                pass

        p = c.packages.create(Package(name="bft-automated-job",
                                      testlist=self.tests,
                                      config_id=cfg.id))
        j = c.jobs.launch(Job(package_id=p.id))

        while j.result_id is None:
            time.sleep(1)
            j = c.jobs.get(j.id)

        print('Job Result-ID: {0}'.format(j.result_id))

        while True:
            r = c.results.get(j.result_id)
            print(r.status)

            # we are ready to go from boardfarm reset above
            if r.status == "paused":
                c.results.unpause(j.result_id)
                time.sleep(5)
                continue

            if r.status != "running":
                break

            time.sleep(5)

        print(r.result)
        self.result_message = r.result.encode('ascii','ignore')
        # TODO: results URL?

        summary = c.results.summary_stats(j.result_id)

        self.result_message += " (Failed= %s, Passed = %s, Skipped = %s)" \
                % (summary.result_breakdown.failed, \
                   summary.result_breakdown.passed, \
                   summary.result_breakdown.skipped)

        for test in summary.test_summaries:
            self.logged[test.name] = vars(test)

            if str(test.name) not in ["start", "final"]:
                from lib.common import TestResult
                grade_map = {"pass": "OK", "fail": "FAIL", "skip": "SKIP"}[test.result]
                tr = TestResult(test.name, grade_map, test.description)
                self.subtests.append(tr)

            # TODO: handle skipped tests

            try:
                metric = c.results.get(result_id, test.name, "bandwidth")
                print vars(metric)
                # TODO: decide how to export data to kibana
            except:
                # Not all tests have this metric, no other way?
                pass


        assert (r.result == "The package completed successfully")

        self.recover()

    def recover(self):
        # TODO: full recovery...
        for d in [wan,lan]:
            d.sendline('ifconfig eth1 up')
            d.expect(prompt)

cdrouter_test_matrix = {
        "Basic": { "tests": [ "cdrouter_basic_{0}".format(i) for i in [1, 2, 10, 20] ] },
        "DHCP": { "tests": [ "cdrouter_dhcp_{0}".format(i) for i in [1, 2, 3, 4, 5, 10, 11, 20 ] ] },
        "DHCPServer": { "tests": [ "cdrouter_dhcp_server_{0}".format(i) for i in [1, 2] \
                                    + range(4, 11) \
                                    + [30, 31, 100, 200, 300, 301, 401, 501, 520, 540, 600, 610, 620, 630, 700, 710, 720, 800, 801] ],
                        "extra_config": "testvar dhcpClientStart 10.0.0.2,testvar dhcpClientEnd 10.0.0.253,testvar lanIp 10.0.0.1",
                        },
        "NAT": { "tests": [ "cdrouter_nat_{0}".format(i) for i in [1, 2, 100, 101, 120, 130, 150, 200, 201, 300, 320, 330, 340, 350, 360, 361, 400, 401, 410, 500, 501, 510, 511, 520, 530, 600, 610] ] },
        "NATTimeout": { "tests": [ "cdrouter_nat_timeout_{0}".format(i) for i in [1, 2, 10, 11, 20, 25, 30, 40] ] },
}

for k, v in cdrouter_test_matrix.iteritems():
    name = "CDrouter" + k

    globals()[name] = type(name, (CDrouterStub, ),
                            {
                                'tests': v['tests'],
                                'extra_config': v.get('extra_config', False),
                            })

class CDrouterCustom(CDrouterStub):
    tests = os.environ.get("BFT_CDROUTER_CUSTOM", "").split(" ")
