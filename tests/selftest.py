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

class selftest_test_copy_file_to_server(rootfs_boot.RootFSBootTest):
    '''
    Copy a file to /tmp on the WAN device using common.copy_file_to_server
    '''
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping copy file to WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        fname = "/tmp/smallFile.txt"

        letters = string.ascii_letters
        fcontent = ''.join(random.choice(letters) for i in range(50))

        text_file = open(fname, "w")
        text_file.write(fcontent)
        text_file.close()

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

