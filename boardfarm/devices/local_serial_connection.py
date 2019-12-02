import pexpect
from boardfarm.lib.regexlib import telnet_ipv4_conn
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper

class LocalSerialConnection():
    '''
    To use, set conn_cmd in your json to "cu -s <port_speed> -l <path_to_serialport>"
    and set connection_type to "local_serial"

    '''
    def __init__(self, device=None, conn_cmd=None, **kwargs):
        self.device = device
        self.conn_cmd = conn_cmd

    def connect(self):
        bft_pexpect_helper.spawn.__init__(self.device,
                           command='/bin/bash',
                           args=['-c', self.conn_cmd])
        try:
            self.device.expect([telnet_ipv4_conn, "----------------------------------------------------"])
        except pexpect.EOF:
            raise Exception("Board is in use (connection refused).")

    def close(self):
        self.device.sendline("~.")
