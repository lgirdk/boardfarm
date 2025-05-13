# ruff: noqa: EM102,TRY003,D401,EM101,RUF005,SIM102,PGH003,FA100,TRY300,RUF100

"""PJSIPPhone device module."""

import logging
from argparse import Namespace
from contextlib import suppress
from ipaddress import IPv4Interface, IPv6Interface
from itertools import cycle
from typing import Any, Optional

import pexpect
from pexpect import TIMEOUT

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices.linux_device import LinuxDevice
from boardfarm3.exceptions import NotSupportedError, VoiceError
from boardfarm3.lib.device_manager import DeviceManager, get_device_manager
from boardfarm3.templates.sip_phone import SIPPhone as SIPPhoneTemplate
from boardfarm3.templates.sip_server import SIPServer

_LOGGER = logging.getLogger(__name__)


class PJSIPPhone(LinuxDevice, SIPPhoneTemplate):
    """Perform Functions related to PJSIPphone software."""

    # pylint: disable=too-many-instance-attributes,too-many-public-methods

    supported_lines = cycle([1])
    _YOU_HAVE_0_ACTIVE_CALL: str = "You have 0 active call"

    def __init__(self, config: dict[str, Any], cmdline_args: Namespace) -> None:
        """Instance initialization of the PJSIPPhone class.

        :param config: device configuration
        :type config: dict[str, Any]
        :param cmdline_args: device configuration
        :type cmdline_args: Namespace
        :raises VoiceError: if numbers not present in config
        """
        super().__init__(config=config, cmdline_args=cmdline_args)
        # to ensure all calls go via SIP server IP address
        # will be set once phone_config is called.
        self._proxy_ip: Optional[str] = None
        self._phone_started = False
        self._phone_configured = False
        self._active_line = next(self.supported_lines)
        try:
            self._own_number = self._config.get("number")
        except KeyError as exc:
            msg = "Number not present in the config."
            raise VoiceError(msg) from exc
        self._num_port = self._config.get("num_port", "5060")
        self._config_name = "pjsip.conf"
        self._pjsip_prompt = ">>>"
        self._iface_dut = "eth1"
        # Currently these are static IPs
        # TODO: factorise with the _setup options
        try:
            options = self._parse_device_suboptions()
            self._ipv4_address = options.get("wan-static-ip")
        except (IndexError, ValueError, KeyError):
            self._ipv4_address = None

        self._ipv6_address = None
        self.button_mapping = {"R": self.hold}

    @property
    def name(self) -> str:
        """Return the SIP phone name.

        :return: device name
        :rtype: str
        """
        return self._config["name"]

    @property
    def ipv4_addr(self) -> Optional[str]:
        """Return the SIP Phone IP v4 address.

        :return: phone IP v4 address
        :rtype: Optional[str]
        """
        return self._ipv4_address

    @property
    def ipv6_addr(self) -> Optional[str]:
        """Return the SIP Phone IP v6 address.

        :return: phone IP v6 address
        :rtype: Optional[str]
        """
        return self._ipv6_address

    @property
    def phone_started(self) -> bool:
        """Return the phone initialisation status.

        :return: True if started
        :rtype: bool
        """
        return self._phone_started

    @property
    def active_line(self) -> int:
        """Return the currently active line.

        :return: the value of the active line
        :rtype: int
        """
        return self._active_line

    def _get_number(self) -> str:
        sipserver = get_device_manager().get_device_by_type(SIPServer)  # type: ignore
        return sipserver.allocate_number(self._own_number)

    def _setup(self) -> None:
        # TODO: we need to facotrise the following code as it is common for
        # wan side devices
        if "options" not in self._config:
            return
        self._console.execute_command(f"ifconfig {self._iface_dut} down")
        self._console.execute_command(f"ifconfig {self._iface_dut} up")
        options = self._parse_device_suboptions()
        if "lan-ip-dhcp" in options:
            self._console.execute_command(f"ip -4 addr flush dev {self._iface_dut}")
            self._console.execute_command("dhclient")
        if ipv6_address := options.get("wan-static-ipv6"):
            ipv6_interface = IPv6Interface(ipv6_address)
            # we are bypassing this for now
            # (see http://patchwork.ozlabs.org/patch/117949/)
            self._console.execute_command(
                f"sysctl -w net.ipv6.conf.{self._iface_dut}.accept_dad=0"
            )
            self._console.execute_command(
                f"ip -6 addr del {ipv6_interface} dev {self._iface_dut}"
            )
            self._console.execute_command(
                f"ip -6 addr add {ipv6_interface} dev {self._iface_dut}"
            )
        if value := options.get("wan-static-ip"):
            ipv4_interface = IPv4Interface(value)
            self._console.execute_command(
                f"ip -4 addr del {ipv4_interface} dev {self._iface_dut}"
            )
            self._console.execute_command(
                f"ip -4 addr add {ipv4_interface} dev {self._iface_dut}"
            )
        self._setup_static_routes()

    async def _setup_async(self) -> None:
        # TODO: we need to facotrise the following code as it is common for
        # wan side devices
        if "options" not in self._config:
            return
        await self._console.execute_command_async(f"ifconfig {self._iface_dut} down")
        await self._console.execute_command_async(f"ifconfig {self._iface_dut} up")
        options = self._parse_device_suboptions()
        if "lan-ip-dhcp" in options:
            await self._console.execute_command_async(
                f"ip -4 addr flush dev {self._iface_dut}"
            )
            await self._console.execute_command_async("dhclient")
        if ipv6_address := options.get("wan-static-ipv6"):
            ipv6_interface = IPv6Interface(ipv6_address)
            # we are bypassing this for now
            # (see http://patchwork.ozlabs.org/patch/117949/)
            await self._console.execute_command_async(
                f"sysctl -w net.ipv6.conf.{self._iface_dut}.accept_dad=0"
            )
            await self._console.execute_command_async(
                f"ip -6 addr del {ipv6_interface} dev {self._iface_dut}"
            )
            await self._console.execute_command_async(
                f"ip -6 addr add {ipv6_interface} dev {self._iface_dut}"
            )
        if value := options.get("wan-static-ip"):
            ipv4_interface = IPv4Interface(value)
            await self._console.execute_command_async(
                f"ip -4 addr del {ipv4_interface} dev {self._iface_dut}"
            )
            await self._console.execute_command_async(
                f"ip -4 addr add {ipv4_interface} dev {self._iface_dut}"
            )
        await self._setup_static_routes_async()

    @hookimpl
    def boardfarm_attached_device_boot(self) -> None:
        """Boardfarm hook implementation to boot the PJSIPPhone  device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._setup()

    @hookimpl
    async def boardfarm_attached_device_boot_async(self) -> None:
        """Boardfarm hook implementation to boot the PJSIPPhone  device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()
        await self._setup_async()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm skip-boot hook to initialize the PJSIPPhone device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Boardfarm skip-boot hook to initialize the PJSIPPhone device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()

    @hookimpl
    def boardfarm_attached_device_configure(
        self, device_manager: DeviceManager
    ) -> None:
        """Configure the boardfarm PJSIPPhone device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        #  in case ipv6 needs to be used
        # "endpoint-transport" to be set explicity in config
        ipv6_flag: bool = False
        if "endpoint-transport" in self._config:
            if self._config["endpoint-transport"] == "ipv6":
                ipv6_flag = True
                self.phone_config(
                    ipv6_flag,
                    device_manager.get_device_by_type(
                        SIPServer,  # type: ignore[type-abstract]
                    ).ipv6_addr,
                )
                return

        self.phone_config(
            ipv6_flag,
            device_manager.get_device_by_type(
                SIPServer,  # type: ignore[type-abstract]
            ).ipv4_addr,
        )

    @hookimpl
    async def boardfarm_attached_device_configure_async(
        self, device_manager: DeviceManager
    ) -> None:
        """Configure the boardfarm PJSIPPhone device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        """
        #  in case ipv6 needs to be used
        # "endpoint-transport" to be set explicity in config
        ipv6_flag: bool = False
        if "endpoint-transport" in self._config:
            if self._config["endpoint-transport"] == "ipv6":
                ipv6_flag = True
                self.phone_config(
                    ipv6_flag,
                    device_manager.get_device_by_type(
                        SIPServer,  # type: ignore[type-abstract]
                    ).ipv6_addr,
                )
                return

        await self.phone_config_async(
            ipv6_flag,
            device_manager.get_device_by_type(
                SIPServer,  # type: ignore[type-abstract]
            ).ipv4_addr,
        )

    async def phone_config_async(
        self, ipv6_flag: bool, sipserver_fqdn: str = ""
    ) -> None:
        """Configure the PJSIP phone.

        :param sipserver_fqdn: ip of sip server, default to ""
        :type sipserver_fqdn: str
        :param ipv6_flag: configure PJSIPphone to use ipv6 if set to True
        :type ipv6_flag: bool
        """
        # sipserver_fqdn is set to IPv4 address of the sipserver currently
        self._own_number = self._get_number()
        conf: str = " ".join(
            [
                f"--local-port={self._num_port}",
                f"--id=sip:{self._own_number}@{sipserver_fqdn}",
                f"--registrar=sip:{sipserver_fqdn}",
                "--realm=*",
                f"--username={self._own_number}",
                "--password=1234",
                "--null-audio",
                "--max-calls=1",
                "--auto-answer=180",
                "--no-tcp",
            ]
        )
        if ipv6_flag:
            conf = conf + " --ipv6"

        self._console.sendline("\n")
        idx = await self._console.expect(
            [self._pjsip_prompt] + self._shell_prompt, async_=True
        )
        if idx == 0:
            # come out of pjsip prompt
            self._console.sendcontrol("c")
            await self._console.expect(self._shell_prompt, async_=True)
        try:
            # check for the existing configuration
            out = await self._console.execute_command_async(f"cat {self._config_name}")
            self._phone_configured = conf == out.replace("\r", "")
        except TIMEOUT:
            self._phone_configured = False

        if not self._phone_configured:
            conf_cmd = f"cat >{self._config_name}<<EOF\n{conf}\nEOF\n"
            self._console.sendline(conf_cmd)
            await self._console.expect(self._shell_prompt, async_=True)
            self._phone_configured = True
        self._proxy_ip = sipserver_fqdn

    def phone_config(self, ipv6_flag: bool, sipserver_fqdn: str = "") -> None:
        """Configure the PJSIP phone.

        :param sipserver_fqdn: ip of sip server, default to ""
        :type sipserver_fqdn: str
        :param ipv6_flag: configure PJSIPphone to use ipv6 if set to True
        :type ipv6_flag: bool
        """
        self._own_number = self._get_number()
        conf: str = " ".join(
            [
                f"--local-port={self._num_port}",
                f"--id=sip:{self._own_number}@{sipserver_fqdn}",
                f"--registrar=sip:{sipserver_fqdn}",
                "--realm=*",
                f"--username={self._own_number}",
                "--password=1234",
                "--null-audio",
                "--max-calls=1",
                "--auto-answer=180",
                "--no-tcp",
            ]
        )

        if ipv6_flag:
            conf = conf + " --ipv6"

        self._console.sendline("\n")
        idx = self._console.expect([self._pjsip_prompt] + self._shell_prompt)
        if idx == 0:
            # come out of pjsip prompt
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)
        try:
            # check for the existing configuration
            out = self._console.execute_command(f"cat {self._config_name}")
            self._phone_configured = conf == out.replace("\r", "")
        except TIMEOUT:
            self._phone_configured = False

        if not self._phone_configured:
            conf_cmd = f"cat >{self._config_name}<<EOF\n{conf}\nEOF\n"
            self._console.sendline(conf_cmd)
            self._console.expect(self._shell_prompt)
            self._phone_configured = True
        self._proxy_ip = sipserver_fqdn

    def phone_start(self) -> None:
        """Start the PJSIP phone.

        Note: To avoid failures start PJSIPphone after the SIP server is running.

        :raises VoiceError: on failure to start the the PJSIPphone
        """
        if not self._proxy_ip or not self._phone_configured:
            raise VoiceError("Please configure PJSIPphone first!!")
        try:
            # check if the phone is already started
            self._console.sendline("\n")
            self._console.expect(self._pjsip_prompt, timeout=2)
            self._phone_started = True
            return
        except TIMEOUT:
            try:
                self._console.sendline("pjsua --config-file=" + self._config_name)
                self._console.expect(r"registration success, status=200 \(OK\)")
                self._console.sendline("\n")
                self._console.expect(self._pjsip_prompt)
                self._phone_started = True
            except TIMEOUT as exc:
                self._phone_started = False
                raise VoiceError("Failed to start Phone!!") from exc

    def _select_option_make_call(self) -> None:
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("m")
        self._console.expect(r"Make call\:")

    def _is_phone_started(self) -> None:
        if not self.phone_started:
            raise VoiceError("Please start the phone first!!")

    def dial(self, sequence: str) -> None:
        """Dial the given sequence.

        This sequence could be a phone number or a VSC.

        :param sequence: phone number or VSC
        :type sequence: str
        """
        self._is_phone_started()
        self._select_option_make_call()
        self._console.sendline("sip:" + sequence + "@" + self._proxy_ip)
        self._console.expect("Call [0-9]* state changed to CALLING")
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)

    def answer(self) -> bool:
        """To answer the incoming call in PJSIP phone.

        :return: True if succefully answered a call
        :rtype: bool
        """
        self._is_phone_started()
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("a")
        idx = self._console.expect(
            [
                r"Answer with code \(100\-699\) \(empty to cancel\)\:",
                "No pending incoming call",
            ]
        )
        if idx == 1:
            return False
        self._console.sendline("200")
        self._console.expect("Call [0-9]* state changed to CONFIRMED")
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        return True

    def hangup(self) -> None:
        """To hangup the ongoing call."""
        self._is_phone_started()
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("h")
        self._console.expect(["DISCON", "No current call"])
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)

    def reinvite(self) -> None:
        """To re-trigger the Invite message."""
        self._is_phone_started()
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("v")
        self._console.expect("Sending re-INVITE on call [0-9]*")
        self._console.expect("SDP negotiation done: Success")
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)

    def place_call_offhold(self) -> None:
        """To place call off hold and thus reinvites the call on hold."""
        self._is_phone_started()
        self.reinvite()

    def hold(self) -> None:
        """To hold the current call."""
        self._is_phone_started()
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("H")
        self._console.expect("Putting call [0-9]* on hold")
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)

    def phone_kill(self) -> None:
        """To kill the pjsip session."""
        self._is_phone_started()
        # De-Registration is required before quit a phone and q will handle it
        self._console.sendline("q")
        self._console.expect(self._shell_prompt)
        self._phone_started = False

    def validate_state(self, msg: str) -> bool:
        """Verify the message to validate the status of the call.

        example usage:
           validate_state('INCOMING') to validate an incoming call.
           validate_state('Current call id=<call_id> to <sip_uri> [CONFIRMED]')
           to validate call connected.

        :param msg: The message to expect on the PJSIPphone container
        :type msg: str
        :return: True if success
        :rtype: bool
        """
        self._is_phone_started()
        out = False
        with suppress(pexpect.TIMEOUT):
            self._console.sendline("\n")
            self._console.expect(self._pjsip_prompt)
            if msg == "INCOMING":
                msg = "180 Ringing"
            self._console.expect(msg)
            self._console.expect(self._pjsip_prompt)
            out = True
        return out

    def _send_update_and_validate(self, msg: str) -> bool:
        with suppress(pexpect.TIMEOUT):
            self._console.sendline("\n")
            self._console.expect(self._pjsip_prompt)
            self._console.sendline("U")
            self._console.expect(msg)
        return True

    def on_hook(self) -> None:
        """Line hungup (i.e. put down the handset)."""
        self._is_phone_started()
        self.hangup()

    def off_hook(self) -> None:
        """Line off hook (i.e. lift the handset)."""
        self._is_phone_started()
        self.answer()

    def is_idle(self) -> bool:
        """Is the line idle.

        :return: True if the line is idle
        :rtype: bool
        """
        self._is_phone_started()
        return self.validate_state(self._YOU_HAVE_0_ACTIVE_CALL)

    def is_dialing(self) -> bool:
        """Is the line in dialig state.

        :return: True if in dialling state
        :rtype: bool
        """
        self._is_phone_started()
        return self.validate_state(
            "You have 1 active call.*Current call id=[0-9]* to sip:[0-9]"
            rf"*@{self._proxy_ip} \[EARLY\]"
        )

    def is_incall_dialing(self) -> bool:
        """Add compatibility with FXS phones.

        :return: if the incall is connected
        :rtype: bool
        """
        self._is_phone_started()
        return bool(self.is_connected())

    def is_ringing(self) -> bool:
        """Is the line ringing.

        :return: if the line is ringing
        :rtype: bool
        """
        self._is_phone_started()
        return self.validate_state("180 Ringing")

    def is_connected(self) -> bool:
        """Is it the call connected.

        :return: True if the call is connected
        :rtype: bool
        """
        self._is_phone_started()
        return self.validate_state("CONFIRMED")

    def is_incall_connected(self) -> bool:
        """Is incall connected.

        :return: True if the incall is connected
        :rtype: bool
        """
        self._is_phone_started()
        # This is not supported, added here to provide compatibility with FXS phones
        return bool(self.is_connected())

    def is_onhold(self) -> bool:
        """Is on hold.

        :return: True if the call is on hold
        :rtype: bool
        """
        self._is_phone_started()
        return self._send_update_and_validate(
            r"PCMU \(sendonly\).*\[type=audio\], status is Local hold"
        )

    def is_playing_dialtone(self) -> bool:
        """Is it playing the dialtone.

        :return: True if the dialtone is playing
        :rtype: bool
        """
        self._is_phone_started()
        return self._send_update_and_validate("No current call")

    def is_incall_playing_dialtone(self) -> bool:
        """Return if incall has dialtone.

        :raises NotSupportedError: currently not supoported
        """
        raise NotSupportedError

    def is_call_ended(self) -> bool:
        """Call should disconnect when hangup by other user.

        :return: True if the call has ended
        :rtype: bool
        """
        self._is_phone_started()
        self._console.sendline("\n")
        # Call should be disconnected as the call hangup by other user
        self._console.expect(self._YOU_HAVE_0_ACTIVE_CALL)
        out = "DISCONNECTED [reason=200 (Normal call clearing)]" in self._console.before
        self._console.expect(self._pjsip_prompt)
        return out

    def is_code_ended(self) -> bool:
        """Is code ended.

        :return: True if the device has been idle for a number of seconds
        :rtype: bool
        """
        self._is_phone_started()
        with suppress(pexpect.TIMEOUT):
            self._console.sendline("\n")
            self._console.expect(self._pjsip_prompt)
            self._console.expect(
                r"Closing sound device after idle for [0-9]* second\(s\)"
            )
            self._console.sendline("\n")
        return True

    def is_call_waiting(self) -> bool:
        """Is call waiting.

        :return: True if the call is in wating state
        :rtype: bool
        """
        self._is_phone_started()
        return self.validate_state(r"Incoming call for account [0-9]*")

    def is_in_conference(self) -> bool:
        """Check if current call is in conference.

        :raises NotSupportedError: currently not supported
        """
        raise NotSupportedError

    def has_off_hook_warning(self) -> bool:
        """Has off hook warning.

        :raises NotSupportedError: Currently not supported
        """
        raise NotSupportedError

    def detect_dialtone(self) -> bool:
        """Detect dialtone.

        :return: True if dialtone is detected
        :rtype: bool
        """
        self._is_phone_started()
        return self.is_playing_dialtone()

    @property
    def number(self) -> str:
        """Return the number.

        :return: the number
        :rtype: str
        """
        return self._own_number

    def reply_with_code(self, code: int) -> None:
        """Reply with the give code.

        :param code: the code (100 <= code < 700)
        :type code: int
        :raises VoiceError: if there is no incoming call
        """
        self._is_phone_started()
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)
        self._console.sendline("a")
        idx = self._console.expect(
            [
                r"Answer with code \(100\-699\) \(empty to cancel\)\:",
                "No pending incoming call",
            ]
        )
        if idx == 1:
            raise VoiceError("No incoming call to reply to!!")
        self._console.sendline(f"{code}")
        self._console.sendline("\n")
        self._console.expect(self._pjsip_prompt)

    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        :return: True if line is busy, else False
        :rtype: bool
        """
        self._is_phone_started()
        self._console.sendline("\n")
        # Call should be disconnected due to callee being BUSY
        # If we do not see the prompt menu, something went wrong
        self._console.expect(self._YOU_HAVE_0_ACTIVE_CALL)
        out = "DISCONNECTED [reason=486 (Busy Here)]" in self._console.before
        self._console.expect(self._pjsip_prompt)
        return out

    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered.

        :return: True if not answered, else False
        :rtype: bool
        """
        self._is_phone_started()
        self._console.sendline("\n")
        # Call should be disconnected due to not getting answered
        # If we do not see the prompt menu, something went wrong
        self._console.expect(self._YOU_HAVE_0_ACTIVE_CALL)
        out = "DISCONNECTED [reason=408 (Request Timeout)]" in self._console.before
        self._console.expect(self._pjsip_prompt)
        return out

    def answer_waiting_call(self) -> None:
        """Answer the waiting call and hang up on the current call.

        :raises NotSupportedError: Currently Unsupported
        """
        raise NotSupportedError

    def toggle_call(self) -> None:
        """Toggle between the calls.

        Need to first validate, there is an incoming call on other line.

        :raises NotSupportedError: Currently Unsupported
        """
        raise NotSupportedError

    def merge_two_calls(self) -> None:
        """Merge the two calls for conference calling.

        Ensure call waiting must be enabled.
        There must be a call on other line to add to conference.

        :raises NotSupportedError: Currently Unsupported
        """
        raise NotSupportedError

    def reject_waiting_call(self) -> None:
        """Reject a call on waiting on second line.

        This will send the call to voice mail or a busy tone.
        There must be a call on the second line to reject.

        :raises NotSupportedError: Currently Unsupported
        """
        raise NotSupportedError

    def place_call_onhold(self) -> None:
        """Place an ongoing call on-hold.

        There must be an active call to be placed on hold.
        """
        self.hold()

    def press_R_button(self) -> None:
        """Press the R button.

        Used when we put a call on hold, or during dialing.
        """
        self.button_mapping["R"]()

    def hook_flash(self) -> None:
        """To perfrom hook flash."""
        self.press_R_button()

    def _dial_feature_code(self, code: str) -> None:
        self._select_option_make_call()
        self._console.sendline(f"sip:{code}@{self._proxy_ip}")
        self._console.expect("Call [0-9]* state changed to CALLING")
        if not self.is_code_ended():
            raise VoiceError(f"Call not ended after dialing a feature code: {code}")

    def press_buttons(self, buttons: str) -> None:
        """Press user provided buttons.

        :param buttons: user provided buttons
        :type buttons: str
        """
        for button in buttons:
            self.button_mapping[button]()


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template

    PJSIPPhone(config={}, cmdline_args=Namespace())
