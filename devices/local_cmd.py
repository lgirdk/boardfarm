import pexpect
import base_connection

class LocalCmd(base_connection.BaseConnection):
    '''
    Set connection_type to local_cmd, ignores all output for now
    '''
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        try:
            if super(LocalCmd, self).connect():
                return
            pexpect.spawn.__init__(self.device,
                               command='/bin/bash',
                               args=['-c', self.conn_cmd])
            self.device.expect(pexpect.TIMEOUT, timeout=5)
        except pexpect.EOF as e:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        if super(LocalCmd, self).close():
            return
        self.device.sendcontrol('c')

