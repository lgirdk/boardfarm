import os

import rootfs_boot
from lib.installers import install_jmeter

from devices import lan, prompt
from devices.common import scp_from

class JMeter(rootfs_boot.RootFSBootTest):

    jmx = "https://jmeter.apache.org/demos/ForEachTest2.jmx"

    def runTest(self):
        install_jmeter(lan)

        if 'http' in self.jmx:
            lan.sendline('curl %s > test.jmx')
            lan.expect(prompt)
        else:
            raise Exception("Don't know how to handle downloading %s")

        lan.sendline('rm -rf output *.log')
        lan.expect(prompt)
        lan.sendline('mkdir -p output')
        lan.expect(prompt)
        lan.sendline('jmeter -n -t AssertionTestPlan.jmx -l foo.log -e -o output')
        lan.expect(prompt)

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
