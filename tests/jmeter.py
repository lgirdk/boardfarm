import os
import pexpect

import rootfs_boot
from lib.installers import install_jmeter

from devices import board, lan, prompt
from devices.common import scp_from

class JMeter(rootfs_boot.RootFSBootTest):
    '''Runs JMeter jmx file from LAN device'''

    #jmx = "https://jmeter.apache.org/demos/ForEachTest2.jmx"
    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq.jmx')

    def runTest(self):
        install_jmeter(lan)

        if self.jmx.startswith('http'):
            lan.sendline('curl %s > test.jmx' % self.jmx)
            lan.expect(prompt)
        else:
            print("Copying %s to lan device")
            lan.copy_file_to_server(self.jmx, dst='/root/test.jmx')

        lan.sendline('rm -rf output *.log')
        lan.expect(prompt)
        lan.sendline('mkdir -p output')
        lan.expect(prompt)

        board.collect_stats(stats=['mpstat'])

        lan.sendline('jmeter -n -t test.jmx -l foo.log -e -o output')
        lan.expect_exact('jmeter -n -t test.jmx -l foo.log -e -o output')
        for i in range(300):
            if 0 != lan.expect([pexpect.TIMEOUT] + prompt, timeout=5):
                break;
            board.get_nf_conntrack_conn_count()
            board.get_proc_vmstat()
            board.touch()

            if i == 299:
                raise Exception("jmeter did not have enough time to complete")

        print "Copying files from lan to dir = %s" % self.config.output_dir
        lan.sendline('readlink -f output/')
        lan.expect('readlink -f output/')
        lan.expect(prompt)
        fname=lan.before.strip()
        scp_from(fname, lan.ipaddr, lan.username, lan.password, lan.port, os.path.join(self.config.output_dir, 'jmeter'))

        #lan.sendline('rm -rf output')
        #lan.expect(prompt)
        lan.sendline('rm test.jmx')
        lan.expect(prompt)

        self.recover()

    def recover(self):
        lan.sendcontrol('c')
        lan.expect(prompt)

        board.parse_stats(dict_to_log=self.logged)
        self.result_message = 'JMeter: DONE, cpu usage = %s' % self.logged['mpstat']
