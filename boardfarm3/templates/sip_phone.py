"""SIPPhone Template module."""

# ruff: noqa: FIX001
from __future__ import annotations

from abc import ABC, abstractmethod

from boardfarm3.exceptions import VoiceError

# pylint: disable=too-many-public-methods


class SIPPhone(ABC):
    """SIP Phone Template."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the SIP Phone name.

        :return: phone name
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def ipv4_addr(self) -> str | None:
        """Return the SIP Phone IP v4 address.

        :return: phone IP v4 address
        :rtype: str | None
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def ipv6_addr(self) -> str | None:
        """Return the SIP Phone IP v6 address.

        :return: phone IP v6 address
        :rtype: str | None
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def number(self) -> str:
        """To get the registered SIP number.

        This property shall be dynamically populated during the post_boot
        activities of environment setup for voice.
        """
        raise NotImplementedError

    # TODO: should not this be private and part of bootign?
    @abstractmethod
    def phone_start(self) -> None:
        """Connect to the serial line of FXS modem."""
        raise NotImplementedError

    # TODO: should not this be private and part of booting?
    @abstractmethod
    def phone_config(self, ipv6_flag: bool, sipserver_fqdn: str = "") -> None:
        """Configure phone with a SIP url using SIP server ddqn for registration.

        :param ipv6_flag: dicatates whether to use ipv6 address or not
        :type ipv6_flag: bool
        :param sipserver_fqdn: the sip server, defaults to ""
        :type sipserver_fqdn: str
        """
        raise NotImplementedError

    # TODO: private, booting/framework
    @abstractmethod
    def phone_kill(self) -> None:
        """Close the serial connection."""
        raise NotImplementedError

    @abstractmethod
    def on_hook(self) -> None:
        """Execute on_hook procedure to disconnect to a line."""
        raise NotImplementedError

    @abstractmethod
    def off_hook(self) -> None:
        """Execute off_hook procedure to connect to a line."""
        raise NotImplementedError

    @abstractmethod
    def answer(self) -> bool:
        """To answer a call on RING state."""
        raise NotImplementedError

    @abstractmethod
    def dial(self, sequence: str) -> None:
        """Dial the given sequence.

        This sequence could be a phone number or a VSC.

        Call shall proceed on the line indicated by active_line property.

        :param sequence: phone number or VSC
        :type sequence: str
        :raises NotImplementedError: as this is a Template.
        """
        raise NotImplementedError

    def dial_feature_code(self, code: str) -> None:
        """Dial a feature code.

        Dial the given code, check that it executed and put the phone on hook.

        :param code: the code to be executed
        :type code: str
        :raises VoiceError: in case execution did not end well
        """
        self.dial(sequence=code)
        if not self.is_code_ended():
            msg = f"Call not ended after dialing a feature code: {code}"
            raise VoiceError(msg)
        self.on_hook()

    @abstractmethod
    def is_idle(self) -> bool:
        """Check if Phone is in idle state on a line represented by active_line.

        :return: True if the phone is idle
        :rtype: bool
        """
        raise NotImplementedError

    # FIXME: typo!
    @abstractmethod
    def is_dialing(self) -> bool:
        """Check if the phone is dialing to another phone.

        Check if the phone is dialing to another phone on a line represented
        by active_line.

        :return: True if the phone is dialing in progress
        :rtype: bool
        """
        raise NotImplementedError

    # TODO: what is this?
    @abstractmethod
    def is_incall_dialing(self) -> bool:
        """Check if Phone is in call and dialing.

        Check if Phone is in call and dialing to another phone on a line
        represented by active_line.

        :return: True if the phone is in call and dialing in progress on
                 another line
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_ringing(self) -> bool:
        """Check if Phone is ringing on a line represented by active_line.

        :return: True if the phone is ringing
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if call is connected on the active_line.

        :return: True if the phone is connected
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_incall_connected(self) -> bool:
        """Check if call is in call connected on the active_line.

        :return: True if the phone is in call connected
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_onhold(self) -> bool:
        """Check if Phone is on hold on a line represented by active_line.

        :return: True if the phone is on hold
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_playing_dialtone(self) -> bool:
        """Check if Phone is playing dialtone on a line represented by active_line.

        :return: True if the phone is playing dialtone
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_incall_playing_dialtone(self) -> bool:
        """Check if Phone is playing dialtone. on one line and on call to another line.

        :return: True if the phone is incall playing dialtone
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_call_ended(self) -> bool:
        """Check if Phone has end up the call on a line represented by active_line.

        :return: True if the phone end up the call
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_code_ended(self) -> bool:
        """Check if Phone has end up the code on a line represented by active_line.

        :return: True if the phone has end up the code
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_call_waiting(self) -> bool:
        """Check if Phone is on call waiting on a line represented by active_line.

        :return: True if the phone is on call waiting
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_in_conference(self) -> bool:
        """Check if Phone is in conference on a line represented by active_line.

        :return: True if the phone is in conference
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def has_off_hook_warning(self) -> bool:
        """Check if Phone has off hook warning on a line represented by active_line.

        :return: True if the phone has off hook warning
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def detect_dialtone(self) -> bool:
        """Check if dialtone is detected off_hook on the active_line.

        :return: True if dial tone is detected
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        Validation will be performed on the line indicated by
        active_line property.

        :return: True if line is busy, else False
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def reply_with_code(self, code: int) -> None:
        """To reply back to an incoming call with a SIP code value.

        In case of certain phones, we need to explicitly send out SIP codes
        such as:
        - 486 Busy
        - 200 OK
        - 603 Decline
        - 608 Rejected

        :param code: SIP code value
        :type code: int
        """
        raise NotImplementedError

    @abstractmethod
    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered on active_line.

        :return: True if not answered, else False
        :rtype: bool
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def answer_waiting_call(self) -> None:
        """Answer the waiting call and hang up on the current call.

        This will toggle the line on the device.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def toggle_call(self) -> None:
        """Toggle between the calls.

        Need to first validate, there is an incoming call on other line.
        If not throw an exception.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def merge_two_calls(self) -> None:
        """Merge the two calls for conference calling.

        Ensure call waiting must be enabled.
        There must be a call on other line to add to conference.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def reject_waiting_call(self) -> None:
        """Reject a call on waiting on second line.

        This will send the call to voice mail or a busy tone.
        There must be a call on the second line to reject.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def place_call_onhold(self) -> None:
        """Place an ongoing call on-hold.

        There must be an active call to be placed on hold.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def place_call_offhold(self) -> None:
        """Place an ongoing call off-hold.

        There must be a call on hold to be placed to off hold.
        """
        raise NotImplementedError

    # FIXME: obsolete by press_buttons()
    @abstractmethod
    def press_R_button(self) -> None:  # pylint: disable=invalid-name
        """Press the R button.

        Used when we put a call on hold, or during dialing.
        """
        raise NotImplementedError

    @abstractmethod
    def hook_flash(self) -> None:
        """Perform hook flash.

        :raises NotImplementedError: as this is a Template
        """
        msg = "Not supported."
        raise NotImplementedError(msg)

    @abstractmethod
    def press_buttons(self, buttons: str) -> None:
        """Press the given sequence of buttons.

        :param buttons: sequence of buttons, e.g. "R2"
        :type buttons: str
        :raises NotImplementedError: as this is a Template
        """
        # press a button for each button in the list
        raise NotImplementedError
