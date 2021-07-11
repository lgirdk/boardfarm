import re
from functools import wraps

from debtcollector import deprecate

from boardfarm.exceptions import CodeError


class SerialPhone(object):
    """Fax modem."""

    model = "serialmodem"
    profile = {}

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self.own_number = self.kwargs.get("number", None)
        self.tcid = self.kwargs.get("tcid", None)
        self.line = self.kwargs.get("line")
        self.profile[self.name] = self.profile.get(self.name, {})
        serialphone_profile = self.profile[self.name] = {}
        serialphone_profile["on_boot"] = self.phone_config

    def __str__(self):
        return f"serialmodem {self.line}"

    class PyHandler:
        @classmethod
        def exit_python_on_exception(cls, func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    print(
                        "Python Execution Failed!\n", "Bailing out of Python Console!!"
                    )
                    d = args[0]
                    d.sendcontrol("c")
                    d.sendcontrol("d")
                    d.expect_prompt()

            return wrapper

    def pyexpect(self, *args, **kwargs):
        self.expect(*args, **kwargs)
        if "Traceback" in self.before:
            raise CodeError(f"Python command Failed.Output :\n{self.before}")

    def check_tty(self):
        """To check if tty dev exists.

        rvalue: TRUE/FALSE
        rtype: Boolean
        """
        self.sendline(f"find /dev/tty{self.line}")
        self.expect(self.prompt)
        return bool(
            re.search(
                (r" find /dev/tty%s\r\n/dev/tty%s\r\n" % (self.line, self.line)),
                self.before,
            )
        )

    def phone_config(self):
        """To configure system link/soft link."""
        # to check whether the dev/tty exists-to be added
        self.sendline(f"ln -s /dev/tty{self.line}  /root/line-{self.line}")
        self.expect(["File exists"] + self.prompt)

    def phone_unconfig(self):
        """To remove the system link."""
        self.sendline(f"rm  /root/line-{self.line}")
        self.expect(self.prompt)

    @PyHandler.exit_python_on_exception
    def phone_start(self, baud="115200", timeout="1"):
        """To start the softphone session."""
        self.sendline("python")
        self.pyexpect(">>>")
        self.sendline("import serial,time")
        self.pyexpect(">>>")
        self.sendline(
            "serial_line = serial.Serial('/root/line-%s', %s ,timeout= %s)"
            % (self.line, baud, timeout)
        )
        self.pyexpect(">>>")
        self.sendline("serial_line.write(b'ATZ\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("OK")
        self.sendline("serial_line.write(b'AT\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("OK")
        self.sendline("serial_line.write(b'AT+FCLASS=1\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("OK")

    @PyHandler.exit_python_on_exception
    def mta_readlines(self, time="3"):
        """To readlines from serial console."""
        self.sendline("serial_line.flush()")
        self.pyexpect(">>>")
        self.sendline(f"time.sleep({time})")
        self.pyexpect(">>>")
        self.sendline("l=serial_line.readlines()")
        self.pyexpect(">>>")
        self.sendline("print(l)")

    @PyHandler.exit_python_on_exception
    def offhook_onhook(self, hook_value):
        """To generate the offhook/onhook signals."""
        self.sendline(f"serial_line.write(b'ATH{hook_value}\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("OK")

    @PyHandler.exit_python_on_exception
    def dial(self, number, receiver_ip=None):
        """To dial to another number.

        number(str) : number to be called
        receiver_ip(str) : receiver's ip; defaults to none
        """
        self.sendline(f"serial_line.write(b'ATDT{number};\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("ATDT")

    @PyHandler.exit_python_on_exception
    def answer(self):
        """To answer the incoming call."""
        deprecate(
            "Warning!",
            message="answer() is deprecated. Use offhook_onhook() method to answer the calls",
            category=UserWarning,
        )
        self.mta_readlines(time="10")
        self.expect("RING")
        self.sendline("serial_line.write(b'ATA\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("ATA")

    @PyHandler.exit_python_on_exception
    def hangup(self):
        """To hangup the ongoing call."""
        self.sendline("serial_line.write(b'ATH0\\r')")
        self.pyexpect(">>>")
        self.mta_readlines()
        self.expect("OK")

    @PyHandler.exit_python_on_exception
    def phone_kill(self):
        """To kill the serial port console session."""
        self.sendline("serial_line.close()")
        self.pyexpect(">>>")
        self.sendline("exit()")
        self.expect(self.prompt)

    @PyHandler.exit_python_on_exception
    def validate_state(self, state):
        """Read the mta_line message to validate the call state

        :param state: The call state expected in the MTA line
        :type state: string
        :example usage: validate_state('RING') to verify Ringing state.
        :return: boolean True if success
        :rtype: Boolean
        """
        self.mta_readlines()
        self.expect(state)
        self.sendline()
        self.pyexpect(">>>")
        return True
