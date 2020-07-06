import pexpect
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class SshConnection:
    """To use, set conn_cmd in your json to "ssh root@192.168.1.1 -i ~/.ssh/id_rsa" and set connection_type to ssh."""
    def __init__(self,
                 device=None,
                 conn_cmd=None,
                 ssh_password="None",
                 **kwargs):
        """Call connection-decider from device class which in return\
           initialize an SSH connection for the device class.

        This class in not supposed to be initialized directly.
        :param device: device to connect, defaults to None
        :type device: object
        :param conn_cmd: conn_cmd to connect to device, defaults to None
        :type conn_cmd: string
        :param ssh_password: ssh_password to connect to device, defaults to 'None'
        :type ssh_password: string
        :param ``**kwargs``: args to be used
        :type ``**kwargs``: dict
        """
        self.device = device
        self.conn_cmd = conn_cmd
        self.ssh_password = ssh_password

    def connect(self):
        """Connect to the device via ssh using credentials\
        spawn the device to check the availability and expect\
        for password/passphrase raise exeception if we are not getting prompt for password.

        :param self: self object
        :type self: object
        :raises: Exception Board is in use (connection refused). / Assert Exception ssh_password is None
        """
        bft_pexpect_helper.spawn.__init__(self.device,
                                          command="/bin/bash",
                                          args=["-c", self.conn_cmd])

        try:
            result = self.device.expect(["assword:", "passphrase", "yes/no"] +
                                        self.device.prompt)
            if result == 2:
                self.device.sendline("yes")
                result = self.device.expect(["assword:", "passphrase"] +
                                            self.device.prompt)
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")
        if result == 0 or result == 1:
            assert (
                self.ssh_password is not None
            ), "Please add ssh_password in your json configuration file."
            self.device.sendline(self.ssh_password)
            self.device.expect(self.device.prompt)

    def close(self):
        """Close the pexpect session to the device.

        :param self: self object
        :type self: object
        """
        self.sendline("exit")
        super(type(self), self).close()
