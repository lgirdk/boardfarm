import rootfs_boot
import lib

class selftest_fake_test(rootfs_boot.RootFSBootTest):
    '''
    A place holder test that is skipped by default
    Can be used for module import fail and force the results
    to show a skipped test.
    It is in its own module so (in theory) it will always be imported
    '''
    log_to_file = ""
    def runTest(self):
        msg = 'fake test Skipping'
        lib.common.test_msg(msg)
        self.skipTest(msg)
