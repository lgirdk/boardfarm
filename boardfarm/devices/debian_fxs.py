import atexit
from contextlib import suppress

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


class DebianFXS(SIPPhoneTemplate, DebianBox):
    """Fax modem."""

    model = "debian_fxs"

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs

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
        return f"FXS Phone {self.name}/{self.usb_port}/{self.fxs_ep}"

    @property
    def number(self):
        return self.own_number

    def close(self):
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

    def phone_config(self, sipserver):
        super().phone_config(sipserver)

    def phone_start(self, baud="115200", timeout="1"):
        """To start the softphone session."""
        self.py.run("import serial,time")
        self.py.run(
            f"serial_line = serial.Serial('/dev/{self.line}', {baud} ,timeout= {timeout})"
        )
        self.py.run("serial_line.write(b'ATZ\\r')")
        self.mta_readlines(search="OK")
        self.py.run("serial_line.write(b'AT\\r')")
        self.mta_readlines(search="OK")
        self.py.run("serial_line.write(b'AT+FCLASS=1\\r')")
        self.mta_readlines(search="OK")

    # maintaining backward compatibility for legacy tests.
    def mta_readlines(self, time="3", search=""):
        """To readlines from serial console."""
        self.py.run("serial_line.flush()")
        self.py.run(f"time.sleep({time})")
        self.py.run("l=serial_line.readlines()")
        self.py.run("print(l)", expect=search)

    # this is bad, maintaining just to support legacy.
    # breaking this down below
    def offhook_onhook(self, hook_value):
        """To generate the offhook/onhook signals."""
        self.py.run(f"serial_line.write(b'ATH{hook_value}\\r')")
        self.mta_readlines(search="OK")

    def on_hook(self):
        """Execute on_hook procedure to disconnect to a line.

        On hook. Hangs up the phone, ending any call in progress.
        Need to send ATH0 command over FXS modem
        """
        self.py.run("serial_line.write(b'ATH0\\r')")
        self.mta_readlines(search="OK")

    def off_hook(self):
        """Execute off_hook procedure to connect to a line.

        Off hook. Picks up the phone line (typically you'll hear a dialtone)
        Need to send ATH1 command over FXS modem
        """
        self.py.run("serial_line.write(b'ATH1\\r')")
        self.mta_readlines(search="OK")

    def answer(self):
        """To answer a call on RING state.

        Answer. Picks up the phone line and answer the call manually.
        Need to send ATA command over FXS modem
        """
        self.mta_readlines(time="10", search="RING")
        self.py.run("serial_line.write(b'ATA\\r')")
        self.mta_readlines(search="ATA")

    def dial(self, number, receiver_ip=None):
        """To dial to another number.

        number(str) : number to be called
        receiver_ip(str) : receiver's ip; defaults to none
        """
        self.py.run(f"serial_line.write(b'ATDT{number};\\r')")
        self.mta_readlines(search="ATDT")

    # maintaining backward compatibility for legacy tests.
    def hangup(self):
        """To hangup the ongoing call."""
        deprecate(
            "Warning!",
            message="hangup() is deprecated. use on_hook() method to hangup the calls",
            category=UserWarning,
        )
        self.on_hook()

    def phone_kill(self):
        """To kill the serial port console session."""
        self.py.run("serial_line.close()")

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
