import rootfs_boot
import lib
import hashlib
import random
import string
from devices import board, wan, lan, wlan, prompt, common

'''
    This file can bu used to add unit tests that
    tests/validate the behavior of new/modified
    components.
'''

class test_create_session(rootfs_boot.RootFSBootTest):
    '''
    tests the create_session function in devices/__init__.py
    '''
    session = None
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping test_create_session.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        wan_ip = wan.get_interface_ipaddr("eth0")

        import devices
        # this should fail, as "DebianBoxNonExistent" is not (yet) a device
        try:
            self.session = devices.create_session("DebianBoxNonExistent", "wan_test_calls_fail", wan_ip, 22, 'magenta')
        except:
            print("Failed to create session on wrong class name (expected) PASS")
            pass
        else:
            assert 0,"Test Failed on wrong class name"

        # this must fail, as "169.254.12.18" is not a valid ip
        try:
            self.session = devices.create_session("DebianBox", "wan_test_ip_fail", "169.254.12.18", 22, 'cyan')
        except:
            print("Failed to create session on wrong IP (expected) PASS")
            pass
        else:
            assert 0,"Test Failed on wrong IP"

        # this must fail, as 50 is not a valid port
        try:
            self.session = devices.create_session("DebianBox", "wan_test_port_fail", wan_ip, 50, 'red')
        except:
            print("Failed to create session on wrong port expected")
            pass
        else:
            assert 0,"Test Failed on wrong port"

        # this should pass
        try:
            self.session = devices.create_session("DebianBox", "wan_test", wan_ip, 22, 'yellow')
        except:
            assert 0, "Failed to create session, Test FAILED!"

        print("Session created successfully")

        # is the session really logged onto the wan?

        wan.sendline()
        wan.expect(wan.prompt)
        wan.sendline("ip a")
        wan.expect(wan.prompt)
        w = wan.before

        self.session.sendline()
        self.session.expect(self.session.prompt)
        self.session.sendline("ip a")
        self.session.expect(self.session.prompt)
        s = self.session.before

        assert w == s, "Interfaces differ!!! Test Failed"

        self.session.sendline("exit")

        print("Test passed")

    def recover(self):
        if self.session is not None:
            self.session.sendline("exit")



