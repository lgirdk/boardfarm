import os

from boardfarm.tests import rootfs_boot


class IPTablesDump(rootfs_boot.RootFSBootTest):
    """Dumps all IPTables rules with stats."""

    def runTest(self):
        """Start Dumping all IPTables rules with stats."""
        board = self.dev.board

        pp = board.get_pp_dev()
        with open(os.path.join(self.config.output_dir, "iptables.log"), "w") as ipt_log:
            for tbl in ["filter", "nat", "mangle", "raw", "security"]:
                pp.sendline("iptables -n -t %s -L -v; echo DONE" % tbl)
                pp.expect_exact("echo DONE")
                pp.expect_exact("DONE")
                ipt_log.write(pp.before)
                pp.expect(pp.prompt)


class IPTablesFlushMangle(rootfs_boot.RootFSBootTest):
    """Flushes mangle table."""

    def runTest(self):
        """Start flushing mangle table."""
        board = self.dev.board

        pp = board.get_pp_dev()
        pp.sendline("iptables -t mangle -F; iptables -t mangle -X")
        pp.expect(pp.prompt)


class IPTablesResetCounters(rootfs_boot.RootFSBootTest):
    """Reset iptables counters."""

    def runTest(self):
        """Start reseting iptables counters."""
        board = self.dev.board

        pp = board.get_pp_dev()
        pp.sendline("iptables -Z")
        pp.expect(pp.prompt)
