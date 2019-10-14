class SerialPhone(object):
    '''
    Fax modem
    '''

    model = ('serialmodem')
    profile = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.line = self.kwargs.get("line")
        self.profile["on_boot"] = self.phone_config

    def __str__(self):
        return "serialmodem %s"% self.line

    def phone_config(self):
        '''
        to configure system link/soft link
        '''
        self.sendline("ln -s /dev/tty%s  /root/line-%s" % (self.line,self.line))
        self.expect(["File exists"] + self.prompt)
    
    def phone_unconfig(self):
        '''
        to remove the system link
        '''
        self.sendline("rm  /root/line-%s" % self.line)
        self.expect(self.prompt)

