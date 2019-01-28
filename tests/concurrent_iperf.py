import rootfs_boot
import pexpect

from common import print_bold
from datetime import datetime

from devices import board, prompt, wan, lan

class ConcurrentIperf(rootfs_boot.RootFSBootTest):
    '''Determine's max number of iperf connections'''
    def runTest(self):
        wan_ip = wan.get_interface_ipaddr(wan.iface_dut)
        wan.sendline('iperf -s -l 1M -w 1M')
        wan.expect('Server listening on ')

        board.collect_stats(stats=['mpstat'])

        time = 10
        cmd = "iperf -R -c %s -P %s -t 10 -N -w 1M -l 1M | grep SUM"
        # prime the pipes...
        lan.sendline(cmd % (wan_ip, 4))
        lan.expect(prompt)

        for con_conn in range(32, 513, 16):
            try:
                tstart = datetime.now()
                lan.sendline(cmd % (wan_ip, con_conn))
                failed_cons = 0
                while (datetime.now() - tstart).seconds < (time * 2):
                    board.get_nf_conntrack_conn_count()
                    timeout=(time*2)-(datetime.now() - tstart).seconds
                    if 0 == lan.expect(['write failed: Connection reset by peer'] + prompt, timeout=timeout):
                        failed_cons += 1
                    else:
                        break
                print_bold("For iperf with %s connections, %s failed...." % (con_conn, failed_cons))
                lan.expect('.*')
                wan.expect('.*')

                board.touch()
            except:
                self.result_message = "iPerf Concurrent Connections failed entirely at %s" % con_conn
                break

        print self.result_message

        self.recover()

    def recover(self):
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

        board.parse_stats(stats=['mpstat'], dict_to_log=self.logged)

        self.result_message += ", cpu usage = %.2f" % self.logged['mpstat']
