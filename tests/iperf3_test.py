# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re
import rootfs_boot
from lib import installers
from devices import board, wan, lan, wlan, prompt

try:
    from devices import winwsl
except:
    winwsl = None

class iPerf3Test(rootfs_boot.RootFSBootTest):
    '''iPerf3 generic performance tests'''

    opts= ""
    time = 60
    server_port = "5201"
    client = lan
    target_ip = None

    def runTest(self):
        installers.install_iperf3(wan)
        installers.install_iperf3(self.client)

        wan.sendline('iperf3 -s -p %s' % self.server_port)
        wan.expect('-----------------------------------------------------------')
        wan.expect('-----------------------------------------------------------')

        if self.target_ip == None:
            self.target_ip = wan.gw

        board.collect_stats(stats=['mpstat'])

        self.client.sendline('iperf3 %s -c %s -P5 -t %s -i 0 -p %s' % (self.opts, self.target_ip, self.time, self.server_port))
        self.client.expect(prompt, timeout=self.time+10)

        sender = re.findall('SUM.*Bytes\s*(.*/sec).*sender', self.client.before)[-1]
        if 'Mbits' in sender:
            s_rate = float(sender.split()[0])
        elif 'Kbits' in sender:
            s_rate = float(sender.split()[0])/1024
        elif 'Gbits' in sender:
            s_rate = float(sender.split()[0])*1024
        else:
            raise Exception("Unknown rate in sender results")

        recv = re.findall('SUM.*Bytes\s*(.*/sec).*receiver', self.client.before)[-1]
        if 'Mbits' in recv:
            r_rate = float(recv.split()[0])
        elif 'Kbits' in recv:
            r_rate = float(recv.split()[0])/1024
        elif 'Gbits' in recv:
            r_rate = float(recv.split()[0])*1024
        else:
            raise Exception("Unknown rate in recv results")

        self.logged['s_rate'] = s_rate
        self.logged['r_rate'] = r_rate

        self.recovery()

    def recovery(self):
        for d in [wan, self.client]:
            d.sendcontrol('c')
            d.sendcontrol('c')
            d.expect(prompt)

        board.parse_stats(dict_to_log=self.logged)

        args = (self.logged['s_rate'], self.logged['r_rate'], self.logged['mpstat'])
        self.result_message = "Sender rate = %s MBits/sec, Receiver rate = %s Mbits/sec, cpu = %.2f\n" % args

class iPerf3RTest(iPerf3Test):
    '''iPerf3 reverse generic performance tests'''

    opts = "-R"

class iPerf3_v6Test(iPerf3Test):
    '''iPerf3 ipv6 generic performance tests'''

    opts = "-6"

    def runTest(self):
        self.target_ip = wan.gwv6
        super(iPerf3_v6Test, self).runTest()

class iPerf3R_v6Test(iPerf3Test):
    '''iPerf3 ipv6 reverse generic performance tests'''

    opts = "-6 -R"

    def runTest(self):
        self.target_ip = wan.gwv6
        super(iPerf3R_v6Test, self).runTest()

class iPerf3Test2nd(iPerf3Test):
    '''iPerf3 on second server port'''
    server_port = "5202"

class iPerf3TestWSL(iPerf3Test):
    '''iPerf3 with windows WSL client'''

    client = winwsl
