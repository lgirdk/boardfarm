import rootfs_boot
import lib
import hashlib
import random
import string
import os
import tempfile
from devices import board, wan, lan, wlan, prompt, common

'''
    This file can bu used to add unit tests that
    tests/validate the behavior of new/modified
    components.
'''

class selftest_test_copy_file_to_server(rootfs_boot.RootFSBootTest):
    '''
    Copy a file to /tmp on the WAN device using common.copy_file_to_server
    '''
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping copy file to WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        if not hasattr(wan, 'ipaddr'):
            msg = 'WAN device is not running ssh server, can\'t copy with this function'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        text_file = tempfile.NamedTemporaryFile()
        self.fname = fname = text_file.name

        letters = string.ascii_letters
        fcontent = ''.join(random.choice(letters) for i in range(50))

        text_file.write(fcontent)
        text_file.flush()

        fmd5 = hashlib.md5(open(fname,'rb').read()).hexdigest()
        print("File orginal md5sum: %s"% fmd5)

        wan_ip = wan.get_interface_ipaddr("eth0")

        cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"cat - > %s\""\
              % (fname, wan.username, wan_ip, fname)
        # this must fail as the command does not echo the filename
        try:
            common.copy_file_to_server(cmd, wan.password, "/tmp")
        except:
            print("Copy failed as expected")
            pass

        cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"cat - > %s; echo %s\""\
              % (fname, wan.username, wan_ip, fname, fname)
        # this should pass
        try:
            common.copy_file_to_server(cmd, wan.password, "/tmp")
        except:
            assert 0,"copy_file_to_server failed, Test failed!!!!"

        # is the destination file identical to the source file
        wan.sendline("md5sum %s"% fname)
        wan.expect(fmd5)
        wan.expect(wan.prompt)

        print("Test passed")

class selftest_test_create_session(rootfs_boot.RootFSBootTest):
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
            kwargs ={
                    'name':"wan_test_calls_fail",
                    'ipaddr':wan_ip,
                    'port':22,
                    'color': 'magenta'
                    }
            self.session = devices.get_device("DebianBoxNonExistent", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong class name"
            print("Failed to create session on wrong class name (expected) PASS")

        # this must fail, as "169.254.12.18" is not a valid ip
        try:
            kwargs ={
                    'name':"wan_test_ip_fail",
                    'ipaddr':"169.254.12.18",
                    'port':22,
                    'color': 'cyan'
                    }
            self.session = devices.get_device("DebianBox", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong IP"
            print("Failed to create session on wrong IP (expected) PASS")

        # this must fail, as 50 is not a valid port
        try:
            kwargs ={
                    'name':"wan_test_port_fail",
                    'ipaddr':wan_ip,
                    'port':50,
                    'color': 'red'
                    }
            self.session = devices.get_device("DebianBox", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong port"
            print("Failed to create session on wrong port (expected) PASS")

        # this must fail, close but no cigar
        try:
            kwargs ={
                    'name':"wan_test_type_fail",
                    'ipaddr':wan_ip,
                    'port':50,
                    'color': 'red'
                    }
            self.session = devices.get_device("debina", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on misspelled class name"
            print("Failed to create session on misspelled class name (expected) PASS")

        # this should pass
        try:
            kwargs ={
                    'name':"correct_wan_parms",
                    'ipaddr':wan_ip,
                    'port':'22',
                    'color': 'yellow'
                    }
            self.session = devices.get_device("debian", **kwargs)
        except:
            assert 0, "Failed to create session, Test FAILED!"
        else:
            assert self.session is not None,"Test Failed on correct paramters!!"

        print("Session created successfully")

        # is the session really logged onto the wan?

        wan.sendline()
        wan.expect(wan.prompt)
        wan.sendline("ip a")
        wan.expect_exact("ip a")
        wan.expect(wan.prompt)
        w = wan.before

        self.session.sendline()
        self.session.expect(self.session.prompt)
        self.session.sendline("ip a")
        self.session.expect_exact("ip a")
        self.session.expect(self.session.prompt)
        s = self.session.before

        assert w == s, "Interfaces differ!!! Test Failed"

        self.session.sendline("exit")

        print("Test passed")

    def recover(self):
        if self.session is not None:
            self.session.sendline("exit")

class selftest_increment_mac(rootfs_boot.RootFSBootTest):
    '''This function to increment the value of mac address for different format '''

    def runTest(self):
        from lib.common import increment_mac
        mac = ["38:43:7D:80:04:67", "38:43:7D:80:04:0F", "38:43:7D:80:04:FF", '3843.7d80.046f', "38-43-7D-80-04-FF", '3843.7d80.ffff', "38-43-7D-80-FF-FF"]

        expected_mac = ["38:43:7D:80:04:68", "38:43:7D:80:04:10", "38:43:7D:80:05:00", '3843.7d80.0470', "38-43-7D-80-05-00", '3843.7d81.0000', "38-43-7D-81-00-00"]
        for i in range(len(mac)):
            assert expected_mac[i].lower() == increment_mac(mac[i], 1).lower(), "Failed on incrementing mac" + mac[i]
            print('mac: '+mac[i] + '+1 = ' + expected_mac[i] + ' PASS')

        print("Test passed")
