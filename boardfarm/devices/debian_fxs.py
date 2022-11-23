import atexit
import functools
from contextlib import suppress
from time import sleep

from debtcollector import deprecate
from pexpect import TIMEOUT

from boardfarm.exceptions import CodeError
from boardfarm.lib.DeviceManager import get_device_by_name

from .base_devices import fxo_template
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


class DebianFXS(SIPPhoneTemplate, DebianBox):  # type: ignore
    """Fax modem."""

    model = "debian_fxs"
    fxo: fxo_template.FXOTemplate
    call_line1 = None
    call_line2 = None

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self._phone_started = False

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
        if not self.number:
            raise CodeError("Please call register FXS method first!!")

        self._phone_started = True

        board = get_device_by_name("board")
        self.fxo = board.sw.voice
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
    def mta_readlines(self, time: int = 4, search: str = "") -> None:
        """To readlines from serial console."""
        self.py.run("serial_line.flush()")
        sleep(time)
        self.py.run("l=serial_line.readlines()")
        return self.py.run("for i in l: print(i.decode());\n", expect=search)

    # this is bad, maintaining just to support legacy.
    # breaking this down below
    @Checks.is_phone_started
    def offhook_onhook(self, hook_value: int) -> None:
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
        self.off_hook()
        return True

    def _dial(self, number) -> None:
        self.py.run(f"serial_line.write(b'ATD{number};\\r')")
        self.mta_readlines(search="OK")

    @Checks.is_phone_started
    def dial(self, number: str, receiver_ip: str = None) -> None:
        """Execute Hayes ATDT command for dialing a number in FXS modems."""
        deprecate(
            "Warning!",
            message="dial() is deprecated. use call() method to make calls",
            category=UserWarning,
        )
        self._dial(number)

    @Checks.is_phone_started
    def call(self, callee: "SIPPhoneTemplate") -> None:
        """To dial a call to callee.

        :param callee: Device which will act as the caller.
        :type callee: SIPPhoneTemplate
        """
        number = callee.number
        self._dial(number)

    # maintaining backward compatibility for legacy tests.
    @Checks.is_phone_started
    def hangup(self) -> None:
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
    def validate_state(self, state: str) -> bool:
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
    def is_idle(self) -> bool:
        return self.fxo.check_call_state(
            self.fxs_port, self.fxo.states.idle, operator="and"
        )

    @Checks.is_phone_started
    def is_dialing(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.dialing)

    @Checks.is_phone_started
    def is_incall_dialing(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.incall_dialing)

    @Checks.is_phone_started
    def is_ringing(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.ringing)

    @Checks.is_phone_started
    def is_connected(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.connected)

    @Checks.is_phone_started
    def is_incall_connected(self) -> bool:
        return self.fxo.check_call_state(
            self.fxs_port, self.fxo.states.incall_connected
        )

    @Checks.is_phone_started
    def is_onhold(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.on_hold)

    @Checks.is_phone_started
    def is_playing_dialtone(self) -> bool:
        return self.fxo.check_call_state(
            self.fxs_port, self.fxo.states.playing_dialtone
        )

    @Checks.is_phone_started
    def is_call_ended(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.call_ended)

    @Checks.is_phone_started
    def is_code_ended(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.code_ended)

    @Checks.is_phone_started
    def is_call_waiting(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.call_waiting)

    @Checks.is_phone_started
    def is_in_conference(self) -> bool:
        return self.fxo.check_call_state(
            self.fxs_port, self.fxo.states.conference, operator="and"
        )

    @Checks.is_phone_started
    def has_off_hook_warning(self) -> bool:
        return self.fxo.check_call_state(self.fxs_port, self.fxo.states.call_waiting)

    @Checks.is_phone_started
    def is_incall_playing_dialtone(self) -> bool:
        return self.fxo.check_call_state(
            self.fxs_port, self.fxo.states.incall_playing_dialtone
        )

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

    @Checks.is_phone_started
    def answer_waiting_call(self) -> None:
        """Answer the waiting call and hang up on the current call.

        AT Dial (!1) on FXS modem.
        """
        self._dial("!1")

    @Checks.is_phone_started
    def toggle_call(self) -> None:
        """Toggle between the calls.

        Need to first validate, there is an incoming call on other line.
        AT Dial (!2) on FXS modem.
        """
        self._dial("!2")

    @Checks.is_phone_started
    def merge_two_calls(self) -> None:
        """Merge the two calls for conference calling.

        Ensure call waiting must be enabled.
        There must be a call on other line to add to conference.
        AT Dial (!3) on FXS modem.
        """
        self._dial("!3")

    @Checks.is_phone_started
    def reject_waiting_call(self) -> None:
        """Reject a call on waiting on second line.

        This will send the call to voice mail or a busy tone.
        There must be a call on the second line to reject.
        AT Dial (!4) on FXS modem.
        """
        self._dial("!4")

    @Checks.is_phone_started
    def place_call_onhold(self) -> None:
        """Place an ongoing call on-hold.

        There must be an active call to be placed on hold.
        """
        self._dial("!")

    @Checks.is_phone_started
    def place_call_offhold(self) -> None:
        """Place an ongoing call on-hold to off hold.

        There must be an active call to be placed off hold.
        """
        self.press_R_button()

    @Checks.is_phone_started
    def press_R_button(self) -> None:
        """Press the R button.

        Used when we put a call on hold, or during dialing.
        """
        self._dial("!")

    def hook_flash(self) -> None:
        """To perfrom hook flash"""
        self.press_R_button()

    def enable_call_waiting(self) -> None:
        """Enabled the call waiting.

        This will enable call waiting by dialing the desired number
        """
        self._dial("*43#")
        if not self.is_code_ended():
            raise CodeError("Cannot enable call waiting")
        self.on_hook()

    def enable_call_forwarding_busy(self, forward_to: SIPPhoneTemplate) -> None:
        self._dial(f"*67*{forward_to._obj().number}#")
        self.on_hook()

    def disable_call_forwarding_busy(self) -> None:
        self._dial("#67#")
        self.on_hook()

    def disable_call_waiting_overall(self) -> None:
        self._dial("#43#")
        self.on_hook()

    def disable_call_waiting_per_call(self) -> None:
        self._dial("#43*")
        self.on_hook()
