import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper

class LocalCmd():
    '''
    Set connection_type to local_cmd, ignores all output for now
    '''
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        try:
            bft_pexpect_helper.spawn.__init__(self.device,
                               command='/bin/bash',
                               args=['-c', self.conn_cmd])
            self.device.expect(pexpect.TIMEOUT, timeout=5)
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        self.device.sendcontrol('c')
