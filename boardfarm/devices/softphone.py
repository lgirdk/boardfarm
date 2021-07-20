"""Class functions related to softphone software."""
import functools
from contextlib import suppress

import pexpect
from debtcollector import deprecate
from pexpect import TIMEOUT

from boardfarm.exceptions import CodeError
from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import install_pjsua

from .base_devices.sip_template import SIPPhoneTemplate


class Checks:
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
    profile = {}

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        # to ensure all calls go via SIP server IP address
        # will be set once phone_config is called.
        self._proxy_ip = None
        self._phone_started = False
        self._phone_configured = False

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

    def __str__(self):
        """Magic method to return a printable string."""
        return "softphone"

    def install_softphone(self):
        """Install softphone from local url or from internet."""
        self.prefer_ipv4()
        install_pjsua(self, getattr(self, "pjsip_local_url", None))

    def phone_config(self, sipserver_ip):
        """Configure the soft phone.

        Arguments:
        sipserver_ip(str): ip of sip server
        """
        if self._phone_configured:
            return

        conf = (
            """(
        echo --local-port="""
            + self.num_port
            + """
        echo --id=sip:"""
            + self.own_number
            + """@"""
            + sipserver_ip
            + """
        echo --registrar=sip:"""
            + sipserver_ip
            + """
        echo --realm=*
        echo --username="""
            + self.own_number
            + """
        echo --password=1234
        echo --null-audio
        echo --max-calls=1
        echo --auto-answer=180
        )> """
            + self.config_name
        )
        self.sendline(conf)
        self.expect(self.prompt)
        self._proxy_ip = sipserver_ip

    def phone_start(self):
        """Start the soft phone.

        Note: Start softphone only when asterisk server is running to avoid failure
        """
        if not self._proxy_ip:
            raise CodeError("Please configure softphone first!!")
        if self._phone_started:
            return
        else:
            try:
                self.sendline("pjsua --config-file=" + self.config_name)
                self.expect(r"registration success, status=200 \(OK\)")
                self.sendline("\n")
                self.expect(self.pjsip_prompt)
                self._phone_started = True
            except TIMEOUT as e:
                self._phone_started = False
                raise CodeError(f"Failed to start Phone!!\nReason{e}")

    @Checks.is_phone_started
    def dial(self, number: str, receiver_ip: str = None) -> None:
        """To dial a number via receiver ip."""
        deprecate(
            "Warning!",
            message="dial() is deprecated. use call() method to make calls",
            category=UserWarning,
        )
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("m")
        self.expect(r"Make call\:")
        self.sendline("sip:" + number + "@" + receiver_ip)
        self.expect("Call [0-9]* state changed to CALLING")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def call(self, callee: SIPPhoneTemplate):
        """To dial a call to callee.

        :param callee: Device which will act as the caller.
        :type callee: SIPPhoneTemplate
        """
        dial_number = callee.number
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("m")
        self.expect(r"Make call\:")
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
    def hangup(self):
        """To hangup the ongoing call."""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("h")
        self.expect(["DISCON", "No current call"])
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def reinvite(self):
        """To re-trigger the Invite message"""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("v")
        self.expect("Sending re-INVITE on call [0-9]*")
        self.expect("SDP negotiation done: Success")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def hold(self):
        """To hold the current call"""
        self.sendline("\n")
        self.expect(self.pjsip_prompt)
        self.sendline("H")
        self.expect("Putting call [0-9]* on hold")
        self.sendline("\n")
        self.expect(self.pjsip_prompt)

    @Checks.is_phone_started
    def phone_kill(self):
        """To kill the pjsip session."""
        # De-Registration is required before quit a phone and q will handle it
        self.sendline("q")
        self.expect(self.prompt)
        self._phone_started = False

    def validate_state(self, msg):
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

    @Checks.is_phone_started
    def on_hook(self):
        self.hangup()

    @Checks.is_phone_started
    def off_hook(self):
        self.answer()

    @Checks.is_phone_started
    def is_ringing(self) -> bool:
        return self.validate_state("180 Ringing")

    @Checks.is_phone_started
    def is_connected(self) -> bool:
        return self.validate_state("CONFIRMED")

    @Checks.is_phone_started
    def detect_dialtone(self):
        # TODO: need to be implemented!!
        return True

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
