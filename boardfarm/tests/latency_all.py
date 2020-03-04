from boardfarm.tests import rootfs_boot
import re

from boardfarm.devices import board


class LatencyAllDevices(rootfs_boot.RootFSBootTest):
    '''finds latency between all devices'''
    def runTest(self):

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
                        r = [
                            float(i)
                            for i in re.findall(r'time=([^\s]*) ms', string)
                        ]
                        return sum(r) / len(r)

                    d1.sendline("ping -c20 %s" % ip2)
                    d1.expect_exact("ping -c20 %s" % ip2)
                    d1.expect(d1.prompt)

                    result = parse_ping_times(d1.before)
                    if result is not float('nan'):
                        results.append('latency from %s to %s = %s ms' %
                                       (d1.name, d2.name, str(result)))

                    d2.sendline("ping -c20 %s" % ip1)
                    d2.expect_exact("ping -c20 %s" % ip1)
                    d2.expect(d2.prompt)

                    result = parse_ping_times(d2.before)
                    if result is not float('nan'):
                        results.append('latency from %s to %s = %s ms' %
                                       (d2.name, d1.name, str(result)))
                except:
                    print("failed to ping " + d1.name + " to " + d2.name)
                    continue

        print("Results:")
        for line in results:
            print(line)
