from datetime import datetime

import pexpect
from boardfarm.devices import prompt
from boardfarm.lib.common import print_bold
from boardfarm.tests import rootfs_boot


class ConcurrentIperf(rootfs_boot.RootFSBootTest):
    '''Determine's max number of iperf connections'''
    def runTest(self):
        board = self.dev.board
        wan = self.dev.wan
        lan = self.dev.lan

        wan_ip = wan.get_interface_ipaddr(wan.iface_dut)
        wan.sendline('iperf -s -l 1M -w 1M')
        wan.expect('Server listening on ')

        board.collect_stats(stats=['mpstat'])

        time = 10
        cmd = "iperf -R -c %s -P %s -t 10 -N -w 1M -l 1M | grep SUM"
        # prime the pipes...
        lan.sendline(cmd % (wan_ip, 4))
        lan.expect(prompt)

        prev_failed = 0
        for con_conn in range(32, 513, 16):
            try:
                tstart = datetime.now()
                lan.sendline(cmd % (wan_ip, con_conn))
                failed_cons = 0
                while (datetime.now() - tstart).seconds < (time * 2):
                    timeout = (time * 2) - (datetime.now() - tstart).seconds
                    if 0 == lan.expect(
                        ['write failed: Connection reset by peer'] + prompt,
                            timeout=timeout):
                        failed_cons += 1
                    else:
                        break
                print_bold("For iperf with %s connections, %s failed...." %
                           (con_conn, failed_cons))
                lan.expect('.*')
                wan.expect('.*')

                board.touch()
                prev_conn = con_conn
                prev_failed = failed_cons

                if con_conn == 512:
                    self.result_message = "iPerf Concurrent passed 512 connections (failed conns = %s)" % failed_cons
            except:
                self.result_message = "iPerf Concurrent Connections failed entirely at %s (failed conns = %s)" % (
                    prev_conn, prev_failed)
                break

        print(self.result_message)

        self.recover()

    def recover(self):
        board = self.dev.board
        wan = self.dev.wan
        lan = self.dev.lan

        for d in [wan, lan]:
            d.sendcontrol('z')
            if 0 == d.expect([pexpect.TIMEOUT] + prompt):
                d.sendcontrol('c')
                d.sendcontrol('c')
                d.sendcontrol('c')
                d.sendcontrol('c')
                d.sendcontrol('c')
                d.sendline('')
                d.sendline('echo FOOBAR')
                d.expect_exact('echo FOOBAR')
                d.expect_exact('FOOBAR')
                d.expect(prompt)
            else:
                d.sendline("kill %1")
                d.expect(prompt)

            d.sendline('pkill -9 -f iperf')
            d.expect_exact('pkill -9 -f iperf')
            d.expect(prompt)

        board.parse_stats(dict_to_log=self.logged)

        self.result_message += ", cpu usage = %.2f" % self.logged['mpstat']
