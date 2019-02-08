import rootfs_boot

from devices import board

class DelayBetweenChar(rootfs_boot.RootFSBootTest):
    def runTest(self):
        board.delaybetweenchar = 0.1

class NoDelayBetweenChar(rootfs_boot.RootFSBootTest):
    def runTest(self):
        board.delaybetweenchar = None

