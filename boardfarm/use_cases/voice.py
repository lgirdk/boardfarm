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
from boardfarm.lib.network_testing import (
    check_mta_media_attribute,
    kill_process,
    rtp_flow_check,
    rtp_read_verify,
    tcpdump_capture,
)


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
    return who_is_playing_dialtone._obj().is_playing_dialtone()


def is_call_ended(whose_call_ended: VoiceClient) -> bool:
    return whose_call_ended._obj().is_call_ended()


def is_code_ended(whose_code_ended: VoiceClient) -> bool:
    return whose_code_ended._obj().is_code_ended()


def is_call_waiting(who_is_waiting: VoiceClient) -> bool:
    return who_is_waiting._obj().is_call_waiting()


def is_incall_playing_dialtone(who_is_playing_incall_dialtone: VoiceClient) -> bool:
    return who_is_playing_incall_dialtone._obj().is_incall_playing_dialtone()


def has_off_hook_warning(who_has_offhook_warning: VoiceClient) -> bool:
    return who_has_offhook_warning._obj().has_off_hook_warning()


def enable_call_waiting(agent: VoiceClient) -> None:
    """Enabled the call waiting.

    This will enable call waiting by dialing the desired number
    :param agent: Agent that enables call waiting
    :type agent: VoiceClient
    """
    agent._obj().enable_call_waiting()


def enable_call_forwarding_busy(
    who_forwards: VoiceClient, forward_to: VoiceClient
) -> None:
    """ """
    who_forwards._obj().enable_call_forwarding_busy(forward_to=forward_to)


def disable_call_waiting_overall(agent: VoiceClient) -> None:
    """ """
    agent._obj().disable_call_waiting_overall()


def disable_call_waiting_per_call(agent: VoiceClient) -> None:
    """ """
    agent._obj().disable_call_waiting_per_call()


def has_rtp_packet_flow(
    sip_server: VoiceServer,
    capture_file: str,
    source: VoiceClient,
    destination: VoiceClient,
    rm_file: bool = False,
    negate: bool = False,
) -> bool:
    """Function to check the RTP packets flow based on SIP/SDP Invite for given src and dst IP's
    and return bool based on validation
    :param sip_server: sipcenter where traces are collected
    :type sip_server: VoiceServer
    :param capture_file: pcap filename
    :type capture_file: str
    :param source: source of sip invite/rtp
    :type source: VoiceClient
    :param destination: dst_ip of sip invite/rtp
    :type destination: VoiceClient
    :param rm_file: Flag if same pcap is required for further verification
    :type rm_file: bool
    :param negate: To validate negative cases like no RTP flow
    :type negate: bool
    :return: Return bool based on validation
    :rtype: bool
    """
    for src, dst, rm in zip(
        [source.ip, sip_server.ip],
        [sip_server.ip, destination.ip],
        [False, rm_file],
    ):
        flow_check = rtp_flow_check(
            sip_server._obj(), capture_file, src, dst, rm_file=rm, negate=negate
        )
        if (not flow_check and not negate) or (flow_check and negate):
            return False
    return True


def has_rtp_packets(
    sip_server: VoiceServer, capture_file: str, msg_list: list, rm_pcap: bool = False
) -> bool:
    """To filter RTP packets from the captured file and verify. Delete the capture file after verify.
    Real-time Transport Protocol is for delivering audio and video over IP networks.
    :param sip_server: sipcenter where traces are collected
    :type sip_server: VoiceServer
    :param capture_file: Filename in which the packets were captured
    :type capture_file: String
    :param msg_list: list of 'rtp_msg' named_tuples having the source and
                    destination IPs of the endpoints
    :type msg_list: list
    :return: True if RTP messages found else False
    :rtype: Boolean
    """
    return rtp_read_verify(
        sip_server._obj(), capture_file, msg_list=msg_list, rm_pcap=rm_pcap
    )


def has_mta_media_attribute(
    sip_server: VoiceServer,
    capture_file: str,
    agent: VoiceClient,
    media_attr: str = "sendonly",
    port: int = 5060,
    timeout: int = 30,
    **kwargs,
) -> bool:
    """This function used to parse and verify the invite message media attribute
    :param sip_server: sipcenter where traces are collected
    :type sip_server: VoiceServer
    :param capture_file: pcap filename
    :type capture_file: str
    :param agent: SIP phone to verify mta media attribute
    :type agent: VoiceClient
    :param media_attr: Hold what type of media attribute needs to be captured; default is sendonly
    :type media_attr: String
    :param port: port hold what port the packet needs to be filtered; default is 5060
    :type port: Integer
    :param timeout: timeout value sent to tcpdump read; default is 30 seconds
    :type timeout: int
    :param return: Returns dictionary as result
    :type return: Dictionary
    """
    return check_mta_media_attribute(
        sip_server._obj(),
        capture_file,
        agent.number,
        media_attr=media_attr,
        port=port,
        timeout=timeout,
        **kwargs,
    )["status"]
