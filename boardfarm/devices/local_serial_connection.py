import pexpect
from boardfarm.lib.regexlib import telnet_ipv4_conn
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class LocalSerialConnection():
    """To use, set conn_cmd in your json to "cu -s <port_speed> -l <path_to_serialport>"
       and set connection_type to "local_serial"
    """
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        """Initializes the instance of LocalSerialConnection class

        Parameters initialized will later be used to connect to a device
        serially via a COM/TTY port

        :param device: device to connect, defaults to None
        :type device: object
        :param conn_cmd: conn_cmd to connect to device, defaults to None
        :type conn_cmd: string
        :param **kwargs: args to be used
        :type **kwargs: dict
        """
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        """Initializes a pexpect session using the serial command
        Command can be a screen/cu command to connect to a TTY/COM port.

        :raises: Exception Board is in use (connection refused).
        """
        bft_pexpect_helper.spawn.__init__(self.device,
                                          command='/bin/bash',
                                          args=['-c', self.conn_cmd])
        try:
            self.device.expect([
                telnet_ipv4_conn,
                "----------------------------------------------------"
            ])
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        """closes the pexpect session to the device
        """
        self.device.sendline("~.")
