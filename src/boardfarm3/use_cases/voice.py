"""Voice use cases library.

This module deals with only SIP end points.
All APIs are independent of board under test.
"""
# ruff: noqa: FIX001

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from termcolor import colored

from boardfarm3.exceptions import VoiceError
from boardfarm3.templates.sip_phone import SIPPhone
from boardfarm3.templates.sip_server import SIPServer

_LOGGER = logging.getLogger(__name__)

# TODO: confirm that FXS is a SIP Phone
VoiceClient = SIPPhone
VoiceServer = SIPServer

VoiceResource = tuple[list[VoiceClient], VoiceServer, str, SimpleNamespace]

VoiceResourceGen = Generator[VoiceResource, None, None]


@contextmanager
def tcpdump(
    dev: VoiceServer,
    fname: str,
    filters: str = "",
) -> Generator[str]:
    """Start packet capture using tcpdump and kills the process at the end.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Start the packets capture to be able to analyze SIP/RTP/RTCP protocol

    :param dev: device object for a VoiceServer
    :type dev: VoiceServer
    :param fname: name of the pcap file to which the capture will be stored
    :type fname: str
    :param filters: additional filters for capture, defaults to ""
    :type filters: str
    :yield: process id
    :rtype: Generator[str, None, None]
    """
    with dev.tcpdump_capture(
        fname=fname,
        interface=dev.iface_dut,
        additional_args=f"-s0 {filters}",
    ) as pid:
        yield pid


def call_a_phone(caller: VoiceClient, callee: VoiceClient) -> None:
    """Call the Callee by the Caller.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) calls (User)

    :param caller: SIP agent who intiates the call
    :type caller: VoiceClient
    :param callee: SIP agent who receives the call
    :type callee: VoiceClient
    :raises VoiceError: In case the call fails.
    """
    try:
        assert caller is not callee, "Caller and Callee cannot be same!"  # noqa: S101
        caller.dial(callee.number)
    except Exception as exc:  # pylint: disable=broad-except  # BOARDFARM-4980
        msg = f"Failed to initiate a call between: {caller.name} --> {callee.name}"
        raise VoiceError(msg) from exc


def call_a_number(caller: VoiceClient, phone_nr: str) -> None:
    """Have the Caller dial the given phone number.

    :param caller: SIP agent that initiates the call
    :type caller: VoiceClient
    :param phone_nr: Phone number to be dialled
    :type phone_nr: str
    """
    caller.dial(phone_nr)


def put_phone_offhook(who_puts_offhook: VoiceClient) -> None:
    """Put the phone off hook.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) goes off Hook.

    :param who_puts_offhook: SIP agent who puts phone off hook
    :type who_puts_offhook: VoiceClient
    """
    who_puts_offhook.off_hook()


def answer_a_call(who_answers: VoiceClient) -> bool:
    """Answer a ringing call by target SIP agent.

    Execution order:
    - Ensure there is a ring on the target agent.
    - Pick up the call
    - Ensure the line is connected

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) answers to (User)

    :param who_answers: SIP agent who is suppose to answer the call.
    :type who_answers: VoiceClient
    :raises VoiceError: In case answering the call fails.
    :return: True if call is connected, else False
    :rtype: bool
    """
    if not who_answers.is_ringing():
        msg = f"{who_answers.name} is not ringing!!"
        raise VoiceError(msg)
    who_answers.answer()

    return who_answers.is_connected()


def disconnect_the_call(who_disconnects: VoiceClient) -> bool:
    """Disconnecting a call on a SIP agent.

    The user will not verify if the call is ongoing.
    It will simply call the on_hook implementation.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) goes on hook.

    :param who_disconnects: SIP agent who is suppose to disconnect the call.
    :type who_disconnects: VoiceClient
    :raises VoiceError: In case disconnecting the call fails.
    :return: True if call is disconnected
    :rtype: bool
    """
    try:
        who_disconnects.on_hook()
    except Exception as exc:  # pylint: disable=broad-except  # BOARDFARM-4981
        msg = f"Failed to disconnect the call: {who_disconnects.name}"
        raise VoiceError(msg) from exc
    return True


def is_dialtone_detected(agent: VoiceClient) -> bool:
    """Verify if a dialtone is detected off_hook.

    Device will be first placed on_hook.
    This is done to ensure disconnecting any previous sessions.

    After verifying dial tone device will again go back to on_hook state.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) goes off hook

    :param agent: SIP agent used to verify dialtone.
    :type agent: VoiceClient
    :return: True if dialtone is detected.
    :rtype: bool
    """
    agent.on_hook()
    return agent.detect_dialtone()


# TODO: review why 2 clients are needed here
def is_line_busy(on_which_agent: VoiceClient, who_is_busy: VoiceClient) -> bool:
    """To verify if the caller was notified that the callee is BUSY.

    Some phone will send this explicitly and will have RINGING 180
    as well inside their trace.

    .. hint:: This Use Case implements statements from the test suite such as:

        - To verify if the caller was notified that the callee is BUSY.

    :param on_which_agent: Caller who will receive BUSY
    :type on_which_agent: VoiceClient
    :param who_is_busy: Callee who replies BUSY
    :type who_is_busy: VoiceClient
    :return: True if caller received BUSY, else False
    :rtype: bool
    """
    assert on_which_agent is not who_is_busy, "Both args cannot be same"  # noqa: S101

    return on_which_agent.is_line_busy()


# TODO: consider renaming as caller
def is_call_not_answered(whose_call: VoiceClient) -> bool:
    """Verify if callee did not pick up the call.

    The Caller will receive a NO CARRIER or TIMEOUT reply.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if callee did not pick up the call.

    :param whose_call: Callee
    :type whose_call: VoiceClient
    :return: True is not answered, else False
    :rtype: bool
    """
    return whose_call.is_call_not_answered()


def initialize_phone(target_phone: VoiceClient) -> None:
    """Configure the phone, and start the application.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Configure the phone, and start the application.

    :param target_phone: Target phone to be initialized
    :type target_phone: VoiceClient
    """
    target_phone.phone_start()
    target_phone.on_hook()


# TODO: why should a Use Case shut down a device? It should be a framework's problem
# unless this is de-registering...
def shutdown_phone(target_phone: VoiceClient) -> None:
    """Go on_hook and stop the phone application.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Go on_hook and stop the phone application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: VoiceClient
    """
    dev = target_phone
    try:
        dev.on_hook()
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001  # BOARDFARM-4982
        _LOGGER.warning(colored("Cannot put phone onhook", color="yellow"))
    dev.phone_kill()


# TODO: is this different from answering a call?
def answer_waiting_call(who_answers: VoiceClient) -> None:
    """Answer the waiting call and hang up on the current call.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses R1

    :param who_answers: SIP agent who is suppose to answer the call.
    :type who_answers: VoiceClient
    """
    who_answers.answer_waiting_call()


def toggle_call(who_toggles: VoiceClient) -> None:
    """Toggle between the calls.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses R2 button

    Need to first validate, there is an incoming call on other line.
    If not throw an exception.

    :param who_toggles: SIP agent who is suppose to toggle the call
    :type who_toggles: VoiceClient
    """
    who_toggles.toggle_call()


def merge_two_calls(who_is_conferencing: VoiceClient) -> None:
    """Merge the two calls for conference calling.

    Ensure call waiting must be enabled.
    There must be a call on other line to add to conference.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses R3 and initiates 3-Way Conference

    :param who_is_conferencing: SIP agent that adds all calls in a conference.
    :type who_is_conferencing: VoiceClient
    """
    client: SIPPhone = who_is_conferencing
    client.merge_two_calls()


# TODO: place_active_call_on_hold?
def place_call_onhold(who_places: VoiceClient) -> None:
    """Place an ongoing call on-hold.

    There must be an active call to be placed on hold.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses flash hook

    :param who_places: SIP agent that is suppose to place the call on-hold.
    :type who_places: VoiceClient
    :raises VoiceError: If there is no on-going call
    """
    client: SIPPhone = who_places
    if not client.is_connected() and not client.is_incall_connected():
        msg = "No active call in place!!"
        raise VoiceError(msg)
    client.place_call_onhold()


def place_call_offhold(who_places: VoiceClient) -> None:
    """Place an ongoing call on hold to off-hold.

    There must be an active call to be placed off hold.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses flash hook

    :param who_places: SIP agent that is suppose to place the call off-hold.
    :type who_places: VoiceClient
    """
    client: SIPPhone = who_places
    client.place_call_offhold()


# TODO: why?
# why not press button(R)
# why are the other Use Cases not enought?
def press_R_button(who_presses: VoiceClient) -> None:  # pylint: disable=invalid-name
    """Press the R button.

    Used when we put a call on hold, or during dialing.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) presses R button

    :param who_presses: Agent that presses the R button.
    :type who_presses: VoiceClient
    """
    client: SIPPhone = who_presses
    client.press_R_button()


# TODO: ringing?
def is_call_dialing(who_is_dialing: VoiceClient) -> bool:
    """Verify if a phone is dialing and a call in progress.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a phone is dialing and a call in progress.

    :param who_is_dialing: SIP agent used to verify dialing
    :type who_is_dialing: VoiceClient
    :return: True if in progress dialing is detected
    :rtype: bool
    """
    return who_is_dialing.is_dialing()


# FIXME: this does not make sense
def is_incall_dialing(who_is_incall_dialing: VoiceClient) -> bool:
    """Verify if a phone is incall and call is dialing/in progress.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a phone is incall and call is dialing/in progress.

    :param who_is_incall_dialing: SIP agent used to verify incall dialing
    :type who_is_incall_dialing: VoiceClient
    :return: True if in progress dialing is detected
    :rtype: bool
    """
    return who_is_incall_dialing.is_incall_dialing()


# FIXME: doesn't make sense
def is_call_idle(who_is_idle: VoiceClient) -> bool:
    """Verify if a phone is in idle state.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) goes on Hook
        - Verify if a phone is in idle state.

    :param who_is_idle: SIP agent used to verify idle
    :type who_is_idle: VoiceClient
    :return: True if idle is detected
    :rtype: bool
    """
    return who_is_idle.is_idle()


# TODO: this is for the callee, right?
def is_call_ringing(who_is_ringing: VoiceClient) -> bool:
    """Verify if a ringtone is detected on a phone device.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a ringtone is detected on a phone device.

    :param who_is_ringing: SIP agent used to verify ringtone
    :type who_is_ringing: VoiceClient
    :return: True if ringtone is detected
    :rtype: bool
    """
    return who_is_ringing.is_ringing()


def is_call_connected(who_is_connected: VoiceClient) -> bool:
    """Verify if a call is connected.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a call is connected.

    :param who_is_connected: SIP client on which connection needs to be checked
    :type who_is_connected: VoiceClient
    :return: True if call is connected.
    :rtype: bool
    """
    return who_is_connected.is_connected()


# TODO: what is the difference?
def is_incall_connected(who_is_incall_connected: VoiceClient) -> bool:
    """Verify if a call is incall connected.

    .. hint:: This Use Case implements statements from the test suite such as:

        - (User) answers to (User)
        - Verify if a call is incall connected.

    :param who_is_incall_connected: SIP client on which connection needs to be checked
    :type who_is_incall_connected: VoiceClient
    :return: True if phone is incall connected.
    :rtype: bool
    """
    return who_is_incall_connected.is_incall_connected()


def is_call_on_hold(who_is_onhold: VoiceClient) -> bool:
    """Verify if a call is on hold.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a call is on hold.

    :param who_is_onhold: SIP client on which hold state needs to be checked
    :type who_is_onhold: VoiceClient
    :return: True if call is on hold.
    :rtype: bool
    """
    return who_is_onhold.is_onhold()


def is_call_in_conference(who_in_conference: VoiceClient) -> bool:
    """Verify if a call is in conference.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if a call is in conference.

    :param who_in_conference: SIP client on which conference state needs to be checked
    :type who_in_conference: VoiceClient
    :return: True if call is in conference state
    :rtype: bool
    """
    return who_in_conference.is_in_conference()


# FIXME: what is the difference with is_dialtone_detected()?
def is_playing_dialtone(who_is_playing_dialtone: VoiceClient) -> bool:
    """Verify if the phone is playing a dialtone.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if the phone is playing a dialtone.

    :param who_is_playing_dialtone: SIP Client
    :type who_is_playing_dialtone: VoiceClient
    :return: True if dialtone is playing else False
    :rtype: bool
    """
    return who_is_playing_dialtone.is_playing_dialtone()


def is_call_ended(whose_call_ended: VoiceClient) -> bool:
    """Verify if the call has been disconnected and ended.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if the call has been disconnected and ended.

    :param whose_call_ended: SIP Client
    :type whose_call_ended: VoiceClient
    :return: True if call is disconnected
    :rtype: bool
    """
    return whose_call_ended.is_call_ended()


# TODO: what does expired mean?
def is_code_ended(whose_code_ended: VoiceClient) -> bool:
    """Verify if the dialed code or number has expired.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if the dialed code or number has expired.

    :param whose_code_ended: SIP Client
    :type whose_code_ended: VoiceClient
    :return: True if code ended
    :rtype: bool
    """
    return whose_code_ended.is_code_ended()


def is_call_waiting(who_is_waiting: VoiceClient) -> bool:
    """Verify if the phone notifies for the call on other line to be waiting.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify if the phone notifies for the call on other line to be waiting.

    :param who_is_waiting: SIP Client
    :type who_is_waiting: VoiceClient
    :return: True if call is in waiting
    :rtype: bool
    """
    return who_is_waiting.is_call_waiting()


# TODO: is in call *and* playing dialtone
def is_incall_playing_dialtone(who_is_playing_incall_dialtone: VoiceClient) -> bool:
    """Verify phone is connected on one line and playing dialtone on another line.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify phone is connected on one line and playing dialtone on another line.

    :param who_is_playing_incall_dialtone: SIP Client
    :type who_is_playing_incall_dialtone: VoiceClient
    :return: True if call is incall playing dialtone state
    :rtype: bool
    """
    return who_is_playing_incall_dialtone.is_incall_playing_dialtone()


def is_off_hook_warning(who_has_offhook_warning: VoiceClient) -> bool:
    """Verify phone has been left off-hook without use for an extended period.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Verify phone has been left off-hook without use for an extended period.

    :param who_has_offhook_warning: SIP Client
    :type who_has_offhook_warning: VoiceClient
    :return: True if phone generates off hook warning state
    :rtype: bool
    """
    return who_has_offhook_warning.has_off_hook_warning()


def enable_call_forwarding_busy(
    who_forwards: VoiceClient,
    forward_to: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Enable call forwarding on a phone when busy.

    This thus forwards a call to another user

    .. hint:: This Use Case implements statements from the test suite such as:

        - Enable Call Forwarding Busy on (User) to (User)

    :param who_forwards: Agent that enables call forwarding busy
    :type who_forwards: VoiceClient
    :param forward_to: SIP Client to which agent forwards the call to
    :type forward_to: VoiceClient
    :param sip_srv: sip server
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("set_cf_busy")
    if vsc.endswith("#"):
        who_forwards.dial_feature_code(f"{vsc[:-1]}{forward_to.number}#")
    else:
        who_forwards.dial_feature_code(f"{vsc}{forward_to.number}")


def enable_call_forwarding_no_answer(
    who_forwards: VoiceClient,
    forward_to: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Enable call forwarding on a phone when there's no answer.

    This thus forwards a call to another user

    .. hint:: This Use Case implements statements from the test suite such as:

        - Enable Call Forwarding No Answer on (User) to (User)

    :param who_forwards: Agent that enables call forwarding no answer
    :type who_forwards: VoiceClient
    :param forward_to: SIP Client to which agent forwards the call to
    :type forward_to: VoiceClient
    :param sip_srv: SIP server to retrieve the Vertical Service Code from
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("set_cf_no_answer")
    if vsc.endswith("#"):
        who_forwards.dial_feature_code(f"{vsc[:-1]}{forward_to.number}#")
    else:
        who_forwards.dial_feature_code(f"{vsc}{forward_to.number}")


def disable_call_forwarding_no_answer(
    who_disables: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Disable call forwarding on a phone when not answered.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Disable call forwarding no answer on (User)

    :param who_disables: Agent that disables call forwarding no answer
    :type who_disables: VoiceClient
    :param sip_srv: SIP server to retrieve the Vertical Service Code from
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("unset_cf_no_answer")
    who_disables.dial_feature_code(vsc)


def disable_call_forwarding_busy(
    who_disables: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Disable call forwarding on a phone when busy.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Disable call forwarding on (User)

    :param who_disables: Agent that disables call forwarding busy
    :type who_disables: VoiceClient
    :param sip_srv: SIP server to retrieve the Vertical Service Code from
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("unset_cf_busy")
    who_disables.dial_feature_code(vsc)


def enable_unconditional_call_forwarding(
    who_forwards: VoiceClient,
    forward_to: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Enable unconditional call forwarding on a phone.

    This thus forwards a call to another user

    :param who_forwards: Agent that enables call forwarding busy
    :type who_forwards: VoiceClient
    :param forward_to: SIP Client to which agent forwards the call to
    :type forward_to: VoiceClient
    :param sip_srv: SIP server
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("set_cf_unconditional")
    if vsc.endswith("#"):
        who_forwards.dial_feature_code(f"{vsc[:-1]}{forward_to.number}#")
    else:
        who_forwards.dial_feature_code(f"{vsc}{forward_to.number}")


def disable_unconditional_call_forwarding(
    who_disables: VoiceClient,
    sip_srv: SIPServer,
) -> None:
    """Disable unconditional call forwarding on a phone.

    :param who_disables: Agent that disables call forwarding busy
    :type who_disables: VoiceClient
    :param sip_srv: SIP server to retrieve the Vertical Service Code from
    :type sip_srv: SIPServer
    """
    vsc = sip_srv.get_vsc_prefix("unset_cf_unconditional")
    who_disables.dial_feature_code(vsc)


def remove_user_profile(
    where_to_remove: VoiceServer,
    whom_to_remove: VoiceClient,
) -> None:
    """Deregister user profile from the SIP Server.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Remove the user profile of (User A) from SIP Server.

    :param where_to_remove: SIP Server
    :type where_to_remove: VoiceServer
    :param whom_to_remove: Phone device to be removed
    :type whom_to_remove: VoiceClient
    :raises VoiceError: if the device does not already exist on the SIP Server
    """
    if whom_to_remove.number not in where_to_remove.sipserver_get_online_users():
        msg = f"User {whom_to_remove.name} is not registered"
        raise VoiceError(msg)
    where_to_remove.remove_endpoint_from_sipserver(whom_to_remove.number)
    # TODO: the restart, as it might not be needed for some Voice servers, should be
    # part of the remove_enpoint_...() method
    where_to_remove.sipserver_restart()


def add_user_profile(where_to_add: VoiceServer, whom_to_add: VoiceClient) -> None:
    """Register user profile on the SIP Server.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Add user profile of (User) to the SIP Server.

    :param where_to_add: SIP Server
    :type where_to_add: VoiceServer
    :param whom_to_add: Phone device to be registered
    :type whom_to_add: VoiceClient
    :raises VoiceError: if the device already exist on the SIP Server
    """
    if whom_to_add.number in where_to_add.sipserver_get_online_users():
        msg = f"User {whom_to_add.name} is already registered"
        raise VoiceError(msg)
    where_to_add.sipserver_user_add(whom_to_add.number)
    # TODO: the need for restart should be specific to the SIP server device class
    where_to_add.sipserver_restart()


def is_user_profile_present(sip_proxy: VoiceServer, whose_profile: VoiceClient) -> bool:
    """Check whether the user profile is registered on the SIP Server or not.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Make sure that (User) is successfully registered.

    :param sip_proxy: SIP Server
    :type sip_proxy: VoiceServer
    :param whose_profile: Phone device to be checked
    :type whose_profile: VoiceClient
    :return: True if phone device is registered on the SIP Server
    :rtype: bool
    """
    return whose_profile.number in sip_proxy.sipserver_get_online_users()


def set_sip_expiry_time(sip_proxy: VoiceServer, to_what_time: int = 60) -> None:
    """Modify the call expires timer in the config file of the sip_proxy.

    .. hint:: This Use Case implements statements from the test suite such as:

        - Modify the call expires timer in the config file of the sip_proxy.

    :param sip_proxy: SIP Server
    :type sip_proxy: VoiceServer
    :param to_what_time: New expiry time to be set, defaults to 60
    :type to_what_time: int
    :raises VoiceError: if the sipserver is not installed
    """
    if sip_proxy.sipserver_status() in ["Not installed", "Not Running"]:
        msg = "Install the sipserver first"
        raise VoiceError(msg)
    sip_proxy.sipserver_set_expire_timer(
        to_timer=to_what_time,
    )


def get_sip_expiry_time(sip_proxy: VoiceServer) -> int:
    """Get the call expiry timer from the config file.

    :param sip_proxy: SIP server
    :type sip_proxy: VoiceServer
    :return: expiry timer saved in the config
    :rtype: int
    :raises VoiceError: if the SIP Server is not installed
    """
    if sip_proxy.sipserver_status() in ["Not installed", "Not Running"]:
        err_msg = "Install the sipserver first"
        raise VoiceError(err_msg)
    return sip_proxy.sipserver_get_expire_timer()


@contextmanager
def stop_and_start_sip_server(sip_proxy: VoiceServer) -> Generator[None, Any, None]:
    """Stop and start the SIP server.

    :param sip_proxy: The SIP server to be restarted
    :type sip_proxy: VoiceServer
    :yield: in between stopping and starting the SIP server
    :rtype: Generator[None, Any, None]
    """
    try:
        sip_proxy.stop()
        yield
    finally:
        sip_proxy.start()
