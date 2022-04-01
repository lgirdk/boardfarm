"""Class functions related to softphone software."""
import functools
from contextlib import suppress
from itertools import cycle

import pexpect
from debtcollector import deprecate
from pexpect import TIMEOUT

from boardfarm.exceptions import CodeError
from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import install_pjsua

from .base_devices.sip_template import SIPPhoneTemplate


class Checks:
    """Wrappers for various softphone checks."""

    @classmethod
    def is_phone_started(cls, func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self._phone_started:
                raise CodeError("Please start the phone first!!")
            return func(self, *args, **kwargs)

        return wrapper


class SoftPhone(SIPPhoneTemplate):
    """Perform Functions related to softphone software."""

    model = "pjsip"
    profile: dict = {}
    check_on_board = False
    supported_lines = cycle([1])

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        # to ensure all calls go via SIP server IP address
        # will be set once phone_config is called.
        self._proxy_ip = None
        self._phone_started = False
        self._phone_configured = False
        self._active_line = next(self.supported_lines)

        self.own_number = self.kwargs.get("number", "3000")
        self.num_port = self.kwargs.get("num_port", "5060")
        self.config_name = "pjsip.conf"
        self.pjsip_local_url = kwargs.get("local_site", None)
        self.pjsip_prompt = ">>>"
        self.profile[self.name] = self.profile.get(self.name, {})
        softphone_profile = self.profile[self.name] = {}
        softphone_profile["on_boot"] = self.install_softphone
        self.dns = DNS(self, kwargs.get("options", {}), kwargs.get("aux_ip", {}))

        if "dev_array" not in kwargs:
            self.legacy_add = True
            self.dev_array = "softphones"

    @property
    def active_line(self) -> int:
        return self._active_line

    def __str__(self):
        """Magic method to return a printable string."""
        return "softphone"

    def install_softphone(self) -> None:
        """Install softphone from local url or from internet."""
        self.prefer_ipv4()
        install_pjsua(self, getattr(self, "pjsip_local_url", None))

    def phone_config(self, sipserver_ip: str) -> None:
        """Configure the soft phone.

        Arguments:
        sipserver_ip(str): ip of sip server
        """

        conf = f"""--local-port={self.num_port}
--id=sip:{self.own_number}@{sipserver_ip}
--registrar=sip:{sipserver_ip}
--realm=*
--username={self.own_number}
--password=1234
--null-audio
--max-calls=1
--auto-answer=180
--no-tcp"""

        self.sendline("\n")
        id = self.expect([self.pjsip_prompt] + self.prompt)
        if id == 0:
            # come out of pjsip prompt
            self.sendcontrol("c")
            self.expect(self.prompt)
        try:
            # check for the existing configuration
            self.sendline(f"cat {self.config_name}")
            self.expect(self.prompt)
            self._phone_configured = conf in self.before.replace("\r", "")
        except TIMEOUT:
            self._phone_configured = False

        if not self._phone_configured:
            conf_cmd = f"cat >{self.config_name}<<EOF\n{conf}\nEOF\n"
            self.sendline(conf_cmd)
            self.expect(self.prompt)
            self._phone_configured = True
        self._proxy_ip = sipserver_ip

    def phone_start(self) -> None:
        """Start the soft phone.

        Note: Start softphone only when asterisk server is running to avoid failure
        """
        if not self._proxy_ip or not self._phone_configured:
            raise CodeError("Please configure softphone first!!")
        try:
            # check if the phone is already started
            self.sendline("\n")
            self.expect(self.pjsip_prompt, timeout=2)
            self._phone_started = True
            return
        except TIMEOUT:
            try:
                self.sendline("pjsua --config-file=" + self.config_name)
                self.expect(r"registration success, status=200 \(OK\)")
                self.sendline("\n")
                self.expect(self.pjsip_prompt)
                self._phone_started = True
            except TIMEOUT as e:
                self._phone_started = False
                raise CodeError(f"Failed to start Phone!!\nReason{e}")

    def _select_option_make_call(self):
        """Selects the option to make a call on softphone menu"""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("m")
        self.expect(r"Make call\:")

    @Checks.is_phone_started
    def dial(self, number: str, receiver_ip: str = None) -> None:
        """To dial a number via receiver ip."""
        deprecate(
            "Warning!",
            message="dial() is deprecated. use call() method to make calls",
            category=UserWarning,
        )
        self._select_option_make_call()
        self.sendline("sip:" + number + "@" + receiver_ip)
        self.expect("Call [0-9]* state changed to CALLING")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def call(self, callee: SIPPhoneTemplate) -> None:
        """To dial a call to callee.

        :param callee: Device which will act as the caller.
        :type callee: SIPPhoneTemplate
        """
        self._select_option_make_call()
        dial_number = callee.number
        self.sendline("sip:" + dial_number + "@" + self._proxy_ip)
        self.expect("Call [0-9]* state changed to CALLING")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def answer(self) -> bool:
        """To answer the incoming call in soft phone."""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("a")
        idx = self.expect(
            [
                r"Answer with code \(100\-699\) \(empty to cancel\)\:",
                "No pending incoming call",
            ]
        )
        if idx == 1:
            return False
        self.sendline("200")
        self.expect("Call [0-9]* state changed to CONFIRMED")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        return True

    @Checks.is_phone_started
    def hangup(self) -> None:
        """To hangup the ongoing call."""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("h")
        self.expect(["DISCON", "No current call"])
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def reinvite(self) -> None:
        """To re-trigger the Invite message"""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("v")
        self.expect("Sending re-INVITE on call [0-9]*")
        self.expect("SDP negotiation done: Success")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def place_call_offhold(self) -> None:
        """To place call off hold and thus reinvites the call on hold"""
        self.reinvite()

    @Checks.is_phone_started
    def hold(self) -> None:
        """To hold the current call"""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("H")
        self.expect("Putting call [0-9]* on hold")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def phone_kill(self) -> None:
        """To kill the pjsip session."""
        # De-Registration is required before quit a phone and q will handle it
        self.sendline("q")
        self.expect(self.prompt)
        self._phone_started = False

    def validate_state(self, msg: str) -> bool:
        """Verify the message to validate the status of the call

        :param msg: The message to expect on the softphone container
        :type msg: string
        :example usage:
           validate_state('INCOMING') to validate an incoming call.
           validate_state('Current call id=<call_id> to <sip_uri> [CONFIRMED]') to validate call connected.
        :return: boolean True if success
        :rtype: Boolean
        """
        out = False
        with suppress(pexpect.TIMEOUT):
            self.sendline("\n")
            self.expect(self.pjsip_prompt)
            if msg == "INCOMING":
                msg = "180 Ringing"
            self.expect(msg)
            self.expect(self.pjsip_prompt)
            out = True
        return out

    def _send_update_and_validate(self, msg: str) -> bool:
        with suppress(pexpect.TIMEOUT):
            self.sendline("\n")
            self.expect(self.pjsip_prompt)
            self.sendline("U")
            self.expect(msg)
            self.sendline("\n")
            self.expect(self.pjsip_prompt)
            return True
        return False

    @Checks.is_phone_started
    def on_hook(self) -> None:
        self.hangup()

    @Checks.is_phone_started
    def off_hook(self) -> None:
        self.answer()

    @Checks.is_phone_started
    def is_idle(self) -> bool:
        return self.validate_state("You have 0 active call")

    @Checks.is_phone_started
    def is_dialing(self) -> bool:
        return self.validate_state(
            rf"You have 1 active call.*Current call id=[0-9]* to sip:[0-9]*@{self._proxy_ip} \[EARLY\]"
        )

    @Checks.is_phone_started
    def is_incall_dialing(self) -> bool:
        # This is not supported, added here to provide compatibility with FXS phones
        return self.is_connected()

    @Checks.is_phone_started
    def is_ringing(self) -> bool:
        return self.validate_state("180 Ringing")

    @Checks.is_phone_started
    def is_connected(self) -> bool:
        return self.validate_state("CONFIRMED")

    @Checks.is_phone_started
    def is_incall_connected(self) -> bool:
        # This is not supported, added here to provide compatibility with FXS phones
        return self.is_connected()

    @Checks.is_phone_started
    def is_onhold(self) -> bool:
        return self._send_update_and_validate(
            r"PCMU \(sendonly\).*\[type=audio\], status is Local hold"
        )

    @Checks.is_phone_started
    def is_playing_dialtone(self) -> bool:
        return self._send_update_and_validate("No current call")

    @Checks.is_phone_started
    def is_incall_playing_dialtone(self) -> bool:
        raise NotImplementedError("Unsupported")

    @Checks.is_phone_started
    def is_call_ended(self) -> bool:
        self.sendline("\n")
        # Call should be disconnected as the call hangup by other user
        self.expect("You have 0 active call")
        out = "DISCONNECTED [reason=200 (Normal call clearing)]" in self.before
        self.expect(self.pjsip_prompt)
        return out

    @Checks.is_phone_started
    def is_code_ended(self) -> bool:
        with suppress(pexpect.TIMEOUT):
            self.sendline("\n")
            self.expect(self.pjsip_prompt)
            self.expect(r"Closing sound device after idle for [0-9]* second\(s\)")
            self.sendline("\n")
            self.expect(self.pjsip_prompt)
            return True
        return False

    @Checks.is_phone_started
    def is_call_waiting(self) -> bool:
        return self.validate_state(r"Incoming call for account [0-9]*")

    @Checks.is_phone_started
    def is_in_conference(self) -> bool:
        raise NotImplementedError("Unsupported")

    @Checks.is_phone_started
    def has_off_hook_warning(self) -> bool:
        raise NotImplementedError("Unsupported")

    @Checks.is_phone_started
    def detect_dialtone(self) -> bool:
        return self.is_playing_dialtone()

    @property
    def number(self):
        return self.own_number

    @Checks.is_phone_started
    def reply_with_code(self, code) -> None:
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("a")
        idx = self.expect(
            [
                r"Answer with code \(100\-699\) \(empty to cancel\)\:",
                "No pending incoming call",
            ]
        )
        if idx == 1:
            raise CodeError("No incoming call to reply to!!")
        self.sendline(f"{code}")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        :return: True if line is busy, else False
        :rtype: bool
        """
        self.sendline("\n")
        # Call should be disconnected due to callee being BUSY
        # If we do not see the prompt menu, something went wrong
        self.expect("You have 0 active call")
        out = "DISCONNECTED [reason=486 (Busy Here)]" in self.before
        self.expect(self.pjsip_prompt)
        return out

    @Checks.is_phone_started
    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered

        :return: True if not answered, else False
        :rtype: bool
        """
        self.sendline("\n")
        # Call should be disconnected due to not getting answered
        # If we do not see the prompt menu, something went wrong
        self.expect("You have 0 active call")
        out = "DISCONNECTED [reason=408 (Request Timeout)]" in self.before
        self.expect(self.pjsip_prompt)
        return out

    def answer_waiting_call(self) -> None:
        """Answer the waiting call and hang up on the current call."""
        raise NotImplementedError("Unsupported")

    def toggle_call(self) -> None:
        """Toggle between the calls.

        Need to first validate, there is an incoming call on other line.
        """
        raise NotImplementedError("Unsupported")

    def merge_two_calls(self) -> None:
        """Merge the two calls for conference calling.

        Ensure call waiting must be enabled.
        There must be a call on other line to add to conference.
        """
        raise NotImplementedError("Unsupported")

    def reject_waiting_call(self) -> None:
        """Reject a call on waiting on second line.

        This will send the call to voice mail or a busy tone.
        There must be a call on the second line to reject.
        """
        raise NotImplementedError("Unsupported")

    def place_call_onhold(self) -> None:
        """Place an ongoing call on-hold.

        There must be an active call to be placed on hold.
        """
        self.hold()

    def press_R_button(self) -> None:
        """Press the R button.

        Used when we put a call on hold, or during dialing.
        """
        self.hold()

    def hook_flash(self) -> None:
        """To perfrom hook flash"""
        self.press_R_button()

    def _dial_feature_code(self, code: str):
        """Selects the option to make a call and then sends the desired feature code to the sipcenter

        :param code: code to be send as a request for a feature
        :type code: str
        :raises CodeError: Raises this error when call is not ended after dialing the code
        """
        self._select_option_make_call()
        self.sendline(f"sip:{code}@{self._proxy_ip}")
        self.expect("Call [0-9]* state changed to CALLING")
        if not self.is_code_ended():
            raise CodeError(f"Call not ended after dialing a feature code: {code}")

    def enable_call_waiting(self) -> None:
        self._dial_feature_code("*42#")

    def enable_call_forwarding_busy(self, forward_to: SIPPhoneTemplate) -> None:
        code = f"*67*{forward_to.number}#"
        self._dial_feature_code(code)

    def disable_call_forwarding_busy(self) -> None:
        self._dial_feature_code("#67#")

    def disable_call_waiting_overall(self) -> None:
        self._dial_feature_code("#43#")

    def disable_call_waiting_per_call(self) -> None:
        self._dial_feature_code("#43*")
