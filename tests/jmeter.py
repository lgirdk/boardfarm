import os
import pexpect

import rootfs_boot
from lib.installers import install_jmeter

from devices import board, lan, prompt
from devices.common import scp_from

class JMeter(rootfs_boot.RootFSBootTest):
    '''Runs JMeter jmx file from LAN device'''

    jmx = "https://jmeter.apache.org/demos/ForEachTest2.jmx"
    shortname = "ForEachTest2"

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
        for i in range(600):
            if 0 != lan.expect([pexpect.TIMEOUT] + prompt, timeout=5):
                break;
            board.get_nf_conntrack_conn_count()
            board.get_proc_vmstat()
            board.touch()

            if i == 599:
                raise Exception("jmeter did not have enough time to complete")


        #lan.sendline('rm -rf output')
        #lan.expect(prompt)
        lan.sendline('rm test.jmx')
        lan.expect(prompt)

        self.recover()

    def recover(self):
        lan.sendcontrol('c')
        lan.expect(prompt)

        print "Copying files from lan to dir = %s" % self.config.output_dir
        lan.sendline('readlink -f output/')
        lan.expect('readlink -f output/')
        lan.expect(prompt)
        fname=lan.before.strip()
        scp_from(fname, lan.ipaddr, lan.username, lan.password, lan.port, os.path.join(self.config.output_dir, 'jmeter_%s' % self.shortname))

        # let board settle down
        board.expect(pexpect.TIMEOUT, timeout=30)

        board.parse_stats(dict_to_log=self.logged)
        self.result_message = 'JMeter: DONE, name = %s cpu usage = %s' % (self.shortname, self.logged['mpstat'])


class JMeter_10x_10u_5t(JMeter):
    '''Runs JMeter jmx 10x_10u_5t'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_10x_10u_5t.jmx')
    name = "httpreq_10x_10u_5t"

class JMeter_1x_9u_5t(JMeter):
    '''Runs JMeter jmx 1x_9u_5t'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_1x_9u_5t.jmx')
    name = "httpreq_1x_9u_5t"

class JMeter_20x_9u_1t(JMeter):
    '''Runs JMeter jmx 20x_9u_1t'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_20x_9u_1t.jmx')
    name = "httpreq_20x_9u_1t"

class JMeter_20x_9u_1t_300msdelay(JMeter):
    '''Runs JMeter jmx 20x_9u_1t_300msdelay'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_20x_9u_1t_300msdelay.jmx')
    name = "httpreq_20x_9u_1t_300msdelay"

class JMeter_20x_9u_1t_500msdelay(JMeter):
    '''Runs JMeter jmx 20x_9u_1t_500msdelay'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_20x_9u_1t_500msdelay.jmx')
    name = "httpreq_20x_9u_1t_500msdelay"

class JMeter_20x_9u_1t_1000msdelay(JMeter):
    '''Runs JMeter jmx 20x_9u_1t_1000msdelay'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_20x_9u_1t_1000msdelay.jmx')
    name = "httpreq_20x_9u_1t_1000msdelay"

class JMeter_20x_9u_1t_1500msdelay(JMeter):
    '''Runs JMeter jmx 20x_9u_1t_1500msdelay'''

    jmx = os.path.join(os.path.dirname(__file__), 'jmeter/httpreq_20x_9u_1t_1500msdelay.jmx')
    name = "httpreq_20x_9u_1t_1500msdelay"
