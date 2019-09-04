import pexpect

class SyslogServer(object):
    '''
    Linux based syslog server
    '''

    model = ('syslog')
    profile = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.syslog_ip = self.kwargs['ipaddr']
        self.syslog_name = self.kwargs['username']
        self.syslog_pwd = self.kwargs['password']

    def read_syslog(self, ip_address, msg_length=10):
        self.sendline("tail -f -n %s /var/log/BF/log_%s" % (msg_length, ip_address))
        self.expect(pexpect.TIMEOUT, timeout=4)
        self.sendcontrol('c')
        self.expect(self.prompt)
        return self.before
