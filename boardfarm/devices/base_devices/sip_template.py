import random
from abc import ABC, abstractmethod
from typing import List, Optional, Union

from debtcollector import moves

from boardfarm.devices.base_devices import fxo_template
from boardfarm.devices.linux import LinuxInterface
from boardfarm.lib.signature_checker import __MetaSignatureChecker


class SIPPhoneTemplate(LinuxInterface, ABC):
    @property
    @abstractmethod
    def model(self):
        """This attribute is used by boardfarm device manager.

        This is used to match parameters entry from config
        and initialise correct object.

        This property shall be any string value that matches the "type"
        attribute of FSX entry in the inventory config file.
        See devices/serialphone.py as a reference
        """

    @property
    @abstractmethod
    def number(self):
        """To get the registered SIP number.

        This property shall be dynamically populated during the post_boot
        activities of environment setup for voice.
        """

    @abstractmethod
    def phone_start(self) -> None:
        """Connect to the serial line of FXS modem.

        :param baud: serial baud rate, defaults to "115200"
        :type baud: str, optional
        :param timeout: connection timeout, defaults to "1"
        :type timeout: str, optional
        """

    @abstractmethod
    def phone_config(self, sip_server: str = "") -> None:
        """Configure the phone with a SIP url using SIP server IP for registration."""

    @abstractmethod
    def phone_kill(self) -> None:
        """Close the serial connection."""

    @abstractmethod
    def on_hook(self) -> None:
        """Execute on_hook procedure to disconnect to a line."""

    @abstractmethod
    def off_hook(self) -> None:
        """Execute off_hook procedure to connect to a line."""

    @abstractmethod
    def answer(self) -> bool:
        """To answer a call on RING state."""

    @abstractmethod
    def call(self, callee: "SIPPhoneTemplate") -> None:
        """To dial a call to callee.

        FXS modems simulate analog phones and requie ISDN/PSTN number to dial.
        In case of dialing a SIP enabled phone, SIP proxy IP is used
        to auto-generate a SIP URL for dialing.

        Call shall proceed on the line indicated by active_line property.

        :param callee: Device which will act as the callee.
        :type callee: SIPPhoneTemplate
        """

    @abstractmethod
    def enable_call_waiting(self) -> None:
        """Enables call waiting by dialing a number and then puts phone onhook"""

    @abstractmethod
    def enable_call_forwarding_busy(self, forward_to: "SIPPhoneTemplate") -> None:
        """Enables call forwarding to a number when the call is busy
        Dials a code and a number to which a call is supposed to forward and then puts phone onhook

        :param forward_to: Device to which call needs to be forwarded to.
        :type forward_to: SIPPhoneTemplate"""

    @abstractmethod
    def disable_call_forwarding_busy(self) -> None:
        """Disables call forwarding busy by dialing a code and then puts phone onhook"""

    @abstractmethod
    def disable_call_waiting_overall(self) -> None:
        """ """

    @abstractmethod
    def disable_call_waiting_per_call(self) -> None:
        """ """

    @abstractmethod
    def is_idle(self) -> bool:
        """Check if Phone is in idle state on a line represented by active_line.

        :return: True if the phone is idle
        :rtype: bool
        """

    @abstractmethod
    def is_dialing(self) -> bool:
        """Check if Phone is dialing to another phone on a line represented by active_line.

        :return: True if the phone is dialing in progress
        :rtype: bool
        """

    @abstractmethod
    def is_incall_dialing(self) -> bool:
        """Check if Phone is in call and dialing to another phone on a line represented by active_line.

        :return: True if the phone is in call and dialing in progress on another line
        :rtype: bool
        """

    @abstractmethod
    def is_ringing(self) -> bool:
        """Check if Phone is ringing on a line represented by active_line.

        :return: True if the phone is ringing
        :rtype: bool
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if call is connected on the active_line.

        :return: True if the phone is connected
        :rtype: bool
        """

    @abstractmethod
    def is_incall_connected(self) -> bool:
        """Check if call is in call connected on the active_line.

        :return: True if the phone is in call connected
        :rtype: bool
        """

    @abstractmethod
    def is_onhold(self) -> bool:
        """Check if Phone is on hold on a line represented by active_line.

        :return: True if the phone is on hold
        :rtype: bool
        """

    @abstractmethod
    def is_playing_dialtone(self) -> bool:
        """Check if Phone is playing dialtone on a line represented by active_line.

        :return: True if the phone is playing dialtone
        :rtype: bool
        """

    @abstractmethod
    def is_incall_playing_dialtone(self) -> bool:
        """Check if Phone is playing dialtone on one line and on call to another line

        :return: True if the phone is incall playing dialtone
        :rtype: bool
        """

    @abstractmethod
    def is_call_ended(self) -> bool:
        """Check if Phone has end up the call on a line represented by active_line.

        :return: True if the phone end up the call
        :rtype: bool
        """

    @abstractmethod
    def is_code_ended(self) -> bool:
        """Check if Phone has end up the code on a line represented by active_line.

        :return: True if the phone has end up the code
        :rtype: bool
        """

    @abstractmethod
    def is_call_waiting(self) -> bool:
        """Check if Phone is on call waiting on a line represented by active_line.

        :return: True if the phone is on call waiting
        :rtype: bool
        """

    @abstractmethod
    def is_in_conference(self) -> bool:
        """Check if Phone is in conference on a line represented by active_line.

        :return: True if the phone is in conference
        :rtype: bool
        """

    @abstractmethod
    def has_off_hook_warning(self) -> bool:
        """Check if Phone has off hook warning on a line represented by active_line.

        :return: True if the phone has off hook warning
        :rtype: bool
        """

    @abstractmethod
    def detect_dialtone(self) -> bool:
        """Check if dialtone is detected off_hook on the active_line

        :return:
        :rtype: bool
        """

    @abstractmethod
    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        Validation will be performed on the line indicated by
        active_line property.

        :return: True if line is busy, else False
        :rtype: bool
        """

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

    @abstractmethod
    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered on active_line

        :return: True if not answered, else False
        :rtype: bool
        """

    @abstractmethod
    def answer_waiting_call(self) -> None:
        """Answer the waiting call and hang up on the current call.

        This will toggle the line on the device.
        """

    @abstractmethod
    def toggle_call(self) -> None:
        """Toggle between the calls.

        Need to first validate, there is an incoming call on other line.
        If not throw an exception.
        """

    @abstractmethod
    def merge_two_calls(self) -> None:
        """Merge the two calls for conference calling.

        Ensure call waiting must be enabled.
        There must be a call on other line to add to conference.
        """

    @abstractmethod
    def reject_waiting_call(self) -> None:
        """Reject a call on waiting on second line.

        This will send the call to voice mail or a busy tone.
        There must be a call on the second line to reject.
        """

    @abstractmethod
    def place_call_onhold(self) -> None:
        """Place an ongoing call on-hold.

        There must be an active call to be placed on hold.
        """

    @abstractmethod
    def place_call_offhold(self) -> None:
        """Place an ongoing call off-hold.

        There must be a call on hold to be placed to off hold.
        """

    @abstractmethod
    def press_R_button(self) -> None:  # pylint: disable=invalid-name
        """Press the R button.

        Used when we put a call on hold, or during dialing.
        """

    @abstractmethod
    def hook_flash(self) -> None:
        """Perform hook flash."""
        raise NotImplementedError("Not supported!")


class SIPTemplate(LinuxInterface, metaclass=__MetaSignatureChecker):
    """SIP server template class.
    Contains basic list of APIs to be able to use TR069 intercation with CPE
    All methods, marked with @abstractmethod annotation have to be implemented in derived
    class with the same signatures as in template. You can use 'pass' keyword if you don't
    need some methods in derived class.
    """

    @property
    @abstractmethod
    def model(self):
        """This attribute is used by boardfarm to match parameters entry from config
        and initialise correct object.
        This property shall be any string value that matches the "type"
        attribute of SIP entry in the inventory config file.
        See devices/kamailio.py as a reference
        """

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        """Initialize SIP parameters.
        Config data dictionary will be unpacked and passed to init as kwargs.
        You can use kwargs in a following way:
            self.username = kwargs.get("username", "DEFAULT_USERNAME")
            self.password = kwargs.get("password", "DEFAULT_PASSWORD")
        """
        super().__init__(*args, **kwargs)  # type: ignore

    @abstractmethod
    def sipserver_install(self) -> None:
        """Install sipserver."""

    @abstractmethod
    def sipserver_purge(self) -> None:
        """To purge the sipserver installation."""

    @abstractmethod
    def sipserver_configuration(self) -> None:
        """Configure sipserver."""

    @abstractmethod
    def sipserver_start(self) -> None:
        """Start the server"""

    @abstractmethod
    def sipserver_stop(self) -> None:
        """Stop the server."""

    @abstractmethod
    def sipserver_restart(self) -> None:
        """Restart the server."""

    @abstractmethod
    def sipserver_status(self) -> str:
        """Return the status of the server."""

    @abstractmethod
    def sipserver_kill(self) -> None:
        """Kill the server."""

    @moves.moved_method("add_endpoint_to_sipserver")
    def sipserver_user_add(self, user: str, password: str = None) -> None:
        """Add user to the directory.

        param user: the user entry to be added
        type user: string
        param password: the password of the endpoint is determined by the user, defaults to None
        type password: string
        """
        self.add_endpoint_to_sipserver(endpoint=user, password=password)

    @abstractmethod
    def add_endpoint_to_sipserver(self, endpoint: str, password: str) -> None:
        """Add endpoint to the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param password: the password of the endpoint
        type password: string
        """

    @moves.moved_method("remove_endpoint_from_sipserver")
    def sipserver_user_remove(self, user: str) -> None:
        """Remove a user from the directory.
        param user: the user entry to be added
        type user: string
        """
        self.remove_endpoint_from_sipserver(endpoint=user)

    @abstractmethod
    def remove_endpoint_from_sipserver(self, endpoint: str) -> None:
        """Remove an endpoint from the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        """

    @moves.moved_method("update_endpoint_in_sipserver")
    def sipserver_user_update(self, user: str, password: str) -> None:
        """Update user in the directory.

        param user: the user entry to be added
        type user: string
        param password: the password of the user
        type password: string
        """
        self.update_endpoint_in_sipserver(endpoint=user, password=password)

    @abstractmethod
    def update_endpoint_in_sipserver(self, endpoint: str, password: str) -> None:
        """Update an endpoint in the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param password: the password of the endpoint
        type password: string
        """

    @abstractmethod
    def configure_tls_to_endpoint_in_sipserver(
        self, phone_list: List[Union[fxo_template.FXOTemplate, SIPPhoneTemplate]]
    ) -> None:
        """Configure TLS for the devices mentioned

        param phone_list: list of phones which needs tls to be configured
        type phone_list: List[FXOTemplate]
        """

    @moves.moved_method("endpoint_registration_status_in_sipserver")
    def sipserver_user_registration_status(self, user: str, ip_address: str) -> str:
        """Return the registration status.

        param user: the user entry to be added
        type user: string
        param ip_address: the password of the user
        type ip_address: string
        """
        self.endpoint_registration_status_in_sipserver(
            endpoint=user, ip_address=ip_address
        )

    @abstractmethod
    def endpoint_registration_status_in_sipserver(
        self, endpoint: str, ip_address: str
    ) -> str:
        """Return the registration status.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param ip_address: the ip address of the endpoint
        type ip_address: string
        """

    def allocate_number(self, number: Optional[str] = None) -> str:
        """Allocate a number from the sipserver number list"""
        if number:
            number_to_be_allocated = number
        else:
            number_to_be_allocated = random.choice(self.users)
        self.users.remove(number_to_be_allocated)
        return number_to_be_allocated
