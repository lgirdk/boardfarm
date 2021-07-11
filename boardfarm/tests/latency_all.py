import re

from boardfarm.tests import rootfs_boot


class LatencyAllDevices(rootfs_boot.RootFSBootTest):
    """finds latency between all devices."""

    def runTest(self):
        board = self.dev.board

        # TODO: create a get devices function?
        devs = []
        for device in self.config.devices:
            devs.append(getattr(self.config, device))

        devs.append(board.get_pp_dev())

        results = []

        for d1 in devs:
            for d2 in devs:
                if d1 is d2:
                    continue

                board.touch()

                print("comparing " + d1.name + " to " + d2.name)

                try:
                    ip1 = d1.get_interface_ipaddr(d1.iface_dut)
                    ip2 = d2.get_interface_ipaddr(d2.iface_dut)

                    def parse_ping_times(string):
                        r = [float(i) for i in re.findall(r"time=([^\s]*) ms", string)]
                        return sum(r) / len(r)

                    d1.sendline(f"ping -c20 {ip2}")
                    d1.expect_exact(f"ping -c20 {ip2}")
                    d1.expect(d1.prompt)

                    result = parse_ping_times(d1.before)
                    if result is not float("nan"):
                        results.append(
                            f"latency from {d1.name} to {d2.name} = {str(result)} ms"
                        )

                    d2.sendline(f"ping -c20 {ip1}")
                    d2.expect_exact(f"ping -c20 {ip1}")
                    d2.expect(d2.prompt)

                    result = parse_ping_times(d2.before)
                    if result is not float("nan"):
                        results.append(
                            f"latency from {d2.name} to {d1.name} = {str(result)} ms"
                        )
                except Exception as error:
                    print(error)
                    print("failed to ping " + d1.name + " to " + d2.name)
                    continue

        print("Results:")
        for line in results:
            print(line)
