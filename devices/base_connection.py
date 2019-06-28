import pexpect
from lib.common import cmd_exists

class BaseConnection(pexpect.spawn):
    disable_kermit = False
    use_kermit = False
    prompt = "C-Kermit>"

    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        if self.disable_kermit: return False
        try:
            if cmd_exists('kermit') and 'telnet' in self.conn_cmd:
                pexpect.spawn.__init__(self.device,
                                       command='/bin/bash',
                                       args=['-c', "kermit"])
                self.device.sendline()
                self.device.expect(self.prompt)
                self.device.sendline("SET TELNET WAIT OFF") # don't be strict and wait too long
                self.device.expect(self.prompt)
                self.device.sendline(self.conn_cmd)
                idx = self.device.expect(['Failed: Connection refused', '----------------------------------------------------', pexpect.TIMEOUT], timeout=15)
                if 1 == idx:
                    # check if it is a Microsoft Telnet Service
                    if 0 == self.device.expect(['Welcome to Microsoft Telnet Service', pexpect.TIMEOUT], timeout=15):
                        # MS does weird things... just let the derived class deal with it!
                        return self.use_kermit
                    self.use_kermit = True
                elif 0 == idx:
                    raise Exception(pexpect.EOF)
        except Exception as e:
            self.use_kermit = False
            self.device.close()
            print "failed to connect via kermit"
            raise e
        return self.use_kermit

    def close(self):
        if self.use_kermit:
            self.device.sendcontrol('\\')
            self.device.sendline('c')
            self.device.expect(self.prompt)
            self.device.sendline('q')
            self.device.expect('OK to exit\?')
            self.device.sendline('y')
            self.use_kermit = False

