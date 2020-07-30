"""Class functions related to console delay actions."""
from boardfarm.tests import rootfs_boot


class DelayBetweenChar(rootfs_boot.RootFSBootTest):
    """Delay between each characters."""

    def runTest(self):
        """Introduce required delay."""
        board = self.dev.board

        board.delaybetweenchar = 0.1

        for console in board.consoles:
            console.delaybetweenchar = 0.1


class DelayBetweenCharExtreme(rootfs_boot.RootFSBootTest):
    """High delay time between each characters."""

    def runTest(self):
        """Introduce required delay."""
        board = self.dev.board

        board.delaybetweenchar = 1
        for console in board.consoles:
            console.delaybetweenchar = 1


class NoDelayBetweenChar(rootfs_boot.RootFSBootTest):
    """No delay between input characters."""

    def runTest(self):
        """Introduce No delay."""
        board = self.dev.board

        board.delaybetweenchar = None
        for console in board.consoles:
            console.delaybetweenchar = None
