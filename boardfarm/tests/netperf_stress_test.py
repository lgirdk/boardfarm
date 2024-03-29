# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time

from boardfarm import lib
from boardfarm.devices import prompt
from boardfarm.tests import netperf_test
from boardfarm.tests.netperf_test import install_netperf


class NetperfStressTest(netperf_test.NetperfTest):
    @lib.common.run_once
    def wan_setup(self):
        wan = self.dev.wan

        install_netperf(wan)

    @lib.common.run_once
    def lan_setup(self):
        lan = self.dev.lan

        install_netperf(lan)

    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan

        # Record number of bytes and packets sent through interfaces
        board.sendline("\nifconfig | grep 'encap\\|packets\\|bytes'")
        board.expect("br-lan")
        board.expect(prompt)

        # Start netperf tests
        num_conn = 200
        run_time = 30
        pkt_size = 256

        board.sendline(f"mpstat -P ALL {run_time} 1")
        print(f"\nStarting {num_conn} netperf tests in parallel.")
        opts = f"192.168.0.1 -c -C -l {run_time} -- -m {pkt_size} -M {pkt_size} -D"
        for _ in range(0, num_conn):
            self.run_netperf_cmd_nowait(lan, opts)
        # Let netperf tests run
        time.sleep(run_time * 1.5)

        board.expect("Average:\\s+all.*\\s+([0-9]+.[0-9]+)\r\n")
        idle_cpu = board.match.group(1)
        avg_cpu = 100 - float(idle_cpu)
        print(f"Average cpu usage was {avg_cpu}")

        # try to flush out backlog of buffer from above, we try b/c not all might start
        # correctly
        try:
            for _ in range(0, num_conn):
                lan.exepct("TEST")
        except:
            pass

        # add up as many netperf connections results that were established
        try:
            bandwidth = 0.0
            conns_parsed = 0
            for _ in range(0, num_conn):
                bandwidth += self.run_netperf_parse(lan, timeout=1) * run_time
                conns_parsed += 1
        except Exception as e:
            # print the exception for logging reasons
            print(e)

        # make sure at least one netperf was run
        assert conns_parsed > 0

        board.sendline("pgrep logger | wc -l")
        board.expect("([0-9]+)\r\n")
        n = board.match.group(1)

        print(f"Stopped with {conns_parsed} connections, {n} netperf's still running")
        print(f"Mbits passed was {bandwidth}")

        # Record number of bytes and packets sent through interfaces
        board.sendline(r"ifconfig | grep 'encap\|packets\|bytes'")
        board.expect("br-lan")
        board.expect(prompt)

        lan.sendline("killall netperf")
        lan.expect(prompt)
        lan.sendline("")
        lan.expect(prompt)
        lib.common.clear_buffer(lan)

        self.result_message = (
            "Ran %s/%s for %s seconds (Pkt Size = %s, Mbits = %s, CPU = %s)"
            % (conns_parsed, num_conn, run_time, pkt_size, bandwidth, avg_cpu)
        )
