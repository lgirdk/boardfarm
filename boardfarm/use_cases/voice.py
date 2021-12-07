"""
Voice use cases library.

This module deals with only SIP end points.
All APIs are independent of board under test.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from time import sleep
from typing import Generator

from boardfarm.devices.base_devices.sip_template import SIPPhoneTemplate, SIPTemplate
from boardfarm.exceptions import CodeError
from boardfarm.lib.DeviceManager import get_device_by_name
from boardfarm.lib.network_testing import kill_process, tcpdump_capture


@dataclass
class VoiceClient:
    name: str
    ip: str
    number: str
    __obj: SIPPhoneTemplate

    def _obj(self) -> SIPPhoneTemplate:
        return self.__obj


@dataclass
class VoiceServer:
    name: str
    ip: str
    __obj: SIPTemplate

    def _obj(self):
        return self.__obj


def get_sip_proxy() -> VoiceServer:
    """Initialize and return SIP proxy details.

    :return: name and IP details of SIP proxy.
    :rtype: VoiceServer
    """
    sip_proxy: SIPTemplate = get_device_by_name("sipcenter")
    return VoiceServer(sip_proxy.name, str(sip_proxy.gw), sip_proxy)


@contextmanager
def tcpdump(
    dev: VoiceServer, fname: str, filters: str = ""
) -> Generator[str, None, None]:
    pid: str = ""
    device = dev._obj()
    try:
        pid = tcpdump_capture(
            device,
            device.iface_dut,
            capture_file=fname,
            return_pid=True,
            additional_filters=f"-s0 {filters}",
        )
        yield pid
    finally:
        kill_process(device, process="tcpdump", pid=pid)


def make_a_call(caller: VoiceClient, callee: VoiceClient) -> None:
    """To make a call by caller to callee

    :param caller: SIP agent who intiates the call
    :type caller: VoiceClient
    :param callee: SIP agent who receives the call
    :type callee: VoiceClient
    :raises CodeError: In case the call fails.
    """
    try:
        assert caller is not callee, "Caller and Caller cannot be same!"
        caller._obj().call(callee._obj())
        sleep(5)
    except Exception:
        raise CodeError(
            f"Failed to initiate a call between: {caller.name} --> {callee.name}"
        )


def put_phone_offhook(who_puts_offhook: VoiceClient) -> None:
    """Puts the phone off hook

    :param who_puts_offhook: SIP agent who puts phone off hook
    :type who_puts_offhook: VoiceClient
    """
    who_puts_offhook._obj().off_hook()


def answer_a_call(who_answers: VoiceClient) -> bool:
    """Answer a ringing call by target SIP agent.

    Execution order:
    - Ensure there is a ring on the target agent.
    - Pick up the call
    - Ensure the line is connected

    :param who_answers: SIP agent who is suppose to answer the call.
    :type who_answers: SIPPhoneTemplate
    :return: True if call is connected, else False
    :rtype: bool
    :raises CodeError: In case answering the call fails.
    """
    if not who_answers._obj().is_ringing():
        raise CodeError(f"{who_answers._obj().name} is not ringing!!")
    who_answers._obj().answer()

    return who_answers._obj().is_connected()


def disconnect_the_call(who_disconnects: VoiceClient) -> bool:
    """Disconnecting a call on a SIP agent.

    The user will not verify if the call is ongoing.
    It will simply call the on_hook implementation.

    :param who_disconnects: SIP agent who is suppose to disconnect the call.
    :type who_disconnects: VoiceClient
    :raises CodeError: In case disconnecting the call fails.
    :return: True if call is disconnected
    :rtype: bool
    """
    try:
        who_disconnects._obj().on_hook()
        sleep(5)
    except Exception:
        raise CodeError(f"Failed to disconnect the call: {who_disconnects.name}")
    return True


def is_dialtone_detected(agent: VoiceClient) -> bool:
    """Verify if a dialtone is detected off_hook.

    Device will be first placed on_hook.
    This is done to ensure disconnecting any previous sessions.

    After verifying dial tone device will again go back to on_hook state.

    :param agent: SIP agent used to verify dialtone.
    :type agent: VoiceClient
    :return: True if dialtone is detected.
    :rtype: bool
    """
    agent._obj().on_hook()
    return agent._obj().detect_dialtone()


def is_line_busy(on_which_agent: VoiceClient, who_is_busy: VoiceClient) -> bool:
    """To verify if the caller was notified that the callee is BUSY.

    Some phone will send this explicitly and will have RINGING 180
    as well inside their trace.

    :param on_which_agent: Caller who will receive BUSY
    :type on_which_agent: VoiceClient
    :param who_is_busy: Callee who replies BUSY
    :type who_is_busy: VoiceClient
    :return: True if caller received BUSY, else False
    :rtype: bool
    """
    assert on_which_agent is not who_is_busy, "Both args cannot be same"

    who_is_busy._obj().reply_with_code(486)
    return on_which_agent._obj().is_line_busy()


def is_call_not_answered(whose_call: VoiceClient) -> bool:
    """Verify if callee did not pick up the call

    The Caller will receive a NO CARRIER or TIMEOUT reply.

    :param whose_call: Callee
    :type whose_call: VoiceClient
    :return: True is not answered, else False
    :rtype: bool
    """
    return whose_call._obj().is_call_not_answered()


def initialize_phone(target_phone: str) -> VoiceClient:
    """Configure the phone, and start the application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: str
    """
    dev: SIPPhoneTemplate = get_device_by_name(target_phone)  # devices.fxs1
    sip_proxy: SIPTemplate = get_device_by_name("sipcenter")

    dev.phone_config(str(sip_proxy.gw))
    dev.phone_start()
    dev.on_hook()

    return VoiceClient(dev.name, str(dev.gw), dev.number, dev)


def shutdown_phone(target_phone: VoiceClient) -> None:
    """Go on_hook and stop the phone application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: SIPPhoneTemplate
    """
    dev = target_phone._obj()
    dev.on_hook()
    dev.phone_kill()


def answer_waiting_call(who_answers: VoiceClient) -> None:
    """Answer the waiting call and hang up on the current call.

    :param who_answers: SIP agent who is suppose to answer the call.
    :type who_answers: VoiceClient
    """
    who_answers._obj().answer_waiting_call()


def toggle_call(who_toggles: VoiceClient) -> None:
    """Toggle between the calls.

    Need to first validate, there is an incoming call on other line.
    If not throw an exception.

    :param who_toggles: SIP agent who is suppose to toggle the call
    :type who_toggles: VoiceClient
    :raises CodeError: In case there is no call to toggle to.
    """
    who_toggles._obj().toggle_call()


def merge_two_calls(who_is_conferencing: VoiceClient) -> None:
    """Merge the two calls for conference calling.

    Ensure call waiting must be enabled.
    There must be a call on other line to add to conference.

    :param who_is_conferencing: SIP agent that adds all calls in a conference.
    :type who_is_conferencing: VoiceClient
    :raises CodeError: In case there is no call to add for conferencing.
    """
    client: SIPPhoneTemplate = who_is_conferencing._obj()
    client.merge_two_calls()


def reject_waiting_call(who_rejects: VoiceClient) -> None:
    """Reject a call on waiting on second line.

    This will send the call to voice mail or a busy tone.
    There must be a call on the second line to reject.

    :param who_rejects: SIP agent who is suppose to reject the call.
    :type who_rejects: VoiceClient
    :raises CodeError: In case there is no call waiting to reject.
    """


def place_call_onhold(who_places: VoiceClient) -> None:
    """Place an ongoing call on-hold.
    There must be an active call to be placed on hold.

    :param who_places: SIP agent that is suppose to place the call on-hold.
    :type who_places: VoiceClient
    :raises CodeError: If there is no on-going call
    """
    client: SIPPhoneTemplate = who_places._obj()
    if not client.is_connected() and not client.is_incall_connected():
        raise CodeError("No active call in place!!")
    client.place_call_onhold()


def place_call_offhold(who_places: VoiceClient) -> None:
    """Place an ongoing call on hold to off-hold.
    There must be an active call to be placed off hold.

    :param who_places: SIP agent that is suppose to place the call off-hold.
    :type who_places: VoiceClient
    """
    client: SIPPhoneTemplate = who_places._obj()
    client.place_call_offhold()


def press_R_button(who_presses: VoiceClient) -> None:
    """Press the R button.

    Used when we put a call on hold, or during dialing.

    :param who_presses: Agent that presses the R button.
    :type who_presses: VoiceClient
    """
    client: SIPPhoneTemplate = who_presses._obj()
    client.press_R_button()


def is_call_dialing(who_is_dialing: VoiceClient) -> bool:
    """Verify if a phone is dialing and a call in progress

    :param who_is_dialing: SIP agent used to verify dialing
    :type who_is_dialing: VoiceClient
    :return: True if in progress dialing is detected
    :rtype: bool
    """
    return who_is_dialing._obj().is_dialing()


def is_incall_dialing(who_is_incall_dialing: VoiceClient) -> bool:
    """Verify if a phone is incall and call is dialing/in progress

    :param who_is_incall_dialing: SIP agent used to verify incall dialing
    :type who_is_incall_dialing: VoiceClient
    :return: True if in progress dialing is detected
    :rtype: bool
    """
    return who_is_incall_dialing._obj().is_incall_dialing()


def is_call_idle(who_is_idle: VoiceClient) -> bool:
    """Verify if a phone is in idle state

    :param who_is_idle: SIP agent used to verify idle
    :type who_is_idle: VoiceClient
    :return: True if idle is detected
    :rtype: bool
    """
    return who_is_idle._obj().is_idle()


def is_call_ringing(who_is_ringing: VoiceClient) -> bool:
    """Verify if a ringtone is detected on a phone device

    :param who_is_ringing: SIP agent used to verify ringtone
    :type who_is_ringing: VoiceClient
    :return: True if ringtone is detected
    :rtype: bool
    """
    return who_is_ringing._obj().is_ringing()


def is_call_connected(who_is_connected: VoiceClient) -> bool:
    """Verify if a call is connected

    :param who_is_connected: SIP client on which connection needs to be checked
    :type who_is_connected: VoiceClient
    :return: True if call is connected.
    :rtype: bool
    """
    return who_is_connected._obj().is_connected()


def is_incall_connected(who_is_incall_connected: VoiceClient) -> bool:
    """Verify if a call is incall connected

    :param who_is_incall_connected: SIP client on which connection needs to be checked
    :type who_is_incall_connected: VoiceClient
    :return: True if phone is incall connected.
    :rtype: bool
    """
    return who_is_incall_connected._obj().is_incall_connected()


def is_call_on_hold(who_is_onhold: VoiceClient) -> bool:
    """Verify if a call is on hold

    :param who_is_onhold: SIP client on which hold state needs to be checked
    :type who_is_onhold: VoiceClient
    :return: True if call is on hold.
    :rtype: bool
    """
    return who_is_onhold._obj().is_onhold()


def is_call_in_conference(who_in_conference: VoiceClient) -> bool:
    """Verify if a call is in conference

    :param who_in_conference: SIP client on which conference state needs to be checked
    :type who_in_conference: VoiceClient
    :return: True if call is in conference state
    :rtype: bool
    """
    return who_in_conference._obj().is_in_conference()


def is_playing_dialtone(who_is_playing_dialtone: VoiceClient) -> bool:
    """Verify if the phone is playing a dialtone

    :param who_is_playing_dialtone: SIP Client
    :type who_is_playing_dialtone: VoiceClient
    :return: True if dialtone is playing else False
    :rtype: bool
    """
    return who_is_playing_dialtone._obj().is_playing_dialtone()


def is_call_ended(whose_call_ended: VoiceClient) -> bool:
    """Verify if the call has been disconnected and ended

    :param whose_call_ended: SIP Client
    :type whose_call_ended: VoiceClient
    :return: True if call is disconnected
    :rtype: bool
    """
    return whose_call_ended._obj().is_call_ended()


def is_code_ended(whose_code_ended: VoiceClient) -> bool:
    """Verify if the dialed code or number has expired

    :param whose_code_ended: SIP Client
    :type whose_code_ended: VoiceClient
    :return: True if code ended
    :rtype: bool
    """
    return whose_code_ended._obj().is_code_ended()


def is_call_waiting(who_is_waiting: VoiceClient) -> bool:
    """Verify if the phone notifies for the call on other line to be waiting

    :param who_is_waiting: SIP Client
    :type who_is_waiting: VoiceClient
    :return: True if call is in waiting
    :rtype: bool
    """
    return who_is_waiting._obj().is_call_waiting()


def is_incall_playing_dialtone(who_is_playing_incall_dialtone: VoiceClient) -> bool:
    """Verify if the phone is connected on one line and playing dialtone on another line

    :param who_is_playing_incall_dialtone: SIP Client
    :type who_is_playing_incall_dialtone: VoiceClient
    :return: True if call is incall playing dialtone state
    :rtype: bool
    """
    return who_is_playing_incall_dialtone._obj().is_incall_playing_dialtone()


def is_off_hook_warning(who_has_offhook_warning: VoiceClient) -> bool:
    """Verify if the the phone has been left off-hook without use for an extended period

    :param who_has_offhook_warning: SIP Client
    :type who_has_offhook_warning: VoiceClient
    :return: True if phone generates off hook warning state
    :rtype: bool
    """
    return who_has_offhook_warning._obj().has_off_hook_warning()


def enable_call_waiting(who_enables: VoiceClient) -> None:
    """Enables the call waiting by dialing the desired number

    :param who_enables: Agent that enables call waiting
    :type who_enables: VoiceClient
    """
    who_enables._obj().enable_call_waiting()


def enable_call_forwarding_busy(
    who_forwards: VoiceClient, forward_to: VoiceClient
) -> None:
    """Enables call forwarding on a phone when busy which can then be used to forward a call to other no.

    :param who_forwards: Agent that enables call forwarding busy
    :type who_forwards: VoiceClient
    :param forward_to: SIP Client to which agent forwards the call to
    :type forward_to: VoiceClient
    """
    who_forwards._obj().enable_call_forwarding_busy(forward_to=forward_to)


def disable_call_waiting_overall(agent: VoiceClient) -> None:
    """Disables the call waiting overall on a phone by dialing a desired number

    :param agent: Agent that disables call waiting
    :type agent: VoiceClient
    """
    agent._obj().disable_call_waiting_overall()


def disable_call_waiting_per_call(agent: VoiceClient) -> None:
    """Disables the call waiting per call on a phone by dialing a desired number

    :param agent: Agent that disables call waiting
    :type agent: VoiceClient
    """
    agent._obj().disable_call_waiting_per_call()


def remove_user_profile(
    where_to_remove: VoiceServer, whom_to_remove: VoiceClient
) -> None:
    """Deregister user profile from the sip server

    :param where_to_remove: SIP Server
    :type where_to_remove: VoiceServer
    :param whom_to_remove: Phone device to be removed
    :type whom_to_remove: VoiceClient
    :raises CodeError: if the device does not already exist on the sip server
    """
    if whom_to_remove.number not in where_to_remove._obj().sipserver_get_online_users():
        raise CodeError(f"User {whom_to_remove.name} is not registered")
    where_to_remove._obj().sipserver_user_remove(whom_to_remove.number)
    where_to_remove._obj().sipserver_restart()


def add_user_profile(where_to_add: VoiceServer, whom_to_add: VoiceClient) -> None:
    """Registers user profile on the sip server

    :param where_to_add: SIP Server
    :type where_to_add: VoiceServer
    :param whom_to_add: Phone device to be registered
    :type whom_to_add: VoiceClient
    :raises CodeError: if the device already exist on the sip server
    """
    if whom_to_add.number in where_to_add._obj().sipserver_get_online_users():
        raise CodeError(f"User {whom_to_add.name} is already registered")
    where_to_add._obj().sipserver_user_add(whom_to_add.number)
    where_to_add._obj().sipserver_restart()


def is_user_profile_present(sip_proxy: VoiceServer, whose_profile: VoiceClient) -> bool:
    """Checks whether the user profile is registered on the sip server or not

    :param sip_proxy: SIP Server
    :type sip_proxy: VoiceServer
    :param whose_profile: Phone device to be checked
    :type whose_profile: VoiceClient
    :return: True if phone device is registered on the sip server
    :rtype: bool
    """
    return whose_profile.number in sip_proxy._obj().sipserver_get_online_users()


def set_sip_expiry_time(sip_proxy: VoiceServer, to_what_time: int = 60) -> None:
    """Modify the call expires timer in the config file of the sip_proxy eg: kamailio.cfg for Kamailio sipserver

    :param sip_proxy: SIP Server
    :type sip_proxy: VoiceServer
    :param to_what_time: New expiry time to be set. Defaults to 60., defaults to 60
    :type to_what_time: int, optional
    :raises CodeError: if the sipserver is not installed
    """
    if sip_proxy._obj().sipserver_status() in ["Not installed", "Not Running"]:
        raise CodeError("Install the sipserver first")
    sip_proxy._obj().sipserver_set_expire_timer(to_timer=to_what_time)
