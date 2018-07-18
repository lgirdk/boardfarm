
import sys
import base
import connection_decider

class WindowsTelnet(base.BaseDevice):

    model = ('windows-telnet')
    # This prompt regex could use more work
    prompt = ['[a-zA-Z]:\\\\.*>$']

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.ip = self.kwargs['ipaddr']
        self.username = self.kwargs.get('username', 'Administrator')
        self.password = self.kwargs.get('password', 'bigfoot1')

        conn_cmd = "telnet %s" % self.ip

        self.connection = connection_decider.connection("local_cmd", device=self, conn_cmd=conn_cmd)
        self.connection.connect()
        self.logfile_read = sys.stdout
        self.linesep = '\r'

        self.expect('login: ')
        self.sendline(self.username)
        self.expect('password: ')
        self.sendline(self.password)
        self.expect(self.prompt)

        # Hide login prints, resume after that's done
