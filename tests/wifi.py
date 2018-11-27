
import rootfs_boot
from devices import wlan

class WifiScan(rootfs_boot.RootFSBootTest):
    '''Simple test to run a wifi scan'''

    def runTest(self):
        output = wlan.scan()
        return output()
