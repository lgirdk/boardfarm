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

class selftest_test_moved_function(rootfs_boot.RootFSBootTest):
    '''
    tests the function moved from base.py to devices/linux.py
    '''
    def runTest(self):
        from devices import lan
        import debian, linux
        if lan.model == "debian":
            # check that lan is derived from LinuxDevice
            assert(issubclass(debian.DebianBox, linux.LinuxDevice))

        lan_mac = lan.get_interface_macaddr(lan.iface_dut)
        assert lan_mac != None, "Failed getting lan mac address"
        print "lan mac address: %s", lan_mac

        uptime = lan.get_seconds_uptime()
        assert uptime != None, "Failed getting system uptime"
        print "system uptime is: %s", uptime

        ping_check = lan.ping("8.8.8.8")
        print "ping status is %s", ping_check

        ipv6_disable = lan.disable_ipv6(lan.iface_dut)
        ipv6_enable = lan.enable_ipv6(lan.iface_dut)
        board.set_printk()
        print("Test passed")

    def recover(self):
        if self.session is not None:
            self.session.sendline("exit")
