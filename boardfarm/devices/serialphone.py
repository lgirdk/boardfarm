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
        self.profile[self.name] = self.profile.get(self.name, {})
        serialphone_profile = self.profile[self.name] = {}
        serialphone_profile["on_boot"] = self.phone_config

    def __str__(self):
        return "serialmodem %s" % self.line

    def phone_config(self):
        '''
        to configure system link/soft link
        '''
        # to check whether the dev/tty exists-to be added
        self.sendline("ln -s /dev/tty%s  /root/line-%s" % (self.line, self.line))
        self.expect(["File exists"] + self.prompt)
    
    def phone_unconfig(self):
        '''
        to remove the system link
        '''
        self.sendline("rm  /root/line-%s" % self.line)
        self.expect(self.prompt)

    def phone_start(self, baud="115200", timeout="1"):
        '''
        to start the softphone session
        '''
        self.sendline("pip install pyserial")
        self.expect(self.prompt)
        self.sendline("python")
        self.expect(">>>")
        self.sendline("import serial,time")
        self.expect(">>>")
        self.sendline("ser = serial.Serial('/root/line-%s', %s ,timeout= %s)" % (self.line, baud, timeout))
        self.expect(">>>")
        self.sendline("ser.write(b'ATZ\\r')")
        self.expect(">>>")
        self.mta_readlines()
        self.expect("OK")
        self.sendline("ser.write(b'AT\\r')")
        self.expect(">>>")
        self.mta_readlines()
        self.expect("OK")

    def mta_readlines(self, time='3'):
        '''
        to readlines from serial console
        '''
        self.sendline("ser.flush()")
        self.expect(">>>")
        self.sendline("time.sleep(%s)" % time)
        self.expect(">>>")
        self.sendline("l=ser.readlines()")
        self.expect(">>>")
        self.sendline("print(l)")

    def dial(self, number):
        '''
        to dial to another number
        number(str) : number to be called
        '''
        AT = str.encode(number)
        self.sendline("ser.write(b'ATDT%s\\r')" % AT)
        self.expect(">>>")
        self.mta_readlines()
        self.expect("ATDT")

    def answer(self):
        '''
        to answer the incoming call
        '''
        self.mta_readlines(time='10')
        self.expect("RING")
        self.sendline("ser.write(b'ATA\\r')")
        self.expect(">>>")
        self.mta_readlines()
        self.expect("ATA")

    def hangup(self):
        '''
        to hangup the ongoing call
        '''
        self.sendline("ser.write(b'ATH\\r')")
        self.expect(">>>")
        self.mta_readlines()
        self.expect("OK")

    def kill(self):
        '''
        to kill the serial port console session
        '''
        self.sendline('ser.close()')
        self.expect('>>>')
        self.sendline('exit()')
        self.expect(self.prompt)

