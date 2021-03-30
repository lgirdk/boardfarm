import functools

from debtcollector import deprecate

from boardfarm.exceptions import CodeError

from .base_devices.fxs_modem import FXSModemTemplate
from .platform.debian import DebianBox


class PythonExecutor:
    """To execute python commands over a pexpect session"""

    def __init__(self, device):
        self.device = device
        self.prompt = ">>>"

        self.run("python3")

    def run(self, cmd, expect=""):
        self.device.sendline(cmd)
        if not expect:
            return self.device.expect(self.prompt)
        else:
            return self.device.expect(expect)

    def exit(self):
        self.device.sendline("exit()")
        self.device.expect(self.device.prompt)


class DebianFXS(FXSModemTemplate, DebianBox):
    """Fax modem."""

    model = "debian_fxs"

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self.own_number = self.kwargs.pop("number")
        self.tcid = self.kwargs.pop("tcid")
        self.line = self.kwargs.pop("line")

        # pexpect session handled by a parent method
        self.parse_device_options(*args, **kwargs)
        if "dev_array" not in kwargs:
            self.legacy_add = True
            self.dev_array = "FXS"

        # verify tty lines
        if not self._tty_line_exists():
            raise CodeError("Device does not have a TTY line to speak to!")

        # NOTE: this will go away with custom Dockerfiles for serial phones
        # moving this out from phone_start method.
        self.sendline("pip3 show pyserial")
        self.expect(self.prompt)
        if "Package(s) not found" in self.before:
            self.sendline("pip install pyserial")
            self.expect(self.prompt)

    def __str__(self):
        return "serialmodem %s" % self.line

    def _tty_line_exists(self):
        """To check if tty dev exists.

        rvalue: TRUE/FALSE
        rtype: Boolean
        """
        self.sendline(f"ls /dev/tty{self.line}")
        self.expect(self.prompt)
        return "No such file or directory" not in self.before

    def _python_console_check(func):
        """Decorator to check python console before execution.

        Note - Only to validate instance methods."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            instance = args[0]
            if hasattr(instance, "py"):
                return func(*args, **kwargs)
            raise CodeError("Function was called without opening python console!")

        return wrapper

    def phone_start(self, baud="115200", timeout="1"):
        """To start the softphone session."""

        self.py = PythonExecutor(self)
        self.py.run("import serial,time")
        self.py.run(
            f"set = serial.Serial('/dev/tty{self.line}', {baud} ,timeout= {timeout})"
        )
        self.py.run("set.write(b'ATZ\\r')")
        self.mta_readlines(search="OK")
        self.py.run("set.write(b'AT\\r')")
        self.mta_readlines(search="OK")
        self.py.run("set.write(b'AT+FCLASS=1\\r')")
        self.mta_readlines(search="OK")

    # maintaining backward compatibility for tests.
    @_python_console_check
    def mta_readlines(self, time="3", search=""):
        """To readlines from serial console."""
        self.py.run("set.flush()")
        self.py.run(f"time.sleep({time})")
        self.py.run("l=set.readlines()")
        self.py.run("print(l)", expect=search)

    # this is bad
    # breaking this down below
    @_python_console_check
    def offhook_onhook(self, hook_value):
        """To generate the offhook/onhook signals."""
        self.py.run(f"set.write(b'ATH{hook_value}\\r')")
        self.mta_readlines(search="OK")

    @_python_console_check
    def on_hook(self):
        self.py.run("set.write(b'ATH0\\r')")
        self.mta_readlines(search="OK")

    @_python_console_check
    def off_hook(self):
        self.py.run("set.write(b'ATH1\\r')")
        self.mta_readlines(search="OK")

    @_python_console_check
    def answer(self):
        """To answer the incoming call."""
        deprecate(
            "Warning!",
            message="answer() is deprecated. Use off_hook() and on_hook() method to answer the calls",
            category=UserWarning,
        )
        self.mta_readlines(time="10", search="RING")
        self.py.run("set.write(b'ATA\\r')")
        self.mta_readlines(search="ATA")

    @_python_console_check
    def dial(self, number, receiver_ip=None):
        """To dial to another number.

        number(str) : number to be called
        receiver_ip(str) : receiver's ip; defaults to none
        """
        self.py.run(f"set.write(b'ATDT{number};\\r')")
        self.mta_readlines(search="ATDT")

    @_python_console_check
    def hangup(self):
        """To hangup the ongoing call."""
        self.py.run("set.write(b'ATH0\\r')")
        self.mta_readlines(search="OK")

    @_python_console_check
    def phone_kill(self):
        """To kill the serial port console session."""
        self.py.run("set.close()")
        self.py.exit()
        delattr(self, "py")

    @_python_console_check
    def validate_state(self, state):
        """Read the mta_line message to validate the call state

        :param state: The call state expected in the MTA line
        :type state: string
        :example usage: validate_state('RING') to verify Ringing state.
        :return: boolean True if success
        :rtype: Boolean
        """
        self.mta_readlines(search=state)
        self.py.run("")
        return True
