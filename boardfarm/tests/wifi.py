from boardfarm.tests import rootfs_boot


class WifiScan(rootfs_boot.RootFSBootTest):
    '''Simple test to run a wifi scan'''
    def runTest(self):
        wlan = self.dev.wlan

        scan_output = wlan.scan()
        return scan_output
