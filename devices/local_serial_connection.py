import pexpect
import base_connection
from lib.regexlib import telnet_ipv4_conn

class LocalSerialConnection(base_connection.BaseConnection):
    '''
    To use, set conn_cmd in your json to "cu -s <port_speed> -l <path_to_serialport>"
    and set connection_type to "local_serial"

    '''
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        try:
            if super(LocalSerialConnection, self).connect():
                return
            pexpect.spawn.__init__(self.device,
                               command='/bin/bash',
                               args=['-c', self.conn_cmd])
            result = self.device.expect([telnet_ipv4_conn, "----------------------------------------------------"])
        except pexpect.EOF as e:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        if super(LocalSerialConnection, self).close():
            return
        self.device.sendline("~.")
