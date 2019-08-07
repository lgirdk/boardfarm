
import rootfs_boot
from devices import wlan

class WifiScan(rootfs_boot.RootFSBootTest):
    '''Simple test to run a wifi scan'''

    def runTest(self):
        scan_output = wlan.scan()
        return scan_output
