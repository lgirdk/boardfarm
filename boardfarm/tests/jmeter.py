"""Jmeter related."""
import os
import shutil

import pexpect

from boardfarm.devices import prompt
from boardfarm.lib.common import scp_from
from boardfarm.lib.installers import install_jmeter
from boardfarm.tests import rootfs_boot


def rm_r(path):
    """Unlink path."""
    if not os.path.exists(path):
        return
    if os.path.isfile(path) or os.path.islink(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


class JMeter(rootfs_boot.RootFSBootTest):
    """Runs JMeter jmx file from LAN device."""

    jmx = "https://jmeter.apache.org/demos/ForEachTest2.jmx"
    shortname = "ForEachTest2"
    default_time = 600

    def runTest(self):
        """Runs the JMeter jmx file."""
        board = self.dev.board
        lan = self.dev.lan

        self.dir = f"jmeter_{self.shortname}"
        install_jmeter(lan)

        lan.sendline(f"rm -rf $HOME/{self.dir}")
        lan.expect(prompt)
        lan.sendline(f"mkdir -p $HOME/{self.dir}/wd")
        lan.expect(prompt)
        lan.sendline(f"mkdir -p $HOME/{self.dir}/results")
        lan.expect(prompt)

        if self.jmx.startswith("http"):
            lan.sendline(f"curl {self.jmx} > $HOME/{self.dir}/test.jmx")
            lan.expect(prompt)
        else:
            print(f"Copying {self.jmx} to lan device")
            lan.sendline("echo $HOME")
            lan.expect_exact("echo $HOME")
            lan.expect(prompt)
            lan.copy_file_to_server(
                self.jmx, dst=lan.before.strip() + f"/{self.dir}/test.jmx"
            )

        board.collect_stats(stats=["mpstat"])

        lan.sendline(f"cd $HOME/{self.dir}/wd")
        lan.expect(prompt)
        lan.sendline(
            'JVM_ARGS="-Xms4096m -Xmx8192m" jmeter -n -t ../test.jmx -l foo.log -e -o $HOME/%s/results'
            % self.dir
        )
        lan.expect_exact(f"$HOME/{self.dir}/results")
        for i in range(self.default_time):
            if 0 != lan.expect([pexpect.TIMEOUT] + prompt, timeout=5):
                break
            conns = board.get_nf_conntrack_conn_count()
            board.get_proc_vmstat()
            board.touch()

            if i > 100 and conns < 20:
                raise Exception("jmeter is dead/stuck/broke, aborting the run")

            if i == 599:
                raise Exception("jmeter did not have enough time to complete")

        lan.sendline("cd -")
        lan.expect(prompt)
        lan.sendline("rm test.jmx")
        lan.expect(prompt)

        self.recover()

    def recover(self):
        """Do clean the LAN after running JMeter."""
        board = self.dev.board
        lan = self.dev.lan

        board.touch()
        lan.sendcontrol("c")
        lan.expect(prompt)
        board.touch()

        print(f"Copying files from lan to dir = {self.config.output_dir}")
        lan.sendline(f"readlink -f $HOME/{self.dir}/")
        lan.expect_exact(f"$HOME/{self.dir}/")
        board.touch()
        lan.expect(prompt)
        board.touch()
        fname = lan.before.replace("\n", "").replace("\r", "")
        board.touch()
        rm_r(os.path.join(self.config.output_dir, self.dir))
        scp_from(
            fname,
            lan.ipaddr,
            lan.username,
            lan.password,
            lan.port,
            self.config.output_dir,
        )

        # let board settle down
        board.expect(pexpect.TIMEOUT, timeout=30)
        board.touch()

        board.parse_stats(dict_to_log=self.logged)
        board.touch()
        self.result_message = "JMeter: DONE, name = {} cpu usage = {}".format(
            self.shortname,
            self.logged["mpstat"],
        )


class JMeter_10x_10u_5t(JMeter):
    """Runs JMeter jmx 10x_10u_5t."""

    jmx = os.path.join(os.path.dirname(__file__), "jmeter/httpreq_10x_10u_5t.jmx")
    shortname = "httpreq_10x_10u_5t"


class JMeter_1x_9u_5t(JMeter):
    """Runs JMeter jmx 1x_9u_5t."""

    jmx = os.path.join(os.path.dirname(__file__), "jmeter/httpreq_1x_9u_5t.jmx")
    shortname = "httpreq_1x_9u_5t"


class JMeter_20x_9u_1t(JMeter):
    """Runs JMeter jmx 20x_9u_1t."""

    jmx = os.path.join(os.path.dirname(__file__), "jmeter/httpreq_20x_9u_1t.jmx")
    shortname = "httpreq_20x_9u_1t"


class JMeter_20x_9u_1t_300msdelay(JMeter):
    """Runs JMeter jmx 20x_9u_1t_300msdelay."""

    jmx = os.path.join(
        os.path.dirname(__file__), "jmeter/httpreq_20x_9u_1t_300msdelay.jmx"
    )
    shortname = "httpreq_20x_9u_1t_300msdelay"


class JMeter_20x_9u_1t_500msdelay(JMeter):
    """Runs JMeter jmx 20x_9u_1t_500msdelay."""

    jmx = os.path.join(
        os.path.dirname(__file__), "jmeter/httpreq_20x_9u_1t_500msdelay.jmx"
    )
    shortname = "httpreq_20x_9u_1t_500msdelay"


class JMeter_20x_9u_1t_1000msdelay(JMeter):
    """Runs JMeter jmx 20x_9u_1t_1000msdelay."""

    jmx = os.path.join(
        os.path.dirname(__file__), "jmeter/httpreq_20x_9u_1t_1000msdelay.jmx"
    )
    shortname = "httpreq_20x_9u_1t_1000msdelay"


class JMeter_20x_9u_1t_1500msdelay(JMeter):
    """Runs JMeter jmx 20x_9u_1t_1500msdelay."""

    jmx = os.path.join(
        os.path.dirname(__file__), "jmeter/httpreq_20x_9u_1t_1500msdelay.jmx"
    )
    shortname = "httpreq_20x_9u_1t_1500msdelay"
