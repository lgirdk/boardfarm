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

class iPerf3Test(rootfs_boot.RootFSBootTest):
    '''iPerf3 generic performance tests'''

    opts= ""
    time = 60

    def runTest(self):
        installers.install_iperf3(wan)
        installers.install_iperf3(lan)

        wan.sendline('iperf3 -s')
        wan.expect('-----------------------------------------------------------')
        wan.expect('-----------------------------------------------------------')


        lan.sendline('iperf3 %s -c %s -P5 -t %s -i 0' % (self.opts, wan.gw, self.time))
        lan.expect(prompt, timeout=self.time+5)

        sender = re.findall('SUM.*Bytes\s*(.*/sec).*sender', lan.before)[-1]
        if 'Mbits' in sender:
            s_rate = float(sender.split()[0])
        elif 'Kbits' in sender:
            s_rate = float(sender.split()[0])/1024
        elif 'Gbits' in sender:
            s_rate = float(sender.split()[0])*1024
        else:
            raise Exception("Unknown rate in sender results")

        recv = re.findall('SUM.*Bytes\s*(.*/sec).*receiver', lan.before)[-1]
        if 'Mbits' in recv:
            r_rate = float(recv.split()[0])
        elif 'Kbits' in recv:
            r_rate = float(recv.split()[0])/1024
        elif 'Gbits' in recv:
            r_rate = float(recv.split()[0])*1024
        else:
            raise Exception("Unknown rate in recv results")

        self.result_message = "Sender rate = %s MBits/sec, Receiver rate = %s Mbits/sec\n" % (s_rate, r_rate)
        self.logged['s_rate'] = s_rate
        self.logged['r_rate'] = r_rate

        self.recovery()

    def recovery(self):
        for d in [wan, lan]:
            d.sendcontrol('c')
            d.sendcontrol('c')
            d.expect(prompt)

class iPerf3RTest(iPerf3Test):
    '''iPerf3 reverse generic performance tests'''

    opts = "-R"
