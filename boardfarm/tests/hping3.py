"""Floods hping3, creating lots of firewall entries in router."""
import pexpect

from boardfarm.devices import prompt
from boardfarm.lib.installers import install_hping3
from boardfarm.tests import rootfs_boot


class hping3_basic_udp(rootfs_boot.RootFSBootTest):
    """Floods hping3, creating lots of firewall entries in router."""

    conn_rate = "u2000"
    conns = 20000

    def runTest(self):
        """Flood hping3."""
        board = self.dev.board
        wan = self.dev.wan
        lan = self.dev.lan

        install_hping3(lan)
        wan_ip = wan.get_interface_ipaddr(wan.iface_dut)
        wan.sendline(f"nc -lvu {wan_ip} 565")
        wan.expect_exact(f"nc -lvu {wan_ip} 565")

        board.collect_stats(stats=["mpstat"])

        # dest ip and port are fixed, random src port, fixed src ip, 100 us between
        lan.sendline(
            "hping3 -2 -c %s -d 120 -S -w 64 -p 445 -i %s %s"
            % (self.conns, self.conn_rate, wan_ip)
        )
        lan.expect("HPING")

        self.max_conns = 0
        for _ in range(10):
            self.max_conns = max(self.max_conns, board.get_nf_conntrack_conn_count())
            board.get_proc_vmstat()
            lan.expect(pexpect.TIMEOUT, timeout=3)
            board.expect(pexpect.TIMEOUT, timeout=3)
            board.touch()

        self.recover()

    def recover(self):
        """Kill hping3."""
        board = self.dev.board
        wan = self.dev.wan
        lan = self.dev.lan

        lan.sendcontrol("c")
        lan.expect(prompt)
        lan.sendline("pkill -9 -f hping3")
        lan.expect_exact("pkill -9 -f hping3")
        lan.expect(prompt)

        wan.sendcontrol("c")
        wan.expect(prompt)
        wan.sendline("pkill -9 -f nc ")
        wan.expect_exact("pkill -9 -f nc")
        wan.expect(prompt)

        board.parse_stats(dict_to_log=self.logged)

        args = (self.conn_rate, self.max_conns, self.logged["mpstat"])
        self.result_message = (
            "hping3 udp firewall test, conn_rate = %s, max_conns = %s, cpu usage = %.2f"
            % args
        )


class hping3_basic_udp_long(hping3_basic_udp):
    """Floods hping3, creating lots of firewall entries in router."""

    conn_rate = "u2000"
    conns = "60000"
