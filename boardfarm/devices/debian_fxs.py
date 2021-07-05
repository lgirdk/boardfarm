import atexit
import functools
from contextlib import suppress
from time import sleep

from debtcollector import deprecate
from pexpect import TIMEOUT

from boardfarm.exceptions import CodeError

from .base_devices.sip_template import SIPPhoneTemplate
from .platform.debian import DebianBox


class PythonExecutor:
    """To execute python commands over a pexpect session"""

    def __init__(self, device):
        self.device = device
        self.py_prompt = ">>>"

        self.device.check_output("kill -9 $(pgrep python3)")
        self.run("python3")

    def run(self, cmd, expect=""):
        self.device.sendline(cmd)
        if not expect:
            self.device.expect(self.py_prompt)
            out = self.device.before
        else:
            self.device.expect(expect)
            out = self.device.before
            self.device.expect(self.py_prompt)

        if "Traceback" in out:
            raise CodeError(
                "Failed to execute on python console command:"
                + f"\n{cmd}\nOutput:{out}"
            )

        return out

    def exit(self):
        with suppress(TIMEOUT):
            self.device.sendcontrol("c")
            self.device.expect(self.py_prompt)
            self.device.sendcontrol("d")
            self.device.expect(self.device.prompt)


class Checks:
    @classmethod
    def is_phone_started(cls, func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self._phone_started:
                raise CodeError("Please start the phone first!!")
            return func(self, *args, **kwargs)

        return wrapper


class DebianFXS(SIPPhoneTemplate, DebianBox):
    """Fax modem."""

    model = "debian_fxs"

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self._phone_started = False
        self._connected = False

        # legacy approach specify TCID, Serial Line via INV JSON
        self.own_number = self.kwargs.get("number")
        self.tcid = self.kwargs.get("tcid")
        self.line = self.kwargs.get("line")

        self.usb_port = self.kwargs.get("usb_port")
        self.fxs_port = self.kwargs.get("fxs_port")

        if not (self.line or self.usb_port):
            raise CodeError("Please provide either a TTY Line or USB port")
        if not (self.own_number or self.fxs_port):
            raise CodeError("Please provide either a FXS EP or Phone number")

        # pexpect session handled by a parent method
        self.parse_device_options(*args, **kwargs)
        if "dev_array" not in kwargs:
            self.legacy_add = True
            self.dev_array = "FXS"

        # if usb_port exists: fetch tty line from /sys filesystem
        # else validate if the tty line provided by kwargs exists
        if self.usb_port:
            self.line = self.check_output(
                f"ls /sys/bus/usb/devices/{self.usb_port}:1.0/tty"
            )
            if not self.line:
                raise CodeError(
                    f"Failed to find Serial Line for USB port - {self.usb_port}"
                )
        elif not self._tty_line_exists():
            raise CodeError("Device does not have a TTY line to speak to!")

        self.py = PythonExecutor(self)
        atexit.register(self.close)

    def __str__(self):
        return f"FXS Phone {self.name}/{self.usb_port}/{self.fxs_port}"

    @property
    def number(self):
        return self.own_number

    def close(self):
        if self._phone_started:
            self.phone_kill()
        self.py.exit()

    def _tty_line_exists(self):
        """To check if tty dev exists.

        rvalue: TRUE/FALSE
        rtype: Boolean
        """
        self.line = f"tty{self.line}"
        self.sendline(f"ls /dev/{self.line}")
        self.expect(self.prompt)
        return "No such file or directory" not in self.before

    def phone_config(self, sip_server: str = "") -> None:
        super().phone_config(sip_server)

    def phone_start(self) -> None:
        """To start the softphone session."""
        self._phone_started = True
        try:
            self.py.run("import serial")
            self.py.run(
                f"serial_line = serial.Serial('/dev/{self.line}', 115200 ,timeout=1)"
            )
            self.py.run("serial_line.write(b'ATZ\\r')")
            self.mta_readlines(search="OK")
            self.py.run("serial_line.write(b'AT+FCLASS=1\\r')")
            self.mta_readlines(search="OK")
            self.py.run("serial_line.write(b'ATV1\\r')")
            self.mta_readlines(search="OK")
            self.py.run("serial_line.write(b'ATX4\\r')")
            self.mta_readlines(search="OK")
            self.py.run("serial_line.write(b'AT-STE=7\\r')")
            self.mta_readlines(search="OK")
        except TIMEOUT as e:
            self._phone_started = False
            raise CodeError(f"Failed to start Phone!!\nReason{e}")

    # maintaining backward compatibility for legacy tests.
    @Checks.is_phone_started
    def mta_readlines(self, time=4, search=""):
        """To readlines from serial console."""
        self.py.run("serial_line.flush()")
        sleep(time)
        self.py.run("l=serial_line.readlines()")
        return self.py.run("for i in l: print(i.decode());\n", expect=search)

    # this is bad, maintaining just to support legacy.
    # breaking this down below
    @Checks.is_phone_started
    def offhook_onhook(self, hook_value):
        """To generate the offhook/onhook signals."""
        self.py.run(f"serial_line.write(b'ATH{hook_value}\\r')")
        self.mta_readlines(search="OK")

    @Checks.is_phone_started
    def on_hook(self) -> None:
        """Execute on_hook procedure to disconnect to a line.

        On hook. Hangs up the phone, ending any call in progress.
        Need to send ATH0 command over FXS modem
        """
        self.py.run("serial_line.write(b'ATH0\\r')")
        self.mta_readlines(time=5, search="OK")
        self._connected = False

    @Checks.is_phone_started
    def off_hook(self) -> None:
        """Execute off_hook procedure to connect to a line.

        Off hook. Picks up the phone line (typically you'll hear a dialtone)
        Need to send ATH1 command over FXS modem
        """
        self.py.run("serial_line.write(b'ATH1\\r')")
        self.mta_readlines(search="OK")

    @Checks.is_phone_started
    def answer(self) -> bool:
        """To answer a call on RING state.

        Answer. Picks up the phone line and answer the call manually.
        Need to send ATA command over FXS modem
        """
        self.py.run("serial_line.write(b'ATA\\r')")
        self.mta_readlines(search="CONNECT")
        self._connected = True
        self.mta_readlines(search="OK")
        return True

    @Checks.is_phone_started
    def dial(self, number: str, receiver_ip: str = None) -> None:
        """Execute Hayes ATDT command for dialing a number in FXS modems."""
        deprecate(
            "Warning!",
            message="dial() is deprecated. use call() method to make calls",
            category=UserWarning,
        )
        self.py.run(f"serial_line.write(b'ATD{number}\\r')")
        self.mta_readlines(search="ATD")

    @Checks.is_phone_started
    def call(self, callee: "SIPPhoneTemplate") -> None:
        """To dial a call to callee.

        :param callee: Device which will act as the caller.
        :type callee: SIPPhoneTemplate
        """
        number = callee.number
        self.py.run(f"serial_line.write(b'ATD{number}\\r')")
        self.mta_readlines(search="ATD")

    # maintaining backward compatibility for legacy tests.
    @Checks.is_phone_started
    def hangup(self):
        """To hangup the ongoing call."""
        deprecate(
            "Warning!",
            message="hangup() is deprecated. use on_hook() method to hangup the calls",
            category=UserWarning,
        )
        self.on_hook()

    @Checks.is_phone_started
    def phone_kill(self) -> None:
        """To kill the serial port console session."""
        self.py.run("serial_line.close()")
        self._phone_started = False

    @Checks.is_phone_started
    def validate_state(self, state):
        """Read the mta_line message to validate the call state

        :param state: The call state expected in the MTA line
        :type state: string
        :example usage: validate_state('RING') to verify Ringing state.
        :return: boolean True if success
        :rtype: Boolean
        """
        out = False
        with suppress(TIMEOUT):
            self.mta_readlines(search=state)
            self.py.run("")
            out = True
        return out

    @Checks.is_phone_started
    def is_ringing(self) -> bool:
        return self.validate_state("RING")

    @Checks.is_phone_started
    def is_connected(self) -> bool:
        return self._connected

    @Checks.is_phone_started
    def detect_dialtone(self) -> bool:
        with suppress(TIMEOUT) as out:
            # ATDW ensures to first wait for a dialtone.
            self.py.run("serial_line.write(b'ATDW;\\r')")
            # IF RESULT CODE OK is received dial tone was detected
            self.mta_readlines(search="OK")
            out = True
        return out is not None

    @Checks.is_phone_started
    def reply_with_code(self, code: int) -> None:
        """Not required in case of FXS phones.

        .. note::
            - Maintaining it due to abstract base template.
        """

    @Checks.is_phone_started
    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        :return: True if line is busy, else False
        :rtype: bool
        """
        return self.validate_state("BUSY")

    @Checks.is_phone_started
    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered

        :return: True if not answered, else False
        :rtype: bool
        """
        return self.validate_state("NO CARRIER")
