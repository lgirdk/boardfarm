import boardfarm.exceptions
import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class LocalCmd():
    """This class is meant to be used to connect to a device
    using a custom Linux command instead of telnet/SSH.

    Sets connection_type to local_cmd, ignores all output for now
    """
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        """Initializes instance of LocalCmd class

        :param device: the device on which the command is to be executed, defaults to None
        :type device: object
        :param conn_cmd: the command to be used to connect to the device, defaults to None
        :type conn_cmd: string
        :param **kwargs: extra args to be used if any
        :type **kwargs: dict
        """
        self.device = device
        self.conn_cmd = conn_cmd
        self.device.conn_cmd = conn_cmd

    def connect(self):
        """This method is used to connect to the device
           It spawns a pexpect session for the device using the local cmd.

        :raises: Exception Board is in use (connection refused).
        """
        try:
            bft_pexpect_helper.spawn.__init__(self.device,
                                              command='/bin/bash',
                                              args=['-c', self.conn_cmd])
            self.device.expect(pexpect.TIMEOUT, timeout=5)
        except pexpect.EOF:
            raise boardfarm.exceptions.ConnectionRefused(
                "Board is in use (connection refused).")

    def close(self, force=True):
        """closes the pexpect session to the device
        """
        try:
            if 'telnet' in self.conn_cmd:
                self.sendcontrol(']')
                self.sendline('q')
            else:
                self.sendcontrol('c')
        except:
            pass
        finally:
            super(type(self), self).close()
