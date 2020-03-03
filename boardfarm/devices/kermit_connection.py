import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class KermitConnection():
    """Wrapper for the kermit command
    kermit can be used as an alternative to telnet. On some
    platform telnet can hog the cpu to 100% for no apparent
    reason. kermit seems to be more stable, but to work properly
    it needs a little setting up.
    """
    prompt = "C-Kermit>"

    def __init__(self, device=None, conn_cmd=None, **kwargs):
        """This method initializes the variables used for a kermit connection.

        :param device: the device on which the command is to be executed, defaults to None
        :type device: object
        :param conn_cmd: the command to be used to connect to the device, defaults to None
        :type conn_cmd: string
        :param **kwargs: extra args to be used if any
        :type **kwargs: dict
        """
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        """This method initializes a pexpect session with kermit command as argument.
        This will result in a telnet connection to the device.
        Note: This function only works on password-less devices

        :raises: Exception Board is in use (connection refused).
        """
        try:
            bft_pexpect_helper.spawn.__init__(self.device,
                                              command='/bin/bash',
                                              args=['-c', "kermit"])
            self.device.sendline()
            self.device.expect(self.prompt)
            # don't be strict and wait too long for the negotiations
            self.device.sendline("SET TELNET WAIT OFF")
            self.device.expect(self.prompt)
            self.device.sendline("set host %s" %
                                 ' '.join(self.conn_cmd.split(' ')[1:]))
            self.device.expect(self.prompt)
            self.device.sendline('connect')
            self.device.expect(
                ['----------------------------------------------------'],
                timeout=15)
            # check if it is a Microsoft Telnet Service
            if 0 == self.device.expect(
                ['Welcome to Microsoft Telnet Service', pexpect.TIMEOUT],
                    timeout=10):
                # MS telnet server does weird things... this sendline should get the 'login:' prompt
                self.device.sendline()
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        """Closes the pexpect session to the device
        """
        self.device.sendcontrol('\\')
        self.device.sendline('c')
        self.device.expect(self.prompt)
        self.device.sendline('q')
        self.device.expect(r'OK to exit\?')
        self.device.sendline('y')
