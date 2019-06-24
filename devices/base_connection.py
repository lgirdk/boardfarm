import pexpect
from lib.common import cmd_exists

class BaseConnection(pexpect.spawn):
    use_kermit = False
    prompt = "C-Kermit>"

    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        try:
            if cmd_exists('kermit') and 'telnet' in self.conn_cmd:
                pexpect.spawn.__init__(self.device,
                                       command='/bin/bash',
                                       args=['-c', "kermit"])
                self.device.sendline()
                self.device.expect(self.prompt)
                self.device.sendline("SET TELNET WAIT OFF")
                self.device.expect(self.prompt)
                self.device.sendline(self.conn_cmd)
                self.device.expect('----------------------------------------------------', timeout = 5)
                self.use_kermit = True
        except:
            self.device.close()
            print "failed to connect via kermit"
            pass

        return self.use_kermit

    def close():
        if self.use_kermit:
            self.device.sendcontrol('\\')
            self.device.sendline('c')
            self.device.expect(self.prompt)
            self.device.sendline('q')
            self.device.expect('OK to exit\?')
            self.device.sendline('y')

