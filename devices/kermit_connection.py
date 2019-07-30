import os
import pexpect
import config
from lib.common import cmd_exists

class KermitConnection():
    """
    Wrapper for the kermit command
    kermit can be used as an alternative to telnet. On some
    platform telnet can hog the cpu to 100% for no apparent
    reason. kermit seems to be more stable, but to work properly
    it needs a little setting up.
    """
    prompt = "C-Kermit>"

    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        try:
            pexpect.spawn.__init__(self.device,
                                   command='/bin/bash',
                                   args=['-c', "kermit"])
            self.device.sendline()
            self.device.expect(self.prompt)
            # don't be strict and wait too long for the negotiations
            self.device.sendline("SET TELNET WAIT OFF")
            self.device.expect(self.prompt)
            self.device.sendline("set host %s"% ' '.join(self.conn_cmd.split(' ')[1:]))
            self.device.expect(self.prompt)
            self.device.sendline('connect')
            self.device.expect(['----------------------------------------------------'], timeout=15)
            # check if it is a Microsoft Telnet Service
            if 0 == self.device.expect(['Welcome to Microsoft Telnet Service', pexpect.TIMEOUT], timeout=10):
                # MS telnet server does weird things... this sendline should get the 'login:' prompt
                self.device.sendline()
        except pexpect.EOF as e:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        self.device.sendcontrol('\\')
        self.device.sendline('c')
        self.device.expect(self.prompt)
        self.device.sendline('q')
        self.device.expect('OK to exit\?')
        self.device.sendline('y')
